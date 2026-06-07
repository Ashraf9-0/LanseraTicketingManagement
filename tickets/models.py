from django.db import models
from django.contrib.auth.models import User
import uuid
import hashlib
import secrets


class UserProfile(models.Model):
    ROLES = [
        ('seller', 'Ticket Seller'),
        ('scanner', 'Ticket Scanner'),
        ('admin', 'Super Administrator'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLES, default='seller')

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_seller(self):
        return self.role == 'seller'

    @property
    def is_scanner(self):
        return self.role == 'scanner'

    @property
    def is_admin(self):
        return self.role == 'admin'


class Ticket(models.Model):
    STATUS_UNUSED = 'unused'
    STATUS_USED = 'used'
    STATUS_CHOICES = [
        (STATUS_UNUSED, 'Unused'),
        (STATUS_USED, 'Used'),
    ]

    ticket_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token = models.CharField(max_length=64, unique=True, editable=False)
    purchaser_name = models.CharField(max_length=200)
    purchaser_email = models.EmailField(blank=True)
    purchaser_phone = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_tickets')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_UNUSED)
    is_active = models.BooleanField(default=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_tickets')
    qr_image = models.ImageField(upload_to='qrcodes/', blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {str(self.ticket_id)[:8]} - {self.purchaser_name}"

    @property
    def is_used(self):
        return self.status == self.STATUS_USED

    @property
    def short_id(self):
        return str(self.ticket_id).upper()[:8]


class ScanLog(models.Model):
    RESULT_VALID = 'valid'
    RESULT_USED = 'already_used'
    RESULT_INVALID = 'invalid'
    RESULT_INACTIVE = 'inactive'
    RESULT_CHOICES = [
        (RESULT_VALID, 'Valid'),
        (RESULT_USED, 'Already Used'),
        (RESULT_INVALID, 'Invalid'),
        (RESULT_INACTIVE, 'Inactive'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='scan_logs')
    scanned_by = models.ForeignKey(User, on_delete=models.PROTECT)
    scanned_at = models.DateTimeField(auto_now_add=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    raw_data = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        return f"Scan by {self.scanned_by.username} at {self.scanned_at} - {self.result}"
