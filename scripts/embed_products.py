#!/usr/bin/env python3
"""Generate the product embedding cache once. Requires BOXAPI_API_KEY.

Writes DATA_DIR/emb_cache/, product_emb.f16.npy and product_emb_ids.json.
Those files are gitignored. Do not commit them.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "backend" / "app" / "engine" / "embed_products.py"
sys.exit(runpy.run_path(str(TARGET), run_name="__main__"))
