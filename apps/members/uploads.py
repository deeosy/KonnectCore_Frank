"""Validation for sensitive identification document images."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_IMAGE_FORMATS = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
    "WEBP": {".webp"},
}
ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/webp",
}


def max_id_image_bytes() -> int:
    return int(getattr(settings, "MAX_ID_IMAGE_BYTES", 5 * 1024 * 1024))


def validate_id_image(uploaded, label: str):
    """Check size, declared type, extension and actual image content.

    Pillow verifies the file bytes, so an executable renamed to ``.png`` is
    rejected. The uploaded stream is rewound for Django's ImageField after
    verification.
    """
    if uploaded is None:
        return uploaded
    size = getattr(uploaded, "size", 0) or 0
    if size > max_id_image_bytes():
        raise ValidationError(f"{label} image must be 5 MB or smaller.")

    suffix = Path(uploaded.name or "").suffix.lower()
    allowed_suffixes = {item for suffixes in ALLOWED_IMAGE_FORMATS.values() for item in suffixes}
    if suffix not in allowed_suffixes:
        raise ValidationError(f"Upload a JPEG, PNG or WebP image for the {label.lower()} image.")

    content_type = (getattr(uploaded, "content_type", "") or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(f"Upload a JPEG, PNG or WebP image for the {label.lower()} image.")

    try:
        from PIL import Image

        uploaded.seek(0)
        with Image.open(uploaded) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        raise ValidationError(f"The {label.lower()} image is not a valid image file.") from exc

    if image_format not in ALLOWED_IMAGE_FORMATS or suffix not in ALLOWED_IMAGE_FORMATS[image_format]:
        raise ValidationError(f"Upload a JPEG, PNG or WebP image for the {label.lower()} image.")
    uploaded.seek(0)
    return uploaded


def validate_document_file(uploaded):
    """Validate attached documents by extension and real file signature."""
    max_bytes = 10 * 1024 * 1024
    if (getattr(uploaded, "size", 0) or 0) > max_bytes:
        raise ValidationError("Document must be 10 MB or smaller.")

    suffix = Path(uploaded.name or "").suffix.lower()
    allowed_suffixes = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
    if suffix not in allowed_suffixes:
        raise ValidationError("Upload a PDF or image file.")

    uploaded.seek(0)
    head = uploaded.read(5)
    uploaded.seek(0)
    if suffix == ".pdf":
        if not head.startswith(b"%PDF-"):
            raise ValidationError("The PDF file is not a valid PDF document.")
        return uploaded
    return validate_id_image(uploaded, "Document")
