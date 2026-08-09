import json
from decimal import Decimal
from html import escape

from .models import Marker


MARKER_SNAPSHOT_VERSION = 1


def build_marker_snapshot(render) -> dict:
    marker_sets = {}
    for marker_set in render.marker_sets.prefetch_related("markers").all():
        markers = {}
        for marker in marker_set.markers.all():
            markers[marker.bluemap_id] = {
                "type": marker.marker_type,
                "label": marker.label,
                "detail": marker.detail,
                "position_x": format_number(marker.position_x),
                "position_y": format_number(marker.position_y),
                "position_z": format_number(marker.position_z),
                "sorting": marker.sorting,
                "listed": marker.listed,
                "min_distance": marker.min_distance,
                "max_distance": marker.max_distance,
                "icon": marker.icon,
                "anchor_x": marker.anchor_x,
                "anchor_y": marker.anchor_y,
            }
        marker_sets[marker_set.bluemap_id] = {
            "label": marker_set.label,
            "toggleable": marker_set.toggleable,
            "default_hidden": marker_set.default_hidden,
            "sorting": marker_set.sorting,
            "markers": markers,
        }
    return {"version": MARKER_SNAPSHOT_VERSION, "sets": marker_sets}


def normalize_marker_snapshot(snapshot) -> dict | None:
    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("version") != MARKER_SNAPSHOT_VERSION:
        return None
    if not isinstance(snapshot.get("sets"), dict):
        return None
    return snapshot


def build_marker_management_state(render) -> dict:
    current = build_marker_snapshot(render)
    published = normalize_marker_snapshot(render.published_marker_snapshot)
    current_sets = current["sets"]
    published_sets = published["sets"] if published else {}
    marker_set_objects = {
        marker_set.bluemap_id: marker_set
        for marker_set in render.marker_sets.prefetch_related("markers").all()
    }
    rows = []
    change_count = 0

    for set_id, set_data in current_sets.items():
        marker_set = marker_set_objects[set_id]
        published_set = published_sets.get(set_id)
        if published is None:
            set_status = "unknown"
        elif published_set is None:
            set_status = "new"
            change_count += 1
        elif marker_set_properties(set_data) != marker_set_properties(published_set):
            set_status = "modified"
            change_count += 1
        else:
            set_status = "published"

        published_markers = published_set.get("markers", {}) if published_set else {}
        marker_objects = {marker.bluemap_id: marker for marker in marker_set.markers.all()}
        marker_rows = []
        for marker_id, marker_data in set_data["markers"].items():
            published_marker = published_markers.get(marker_id)
            if published is None:
                marker_status = "unknown"
            elif published_marker is None:
                marker_status = "new"
                change_count += 1
            elif marker_data != published_marker:
                marker_status = "modified"
                change_count += 1
            else:
                marker_status = "published"
            marker_rows.append(
                {
                    "marker": marker_objects[marker_id],
                    "status": marker_status,
                }
            )

        deleted_markers = []
        for marker_id, marker_data in published_markers.items():
            if marker_id not in set_data["markers"]:
                deleted_markers.append({"id": marker_id, **marker_data})
                change_count += 1

        rows.append(
            {
                "marker_set": marker_set,
                "status": set_status,
                "markers": marker_rows,
                "deleted_markers": deleted_markers,
                "has_marker_changes": any(
                    row["status"] in {"new", "modified"} for row in marker_rows
                )
                or bool(deleted_markers),
            }
        )

    deleted_sets = []
    if published:
        for set_id, set_data in published_sets.items():
            if set_id not in current_sets:
                deleted_sets.append({"id": set_id, **set_data})
                change_count += 1

    return {
        "rows": rows,
        "deleted_sets": deleted_sets,
        "tracking": published is not None,
        "is_dirty": published is not None and current != published,
        "change_count": change_count,
        "current_snapshot": current,
    }


def marker_set_properties(marker_set_data: dict) -> dict:
    return {
        key: marker_set_data.get(key)
        for key in ["label", "toggleable", "default_hidden", "sorting"]
    }


def format_marker_sets(render, snapshot=None) -> str:
    snapshot = normalize_marker_snapshot(snapshot) or build_marker_snapshot(render)
    marker_sets = snapshot["sets"]
    if not marker_sets:
        return "{}"

    set_blocks = [
        format_marker_set(marker_set_id, marker_set_data)
        for marker_set_id, marker_set_data in marker_sets.items()
    ]
    return "{\n" + "\n".join(set_blocks) + "\n}"


def format_marker_set(marker_set_id: str, marker_set_data: dict) -> str:
    marker_blocks = [
        format_marker(marker_id, marker_data)
        for marker_id, marker_data in marker_set_data["markers"].items()
    ]
    markers = "{}"
    if marker_blocks:
        markers = "{\n" + "\n".join(marker_blocks) + "\n  }"

    return (
        f"  {marker_set_id}: {{\n"
        f"    label: {hocon_string(marker_set_data['label'])}\n"
        f"    toggleable: {hocon_bool(marker_set_data['toggleable'])}\n"
        f"    default-hidden: {hocon_bool(marker_set_data['default_hidden'])}\n"
        f"    sorting: {marker_set_data['sorting']}\n"
        f"    markers: {markers}\n"
        "  }"
    )


def format_marker(marker_id: str, marker_data: dict) -> str:
    if marker_data["type"] != Marker.Type.POI:
        raise ValueError(f"Unsupported marker type: {marker_data['type']}")

    lines = [
        f"    {marker_id}: {{",
        '      type: "poi"',
        (
            "      position: { "
            f"x: {marker_data['position_x']}, "
            f"y: {marker_data['position_y']}, "
            f"z: {marker_data['position_z']} "
            "}"
        ),
        f"      label: {hocon_string(marker_data['label'])}",
    ]
    if marker_data["detail"]:
        lines.append(
            f"      detail: {hocon_string(safe_marker_detail(marker_data['detail']))}"
        )
    lines.extend(
        [
            f"      icon: {hocon_string(marker_data['icon'])}",
            (
                "      anchor: { "
                f"x: {marker_data['anchor_x']}, y: {marker_data['anchor_y']} "
                "}"
            ),
            f"      sorting: {marker_data['sorting']}",
            f"      listed: {hocon_bool(marker_data['listed'])}",
        ]
    )
    if marker_data["min_distance"] is not None:
        lines.append(f"      min-distance: {marker_data['min_distance']}")
    if marker_data["max_distance"] is not None:
        lines.append(f"      max-distance: {marker_data['max_distance']}")
    lines.append("    }")
    return "\n".join(lines)


def safe_marker_detail(detail: str) -> str:
    normalized = detail.replace("\r\n", "\n").replace("\r", "\n")
    return escape(normalized, quote=True).replace("\n", "<br>")


def hocon_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def hocon_bool(value: bool) -> str:
    return "true" if value else "false"


def format_number(value) -> str:
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        return f"{value.normalize():f}"
    return str(value)
