"""Backfill identification fields without changing any existing ID number.

Historical records keep their original display value. ``id_number_raw`` stays
blank so an unchanged legacy value is not forced through the new strict rules;
editing the number explicitly revalidates it.
"""

import re

from django.db import migrations


def _legacy_normalized(id_type, value):
    text = (value or "").strip()
    if not text:
        return ""
    if id_type == "ghana_card":
        return re.sub(r"[^0-9]", "", text)
    if id_type != "other":
        return re.sub(r"\s+", "", text).upper()
    return text


def backfill(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    rows = Member.objects.exclude(id_number="").only(
        "id", "organisation_id", "id_type", "id_number", "id_issuing_authority", "created_at"
    )
    updates = []
    seen = set()
    for row in rows.order_by("created_at", "pk"):
        normalized = _legacy_normalized(row.id_type, row.id_number)
        key = (row.organisation_id, row.id_type, normalized, (row.id_issuing_authority or "").lower())
        # Keep the oldest record canonical; blank later duplicates so the new
        # constraint can be added without rejecting historical data.
        if normalized and key in seen:
            normalized = ""
        elif normalized:
            seen.add(key)
        row.id_number_display = row.id_number
        row.id_number_normalized = normalized
        updates.append(row)
    if updates:
        Member.objects.bulk_update(updates, ["id_number_display", "id_number_normalized"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012
        ("members", "0007_member_id_document_name_member_id_issuing_authority_and_more"),
    ]

    operations = [  # noqa: RUF012
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
