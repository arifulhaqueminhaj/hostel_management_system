from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def sum_amount(queryset):
    """Sum the amount field of a queryset of payments."""
    return sum(p.amount for p in queryset)

@register.filter
def floatdiv(value, arg):
    """Divide value by arg and return float, handling division by zero."""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0