"""Import bootstrap for the whole backend test tree.

Every test file here imports project modules by flat name, and this repository
has no packaging metadata to arrange that, so each one used to insert
``backend/`` into ``sys.path`` itself.  Those lines still work and are left
alone.  What they cannot do is find ``backend/toolkit/``, which moved out from
under them when PROJECT_ASSESSMENT section 4.1 product B was split off.

pytest loads this file before collecting anything below it, so putting the two
roots on the path here means no test file needed editing for the move.  The
toolkit path itself is not spelled out twice: it comes from ``toolkit_path``,
the single module that owns it.
"""

from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import toolkit_path  # noqa: E402,F401  the one place that knows where the toolkit is
