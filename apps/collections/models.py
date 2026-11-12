import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.farms.models import Crop
from apps.members.models import Member
from apps.organisations.models import OrganisationMembership, OrganisationOwnedModel


# ==============================================================================
# FILE PATH HELERS
# ==============================================================================
def collection_photo_path(instance, filename):
    """Stores photos taken during collection: media/organisations/<org_id>/collections/<record_id>/photo.<ext>"""
    suffix = Path(filename).suffix.lower()
    return f"organisations/{instance.organisation_id}/collections/{instance.pk}/photo{suffix}"


# ==============================================================================
# COLLECTION RECORD MODEL
# = : Tracks the physical intake of produce from a farmer.
# ==============================================================================
class CollectionRecord(OrganisationOwnedModel):
    """
    Represents a single event where a farmer brings produce (e.g., a bag of Cocoa)
    to a collection point.
    """
    class QuantityUnit(models.TextChoices):
        KILOGRAMS = "kg", "Kilograms"
        TONNES = "tonnes", "Tonnes"
        BAGS = "bags", "Bags"
        CRATES = "crates", "Crates"
        LITRES = "litres", "Litres"
        UNITS = "units", "Units"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to the farmer.
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="collection_records")

    # Link to the crop type.
    crop = models.ForeignKey(Crop, on_delete=models.PROTECT, related_name="collection_records")

    # Quantity and measurement unit.
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    quantity_unit = models.CharField(max_length=12, choices=QuantityUnit.choices, default=QuantityUnit.KILOGRAMS)

    collection_date = models.DateField()
    collection_location = models.CharField(max_length=255)

    # E.g., 'Grade A', 'Premium', 'Reject'.
    quality_grade = models.CharField(max_length=80, blank=True)

    # Price per unit agreed at time of collection.
    price_per_unit = models.DecimalField(max_digits=14, decimal_places=2)

    # total_value = quantity * price_per_unit. Calculated automatically on save.
    total_value = models.DecimalField(max_digits=18, decimal_places=2, editable=False)

    photo = models.ImageField(upload_to=collection_photo_path, blank=True)
    notes = models.TextField(blank=True)

    # Track which staff member recorded this collection.
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="collection_records_created")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ANTI-DUPLICATE SYSTEM:
    # submission_key prevents double-submitting a form if the user clicks 'Save' twice.
    submission_key = models.UUIDField(null=True, blank=True, editable=False)
    submission_fingerprint = models.CharField(max_length=64, blank=True, editable=False)

    # VOID SYSTEM:
    # Instead of deleting records (which is bad for audits), we 'void' them.
    # Voided records remain in the DB but are ignored in financial totals.
    voided_at = models.DateTimeField(null=True, blank=True, editable=False)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="collection_records_voided", editable=False)
    void_reason = models.TextField(blank=True, editable=False)

    # Stores metadata about the review process when a record was voided.
    void_review = models.JSONField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-collection_date", "-created_at"]
        constraints = [
            # Ensure quantities are positive numbers.
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="collection_quantity_positive"),
            models.CheckConstraint(condition=models.Q(price_per_unit__gte=0), name="collection_price_nonnegative"),
            models.CheckConstraint(condition=models.Q(total_value__gte=0), name="collection_total_nonnegative"),
            # Ensure the same form submission key isn't used twice in one organisation.
            models.UniqueConstraint(
                fields=["organisation", "submission_key"],
                condition=models.Q(submission_key__isnull=False),
                name="unique_collection_submission_key",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "collection_date"]),
            models.Index(fields=["organisation", "member"]),
            models.Index(fields=["organisation", "crop"]),
        ]

    def clean(self):
        """Standard Django validation before saving."""
        errors = {}
        self.collection_location = self.collection_location.strip()
        self.quality_grade = self.quality_grade.strip()

        # Multi-tenancy check: ensure member and crop belong to the same organisation.
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            errors["member"] = "Member must belong to the same organisation."
        if self.crop_id and self.organisation_id and self.crop.organisation_id != self.organisation_id:
            errors["crop"] = "Crop must belong to the same organisation."

        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "Quantity must be greater than zero."
        if self.price_per_unit is not None and self.price_per_unit < 0:
            errors["price_per_unit"] = "Price per unit cannot be negative."

        # Ensure the person recording the entry is a member of the organisation.
        if self.recorded_by_id and self.organisation_id and not OrganisationMembership.objects.filter(
            organisation_id=self.organisation_id, user_id=self.recorded_by_id
        ).exists():
            errors["recorded_by"] = "Recorder must belong to the same organisation."

        if not self.collection_location:
            errors["collection_location"] = "Collection location is required."

        # Allocation Check: prevent editing a record if money has already been
        # allocated to it from a payment.
        if self.pk and not self._state.adding and self.quantity is not None and self.price_per_unit is not None:
            allocated = self.allocated_amount
            if allocated and self.calculate_total() < allocated:
                errors["quantity"] = f"This collection has {allocated} allocated from payments. Its value cannot fall below that. Move or remove allocations first."

        if errors:
            raise ValidationError(errors)

    @property
    def is_voided(self):
        """Helper to check if record was cancelled/voided."""
        return self.voided_at is not None

    @property
    def allocated_amount(self):
        """
        Calculates how much money from Payments has already been assigned to
        this specific collection.
        """
        if not self.pk:
            return Decimal("0.00")
        total = self.allocations.filter(removed_at__isnull=True).exclude(payment__status="cancelled").aggregate(total=models.Sum("amount"))["total"]
        return (total or Decimal("0.00")).quantize(Decimal("0.01"))

    @property
    def unallocated_value(self):
        """The remaining value of the produce that hasn't been paid for yet."""
        return (self.total_value or Decimal("0.00")) - self.allocated_amount

    def calculate_total(self):
        """Helper to multiply quantity by price and round correctly."""
        if self.quantity is None or self.price_per_unit is None:
            return Decimal("0.00")
        quantity = Decimal(str(self.quantity))
        price = Decimal(str(self.price_per_unit))
        return (quantity * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        """Automatically calculates the total_value before writing to the database."""
        self.total_value = self.calculate_total()
        # If updating specific fields, ensure total_value is included in the update.
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"total_value"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.member.full_name} - {self.crop.display_name} - {self.collection_date}"
