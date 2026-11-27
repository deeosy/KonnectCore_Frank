"""Enforce identification uniqueness after legacy rows have been backfilled."""

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0008_backfill_identification_fields"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="member",
            constraint=models.UniqueConstraint(
                models.F("organisation"),
                models.F("id_type"),
                models.F("id_number_normalized"),
                models.F("id_issuing_authority"),
                condition=~Q(id_number_normalized=""),
                name="unique_org_identification_number",
                violation_error_message="This identification number is already registered.",
            ),
        ),
    ]
