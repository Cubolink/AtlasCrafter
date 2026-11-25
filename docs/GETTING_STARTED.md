# Getting started

[Back to README](../README.md) · [User guide](USER_GUIDE.md)

Choose Docker for a local installation with PostgreSQL and a separate render worker, or native setup to develop the panel or run its processes directly on Linux/Windows.

## Requirements

| Setup | Requirements |
| :--- | :--- |
| Docker | Docker Engine/Desktop with Compose. The image builds the CSS and includes Python 3.12 and Java 25. |
| Native | Python 3.12, Node.js/npm (the Docker build uses Node 22), and Java compatible with your BlueMap release. |
| Rendering | A Minecraft Java Edition world folder and a compatible standalone BlueMap CLI jar. |
| Viewing | A browser with WebGL support. |

Download the **CLI** artifact from [BlueMap releases](https://github.com/BlueMap-Minecraft/BlueMap/releases), choosing a release compatible with your world and Java runtime. A server plugin jar is not a substitute. Check that release's Java requirements.

Panel development and the Django tests do not need a BlueMap jar or world. Actual rendering does.

## Docker installation

### 1. Prepare files

```sh
git clone https://github.com/Cubolink/AtlasCrafter.git
cd AtlasCrafter
```

Prepare these paths. Copy a world into the default source directory, or edit the Compose bind mounts to point to your existing server folders.

| Host path | Purpose | Container access |
| :--- | :--- | :--- |
| `data/bin/bluemap-cli.jar` | Standalone CLI jar, renamed to this filename. | Read-only |
| `data/source-worlds/` | World/server folders to scan; each world contains `level.dat`. | Read-only |
| `data/resource-sources/` | Optional modpack/resource sources. | Read-only |
| `data/bluemap/config/` | Generated BlueMap configuration. | Writable |
| `data/bluemap/web/` | Generated viewer/map output. | Writable |
| `data/tmp/` | Java and render temporary files. | Writable |

Keep your original world backups. Generated map output is separate from the sources.

### 2. Configure and start

Compose has defaults for local use. To override them, copy `.env.example` to `.env` and edit it:

```sh
cp .env.example .env
```

In PowerShell, use `Copy-Item .env.example .env` instead.

Compose reads `.env` for interpolation and sets the container's paths explicitly; the native relative paths in the example do not change Compose bind mounts. Keep `DATABASE_URL` commented out to use the default Compose database. If you customize PostgreSQL credentials, update `DATABASE_URL` and the `POSTGRES_*` values together.

```sh
docker compose up --build -d
docker compose logs -f web renderworker
```

Both application services run migrations at startup. Once the web service is ready, use another terminal to create the first administrator:

```sh
docker compose exec web python manage.py createsuperuser
```

Open [http://localhost:8000](http://localhost:8000). The render worker is already running in another container. The panel does not create example Projects or maps automatically.

Compose publishes port 8000 on the host. To accept local connections only, bind it to `127.0.0.1` in your Compose configuration. The supplied server and credentials are development defaults; read [deployment considerations](#deployment-considerations) before exposing it.

### 3. Create a map

Follow [your first map](USER_GUIDE.md#your-first-map). A fresh installation needs sources, a BlueMap Profile, a Project, an Atlas, and a Render before it can display a map.

Stop the stack while keeping its database and output:

```sh
docker compose down
```

The database lives in the `postgres_data` named volume; generated bind-mounted files stay under `data/`.

## Native installation

These instructions use SQLite unless `DATABASE_URL` is set. Run commands from the repository root.

### Linux

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run build:css
cp .env.example .env
```

Edit `.env` for your paths, CLI jar, and Java executable, then run:

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

In another terminal, activate the same environment and start the worker:

```sh
. .venv/bin/activate
python manage.py renderworker
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
npm.cmd run build:css
Copy-Item .env.example .env
```

Edit `.env`, then run:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

In another terminal:

```powershell
.\.venv\Scripts\python.exe manage.py renderworker
```

Open [http://localhost:8000](http://localhost:8000). Keep both processes running: the web process accepts requests and queues jobs; the worker executes them. Unlike `runserver`, `renderworker` does not reload Python changes automatically.

For template/style development, run `npm run watch:css` in another terminal (`npm.cmd run watch:css` in PowerShell).

## Configuration reference

The app loads `.env` automatically. Existing process environment values take precedence. Relative filesystem paths resolve from the repository root.

| Setting | Purpose / default |
| :--- | :--- |
| `SOURCE_WORLDS_DIR` | World/server discovery root; `data/source-worlds`. |
| `BLUEMAP_RESOURCE_SOURCES_DIR` | Additional reusable resource sources; `data/resource-sources`. |
| `BLUEMAP_CLI_PATH` | Executable or CLI jar. `.env.example` uses `./data/bin/bluemap-cli.jar`; without it the app looks for `bluemap`. |
| `BLUEMAP_JAVA_PATH` | Java executable for jar execution; `java`. |
| `BLUEMAP_CONFIG_DIR` | Generated configs; `data/bluemap/config`. |
| `BLUEMAP_WEBROOT_DIR` | Generated viewer/map output; `data/bluemap/web`. |
| `BLUEMAP_TMP_DIR` | Java/BlueMap temporary files; `data/tmp`. |
| `BLUEMAP_RENDER_TIMEOUT_SECONDS` | Subprocess timeout; `3600`. Increase for large renders when needed. |
| `BLUEMAP_RENDER_WORKER_CONCURRENCY` | Worker job concurrency; `1`. |
| `BLUEMAP_RENDER_WORKER_POLL_SECONDS` | Queue polling interval; `5`. |
| `DATABASE_URL` | PostgreSQL or SQLite URL. When absent, native setup uses `db.sqlite3`. Compose supplies PostgreSQL by default. |
| `DJANGO_TIME_ZONE` | Timezone; `UTC`. |
| `DJANGO_SECRET_KEY` | Django signing secret. Replace the development default for deployment. |
| `DJANGO_DEBUG` | Development mode; defaults to `true`. With `false`, map files require Nginx internal delivery. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated permitted hostnames. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins including scheme, for reverse-proxy deployments. |
| `DJANGO_USE_X_FORWARDED_HOST` | Trust forwarded host; enable only behind a proxy that controls it. |
| `DJANGO_CSRF_COOKIE_SECURE`, `DJANGO_SESSION_COOKIE_SECURE` | Secure-cookie flags. App defaults follow `DEBUG`; `.env.example` explicitly sets both to `false` for local HTTP. |
| `INTERNAL_ACCEL_ROOT` | Nginx internal map route prefix; `/_protected_bluemap/`. |

Compose also accepts `DJANGO_PORT` (host port, default `8000`) and `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` for database initialization. Changing `POSTGRES_*` does not change credentials in an already initialized database volume.

## BlueMap's first run

AtlasCrafter writes per-Render configs under `BLUEMAP_CONFIG_DIR/maps/` when jobs execute and prepares runtime webapp/file-storage configuration. It invokes jar-based profiles through Java automatically.

BlueMap may stop the first job after creating `core.conf`. Open `data/bluemap/config/core.conf` (or your configured directory), read BlueMap's resource-download notice, and set `accept-download: true` only if you accept the terms and meet their requirements. Then trigger the Render again.

Normal map configuration is managed through the UI. Raw preview is read-only. Avoid manually changing panel-generated map files: later jobs regenerate them from database state. Use a dedicated config/output directory instead of sharing another BlueMap installation's generated files.

## Troubleshooting

| Symptom | Check |
| :--- | :--- |
| Job stays queued | `renderworker` must be running with the same database and paths as the web process. |
| CLI not found / Java fails | Check the CLI path, mounted filename, Java executable, and CLI release's Java requirement. Open the job logs. |
| First job requests resources | Review `core.conf` as described above, then trigger the Render again. |
| No worlds after scanning | Check the source root and read permissions. Each world needs `level.dat`. |
| Project has no available worlds | A superadministrator must make folders visible to the Project. Then explicitly create an Atlas. |
| Terrain rendering is blocked | Check whether the source is archived or `level.dat` is missing. Restore it in Minecraft Sources once valid. |
| Viewer says no output exists | Complete a successful render and check the configured webroot. A Render record alone has no generated map. |
| Viewer fails with `DEBUG=false` | Configure the Nginx internal location; Django returns `X-Accel-Redirect` in this mode. |
| POST fails behind HTTPS | Configure the public host, trusted HTTPS origin, forwarded headers, and secure-cookie flags consistently. |

## Deployment considerations

The supplied Compose file runs Django's development server. A production deployment needs a production application server, HTTPS/reverse-proxy configuration, a strong signing secret, suitable database credentials, and persistent worker supervision.

With `DJANGO_DEBUG=false`, map files use Nginx internal delivery. Match the alias to your generated webroot and the location to `INTERNAL_ACCEL_ROOT`:

```nginx
location /_protected_bluemap/ {
    internal;
    alias /srv/atlascrafter/bluemap-web/;
}
```

This is only the internal location, not a complete server block. Proxy panel and `/renders/<id>/assets/` requests to Django first. A public static alias or exposed BlueMap webserver would bypass the panel's access checks. The generated `webserver.conf` currently contains an enabled port 8100 configuration, but normal render commands do not start that server; do not start/publish it as a parallel public viewer.

Panel CSS/JS/icons are ordinary static assets; the Docker build collects them and WhiteNoise serves them. BlueMap files use the separate protected route.

Back up the application database, generated configs, and optionally map output if regeneration is expensive. Source-world backups remain your Minecraft infrastructure's responsibility. See [architecture](ARCHITECTURE.md) for runtime boundaries.
