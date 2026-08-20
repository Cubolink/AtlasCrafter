from django.db import migrations, models

import projects.models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0009_render_marker_publication_state"),
    ]

    operations = [
        migrations.AlterField(
            model_name="marker",
            name="marker_type",
            field=models.CharField(
                choices=[("poi", "Point of interest"), ("html", "Styled label")],
                default="poi",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="html_background_color",
            field=models.CharField(
                default="#2563eb",
                max_length=7,
                validators=[projects.models.hex_color_validator],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="html_size",
            field=models.CharField(
                choices=[("small", "Small"), ("medium", "Medium"), ("large", "Large")],
                default="medium",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="html_symbol",
            field=models.CharField(
                choices=[
                    ("none", "No symbol"),
                    ("pin", "Map pin"),
                    ("star", "Star"),
                    ("home", "Home"),
                    ("shop", "Shop"),
                    ("portal", "Portal"),
                    ("warning", "Warning"),
                ],
                default="pin",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="html_text_color",
            field=models.CharField(
                default="#ffffff",
                max_length=7,
                validators=[projects.models.hex_color_validator],
            ),
        ),
        migrations.AddField(
            model_name="marker",
            name="html_variant",
            field=models.CharField(
                choices=[
                    ("label", "Floating label"),
                    ("badge", "Rounded badge"),
                    ("sign", "Sign"),
                ],
                default="badge",
                max_length=20,
            ),
        ),
    ]
