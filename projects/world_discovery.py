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
    unchanged: list[WorldFolder] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.created) + len(self.updated) + len(self.unchanged)


def scan_source_worlds(source_root: Path | None = None) -> WorldScanResult:
    source_root = Path(source_root or settings.SOURCE_WORLDS_DIR).resolve()
    result = WorldScanResult()
    if not source_root.exists():
        return result

    for level_dat in sorted(source_root.rglob("level.dat")):
        world_path = level_dat.parent.resolve()
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

        if world.detected_dimensions != dimensions:
            world.detected_dimensions = dimensions
            world.save(update_fields=["detected_dimensions", "updated_at"])
            result.updated.append(world)
        else:
            result.unchanged.append(world)

    return result


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
