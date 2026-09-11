from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.organisations.decorators import manager_or_admin_required, organisation_required

from .forms import MemberDocumentForm, MemberForm, MemberImportForm
from .models import Member, MemberDocument, MemberHistory
from .services import changed_fields, import_members, member_snapshot, record_history


@organisation_required
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
    return render(request, "members/member_list.html", {
        "members": members,
        "query": query,
        "selected_status": status,
        "statuses": Member.Status.choices,
    })


@organisation_required
def member_detail(request, member_id):
    member = get_object_or_404(
        Member.objects.for_organisation(request.organisation).prefetch_related("documents", "history__actor"),
        pk=member_id,
    )
    return render(request, "members/member_detail.html", {"member": member})


@manager_or_admin_required
def member_create(request):
    form = MemberForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        member.organisation = request.organisation
        member.created_by = request.user
        member.updated_by = request.user
        member.full_clean()
        member.save()
        record_history(member, MemberHistory.Action.CREATED, request.user, {"member": member_snapshot(member)})
        messages.success(request, "Member registered.")
        return redirect("member_detail", member_id=member.pk)
    return render(request, "members/member_form.html", {"form": form, "title": "Register member"})


@manager_or_admin_required
def member_edit(request, member_id):
    member = get_object_or_404(Member.objects.for_organisation(request.organisation), pk=member_id)
    before = member_snapshot(member)
    form = MemberForm(request.POST or None, request.FILES or None, instance=member)
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        member.updated_by = request.user
        member.full_clean()
        member.save()
        changes = changed_fields(before, member_snapshot(member))
        if changes:
            record_history(member, MemberHistory.Action.UPDATED, request.user, changes)
        messages.success(request, "Member updated.")
        return redirect("member_detail", member_id=member.pk)
    return render(request, "members/member_form.html", {"form": form, "member": member, "title": "Edit member"})


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
    member = get_object_or_404(Member.objects.for_organisation(request.organisation), pk=member_id)
    if not member.photo:
        raise Http404("Member has no photo.")
    return FileResponse(member.photo.open("rb"), content_type="image/*")


@organisation_required
def member_document_download(request, document_id):
    document = get_object_or_404(
        MemberDocument.objects.for_organisation(request.organisation).select_related("member"),
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
