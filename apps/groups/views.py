from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import operational_staff_required

from .forms import GroupMemberAssignmentForm, StructureUnitForm
from .models import GroupMemberAssignment, StructureUnit


@operational_staff_required
def structure_list(request):
    units = StructureUnit.objects.for_organisation(request.organisation).select_related(
        "parent", "leader", "field_officer__user"
    ).annotate(assigned_member_count=Count("member_assignments", distinct=True))
    query = request.GET.get("q", "").strip()
    unit_type = request.GET.get("type", "").strip()
    if query:
        units = units.filter(
            Q(name__icontains=query)
            | Q(parent__name__icontains=query)
            | Q(leader__first_name__icontains=query)
            | Q(leader__last_name__icontains=query)
        )
    if unit_type in StructureUnit.Type.values:
        units = units.filter(unit_type=unit_type)
    return render(request, "groups/structure_list.html", {
        "units": units,
        "query": query,
        "selected_type": unit_type,
        "unit_types": StructureUnit.Type.choices,
    })


@operational_staff_required
def structure_detail(request, unit_id):
    unit = get_object_or_404(
        StructureUnit.objects.for_organisation(request.organisation).select_related(
            "parent", "leader", "field_officer__user"
        ).prefetch_related("children", "member_assignments__member"),
        pk=unit_id,
    )
    return render(request, "groups/structure_detail.html", {"unit": unit})


@manager_or_admin_required
def structure_create(request):
    form = StructureUnitForm(request.POST or None, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        messages.success(request, f"{unit.get_unit_type_display()} created.")
        return redirect("structure_detail", unit_id=unit.pk)
    return render(request, "groups/structure_form.html", {"form": form, "title": "Create structure unit"})


@manager_or_admin_required
def structure_edit(request, unit_id):
    unit = get_object_or_404(StructureUnit.objects.for_organisation(request.organisation), pk=unit_id)
    form = StructureUnitForm(request.POST or None, instance=unit, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        messages.success(request, f"{unit.get_unit_type_display()} updated.")
        return redirect("structure_detail", unit_id=unit.pk)
    return render(request, "groups/structure_form.html", {"form": form, "unit": unit, "title": "Edit structure unit"})


@manager_or_admin_required
def assignment_add(request, unit_id):
    unit = get_object_or_404(StructureUnit.objects.for_organisation(request.organisation), pk=unit_id)
    form = GroupMemberAssignmentForm(
        request.POST or None,
        organisation=request.organisation,
        unit=unit,
    )
    if request.method == "POST" and form.is_valid():
        assignment = form.save()
        messages.success(request, f"{assignment.member.full_name} assigned.")
        return redirect("structure_detail", unit_id=unit.pk)
    return render(request, "groups/assignment_form.html", {"form": form, "unit": unit})


@manager_or_admin_required
@require_POST
def assignment_remove(request, unit_id, assignment_id):
    unit = get_object_or_404(StructureUnit.objects.for_organisation(request.organisation), pk=unit_id)
    assignment = get_object_or_404(
        GroupMemberAssignment.objects.for_organisation(request.organisation),
        pk=assignment_id,
        unit=unit,
    )
    member_name = assignment.member.full_name
    assignment.delete()
    messages.success(request, f"{member_name} removed from {unit.name}.")
    return redirect("structure_detail", unit_id=unit.pk)
