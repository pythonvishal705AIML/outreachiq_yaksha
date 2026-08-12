from django.contrib import admin
from .models import SentEmail, EmailReply


@admin.register(SentEmail)
class SentEmailAdmin(admin.ModelAdmin):
    list_display = ('recipient_email', 'subject', 'status', 'sent_at', 'campaign_id', 'sent_from')
    list_filter = ('status', 'sent_at', 'campaign_id')
    search_fields = ('recipient_email', 'subject', 'body', 'campaign_id')
    readonly_fields = ('id', 'sent_at')
    ordering = ('-sent_at',)


@admin.register(EmailReply)
class EmailReplyAdmin(admin.ModelAdmin):
    list_display = ('from_email', 'subject', 'sentiment', 'is_read', 'received_at', 'sent_email')
    list_filter = ('sentiment', 'is_read', 'received_at')
    search_fields = ('from_email', 'subject', 'body')
    readonly_fields = ('id', 'received_at')
    ordering = ('-received_at',)
