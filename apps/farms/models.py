import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.members.models import Member
from apps.organisations.models import OrganisationOwnedModel


class Crop(OrganisationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    variety = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "variety"]
        constraints = [models.UniqueConstraint(fields=["organisation", "name", "variety"], name="unique_org_crop_variety")]
        indexes = [models.Index(fields=["organisation", "name"])]

    def clean(self):
        self.name = self.name.strip()
        self.variety = self.variety.strip()
        if not self.name:
            raise ValidationError({"name": "Crop name is required."})

    @property
    def display_name(self):
        return f"{self.name} — {self.variety}" if self.variety else self.name

    def __str__(self):
        return self.display_name


class Farm(OrganisationOwnedModel):
    class SizeUnit(models.TextChoices):
        HECTARES = "ha", "Hectares"
        ACRES = "acres", "Acres"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="farms")
    name = models.CharField(max_length=160, default="Main farm")
    size = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    size_unit = models.CharField(max_length=8, choices=SizeUnit.choices, default=SizeUnit.HECTARES)
    location = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["member__first_name", "member__last_name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["organisation", "member", "name"], name="unique_org_member_farm_name"),
            models.CheckConstraint(condition=models.Q(size__isnull=True) | models.Q(size__gte=0), name="farm_size_nonnegative"),
        ]
        indexes = [models.Index(fields=["organisation", "member"]), models.Index(fields=["organisation", "location"])]

    def clean(self):
        errors = {}
        self.name = self.name.strip()
        if not self.name:
            errors["name"] = "Farm name is required."
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            errors["member"] = "Member must belong to the same organisation."
        if (self.latitude is None) != (self.longitude is None):
            errors["latitude" if self.latitude is None else "longitude"] = "Enter both latitude and longitude, or leave both blank."
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
        if self.latitude is None or self.longitude is None:
            return ""
        return f"{self.latitude}, {self.longitude}"

    def __str__(self):
        return f"{self.name} — {self.member.full_name}"


class FarmCropSeason(OrganisationOwnedModel):
    class YieldUnit(models.TextChoices):
        KILOGRAMS = "kg", "Kilograms"
        TONNES = "tonnes", "Tonnes"
        BAGS = "bags", "Bags"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="crop_seasons")
    crop = models.ForeignKey(Crop, on_delete=models.PROTECT, related_name="farm_seasons")
    season = models.CharField(max_length=120)
    planting_start = models.DateField(null=True, blank=True)
    planting_end = models.DateField(null=True, blank=True)
    estimated_yield = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    actual_yield = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    yield_unit = models.CharField(max_length=10, choices=YieldUnit.choices, default=YieldUnit.KILOGRAMS)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-planting_start", "season", "crop__name"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "crop", "season"], name="unique_farm_crop_season"),
            models.CheckConstraint(condition=models.Q(estimated_yield__isnull=True) | models.Q(estimated_yield__gte=0), name="estimated_yield_nonnegative"),
            models.CheckConstraint(condition=models.Q(actual_yield__isnull=True) | models.Q(actual_yield__gte=0), name="actual_yield_nonnegative"),
        ]
        indexes = [models.Index(fields=["organisation", "farm"]), models.Index(fields=["organisation", "crop"]), models.Index(fields=["organisation", "season"])]

    def clean(self):
        errors = {}
        self.season = self.season.strip()
        if not self.season:
            errors["season"] = "Season or planting period is required."
        if self.farm_id and self.organisation_id and self.farm.organisation_id != self.organisation_id:
            errors["farm"] = "Farm must belong to the same organisation."
        if self.crop_id and self.organisation_id and self.crop.organisation_id != self.organisation_id:
            errors["crop"] = "Crop must belong to the same organisation."
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