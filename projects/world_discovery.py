from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from .models import WorldFolder


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
        world, created = WorldFolder.objects.get_or_create(
            source_path=str(world_path),
            defaults={
                "display_name": world_path.name,
                "detected_dimensions": dimensions,
            },
        )
        if created:
            result.created.append(world)
            continue

        was_inactive = not world.is_active
        if world.detected_dimensions != dimensions or was_inactive:
            world.detected_dimensions = dimensions
            world.is_active = True
            world.save(update_fields=["detected_dimensions", "is_active", "updated_at"])
            if was_inactive:
                result.restored.append(world)
            else:
                result.updated.append(world)
        else:
            result.unchanged.append(world)

    archive_missing_worlds(source_root, discovered_paths, result)
    return result


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


def build_world_tree(worlds, source_root: Path | None = None) -> dict:
    source_root = Path(source_root or settings.SOURCE_WORLDS_DIR).resolve()
    root = {"name": source_root.name, "children": {}, "worlds": []}

    for world in worlds:
        world_path = Path(world.source_path)
        parts = relative_world_parts(world_path, source_root)
        node = root
        for part in parts[:-1]:
            node = node["children"].setdefault(part, {"name": part, "children": {}, "worlds": []})
        node["worlds"].append(world)

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
    for child in node["children"].values():
        sort_tree(child)
