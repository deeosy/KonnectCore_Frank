from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.members.models import Member
from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import is_field_officer, operational_staff_required, visible_members

from .forms import CropForm, FarmCropSeasonForm, FarmForm, FarmOwnershipTransferForm
from .models import Crop, Farm, FarmCropSeason, FarmOwnershipTransfer


@operational_staff_required
def farm_list(request):
    farms = Farm.objects.for_organisation(request.organisation).select_related("member").prefetch_related("crop_seasons__crop")
    query = request.GET.get("q", "").strip()
    crop_id = request.GET.get("crop", "").strip()
    if query:
        farms = farms.filter(Q(name__icontains=query) | Q(location__icontains=query) | Q(member__first_name__icontains=query) | Q(member__last_name__icontains=query) | Q(member__membership_number__icontains=query))
    crops = Crop.objects.for_organisation(request.organisation)
    selected_crop = next((str(crop.pk) for crop in crops if str(crop.pk) == crop_id), "")
    if selected_crop:
        farms = farms.filter(crop_seasons__crop_id=selected_crop).distinct()
    return render(request, "farms/farm_list.html", {"farms": farms, "crops": crops, "query": query, "selected_crop": selected_crop})


@organisation_required
def harvest_coordination(request):
    """Shared machinery dashboard: nearby farmers with overlapping harvest dates.

    Admins and Managers see the whole organisation. Field Officers only see
    farmers in their assigned groups.
    """
    organisation = request.organisation
    crops = Crop.objects.for_organisation(organisation).filter(is_active=True)
    crop_id = request.GET.get("crop", "").strip()
    selected_crop = next((crop for crop in crops if str(crop.pk) == crop_id), None)
    reference_date = parse_date(request.GET.get("date", "").strip()) or timezone.localdate()
    member_ids = visible_members(request).values("pk") if is_field_officer(request) else None
    groups = FarmCropSeason.harvest_groups(
        organisation,
        crop=selected_crop,
        reference_date=reference_date,
        window_days=7,
        member_ids=member_ids,
    )
    return render(
        request,
        "farms/harvest_coordination.html",
        {
            "groups": groups,
            "crops": crops,
            "selected_crop": selected_crop,
            "reference_date": reference_date,
            "window_days": 7,
        },
    )


@operational_staff_required
def farm_detail(request, farm_id):
    farm = get_object_or_404(
        Farm.objects.for_organisation(request.organisation)
        .select_related("member")
        .prefetch_related(
            "crop_seasons__crop",
            "ownership_transfers__previous_member",
            "ownership_transfers__successor_member",
            "ownership_transfers__transferred_by",
        ),
        pk=farm_id,
    )
    return render(request, "farms/farm_detail.html", {"farm": farm})


@manager_or_admin_required
def farm_create(request):
    initial = {}
    member_id = request.GET.get("member", "").strip()
    if member_id:
        member = next(
            (item for item in Member.objects.for_organisation(request.organisation) if str(item.pk) == member_id),
            None,
        )
        if member:
            initial["member"] = member
    form = FarmForm(request.POST or None, organisation=request.organisation, initial=initial)
    if request.method == "POST" and form.is_valid():
        farm = form.save()
        messages.success(request, "Farm profile created.")
        return redirect("farm_detail", farm_id=farm.pk)
    return render(request, "farms/model_form.html", {"form": form, "title": "Add farm", "cancel_url": "farm_list"})


@manager_or_admin_required
def farm_edit(request, farm_id):
    farm = get_object_or_404(Farm.objects.for_organisation(request.organisation), pk=farm_id)
    form = FarmForm(request.POST or None, instance=farm, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        farm = form.save()
        messages.success(request, "Farm profile updated.")
        return redirect("farm_detail", farm_id=farm.pk)
    return render(request, "farms/model_form.html", {"form": form, "title": "Edit farm", "cancel_object": farm})

@manager_or_admin_required
def farm_transfer(request, farm_id):
    farm = get_object_or_404(
        Farm.objects.for_organisation(request.organisation).select_related("member"),
        pk=farm_id,
    )
    current_member = farm.member
    form = FarmOwnershipTransferForm(
        request.POST or None,
        organisation=request.organisation,
        current_member=current_member,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                locked_farm = Farm.objects.select_for_update().select_related("member").get(
                    pk=farm.pk,
                    organisation=request.organisation,
                )
                if locked_farm.member_id != current_member.pk:
                    raise ValidationError("This farm's owner changed. Reload and review the current owner.")

                previous_member = locked_farm.member
                successor = form.cleaned_data["successor_member"]
                locked_farm.member = successor
                locked_farm.full_clean()

                transfer = FarmOwnershipTransfer(
                    organisation=request.organisation,
                    farm=locked_farm,
                    previous_member=previous_member,
                    successor_member=successor,
                    transferred_by=request.user,
                    reason=form.cleaned_data["reason"].strip(),
                )
                transfer.full_clean()
                locked_farm.save(update_fields=["member", "updated_at"])
                transfer.save()
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        except IntegrityError:
            form.add_error(
                None,
                "The transfer could not be completed because the successor already has a farm with this name.",
            )
        else:
            messages.success(request, f"Farm ownership transferred to {successor.full_name}.")
            return redirect("farm_detail", farm_id=farm.pk)

    return render(
        request,
        "farms/transfer_form.html",
        {"farm": farm, "form": form},
    )


@operational_staff_required
def crop_list(request):
    crops = Crop.objects.for_organisation(request.organisation).prefetch_related("farm_seasons")
    return render(request, "farms/crop_list.html", {"crops": crops})


@manager_or_admin_required
def crop_create(request):
    form = CropForm(request.POST or None, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Crop added to the catalogue.")
        return redirect("crop_list")
    return render(request, "farms/model_form.html", {"form": form, "title": "Add crop", "cancel_url": "crop_list"})


@manager_or_admin_required
def crop_edit(request, crop_id):
    crop = get_object_or_404(Crop.objects.for_organisation(request.organisation), pk=crop_id)
    form = CropForm(request.POST or None, instance=crop, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Crop updated.")
        return redirect("crop_list")
    return render(request, "farms/model_form.html", {"form": form, "title": "Edit crop", "cancel_url": "crop_list"})


@manager_or_admin_required
def season_pick_farm(request):
    """Add Crop quick action: choose the farm, then record a crop season on it."""
    farms = Farm.objects.for_organisation(request.organisation).select_related("member").order_by("member__first_name", "member__last_name", "name")
    query = request.GET.get("q", "").strip()
    if query:
        farms = farms.filter(Q(name__icontains=query) | Q(location__icontains=query) | Q(member__first_name__icontains=query) | Q(member__last_name__icontains=query) | Q(member__membership_number__icontains=query))
    return render(request, "farms/season_pick_farm.html", {"farms": farms, "query": query})


@manager_or_admin_required
def season_create(request, farm_id):
    farm = get_object_or_404(Farm.objects.for_organisation(request.organisation), pk=farm_id)
    form = FarmCropSeasonForm(request.POST or None, organisation=request.organisation, farm=farm)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Crop season recorded.")
        return redirect("farm_detail", farm_id=farm.pk)
    return render(request, "farms/season_form.html", {"form": form, "farm": farm, "title": "Record crop season"})


@manager_or_admin_required
def season_edit(request, farm_id, season_id):
    farm = get_object_or_404(Farm.objects.for_organisation(request.organisation), pk=farm_id)
    season = get_object_or_404(FarmCropSeason.objects.for_organisation(request.organisation), pk=season_id, farm=farm)
    form = FarmCropSeasonForm(request.POST or None, instance=season, organisation=request.organisation, farm=farm)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Crop season updated.")
        return redirect("farm_detail", farm_id=farm.pk)
    return render(request, "farms/season_form.html", {"form": form, "farm": farm, "title": "Edit crop season"})