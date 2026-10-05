from pathlib import Path

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.farms.models import Crop
from apps.members.models import Member
from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import operational_staff_required, visible_member_ids

from apps.core.submissions import SubmissionConflict, save_once

from .forms import CollectionFilterForm, CollectionRecordForm
from .models import CollectionRecord


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
    selected_member = selected_crop = ""
    values = {"q": "", "date_from": "", "date_to": ""}
    if filters.is_valid():
        data = filters.cleaned_data
        values["q"] = data.get("q", "").strip()
        values["date_from"] = data.get("date_from") or ""
        values["date_to"] = data.get("date_to") or ""
        selected_member = _matching_pk(members, data.get("member"))
        selected_crop = _matching_pk(crops, data.get("crop"))
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
    form = CollectionRecordForm(
        request.POST or None,
        request.FILES or None,
        organisation=request.organisation,
        recorded_by=request.user,
        initial=initial,
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
    })


@manager_or_admin_required
def collection_edit(request, record_id):
    record = get_object_or_404(
        CollectionRecord.objects.for_organisation(request.organisation),
        pk=record_id,
    )
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