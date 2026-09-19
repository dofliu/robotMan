"""Put the archive directory on ``sys.path`` -- the one place that knows where it is.

PROJECT_ASSESSMENT section 4.2 recommends archiving the closed research lines:
the v7 pilot and selection contracts, the second case, the seed-variance line,
the two tracked-lineage contracts and the R0 probe.  They moved to
``backend/archive/`` on 2026-09-19 and, like the toolkit, they import by FLAT
module name, so the directory has to reach ``sys.path`` before they resolve.

Archived does NOT mean unchecked.  The owner chose on 2026-09-19 that the 434
tests belonging to these lines keep running, because three files that were NOT
archived -- ``config_schema.py``, ``motion_tasks.py`` and ``rl/eval_policy.py``
-- have their bytes pinned by tests that were, and dropping those tests would
have stopped checking live files.  That is why this module exists rather than
the archive simply falling out of collection.
"""

from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(BACKEND_DIR, "archive")

if ARCHIVE_DIR not in sys.path:
    sys.path.insert(0, ARCHIVE_DIR)
