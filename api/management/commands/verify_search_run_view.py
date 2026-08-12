from django.core.management.base import BaseCommand
from unittest.mock import MagicMock, patch
from api.views import SearchRunResultsView
from rest_framework.test import APIRequestFactory

class Command(BaseCommand):
    help = "Verify SearchRunResultsView Response Format"

    def handle(self, *args, **options):
        self.stdout.write("Verifying SearchRunResultsView...")
        
        # 1. Setup Data
        factory = APIRequestFactory()
        request = factory.get('/leads/search/runs/test_run/leads/')
        view = SearchRunResultsView.as_view()
        
        # 2. Mock DB
        with patch('api.models.SearchRun.objects.get') as mock_get_run, \
             patch('api.models.SearchRun.objects.filter') as mock_filter_run:
            
            # Mock Run
            mock_run = MagicMock()
            mock_run.lead_count = 1
            mock_filter_run.return_value.first.return_value = mock_run # For filter().first() query
            
            # Mock Leads
            mock_lead = MagicMock()
            mock_lead.third_party_org_id = "test_123"
            mock_lead.first_name = "Test"
            mock_lead.last_name = "User"
            mock_lead.email = "secret@example.com"
            mock_lead.phone = "123"
            mock_lead.is_revealed = True
            
            # Mock M2M manager
            mock_qs = MagicMock()
            mock_qs.__iter__.return_value = [mock_lead]
            mock_qs.__getitem__.return_value = [mock_lead] # For slicing [start:end]
            mock_qs.count.return_value = 1
            
            mock_run.leads.all.return_value.order_by.return_value = mock_qs
            
            # 3. Call View
            response = view(request, run_id="test_run")
            
            self.stdout.write(f"Status Code: {response.status_code}")
            if response.status_code != 200:
                self.stdout.write(f"Error: {response.data}")
                return

            data = response.data
            people = data.get("people", [])
            if not people:
                self.stdout.write("FAIL: No people returned.")
                return

            p = people[0]
            self.stdout.write(f"Person: {p}")
            
            # 4. Assertions
            if "email" in p:
                self.stdout.write("FAIL: 'email' field found in response.")
            else:
                self.stdout.write("PASS: 'email' field is hidden.")

            if "last_name_obfuscated" in p:
                self.stdout.write("FAIL: 'last_name_obfuscated' field found in response.")
            else:
                self.stdout.write("PASS: 'last_name_obfuscated' field is hidden.")

            if p.get("last_name") == "User":
                self.stdout.write("PASS: 'last_name' is present.")
            else:
                self.stdout.write("FAIL: 'last_name' mismatch.")
