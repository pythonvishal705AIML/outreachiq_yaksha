import itertools
import time
import logging
import threading
import concurrent.futures
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Singleton Cache ──────────────────────────────────────────────
# Avoids 22 OpenAI embedding calls on every request by reusing the instance.
_singleton_lock = threading.Lock()
_singleton_instance = None


def get_normalizer():
    """Return a cached SearchFilterNormalizer instance (thread-safe singleton)."""
    global _singleton_instance
    if _singleton_instance is not None:
        logger.info("[SINGLETON] Cache HIT — skipping __init__ (0ms)")
        return _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _t = time.perf_counter()
            _singleton_instance = SearchFilterNormalizer()
            _ms = round((time.perf_counter() - _t) * 1000)
            logger.info(f"[SINGLETON] Cache MISS — cold init took {_ms}ms (next call = 0ms)")
    return _singleton_instance


class SearchFilterNormalizer:
    """
    Normalizes free-text lead-search filter values (titles, locations,
    seniorities, keywords, company sizes) into a canonical taxonomy via
    OpenAI-embedding cosine similarity against in-memory taxonomy lists.
    Source-agnostic: used for local-DB search filtering and LLM-extracted
    parameter cleanup, independent of any external lead-data API.
    """

    # Canonical taxonomy tags, matched against via embedding similarity.
    KEYWORDS = [
        "Enterprise IT", "Digital Transformation", "Cloud Computing", "Artificial Intelligence",
        "Machine Learning", "Cybersecurity", "SaaS", "B2B Software", "DevOps", "Data Analytics",
        "Business Intelligence", "ERP", "CRM", "Automation", "Robotic Process Automation",
        "Internet of Things", "Blockchain", "Big Data", "API Integration", "Microservices",
        "Infrastructure", "Network Security", "Software Development", "Agile", "Scrum",
        "Product Management", "Revenue Growth", "Sales Enablement", "Marketing Technology",
        "Customer Success", "Go-To-Market", "Lead Generation", "Account Management",
        "Financial Services", "Healthcare IT", "Supply Chain", "Logistics", "E-commerce",
        "Mobile Applications", "Web Development", "UI/UX Design", "Data Science",
        "Natural Language Processing", "Computer Vision", "Predictive Analytics",
        "Cloud Migration", "Hybrid Cloud", "Multi-cloud", "Platform Engineering",
        "Site Reliability Engineering", "Information Security", "Zero Trust",
        "Compliance", "GDPR", "SOC2", "Risk Management", "Digital Marketing",
        "Content Marketing", "SEO", "Performance Marketing", "Brand Strategy",
    ]

    PERSON_TITLES = [
        "Chief Executive Officer", "Chief Technology Officer", "Chief Information Officer",
        "Chief Operating Officer", "Chief Financial Officer", "Chief Marketing Officer",
        "Chief Revenue Officer", "Chief Product Officer", "Chief Data Officer",
        "VP of Engineering", "VP of Sales", "VP of Marketing", "VP of Product",
        "VP of Operations", "VP of Finance", "VP of Customer Success",
        "Director of Engineering", "Director of Sales", "Director of Marketing",
        "Director of Product Management", "Director of Operations", "Director of IT",
        "Director of Business Development", "Director of Data Science",
        "Head of Engineering", "Head of Sales", "Head of Marketing", "Head of Product",
        "Head of Data", "Head of Infrastructure", "Head of Security",
        "Senior Software Engineer", "Software Engineer", "Principal Engineer",
        "Staff Engineer", "Engineering Manager", "Product Manager", "Senior Product Manager",
        "Data Scientist", "Senior Data Scientist", "Machine Learning Engineer",
        "Data Engineer", "DevOps Engineer", "Platform Engineer", "Site Reliability Engineer",
        "Security Engineer", "Solutions Architect", "Enterprise Architect",
        "Business Analyst", "Sales Manager", "Account Executive", "Sales Development Representative",
        "Customer Success Manager", "Marketing Manager", "Growth Manager",
        "Founder", "Co-Founder", "Managing Director", "General Manager", "Partner",
    ]

    LOCATIONS = [
        "United States", "California", "New York", "Texas", "Florida", "Illinois",
        "Washington", "Massachusetts", "Georgia", "Colorado", "North Carolina",
        "San Francisco", "New York City", "Los Angeles", "Chicago", "Austin",
        "Seattle", "Boston", "Atlanta", "Denver", "Miami",
        "Canada", "Toronto", "Vancouver", "Montreal",
        "United Kingdom", "London", "Manchester", "Edinburgh",
        "Germany", "Berlin", "Munich", "Hamburg",
        "France", "Paris", "Lyon",
        "Netherlands", "Amsterdam",
        "Australia", "Sydney", "Melbourne",
        "India", "Bangalore", "Mumbai", "Delhi",
        "Singapore", "Japan", "Tokyo",
        "Israel", "Tel Aviv",
        "Brazil", "São Paulo",
        "Europe", "Asia Pacific", "North America", "EMEA", "APAC", "LATAM",
        "Remote", "Worldwide", "Global",
    ]

    def __init__(self):
        _t_init = time.perf_counter()

        self.openai = OpenAI()

        # ENUMS
        self.valid_seniority = [
            "owner","founder","c_suite","partner","vp",
            "head","director","manager","senior","entry","intern"
        ]

        self.valid_company_sizes = [
            "1,10","11,20","21,50","51,100","101,200",
            "201,500","501,1000","1001,2000",
            "2001,5000","5001,10000","10001"
        ]

        # ── Embedding Cache (must be before precompute calls) ────
        self._embed_cache = {}
        self._embed_cache_lock = threading.Lock()

        # Precompute enum + taxonomy embeddings efficiently (Batched)
        _t_embed = time.perf_counter()
        self._batch_precompute_enums()
        _embed_ms = round((time.perf_counter() - _t_embed) * 1000)

        _total_ms = round((time.perf_counter() - _t_init) * 1000)
        logger.info(
            f"[INIT LATENCY] SearchFilterNormalizer.__init__ completed in {_total_ms}ms "
            f"(Batched precomputation: {_embed_ms}ms)"
        )

        # Query scoring weights
        self.title_weight = 3
        self.keyword_weight = 2
        self.location_weight = 1
        self.size_weight = 1

    def _batch_precompute_enums(self):
        """Batch process embeddings to avoid individual sequential API calls."""
        all_enums = (
            self.valid_seniority + self.valid_company_sizes
            + self.KEYWORDS + self.PERSON_TITLES + self.LOCATIONS
        )

        try:
            # Batch embedding multiple inputs
            response = self.openai.embeddings.create(
                model="text-embedding-3-small",
                input=all_enums
            )
            with self._embed_cache_lock:
                for idx, text in enumerate(all_enums):
                    self._embed_cache[text] = response.data[idx].embedding

        except Exception as e:
            logger.error(f"Failed to batch embed enums: {e}")

        self.seniority_embeddings = {
            s: self._embed_cache.get(s, []) for s in self.valid_seniority if s in self._embed_cache
        }
        self.company_size_embeddings = {
            s: self._embed_cache.get(s, []) for s in self.valid_company_sizes if s in self._embed_cache
        }
        self.keyword_embeddings = {
            t: self._embed_cache[t] for t in self.KEYWORDS if t in self._embed_cache
        }
        self.title_embeddings = {
            t: self._embed_cache[t] for t in self.PERSON_TITLES if t in self._embed_cache
        }
        self.location_embeddings = {
            t: self._embed_cache[t] for t in self.LOCATIONS if t in self._embed_cache
        }

    # -------------------------
    # EMBEDDING
    # -------------------------

    def embed(self, text):
        with self._embed_cache_lock:
            if text in self._embed_cache:
                return self._embed_cache[text]

        response = self.openai.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )

        vec = response.data[0].embedding

        with self._embed_cache_lock:
            self._embed_cache[text] = vec

        return vec

    # -------------------------
    # COSINE SIMILARITY
    # -------------------------

    def cosine(self, a, b):
        if not len(a) or not len(b):
            return 0.0

        a = np.array(a)
        b = np.array(b)

        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    # -------------------------
    # TAG SEARCH (local embedding similarity)
    # -------------------------

    def search_tags(self, text, tag_embeddings, limit=5, threshold=0.85):
        if not text or not tag_embeddings:
            return []

        query_vec = self.embed(text)

        scored = [
            (self.cosine(query_vec, vec), tag)
            for tag, vec in tag_embeddings.items() if vec
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        # Primary path: only keep high-confidence tags.
        results = [tag for score, tag in top if score >= threshold]
        if results:
            return list(dict.fromkeys(results))

        # Fallback path: keep top semantic matches in case threshold is too strict.
        fallback_results = [tag for score, tag in top if score >= 0.45]
        return list(dict.fromkeys(fallback_results))

    # -------------------------
    # NORMALIZATION
    # -------------------------

    def normalize_titles(self, titles):
        try:
            resolved = []
            for t in titles:
                resolved.extend(self.search_tags(t, self.title_embeddings, limit=3, threshold=0.8))

            if not resolved:
                return list(dict.fromkeys([t for t in (titles or []) if t]))
            return list(set(resolved))
        except Exception as e:
            logger.error(f"Error normalizing titles: {e}")
            return list(dict.fromkeys([t for t in (titles or []) if t]))

    def normalize_keywords(self, keywords):
        try:
            resolved = []
            parts = keywords.split(";") if isinstance(keywords, str) else keywords
            for k in (parts or []):
                if isinstance(k, str) and k.strip():
                    resolved.extend(self.search_tags(k.strip(), self.keyword_embeddings, limit=3, threshold=0.75))

            if not resolved:
                return list(set([k.strip() for k in (parts or []) if isinstance(k, str) and k.strip()]))
            return list(set(resolved))
        except Exception as e:
            logger.error(f"Error normalizing keywords: {e}")
            return []

    def normalize_locations(self, locations):
        try:
            resolved = []
            parsed_locations = []

            for loc in (locations or []):
                if isinstance(loc, str):
                    parsed_locations.extend([l.strip() for l in loc.split(",") if l.strip()])
                else:
                    parsed_locations.append(loc)

            for loc in parsed_locations:
                matches = self.search_tags(loc, self.location_embeddings, limit=3, threshold=0.7)
                resolved.extend(matches)

            # Fallback: if vector lookup fails / returns nothing
            if not resolved:
                return list(set(parsed_locations))
            return list(set(resolved))
        except Exception as e:
            logger.error(f"Error normalizing locations: {e}")
            return list(set(locations or []))

    # -------------------------
    # SEMANTIC SENIORITY
    # -------------------------

    def normalize_seniority(self, seniorities):
        try:
            resolved = set()
            for text in seniorities:
                query_vec = self.embed(text)
                scores = []
                for key, vec in self.seniority_embeddings.items():
                    sim = self.cosine(query_vec, vec)
                    scores.append((sim, key))

                scores.sort(reverse=True)
                for s, val in scores[:3]:
                    resolved.add(val)
            return list(resolved)
        except Exception as e:
            logger.error(f"Error normalizing seniority: {e}")
            return list(seniorities or [])

    # -------------------------
    # SEMANTIC COMPANY SIZE
    # -------------------------

    def normalize_company_size(self, sizes):
        try:
            resolved = set()
            for text in sizes:
                query_vec = self.embed(text)
                scores = []
                for key, vec in self.company_size_embeddings.items():
                    sim = self.cosine(query_vec, vec)
                    scores.append((sim, key))

                scores.sort(reverse=True)
                for s, val in scores[:3]:
                    resolved.add(val)
            return list(resolved)
        except Exception as e:
            logger.error(f"Error normalizing company size: {e}")
            return list(sizes or [])

    # -------------------------
    # NORMALIZE PIPELINE
    # -------------------------

    def normalize(self, llm_output):
        normalized = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            f_titles = executor.submit(self.normalize_titles, llm_output.get("person_titles", []))
            f_keywords = executor.submit(self.normalize_keywords, llm_output.get("q_keywords", ""))
            f_locations = executor.submit(self.normalize_locations, llm_output.get("person_locations", []))
            f_seniority = executor.submit(self.normalize_seniority, llm_output.get("person_seniorities", []))
            f_sizes = executor.submit(self.normalize_company_size, llm_output.get("organization_num_employees_ranges", []))

            normalized["person_titles"] = f_titles.result()
            normalized["q_keywords"] = f_keywords.result()
            normalized["person_locations"] = f_locations.result()
            normalized["organization_locations"] = normalized["person_locations"]
            normalized["person_seniorities"] = f_seniority.result()
            normalized["organization_num_employees_ranges"] = f_sizes.result()

        return normalized

    # -------------------------
    # QUERY EXPANSION
    # -------------------------

    def expand_queries(self, params):
        titles = params.get("person_titles", []) or []
        keywords = params.get("q_keywords", []) or []
        locations = params.get("person_locations", []) or []
        sizes = params.get("organization_num_employees_ranges", []) or []

        # Build dimension lists — use [None] as placeholder so itertools.product
        # still generates combinations even when a field is absent.
        title_dim    = titles[:10]    or [None]
        keyword_dim  = keywords[:10]  or [None]
        location_dim = locations[:10] or [None]
        size_dim     = sizes[:10]     or [None]

        combos = list(itertools.product(title_dim, keyword_dim, location_dim, size_dim))

        queries = []

        for c in combos:
            q = {"person_seniorities": params.get("person_seniorities", [])}

            if c[0] is not None:
                q["person_titles"] = [c[0]]
            if c[1] is not None:
                q["q_keywords"] = c[1]
            if c[2] is not None:
                q["person_locations"] = [c[2]]
                q["organization_locations"] = [c[2]]
            if c[3] is not None:
                q["organization_num_employees_ranges"] = [c[3]]

            queries.append(q)

        return queries

    # -------------------------
    # QUERY SCORING
    # -------------------------

    def score_query(self, query):
        score = 0
        if query.get("person_titles"):
            score += self.title_weight
        if query.get("q_keywords"):
            score += self.keyword_weight
        if query.get("person_locations"):
            score += self.location_weight
        if query.get("organization_num_employees_ranges"):
            score += self.size_weight
        return score

    # -------------------------
    # QUERY PLANNER
    # -------------------------

    def plan_queries(self, queries, limit=1000):
        scored = []
        for q in queries:
            score = self.score_query(q)
            scored.append((score, q))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [q for s, q in scored[:limit]]

    # -------------------------
    # FULL PIPELINE
    # -------------------------

    def build_queries(self, llm_output):
        normalized = self.normalize(llm_output)
        expanded = self.expand_queries(normalized)
        planned = self.plan_queries(expanded)
        return planned


def main():

    llm_output = {
        "q_keywords": "Enterprise IT; Technology; Digital Transformation",
        "person_titles": [
            "Chief Information Officer",
            "Chief Technology Officer"
        ],
        "person_seniorities": [
            "executive leadership"
        ],
        "person_locations": [
            "United States",
            "Canada"
        ],
        "organization_num_employees_ranges": [
            "1000,5000",
            "5000,10000",
            "10000+"
        ]
    }

    normalizer = get_normalizer()
    queries = normalizer.build_queries(llm_output)

    print("\nGenerated Search Queries:\n")
    for q in queries:
        print(q)


# if __name__ == "__main__":
#     main()
