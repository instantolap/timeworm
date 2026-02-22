"""Locale-aware formatting for currency, dates, and numbers."""
import locale as _locale
import os
from datetime import datetime


def _get_lang():
    """Get current language code."""
    lang = os.environ.get('LANGUAGE') or os.environ.get('LC_ALL') or \
           os.environ.get('LC_MESSAGES') or os.environ.get('LANG', 'de')
    return lang.split('.')[0].split(':')[0].split('_')[0].lower()


def format_currency(amount, currency='€'):
    """Format a currency amount with the given currency symbol."""
    lang = _get_lang()

    if lang in ('en', 'ja', 'ko', 'zh'):
        if amount == 0:
            return f"{currency}0.00"
        return f"{currency}{amount:,.2f}"
    else:
        # German-style: 1.234,56 €
        if amount == 0:
            return f"0,00\u2009{currency}"
        s = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s}\u2009{currency}"


def format_rate(rate, currency='€'):
    """Format hourly rate like '125,00 €/h'."""
    lang = _get_lang()
    if lang in ('en', 'ja', 'ko', 'zh'):
        return f"{currency}{rate:,.2f}/h"
    else:
        s = f"{rate:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s}\u2009{currency}/h"


def format_hours(hours):
    """Format hours like '2,5h' or '2.5h'."""
    lang = _get_lang()
    if lang in ('en', 'ja', 'ko', 'zh'):
        return f"{hours:,.1f}h"
    else:
        return f"{hours:,.1f}h".replace(".", ",")


def format_decimal(value, decimals=2):
    """Format a decimal number."""
    lang = _get_lang()
    fmt = f"{value:,.{decimals}f}"
    if lang in ('en', 'ja', 'ko', 'zh'):
        return fmt
    else:
        return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


def format_date(dt):
    """Format a date."""
    lang = _get_lang()
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if lang in ('ja', 'ko', 'zh'):
        return dt.strftime('%Y/%m/%d')
    elif lang == 'en':
        return dt.strftime('%m/%d/%Y')
    else:
        # DE, FR, ES, PT, NL
        return dt.strftime('%d.%m.%Y')


def format_time(dt):
    """Format a time."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime('%H:%M')


def parse_date(text):
    """Parse a date string in locale-aware format. Returns datetime or raises ValueError."""
    for fmt in ('%d.%m.%Y', '%m/%d/%Y', '%Y/%m/%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {text}")
