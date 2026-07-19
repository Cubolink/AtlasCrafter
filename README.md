# BlueMap Web UI Panel

A Django-based management panel for BlueMap. The application provides a secure web UI for managing Projects, Atlases, and BlueMap Renders, writing BlueMap `.conf` files through forms, triggering renders through the backend, tracking render history, and serving BlueMap viewer assets behind RBAC.

BlueMap remains the renderer and WebGL map viewer technology. This project wraps BlueMap with authentication, authorization, configuration management, render orchestration, and protected delivery.

## Core Idea

BlueMap already does the hard rendering and provides a polished 3D web viewer. This panel should not replace BlueMap's renderer or rewrite its WebGL frontend.

Instead, the panel owns:

- users, roles, permissions, and object-level access;
- discovery of Minecraft world folders from configured source roots;
- detection of Minecraft servers and reusable mod/resource sources;
- UI-driven creation and editing of BlueMap config files;
- Project, Atlas, and Render organization and metadata;
- render execution through BlueMap CLI commands, including incremental updates and full rebuilds;
- render queue, active job overview, logs, elapsed times, and history;
- protected viewer entry points;
- protected static asset delivery for BlueMap output.

## Current Stack

- **Django** as the backend framework.
- **Django templates** for the current UI.
- **Tailwind CSS CLI** plus **DaisyUI** for the panel design system.
- **SQLite** by default for local development.
- **Django auth** plus `ProjectMembership` rows for RBAC.
- **Database-backed render queue** through `RenderJob`.
- **`renderworker` management command** for asynchronous BlueMap execution.
- **BlueMap CLI or standalone CLI jar** for rendering.
- **Protected Django asset route** in local development; **Nginx X-Accel-Redirect** is the intended production serving model.

The included Docker Compose setup already uses PostgreSQL plus separate web and worker containers. Celery, Redis, HTMX, Alpine.js, and Django Ninja remain optional future additions rather than current requirements.

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

Archive flags are soft lifecycle controls:

- `Project.is_active = false` archives a Project and hides it from the main Projects page. It still appears in the superadmin Project management page.
- `Atlas.is_active = false` archives an Atlas. Admins can view and restore archived Atlases from the Project archive page.
- `Render.is_enabled = false` archives a Render. Admins can view and restore archived Renders from the active Atlas archive page.
- `WorldFolder.is_active = false` archives a source world folder for new setup and new render jobs. Existing Atlases, Renders, and previously generated viewer output remain visible unless their Project, Atlas, or Render is archived.

Current model relationships:

```text
User
  |-- ProjectMembership -- Project -- ProjectVisibleWorld -- WorldFolder
                              |             ^
                              v             |
                            Atlas ----------+
                              |
                              v
                            Render -- BlueMapRenderConfig -- BlueMapProfile
                              |
                              v
                            RenderJob -- RenderLogChunk -- RenderArtifact
```

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
  |-- Database render queue
  |-- Viewer wrapper pages
  |
  v
renderworker management command
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
| **Staff** | Can access Panel Settings, manage users, monitor render jobs, and inspect job detail pages. Superuser status is still required for global Project and Minecraft Source administration. |
| **Superadministrator** | Full system access. Can create Projects, create users, assign users to Projects with specific roles, configure Minecraft Sources, and decide which physical Minecraft world folders are visible to each Project. |
| **Project Administrator** | Full access within a specific Project. Can see all Minecraft world folders visible to that Project, create Atlases from selected visible world folders, define one or more Renders for each Atlas, edit configuration, trigger incremental renders, rebuild a Render, and inspect logs. |
| **Project User** | Read-only access within a specific Project. Can view all defined Atlases, project members, Atlas world folders in use, and associated Renders, but cannot trigger new renders or modify configurations. |

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

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
npm.cmd install
npm.cmd run build:css
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver
```

The development app uses SQLite by default. Configure paths and runtime settings by copying `.env.example` to `.env`. The app loads `.env` automatically on startup, and relative paths are resolved from the project root.

While editing templates or Tailwind/DaisyUI styles, keep the CSS compiler running in another terminal:

```powershell
npm.cmd run watch:css
```

Render jobs are processed by a separate worker process. Start it in another terminal:

```powershell
.\.venv\Scripts\python manage.py renderworker
```

Unlike `manage.py runserver`, `renderworker` does not autoreload Python code. Restart the worker after changing render execution code.

Local runtime data is kept under `data/` by default:

```text
data/source-worlds/      Minecraft world folders for local development
data/resource-sources/   Additional modpacks/resource sources
data/bluemap/config/     Generated BlueMap config files
data/bluemap/web/        Generated BlueMap web viewer and map output
data/tmp/                Temporary files for BlueMap/Java subprocesses
```

## Docker Development

The Docker setup uses one application image for both the web process and the render worker, plus Postgres. The BlueMap CLI jar is not committed or copied into the image; mount it from the host instead.

Expected local layout:

```text
data/bin/bluemap-cli.jar       BlueMap standalone CLI jar
data/source-worlds/            Minecraft world folders mounted read-only
data/resource-sources/         Additional mod resources mounted read-only
```

Start the stack:

```powershell
docker compose up --build
```

The Docker image builds the Tailwind/DaisyUI stylesheet in a Node stage and copies the compiled CSS into the Django image.

Then create a superuser inside the web container:

```powershell
docker compose exec web python manage.py createsuperuser
```

Default container paths are:

```text
/app/data/source-worlds        read-only source worlds
/app/data/resource-sources     read-only mod/resource sources
/app/bin/bluemap-cli.jar       mounted BlueMap CLI jar
/app/data/bluemap/config       generated BlueMap config bind mount
/app/data/bluemap/web          generated BlueMap web output bind mount
/app/data/tmp                  Java/BlueMap temp bind mount
```

The compose file defaults to one render at a time:

```text
BLUEMAP_RENDER_WORKER_CONCURRENCY=1
```

Override compose settings with environment variables in your shell or a local `.env` file used by Docker Compose. Keep in mind that Django's own `.env` file is not copied into the image.

## BlueMap Connection

The current integration expects BlueMap to be available as a local command or standalone CLI jar. Configure:

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

Project Administrators can also choose **Rebuild Render** when Minecraft resources or render settings require every tile to be regenerated. A rebuild temporarily moves only that map's existing BlueMap output aside, runs BlueMap with `--force-render`, and removes the backup after success. If BlueMap fails or times out, the worker restores the previous generated map.

If BlueMap is not installed or `BLUEMAP_CLI_PATH` is wrong, the render job fails with a log explaining what needs to be configured.

If a World Folder is archived, new render jobs for its existing Renders are blocked and a direct trigger attempt creates a failed job explaining that the World Folder must be restored first. If the physical folder disappears from disk, scan and render-time checks archive the World Folder and record a job log explaining the missing `level.dat`.

In local `DEBUG` mode, the app serves BlueMap viewer files directly from `BLUEMAP_WEBROOT_DIR` through the authenticated Render asset route. In production this route should return `X-Accel-Redirect` and let Nginx serve the files.

On the first BlueMap CLI run, BlueMap may generate `core.conf` and ask you to set `accept-download: true`. Only do this after confirming you accept Mojang's resource download terms and own a Minecraft Java Edition license.

## Current Functional Scope

1. Login/logout and user management.
2. Superadministrator, Project Administrator, and Project User roles.
3. Object permissions for Projects, Atlases, and Renders.
4. Discover world folders under `SOURCE_WORLDS_DIR`.
5. Let superadministrators define which world folders are visible to each Project.
6. Let Project Administrators create Atlases from visible world folders.
7. Create and edit BlueMap Render configs through styled forms, including color pickers, toggles, sliders, start position, render masks, marker sets, and Minecraft resource selection.
8. Preview generated config content and show a read-only raw config panel.
9. Generate BlueMap `.conf` files.
10. Trigger BlueMap CLI render jobs and full Render rebuilds.
11. Store render logs, status, exit code, operation type, timestamps, elapsed time, and progress fields.
12. Monitor active and recent finished jobs from Panel Settings.
13. Serve viewer pages and Render assets behind RBAC.
14. Docker deployment with read-only source worlds and resource sources.

## Non-Goals

- Reimplementing BlueMap rendering.
- Rewriting BlueMap's WebGL viewer.
- Managing the Minecraft server process.
- Requiring Crafty Controller or any specific game server panel.
- Exposing BlueMap directly to the public internet.
