from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.members.models import Member
from apps.organisations.decorators import manager_or_admin_required, organisation_required
from apps.organisations.scope import operational_staff_required

from .forms import CropForm, FarmCropSeasonForm, FarmForm
from .models import Crop, Farm, FarmCropSeason


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


@operational_staff_required
def farm_detail(request, farm_id):
    farm = get_object_or_404(Farm.objects.for_organisation(request.organisation).select_related("member").prefetch_related("crop_seasons__crop"), pk=farm_id)
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
    return render(request, "farms/model_form.html", {"form": form, "title": "Register farm", "cancel_url": "farm_list"})


@manager_or_admin_required
def farm_edit(request, farm_id):
    farm = get_object_or_404(Farm.objects.for_organisation(request.organisation), pk=farm_id)
    form = FarmForm(request.POST or None, instance=farm, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        farm = form.save()
        messages.success(request, "Farm profile updated.")
        return redirect("farm_detail", farm_id=farm.pk)
    return render(request, "farms/model_form.html", {"form": form, "title": "Edit farm", "cancel_object": farm})


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