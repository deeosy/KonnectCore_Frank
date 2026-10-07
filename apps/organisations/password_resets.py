"""Admin-issued password reset links.

The app sends no email, so an Admin issues a one-time link and shares it by WhatsApp,
the same way invitations work. Only a SHA-256 hash of the link token is stored.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .models import Organisation

RESET_LIFETIME = timedelta(hours=24)


class StaffPasswordReset(models.Model):
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="password_resets")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_resets")
    token_hash = models.CharField(max_length=64, unique=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_password_resets")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    @transaction.atomic
    def issue(cls, *, organisation, user, issued_by):
        """Create a new link and cancel any earlier unused ones for this user (kept for audit)."""
        now = timezone.now()
        cls.objects.filter(user=user, used_at__isnull=True, cancelled_at__isnull=True).update(cancelled_at=now)
        token = secrets.token_urlsafe(32)
        reset = cls.objects.create(
            organisation=organisation,
            user=user,
            issued_by=issued_by,
            token_hash=cls.digest(token),
            expires_at=now + RESET_LIFETIME,
        )
        return reset, token

    @classmethod
    def valid(cls):
        return cls.objects.select_related("user", "organisation").filter(
            used_at__isnull=True,
            cancelled_at__isnull=True,
            expires_at__gt=timezone.now(),
            organisation__status=Organisation.Status.ACTIVE,
        )

    @property
    def is_valid(self):
        return (
            self.used_at is None
            and self.cancelled_at is None
            and self.expires_at > timezone.now()
            and self.organisation.status == Organisation.Status.ACTIVE
        )
