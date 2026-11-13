import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.members.models import Member
from apps.organisations.models import OrganisationOwnedModel

# ==============================================================================
# CROP MODEL
# = : Represents the types of agricultural products an organisation tracks.
# ==============================================================================
class Crop(OrganisationOwnedModel):
    """
    A list of crops (e.g., Cocoa, Maize, Coffee) configured for each organisation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)

    # Optional field to specify the variety of the crop (e.g., 'Arabica' for Coffee).
    variety = models.CharField(max_length=120, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "variety"]
        # Ensures that a Crop/Variety combination is unique within an organisation.
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "name", "variety"],
                name="unique_org_crop_variety"
            )
        ]
        indexes = [models.Index(fields=["organisation", "name"])]

    def clean(self):
        """Pre-save validation to clean up user input."""
        self.name = self.name.strip()
        self.variety = self.variety.strip()
        if not self.name:
            raise ValidationError({"name": "Crop name is required."})

    @property
    def display_name(self):
        """Helper to show 'Crop Name - Variety' or just 'Crop Name'."""
        return f"{self.name} — {self.variety}" if self.variety else self.name

    def __str__(self):
        return self.display_name


# ==============================================================================
# FARM MODEL
# = : Represents a specific piece of land owned by a Member.
# ==============================================================================
class Farm(OrganisationOwnedModel):
    class SizeUnit(models.TextChoices):
        HECTARES = "ha", "Hectares"
        ACRES = "acres", "Acres"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Every farm must belong to a member.
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="farms")

    name = models.CharField(max_length=160, default="Main farm")

    # DecimalField is used for financial or precise measurements instead of FloatField.
    size = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    size_unit = models.CharField(max_length=8, choices=SizeUnit.choices, default=SizeUnit.HECTARES)

    # General descriptive location.
    location = models.CharField(max_length=255, blank=True)

    # Precise GPS coordinates for mapping.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["member__first_name", "member__last_name", "name"]
        constraints = [
            # Each member can only have one farm with a particular name in that organisation.
            models.UniqueConstraint(fields=["organisation", "member", "name"], name="unique_org_member_farm_name"),
            # Prevents entering negative farm sizes.
            models.CheckConstraint(condition=models.Q(size__isnull=True) | models.Q(size__gte=0), name="farm_size_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["organisation", "member"]),
            models.Index(fields=["organisation", "location"])
        ]

    def clean(self):
        """Comprehensive validation for farm data."""
        errors = {}
        self.name = self.name.strip()
        if not self.name:
            errors["name"] = "Farm name is required."

        # Ensure the member actually belongs to the organisation.
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            errors["member"] = "Member must belong to the same organisation."

        # Ensure GPS coordinates are either both provided or both empty.
        if (self.latitude is None) != (self.longitude is None):
            errors["latitude" if self.latitude is None else "longitude"] = "Enter both latitude and longitude, or leave both blank."

        # Validate latitude (-90 to 90) and longitude (-180 to 180).
        if self.latitude is not None and not Decimal("-90") <= self.latitude <= Decimal("90"):
            errors["latitude"] = "Latitude must be between -90 and 90."
        if self.longitude is not None and not Decimal("-180") <= self.longitude <= Decimal("180"):
            errors["longitude"] = "Longitude must be between -180 and 180."

        if self.size is not None and self.size < 0:
            errors["size"] = "Farm size cannot be negative."

        if errors:
            raise ValidationError(errors)

    @property
    def gps(self):
        """Returns GPS as a comma-separated string."""
        if self.latitude is None or self.longitude is None:
            return ""
        return f"{self.latitude}, {self.longitude}"

    def __str__(self):
        return f"{self.name} — {self.member.full_name}"


class FarmOwnershipTransfer(OrganisationOwnedModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="ownership_transfers")
    previous_member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name="farms_transferred_from",
    )
    successor_member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name="farms_transferred_to",
    )
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="farm_ownership_transfers",
    )
    reason = models.TextField()
    transferred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transferred_at", "-pk"]
        indexes = [models.Index(fields=["organisation", "farm", "transferred_at"])]

    def clean(self):
        errors = {}
        if self.farm_id and self.organisation_id and self.farm.organisation_id != self.organisation_id:
            errors["farm"] = "Farm must belong to the same organisation."
        for field in ("previous_member", "successor_member"):
            member_id = getattr(self, f"{field}_id")
            if member_id and self.organisation_id:
                member = getattr(self, field)
                if member.organisation_id != self.organisation_id:
                    errors[field] = "Member must belong to the same organisation."
        if self.previous_member_id and self.previous_member_id == self.successor_member_id:
            errors["successor_member"] = "Choose a different successor member."
        if self.farm_id and self.successor_member_id and self.farm.member_id != self.successor_member_id:
            errors["successor_member"] = "The farm must be assigned to the successor member."
        if self.successor_member_id and self.successor_member.status != Member.Status.ACTIVE:
            errors["successor_member"] = "Successor must be an active member."
        if self.transferred_by_id and self.organisation_id:
            from apps.organisations.models import OrganisationMembership

            if not OrganisationMembership.objects.filter(
                organisation_id=self.organisation_id,
                user_id=self.transferred_by_id,
                role__in=(
                    OrganisationMembership.Role.ADMIN,
                    OrganisationMembership.Role.MANAGER,
                ),
                is_active=True,
            ).exists():
                errors["transferred_by"] = "Transfer must be recorded by an active Admin or Manager."
        if not self.reason.strip():
            errors["reason"] = "A transfer reason is required."
        if errors:
            raise ValidationError(errors)


# ==============================================================================
# FARM CROP SEASON MODEL
# = : Tracks what is planted on a farm during a specific season.
# ==============================================================================
class FarmCropSeason(OrganisationOwnedModel):
    """
    Connects a Farm to a Crop for a specific time period (Season).
    This allows us to track yield estimates vs actuals.
    """
    class YieldUnit(models.TextChoices):
        KILOGRAMS = "kg", "Kilograms"
        TONNES = "tonnes", "Tonnes"
        BAGS = "bags", "Bags"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="crop_seasons")
    crop = models.ForeignKey(Crop, on_delete=models.PROTECT, related_name="farm_seasons")

    # E.g., '2024 Main Season'
    season = models.CharField(max_length=120)

    planting_start = models.DateField(null=True, blank=True)
    planting_end = models.DateField(null=True, blank=True)

    # What the farmer expects to harvest.
    estimated_yield = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # What was actually harvested.
    actual_yield = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    yield_unit = models.CharField(max_length=10, choices=YieldUnit.choices, default=YieldUnit.KILOGRAMS)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-planting_start", "season", "crop__name"]
        constraints = [
            # Each farm/crop combo can only appear once in a given season.
            models.UniqueConstraint(fields=["farm", "crop", "season"], name="unique_farm_crop_season"),
            models.CheckConstraint(condition=models.Q(estimated_yield__isnull=True) | models.Q(estimated_yield__gte=0), name="estimated_yield_nonnegative"),
            models.CheckConstraint(condition=models.Q(actual_yield__isnull=True) | models.Q(actual_yield__gte=0), name="actual_yield_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["organisation", "farm"]),
            models.Index(fields=["organisation", "crop"]),
            models.Index(fields=["organisation", "season"])
        ]

    def clean(self):
        """Validate season dates and ownership."""
        errors = {}
        self.season = self.season.strip()
        if not self.season:
            errors["season"] = "Season or planting period is required."

        # Ensure all related objects belong to the same organisation.
        if self.farm_id and self.organisation_id and self.farm.organisation_id != self.organisation_id:
            errors["farm"] = "Farm must belong to the same organisation."
        if self.crop_id and self.organisation_id and self.crop.organisation_id != self.organisation_id:
            errors["crop"] = "Crop must belong to the same organisation."

        # Date logic.
        if self.planting_start and self.planting_end and self.planting_end < self.planting_start:
            errors["planting_end"] = "Planting end cannot be before planting start."

        if self.estimated_yield is not None and self.estimated_yield < 0:
            errors["estimated_yield"] = "Estimated yield cannot be negative."
        if self.actual_yield is not None and self.actual_yield < 0:
            errors["actual_yield"] = "Actual yield cannot be negative."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.crop.display_name} — {self.season}"
