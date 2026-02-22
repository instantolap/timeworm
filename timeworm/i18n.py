"""Internationalization support for TimeWorm."""
import gettext
import locale
import os
from pathlib import Path

DOMAIN = "timeworm"

# Look for locale files in package or system
_locale_dir = Path(__file__).parent.parent / "po" / "locale"
if not _locale_dir.exists():
    _locale_dir = Path("/usr/share/locale")

try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    pass

_translation = gettext.translation(DOMAIN, localedir=str(_locale_dir), fallback=True)
_ = _translation.gettext
