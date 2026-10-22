"""Validated shopping engine.

The modules keep their original flat import names (tools, agent, recall, gt_lib,
build_eval_db) so the eval harness can import them unchanged. Importing this
package puts the engine directory on sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
