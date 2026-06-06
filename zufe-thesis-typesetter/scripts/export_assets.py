#!/usr/bin/env python3
"""抽取 DOCX 媒体到 Images/word_media，并把资源证据写回 thesis.json。"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

from common import print_json, read_json, rel, safe_resolve_under, write_json


def export_assets(root: Path, docx_path: Path, thesis_path: Path) -> dict:
    output_dir = safe_resolve_under(root, "Images/word_media", "Images")
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(docx_path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/media/") or name.endswith("/"):
                continue
            target = safe_resolve_under(root, output_dir / Path(name).name, "Images")
            with archive.open(name) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted.append({"docx_media_path": name, "output": rel(target, root)})

    thesis = read_json(thesis_path)
    by_media = {entry["docx_media_path"]: entry["output"] for entry in extracted}
    for block in thesis.get("source_blocks", []):
        media_path = block.get("evidence", {}).get("docx_media_path")
        if media_path in by_media:
            block["asset_output"] = by_media[media_path]
            block["asset_status"] = "exported"
            block["render_result"] = {"path": by_media[media_path], "kind": "asset_extracted"}
    thesis.setdefault("render_log", []).append(
        {
            "step": "export_assets",
            "status": "completed",
            "outputs": extracted,
        }
    )
    write_json(thesis_path, thesis)
    return {
        "flow": "B",
        "step": "export_assets",
        "status": "passed",
        "outputs": extracted,
        "note": "图片在章节 TeX 中的位置仍需要确认目标槽位。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--docx", default="workspace/input/thesis.docx")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    docx_path = (root / args.docx).resolve() if not Path(args.docx).is_absolute() else Path(args.docx).resolve()
    thesis_path = (root / args.thesis_json).resolve() if not Path(args.thesis_json).is_absolute() else Path(args.thesis_json).resolve()
    result = export_assets(root, docx_path, thesis_path)
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
