from django.core.management.base import BaseCommand
from authentication.models import User, Organization


class Command(BaseCommand):
    help = 'Create test users for development'

    def handle(self, *args, **options):
        # Create test organization
        org, created = Organization.objects.get_or_create(
            name='Test Organization',
            defaults={
                'plan_type': 'professional',
                'max_users': 50
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created organization: {org.name}'))
        
        # Create owner user
        if not User.objects.filter(email='owner@test.com').exists():
            owner = User.objects.create_user(
                email='owner@test.com',
                password='TestPass123!',
                first_name='Owner',
                last_name='User',
                organization=org,
                role='owner',
                is_active=True,
                email_verified=True
            )
            self.stdout.write(self.style.SUCCESS(f'Created owner: {owner.email}'))
        
        # Create admin user
        if not User.objects.filter(email='admin@test.com').exists():
            admin = User.objects.create_user(
                email='admin@test.com',
                password='TestPass123!',
                first_name='Admin',
                last_name='User',
                organization=org,
                role='admin',
                is_active=True,
                email_verified=True
            )
            self.stdout.write(self.style.SUCCESS(f'Created admin: {admin.email}'))
        
        # Create member user
        if not User.objects.filter(email='member@test.com').exists():
            member = User.objects.create_user(
                email='member@test.com',
                password='TestPass123!',
                first_name='Member',
                last_name='User',
                organization=org,
                role='member',
                is_active=True,
                email_verified=True
            )
            self.stdout.write(self.style.SUCCESS(f'Created member: {member.email}'))
        
        self.stdout.write(self.style.SUCCESS('\nTest users created successfully!'))
        self.stdout.write('Login credentials:')
        self.stdout.write('  Owner: owner@test.com / TestPass123!')
        self.stdout.write('  Admin: admin@test.com / TestPass123!')
        self.stdout.write('  Member: member@test.com / TestPass123!')
