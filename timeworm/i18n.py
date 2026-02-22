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

# Determine language: LANGUAGE env var takes priority, then system locale
_languages = None
_lang_env = os.environ.get('LANGUAGE') or os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG', '')
if _lang_env:
    _languages = [_lang_env.split('.')[0].split(':')[0]]

try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    pass

_translation = gettext.translation(DOMAIN, localedir=str(_locale_dir), languages=_languages, fallback=True)
_ = _translation.gettext


def setup_i18n():
    """Initialize i18n (called from app.py). Already set up on import, this is a no-op."""
    pass
