from django import template
from django.conf import settings
import os

register = template.Library()

@register.filter
def handle_missing_image(image_field, default_image='placeholder1.jpg'):
    """
    Template filter to handle missing images by showing a default placeholder.
    Usage: {{ product.image|handle_missing_image }}
    """
    if image_field and hasattr(image_field, 'url') and os.path.exists(image_field.path):
        return image_field.url
    return f"{settings.MEDIA_URL}{default_image}"
