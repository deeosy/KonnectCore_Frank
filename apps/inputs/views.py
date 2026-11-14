from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.models import OrganisationMembership
from apps.organisations.scope import visible_members

from .forms import InputAllocationForm, InputAllocationStatusForm
from .models import InputAllocation
from .services import build_distribution_audit


def _allocations_for(request):
    """Allocations the current user may see in the active organisation."""
    allocations = InputAllocation.objects.for_organisation(request.organisation).select_related(
        "member", "verified_by"
    )
    if request.organisation_membership.role == OrganisationMembership.Role.FIELD_OFFICER:
        allocations = allocations.filter(member_id__in=visible_members(request).values("pk"))
    return allocations


@organisation_required
def input_allocation_list(request):
    allocations = _allocations_for(request)
    return render(request, "inputs/input_allocation_list.html", {"allocations": allocations})


@organisation_required
def input_allocation_detail(request, pk):
    allocation = get_object_or_404(_allocations_for(request), pk=pk)
    status_form = None
    # Only Admins and Managers may move an allocation through its workflow.
    if request.organisation_membership.role in (
        OrganisationMembership.Role.ADMIN,
        OrganisationMembership.Role.MANAGER,
    ):
        if request.method == "POST":
            status_form = InputAllocationStatusForm(request.POST, instance=allocation)
            if status_form.is_valid():
                allocation = status_form.save(commit=False)
                allocation.verified_by = request.user
                allocation.save()
                messages.success(request, "Status updated.")
                return redirect("input_allocation_detail", pk=allocation.pk)
        else:
            status_form = InputAllocationStatusForm(instance=allocation)
    return render(
        request,
        "inputs/input_allocation_detail.html",
        {"allocation": allocation, "status_form": status_form},
    )


@organisation_required
def input_allocation_create(request):
    # Field Officers may only request inputs for members in their assigned groups.
    member_queryset = visible_members(request)
    initial = {}
    member_id = request.GET.get("member", "").strip()
    if member_id:
        member = member_queryset.filter(pk=member_id).first()
        if member:
            initial["member"] = member

    if request.method == "POST":
        form = InputAllocationForm(
            request.POST,
            organisation=request.organisation,
            member_queryset=member_queryset,
            initial=initial,
        )
        if form.is_valid():
            allocation = form.save(commit=False)
            allocation.organisation = request.organisation
            allocation.full_clean()
            allocation.save()
            messages.success(request, "Allocation requested.")
            return redirect("input_allocation_list")
    else:
        form = InputAllocationForm(
            organisation=request.organisation,
            member_queryset=member_queryset,
            initial=initial,
        )
    return render(request, "inputs/input_allocation_form.html", {"form": form})


@manager_or_admin_required
def distribution_audit(request):
    """Allocations vs deliveries by region and group, for district directors."""
    audit = build_distribution_audit(request.organisation)
    return render(request, "inputs/distribution_audit.html", audit)
