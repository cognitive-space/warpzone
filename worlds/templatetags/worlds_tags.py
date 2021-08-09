import json

from django import template
from django.utils.html import mark_safe

register = template.Library()


@register.filter
def json_data(value):
    return mark_safe(json.dumps(value))
