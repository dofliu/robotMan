"""Put the toolkit directory on ``sys.path`` -- the one place that knows where it is.

PROJECT_ASSESSMENT section 4.1 product B lives in ``backend/toolkit/`` and its
modules import each other by FLAT name.  That is not an accident to be tidied
away: it is the vendoring recipe docs/TOOLKIT_USAGE.md section 2 publishes, and
rewriting those imports to be package-relative was measured on 2026-09-19 to
break that recipe LATE (the copy imports cleanly, then raises ImportError at the
first real call).  The owner confirmed the same day that the flat imports stay.

A flat import only resolves when the directory holding the files is itself on
``sys.path``, so something has to put it there.  This module is that something.
Importing it is the whole interface::

    import toolkit_path  # noqa: F401
    import environment_lock as el

Every in-repo consumer of the toolkit goes through here, and
``backend/conftest.py`` does the same for the whole test suite, so the path
appears in exactly one place rather than once per caller.
"""

from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLKIT_DIR = os.path.join(BACKEND_DIR, "toolkit")

if TOOLKIT_DIR not in sys.path:
    sys.path.insert(0, TOOLKIT_DIR)
