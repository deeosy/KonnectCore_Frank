from .models import Organisation, OrganisationMembership


class ActiveOrganisationMiddleware:
    SESSION_KEY = "active_organisation_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organisation = None
        request.organisation_membership = None
        if request.user.is_authenticated and not request.user.is_superuser:
            memberships = OrganisationMembership.objects.select_related("organisation").filter(
                user=request.user,
                is_active=True,
                organisation__status=Organisation.Status.ACTIVE,
            )
            selected = request.session.get(self.SESSION_KEY)
            membership = memberships.filter(organisation_id=selected).first() if selected else None
            if selected is None and memberships.count() == 1:
                membership = memberships.first()
                request.session[self.SESSION_KEY] = membership.organisation_id
            elif selected is not None and membership is None:
                request.session.pop(self.SESSION_KEY, None)
            if membership:
                request.organisation_membership = membership
                request.organisation = membership.organisation
        return self.get_response(request)
