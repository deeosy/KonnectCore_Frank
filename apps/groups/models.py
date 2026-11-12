import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.members.models import Member
from apps.organisations.models import OrganisationMembership, OrganisationOwnedModel


# ==============================================================================
# STRUCTURE UNIT MODEL
# = : Defines the organizational hierarchy (e.g., Region, District, Group).
# ==============================================================================
class StructureUnit(OrganisationOwnedModel):
    """
    Represents organizational units like Regions, Districts, Branches, Communities,
    or Groups. Units can be nested (e.g., a Group within a Community).
    """
    class Type(models.TextChoices):
        REGION = "region", "Region"
        DISTRICT = "district", "District"
        BRANCH = "branch", "Branch"
        COMMUNITY = "community", "Community"
        GROUP = "group", "Group"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    unit_type = models.CharField(max_length=16, choices=Type.choices)

    # Hierarchical structure: a unit can have a 'parent' (e.g., District is parent to Branch).
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")

    # The designated leader of this specific unit.
    leader = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL, related_name="led_structure_units")

    # The field officer responsible for this unit.
    field_officer = models.ForeignKey(
        OrganisationMembership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="responsible_structure_units",
    )

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            # Unique constraints to ensure no duplicate names at the same level.
            models.UniqueConstraint(
                fields=["organisation", "parent", "name"],
                condition=models.Q(parent__isnull=False),
                name="unique_org_parent_unit_name",
            ),
            models.UniqueConstraint(
                fields=["organisation", "name"],
                condition=models.Q(parent__isnull=True),
                name="unique_org_root_unit_name",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "unit_type"]),
            models.Index(fields=["organisation", "parent"]),
        ]

    def clean(self):
        """Validates hierarchy, leadership, and staff responsibilities."""
        errors = {}
        if self.parent_id:
            # Prevent circular references (e.g., unit being parent to itself).
            if self.parent_id == self.pk:
                errors["parent"] = "A unit cannot be its own parent."
            elif self.parent.organisation_id != self.organisation_id:
                errors["parent"] = "Parent must belong to the same organisation."
            else:
                # Cycle detection: Ensure this new parent doesn't lead back to this unit.
                ancestor = self.parent
                visited = set()
                while ancestor:
                    if ancestor.pk == self.pk or ancestor.pk in visited:
                        errors["parent"] = "This parent would create a hierarchy cycle."
                        break
                    visited.add(ancestor.pk)
                    ancestor = ancestor.parent

        # Verify leader is part of the same organisation.
        if self.leader_id and self.leader.organisation_id != self.organisation_id:
            errors["leader"] = "Leader must belong to the same organisation."

        # Verify field officer is active and part of the same organisation.
        if self.field_officer_id:
            officer = self.field_officer
            if officer.organisation_id != self.organisation_id:
                errors["field_officer"] = "Field Officer must belong to the same organisation."
            elif officer.role != OrganisationMembership.Role.FIELD_OFFICER or not officer.is_active:
                errors["field_officer"] = "Select an active Field Officer membership."
        if errors:
            raise ValidationError(errors)

    @property
    def member_count(self):
        """Quickly count members assigned to this unit."""
        return self.member_assignments.count()

    def __str__(self):
        return f"{self.name} ({self.get_unit_type_display()})"


# ==============================================================================
# GROUP MEMBER ASSIGNMENT MODEL
# = : Links a Member to a StructureUnit (e.g., assigning a farmer to a village group).
# ==============================================================================
class GroupMemberAssignment(OrganisationOwnedModel):
    """
    Acts as a bridge between Members and StructureUnits.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit = models.ForeignKey(StructureUnit, on_delete=models.CASCADE, related_name="member_assignments")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="group_assignments")
    joined_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["member__first_name", "member__last_name"]
        # Ensure a member is only assigned to a unit once.
        constraints = [
            models.UniqueConstraint(fields=["unit", "member"], name="unique_unit_member_assignment"),
        ]
        indexes = [
            models.Index(fields=["organisation", "unit"]),
            models.Index(fields=["organisation", "member"]),
        ]

    def clean(self):
        """Ensure both member and unit belong to the organisation."""
        errors = {}
        if self.unit_id and self.unit.organisation_id != self.organisation_id:
            errors["unit"] = "Unit must belong to the same organisation."
        if self.member_id and self.member.organisation_id != self.organisation_id:
            errors["member"] = "Member must belong to the same organisation."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.member} · {self.unit}"
