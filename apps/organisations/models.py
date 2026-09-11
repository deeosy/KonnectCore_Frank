from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Organisation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["name"]
    def __str__(self): return self.name

class OrganisationMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        FIELD_OFFICER = "field_officer", "Field Officer"
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organisation_memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organisation", "user"], name="unique_org_user_membership")]
        ordering = ["user__first_name", "user__email"]
    def clean(self):
        if self.organisation_id and self.organisation.status != Organisation.Status.ACTIVE and self.is_active:
            raise ValidationError("Cannot activate membership for an inactive organisation.")
    def __str__(self): return f"{self.user} · {self.organisation} · {self.get_role_display()}"

class OrganisationQuerySet(models.QuerySet):
    def for_organisation(self, organisation):
        if not organisation or not getattr(organisation, "pk", None):
            return self.none()
        return self.filter(organisation=organisation)

class OrganisationOwnedModel(models.Model):
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    objects = OrganisationQuerySet.as_manager()
    class Meta:
        abstract = True

from .invitations import StaffInvitation  # noqa: E402,F401
