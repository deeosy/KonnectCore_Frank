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
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}), "latitude": forms.NumberInput(attrs={"step": "0.000001"}), "longitude": forms.NumberInput(attrs={"step": "0.000001"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.for_organisation(self.organisation)


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