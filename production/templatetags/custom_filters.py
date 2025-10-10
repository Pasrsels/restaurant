from django import template

register = template.Library()

@register.filter
def get_ingredient_item(dictionary, key):
    return dictionary.get(key, [])
