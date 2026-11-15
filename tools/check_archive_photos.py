#!/usr/bin/env python3
"""Report actual qualified photographs without substituting document pages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.content_components import PhotoNotReady, StrictPhotoAlbum


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/research/photo_retrieval_v2.json")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless at least three qualified photographs cover three years")
    args = parser.parse_args(argv)
    album = StrictPhotoAlbum(ROOT, args.manifest)
    ready, missing = [], []
    for asset_id, record in album.assets.items():
        try:
            photo = album.require_photo(asset_id, record.get("scene_event_id", ""))
            ready.append({"asset_id": asset_id, "event_date": photo["event_date"],
                          "local_path": photo.get("local_path", photo.get("local_asset_path"))})
        except PhotoNotReady as error:
            missing.append({"asset_id": asset_id, "reason": str(error), "source_pages": record.get("source_pages", [])})
    years = sorted({photo["event_date"][:4] for photo in ready})
    minimum_ready = len(ready) >= 3 and len(years) >= 3
    result = {"status": "minimum_photo_assets_ready" if minimum_ready else "real_photos_not_ready",
              "qualified_photo_count": len(ready), "distinct_event_years": years,
              "minimum_assets_ready": minimum_ready, "album_rendered": False,
              "document_fallback_allowed": False, "ready": ready, "missing": missing,
              "note": "Photo availability is separate from scene bindings and final film approval."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.require_ready and not minimum_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
