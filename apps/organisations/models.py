from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

# ==============================================================================
# ORGANISATION MODEL
# = : Represents a business, cooperative, or NGO using the platform.
# = : Each Organisation has its own private workspace and data.
# ==============================================================================
class Organisation(models.Model):
    """
    The core 'Tenant' model. Every farmer, farm, and transaction belongs to
    one of these organisations.
    """

    # TextChoices allows us to define human-readable names for database values.
    # Access these using Organisation.Status.ACTIVE
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=180)

    # The 'slug' is a URL-friendly version of the name (e.g., 'kofi-farms').
    # It is used in the URL to identify which organisation workspace to load.
    slug = models.SlugField(unique=True)

    # Currency used for all financial calculations within this organisation.
    currency = models.CharField(max_length=3, default="USD")

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    # Metadata for auditing when the organisation was created/updated.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==============================================================================
# ORGANISATION MEMBERSHIP MODEL
# = : Links a User (from apps.accounts) to an Organisation with a specific Role.
# = : This is the foundation of Role-Based Access Control (RBAC).
# ==============================================================================
class OrganisationMembership(models.Model):
    """
    Determines what a user can do within a specific organisation.
    A user could theoretically belong to multiple organisations with different roles.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"                   # Full control
        MANAGER = "manager", "Manager"             # Operational control
        FIELD_OFFICER = "field_officer", "Field Officer" # Restricted to field tasks

    # ForeignKey creates a many-to-one relationship.
    # on_delete=models.CASCADE means if the organisation is deleted, the membership is too.
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="memberships"
    )

    # Links to the User identity (found in apps/accounts/models.py).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organisation_memberships"
    )

    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevents the same user from having duplicate memberships in one organisation.
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "user"],
                name="unique_org_user_membership"
            )
        ]
        ordering = ["user__first_name", "user__email"]

    def clean(self):
        """
        Validation logic: Prevent activating a user if the parent organisation is suspended.
        """
        if self.organisation_id and self.organisation.status != Organisation.Status.ACTIVE and self.is_active:
            raise ValidationError("Cannot activate membership for an inactive organisation.")

    def __str__(self):
        return f"{self.user} · {self.organisation} · {self.get_role_display()}"


# ==============================================================================
# MULTI-TENANCY TOOLS (QuerySet and Base Model)
# = : These are the most important tools for ensuring data privacy.
# ==============================================================================

class OrganisationQuerySet(models.QuerySet):
    """
    Custom QuerySet that provides a helper method to filter data by organisation.
    Usage: Member.objects.for_organisation(current_org)
    """
    def for_organisation(self, organisation):
        if not organisation or not getattr(organisation, "pk", None):
            # If no organisation is provided, return an empty list for safety.
            return self.none()
        return self.filter(organisation=organisation)


class OrganisationOwnedModel(models.Model):
    """
    AN ABSTRACT BASE CLASS.
    Almost every other model in the project (Member, Farm, Collection) inherits
    from this class. This ensures every record is linked to an organisation
    and uses our security-focused QuerySet by default.
    """
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)

    # Overriding the default manager with our custom one.
    objects = OrganisationQuerySet.as_manager()

    class Meta:
        # abstract = True means Django won't create a database table for this class.
        # It only exists to be inherited by other classes.
        abstract = True


# These imports are at the bottom to avoid 'circular import' errors.
from .invitations import StaffInvitation  # noqa: E402,F401
from .password_resets import StaffPasswordReset  # noqa: E402,F401
