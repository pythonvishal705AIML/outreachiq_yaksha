from django.test import TestCase
from rest_framework.test import APIClient
from .models import User, Organization


class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
    def test_signup(self):
        """Test user registration"""
        data = {
            'email': 'test@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'organization_name': 'Test Org'
        }
        
        response = self.client.post('/api/auth/signup/', data, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('access_token', response.data['tokens'])
        self.assertIn('refresh_token', response.data['tokens'])
        
    def test_login(self):
        """Test user login"""
        # Create user first
        org = Organization.objects.create_organization(name='Test Org')
        user = User.objects.create_user(
            email='test@example.com',
            password='SecurePass123!',
            organization=org
        )
        
        # Login
        data = {
            'email': 'test@example.com',
            'password': 'SecurePass123!'
        }
        
        response = self.client.post('/api/auth/login/', data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.data['tokens'])
