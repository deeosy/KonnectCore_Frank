from pathlib import Path

from django import forms

from .models import Member, MemberDocument

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "first_name", "last_name", "phone", "membership_number",
            "id_reference", "location", "photo", "status",
        ]

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
