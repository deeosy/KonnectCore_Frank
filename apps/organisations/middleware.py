from .models import Organisation, OrganisationMembership


# ==============================================================================
# ACTIVE ORGANISATION MIDDLEWARE
# = : Detects which Organisation the user is currently interacting with.
# = : This is CRITICAL for multi-tenancy.
# ==============================================================================
class ActiveOrganisationMiddleware:
    """
    Sets 'request.organisation' and 'request.organisation_membership' based on:
    1. The 'active_organisation_id' stored in the user's session.
    2. Automatic selection if the user belongs to exactly one active organisation.
    """
    SESSION_KEY = "active_organisation_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Reset values on every request.
        request.organisation = None
        request.organisation_membership = None

        # 2. Only perform checks for authenticated non-superusers.
        # Superusers (platform admins) don't belong to organisations in the same way.
        if request.user.is_authenticated and not request.user.is_superuser:

            # Get all active memberships for this user.
            memberships = OrganisationMembership.objects.select_related("organisation").filter(
                user=request.user,
                is_active=True,
                organisation__status=Organisation.Status.ACTIVE,
            )

            # Check if an organisation ID is already selected in the session.
            selected = request.session.get(self.SESSION_KEY)

            # Attempt to find the corresponding membership record.
            membership = memberships.filter(organisation_id=selected).first() if selected else None

            # 3. Automatic selection: If no organisation is selected, but they
            # only belong to one, auto-select it.
            if selected is None and memberships.count() == 1:
                membership = memberships.first()
                request.session[self.SESSION_KEY] = membership.organisation_id

            # 4. Cleanup: If they were in an organisation that is no longer active
            # (or they were removed), clear the session.
            elif selected is not None and membership is None:
                request.session.pop(self.SESSION_KEY, None)

            # 5. Set request attributes if a valid membership is found.
            if membership:
                request.organisation_membership = membership
                request.organisation = membership.organisation

        # Continue to the view/next middleware.
        return self.get_response(request)
