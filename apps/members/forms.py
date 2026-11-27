from pathlib import Path

from django import forms
from django.core.files.uploadedfile import UploadedFile

from .identification import available_id_types, default_issuing_authority, normalize, profiles
from .models import Member, MemberDocument
from .uploads import validate_document_file, validate_id_image

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
        fields = [  # noqa: RUF012
            "first_name", "last_name", "phone", "membership_number",
            "id_type", "id_number", "id_document_name", "id_issuing_authority",
            "id_front", "id_back",
            "nok_first_name", "nok_last_name", "nok_relationship",
            "nok_phone", "nok_address",
            "location", "photo", "status",
        ]
        widgets = {  # noqa: RUF012
            "id_number": forms.TextInput(attrs={
                "autocomplete": "off", "inputmode": "numeric", "maxlength": "15",
                "placeholder": "Enter the number printed on the document.",
                "data-id-number": "",
            }),
            "id_front": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "id_back": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }
        help_texts = {  # noqa: RUF012
            "id_number": "Type only the digits; GHA and the hyphens are added automatically.",
            "id_document_name": "Required when the document type is Other.",
            "id_issuing_authority": "For example, NIA, EC, NHIA or DVLA.",
        }

    def __init__(self, *args, organisation=None, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)
        self.fields["id_type"].choices = [("", "No identification")] + available_id_types()
        self.fields["id_type"].help_text = "Choose the document first; the number field adapts automatically."
        self.fields["id_issuing_authority"].help_text = (
            "Filled automatically for standard documents; edit if needed. Required for Other."
        )
        self._id_result = None
        self._id_unchanged_legacy = False
        self._uploaded_front = False
        self._uploaded_back = False

        # Modern records edit the original digits; historical records keep their
        # formatted value until an operator actively replaces it.
        if self.instance.pk and not self.instance.id_number_raw:
            existing = self.instance.id_number_display or self.instance.id_number
            if existing:
                self.initial.setdefault("id_number", existing)
                self.fields["id_number"].widget.attrs["data-legacy-display"] = existing

    def clean(self):
        cleaned = super().clean()
        id_type = cleaned.get("id_type") or ""
        submitted = (cleaned.get("id_number") or "").strip()
        submitted_authority = (cleaned.get("id_issuing_authority") or "").strip()
        if not id_type:
            cleaned["id_document_name"] = ""
            cleaned["id_issuing_authority"] = ""
        elif id_type != Member.IDType.OTHER:
            # Issuer is derived from the document type, but an authorised
            # operator may override it when an exception is needed.
            cleaned["id_document_name"] = ""
            cleaned["id_issuing_authority"] = (
                submitted_authority or default_issuing_authority(id_type)
            )
        existing_display = self.instance.id_number_display or self.instance.id_number or ""
        self._uploaded_front = isinstance(cleaned.get("id_front"), UploadedFile)
        self._uploaded_back = isinstance(cleaned.get("id_back"), UploadedFile)

        if (submitted or cleaned.get("id_front") or cleaned.get("id_back")) and not id_type:
            self.add_error("id_type", "Choose the type of identification being verified.")

        legacy_unchanged = (
            self.instance.pk
            and not self.instance.id_number_raw
            and submitted == existing_display
            and bool(existing_display)
        )
        if id_type and not submitted and not legacy_unchanged:
            self.add_error("id_number", "Enter the identification number for this document.")

        if not submitted:
            cleaned["id_number"] = ""
            self.instance.id_number_raw = ""
            self.instance.id_number_normalized = ""
            self.instance.id_number_display = ""
            self.instance.id_verification_status = Member.IDVerificationStatus.UNVERIFIED
            self.instance.id_verified_at = None
        elif (
            self.instance.pk
            and not self.instance.id_number_raw
            and submitted == existing_display
        ):
            self._id_unchanged_legacy = True
            cleaned["id_number"] = existing_display
        else:
            try:
                result = normalize(id_type, submitted)
            except forms.ValidationError as exc:
                self.add_error("id_number", exc.messages[0])
                return cleaned
            self._id_result = result
            cleaned["id_number"] = result.display
            self.instance.id_number_raw = result.raw
            self.instance.id_number_normalized = result.normalized
            self.instance.id_number_display = result.display
            self.instance.id_verification_status = Member.IDVerificationStatus.UNVERIFIED
            self.instance.id_verified_at = None

            if self.organisation is not None and result.normalized:
                duplicate = Member.objects.for_organisation(self.organisation).filter(
                    id_number_normalized__iexact=result.normalized,
                    id_type=id_type,
                    id_issuing_authority__iexact=(cleaned.get("id_issuing_authority") or ""),
                ).exclude(pk=self.instance.pk if self.instance.pk else None)
                if duplicate.exists():
                    self.add_error("id_number", "This identification number is already registered.")

        profile = profiles().get(id_type)
        if profile:
            front = cleaned.get("id_front")
            if id_type == Member.IDType.OTHER and (
                submitted or self._uploaded_front or self._uploaded_back
            ) and not self._id_unchanged_legacy:
                if not (cleaned.get("id_document_name") or "").strip():
                    self.add_error("id_document_name", "Enter the name of this identification document.")
                if not (cleaned.get("id_issuing_authority") or "").strip():
                    self.add_error(
                        "id_issuing_authority",
                        "Enter the issuing organization for this document.",
                    )
            changed = bool(self._id_result) or self._uploaded_front or self._uploaded_back
            if changed and profile.get("requires_front_image") and not (front or getattr(self.instance, "id_front", None)):
                self.add_error("id_front", "Upload a clear photo of the front of this document.")
            if changed and profile.get("requires_back_image") and not (cleaned.get("id_back") or getattr(self.instance, "id_back", None)):
                self.add_error("id_back", "Upload a clear photo of the back of this document.")

        cleaned["id_number_raw"] = self.instance.id_number_raw
        cleaned["id_number_normalized"] = self.instance.id_number_normalized
        cleaned["id_number_display"] = self.instance.id_number_display
        return cleaned

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

    def clean_id_front(self):
        image = self.cleaned_data.get("id_front")
        if image and isinstance(image, UploadedFile):
            return validate_id_image(image, "Front ID")
        return image

    def clean_id_back(self):
        image = self.cleaned_data.get("id_back")
        if image and isinstance(image, UploadedFile):
            return validate_id_image(image, "Back ID")
        return image


class MemberIDVerificationForm(forms.ModelForm):
    """Administrative review; format validation never marks a document verified."""

    class Meta:
        model = Member
        fields = ["id_verification_status"]  # noqa: RUF012
        labels = {"id_verification_status": "Verification decision"}  # noqa: RUF012
        help_texts = {  # noqa: RUF012
            "id_verification_status": "Only change this after reviewing the document and any official check.",
        }


class MemberDocumentForm(forms.ModelForm):
    class Meta:
        model = MemberDocument
        fields = ["document_type", "title", "file"]  # noqa: RUF012

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document_type"].required = False

    def clean_document_type(self):
        return self.cleaned_data.get("document_type") or MemberDocument.DocumentType.OTHER

    def clean_file(self):
        return validate_document_file(self.cleaned_data["file"])


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
