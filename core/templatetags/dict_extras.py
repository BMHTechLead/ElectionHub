from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    if not d:
        return None
    return d.get(key)


# Add CSS class to Django form field
@register.filter(name='add_class')
def add_class(field, css):
    return field.as_widget(attrs={"class": css})
