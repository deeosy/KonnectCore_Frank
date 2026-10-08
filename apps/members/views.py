from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.farms.forms import MemberFarmForm
from apps.farms.models import Farm
from apps.finance.models import FinancialRecord
from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import operational_staff_required, visible_member_ids, visible_members

from .forms import MemberDocumentForm, MemberForm, MemberImportForm
from .models import Member, MemberDocument, MemberHistory
from .services import changed_fields, import_members, member_snapshot, record_history


# Kennedy feedback item 5: "Sort by" on the Members list. Keys are the only accepted ?sort= values.
MEMBER_SORT_OPTIONS = (
    ("name", "Name (A-Z)"),
    ("joined", "Date joined (newest)"),
    ("updated", "Last updated"),
    ("farm_size", "Farm size (largest)"),
    ("owed_to_member", "Owed to member (highest)"),
    ("owed_by_member", "Owed by member (highest)"),
)
NAME_ORDER = ("first_name", "last_name", "membership_number")
ACRES_TO_HECTARES = Decimal("0.404686")
SORT_DECIMAL = DecimalField(max_digits=24, decimal_places=6)


def _member_total(subquery):
    """Per-member total from a subquery, 0 when the member has no rows."""
    return Coalesce(Subquery(subquery, output_field=SORT_DECIMAL), Value(Decimal("0")), output_field=SORT_DECIMAL)


def _outstanding_total(record_types):
    open_amount = ExpressionWrapper(F("amount") - F("paid_amount"), output_field=SORT_DECIMAL)
    rows = (
        FinancialRecord.objects.filter(member=OuterRef("pk"), record_type__in=record_types)
        .exclude(status=FinancialRecord.Status.CANCELLED)
        .values("member").annotate(total=Sum(open_amount)).values("total")
    )
    return _member_total(rows)


def sort_members(members, sort):
    """Order an already-scoped member queryset by one of MEMBER_SORT_OPTIONS (name otherwise)."""
    if sort == "joined":
        return members.order_by("-created_at", *NAME_ORDER)
    if sort == "updated":
        return members.order_by("-updated_at", *NAME_ORDER)
    if sort == "farm_size":
        hectares = Case(
            When(size_unit=Farm.SizeUnit.ACRES, then=F("size") * Value(ACRES_TO_HECTARES)),
            default=F("size"), output_field=SORT_DECIMAL,
        )
        rows = Farm.objects.filter(member=OuterRef("pk"), size__isnull=False).values("member").annotate(total=Sum(hectares)).values("total")
        return members.annotate(sort_farm_hectares=_member_total(rows)).order_by("-sort_farm_hectares", *NAME_ORDER)
    if sort == "owed_to_member":
        total = _outstanding_total([FinancialRecord.Type.MEMBER_PAYMENT])
        return members.annotate(sort_owed_to_member=total).order_by("-sort_owed_to_member", *NAME_ORDER)
    if sort == "owed_by_member":
        total = _outstanding_total([FinancialRecord.Type.DUE, FinancialRecord.Type.CONTRIBUTION])
        return members.annotate(sort_owed_by_member=total).order_by("-sort_owed_by_member", *NAME_ORDER)
    return members.order_by(*NAME_ORDER)


def save_member_form(form, *, organisation, actor, creating):
    """Save a MemberForm, turning model/database duplicate errors into form errors.

    Returns the saved member, or None when errors were added to the form.
    """
    member = form.save(commit=False)
    if creating:
        member.organisation = organisation
        member.created_by = actor
    member.updated_by = actor
    try:
        member.full_clean()
        with transaction.atomic():
            member.save()
    except ValidationError as exc:
        for field, errors in exc.message_dict.items():
            target = field if field in form.fields else None
            for error in errors:
                form.add_error(target if target else "membership_number" if "membership number" in error.lower() else None, error)
        return None
    except IntegrityError:
        form.add_error("membership_number", "This membership number already exists in this organisation.")
        return None
    return member


@operational_staff_required
def member_list(request):
    members = Member.objects.for_organisation(request.organisation)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        members = members.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(membership_number__icontains=query)
            | Q(id_reference__icontains=query)
            | Q(location__icontains=query)
        )
    if status in Member.Status.values:
        members = members.filter(status=status)
    else:
        # Archived members are hidden by default; choose the Archived filter to see them.
        members = members.exclude(status=Member.Status.ARCHIVED)
    sort = request.GET.get("sort", "").strip()
    if sort not in dict(MEMBER_SORT_OPTIONS):
        sort = "name"
    members = sort_members(members, sort)
    return render(request, "members/member_list.html", {
        "members": members,
        "query": query,
        "selected_status": status,
        "statuses": Member.Status.choices,
        "sort": sort,
        "sort_options": MEMBER_SORT_OPTIONS,
    })


@operational_staff_required
def member_detail(request, member_id):
    member = get_object_or_404(
        Member.objects.for_organisation(request.organisation).prefetch_related("documents", "history__actor", "farms__crop_seasons__crop", "collection_records__crop", "collection_records__recorded_by", "financial_records__recorded_by", "field_visits__recorded_by"),
        pk=member_id,
    )
    return render(request, "members/member_detail.html", {"member": member})


def create_member_with_farm(form, farm_form, *, organisation, actor):
    """Save a new member plus the optional farm and crops in one transaction.

    Returns the member, or None when errors were added to either form (nothing is kept).
    """
    with transaction.atomic():
        member = save_member_form(form, organisation=organisation, actor=actor, creating=True)
        if member is None:
            return None
        try:
            farm_form.save_for(member)
        except ValidationError as exc:
            transaction.set_rollback(True)
            for field, errors in exc.message_dict.items():
                for error in errors:
                    farm_form.add_error(field if field in farm_form.fields else None, error)
            return None
        record_history(member, MemberHistory.Action.CREATED, actor, {"member": member_snapshot(member)})
    return member


@manager_or_admin_required
def member_create(request):
    form = MemberForm(request.POST or None, request.FILES or None, organisation=request.organisation)
    farm_form = MemberFarmForm(request.POST or None, organisation=request.organisation)
    if request.method == "POST":
        member_valid = form.is_valid()
        farm_valid = farm_form.is_valid()
        if member_valid and farm_valid:
            member = create_member_with_farm(form, farm_form, organisation=request.organisation, actor=request.user)
            if member is not None:
                messages.success(request, "Member added.")
                return redirect("member_detail", member_id=member.pk)
    return render(request, "members/member_form.html", {"form": form, "farm_form": farm_form, "title": "Add member"})


@manager_or_admin_required
def member_edit(request, member_id):
    member = get_object_or_404(Member.objects.for_organisation(request.organisation), pk=member_id)
    before = member_snapshot(member)
    form = MemberForm(request.POST or None, request.FILES or None, instance=member, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        saved = save_member_form(form, organisation=request.organisation, actor=request.user, creating=False)
        if saved is not None:
            changes = changed_fields(before, member_snapshot(saved))
            if changes:
                record_history(saved, MemberHistory.Action.UPDATED, request.user, changes)
            messages.success(request, "Member updated.")
            return redirect("member_detail", member_id=saved.pk)
    return render(request, "members/member_form.html", {"form": form, "member": member, "title": "Edit member"})


def _status_before_archive(member):
    """Status recorded when the member was last archived; Active if unknown."""
    event = member.history.filter(action=MemberHistory.Action.ARCHIVED).order_by("-created_at").first()
    previous = (event.changes or {}).get("previous_status") if event else None
    if previous in Member.Status.values and previous != Member.Status.ARCHIVED:
        return previous
    return Member.Status.ACTIVE


@manager_or_admin_required
def member_archive(request, member_id):
    """Archive or restore a member (UAT I-5). Records and historical reports are kept."""
    member = get_object_or_404(Member.objects.for_organisation(request.organisation), pk=member_id)
    archiving = member.status != Member.Status.ARCHIVED
    error = ""
    reason = ""
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            error = "Give a reason for archiving this member." if archiving else "Give a reason for restoring this member."
        else:
            with transaction.atomic():
                locked = Member.objects.select_for_update().get(pk=member.pk, organisation=request.organisation)
                if (locked.status != Member.Status.ARCHIVED) != archiving:
                    messages.info(request, "This member's archive status was already changed.")
                    return redirect("member_detail", member_id=member.pk)
                previous = locked.status
                locked.status = Member.Status.ARCHIVED if archiving else _status_before_archive(locked)
                locked.updated_by = request.user
                locked.save(update_fields=["status", "updated_by", "updated_at"])
                record_history(
                    locked,
                    MemberHistory.Action.ARCHIVED if archiving else MemberHistory.Action.RESTORED,
                    request.user,
                    {"previous_status": previous, "new_status": locked.status, "reason": reason},
                )
            messages.success(
                request,
                "Member archived. Their records stay in historical reports." if archiving else "Member restored.",
            )
            return redirect("member_detail", member_id=member.pk)
    return render(request, "members/member_archive.html", {
        "member": member,
        "archiving": archiving,
        "error": error,
        "reason": reason,
        "restore_status": None if archiving else Member.Status(_status_before_archive(member)).label,
    })


@manager_or_admin_required
def member_document_add(request, member_id):
    member = get_object_or_404(Member.objects.for_organisation(request.organisation), pk=member_id)
    form = MemberDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.organisation = request.organisation
        document.member = member
        document.uploaded_by = request.user
        document.full_clean()
        document.save()
        record_history(member, MemberHistory.Action.DOCUMENT_ADDED, request.user, {"title": document.title})
        messages.success(request, "Document attached.")
        return redirect("member_detail", member_id=member.pk)
    return render(request, "members/member_document_form.html", {"form": form, "member": member})


@organisation_required
def member_photo(request, member_id):
    member = get_object_or_404(visible_members(request), pk=member_id)
    if not member.photo:
        raise Http404("Member has no photo.")
    return FileResponse(member.photo.open("rb"), content_type="image/*")


@organisation_required
def member_document_download(request, document_id):
    document = get_object_or_404(
        MemberDocument.objects.for_organisation(request.organisation)
        .filter(member_id__in=visible_member_ids(request))
        .select_related("member"),
        pk=document_id,
        member__organisation=request.organisation,
    )
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=Path(document.file.name).name,
    )


@manager_or_admin_required
def member_import(request):
    form = MemberImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            created = import_members(form.cleaned_data["file"], request.organisation, request.user)
        except ValidationError as exc:
            for error in exc.messages:
                form.add_error("file", error)
        else:
            messages.success(request, f"Imported {len(created)} member(s).")
            return redirect("member_list")
    return render(request, "members/member_import.html", {"form": form})
