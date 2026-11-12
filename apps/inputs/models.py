import uuid
from django.conf import settings
from django.db import models
from apps.members.models import Member
from apps.organisations.models import OrganisationOwnedModel

class InputAllocation(OrganisationOwnedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        VERIFIED = "verified", "Verified"
        DELIVERED = "delivered", "Delivered"
        PARTIALLY_DELIVERED = "partially_delivered", "Partially Delivered"
        REJECTED = "rejected", "Rejected"

    class InputType(models.TextChoices):
        NPK = "npk", "NPK"
        ORGANIC = "organic", "Organic"
        SEEDLINGS = "seedlings", "Seedlings"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="input_allocations")
    input_type = models.CharField(max_length=20, choices=InputType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)

    # Audit fields
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="verified_allocations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organisation", "member", "status"]),
        ]

    def __str__(self):
        return f"{self.member} - {self.input_type} ({self.quantity})"
