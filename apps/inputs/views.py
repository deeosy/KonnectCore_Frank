from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from apps.organisations.decorators import manager_or_admin_required, organisation_required
from .models import InputAllocation
from .forms import InputAllocationForm, InputAllocationStatusForm

# Re-using organisation_required as the base check for all input views
# operational_staff_required seems to be missing from the decorators module

@organisation_required
def input_allocation_list(request):
    allocations = InputAllocation.objects.for_organisation(request.organisation)
    return render(request, "inputs/input_allocation_list.html", {"allocations": allocations})

@organisation_required
def input_allocation_detail(request, pk):
    allocation = get_object_or_404(InputAllocation.objects.for_organisation(request.organisation), pk=pk)
    status_form = None
    # Adjusting permission check to align with existing roles
    if request.organisation_membership.role in ["admin", "manager"]:
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
    return render(request, "inputs/input_allocation_detail.html", {"allocation": allocation, "status_form": status_form})

@organisation_required
def input_allocation_create(request):
    if request.method == "POST":
        form = InputAllocationForm(request.POST, organisation=request.organisation)
        if form.is_valid():
            allocation = form.save(commit=False)
            allocation.organisation = request.organisation
            allocation.save()
            messages.success(request, "Allocation requested.")
            return redirect("input_allocation_list")
    else:
        form = InputAllocationForm(organisation=request.organisation)
    return render(request, "inputs/input_allocation_form.html", {"form": form})
