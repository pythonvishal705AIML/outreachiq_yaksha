from django.core.management.base import BaseCommand
from api.services.etl_service import ETLService

class Command(BaseCommand):
    help = 'Runs daily ETL snapshot for Data Warehouse (LeadHistory & SearchHistory).'

    def handle(self, *args, **options):
        self.stdout.write("Starting Daily ETL...")
        try:
            ETLService.run_daily_load()
            self.stdout.write(self.style.SUCCESS('Successfully completed Daily ETL snapshot.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'ETL Failed: {str(e)}'))
