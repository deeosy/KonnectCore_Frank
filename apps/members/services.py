import csv
import io
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from openpyxl import load_workbook

from .models import Member, MemberHistory

REQUIRED_HEADERS = {"first_name", "last_name", "membership_number"}
ALLOWED_HEADERS = REQUIRED_HEADERS | {"phone", "id_reference", "location", "status"}


def member_snapshot(member):
    return {
        "first_name": member.first_name,
        "last_name": member.last_name,
        "phone": member.phone,
        "membership_number": member.membership_number,
        "id_reference": member.id_reference,
        "location": member.location,
        "status": member.status,
    }


def record_history(member, action, actor, changes=None):
    return MemberHistory.objects.create(
        organisation=member.organisation,
        member=member,
        action=action,
        changes=changes or {},
        actor=actor,
    )


def changed_fields(before, after):
    return {
        key: {"from": before.get(key, ""), "to": value}
        for key, value in after.items()
        if before.get(key, "") != value
    }


def _normalise_header(value):
    return str(value or "").strip().lower().replace(" ", "_").replace("/", "_")


def _csv_rows(uploaded):
    try:
        text = uploaded.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("CSV must use UTF-8 encoding.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError("Import file has no header row.")
    headers = [_normalise_header(value) for value in reader.fieldnames]
    for row in reader:
        yield {headers[index]: str(value or "").strip() for index, value in enumerate(row.values())}


def _xlsx_rows(uploaded):
    try:
        workbook = load_workbook(uploaded, read_only=True, data_only=True)
    except Exception as exc:
        raise ValidationError("The XLSX file could not be read.") from exc
    sheet = workbook.active
    iterator = sheet.iter_rows(values_only=True)
    try:
        headers = [_normalise_header(value) for value in next(iterator)]
    except StopIteration as exc:
        raise ValidationError("Import file is empty.") from exc
    for values in iterator:
        yield {headers[index]: str(value or "").strip() for index, value in enumerate(values)}


def _validated_rows(uploaded):
    suffix = Path(uploaded.name).suffix.lower()
    rows = list(_csv_rows(uploaded) if suffix == ".csv" else _xlsx_rows(uploaded))
    headers = set(rows[0]) if rows else set()
    if not REQUIRED_HEADERS.issubset(headers):
        missing = ", ".join(sorted(REQUIRED_HEADERS - headers))
        raise ValidationError(f"Missing required columns: {missing}.")
    cleaned = []
    errors = []
    valid_statuses = set(Member.Status.values)
    for line_number, row in enumerate(rows, start=2):
        if not any(row.values()):
            continue
        unknown = set(row) - ALLOWED_HEADERS
        if unknown:
            errors.append(f"Row {line_number}: unknown columns: {', '.join(sorted(unknown))}.")
            continue
        data = {key: row.get(key, "").strip() for key in ALLOWED_HEADERS}
        data["status"] = data["status"].lower() or Member.Status.ACTIVE
        if not all(data[key] for key in REQUIRED_HEADERS):
            errors.append(f"Row {line_number}: first_name, last_name and membership_number are required.")
        elif data["status"] not in valid_statuses:
            errors.append(f"Row {line_number}: invalid status '{data['status']}'.")
        else:
            cleaned.append((line_number, data))
    if errors:
        raise ValidationError(errors[:20])
    return cleaned


@transaction.atomic
def import_members(uploaded, organisation, actor):
    rows = _validated_rows(uploaded)
    seen = set()
    existing = {
        number.strip().lower()
        for number in Member.objects.for_organisation(organisation).values_list("membership_number", flat=True)
    }
    errors = []
    for line_number, data in rows:
        number = data["membership_number"].strip()
        data["membership_number"] = number
        key = number.lower()
        if key in seen or key in existing:
            errors.append(f"Row {line_number}: membership number '{number}' already exists.")
        seen.add(key)
    if errors:
        raise ValidationError(errors[:20])
    created = []
    for _, data in rows:
        member = Member(organisation=organisation, created_by=actor, updated_by=actor, **data)
        member.full_clean()
        member.save()
        record_history(member, MemberHistory.Action.IMPORTED, actor, {"member": member_snapshot(member)})
        created.append(member)
    return created
