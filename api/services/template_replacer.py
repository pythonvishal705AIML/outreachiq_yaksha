"""
Template Replacer Service
Handles replacement of template variables like {{company_name}}, {{sender_name}}, etc.
with actual values from user profile and lead data.
"""

import logging
from typing import Dict, Optional
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class TemplateReplacer:
    """
    Service to replace template variables in email content with actual values.
    
    Supported variables:
    - {{company_name}} - User's company name from BusinessProfile
    - {{sender_name}} - User's full name
    - {{first_name}} - Lead's first name
    - {{last_name}} - Lead's last name
    - {{company_name}} - Lead's company name (when in lead context)
    - {{title}} - Lead's job title
    - {{industry}} - Lead's industry
    - {{location}} - Lead's location
    """
    
    @staticmethod
    def get_user_context(user) -> Dict[str, str]:
        """
        Get user-specific context for template replacement.
        
        Args:
            user: User object
            
        Returns:
            Dictionary with user context variables
        """
        context = {}
        
        # Get sender name
        if user.first_name and user.last_name:
            context['sender_name'] = f"{user.first_name} {user.last_name}"
        elif user.first_name:
            context['sender_name'] = user.first_name
        else:
            context['sender_name'] = user.email.split('@')[0].title()
        
        # Get company name from BusinessProfile
        try:
            from api.models import BusinessProfile
            if user.account_id:
                profile = BusinessProfile.objects.filter(account_id=user.account_id).first()
                if profile and profile.name:
                    context['company_name'] = profile.name
                else:
                    context['company_name'] = "Your Company"
            else:
                context['company_name'] = "Your Company"
        except Exception as e:
            logger.warning(f"Could not fetch BusinessProfile for user {user.id}: {e}")
            context['company_name'] = "Your Company"
        
        return context
    
    @staticmethod
    def get_lead_context(lead) -> Dict[str, str]:
        """
        Get lead-specific context for template replacement.
        
        Args:
            lead: Lead object or dictionary with lead data
            
        Returns:
            Dictionary with lead context variables
        """
        context = {}
        
        # Handle both Lead objects and dictionaries
        if isinstance(lead, dict):
            context['first_name'] = lead.get('first_name', '')
            context['last_name'] = lead.get('last_name', '')
            context['company_name'] = lead.get('company_name', '')
            context['title'] = lead.get('title', '')
            context['industry'] = lead.get('industry', '')
            context['location'] = lead.get('location', '')
        else:
            # Lead model object
            context['first_name'] = getattr(lead, 'first_name', '')
            context['last_name'] = getattr(lead, 'last_name', '')
            context['company_name'] = getattr(lead, 'company_name', '')
            context['title'] = getattr(lead, 'title', '')
            context['industry'] = getattr(lead, 'industry', '')
            context['location'] = getattr(lead, 'location', '')
        
        return context
    
    @staticmethod
    def replace_placeholders(text: str, user_context: Dict[str, str] = None, 
                           lead_context: Dict[str, str] = None) -> str:
        """
        Replace all template variables in text with actual values.
        
        Args:
            text: Text containing template variables
            user_context: Dictionary with user-specific variables (sender_name, company_name)
            lead_context: Dictionary with lead-specific variables (first_name, etc.)
            
        Returns:
            Text with all variables replaced
        """
        if not text:
            return text
        
        result = text
        
        # Replace user context variables first (sender info)
        if user_context:
            for key, value in user_context.items():
                placeholder = f"{{{{{key}}}}}"
                result = result.replace(placeholder, value or '')
        
        # Replace lead context variables (may override company_name if lead has one)
        if lead_context:
            for key, value in lead_context.items():
                placeholder = f"{{{{{key}}}}}"
                # Only replace if value exists, to avoid overwriting user's company with empty lead company
                if value:
                    result = result.replace(placeholder, value)
        
        return result
    
    @classmethod
    def replace_email_content(cls, subject: str, body: str, user, lead=None, preview_mode=False) -> Dict[str, str]:
        """
        Replace placeholders in both email subject and body.
        
        Args:
            subject: Email subject with placeholders
            body: Email body with placeholders
            user: User object
            lead: Lead object or dictionary (optional)
            preview_mode: If True and no lead provided, use sample lead data for preview
            
        Returns:
            Dictionary with 'subject' and 'body' keys containing replaced content
        """
        user_context = cls.get_user_context(user)
        
        # If preview mode and no lead, use sample data
        if preview_mode and not lead:
            lead_context = {
                'first_name': '[First Name]',
                'last_name': '[Last Name]',
                'company_name': '[Company Name]',
                'title': '[Job Title]',
                'industry': '[Industry]',
                'location': '[Location]'
            }
        else:
            lead_context = cls.get_lead_context(lead) if lead else {}
        
        return {
            'subject': cls.replace_placeholders(subject, user_context, lead_context),
            'body': cls.replace_placeholders(body, user_context, lead_context)
        }
