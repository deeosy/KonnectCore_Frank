import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from .models import Organisation, OrganisationMembership

class StaffInvitation(models.Model):
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=OrganisationMembership.Role.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_invitations")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="cancelled_invitations")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organisation", "email"], condition=models.Q(accepted_at__isnull=True, cancelled_at__isnull=True), name="unique_pending_org_invitation")]
    @staticmethod
    def digest(token): return hashlib.sha256(token.encode()).hexdigest()
    @classmethod
    def issue(cls, *, organisation, email, role, invited_by):
        # Replaces an earlier pending invitation; cancelled invitations are kept as an audit record.
        cls.objects.filter(organisation=organisation, email__iexact=email, accepted_at__isnull=True, cancelled_at__isnull=True).delete()
        token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(organisation=organisation, email=email.strip().lower(), role=role, invited_by=invited_by, token_hash=cls.digest(token), expires_at=timezone.now() + timedelta(days=7))
        return invitation, token
    @property
    def is_valid(self): return self.accepted_at is None and self.cancelled_at is None and self.expires_at > timezone.now() and self.organisation.status == Organisation.Status.ACTIVE
