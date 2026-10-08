from pathlib import Path

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.farms.models import Crop
from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import operational_staff_required, visible_member_ids

from apps.core.submissions import SubmissionConflict, save_once

from django.db import transaction
from django.utils import timezone

from .forms import CollectionFilterForm, CollectionRecordForm, CollectionVoidForm
from .models import CollectionRecord


def _group_member_ids(organisation, unit_id):
    """Member ids assigned to a group or any unit below it (Kennedy feedback item 8)."""
    units = StructureUnit.objects.for_organisation(organisation)
    ids = {unit_id}
    frontier = [unit_id]
    while frontier:
        frontier = [pk for pk in units.filter(parent_id__in=frontier).values_list("pk", flat=True) if pk not in ids]
        ids.update(frontier)
    return GroupMemberAssignment.objects.for_organisation(organisation).filter(unit_id__in=ids).values("member_id")


def _matching_pk(queryset, value):
    if not value:
        return ""
    value = str(value)
    return next((str(item.pk) for item in queryset if str(item.pk) == value), "")


@operational_staff_required
def collection_list(request):
    records = CollectionRecord.objects.for_organisation(request.organisation).select_related(
        "member", "crop", "recorded_by"
    )
    members = Member.objects.for_organisation(request.organisation)
    crops = Crop.objects.for_organisation(request.organisation)
    filters = CollectionFilterForm(request.GET)
    groups = StructureUnit.objects.for_organisation(request.organisation).filter(is_active=True)
    selected_member = selected_crop = selected_group = ""
    values = {"q": "", "date_from": "", "date_to": ""}
    if filters.is_valid():
        data = filters.cleaned_data
        values["q"] = data.get("q", "").strip()
        values["date_from"] = data.get("date_from") or ""
        values["date_to"] = data.get("date_to") or ""
        selected_member = _matching_pk(members, data.get("member"))
        selected_crop = _matching_pk(crops, data.get("crop"))
        selected_group = _matching_pk(groups, data.get("group"))
        if selected_group:
            records = records.filter(member_id__in=_group_member_ids(request.organisation, data["group"]))
        if values["q"]:
            records = records.filter(
                Q(member__first_name__icontains=values["q"])
                | Q(member__last_name__icontains=values["q"])
                | Q(member__membership_number__icontains=values["q"])
                | Q(collection_location__icontains=values["q"])
                | Q(quality_grade__icontains=values["q"])
            )
        if selected_member:
            records = records.filter(member_id=selected_member)
        if selected_crop:
            records = records.filter(crop_id=selected_crop)
        if values["date_from"]:
            records = records.filter(collection_date__gte=values["date_from"])
        if values["date_to"]:
            records = records.filter(collection_date__lte=values["date_to"])
    return render(request, "collections/collection_list.html", {
        "records": records,
        "members": members,
        "crops": crops,
        "query": values["q"],
        "selected_member": selected_member,
        "selected_crop": selected_crop,
        "groups": groups,
        "selected_group": selected_group,
        "date_from": values["date_from"],
        "date_to": values["date_to"],
        "filter_errors": filters.errors,
    })


@operational_staff_required
def collection_detail(request, record_id):
    record = get_object_or_404(
        CollectionRecord.objects.for_organisation(request.organisation).select_related(
            "member", "crop", "recorded_by"
        ),
        pk=record_id,
    )
    return render(request, "collections/collection_detail.html", {"record": record})


@manager_or_admin_required
def collection_create(request):
    initial = {}
    member_id = _matching_pk(
        Member.objects.for_organisation(request.organisation),
        request.GET.get("member", "").strip(),
    )
    if member_id:
        initial["member"] = member_id
    groups = StructureUnit.objects.for_organisation(request.organisation).filter(is_active=True)
    selected_group = _matching_pk(groups, request.GET.get("group", "").strip())
    member_queryset = None
    if selected_group:
        member_queryset = _group_member_ids(request.organisation, groups.get(pk=selected_group).pk)
    form = CollectionRecordForm(
        request.POST or None,
        request.FILES or None,
        organisation=request.organisation,
        recorded_by=request.user,
        initial=initial,
        member_queryset=member_queryset,
    )
    if request.method == "POST" and form.is_valid():
        try:
            record, created = save_once(form, organisation=request.organisation, actor=request.user)
        except SubmissionConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Produce collection recorded." if created else "This collection was already saved.")
            return redirect("collection_detail", record_id=record.pk)
    return render(request, "collections/collection_form.html", {
        "form": form,
        "title": "Record produce collection",
        "groups": groups,
        "selected_group": selected_group,
    })


@manager_or_admin_required
def collection_edit(request, record_id):
    record = get_object_or_404(
        CollectionRecord.objects.for_organisation(request.organisation),
        pk=record_id,
    )
    if record.is_voided:
        messages.error(request, "Voided collections cannot be edited.")
        return redirect("collection_detail", record_id=record.pk)
    form = CollectionRecordForm(
        request.POST or None,
        request.FILES or None,
        instance=record,
        organisation=request.organisation,
        recorded_by=request.user,
    )
    if request.method == "POST" and form.is_valid():
        record = form.save()
        messages.success(request, "Produce collection updated.")
        return redirect("collection_detail", record_id=record.pk)
    return render(request, "collections/collection_form.html", {
        "form": form,
        "title": "Edit produce collection",
        "record": record,
    })


def _void_blockers(record):
    """Active allocations from non-cancelled payments; any of these blocks a void."""
    return list(
        record.allocations.filter(removed_at__isnull=True)
        .exclude(payment__status="cancelled")
        .select_related("payment")
    )


def _unresolved_payments(record):
    """The member's non-cancelled payments to member with no recorded purpose."""
    from apps.finance.models import FinancialRecord

    return list(
        FinancialRecord.objects.for_organisation(record.organisation)
        .filter(member_id=record.member_id, record_type=FinancialRecord.Type.MEMBER_PAYMENT, purpose="")
        .exclude(status=FinancialRecord.Status.CANCELLED)
        .order_by("-payment_date")
    )


@manager_or_admin_required
def collection_void(request, record_id):
    record = get_object_or_404(
        CollectionRecord.objects.for_organisation(request.organisation).select_related("member", "crop"),
        pk=record_id,
    )
    if record.is_voided:
        messages.info(request, "This collection is already voided.")
        return redirect("collection_detail", record_id=record.pk)
    blockers = _void_blockers(record)
    unresolved = _unresolved_payments(record)
    form = CollectionVoidForm(request.POST or None, unresolved_payments=unresolved)
    if request.method == "POST" and not blockers and form.is_valid():
        with transaction.atomic():
            locked = CollectionRecord.objects.select_for_update().get(pk=record.pk, organisation=request.organisation)
            if locked.is_voided:
                messages.info(request, "This collection is already voided.")
                return redirect("collection_detail", record_id=record.pk)
            if _void_blockers(locked):
                messages.error(request, "A payment was allocated to this collection while you were reviewing it. Voiding is blocked.")
                return redirect("collection_void", record_id=record.pk)
            locked.voided_at = timezone.now()
            locked.voided_by = request.user
            locked.void_reason = form.cleaned_data["void_reason"]
            locked.void_review = form.review_record()
            locked.save(update_fields=["voided_at", "voided_by", "void_reason", "void_review", "updated_at"])
        messages.success(request, "Collection voided. It is excluded from totals, reports and exports, and kept here for audit.")
        return redirect("collection_detail", record_id=record.pk)
    return render(request, "collections/collection_void.html", {
        "record": record,
        "form": form,
        "blockers": blockers,
        "unresolved_payments": unresolved,
    })


@organisation_required
def collection_photo(request, record_id):
    record = get_object_or_404(
        CollectionRecord.objects.for_organisation(request.organisation).filter(
            member_id__in=visible_member_ids(request)
        ),
        pk=record_id,
    )
    if not record.photo:
        raise Http404("Collection has no photo.")
    return FileResponse(
        record.photo.open("rb"),
        content_type="image/*",
        filename=Path(record.photo.name).name,
    )