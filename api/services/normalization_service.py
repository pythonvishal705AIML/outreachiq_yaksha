
import logging
import re

logger = logging.getLogger(__name__)

class NormalizationService:
    """
    Service to normalize filter inputs into canonical schemas as defined in Module E3.
    """

    # --- TAXONOMIES ---
    
    INDUSTRIES = {
        "Software": ["software", "saas", "tech", "technology", "information technology", "it"],
        "Real Estate": ["real estate", "property", "realty", "housing"],
        "Property Management": ["property management", "prop mgmt", "facility management"],
        "Finance": ["finance", "financial services", "banking", "investment", "fintech"],
        "Healthcare": ["healthcare", "health", "medical", "hospital", "clinic"],
        "Retail": ["retail", "ecommerce", "e-commerce", "shopping"],
        "Manufacturing": ["manufacturing", "industrial", "factory", "production"],
        "Education": ["education", "school", "university", "college", "edtech"],
        "Marketing": ["marketing", "advertising", "agency", "pr"],
        "Consulting": ["consulting", "professional services", "legal", "law"],
    }

    SENIORITY_LEVELS = {
        "owner": ["owner", "founder", "co-founder", "partner", "principal"],
        "c-level": ["ceo", "cto", "cfo", "coo", "cmo", "cio", "ciso", "president", "chief"],
        "vp": ["vp", "vice president", "head of"],
        "director": ["director", "dir."],
        "manager": ["manager", "lead", "supervisor", "mgr"],
        "senior": ["senior", "sr.", "principal"],
        "entry": ["junior", "jr.", "associate", "analyst", "intern", "staff"]
    }

    EMPLOYEE_RANGES = [
        "1,10", "11,20", "21,50", "51,100", "101,200", "201,500", 
        "501,1000", "1001,5000", "5000,10000", "10000+"
    ]

    CONTACT_EMAIL_STATUSES = ["verified"]

    # REVENUE RANGES (Mock structure for frontend)
    REVENUE_RANGES_UI = [
        {"label": "< $1M", "min": 0, "max": 1000000},
        {"label": "$1M - $10M", "min": 1000000, "max": 10000000},
        {"label": "$10M - $50M", "min": 10000000, "max": 50000000},
        {"label": "$50M+", "min": 50000000, "max": None}
    ]


    DEPARTMENTS = {
        "engineering": ["engineering", "developer", "software", "tech", "r&d"],
        "sales": ["sales", "account executive", "business development", "sdr", "ae", "bdr"],
        "marketing": ["marketing", "growth", "brand", "content", "social media"],
        "operations": ["operations", "ops", "logistics", "supply chain", "facility"],
        "finance": ["finance", "accounting", "audit", "tax", "controller"],
        "hr": ["hr", "human resources", "people", "recruiting", "talent"],
        "legal": ["legal", "counsel", "lawyer", "attorney"],
        "product": ["product", "pm", "owner"],
    }

    STATE_MAP = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
        "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
        "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
        "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
        "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
        "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
        "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
        "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
        "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
        "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"
    }

    COUNTRY_MAP = {
        "US": "United States", "USA": "United States", "UNITED STATES": "United States",
        "CA": "Canada", "CANADA": "Canada",
        "UK": "United Kingdom", "GB": "United Kingdom", "GREAT BRITAIN": "United Kingdom",
        "United Kingdom": "United Kingdom",
        "AU": "Australia", "AUSTRALIA": "Australia",
        "DE": "Germany", "GERMANY": "Germany",
        "FR": "France", "FRANCE": "France",
        "IN": "India", "INDIA": "India"
    }

    @staticmethod
    def normalize_filters(input_filters):
        """
        Main entry point. Takes raw filter dict and returns normalized schema + warnings.
        Matches Module E3 Canonical Schema.
        """
        normalized = input_filters.copy()
        warnings = []
        
        # 1. Normalize Industries
        if "industries" in normalized:
            # Map strings to clean list
            clean_inds = []
            for ind in normalized["industries"]:
                if isinstance(ind, dict):
                    # Already formatted? take value or label
                    val = ind.get("code") or ind.get("value") or ind.get("label")
                else:
                    val = ind
                
                mapped = NormalizationService._map_industry(val)
                clean_inds.append(mapped)
            
            normalized["industries"] = list(set(clean_inds))

        # 2. Normalize Locations
        if "locations" in normalized:
            norm_locs = []
            for loc in normalized["locations"]:
                if isinstance(loc, str):
                   norm_locs.append(NormalizationService._parse_location_string(loc))
                elif isinstance(loc, dict):
                   norm_locs.append(NormalizationService._normalize_location_object(loc))
            normalized["locations"] = norm_locs

        # 3. Normalize Roles
        if "roles" in normalized:
            normalized["roles"] = [r.title() for r in normalized["roles"]]

        # 4. Range Validation (Revenue)
        if "revenue_range" in normalized:
            rng = normalized["revenue_range"]
            if rng:  # Ensure not None
                min_val = rng.get("min_usd")
                max_val = rng.get("max_usd")
                
                # Auto-swap if inverted
                if min_val is not None and max_val is not None and min_val > max_val:
                    normalized["revenue_range"] = {"min_usd": max_val, "max_usd": min_val}
                    warnings.append({"field": "revenue_range", "message": "Swapped min and max values automatically."})

        # 5. Range Validation (Employees)
        if "company_size" in normalized:
            rng = normalized["company_size"]
            if rng:
                min_val = rng.get("employees_min")
                max_val = rng.get("employees_max")
                
                if min_val is not None and max_val is not None and min_val > max_val:
                    normalized["company_size"] = {"employees_min": max_val, "employees_max": min_val}
                    warnings.append({"field": "company_size", "message": "Swapped min and max values automatically."})

        # 6. Boolean Consistency (Email)
        if "email_requirements" in normalized:
            email_reqs = normalized["email_requirements"]
            if email_reqs.get("work_email_only") is True:
                if email_reqs.get("personal_email_allowed") is True:
                    normalized["email_requirements"]["personal_email_allowed"] = False
                    warnings.append({"field": "email_requirements", "message": "Disabled personal emails because work_email_only is True."})

        return {"filters": normalized, "warnings": warnings}

        return {"filters": normalized, "warnings": warnings}

    @staticmethod
    def _map_industry(raw_value):
        """
        Maps a raw string (e.g. 'saas') to a canonical industry ('Software').
        """
        if not raw_value: return "Unknown"
        raw_lower = str(raw_value).lower().strip()
        
        # Check reverse map
        for canonical, keywords in NormalizationService.INDUSTRIES.items():
            if raw_lower == canonical.lower():
                return canonical
            if raw_lower in keywords:
                return canonical
        
        return raw_value.title()  # Fallback

    @staticmethod
    def _parse_location_string(loc_str):
        """
        Parses "Austin, TX" -> {city: Austin, region: Texas, country: US}
        """
        if not loc_str: return {"type": "unknown"}
        parts = [p.strip() for p in loc_str.split(",")]
        
        if len(parts) == 1:
            val = parts[0]
            # Check country
            if val.upper() in NormalizationService.COUNTRY_MAP:
                return {"country": NormalizationService.COUNTRY_MAP[val.upper()], "type": "country"}
            if val.title() in NormalizationService.COUNTRY_MAP.values():
                return {"country": val.title(), "type": "country"}
            
            # Check state
            if val.upper() in NormalizationService.STATE_MAP:
                 return {"region": NormalizationService.STATE_MAP[val.upper()], "country": "United States", "type": "region"}
            
            # Assume City
            return {"city": val.title(), "type": "city"}
            
        elif len(parts) >= 2: # Flexible handling
            part1 = parts[0]
            part2 = parts[1] # Try 2nd part as state or country
            
            if part2.upper() in NormalizationService.STATE_MAP:
                return {
                    "city": part1.title(),
                    "region": NormalizationService.STATE_MAP[part2.upper()],
                    "country": "United States",
                    "type": "city"
                }
            
            if part2.upper() in NormalizationService.COUNTRY_MAP:
                 return {
                    "city": part1.title(),
                    "country": NormalizationService.COUNTRY_MAP[part2.upper()],
                    "type": "city"
                }
                
        return {"raw": loc_str, "type": "unknown"}

    @staticmethod
    def _normalize_location_object(loc_obj):
        """Standardizes fields within a location object."""
        new_loc = loc_obj.copy()
        if "region" in new_loc:
            r = new_loc["region"].upper()
            if r in NormalizationService.STATE_MAP:
                new_loc["region"] = NormalizationService.STATE_MAP[r]
        
        if "country" in new_loc:
            c = new_loc["country"].upper()
            if c in NormalizationService.COUNTRY_MAP:
                new_loc["country"] = NormalizationService.COUNTRY_MAP[c]
                
        return new_loc

    # --- NEW STATIC DATASETS ---
    COMMON_TITLES = [
        "CEO", "CTO", "CFO", "COO", "CMO", "Founder", "Co-Founder", "Owner", "President",
        "Vice President", "Director", "Manager", "Lead", "Head of Sales", "Head of Marketing",
        "Software Engineer", "Account Executive", "Product Manager", "Data Scientist", "HR Manager"
    ]

    COMMON_KEYWORDS = [
        "SaaS", "B2B", "Artificial Intelligence", "Machine Learning", "Healthcare", "Fintech",
        "E-commerce", "Startups", "Enterprise", "Digital Marketing", "Cloud Computing", "Cybersecurity"
    ]

    COMMON_TECHNOLOGIES = [
        {"id": "salesforce", "label": "Salesforce"},
        {"id": "hubspot", "label": "HubSpot"},
        {"id": "shopify", "label": "Shopify"},
        {"id": "aws", "label": "AWS"},
        {"id": "google_cloud", "label": "Google Cloud"},
        {"id": "react", "label": "React"},
        {"id": "python", "label": "Python"},
        {"id": "stripe", "label": "Stripe"}
    ]

    SAMPLE_DOMAINS = ["google.com", "microsoft.com", "apple.com", "amazon.com", "stripe.com"]

    @staticmethod
    def get_options():
        """
        Returns all static taxonomy lists for the frontend (API 6.2).
        Returns list of objects {code: ..., label: ...} where appropriate.
        """
        
        # Format Industries
        inds = []
        for ind in sorted(list(NormalizationService.INDUSTRIES.keys())):
            inds.append({"code": ind.upper().replace(" ", "_"), "label": ind})
            
        # Format Seniority
        sen_levels = []
        for level in sorted(list(NormalizationService.SENIORITY_LEVELS.keys())):
            sen_levels.append({"id": level, "label": level.replace("-", " ").title()})

        # Format Sources
        sources = [
            {"id": "upload", "label": "Excel/CSV Upload"},
            {"id": "clearbit", "label": "Clearbit"},
            {"id": "linkedin", "label": "LinkedIn"},
            {"id": "google_business", "label": "Google Business"}
        ]
        
        # Format Locations (Countries + States)
        locations = []
        for code, name in NormalizationService.COUNTRY_MAP.items():
             locations.append({"id": name, "label": name, "type": "country"})
        for code, name in NormalizationService.STATE_MAP.items():
            locations.append({"id": f"{name}, US", "label": f"{name}, US", "type": "state"})
            
        return {
            # --- EXISTING UI KEYS ---
            "seniority_levels": sen_levels,
            "employee_ranges": NormalizationService.EMPLOYEE_RANGES,
            "revenue_ranges": NormalizationService.REVENUE_RANGES_UI,
            "email_statuses": NormalizationService.CONTACT_EMAIL_STATUSES,
            "sources": sources,
            # --- LEAD SEARCH FILTER KEYS (Fully Populated) ---
            "q_keywords": NormalizationService.COMMON_KEYWORDS,
            "person_titles": NormalizationService.COMMON_TITLES,
            "person_seniorities": sen_levels,
            "person_locations": locations,
            "organization_locations": locations,
            "organization_num_employees_ranges": NormalizationService.EMPLOYEE_RANGES,
            "revenue_range": NormalizationService.REVENUE_RANGES_UI,
            "q_organization_domains_list": NormalizationService.SAMPLE_DOMAINS,
            "contact_email_status": NormalizationService.CONTACT_EMAIL_STATUSES,
            "q_organization_job_titles": NormalizationService.COMMON_TITLES, # Use common titles for job postings too
            "organization_num_jobs_range": [{"min": 1, "max": 10}, {"min": 10, "max": 50}], # Sample ranges
            "q_organization_keyword_tags": inds,
            "q_organization_name": ["Microsoft", "Google", "OpenAI"], # Sample names
            "organization_ids": [], # IDs are internal, keep empty or sample if needed
            "organization_job_locations": locations,        
            }
