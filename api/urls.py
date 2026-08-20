# api/urls.py
from django.urls import path
from .views import LeadUploadView


urlpatterns = [
    path('leads/upload/', LeadUploadView.as_view()),
]
