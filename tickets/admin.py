from django.contrib import admin
from .models import Ticket, ScanLog, UserProfile

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['short_id', 'purchaser_name', 'status', 'is_active', 'created_by', 'created_at']
    list_filter = ['status', 'is_active']
    search_fields = ['purchaser_name', 'ticket_id']

@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'scanned_by', 'result', 'scanned_at']
    list_filter = ['result']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
