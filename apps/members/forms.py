from pathlib import Path

from django import forms

from .models import Member, MemberDocument

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


def normalise_membership_number(value):
    """Single normalisation rule shared by forms, imports and the model."""
    return (value or "").strip()


def membership_number_taken(organisation, number, exclude_pk=None):
    """Case-insensitive duplicate check within one organisation."""
    queryset = Member.objects.for_organisation(organisation).filter(membership_number__iexact=number)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.exists()


def duplicate_number_message(number):
    return f"Membership number {number} already exists in this organisation."


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "first_name", "last_name", "phone", "membership_number",
            "id_reference", "location", "photo", "status",
        ]

    def __init__(self, *args, organisation=None, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

    def clean_membership_number(self):
        number = normalise_membership_number(self.cleaned_data.get("membership_number"))
        if not number:
            raise forms.ValidationError("Membership number is required.")
        if self.organisation is not None and membership_number_taken(
            self.organisation, number, exclude_pk=self.instance.pk if not self.instance._state.adding else None
        ):
            raise forms.ValidationError(duplicate_number_message(number))
        return number

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and getattr(photo, "size", 0) > MAX_IMAGE_BYTES:
            raise forms.ValidationError("Photo must be 5 MB or smaller.")
        return photo


class MemberDocumentForm(forms.ModelForm):
    class Meta:
        model = MemberDocument
        fields = ["title", "file"]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > MAX_DOCUMENT_BYTES:
            raise forms.ValidationError("Document must be 10 MB or smaller.")
        if Path(uploaded.name).suffix.lower() not in ALLOWED_DOCUMENT_SUFFIXES:
            raise forms.ValidationError("Upload a PDF or image file.")
        return uploaded


class MemberImportForm(forms.Form):
    file = forms.FileField(help_text="CSV or XLSX, maximum 5 MB.")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise forms.ValidationError("Upload a CSV or XLSX file.")
        if uploaded.size > MAX_IMAGE_BYTES:
            raise forms.ValidationError("Import file must be 5 MB or smaller.")
        return uploaded
