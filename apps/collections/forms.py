from django import forms
from django.db.models import Q

from apps.farms.models import Crop
from apps.members.models import Member

from apps.core.submissions import add_submission_key

from .models import CollectionRecord

MAX_IMAGE_BYTES = 5 * 1024 * 1024


class LimitedImageField(forms.ImageField):
    def to_python(self, data):
        if data and getattr(data, "size", 0) > MAX_IMAGE_BYTES:
            raise forms.ValidationError("Photo must be 5 MB or smaller.")
        return super().to_python(data)


class CollectionFilterForm(forms.Form):
    q = forms.CharField(required=False)
    member = forms.UUIDField(required=False)
    crop = forms.UUIDField(required=False)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)


class CollectionVoidForm(forms.Form):
    """Void a collection (UAT I-5). See docs/architecture.md, Voiding collections."""

    DECISION_NOT_RELATED = "not_related"
    DECISION_RELATED = "related"
    DECISIONS = [
        (DECISION_NOT_RELATED, "Not related to this collection"),
        (DECISION_RELATED, "Related - I will link the payment first"),
    ]

    void_reason = forms.CharField(
        label="Reason for voiding",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="For example: duplicate entry, recorded for the wrong member.",
    )

    def __init__(self, *args, unresolved_payments=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.unresolved_payments = list(unresolved_payments)
        if self.unresolved_payments:
            self.fields["reviewed"] = forms.BooleanField(
                label="I have reviewed the payments listed above",
                required=True,
            )
            self.fields["review_decision"] = forms.ChoiceField(
                label="Are any of these payments for this collection?",
                choices=self.DECISIONS,
                widget=forms.RadioSelect,
            )
            self.fields["review_reason"] = forms.CharField(
                label="Reason for your decision",
                widget=forms.Textarea(attrs={"rows": 2}),
            )

    def clean_void_reason(self):
        value = self.cleaned_data["void_reason"].strip()
        if not value:
            raise forms.ValidationError("Give a reason for voiding this collection.")
        return value

    def clean_review_reason(self):
        value = self.cleaned_data.get("review_reason", "").strip()
        if not value:
            raise forms.ValidationError("Explain your decision about these payments.")
        return value

    def clean(self):
        data = super().clean()
        if data.get("review_decision") == self.DECISION_RELATED:
            raise forms.ValidationError(
                "Link the related payment to this collection (or the correct collection) before voiding. "
                "Do not cancel a genuine payment to allow a void."
            )
        return data

    def review_record(self):
        """Stored on the collection with the void."""
        if not self.unresolved_payments:
            return None
        return {
            "decision": self.cleaned_data["review_decision"],
            "reason": self.cleaned_data["review_reason"],
            "payment_ids": [str(p.pk) for p in self.unresolved_payments],
        }


class CollectionRecordForm(forms.ModelForm):
    photo = LimitedImageField(required=False)

    class Meta:
        model = CollectionRecord
        fields = [
            "member", "crop", "quantity", "quantity_unit", "collection_date",
            "collection_location", "quality_grade", "price_per_unit", "photo", "notes",
        ]
        widgets = {
            "collection_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "price_per_unit": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, organisation, recorded_by, **kwargs):
        self.organisation = organisation
        self.recorded_by = recorded_by
        super().__init__(*args, **kwargs)
        self.instance.organisation = organisation
        if self.instance._state.adding:
            self.instance.recorded_by = recorded_by
        self.fields["member"].queryset = Member.objects.for_organisation(organisation)
        crops = Crop.objects.for_organisation(organisation).filter(is_active=True)
        if not self.instance._state.adding and self.instance.crop_id:
            crops = Crop.objects.for_organisation(organisation).filter(
                Q(is_active=True) | Q(pk=self.instance.crop_id)
            )
        self.fields["crop"].queryset = crops
        add_submission_key(self)

    def save(self, commit=True):
        record = super().save(commit=False)
        record.organisation = self.organisation
        if record._state.adding:
            record.recorded_by = self.recorded_by
        record.total_value = record.calculate_total()
        record.full_clean()
        if commit:
            record.save()
        return record