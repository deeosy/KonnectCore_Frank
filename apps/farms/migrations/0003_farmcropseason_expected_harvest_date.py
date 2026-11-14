# Generated for Phase 3 harvest coordination.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0002_farmownershiptransfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='farmcropseason',
            name='expected_harvest_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='farmcropseason',
            index=models.Index(fields=['organisation', 'expected_harvest_date'], name='farms_season_harvest_idx'),
        ),
    ]
