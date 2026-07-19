# Technical Spec

## Current Stack

- Django
- Django templates
- SQLite for local development
- Django auth plus `ProjectMembership` rows for Project RBAC
- Database-backed render queue through `RenderJob`
- `renderworker` management command for asynchronous render processing
- BlueMap CLI or standalone BlueMap CLI jar
- Django protected asset route in development
- Nginx `X-Accel-Redirect` as the intended production asset-serving pattern

Future production deployments may add PostgreSQL, a web/worker container split, Nginx, and a stronger background queue. Celery, Redis, HTMX, Alpine.js, django-guardian, and Django Ninja are not current runtime requirements.

## Django Apps

Current Django app layout:

```text
config/
accounts/
projects/
bluemap_configs/
renders/
schedules/
viewer/
assets/
```

### accounts

Owns profile settings, user-management views, Project role memberships, and role helpers. The app currently uses Django's built-in `User` model and session authentication.

### projects

Owns discovered world folders, Projects, Atlases, and Render metadata.

Core models:

- `WorldFolder`
- `Project`
- `ProjectVisibleWorld`
- `Atlas`
- `Render`
- `Region`

Suggested relationships:

- `ProjectVisibleWorld` links a `Project` to a physical `WorldFolder` that the superadministrator has made available.
- `Atlas` belongs to one `Project` and references one visible `WorldFolder`.
- `Render` belongs to one `Atlas` and stores the BlueMap map id/config identity for one `maps.conf` entry.
- `Region` can be attached to a `Render` when the BlueMap config targets a specific zone of an Atlas.

Relationship diagram:

```text
auth.User
  |-- accounts.ProjectMembership -- projects.Project
                                      |-- projects.ProjectVisibleWorld -- projects.WorldFolder
                                      |-- projects.Atlas ---------------> projects.WorldFolder
                                            |-- projects.Render
                                                  |-- bluemap_configs.BlueMapRenderConfig -- bluemap_configs.BlueMapProfile
                                                  |-- renders.RenderJob -- renders.RenderLogChunk
                                                  |-- schedules.RenderSchedule
```

Lifecycle flags:

- `WorldFolder.is_active`: archived/unavailable for new Atlases and new render jobs. Existing Atlases/Renders are not automatically hidden.
- `Project.is_active`: archived Project. Hidden from the dashboard, still visible in superadmin Project management.
- `Atlas.is_active`: archived Atlas. Hidden from normal Project detail, visible to admins through archived Atlas view.
- `Render.is_enabled`: archived Render. Hidden from normal Atlas render list, visible to admins through archived Render view.

### bluemap_configs

Owns config generation, parsing, validation, templates, and filesystem writes.

Core models:

- `BlueMapProfile`
- `BlueMapRenderConfig`
- `ConfigRevision`
- `GeneratedConfigFile`

### renders

Owns render jobs and render execution state.

Core models:

- `RenderJob`
- `RenderLogChunk`
- `RenderArtifact`

### schedules

Owns automatic render rules. The model exists, but scheduling execution is not implemented yet.

Core models:

- `RenderSchedule`

### viewer

Owns authenticated viewer pages and Render launch URLs.

### assets

Owns authorization checks for BlueMap static assets. In production, Django should authorize and Nginx should serve files through `X-Accel-Redirect`.

## Data Flow: Render

```text
Project Administrator clicks Render
  -> Django validates permission
  -> Django validates source World Folder is active and still has level.dat
  -> RenderJob created with queued status
  -> renderworker claims queued job
  -> Worker revalidates source World Folder availability
  -> Worker writes BlueMap config
  -> Worker calls BlueMap CLI
  -> Worker captures stdout/stderr logs
  -> BlueMap writes rendered assets
  -> Job marked succeeded/failed
```

If the source World Folder is archived, a direct trigger creates a failed job with an explanatory log. If the folder is missing from disk, the app archives the World Folder and records the missing `level.dat` reason in the job log.

## Data Flow: Viewer Asset

```text
Browser requests /renders/<render_id>/assets/...
  -> Django checks session
  -> Django checks object permission for render_id
  -> Django validates file path stays inside rendered-map root
  -> Django returns X-Accel-Redirect header
  -> Nginx serves the actual file
```

## Environment Variables

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DATABASE_URL`
- `REDIS_URL`
- `SOURCE_WORLDS_DIR`
- `BLUEMAP_CONFIG_DIR`
- `BLUEMAP_WEBROOT_DIR`
- `BLUEMAP_CLI_PATH`
- `BLUEMAP_JAVA_PATH`
- `BLUEMAP_TMP_DIR`
- `BLUEMAP_RENDER_TIMEOUT_SECONDS`
- `BLUEMAP_RENDER_WORKER_CONCURRENCY`
- `BLUEMAP_RENDER_WORKER_POLL_SECONDS`
- `INTERNAL_ACCEL_ROOT`

## BlueMap CLI Strategy

The backend stores renderer profiles with command templates. The default profile command is:

```text
"{bluemap_cli}" -c "{config_dir}" -r
```

If `BLUEMAP_CLI_PATH` ends in `.jar`, the app automatically runs it through `BLUEMAP_JAVA_PATH` with `-jar` and a configured temporary directory.

## Configuration File Writes

Config writes should be deliberate and auditable:

1. Generate config content from database state.
2. Show preview in UI without writing files.
3. Write generated content to `<BLUEMAP_CONFIG_DIR>/maps/<bluemap_map_id>.conf` when a render job runs.
4. Store `ConfigRevision` with old and new content.
5. Track generated file path, content hash, and timestamp in `GeneratedConfigFile`.

## Frontend Approach

Use server-rendered Django pages:

- standard forms;
- Django form validation;
- a small JSON polling endpoint for active render jobs;
- ordinary full-page navigation for management flows.

Defer Vue unless interactive region editing or complex map planning becomes a central feature.

## Route Surface

See [Routes and Endpoints](ROUTES.md) for the current HTML, form `POST`, protected asset, and JSON polling routes. There is no separate REST API yet.
