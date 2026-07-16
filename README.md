# BlueMap Web UI Panel

A Django-based management panel for BlueMap. The application provides a secure web UI for managing Projects, Atlases, and BlueMap Renders, writing BlueMap `.conf` files through forms, triggering renders through the backend, tracking render history, and serving BlueMap viewer assets behind RBAC.

BlueMap remains the renderer and WebGL map viewer technology. This project wraps BlueMap with authentication, authorization, configuration management, render orchestration, and protected delivery.

## Core Idea

BlueMap already does the hard rendering and provides a polished 3D web viewer. This panel should not replace BlueMap's renderer or rewrite its WebGL frontend.

Instead, the panel owns:

- users, roles, permissions, and object-level access;
- discovery of Minecraft world folders from configured source roots;
- UI-driven creation and editing of BlueMap config files;
- Project, Atlas, and Render organization and metadata;
- render execution through BlueMap CLI commands;
- render queue, logs, progress, and history;
- schedule management;
- protected viewer entry points;
- protected static asset delivery for BlueMap output.

## Recommended Stack

- **Django** as the backend framework.
- **PostgreSQL** for production data.
- **Django templates + HTMX + Alpine.js** for the first UI.
- **Django Admin** for early internal administration.
- **django-guardian** for object-level RBAC.
- **Django Ninja** for typed JSON APIs where needed.
- **Celery + Redis** for render jobs.
- **Celery Beat** or APScheduler for scheduled renders.
- **Nginx X-Accel-Redirect** for efficient protected BlueMap asset serving.
- **BlueMap CLI** for rendering.

Vue is not required for the MVP. BlueMap already provides the heavy 3D frontend. Add Vue later only if the panel grows into a rich interactive workspace with drag/drop region editing, planning overlays, complex dashboards, or advanced client-side state.

## Domain Model

BlueMap allows a single Minecraft world to be rendered multiple ways. BlueMap calls each entry in `maps.conf` a map, and those entries can point to the same world with different regions, dimensions, resolutions, zoom levels, lighting, masks, storage targets, or other configuration.

To avoid confusing BlueMap's map config entries with physical Minecraft worlds, this application uses the following terms:

| Layer | Name | Description |
| :--- | :--- | :--- |
| **Top** | **Project** | Top-level organizational bucket, such as "My Server", "Archives", or "Testing". A Project can point to a folder containing Minecraft worlds, such as a Minecraft server directory, or be a curated collection of unrelated worlds for administrative convenience. |
| **Middle** | **Atlas** | The app's representation of one physical Minecraft world folder inside a Project. An Atlas can have one or more Renders. The name follows the mathematical idea of an atlas as a collection of charts describing a space. |
| **Bottom** | **Render** | A specific BlueMap render configuration for an Atlas. This corresponds to one entry in BlueMap's `maps.conf`. |
| **Physical disk** | **Minecraft World** or **World Folder** | The actual save folder on disk. It is only referenced when creating or editing an Atlas. |

A superadministrator defines which physical Minecraft world folders are visible to a Project. Visibility does not automatically create Atlases. A Project Administrator must explicitly create an Atlas inside the Project by selecting from the visible world folders, then define one or more Renders for that Atlas.

Example sidebar:

```text
Project: "My Survival Server"
   Atlas: Overworld
      Render: HD 4K
      Render: Spawn Zoom
   Atlas: The Nether
      Render: Standard

Project: "Archived Builds"
   Atlas: Creative_Flat
      Render: Standard
   Atlas: Old_Survival_2022
      Render: Standard
```

## Architecture

```text
Browser
  |
  v
Nginx
  |
  |-- / ------------------------> Django panel
  |-- /renders/<render>/... ----> Django auth check -> X-Accel-Redirect
  |
  v
Django
  |-- Auth / RBAC
  |-- Project, Atlas, and Render config UI
  |-- BlueMap .conf generation
  |-- Render queue API
  |-- Viewer wrapper pages
  |
  v
Celery worker
  |
  v
BlueMap CLI
  |
  v
Rendered BlueMap webroot / map data
```

## BlueMap Exposure Strategy

BlueMap should not expose public ports.

Preferred model:

1. BlueMap renders to a configured output directory.
2. The Django app exposes authenticated viewer pages.
3. BlueMap static files are served only after Django validates the active session and Render permission.
4. Nginx performs the actual file transfer using `X-Accel-Redirect`.

Avoid redirecting users to a public BlueMap webserver if RBAC matters. A public BlueMap port allows users to request static assets directly unless another perimeter blocks them.

## Primary User Roles

| Role | Permissions |
| :--- | :--- |
| **Superadministrator** | Full system access. Can create Projects, create users, assign users to Projects with specific roles, configure source roots, and decide which physical Minecraft world folders are visible to each Project. |
| **Project Administrator** | Full access within a specific Project. Can see all Minecraft world folders visible to that Project, create Atlases from selected visible world folders, define one or more Renders for each Atlas, edit configuration, trigger rendering, manage schedules, and inspect logs. |
| **Project User** | Read-only access within a specific Project. Can view all defined Atlases and their associated Renders, but cannot trigger new renders or modify configurations. |

## Configuration Philosophy

The UI should write BlueMap configuration files. Users should not need to hand-edit `.conf` files for normal workflows.

The app should support:

- global BlueMap config templates;
- per-project config profiles;
- per-Render `.conf` generation;
- safe preview/diff before writing config files;
- validation before rendering;
- preserving unknown config fields where possible;
- explicit tracking of generated vs manually edited config files.

## Repository Documents

- [Product Spec](docs/PRODUCT_SPEC.md)
- [Technical Spec](docs/TECHNICAL_SPEC.md)
- [RBAC and Security Spec](docs/RBAC_SECURITY_SPEC.md)
- [BlueMap Config UI Spec](docs/BLUEMAP_CONFIG_UI_SPEC.md)
- [Deployment Spec](docs/DEPLOYMENT_SPEC.md)

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver
```

The development app uses SQLite by default. Configure paths and runtime settings by copying `.env.example` to `.env`. The app loads `.env` automatically on startup, and relative paths are resolved from the project root.

Render jobs are processed by a separate worker process. Start it in another terminal:

```powershell
.\.venv\Scripts\python manage.py renderworker
```

Local runtime data is kept under `data/` by default:

```text
data/source-worlds/      Minecraft world folders for local development
data/bluemap/config/     Generated BlueMap config files
data/bluemap/web/        Generated BlueMap web viewer and map output
data/tmp/                Temporary files for BlueMap/Java subprocesses
```

## BlueMap Connection

The MVP integration expects BlueMap to be available as a local command or standalone CLI jar. Configure:

- `BLUEMAP_CLI_PATH`: executable path or BlueMap standalone CLI `.jar` path.
- `BLUEMAP_JAVA_PATH`: Java executable used when `BLUEMAP_CLI_PATH` points to a `.jar`; defaults to `java`.
- `BLUEMAP_CONFIG_DIR`: directory where the app writes generated BlueMap config files.
- `BLUEMAP_WEBROOT_DIR`: directory where BlueMap writes rendered web output.
- `BLUEMAP_TMP_DIR`: temp directory used for BlueMap subprocesses and Java extraction.
- `BLUEMAP_RENDER_TIMEOUT_SECONDS`: maximum time a BlueMap render subprocess may run.
- `BLUEMAP_RENDER_WORKER_CONCURRENCY`: maximum number of render jobs the worker may run in parallel. Defaults to `1`.
- `BLUEMAP_RENDER_WORKER_POLL_SECONDS`: how often the worker checks for queued jobs. Defaults to `5`.

Each Render page has a **Trigger render** button for superusers and Project Administrators. Pressing it queues a `RenderJob`; the separate `renderworker` process claims queued jobs and runs BlueMap. The app writes a generated config file to:

```text
<BLUEMAP_CONFIG_DIR>/maps/<bluemap_map_id>.conf
```

Then it executes the selected BlueMap Profile command template. The default template targets BlueMap's standalone CLI style:

```text
"{bluemap_cli}" -c "{config_dir}" -r
```

When `BLUEMAP_CLI_PATH` ends in `.jar`, the render runner automatically executes it as:

```text
java -jar "<BLUEMAP_CLI_PATH>" -c "<BLUEMAP_CONFIG_DIR>" -r
```

If BlueMap is not installed or `BLUEMAP_CLI_PATH` is wrong, the render job fails with a log explaining what needs to be configured.

In local `DEBUG` mode, the app serves BlueMap viewer files directly from `BLUEMAP_WEBROOT_DIR` through the authenticated Render asset route. In production this route should return `X-Accel-Redirect` and let Nginx serve the files.

On the first BlueMap CLI run, BlueMap may generate `core.conf` and ask you to set `accept-download: true`. Only do this after confirming you accept Mojang's resource download terms and own a Minecraft Java Edition license.

## MVP Scope

1. Login/logout and user management.
2. Superadministrator, Project Administrator, and Project User roles.
3. Object permissions for Projects, Atlases, and Renders.
4. Discover world folders under `SOURCE_WORLDS_DIR`.
5. Let superadministrators define which world folders are visible to each Project.
6. Let Project Administrators create Atlases from visible world folders.
7. Create and edit BlueMap Render configs through forms.
8. Generate BlueMap `.conf` files.
9. Trigger BlueMap CLI render jobs.
10. Store render logs, status, exit code, timestamps, duration, and parsed progress.
11. Serve viewer pages and Render assets behind RBAC.
12. Docker deployment with read-only source worlds.

## Non-Goals

- Reimplementing BlueMap rendering.
- Rewriting BlueMap's WebGL viewer.
- Managing the Minecraft server process.
- Requiring Crafty Controller or any specific game server panel.
- Exposing BlueMap directly to the public internet.
