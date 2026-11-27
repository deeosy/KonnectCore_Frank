"""Reusable Ghana identification-number rules for KonnectCore.

The rules are deliberately data-driven so an organisation can adjust a profile
when an official issuer publishes a new specification. They are used by the
member form (client hints and server validation), the model and bulk imports.
Nothing here performs official identity verification: a correctly formatted
number only passes *format* validation.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError  # pyright: ignore[reportMissingModuleSource]

# ``sanitize`` values:
#   digits      - only ASCII digits are accepted (nothing is stripped silently)
#   upper_alnum - spaces are removed and letters are upper-cased
#   plain       - whitespace at the ends is removed, the value is otherwise kept
DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "ghana_card": {
        "label": "Ghana Card",
        "placeholder": "Enter your 10-digit Ghana Card PIN.",
        "help": "Enter the 10 digits without GHA or hyphens.",
        "input_mode": "numeric",
        "autocomplete": "off",
        "sanitize": "digits",
        "pattern": r"[0-9]{10}",
        "min_length": 10,
        "max_length": 10,
        "prefix": "GHA",
        "display": "ghana_card",
        "format_hint": "GHA-123456789-0",
        "error": "Your Ghana Card number must contain exactly 10 digits.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": False,
    },
    "voter_id": {
        "label": "Voter ID",
        "placeholder": "Enter your 10-digit Voter ID number.",
        "help": "Enter the number printed on your Voter ID.",
        "input_mode": "numeric",
        "autocomplete": "off",
        "sanitize": "digits",
        "pattern": r"[0-9]{10}",
        "min_length": 10,
        "max_length": 10,
        "prefix": "",
        "display": "plain",
        "format_hint": "4449012952",
        "error": "Enter a valid 10-digit Voter ID number.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": False,
    },
    "voter_id_legacy": {
        # Enabled only when IDENTIFICATION_LEGACY_VOTER_ENABLED is true.
        "label": "Voter ID (legacy)",
        "placeholder": "Enter the number on your older Voter ID.",
        "help": "For older cards only. Enter the number exactly as printed.",
        "input_mode": "text",
        "autocomplete": "off",
        "sanitize": "upper_alnum",
        "pattern": r"[A-Z0-9]{6,15}",
        "min_length": 6,
        "max_length": 15,
        "prefix": "",
        "display": "plain",
        "format_hint": "OLDVOTER123",
        "error": "Enter a valid legacy Voter ID number.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": True,
    },
    "nhis": {
        "label": "NHIS",
        "placeholder": "Enter your 8-digit NHIS membership number.",
        "help": "Enter the 8 digits printed on your NHIS card.",
        "input_mode": "numeric",
        "autocomplete": "off",
        "sanitize": "digits",
        "pattern": r"[0-9]{8}",
        "min_length": 8,
        "max_length": 8,
        "prefix": "",
        "display": "plain",
        "format_hint": "12345678",
        "error": "Your NHIS membership number must contain exactly 8 digits.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": False,
    },
    "passport": {
        # Ghana's passport number is issued by the Ministry of Foreign Affairs.
        # No unverified universal length is assumed; deployments can tighten the
        # regex once an authoritative current specification is available.
        "label": "Passport",
        "placeholder": "Enter your passport number.",
        "help": "Enter the number printed on your passport biodata page.",
        "input_mode": "text",
        "autocomplete": "off",
        "sanitize": "upper_alnum",
        "pattern": r"[A-Z0-9]{1,20}",
        "min_length": 1,
        "max_length": 20,
        "prefix": "",
        "display": "plain",
        "format_hint": "G1234567",
        "error": "Enter a valid passport number.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": False,
    },
    "drivers_licence": {
        # DVLA Ghana has not published a fixed public numbering specification.
        # Keep the default permissive but bounded, and configure an exact
        # pattern only after a verified DVLA specification is supplied.
        "label": "Driver's Licence",
        "placeholder": "Enter your licence number.",
        "help": "Enter the number printed on your DVLA licence.",
        "input_mode": "text",
        "autocomplete": "off",
        "sanitize": "upper_alnum",
        "pattern": r"[A-Z0-9]{1,20}",
        "min_length": 1,
        "max_length": 20,
        "prefix": "",
        "display": "plain",
        "format_hint": "DL1234567",
        "error": "Enter a valid driving licence number.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": False,
    },
    "other": {
        "label": "Other",
        "placeholder": "Enter your identification number.",
        "help": "Enter the number printed on your identification document.",
        "input_mode": "text",
        "autocomplete": "off",
        "sanitize": "plain",
        "pattern": "",
        "min_length": 1,
        "max_length": 100,
        "prefix": "",
        "display": "plain",
        "format_hint": "Document number",
        "error": "Enter a valid identification number.",
        "requires_front_image": True,
        "requires_back_image": False,
        "legacy": False,
    },
}

PUBLIC_PROFILE_KEYS = (
    "label", "placeholder", "help", "input_mode", "autocomplete", "sanitize",
    "pattern", "min_length", "max_length", "prefix", "display", "format_hint",
    "error", "requires_front_image", "requires_back_image", "legacy",
)


@dataclass(frozen=True)
class IdentificationResult:
    """Normalised values derived from a user-supplied identification number."""

    raw: str
    normalized: str
    display: str
    profile: dict[str, Any]


def legacy_voter_enabled() -> bool:
    return bool(getattr(settings, "IDENTIFICATION_LEGACY_VOTER_ENABLED", False))


def profiles() -> dict[str, dict[str, Any]]:
    """Return default profiles merged with deployment-specific overrides."""
    merged = deepcopy(DEFAULT_PROFILES)
    configured = getattr(settings, "IDENTIFICATION_PROFILES", {}) or {}
    for name, overrides in configured.items():
        if not isinstance(overrides, dict):
            continue
        merged.setdefault(name, deepcopy(DEFAULT_PROFILES.get("other", {})))
        merged[name].update(deepcopy(overrides))
    return merged


def profile_for(id_type: str) -> dict[str, Any]:
    if not id_type:
        raise ValidationError("Choose the type of identification being verified.")
    configured = profiles()
    profile = configured.get(id_type)
    if profile is None:
        raise ValidationError("Choose a supported type of identification.")
    if id_type == "voter_id_legacy" and not legacy_voter_enabled():
        raise ValidationError("Legacy Voter ID support is not enabled for this organisation.")
    return profile


def available_id_types() -> list[tuple[str, str]]:
    """Choices for the public form; the legacy option is opt-in."""
    choices = [
        ("ghana_card", "Ghana Card"),
        ("voter_id", "Voter ID"),
        ("nhis", "NHIS"),
        ("passport", "Passport"),
        ("drivers_licence", "Driver's Licence"),
        ("other", "Other"),
    ]
    if legacy_voter_enabled():
        choices.insert(2, ("voter_id_legacy", "Voter ID (legacy)"))
    return choices


def public_profile_config() -> list[dict[str, Any]]:
    """Small, non-sensitive profile subset used by the browser."""
    config = []
    for id_type, profile in profiles().items():
        if id_type == "voter_id_legacy" and not legacy_voter_enabled():
            continue
        config.append({"id_type": id_type, **{key: profile.get(key) for key in PUBLIC_PROFILE_KEYS}})
    return config


def _sanitize(value: str, mode: str) -> str:
    if mode == "digits":
        return value
    if mode == "upper_alnum":
        return re.sub(r"\s+", "", value).upper()
    return value.strip()


def normalize(id_type: str, value: str) -> IdentificationResult:
    """Validate and normalise one identification number.

    The returned ``raw`` value is what the operator entered, ``normalized`` is
    the canonical duplicate-check value and ``display`` is the official-looking
    presentation value. No missing digits are generated.
    """
    profile = profile_for(id_type)
    raw = str(value or "").strip()
    if not raw:
        return IdentificationResult("", "", "", profile)

    mode = profile.get("sanitize", "plain")
    candidate = raw
    if mode == "digits" and profile.get("display") == "ghana_card":
        # The browser submits the value shown in the input. Accept only the
        # exact display generated by the formatter, never a hand-typed prefix.
        if re.fullmatch(r"GHA-[0-9]{9}-[0-9]", raw):
            candidate = raw[4:13] + raw[14]
        elif "-" in raw or raw.upper().startswith("GHA"):
            raise ValidationError("Enter the 10 digits exactly as shown on the Ghana Card.")
    if mode == "digits" and not re.fullmatch(r"[0-9]+", candidate):
        raise ValidationError(profile.get("error") or "Enter a valid identification number.")

    normalized = _sanitize(candidate, mode)
    minimum = int(profile.get("min_length") or 0)
    maximum = int(profile.get("max_length") or 100)
    if len(normalized) < minimum or len(normalized) > maximum:
        raise ValidationError(profile.get("error") or "Enter a valid identification number.")

    pattern = profile.get("pattern")
    if pattern and not re.fullmatch(str(pattern), normalized):
        raise ValidationError(profile.get("error") or "Enter a valid identification number.")

    if profile.get("display") == "ghana_card":
        display = f"{profile.get('prefix', 'GHA')}-{normalized[:9]}-{normalized[9:]}"
    else:
        display = normalized
    return IdentificationResult(raw=candidate, normalized=normalized, display=display, profile=profile)


def validate(id_type: str, value: str) -> IdentificationResult:
    """Alias kept explicit for callers that only want validation."""
    return normalize(id_type, value)


def mask_number(value: str, keep: int = 4) -> str:
    """Mask an identification number for ordinary listings."""
    text = str(value or "")
    digits = re.sub(r"[^0-9A-Za-z]", "", text)
    if len(digits) <= keep:
        return "•" * len(digits)
    return "•" * (len(digits) - keep) + digits[-keep:]
