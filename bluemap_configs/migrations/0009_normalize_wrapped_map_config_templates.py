from django.db import migrations


NEW_DEFAULT = 'world: "{world_path}"\ndimension: "{dimension}"\nname: "{display_name}"\nsorting: {sorting}\nstart-pos: {{ x: 0, z: 0 }}\nsky-color: "#7dabff"\nvoid-color: "#000000"\nsky-light: 1\nambient-light: 0\nremove-caves-below-y: 55\ncave-detection-ocean-floor: -5\ncave-detection-uses-block-light: false\nmin-inhabited-time: 0\nrender-mask: []\nrender-edges: true\nedge-light-strength: 8\nenable-perspective-view: true\nenable-flat-view: true\nenable-free-flight-view: true\nenable-hires: true\nstorage: "{storage}"\nignore-missing-light-data: false\nmarker-sets: {{}}\n'


def normalize_wrapped_templates(apps, schema_editor):
    BlueMapProfile = apps.get_model("bluemap_configs", "BlueMapProfile")
    for profile in BlueMapProfile.objects.all():
        if profile.config_template.lstrip().startswith("maps:"):
            profile.config_template = NEW_DEFAULT
            profile.save(update_fields=["config_template"])


class Migration(migrations.Migration):
    dependencies = [
        ("bluemap_configs", "0008_alter_bluemapprofile_config_template"),
    ]

    operations = [
        migrations.RunPython(
            normalize_wrapped_templates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
