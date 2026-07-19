# Routes and Endpoints

The current application is primarily server-rendered Django HTML. Most mutating routes are form `POST` endpoints protected by login, CSRF, and role checks. There is one small JSON endpoint for render status polling.

## Public/Auth Routes

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/login/` | `login` | Login form. |
| `POST` | `/logout/` | `logout` | Logout. |
| `GET`, `POST` | `/profile/` | `profile_settings` | Change username, optional email, and password. |

## Project Dashboard

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | `dashboard` | Main Projects page. Shows active Projects available to the user. |
| `GET` | `/projects/<slug>/` | `project_detail` | Project detail with active Atlases and active Renders. |

## Panel Settings

Superadministrator-only unless noted.

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/settings/` | `panel_settings` | Panel settings landing page. |
| `GET` | `/settings/users/create/` | `panel_user_create` | New user form. |
| `POST` | `/settings/users/create/` | `panel_user_create` | Create user with username/password. |
| `GET` | `/settings/users/<user_id>/edit/` | `panel_user_edit` | Edit user email and project access. |
| `POST` | `/settings/users/<user_id>/edit/` | `panel_user_edit` | Save editable user fields. |
| `POST` | `/settings/users/<user_id>/project-access/add/` | `panel_user_project_access_add` | Add Project role membership. |
| `POST` | `/settings/users/<user_id>/project-access/<membership_id>/remove/` | `panel_user_project_access_remove` | Remove Project role membership. |

## Project Management

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/settings/projects/` | `manage_projects` | List active and archived Projects for superadmins. |
| `GET` | `/settings/projects/create/` | `create_project` | Project creation form. |
| `POST` | `/settings/projects/create/` | `create_project` | Create Project and assign visible World Folders. |
| `GET` | `/settings/projects/<project_id>/edit/` | `edit_project` | Project edit form. |
| `POST` | `/settings/projects/<project_id>/edit/` | `edit_project` | Save Project fields, active state, and visible World Folders. |
| `POST` | `/settings/projects/<project_id>/archive/` | `archive_project` | Archive Project if no queued/running jobs exist. |

## World Folder Management

Superadministrator-only. World Folder archive blocks new Atlas selection and new render jobs, but does not hide existing Atlases or Renders by itself.

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/settings/world-folders/` | `world_folders` | Show detected servers, resource sources, the source tree, and known World Folders. |
| `POST` | `/settings/world-folders/scan/` | `scan_world_folders` | Scan `SOURCE_WORLDS_DIR`, detect servers/resources, create/update/restore worlds, and archive missing worlds. |
| `GET` | `/settings/world-folders/create/` | `create_world_folder` | Manual World Folder form. |
| `POST` | `/settings/world-folders/create/` | `create_world_folder` | Add manual World Folder. Active worlds require `level.dat`. |
| `GET` | `/settings/resource-sources/create/` | `create_resource_source` | Manual Minecraft resource-source form. |
| `POST` | `/settings/resource-sources/create/` | `create_resource_source` | Register a resource source from an allowed read-only root. |
| `GET` | `/settings/resource-sources/<source_id>/edit/` | `edit_resource_source` | Edit a detected or manual resource source. |
| `POST` | `/settings/resource-sources/<source_id>/edit/` | `edit_resource_source` | Save resource paths, version, loader, and default loading behavior. |
| `GET` | `/settings/world-folders/<world_id>/edit/` | `edit_world_folder` | Edit World Folder metadata. |
| `POST` | `/settings/world-folders/<world_id>/edit/` | `edit_world_folder` | Save World Folder metadata and active state. |
| `POST` | `/settings/world-folders/<world_id>/archive/` | `archive_world_folder` | Archive World Folder. |
| `POST` | `/settings/world-folders/<world_id>/restore/` | `restore_world_folder` | Restore World Folder if `level.dat` exists. |

## Atlas and Render Management

Project Administrators for the Project and superadmins can use these routes. Project Users cannot.

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/projects/<slug>/atlases/create/` | `create_atlas` | Create Atlas from an active visible World Folder. |
| `GET` | `/projects/<slug>/atlases/archived/` | `archived_atlases` | Admin-only list of archived Atlases in a Project. |
| `GET` | `/atlases/<atlas_id>/edit/` | `edit_atlas` | Edit active Atlas metadata. |
| `POST` | `/atlases/<atlas_id>/edit/` | `edit_atlas` | Save active Atlas metadata. |
| `POST` | `/atlases/<atlas_id>/archive/` | `archive_atlas` | Archive Atlas if no queued/running jobs exist. |
| `POST` | `/atlases/<atlas_id>/restore/` | `restore_atlas` | Restore archived Atlas. |
| `POST` | `/atlases/<atlas_id>/renders/create/` | `create_render` | Create Render under an active Atlas. |
| `GET` | `/atlases/<atlas_id>/renders/archived/` | `archived_renders` | Admin-only list of archived Renders for an active Atlas. |
| `GET` | `/renders/<render_id>/edit/` | `edit_render` | Edit active Render config fields. |
| `POST` | `/renders/<render_id>/edit/` | `edit_render` | Save active Render config fields. |
| `POST` | `/renders/<render_id>/archive/` | `archive_render` | Archive Render if no queued/running job exists. |
| `POST` | `/renders/<render_id>/restore/` | `restore_render` | Restore archived Render. |
| `POST` | `/projects/<slug>/users/add/` | `add_project_user` | Project Admin or superadmin adds an existing user as Project User. |
| `POST` | `/projects/<slug>/memberships/<membership_id>/remove/` | `remove_project_membership` | Remove Project User membership. |

## Render Viewer and Jobs

| Method | Path | Name | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/renders/<render_id>/` | `render_viewer` | Render detail page and scoped BlueMap viewer frame. |
| `GET` | `/renders/<render_id>/config-preview/` | `render_config_preview` | Preview generated BlueMap map config. |
| `POST` | `/renders/<render_id>/trigger/` | `trigger_render` | Queue render job, or create failed job if source World Folder is archived/missing. |
| `POST` | `/renders/<render_id>/rebuild/` | `rebuild_render` | Project Admin-only purge and full rebuild using current config and Minecraft resources. |
| `GET` | `/renders/<render_id>/status/` | `render_status` | JSON status endpoint used by polling while a job is active. |
| `GET` | `/jobs/<job_id>/` | `render_job_detail` | Render job detail and logs. |
| `POST` | `/jobs/<job_id>/cancel/` | `cancel_render_job` | Cancel queued job when permitted. |
| `GET` | `/renders/<render_id>/assets/<path>` | `protected_render_asset` | Authenticated BlueMap asset route. Scopes viewer settings to the requested Render. |

## JSON: Render Status

`GET /renders/<render_id>/status/` returns:

```json
{
  "has_active_job": true,
  "job": {
    "id": 1,
    "operation": "update",
    "operation_label": "Update",
    "status": "running",
    "status_label": "Running",
    "updated_at": "2026-07-18T12:00:00+00:00",
    "finished_at": null
  }
}
```

When no jobs exist, `job` is `null`. When no job is queued or running, `has_active_job` is `false` and `job` is the latest job if one exists.
