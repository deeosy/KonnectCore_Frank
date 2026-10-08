from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import operational_staff_required

from .forms import GroupMemberAssignmentForm, NewMemberAssignmentForm, StructureUnitForm
from apps.farms.forms import MemberFarmForm
from apps.members.forms import MemberForm
from apps.members.models import Member
from apps.members.views import MEMBER_SORT_OPTIONS, create_member_with_farm, sort_members

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
    # Kennedy feedback item 5: same "Sort by" options as the Members list, for members within a group.
    sort = request.GET.get("sort", "").strip()
    if sort not in dict(MEMBER_SORT_OPTIONS):
        sort = "name"
    by_member = {assignment.member_id: assignment for assignment in unit.member_assignments.all()}
    ordered = sort_members(Member.objects.for_organisation(request.organisation).filter(pk__in=list(by_member)), sort)
    assignments = [by_member[member.pk] for member in ordered if member.pk in by_member]
    return render(request, "groups/structure_detail.html", {
        "unit": unit,
        "assignments": assignments,
        "sort": sort,
        "sort_options": MEMBER_SORT_OPTIONS,
    })


@manager_or_admin_required
def structure_create(request):
    form = StructureUnitForm(request.POST or None, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        messages.success(request, f"{unit.get_unit_type_display()} created.")
        if request.POST.get("next") == "members":
            # Kennedy feedback item 6: go straight to adding new members to the new unit.
            return redirect("assignment_new_member", unit_id=unit.pk)
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
def assignment_new_member(request, unit_id):
    """Kennedy feedback item 6: create a new member (with optional farm) and add them to this unit in one step."""
    unit = get_object_or_404(StructureUnit.objects.for_organisation(request.organisation), pk=unit_id)
    form = MemberForm(request.POST or None, request.FILES or None, organisation=request.organisation)
    farm_form = MemberFarmForm(request.POST or None, organisation=request.organisation)
    join_form = NewMemberAssignmentForm(request.POST or None)
    if request.method == "POST":
        results = [form.is_valid(), farm_form.is_valid(), join_form.is_valid()]
        if all(results):
            member = None
            with transaction.atomic():
                member = create_member_with_farm(form, farm_form, organisation=request.organisation, actor=request.user)
                if member is not None:
                    assignment = GroupMemberAssignment(
                        organisation=request.organisation,
                        unit=unit,
                        member=member,
                        joined_at=join_form.cleaned_data.get("joined_at"),
                    )
                    assignment.full_clean()
                    assignment.save()
            if member is not None:
                messages.success(request, f"{member.full_name} added to {unit.name}.")
                if request.POST.get("next") == "another":
                    return redirect("assignment_new_member", unit_id=unit.pk)
                return redirect("structure_detail", unit_id=unit.pk)
    return render(request, "groups/new_member_form.html", {
        "form": form,
        "farm_form": farm_form,
        "join_form": join_form,
        "unit": unit,
    })


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
