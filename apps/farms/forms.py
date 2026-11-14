from django import forms
from django.db.models import Q

from apps.members.models import Member

from .models import Crop, Farm, FarmCropSeason


class TenantModelForm(forms.ModelForm):
    def __init__(self, *args, organisation, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)
        self.instance.organisation = organisation

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.organisation = self.organisation
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class CropForm(TenantModelForm):
    class Meta:
        model = Crop
        fields = ["name", "variety", "is_active"]


class FarmForm(TenantModelForm):
    class Meta:
        model = Farm
        fields = ["member", "name", "size", "size_unit", "location", "latitude", "longitude", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "latitude": forms.HiddenInput,
            "longitude": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.for_organisation(self.organisation)

class FarmOwnershipTransferForm(forms.Form):
    successor_member = forms.ModelChoiceField(
        queryset=Member.objects.none(),
        label="Successor member",
        help_text="Choose the member who will become the recorded owner of this farm.",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Record why ownership is being transferred.",
    )

    def __init__(self, *args, organisation, current_member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["successor_member"].queryset = Member.objects.for_organisation(
            organisation
        ).filter(status=Member.Status.ACTIVE).exclude(pk=current_member.pk)


class FarmCropSeasonForm(TenantModelForm):
    class Meta:
        model = FarmCropSeason
        fields = ["crop", "season", "planting_start", "planting_end", "estimated_yield", "actual_yield", "yield_unit", "notes"]
        widgets = {"planting_start": forms.DateInput(attrs={"type": "date"}), "planting_end": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, farm, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        self.instance.farm = farm
        crops = Crop.objects.for_organisation(self.organisation).filter(is_active=True)
        if self.instance.pk and self.instance.crop_id:
            crops = Crop.objects.for_organisation(self.organisation).filter(
                Q(is_active=True) | Q(pk=self.instance.crop_id)
            )
        self.fields["crop"].queryset = crops

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.farm = self.farm
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class MemberFarmForm(forms.ModelForm):
    """Optional farm and crops captured on the Add member screen.

    Uses the "farm" prefix so its fields never clash with MemberForm (both have "location").
    Nothing is saved unless farm details or crops are entered.
    """

    DETAIL_FIELDS = ("size", "location", "latitude", "longitude")

    crops = forms.ModelMultipleChoiceField(
        queryset=Crop.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
        label="Crops grown on this farm",
    )
    season = forms.CharField(
        max_length=120, required=False, label="Season",
        help_text="For example 2026 major. Needed when crops are selected.",
    )

    class Meta:
        model = Farm
        fields = ["name", "size", "size_unit", "location", "latitude", "longitude"]
        widgets = {"latitude": forms.NumberInput(attrs={"step": "0.000001"}), "longitude": forms.NumberInput(attrs={"step": "0.000001"})}
        labels = {"name": "Farm name", "location": "Farm location"}

    def __init__(self, *args, organisation, **kwargs):
        kwargs.setdefault("prefix", "farm")
        self.organisation = organisation
        super().__init__(*args, **kwargs)
        self.instance.organisation = organisation
        self.fields["name"].required = False
        self.fields["size_unit"].required = False
        self.fields["crops"].queryset = Crop.objects.for_organisation(organisation).filter(is_active=True)

    def clean_size_unit(self):
        return self.cleaned_data.get("size_unit") or Farm.SizeUnit.HECTARES

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip() or "Main farm"

    def clean(self):
        cleaned = super().clean()
        cleaned["season"] = (cleaned.get("season") or "").strip()
        if cleaned.get("crops") and not cleaned["season"]:
            self.add_error("season", "Enter the season for the selected crops.")
        return cleaned

    def has_farm_details(self):
        data = self.cleaned_data
        return bool(data.get("crops")) or any(data.get(name) not in (None, "") for name in self.DETAIL_FIELDS)

    def save_for(self, member):
        """Save the farm and one crop season per selected crop. Call inside a transaction."""
        if not self.has_farm_details():
            return None
        farm = super().save(commit=False)
        farm.organisation = self.organisation
        farm.member = member
        farm.full_clean()
        farm.save()
        for crop in self.cleaned_data.get("crops") or []:
            season = FarmCropSeason(organisation=self.organisation, farm=farm, crop=crop, season=self.cleaned_data["season"])
            season.full_clean()
            season.save()
        return farm