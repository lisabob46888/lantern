"""Vendored Vibe-Research data layer (MIT, see LICENSE-vibe-research).

The modules import each other as top-level names (`import astock`), so this
package puts its own directory on sys.path. Import them as:

    import app.vendor  # noqa: F401  (path setup)
    import astock, gstock, askill, gskill, market, newsradar
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app.config import settings as _settings  # noqa: E402

import gskill as _gskill  # noqa: E402

if _settings.sec_contact:
    _gskill.SEC_CONTACT = _settings.sec_contact
    _gskill.SEC_HEADERS = {"User-Agent": _settings.sec_contact}
