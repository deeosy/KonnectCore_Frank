"""Single owner of role-based record scope inside an organisation.

Policy (pilot):
- Organisation Admins and Managers: all operational records of the active organisation.
- Field Officers: only members assigned to active structure units for which their
  exact membership is responsible, plus records attached to those members.
- Organisation-wide operational pages (lists, reports, exports) are Admin/Manager only;
  Field Officers are redirected to the Field Workspace.
"""
from functools import wraps

from django.shortcuts import redirect

from apps.members.models import Member

from .decorators import organisation_required
from .models import OrganisationMembership

OPERATIONAL_ROLES = (OrganisationMembership.Role.ADMIN, OrganisationMembership.Role.MANAGER)


def is_field_officer(request):
    membership = getattr(request, "organisation_membership", None)
    return bool(membership and membership.role == OrganisationMembership.Role.FIELD_OFFICER)


def visible_members(request):
    """Members the current user may see in the active organisation."""
    members = Member.objects.for_organisation(request.organisation)
    membership = getattr(request, "organisation_membership", None)
    if not membership:
        return members.none()
    if membership.role in OPERATIONAL_ROLES:
        return members
    if membership.role == OrganisationMembership.Role.FIELD_OFFICER:
        return members.filter(
            group_assignments__unit__field_officer=membership,
            group_assignments__unit__is_active=True,
        ).distinct()
    return members.none()


def visible_member_ids(request):
    """Subquery of visible member primary keys, for filtering related records."""
    return visible_members(request).values("pk")


def operational_staff_required(view):
    """Admin/Manager pages. Field Officers go to their Field Workspace instead."""

    @organisation_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        membership = request.organisation_membership
        if membership and membership.role == OrganisationMembership.Role.FIELD_OFFICER:
            return redirect("field_home")
        if not membership or membership.role not in OPERATIONAL_ROLES:
            return redirect("entrypoint")
        return view(request, *args, **kwargs)

    return wrapped
