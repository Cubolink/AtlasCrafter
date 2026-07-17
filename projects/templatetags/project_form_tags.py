from django import template


register = template.Library()


@register.filter
def contains_world_id(values, world_id):
    return str(world_id) in {str(value) for value in values or []}
