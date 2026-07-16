from django.db import migrations


NEW_DEFAULT = '"{bluemap_cli}" -c "{config_dir}" -r'
LEGACY_DEFAULTS = [
    '{bluemap_cli} render --map "{map_id}"',
    '{bluemap_cli} render --config "{config_dir}" --map "{map_id}"',
    '{bluemap_cli} -c "{config_dir}" -r',
]


def update_legacy_render_command_templates(apps, schema_editor):
    BlueMapProfile = apps.get_model("bluemap_configs", "BlueMapProfile")
    BlueMapProfile.objects.filter(command_template__in=LEGACY_DEFAULTS).update(
        command_template=NEW_DEFAULT
    )


class Migration(migrations.Migration):
    dependencies = [
        ("bluemap_configs", "0006_alter_bluemapprofile_command_template"),
    ]

    operations = [
        migrations.RunPython(
            update_legacy_render_command_templates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
