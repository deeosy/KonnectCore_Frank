"""Money display for templates: {{ amount|money:active_organisation.currency }} -> 'GHS 2,160.00'.

A non-breaking space joins the currency and the amount so they never wrap onto two lines.
Display only: stored values and calculations are unchanged.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()
NBSP = "\u00a0"
CENT = Decimal("0.01")


@register.filter
def money(value, currency=""):
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    sign = "-" if amount < 0 else ""
    text = f"{abs(amount).quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"
    prefix = f"{currency}{NBSP}" if currency else ""
    return f"{sign}{prefix}{text}"
