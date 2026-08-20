from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import migrations, models

import projects.models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0010_marker_html_style_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="marker",
            name="marker_type",
            field=models.CharField(
                choices=[
                    ("poi", "Point of interest"),
                    ("html", "Styled label"),
                    ("line", "Line"),
                    ("shape", "Area"),
                    ("extrude", "Volume"),
                ],
                default="poi",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="depth_test",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="marker",
            name="fill_color",
            field=models.CharField(
                default="#ef4444",
                max_length=7,
                validators=[projects.models.hex_color_validator],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="fill_opacity",
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("0.250"),
                max_digits=4,
                validators=[MinValueValidator(0), MaxValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="geometry",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="marker",
            name="line_color",
            field=models.CharField(
                default="#ef4444",
                max_length=7,
                validators=[projects.models.hex_color_validator],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="line_opacity",
            field=models.DecimalField(
                decimal_places=3,
                default=1,
                max_digits=4,
                validators=[MinValueValidator(0), MaxValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="line_width",
            field=models.PositiveSmallIntegerField(
                default=3,
                validators=[MinValueValidator(1), MaxValueValidator(20)],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="link",
            field=models.CharField(
                blank=True,
                max_length=500,
                validators=[URLValidator(schemes=["http", "https"])],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="new_tab",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="marker",
            name="shape_max_y",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="shape_min_y",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=14,
                null=True,
            ),
        ),
    ]
