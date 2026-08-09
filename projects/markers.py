import json
from decimal import Decimal
from html import escape

from .models import Marker


def format_marker_sets(render) -> str:
    marker_sets = render.marker_sets.prefetch_related("markers").all()
    if not marker_sets:
        return "{}"

    set_blocks = [format_marker_set(marker_set) for marker_set in marker_sets]
    return "{\n" + "\n".join(set_blocks) + "\n}"


def format_marker_set(marker_set) -> str:
    marker_blocks = [format_marker(marker) for marker in marker_set.markers.all()]
    markers = "{}"
    if marker_blocks:
        markers = "{\n" + "\n".join(marker_blocks) + "\n  }"

    return (
        f"  {marker_set.bluemap_id}: {{\n"
        f"    label: {hocon_string(marker_set.label)}\n"
        f"    toggleable: {hocon_bool(marker_set.toggleable)}\n"
        f"    default-hidden: {hocon_bool(marker_set.default_hidden)}\n"
        f"    sorting: {marker_set.sorting}\n"
        f"    markers: {markers}\n"
        "  }"
    )


def format_marker(marker) -> str:
    if marker.marker_type != Marker.Type.POI:
        raise ValueError(f"Unsupported marker type: {marker.marker_type}")

    lines = [
        f"    {marker.bluemap_id}: {{",
        '      type: "poi"',
        (
            "      position: { "
            f"x: {format_number(marker.position_x)}, "
            f"y: {format_number(marker.position_y)}, "
            f"z: {format_number(marker.position_z)} "
            "}"
        ),
        f"      label: {hocon_string(marker.label)}",
    ]
    if marker.detail:
        lines.append(f"      detail: {hocon_string(safe_marker_detail(marker.detail))}")
    lines.extend(
        [
            f"      icon: {hocon_string(marker.icon)}",
            f"      anchor: {{ x: {marker.anchor_x}, y: {marker.anchor_y} }}",
            f"      sorting: {marker.sorting}",
            f"      listed: {hocon_bool(marker.listed)}",
        ]
    )
    if marker.min_distance is not None:
        lines.append(f"      min-distance: {marker.min_distance}")
    if marker.max_distance is not None:
        lines.append(f"      max-distance: {marker.max_distance}")
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
        return f"{value.normalize():f}"
    return str(value)
