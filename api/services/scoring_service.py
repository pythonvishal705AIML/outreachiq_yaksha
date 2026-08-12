import logging
import re
from django.utils import timezone
from datetime import timedelta
from ..models import Lead, LeadEvent, BusinessProfile

logger = logging.getLogger(__name__)

class LeadScoringService:
    """
    Lead Scoring Engine (Regression-Based - Heuristic).
    Calculates a dynamic 0-100 score based on calculated weights:
    1. Engagement (LeadEvents): Opens, Clicks, Replies.
    2. Verification: Email health.
    3. ICP Fit: Matching target profile.
    """

    # Scoring model (smooth heuristic 0..100)
    #
    # We avoid “hard bucket” scoring (e.g. title match => 40 else 0) because it
    # collapses most leads into a couple of values.
    #
    # Components:
    # - ICP fit (title/location/industry): 0..40
    # - Verification / email health:      0..30
    # - Data completeness:                0..30
    W_ICP_MAX = 40
    W_VERIFICATION_MAX = 30
    W_COMPLETENESS_MAX = 30

    @staticmethod
    def score_lead(lead: Lead, profile: BusinessProfile = None, icp_params: dict = None) -> dict:
        """
        Main entry point. Calculates and saves the score.
        Uses `icp_params` for ICP Fit if provided, otherwise looks up from SearchRun.
        """
        try:
            # Resolve ICP Params if not provided
            if not icp_params:
                # Try finding lead's search run
                from ..models import SearchRun
                if lead.last_search_run_id:
                     sr = SearchRun.objects.filter(search_id=lead.last_search_run_id).first()
                     if sr and sr.icp_params:
                         icp_params = sr.icp_params
                     elif sr and sr.filters_json:
                         # Fallback to filters if icp_params empty
                         icp_params = sr.filters_json
                
                # If still not found, try many-to-many
                if not icp_params:
                     sr = lead.search_runs.last()
                     if sr:
                         icp_params = sr.icp_params or sr.filters_json

            # 1. Component Scores
            completeness_score, completeness_breakdown = LeadScoringService._calculate_completeness_score(lead)
            ver_score, ver_breakdown = LeadScoringService._calculate_verification_score(lead)
            icp_score, icp_breakdown = LeadScoringService._calculate_icp_fit_score(lead, profile, icp_params)
            # NEW: per-person source_meta profile depth (0..10) — varies across every individual
            depth_score, depth_breakdown = LeadScoringService._calculate_meta_depth_score(lead)

            # 2. Final score (0..100)
            total_raw = float(completeness_score) + float(ver_score) + float(icp_score) + float(depth_score)
            final_score = max(0, min(100, int(round(total_raw))))

            # 3. Update Lead Model
            lead.score = final_score
            lead.score_components = {
                "completeness": {"score": completeness_score, "details": completeness_breakdown},
                "verification": {"score": ver_score, "details": ver_breakdown},
                "icp_fit": {"score": icp_score, "details": icp_breakdown},
                "profile_depth": {"score": depth_score, "details": depth_breakdown},
            }
            lead.score_last_computed_at = timezone.now()
            
            # Retain legacy fields for backward compatibility if needed
            lead.quality_score = ver_score # Approx map
            lead.icp_fit_score = icp_score
            
            lead.save()

            return {
                "score": final_score,
                "components": lead.score_components
            }

        except Exception as e:
            logger.error(f"Error scoring lead {lead.id}: {e}", exc_info=True)
            return {"error": str(e)}

    @staticmethod
    def _tokenize(s: str) -> set[str]:
        return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t}

    @staticmethod
    def _contains_any(haystack: str, needles: list[str]) -> bool:
        h = (haystack or "").lower()
        for n in needles:
            if n and n.lower() in h:
                return True
        return False

    @staticmethod
    def _calculate_completeness_score(lead: Lead) -> tuple[int, dict]:
        """
        Scores basic "contactability" & data richness (0..W_COMPLETENESS_MAX).
        Uses existing lead fields only.
        """
        points = 0

        has_name = bool((lead.first_name or "").strip() or (lead.last_name or "").strip())
        has_title = bool((lead.title or "").strip())
        has_company = bool((lead.company_name or "").strip() or (lead.company_domain or "").strip())
        has_location = bool((lead.location or "").strip())
        has_industry = bool((lead.industry or "").strip())
        has_email = bool((lead.email or "").strip())
        has_phone = bool((lead.phone or "").strip())
        # Per-person enrichment fields — these differ across individuals in the same search
        has_linkedin = bool((getattr(lead, 'linkedin_url', None) or "").strip())
        has_seniority = bool((getattr(lead, 'person_seniority', None) or "").strip())
        has_department = bool((getattr(lead, 'person_department', None) or "").strip())

        if has_name:
            points += 4
        if has_title:
            points += 5          # reduced from 6 to make room
        if has_company:
            points += 5          # reduced from 6
        if has_location:
            points += 3          # reduced from 4
        if has_industry:
            points += 3          # reduced from 4
        if has_email:
            points += 4
        if has_phone:
            points += 2
        if has_linkedin:
            points += 3          # NEW: LinkedIn URL present
        if has_seniority:
            points += 2          # NEW: seniority label present
        if has_department:
            points += 2          # NEW: department present

        # Sub-total cap still 30
        points = min(points, LeadScoringService.W_COMPLETENESS_MAX)

        return int(points), {
            "has_name": has_name,
            "has_title": has_title,
            "has_company": has_company,
            "has_location": has_location,
            "has_industry": has_industry,
            "has_email": has_email,
            "has_phone": has_phone,
            "has_linkedin": has_linkedin,
            "has_seniority": has_seniority,
            "has_department": has_department,
        }

    @staticmethod
    def _calculate_engagement_score(lead: Lead) -> tuple[int, dict]:
        """
        Calculates score based on recent interactions (LeadEvents).
        Lookback: 30 Days.
        """
        score = 0
        details = {"opens": 0, "clicks": 0, "replies": 0, "bounces": 0}
        
        # Fetch events from last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        events = lead.events.filter(timestamp__gte=thirty_days_ago)
        
        for e in events:
            etype = e.event_type.lower()
            if "open" in etype: 
                score += 5
                details["opens"] += 1
            elif "click" in etype:
                score += 15
                details["clicks"] += 1
            elif "replied" in etype or "reply" in etype:
                score += 30
                details["replies"] += 1
            elif "bounce" in etype:
                score -= 50
                details["bounces"] += 1 
        
        # Max Cap for Engagement alone (e.g., 100)
        return min(score, 100), details

    @staticmethod
    def _calculate_meta_depth_score(lead: Lead) -> tuple[int, dict]:
        """
        Mines source_meta for per-person profile richness signals (0..10).
        These fields differ across every individual in the same search batch,
        so this component is the primary driver of score fluctuation.

        Signals used (all are individual-level, not search-level):
          - photo_url present          +1
          - headline / bio present     +2
          - employment_history depth   +0..+3  (capped at 3 jobs)
          - company employee tier      +0..+2  (500+ / 5000+)
          - subdepartments listed      +1
          - personal functions listed  +1
        """
        meta = lead.source_meta if isinstance(lead.source_meta, dict) else {}
        points = 0
        details: dict = {}

        # 1. Photo URL
        if meta.get("photo_url"):
            points += 1
            details["photo"] = True

        # 2. Headline / personal bio
        if meta.get("headline"):
            points += 2
            details["headline"] = True

        # 3. Employment history depth  (0..3)
        emp_hist = meta.get("employment_history") or []
        emp_pts = min(3, len(emp_hist))
        points += emp_pts
        details["employment_history_count"] = len(emp_hist)

        # 4. Company employee count tier  (0..2)
        org = meta.get("organization") or {}
        num_emp = org.get("estimated_num_employees") or 0
        if num_emp >= 5000:
            points += 2
            details["company_size_tier"] = "large"
        elif num_emp >= 500:
            points += 1
            details["company_size_tier"] = "mid"
        else:
            details["company_size_tier"] = "small"

        # 5. Sub-departments listed
        if meta.get("subdepartments"):
            points += 1
            details["subdepartments"] = True

        # 6. Personal functions (e.g. ["sales", "marketing"])
        if meta.get("functions"):
            points += 1
            details["functions"] = True

        points = min(points, 10)  # cap at 10
        return int(points), details

    @staticmethod
    def _calculate_verification_score(lead: Lead) -> tuple[int, dict]:
        """
        Calculates score based on Data Quality & Verification Status.
        """
        status = (lead.verification_status or "").lower()

        if status == "valid":
            score = LeadScoringService.W_VERIFICATION_MAX
            reason = "Email verified valid."
        elif status == "catch_all":
            score = int(round(LeadScoringService.W_VERIFICATION_MAX * 0.55))
            reason = "Email is catch-all (risky)."
        elif status == "invalid":
            score = 0
            reason = "Email invalid."
        else:
            if lead.email:
                score = int(round(LeadScoringService.W_VERIFICATION_MAX * 0.35))
                reason = "Email present but unverified."
            else:
                score = 0
                reason = "No email."

        return int(score), {"status": status or "unknown", "reason": reason}

    @staticmethod
    def _calculate_icp_fit_score(lead: Lead, profile: BusinessProfile, icp_params: dict = None) -> tuple[int, dict]:
        """
        Calculates score based on "Profile Alignment" or "Search Criteria Match".
        Prioritizes `icp_params` (from search run) if available.
        Falls back to `BusinessProfile` matching if no params.
        """
        score = 0.0
        details: list[str] = []
        
        # -----------------------------------------------
        # STRATEGY A: Explicit ICP Params (Search Filters)
        # -----------------------------------------------
        if icp_params:
            lead_title = (lead.title or "").strip()
            lead_loc = (lead.location or "").strip()
            lead_industry = (lead.industry or "").strip()

            # Title (0..18)
            target_titles = icp_params.get("person_titles", []) or [icp_params.get("title")]
            target_titles = [t for t in target_titles if t]
            title_points_max = LeadScoringService.W_ICP_MAX * 0.45
            title_points = 0.0
            if target_titles and lead_title:
                if LeadScoringService._contains_any(lead_title, target_titles):
                    title_points = title_points_max
                    details.append("Title match")
                else:
                    lt = LeadScoringService._tokenize(lead_title)
                    best = 0.0
                    for t in target_titles:
                        tt = LeadScoringService._tokenize(t)
                        if not tt or not lt:
                            continue
                        overlap = len(lt & tt) / max(1, len(tt))
                        best = max(best, overlap)
                    if best > 0:
                        title_points = title_points_max * min(0.75, best)
                        details.append("Title partial match")
            elif lead_title:
                title_points = title_points_max * 0.25
                details.append("Title present")

            # Location (0..12)
            target_locs = (
                icp_params.get("person_locations", [])
                or icp_params.get("organization_locations", [])
                or [icp_params.get("location")]
            )
            target_locs = [l for l in target_locs if l]
            loc_points_max = LeadScoringService.W_ICP_MAX * 0.30
            loc_points = 0.0
            if target_locs:
                candidates = []
                if lead_loc:
                    candidates.append(lead_loc)
                meta = lead.source_meta if isinstance(lead.source_meta, dict) else {}
                for k in ("country", "state", "city"):
                    v = meta.get(k)
                    if v:
                        candidates.append(str(v))
                org = meta.get("organization") if isinstance(meta.get("organization"), dict) else {}
                if org.get("country"):
                    candidates.append(str(org.get("country")))

                if any(LeadScoringService._contains_any(c, target_locs) for c in candidates):
                    loc_points = loc_points_max
                    details.append("Location match")
                elif lead_loc:
                    loc_points = loc_points_max * 0.25
                    details.append("Location present")
            elif lead_loc:
                loc_points = loc_points_max * 0.35
                details.append("Location present (no filter)")

            # Industry/keywords (0..10)
            target_inds = icp_params.get("industry") or icp_params.get("q_keywords")
            if isinstance(target_inds, str):
                target_inds = [t.strip() for t in target_inds.split(",") if t.strip()]
            elif not isinstance(target_inds, list):
                target_inds = []
            ind_points_max = LeadScoringService.W_ICP_MAX * 0.25
            ind_points = 0.0
            if target_inds and lead_industry:
                if LeadScoringService._contains_any(lead_industry, target_inds):
                    ind_points = ind_points_max
                    details.append("Industry match")
                else:
                    li = LeadScoringService._tokenize(lead_industry)
                    best = 0.0
                    for t in target_inds:
                        ti = LeadScoringService._tokenize(t)
                        if not ti or not li:
                            continue
                        overlap = len(li & ti) / max(1, len(ti))
                        best = max(best, overlap)
                    if best > 0:
                        ind_points = ind_points_max * min(0.75, best)
                        details.append("Industry partial match")
            elif lead_industry:
                ind_points = ind_points_max * 0.25
                details.append("Industry present")

            # Seniority bonus (0..4 pts) — seniority differs per person
            # C_SUITE > VP > DIRECTOR > MANAGER > ENTRY (graduated, not binary)
            seniority_bonus_map = {
                "c_suite": 4, "owner": 4, "founder": 4,
                "vp": 3,
                "director": 2,
                "manager": 1,
                "senior": 1,
                "entry": 0, "junior": 0, "intern": 0,
            }
            raw_seniority = (getattr(lead, 'person_seniority', None) or "").lower().strip()
            seniority_bonus = seniority_bonus_map.get(raw_seniority, 0)
            if seniority_bonus:
                details.append(f"Seniority bonus ({raw_seniority})")

            score = float(title_points + loc_points + ind_points + seniority_bonus)
            score = min(float(LeadScoringService.W_ICP_MAX), score)
            return int(round(score)), {"matches": details, "source": "icp_params"}


        # -----------------------------------------------
        # STRATEGY B: NO ICP Params Found
        # -----------------------------------------------
        # Use the per-person `person_seniority` field for a 6-tier graduated scale.
        # This is stored individually per lead so scores will differ across people.
        lead_title = (lead.title or "").lower()
        lead_loc   = (lead.location or "").strip()
        lead_ind   = (lead.industry or "").strip()
        raw_seniority = (getattr(lead, 'person_seniority', None) or "").lower().strip()

        # 6-tier graduated scale (seniority values)
        seniority_score_map = {
            "c_suite":   LeadScoringService.W_ICP_MAX * 0.60,  # ~24
            "owner":     LeadScoringService.W_ICP_MAX * 0.60,  # ~24
            "founder":   LeadScoringService.W_ICP_MAX * 0.60,  # ~24
            "vp":        LeadScoringService.W_ICP_MAX * 0.50,  # ~20
            "director":  LeadScoringService.W_ICP_MAX * 0.42,  # ~17
            "manager":   LeadScoringService.W_ICP_MAX * 0.34,  # ~14
            "senior":    LeadScoringService.W_ICP_MAX * 0.28,  # ~11
            "entry":     LeadScoringService.W_ICP_MAX * 0.12,  # ~5
            "intern":    LeadScoringService.W_ICP_MAX * 0.06,  # ~2
        }

        base = LeadScoringService.W_ICP_MAX * 0.15  # floor so no one is 0
        score = float(base)

        if raw_seniority and raw_seniority in seniority_score_map:
            score += seniority_score_map[raw_seniority]
            details.append(f"Seniority tier: {raw_seniority}")
        elif lead_title:
            # Fallback to title keywords for leads without a seniority label
            senior_kw = ["vp", "vice president", "head", "director", "chief",
                         "founder", "co-founder", "owner", "partner", "principal"]
            manager_kw = ["manager", "lead", "supervisor"]
            junior_kw  = ["intern", "assistant", "associate", "jr", "junior", "student"]

            if LeadScoringService._contains_any(lead_title, senior_kw):
                score += LeadScoringService.W_ICP_MAX * 0.50
                details.append("Senior title keyword")
            elif LeadScoringService._contains_any(lead_title, manager_kw):
                score += LeadScoringService.W_ICP_MAX * 0.34
                details.append("Manager title keyword")
            elif LeadScoringService._contains_any(lead_title, junior_kw):
                score += LeadScoringService.W_ICP_MAX * 0.08
                details.append("Junior title keyword")
            else:
                score += LeadScoringService.W_ICP_MAX * 0.22
                details.append("Title present")

        if lead_loc:
            score += LeadScoringService.W_ICP_MAX * 0.10
            details.append("Location present")

        if lead_ind:
            score += LeadScoringService.W_ICP_MAX * 0.10
            details.append("Industry present")

        score = min(float(LeadScoringService.W_ICP_MAX), score)
        return int(round(score)), {
            "matches": details,
            "source": "heuristic_fallback",
            "raw_seniority": raw_seniority or "unknown",
            "reason": "No ICP Params found in linked Search Run",
        }
