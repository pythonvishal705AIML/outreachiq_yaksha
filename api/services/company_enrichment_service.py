import logging
from typing import Optional, Dict, Any

from django.utils import timezone

from ..models import Lead, Company
from .business_extractor import BusinessExtractor

logger = logging.getLogger(__name__)

class CompanyEnrichmentService:
    """
    Uses the internal scraper + LLM (BusinessExtractor) to enrich company
    details for a Lead.

    Strategy:
    - Resolve a website URL from lead/company:
        - Prefer an explicit website on the Company model.
        - Otherwise, build https://{company_domain} when available.
    - Call BusinessExtractor.extract(name, url) to get a structured JSON dict.
    - Map that dict into Company + denormalized fields on Lead.
    """

    @staticmethod
    def _build_website_url(company_domain: Optional[str], fallback_url: Optional[str]) -> Optional[str]:
        if fallback_url:
            return fallback_url
        if not company_domain:
            return None
        if company_domain.startswith("http://") or company_domain.startswith("https://"):
            return company_domain
        return f"https://{company_domain}"

    @staticmethod
    def enrich_lead_company(lead: Lead) -> Optional[Dict[str, Any]]:
        """
        Enriches the lead's company via scraper + LLM and updates the DB.

        Returns a dict with the enriched company snapshot (what should go into
        `company_details` in your API response), or None if enrichment failed.
        """
        try:
            if not lead.company_name and not (lead.company and lead.company.name):
                logger.info(f"Skipping company enrichment for lead {lead.id}: no company name.")
                return None

            company_name = lead.company_name or (lead.company.name if lead.company else None)
            existing_domain = lead.company_domain or (lead.company.domain if lead.company else None)
            existing_website = lead.company.website if lead.company and lead.company.website else None

            website_url = CompanyEnrichmentService._build_website_url(existing_domain, existing_website)
            if not website_url:
                logger.info(
                    f"Skipping company enrichment for lead {lead.id}: "
                    f"no domain/website available for '{company_name}'."
                )
                return None

            # 1) Call scraper + LLM
            extractor = BusinessExtractor()
            business_data = extractor.extract(name=company_name, url=website_url)
            if not business_data:
                logger.info(
                    f"BusinessExtractor returned no data for '{company_name}' "
                    f"(lead {lead.id})."
                )
                return None

            # 2) Upsert Company model
            company_obj = lead.company

            if not company_obj:
                # Prefer domain match, then name
                if existing_domain:
                    company_obj = Company.objects.filter(domain=existing_domain).first()
                if not company_obj and company_name:
                    company_obj = Company.objects.filter(name=company_name).first()

            if not company_obj:
                company_obj = Company(
                    domain=existing_domain,
                    name=company_name,
                )

            # Map BusinessExtractor -> Company fields
            company_obj.name = business_data.get("name") or company_obj.name

            # Domain/website
            scraped_website = business_data.get("website")
            if scraped_website and not scraped_website.startswith(("http://", "https://")):
                scraped_website = f"https://{scraped_website}"
            # If we had a domain already, keep it; otherwise derive from scraped website if possible
            company_obj.website = scraped_website or company_obj.website
            if existing_domain:
                company_obj.domain = existing_domain
            else:
                # Best-effort: derive domain from website URL
                try:
                    from urllib.parse import urlparse

                    if scraped_website:
                        parsed = urlparse(scraped_website)
                        if parsed.netloc:
                            company_obj.domain = parsed.netloc
                except Exception:
                    pass

            # Industry
            company_obj.industry = business_data.get("industry") or company_obj.industry

            # Location / HQ
            company_obj.hq_city = business_data.get("hqcity") or company_obj.hq_city
            company_obj.hq_region = business_data.get("hqstate") or company_obj.hq_region
            company_obj.hq_country = business_data.get("hqcountry") or company_obj.hq_country

            # Revenue – BusinessExtractor returns a string "revenue_range"; we keep numeric
            # fields untouched unless you want to parse ranges explicitly.

            # Store raw scraper response for traceability
            source_meta = company_obj.source_meta or {}
            source_meta.setdefault("scraper", {})
            source_meta["scraper"]["last_enriched_at"] = timezone.now().isoformat()
            source_meta["scraper"]["business_data"] = business_data
            company_obj.source_meta = source_meta

            company_obj.last_seen_at = timezone.now()
            company_obj.save()

            # 3) Update denormalized fields on Lead
            lead.company = company_obj
            lead.company_name = company_obj.name or lead.company_name
            lead.company_domain = company_obj.domain or lead.company_domain
            lead.company_hq_city = company_obj.hq_city
            lead.company_hq_region = company_obj.hq_region
            lead.company_hq_country = company_obj.hq_country
            lead.industry = company_obj.industry or lead.industry
            lead.save(update_fields=[
                "company",
                "company_name",
                "company_domain",
                "company_hq_city",
                "company_hq_region",
                "company_hq_country",
                "industry",
                "updated_at",
            ])

            # 4) Return a snapshot payload you can embed in API
            enriched_payload: Dict[str, Any] = {
                "id": company_obj.id,
                "third_party_org_id": company_obj.third_party_org_id,
                "name": company_obj.name,
                "domain": company_obj.domain,
                "industry": company_obj.industry,
                "employees_min": company_obj.employees_min,
                "employees_max": company_obj.employees_max,
                "revenue_min_usd": company_obj.revenue_min_usd,
                "revenue_max_usd": company_obj.revenue_max_usd,
                "hq_city": company_obj.hq_city,
                "hq_region": company_obj.hq_region,
                "hq_country": company_obj.hq_country,
                "website": company_obj.website,
                "linkedin_url": company_obj.linkedin_url,
                "technologies": company_obj.technologies,
                "source_meta": company_obj.source_meta,
                "first_seen_at": company_obj.first_seen_at,
                "last_seen_at": company_obj.last_seen_at,
                "is_archived": company_obj.is_archived,
                "archived_at": company_obj.archived_at,
                "deleted_at": company_obj.deleted_at,
            }

            return enriched_payload

        except Exception as e:
            logger.error(
                f"Company enrichment failed for lead {getattr(lead, 'id', None)}: {e}",
                exc_info=True,
            )
            return None
