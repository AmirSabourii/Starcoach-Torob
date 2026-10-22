#!/usr/bin/env python3
"""Download the Starcoach Torob CSV zip and build the local SQLite database.

Safe to re-run. Writes a temporary database and replaces the target only after
the load finishes. Does not commit the zip or the CSVs; keep them out of git.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ingest import build_database  # noqa: E402

DEFAULT_URL = "https://startech.s3.ir-central1.arvanstorage.ir/starcoach-dataset-v16-cap300-csv.zip"
CSV_NAMES = ("shops.csv", "products.csv", "offers.csv")


def download_zip(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "starcoach-torob/0.1"})
    print(f"downloading {url}", flush=True)
    with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 256)
    partial.replace(dest)
    print(f"saved {dest} ({dest.stat().st_size} bytes)", flush=True)


def extract_csvs(zip_path: Path, csv_dir: Path) -> None:
    csv_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        for name in CSV_NAMES:
            if name not in names or Path(name).name != name:
                raise FileNotFoundError(f"{name} is missing from {zip_path}")
            target = (csv_dir / name).resolve()
            if target.parent != csv_dir.resolve():
                raise ValueError(f"refusing to extract {name}")
            with archive.open(name) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            print(f"extracted {name}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the Torob CSV bundle and build SQLite.")
    parser.add_argument("--url", default=os.environ.get("DATASET_URL", DEFAULT_URL))
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", str(ROOT / "data")))
    parser.add_argument(
        "--db",
        default=os.environ.get("DATABASE_PATH", str(ROOT / "data" / "starcoach.db")),
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use CSVs already extracted under the data directory.",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    csv_dir = data_dir / "csv"
    if not args.skip_download:
        zip_path = data_dir / "dataset.zip"
        download_zip(args.url, zip_path)
        extract_csvs(zip_path, csv_dir)
    elif not all((csv_dir / name).exists() for name in CSV_NAMES):
        print("CSVs are missing. Run without --skip-download.", file=sys.stderr)
        return 1

    summary = build_database(csv_dir, Path(args.db), source_url=args.url)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("پایگاه داده ساخته شد.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
