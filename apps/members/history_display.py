"""Plain-English display of the details stored in ``MemberHistory.changes``.

History records keep structured JSON, but the member profile shows them to
non-technical staff. This module turns the stored keys into short labelled lines
(for example, "Location: Changed from Kumasi to Accra") instead of exposing the
raw dictionary representation. Nothing here changes what is stored in the
database; it only controls how the existing audit data is presented.
"""

# Internal keys, or keys already covered by the action label, are not shown.
# Sensitive ID values are hidden even if an older record happens to contain them.
HIDDEN_KEYS = {"tag", "document_id", "id_number", "id_front", "id_back"}

LABELS = {
    "first_name": "First name",
    "last_name": "Last name",
    "phone": "Phone",
    "membership_number": "Membership number",
    "location": "Location",
    "status": "Status",
    "previous_status": "Previous status",
    "new_status": "New status",
    "reason": "Reason",
    "id_type": "ID type",
    "document_type": "Document type",
    "title": "Title",
}

# Choice values are stored as codes, but staff should see their proper names.
CHOICE_LABELS = {
    "active": "Active",
    "inactive": "Inactive",
    "suspended": "Suspended",
    "deceased": "Deceased",
    "archived": "Archived",
    "voter_id": "Voter ID",
    "nhis": "NHIS",
    "ghana_card": "Ghana Card",
    "other": "Other",
}

NOT_RECORDED = "Not recorded"


def _missing(value):
    return value is None or value == ""


def _label(key):
    return LABELS.get(key, str(key).replace("_", " ").capitalize())


def _display(value):
    """Show one stored value in words rather than as a Python/JSON literal."""
    if _missing(value):
        return NOT_RECORDED
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        parts = [f"{_label(key)}: {_display(item)}" for key, item in value.items() if key not in HIDDEN_KEYS]
        return ", ".join(parts) or NOT_RECORDED
    if isinstance(value, (list, tuple)):
        return ", ".join(_display(item) for item in value) or NOT_RECORDED
    text = str(value)
    return CHOICE_LABELS.get(text.lower(), text)


def _from_to(value):
    """Describe a stored {"from": ..., "to": ...} change as a sentence."""
    before = value.get("from")
    after = value.get("to")
    if _missing(before):
        return f"Set to {_display(after)}"
    if _missing(after):
        return f"Cleared (was {_display(before)})"
    return f"Changed from {_display(before)} to {_display(after)}"


def _member_snapshot(snapshot):
    """Show the details recorded when a member was created or imported."""
    names = [str(snapshot[key]).strip() for key in ("first_name", "last_name") if not _missing(snapshot.get(key))]
    lines = []
    if names:
        lines.append({"label": "Name", "value": " ".join(names)})
    for key in ("phone", "membership_number", "location", "status", "id_type"):
        value = snapshot.get(key)
        if not _missing(value):
            lines.append({"label": LABELS[key], "value": _display(value)})
    return lines


def _id_verification(changes):
    """Show ID verification flags without ever showing the ID number or file paths."""
    lines = []
    document_type = changes.get("document_type")
    if not _missing(document_type):
        lines.append({"label": LABELS["document_type"], "value": _display(document_type)})
    if "id_number_updated" in changes:
        lines.append({"label": "ID number", "value": "Updated" if changes["id_number_updated"] else "Not changed"})
    for side in ("front", "back"):
        uploaded = changes.get(f"{side}_image_uploaded")
        changed = changes.get(f"{side}_image_changed")
        if uploaded is None and changed is None:
            continue
        parts = []
        if uploaded is not None:
            parts.append("uploaded" if uploaded else "not uploaded")
        if changed is not None:
            parts.append("changed" if changed else "not changed")
        lines.append({"label": f"{side.title()} ID image", "value": ", ".join(parts)})
    return lines


def format_changes(changes):
    """Return [{"label": ..., "value": ...}, ...] for a history record's changes."""
    if not isinstance(changes, dict) or not changes:
        return []

    snapshot = changes.get("member")
    if isinstance(snapshot, dict):
        return _member_snapshot(snapshot)

    id_verification_flags = ("id_number_updated", "front_image_uploaded", "front_image_changed", "back_image_uploaded", "back_image_changed")
    if "tag" in changes and any(key in changes for key in id_verification_flags):
        return _id_verification(changes)

    lines = []
    for key, value in changes.items():
        if key in HIDDEN_KEYS:
            continue
        if isinstance(value, dict) and "from" in value and "to" in value:
            lines.append({"label": _label(key), "value": _from_to(value)})
        else:
            lines.append({"label": _label(key), "value": _display(value)})
    return lines
