"""One-time submission keys that stop duplicate records from repeated form posts (UAT I-2).

How it works:
- Each unbound *create* form gets a hidden random ``submission_key``.
- On save, the key and a fingerprint of the submitted data are stored on the record.
- A database unique constraint on (organisation, submission_key) makes the first insert win,
  even when two identical requests arrive at the same time.
- A repeat with the same key and the same data returns the original record (not a new one).
- A repeat with the same key but different data, or from a different user, is rejected.
- A freshly opened form has a new key, so separate records with identical values are allowed.

Models using this need ``submission_key`` (nullable UUID) and ``submission_fingerprint``
(CharField, 64) fields plus a conditional unique constraint on (organisation, submission_key).
"""
import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from django import forms
from django.db import IntegrityError, models, transaction

FIELD_NAME = "submission_key"
CONFLICT_MESSAGE = (
    "This form was already submitted with different details. "
    "Reload the page to start a new record."
)


class SubmissionConflict(Exception):
    """The submission key was already used for different data or by another user."""


def add_submission_key(form):
    """Add the hidden one-time key to a create form. Edit forms are left unchanged."""
    if not form.instance._state.adding:
        return
    form.fields[FIELD_NAME] = forms.UUIDField(required=False, widget=forms.HiddenInput)
    if not form.is_bound:
        form.initial[FIELD_NAME] = uuid.uuid4()


def _normalise(value):
    if isinstance(value, models.Model):
        return str(value.pk)
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "read") and hasattr(value, "name"):
        return {"file": getattr(value, "name", ""), "size": getattr(value, "size", None)}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    return value


def fingerprint(form):
    data = {
        name: _normalise(value)
        for name, value in sorted(form.cleaned_data.items())
        if name != FIELD_NAME
    }
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _matching_existing(model, organisation, key, digest, actor_field, actor):
    existing = model.objects.filter(organisation=organisation, submission_key=key).first()
    if existing is None:
        return None
    same_actor = actor_field is None or getattr(existing, f"{actor_field}_id") == getattr(actor, "pk", None)
    if not same_actor or existing.submission_fingerprint != digest:
        raise SubmissionConflict(CONFLICT_MESSAGE)
    return existing


def save_once(form, *, organisation, actor, actor_field="recorded_by"):
    """Save a create form at most once per submission key.

    Returns ``(record, created)``. Raises ``SubmissionConflict`` when the key was reused for
    different data or by another user. Forms without a key (for example API-style posts that
    omit it) are saved normally.
    """
    key = form.cleaned_data.get(FIELD_NAME) if FIELD_NAME in form.fields else None
    if not key:
        return form.save(), True
    model = form._meta.model
    digest = fingerprint(form)
    existing = _matching_existing(model, organisation, key, digest, actor_field, actor)
    if existing is not None:
        return existing, False
    record = form.save(commit=False)
    record.submission_key = key
    record.submission_fingerprint = digest
    try:
        with transaction.atomic():
            record.save()
    except IntegrityError:
        # A simultaneous request with the same key won the insert; return its record.
        existing = _matching_existing(model, organisation, key, digest, actor_field, actor)
        if existing is None:
            raise
        return existing, False
    return record, True
