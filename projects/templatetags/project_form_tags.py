from django import template

from projects.markers import format_number


register = template.Library()


@register.filter
def contains_world_id(values, world_id):
    return str(world_id) in {str(value) for value in values or []}


@register.filter
def compact_coordinate(value):
    return format_number(value)
