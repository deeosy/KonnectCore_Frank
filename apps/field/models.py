import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.members.models import Member
from apps.organisations.models import OrganisationMembership, OrganisationOwnedModel


# ==============================================================================
# FIELD VISIT MODEL
# = : Records on-site visits by Field Officers to farmers' farms.
# ==============================================================================

def visit_photo_path(instance, filename):
    """Stores photos taken during field visits: media/organisations/<org_id>/field-visits/<visit_id>/photo.<ext>"""
    return f"organisations/{instance.organisation_id}/field-visits/{instance.pk}/photo{Path(filename).suffix.lower()}"

def advisory_photo_path(instance, filename):
    """Stores advisory photos in the owning organisation's private media directory."""
    record_id = instance.pk or uuid.uuid4()
    return f"organisations/{instance.organisation_id}/advisories/{record_id}/photo{Path(filename).suffix.lower()}"


class FieldVisit(OrganisationOwnedModel):
    """
    Represents an interaction (visit) between a Field Officer and a Member.
    Used to track engagement and verify farm conditions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to the farmer being visited.
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="field_visits")
    visit_date = models.DateField()
    notes = models.TextField()

    # GPS coordinates captured at the time of the visit.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    photo = models.ImageField(upload_to=visit_photo_path, blank=True)

    # Track which staff member performed the visit.
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="field_visits_recorded")
    created_at = models.DateTimeField(auto_now_add=True)

    # ANTI-DUPLICATE SYSTEM:
    # Used to ensure field app syncs don't create duplicate records.
    submission_key = models.UUIDField(null=True, blank=True, editable=False)
    submission_fingerprint = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        indexes = [
            models.Index(fields=["organisation", "member"]),
            models.Index(fields=["organisation", "visit_date"])
        ]
        # Prevent same form submission being processed twice in one organisation.
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "submission_key"],
                condition=models.Q(submission_key__isnull=False),
                name="unique_fieldvisit_submission_key"
            )
        ]

    def clean(self):
        """Validates visit data (ownership and GPS coordinates)."""
        e = {}
        # Ensure member belongs to the organisation.
        if self.member_id and self.member.organisation_id != self.organisation_id:
            e["member"] = "Member must belong to the same organisation."

        # GPS validation: ensure both are present or both are absent.
        if (self.latitude is None) != (self.longitude is None):
            e["latitude"] = "Enter both GPS coordinates."

        # GPS bounds checking.
        if self.latitude is not None and not Decimal('-90') <= self.latitude <= Decimal('90'):
            e["latitude"] = "Latitude must be between -90 and 90."
        if self.longitude is not None and not Decimal('-180') <= self.longitude <= Decimal('180'):
            e["longitude"] = "Longitude must be between -180 and 180."

        # Verify staff member performing the visit belongs to the organisation.
        if self.recorded_by_id and not OrganisationMembership.objects.filter(
            organisation_id=self.organisation_id, user_id=self.recorded_by_id
        ).exists():
            e["recorded_by"] = "Recorder must belong to the same organisation."

        if e:
            raise ValidationError(e)

class AdvisoryRecord(OrganisationOwnedModel):
    visit = models.ForeignKey(FieldVisit, on_delete=models.CASCADE, related_name="advisories")
    observation = models.TextField()
    photo = models.ImageField(upload_to=advisory_photo_path, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("requested", "Requested"), ("reviewed", "Reviewed")],
        default="requested"
    )
    review_comment = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_advisories"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        errors = {}
        if self.visit_id and self.organisation_id and self.visit.organisation_id != self.organisation_id:
            errors["visit"] = "Visit must belong to the same organisation."
        if self.reviewed_by_id and self.organisation_id and not OrganisationMembership.objects.filter(
            organisation_id=self.organisation_id, user_id=self.reviewed_by_id,
            role__in=(OrganisationMembership.Role.ADMIN, OrganisationMembership.Role.MANAGER),
        ).exists():
            errors["reviewed_by"] = "Reviewer must be an Admin or Manager in the same organisation."
        if errors:
            raise ValidationError(errors)
