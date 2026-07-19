from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

ICON_DIR = settings.BASE_DIR / "node_modules" / "lucide-static" / "icons"
ICON_NAME_PATTERN = set("abcdefghijklmnopqrstuvwxyz0123456789-")
DEFAULT_ICON_CLASSES = "icon"


@register.simple_tag
def icon(name, css_class=DEFAULT_ICON_CLASSES, label=""):
    if not name or any(character not in ICON_NAME_PATTERN for character in name):
        return ""

    svg = load_icon(name)
    if not svg:
        return ""

    if label:
        svg = svg.replace("<svg ", f'<svg role="img" aria-label="{label}" ', 1)
    else:
        svg = svg.replace("<svg ", '<svg aria-hidden="true" ', 1)

    svg = svg.replace("<svg ", f'<svg class="{css_class}" ', 1)
    return format_html("{}", mark_safe(svg))


@lru_cache(maxsize=128)
def load_icon(name):
    path = (ICON_DIR / f"{name}.svg").resolve()
    if not is_relative_to(path, ICON_DIR.resolve()) or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
