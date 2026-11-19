from django import template
from ..models import money
register = template.Library()

@register.filter
def currency(value):
    return f'{money(value or 0):,.2f}'

@register.simple_tag(takes_context=True)
def page_url(context, number):
    params = context['request'].GET.copy()
    params['page'] = number
    return '?' + params.urlencode()
