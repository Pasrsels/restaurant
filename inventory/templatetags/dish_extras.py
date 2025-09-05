from django import template

register = template.Library()

@register.filter
def get_by_name(dishes, name):
    print(dishes)
    return next((dish for dish in dishes if dish.name == name), None)

@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return 0
