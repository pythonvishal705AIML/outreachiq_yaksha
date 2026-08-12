from django.core.management.base import BaseCommand
from api.services.normalization_service import NormalizationService

class Command(BaseCommand):
    help = "Verify Filter Options API"

    def handle(self, *args, **options):
        self.stdout.write("Verifying Filter Options...")
        
        data = NormalizationService.get_options()
        
        # Check new keys
        expected_keys = [
            "employee_ranges", "revenue_ranges", "email_statuses", "seniority_levels",
            "q_keywords", "person_titles", "person_seniorities", "person_locations", "organization_locations",
            "organization_num_employees_ranges", "revenue_range", "q_organization_domains_list",
            "contact_email_status", "q_organization_job_titles", "organization_num_jobs_range",
            "organization_job_posted_at_range", "q_organization_keyword_tags", "q_organization_name",
            "organization_ids", "organization_job_locations"
        ]
        
        all_passed = True
        for key in expected_keys:
            if key in data:
                val = data[key]
                if isinstance(val, list) and len(val) > 0:
                     self.stdout.write(f"PASS: '{key}' found. Count: {len(val)}")
                elif isinstance(val, dict):
                     self.stdout.write(f"PASS: '{key}' found (Object).")
                else:
                     self.stdout.write(f"WARNING: '{key}' found but is EMPTY/None.")
            else:
                self.stdout.write(f"FAIL: '{key}' NOT found.")
                all_passed = False
                
        if all_passed:
            self.stdout.write("\nSUCCESS: All static options exposed correctly.")
        else:
            self.stdout.write("\nFAILURE: Missing keys.")
