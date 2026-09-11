from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from .models import OrganisationMembership

def organisation_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.is_superuser:
            return redirect("platform_organisations")
        if not getattr(request, "organisation", None):
            return redirect("choose_organisation")
        return view(request, *args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(view):
        @organisation_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            membership = request.organisation_membership
            if not membership or membership.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

admin_required = roles_required(OrganisationMembership.Role.ADMIN)
manager_or_admin_required = roles_required(OrganisationMembership.Role.ADMIN, OrganisationMembership.Role.MANAGER)
