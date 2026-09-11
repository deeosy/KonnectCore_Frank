def tenant_context(request):
    return {"active_organisation": getattr(request, "organisation", None), "active_membership": getattr(request, "organisation_membership", None)}
