import json
import logging
import time
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from api.clients.llm_client import LLMClient
from api.services.rag_service import RAGService
from api.prompts import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# Strict Schema Definition for the LLM
EXTRACTION_SCHEMA = {
    "name": "Business Name",
    "industry": "Primary industry classification",
    "brand_voice": "Adjectives describing the brand's tone. Select ONE from: 'professional', 'casual', 'friendly', 'authoritative', 'luxury'.",
    "business_model": "b2b, b2c, Marketplace, SaaS, etc.",
    "phone": "Contact phone number or null",
    "address": "Full physical address or null",
    "hqcity": "Headquarters City or null",
    "hqstate": "Headquarters State/Region or null",
    "hqcountry": "Headquarters Country Code or null",
    "postal_code": "Postal/Zip Code or null",
    "website": "Website URL",
    "description": "Short business description (max 200 chars)",
    "sub_industry": "More specific niche or null",
    "operating_regions": ["List of regions they operate in. Select from: 'local' , 'nationwide','international','region-specific'."],
    "tone_preferences": ["List of email tone preferences. Select from: 'direct', 'story-driven', 'value-first', 'soft-sell'."],
    "revenue_range": "Estimated revenue range or null",
    "services": ["List of 5 services offered"],
    "type": "Company type. Select ONE from: 'agency', 'real-estate', 'healthcare', 'saas', 'consulting', 'ecommerce', 'finance', 'education'.",
    "signature_format": "Predicted email signature format. Select ONE from: 'full-name-title', 'name-only', 'full-brand-footer'.",
    "product": "Main product line or null",
    "timezone": "Timezone identifier (e.g., 'US/Eastern', 'US/Central', 'UTC').",
}


# ──────────────────────────────────────────────
# FIX 1: Rotate User-Agents to avoid blocks
# ──────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Minimum characters of useful content from a scrape
MIN_USEFUL_CONTENT = 200


class BusinessExtractor:
    def __init__(self):
        self.llm_client = LLMClient()
        self.model = "gpt-5-mini-2025-08-07"
        self._ua_index = 0

    # ──────────────────────────────────────────────
    # FIX 2: Full browser-like headers
    # ──────────────────────────────────────────────
    def _get_headers(self) -> dict:
        """Returns full browser-like headers with rotating User-Agent."""
        ua = USER_AGENTS[self._ua_index % len(USER_AGENTS)]
        self._ua_index += 1
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    # ──────────────────────────────────────────────
    # FIX 3: Session + retry + longer timeout
    # FIX 4: Minimum content check
    # ──────────────────────────────────────────────
    def _fetch_single_page(self, url: str) -> tuple[str, list[str]]:
        """
        Fetches text and extracts internal links from a single page.
        Retries with different User-Agent if first attempt fails.
        """
        max_retries = 2

        for attempt in range(max_retries):
            try:
                session = requests.Session()
                headers = self._get_headers()
                response = session.get(
                    url,
                    headers=headers,
                    timeout=10,
                    allow_redirects=True,
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # 1. Extract internal links (BEFORE cleaning)
                internal_links = []
                base_domain = urlparse(url).netloc

                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    full_url = urljoin(url, href)
                    parsed_url = urlparse(full_url)

                    if parsed_url.netloc == base_domain and parsed_url.scheme in ["http", "https"]:
                        lower_href = full_url.lower()
                        if any(
                            x in lower_href
                            for x in [
                                "about", "contact", "services", "team",
                                "career", "product", "solution",
                                "who we are", "reach us", "what we do",
                                "who-we-are", "reach-us", "what-we-do",
                            ]
                        ):
                            internal_links.append(full_url)

                # 2. Remove junk elements
                for element in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
                    element.decompose()

                # 3. Extract clean text
                text = soup.get_text(separator=" ")
                clean_text = " ".join(text.split())

                # FIX 4: Check if we got meaningful content
                if len(clean_text) < 50:
                    logger.warning(f"Page returned very little text ({len(clean_text)} chars): {url}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return "", []

                return clean_text, internal_links

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                logger.warning(f"HTTP {status_code} for {url} (attempt {attempt + 1}/{max_retries})")

                # Don't retry on 403/404 — these won't change
                if status_code in (403, 404):
                    return "", []

                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                return "", []

        return "", []

    # ──────────────────────────────────────────────
    # FIX 5: Backup fetcher using httpx
    # Install: pip install httpx
    # ──────────────────────────────────────────────
    def _fetch_with_httpx(self, url: str) -> str:
        """Backup fetcher using httpx for sites that block requests."""
        try:
            import httpx
            with httpx.Client(
                follow_redirects=True,
                timeout=15,
                headers=self._get_headers(),
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for element in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
                    element.decompose()
                text = " ".join(soup.get_text(separator=" ").split())
                return text
        except ImportError:
            logger.warning("httpx not installed. Skipping httpx fallback. Run: pip install httpx")
            return ""
        except Exception as e:
            logger.warning(f"httpx fallback failed for {url}: {e}")
            return ""

    def crawl_website(self, start_url: str, max_pages: int = 12) -> str:
        """
        Crawls the website starting from start_url.
        Visits up to max_pages unique internal links.
        Returns aggregated text context.
        """
        visited = set()
        queue = [start_url]
        aggregated_text = []

        count = 0

        while queue and count < max_pages:
            current_url = queue.pop(0)

            if current_url in visited:
                continue

            visited.add(current_url)
            logger.info(f"Crawling: {current_url}")

            text, links = self._fetch_single_page(current_url)

            # FIX 5: If primary fetch got no/thin content, try httpx
            if not text or len(text) < 50:
                logger.info(f"Primary fetch got no content. Trying httpx for: {current_url}")
                text = self._fetch_with_httpx(current_url)
                links = []  # httpx version doesn't extract links

            if text:
                aggregated_text.append(f"--- SOURCE: {current_url} ---\n{text}\n")
                count += 1

            # Add new unique links to queue
            for link in links:
                if link not in visited and link not in queue:
                    queue.append(link)

        logger.info(f"Crawl Complete. Visited {count} pages.")
        return "\n".join(aggregated_text)

    # ──────────────────────────────────────────────
    # FIX 6: LLM fallback when scraping fails
    # ──────────────────────────────────────────────
    def _llm_fallback_extract(self, name: str, url: str) -> dict:
        """
        When scraping fails, ask the LLM to fill in what it
        already knows about the company from its training data.
        """
        try:
            fallback_prompt = f"""You are a business intelligence assistant with deep knowledge of companies worldwide.

The website "{url}" for company "{name}" could not be scraped.
Using ONLY your existing knowledge about this company, fill in the JSON schema below.
Be as specific and accurate as possible.
If you truly don't know a field, set it to null.

IMPORTANT RULES:
- "industry" must be filled if you know anything about the company
- "description" must be a real description, not empty string
- "services" should list their actual products/services
- "business_model" should be "b2b", "b2c", "SaaS", etc.
- Do NOT return empty strings "" — use null if unknown
- For well-known companies, you should know most fields

Schema:
{json.dumps(EXTRACTION_SCHEMA, indent=2)}

Return ONLY valid JSON. No markdown, no explanation."""

            messages = [{"role": "user", "content": fallback_prompt}]

            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                json_mode=True,
            )
            data = json.loads(response_text)

            # Ensure critical fields
            data["name"] = data.get("name") or name
            data["website"] = data.get("website") or url
            data["_source"] = "llm_knowledge"

            # Validate: if LLM returned mostly empty, treat as failure
            filled_count = 0
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if v is not None and v != "" and v != [] and v != "null":
                    filled_count += 1

            if filled_count < 5:
                logger.warning(f"LLM fallback too sparse for {name} ({filled_count} fields filled)")
                return None

            logger.info(f"LLM fallback succeeded for {name} ({filled_count} fields filled)")
            return data

        except Exception as e:
            logger.warning(f"LLM fallback failed for {name}: {e}")
            return None

    # ──────────────────────────────────────────────
    # FIX 7: extract() NEVER raises — always returns data
    # Fallback chain: Scrape -> LLM Knowledge -> Empty Schema
    # ──────────────────────────────────────────────
    def extract(self, name: str, url: str) -> dict:
        """
        Main entry point: Scrape -> Prompt -> Parse.
        NEVER raises an exception — always returns usable data.

        Fallback chain:
        1. Scrape website + RAG + LLM extraction (best quality)
        2. LLM knowledge fallback (for blocked/JS-rendered sites)
        3. Empty schema (worst case, user fills manually)
        """
        logger.info(f"Starting Business Extraction for: {name} ({url})")

        # ── Step 1: Scrape (Crawl) ──
        raw_text = ""
        try:
            raw_text = self.crawl_website(url, max_pages=12)
        except Exception as e:
            logger.warning(f"Crawling failed for {url}: {e}")

        # ── Step 2: Check if we got enough content ──
        # JS-rendered sites (React, Next.js) return HTML shell but no real text
        if not raw_text or len(raw_text.strip()) < MIN_USEFUL_CONTENT:
            logger.warning(
                f"Insufficient content from {url} "
                f"({len(raw_text.strip()) if raw_text else 0} chars, need {MIN_USEFUL_CONTENT}). "
                f"Site may be JS-rendered or blocked. Trying LLM fallback..."
            )

            # Try LLM knowledge fallback
            fallback_data = self._llm_fallback_extract(name, url)
            if fallback_data:
                return fallback_data

            # If LLM fallback also fails, return empty schema
            logger.warning(f"All extraction methods failed for {name}. Returning empty schema.")
            empty = self._get_empty_schema(name, url)
            empty["_source"] = "empty_fallback"
            return empty

        # ── Step 3: RAG Filtering (only if we have good content) ──
        try:
            rag = RAGService()
            rag.add_text(raw_text)

            queries = [
                f"Overview and mission statement of {name}",
                f"Headquarters address location and contact details phone email for {name}",
                f"List of services products and solutions offered by {name}",
                f"Business model brand voice and target audience industries for {name}",
                f"Company leadership size employee count revenue and history details for {name}",
            ]

            context_text = rag.retrieve_multiple(queries, k_per_query=5)

        except Exception as e:
            logger.warning(f"RAG failed, falling back to raw text: {e}")
            context_text = raw_text

        # ── Step 4: Prepare Prompt ──
        prompt = EXTRACTION_PROMPT.format(
            schema=json.dumps(EXTRACTION_SCHEMA, indent=2),
            website_text=context_text,
        )

        messages = [{"role": "system", "content": prompt}]

        # ── Step 5: Call LLM for extraction ──
        try:
            response_text = self.llm_client.get_completion(
                messages=messages,
                model=self.model,
                json_mode=True,
            )
            data = json.loads(response_text)

            # Ensure critical fields
            data["name"] = data.get("name") or name
            data["website"] = data.get("website") or url
            data["_source"] = "website_extraction"

            # ── Step 6: Quality check ──
            # If extraction returned mostly empty despite having scraped content,
            # the scraped text was probably garbage (JS bundles, cookie banners, etc.)
            filled_count = 0
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if v is not None and v != "" and v != [] and v != "null":
                    filled_count += 1

            if filled_count < 5:
                logger.warning(
                    f"Website extraction too sparse ({filled_count} fields). "
                    f"Scraped text was likely garbage. Trying LLM knowledge fallback..."
                )
                fallback_data = self._llm_fallback_extract(name, url)
                if fallback_data:
                    return fallback_data

            return data

        except Exception as e:
            logger.error(f"LLM Extraction failed: {e}")

            # Last resort: try LLM knowledge fallback
            fallback_data = self._llm_fallback_extract(name, url)
            if fallback_data:
                return fallback_data

            return self._get_empty_schema(name, url)

    def _get_empty_schema(self, name, url):
        """Returns a null-filled object structure."""
        empty = {k: None for k in EXTRACTION_SCHEMA.keys()}
        empty["name"] = name
        empty["website"] = url
        empty["operating_regions"] = []
        empty["tone_preferences"] = []
        empty["services"] = []
        empty["timezone"] = "UTC"
        return empty
