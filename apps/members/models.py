import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

# Inherit from OrganisationOwnedModel to automatically link data to an organisation.
from apps.organisations.models import OrganisationOwnedModel


# ==============================================================================
# FILE PATH HELPERS
# = : These functions determine where files are stored on the server.
# ==============================================================================
def member_photo_path(instance, filename):
    """Stores farmer photo in: media/organisations/<org_id>/members/<member_id>/photo.<ext>"""
    suffix = Path(filename).suffix.lower()
    return f"organisations/{instance.organisation_id}/members/{instance.pk}/photo{suffix}"


def member_document_path(instance, filename):
    """Stores documents in: media/organisations/<org_id>/members/<member_id>/documents/<doc_id>.<ext>"""
    suffix = Path(filename).suffix.lower()
    return f"organisations/{instance.organisation_id}/members/{instance.member_id}/documents/{instance.pk}{suffix}"


# ==============================================================================
# MEMBER MODEL
# = : Represents the core "Farmer" entity in the system.
# ==============================================================================
class Member(OrganisationOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"
        DECEASED = "deceased", "Deceased"
        ARCHIVED = "archived", "Archived"

    # Using UUIDs (Universally Unique Identifiers) instead of standard sequential integers
    # makes the IDs harder to guess, increasing security.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)

    # Unique identifier for the cooperative/organisation.
    membership_number = models.CharField(max_length=80)

    # ID card or other government/coop reference.
    id_reference = models.CharField("ID/reference", max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to=member_photo_path, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    # Tracking who created/last edited this member record.
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="members_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="members_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name", "membership_number"]

        # Ensures membership numbers are unique within a specific organisation.
        constraints = [
            models.UniqueConstraint(
                "organisation",
                Lower("membership_number"),
                name="unique_org_membership_number_ci",
                violation_error_message="This membership number already exists in this organisation.",
            ),
        ]

        # Database indexes for faster searching/filtering by status or name.
        indexes = [
            models.Index(fields=["organisation", "status"]),
            models.Index(fields=["organisation", "last_name", "first_name"]),
        ]

    # Fields that should have whitespace automatically trimmed by our custom clean method.
    TRIMMED_FIELDS = ("membership_number", "phone", "id_reference")

    def clean_fields(self, exclude=None):
        """
        Custom validation to trim whitespace and ensure required fields are filled.
        This runs before saving to the database.
        """
        exclude = set(exclude or ())
        for name in self.TRIMMED_FIELDS:
            if name not in exclude:
                setattr(self, name, (getattr(self, name) or "").strip())

        errors = {}
        if "membership_number" not in exclude and not self.membership_number:
            errors["membership_number"] = ["Membership number is required."]
            exclude.add("membership_number")

        try:
            super().clean_fields(exclude=exclude)
        except ValidationError as exc:
            errors = exc.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)

    @property
    def full_name(self):
        """Helper to combine names."""
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.full_name} ({self.membership_number})"


# ==============================================================================
# MEMBER DOCUMENT MODEL
# = : Allows storing multiple files (e.g., ID photos, agreements) per Member.
# ==============================================================================
class MemberDocument(OrganisationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=160)
    file = models.FileField(upload_to=member_document_path)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="member_documents_uploaded")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["organisation", "member"])]

    def clean(self):
        """Ensure document belongs to the same organisation as the member."""
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            raise ValidationError("Document and member must belong to the same organisation.")

    def __str__(self):
        return self.title


# ==============================================================================
# MEMBER HISTORY MODEL
# = : An 'audit log' for every change made to a Member record.
# ==============================================================================
class MemberHistory(OrganisationOwnedModel):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DOCUMENT_ADDED = "document_added", "Document added"
        IMPORTED = "imported", "Imported"
        ARCHIVED = "archived", "Archived"
        RESTORED = "restored", "Restored"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="history")
    action = models.CharField(max_length=24, choices=Action.choices)

    # Stores the specific changes (e.g., {"phone": ["old", "new"]}) in JSON format.
    changes = models.JSONField(default=dict, blank=True)

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="member_history_actions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organisation", "member", "created_at"])]

    def clean(self):
        """Ensure history record belongs to the same organisation as the member."""
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            raise ValidationError("History and member must belong to the same organisation.")
