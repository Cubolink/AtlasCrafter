import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import MinecraftResourceSource, MinecraftServer, WorldFolder


DIMENSION_OVERWORLD = "minecraft:overworld"
DIMENSION_NETHER = "minecraft:the_nether"
DIMENSION_END = "minecraft:the_end"


@dataclass
class WorldScanResult:
    created: list[WorldFolder] = field(default_factory=list)
    updated: list[WorldFolder] = field(default_factory=list)
    restored: list[WorldFolder] = field(default_factory=list)
    archived: list[WorldFolder] = field(default_factory=list)
    unchanged: list[WorldFolder] = field(default_factory=list)
    servers: list[MinecraftServer] = field(default_factory=list)
    resource_sources: list[MinecraftResourceSource] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.created)
            + len(self.updated)
            + len(self.restored)
            + len(self.archived)
            + len(self.unchanged)
        )


def scan_source_worlds(source_root: Path | None = None) -> WorldScanResult:
    source_root = Path(source_root or settings.SOURCE_WORLDS_DIR).resolve()
    result = WorldScanResult()
    if not source_root.exists():
        archive_missing_worlds(source_root, set(), result)
        return result

    discovered_paths = set()
    for level_dat in sorted(source_root.rglob("level.dat")):
        world_path = level_dat.parent.resolve()
        discovered_paths.add(str(world_path))
        dimensions = detect_dimensions(world_path)
        server_root = find_server_root(world_path, source_root)
        server = sync_minecraft_server(server_root, result) if server_root else None
        resource_source = server.resource_source if server else sync_modpack_source(
            world_path,
            source_root,
            result,
        )
        world, created = WorldFolder.objects.get_or_create(
            source_path=str(world_path),
            defaults={
                "display_name": world_path.name,
                "detected_dimensions": dimensions,
                "minecraft_server": server,
                "default_resource_source": resource_source,
            },
        )
        if created:
            result.created.append(world)
            continue

        was_inactive = not world.is_active
        changed = world.detected_dimensions != dimensions or was_inactive
        if world.minecraft_server_id != getattr(server, "id", None):
            world.minecraft_server = server
            changed = True
        if world.default_resource_source_id is None and resource_source is not None:
            world.default_resource_source = resource_source
            changed = True
        if changed:
            world.detected_dimensions = dimensions
            world.is_active = True
            world.save(
                update_fields=[
                    "detected_dimensions",
                    "minecraft_server",
                    "default_resource_source",
                    "is_active",
                    "updated_at",
                ]
            )
            if was_inactive:
                result.restored.append(world)
            else:
                result.updated.append(world)
        else:
            result.unchanged.append(world)

    archive_missing_worlds(source_root, discovered_paths, result)
    archive_missing_servers(source_root)
    return result


def find_server_root(world_path: Path, source_root: Path) -> Path | None:
    for candidate in ancestors_within_source(world_path, source_root):
        if is_minecraft_server(candidate):
            return candidate
    return None


def is_minecraft_server(path: Path) -> bool:
    has_server_marker = (path / "server.properties").is_file() or (path / "eula.txt").is_file()
    has_server_libraries = (path / "libraries" / "net" / "minecraft" / "server").is_dir()
    return has_server_marker or has_server_libraries


def sync_minecraft_server(
    server_root: Path,
    result: WorldScanResult,
) -> MinecraftServer:
    scanned_at = timezone.now()
    resource_source = sync_resource_source(
        root_path=server_root,
        source_type=MinecraftResourceSource.SourceType.SERVER,
        display_name=f"{server_root.name} resources",
        scanned_at=scanned_at,
        result=result,
    )
    server, created = MinecraftServer.objects.get_or_create(
        root_path=str(server_root),
        defaults={
            "display_name": server_root.name,
            "resource_source": resource_source,
            "is_active": True,
            "last_scanned_at": scanned_at,
        },
    )
    if not created:
        server.resource_source = resource_source
        server.is_active = True
        server.last_scanned_at = scanned_at
        server.save(
            update_fields=["resource_source", "is_active", "last_scanned_at", "updated_at"]
        )
    if created or server not in result.servers:
        result.servers.append(server)
    return server


def sync_modpack_source(
    world_path: Path,
    source_root: Path,
    result: WorldScanResult,
) -> MinecraftResourceSource | None:
    for candidate in ancestors_within_source(world_path, source_root):
        mods_path = candidate / "mods"
        if mods_path.is_dir() and any(mods_path.glob("*.jar")):
            return sync_resource_source(
                root_path=candidate,
                source_type=MinecraftResourceSource.SourceType.MODPACK,
                display_name=f"{candidate.name} resources",
                scanned_at=timezone.now(),
                result=result,
            )
    return None


def sync_resource_source(
    *,
    root_path: Path,
    source_type: str,
    display_name: str,
    scanned_at,
    result: WorldScanResult,
) -> MinecraftResourceSource:
    mods_path = root_path / "mods"
    detected_values = {
        "display_name": display_name,
        "mods_path": str(mods_path) if mods_path.is_dir() else "",
        "minecraft_version": detect_server_minecraft_version(root_path) or "",
        "mod_loader": detect_mod_loader(root_path),
        "source_type": source_type,
        "is_active": True,
        "is_detected": True,
        "last_scanned_at": scanned_at,
    }
    source, created = MinecraftResourceSource.objects.get_or_create(
        root_path=str(root_path),
        defaults=detected_values,
    )
    if not created and source.auto_detect:
        for field_name, value in detected_values.items():
            setattr(source, field_name, value)
        source.save(update_fields=[*detected_values, "updated_at"])
    if source not in result.resource_sources:
        result.resource_sources.append(source)
    return source


def ancestors_within_source(path: Path, source_root: Path):
    current = path.resolve()
    source_root = source_root.resolve()
    while True:
        try:
            current.relative_to(source_root)
        except ValueError:
            return
        yield current
        if current == source_root or current.parent == current:
            return
        current = current.parent


def detect_server_minecraft_version(server_root: Path) -> str | None:
    versions_path = server_root / "libraries" / "net" / "minecraft" / "server"
    if not versions_path.is_dir():
        return None

    versions = [
        path.name
        for path in versions_path.iterdir()
        if path.is_dir() and re.fullmatch(r"\d+\.\d+(?:\.\d+)?", path.name)
    ]
    if not versions:
        return None
    return max(versions, key=lambda version: tuple(int(part) for part in version.split(".")))


def detect_mod_loader(root_path: Path) -> str:
    libraries = root_path / "libraries"
    if (libraries / "net" / "neoforged").is_dir():
        return MinecraftResourceSource.ModLoader.NEOFORGE
    if (libraries / "net" / "minecraftforge").is_dir() or any(root_path.glob("forge-*.jar")):
        return MinecraftResourceSource.ModLoader.FORGE
    if (root_path / "fabric-server-launch.jar").is_file() or (root_path / ".fabric").is_dir():
        return MinecraftResourceSource.ModLoader.FABRIC
    if (root_path / "quilt-server-launch.jar").is_file():
        return MinecraftResourceSource.ModLoader.QUILT
    return MinecraftResourceSource.ModLoader.UNKNOWN


def archive_missing_worlds(
    source_root: Path,
    discovered_paths: set[str],
    result: WorldScanResult,
) -> None:
    for world in WorldFolder.objects.filter(is_active=True):
        world_path = Path(world.source_path)
        if not is_path_inside_source_root(world_path, source_root):
            continue
        if str(world_path.resolve()) in discovered_paths:
            continue
        if world_folder_exists(world):
            continue
        world.is_active = False
        world.save(update_fields=["is_active", "updated_at"])
        result.archived.append(world)


def archive_missing_servers(source_root: Path) -> None:
    for server in MinecraftServer.objects.filter(is_active=True):
        server_path = Path(server.root_path)
        if not is_path_inside_source_root(server_path, source_root):
            continue
        if server_path.is_dir() and is_minecraft_server(server_path):
            continue
        server.is_active = False
        server.save(update_fields=["is_active", "updated_at"])


def is_path_inside_source_root(world_path: Path, source_root: Path) -> bool:
    try:
        world_path.resolve().relative_to(source_root)
    except ValueError:
        return False
    return True


def world_folder_exists(world: WorldFolder) -> bool:
    return (Path(world.source_path) / "level.dat").is_file()


def detect_dimensions(world_path: Path) -> list[str]:
    dimensions = [DIMENSION_OVERWORLD]
    if (world_path / "DIM-1").is_dir():
        dimensions.append(DIMENSION_NETHER)
    if (world_path / "DIM1").is_dir():
        dimensions.append(DIMENSION_END)
    return dimensions


def build_world_tree(worlds, source_root: Path | None = None, resource_sources=None) -> dict:
    source_root = Path(source_root or settings.SOURCE_WORLDS_DIR).resolve()
    root = {
        "name": source_root.name,
        "path": str(source_root),
        "server": None,
        "resource_sources": [],
        "children": {},
        "worlds": [],
    }

    for world in worlds:
        world_path = Path(world.source_path)
        parts = relative_world_parts(world_path, source_root)
        node = root
        current_path = source_root
        for part in parts[:-1]:
            current_path /= part
            node = node["children"].setdefault(
                part,
                {
                    "name": part,
                    "path": str(current_path),
                    "server": None,
                    "resource_sources": [],
                    "children": {},
                    "worlds": [],
                },
            )
        node["worlds"].append(world)

    for server in MinecraftServer.objects.filter(is_active=True).select_related("resource_source"):
        if not is_path_inside_source_root(Path(server.root_path), source_root):
            continue
        parts = relative_world_parts(Path(server.root_path), source_root)
        node = root
        current_path = source_root
        for part in parts:
            current_path /= part
            node = node["children"].setdefault(
                part,
                {
                    "name": part,
                    "path": str(current_path),
                    "server": None,
                    "resource_sources": [],
                    "children": {},
                    "worlds": [],
                },
            )
        node["server"] = server

    for source in resource_sources or []:
        resource_path = Path(source.mods_path or source.root_path)
        if not is_path_inside_source_root(resource_path, source_root):
            continue
        parts = relative_world_parts(resource_path, source_root)
        node = root
        current_path = source_root
        for part in parts:
            current_path /= part
            node = node["children"].setdefault(
                part,
                {
                    "name": part,
                    "path": str(current_path),
                    "server": None,
                    "resource_sources": [],
                    "children": {},
                    "worlds": [],
                },
            )
        node["resource_sources"].append(source)

    sort_tree(root)
    return root


def relative_world_parts(world_path: Path, source_root: Path) -> tuple[str, ...]:
    try:
        return world_path.resolve().relative_to(source_root).parts
    except ValueError:
        return ("Outside source root", *world_path.parts)


def sort_tree(node: dict) -> None:
    node["children"] = dict(sorted(node["children"].items()))
    node["worlds"].sort(key=lambda world: world.display_name.lower())
    node["resource_sources"].sort(key=lambda source: source.display_name.lower())
    for child in node["children"].values():
        sort_tree(child)
