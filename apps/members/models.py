import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.organisations.models import OrganisationOwnedModel


def member_photo_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"organisations/{instance.organisation_id}/members/{instance.pk}/photo{suffix}"


def member_document_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"organisations/{instance.organisation_id}/members/{instance.member_id}/documents/{instance.pk}{suffix}"


class Member(OrganisationOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"
        DECEASED = "deceased", "Deceased"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)
    membership_number = models.CharField(max_length=80)
    id_reference = models.CharField("ID/reference", max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to=member_photo_path, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="members_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="members_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name", "membership_number"]
        constraints = [
            models.UniqueConstraint(
                "organisation",
                Lower("membership_number"),
                name="unique_org_membership_number_ci",
                violation_error_message="This membership number already exists in this organisation.",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "status"]),
            models.Index(fields=["organisation", "last_name", "first_name"]),
        ]

    def clean(self):
        self.membership_number = self.membership_number.strip()
        self.phone = self.phone.strip()
        self.id_reference = self.id_reference.strip()
        if not self.membership_number:
            raise ValidationError({"membership_number": "Membership number is required."})

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.full_name} ({self.membership_number})"


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
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            raise ValidationError("Document and member must belong to the same organisation.")

    def __str__(self):
        return self.title


class MemberHistory(OrganisationOwnedModel):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DOCUMENT_ADDED = "document_added", "Document added"
        IMPORTED = "imported", "Imported"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="history")
    action = models.CharField(max_length=24, choices=Action.choices)
    changes = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="member_history_actions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organisation", "member", "created_at"])]

    def clean(self):
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            raise ValidationError("History and member must belong to the same organisation.")
