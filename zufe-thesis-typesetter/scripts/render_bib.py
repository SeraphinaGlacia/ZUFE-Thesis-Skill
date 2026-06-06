#!/usr/bin/env python3
"""渲染已确认 BibTeX 条目，不编造参考文献。"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import now_iso, print_json, read_json, rel, write_json


def render(root: Path, thesis_path: Path, input_bib: Path | None) -> dict:
    thesis = read_json(thesis_path, default={}) if thesis_path.exists() else {}
    entries = []
    warnings = []

    if input_bib and input_bib.exists():
        entries.append(input_bib.read_text(encoding="utf-8"))

    for reference in thesis.get("references", []):
        bibtex = reference.get("bibtex")
        if bibtex:
            entries.append(str(bibtex).strip())
        elif reference.get("raw"):
            warnings.append(f"原始参考文献未转换为 BibTeX：{reference.get('raw')}")

    for block in thesis.get("source_blocks", []):
        if block.get("target_slot") != "Reference.bib":
            continue
        bibtex = block.get("bibtex")
        if bibtex:
            entries.append(str(bibtex).strip())
            block["status"] = "rendered"
            block["render_result"] = {"path": "Reference.bib", "kind": "bibtex"}
        elif block.get("text") or block.get("summary"):
            block["status"] = "needs_confirmation"
            warnings.append(f"{block.get('id')} 像参考文献，但没有已确认 BibTeX。")

    target = root / "Reference.bib"
    if entries:
        target.write_text("\n\n".join(entries).strip() + "\n", encoding="utf-8")
    else:
        target.write_text("% No confirmed BibTeX entries were provided.\n", encoding="utf-8")
        warnings.append("Reference.bib 没有已确认条目。")

    if thesis_path.exists():
        thesis.setdefault("warnings", []).extend(warnings)
        thesis.setdefault("render_log", []).append(
            {
                "step": "render_bib",
                "status": "completed_with_warnings" if warnings else "completed",
                "target": rel(target, root),
                "rendered_at": now_iso(),
                "warnings": warnings,
            }
        )
        write_json(thesis_path, thesis)

    return {
        "flow": "B",
        "step": "render_bib",
        "status": "needs_confirmation" if warnings else "passed",
        "target": rel(target, root),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--thesis-json", default="workspace/intermediate/thesis.json")
    parser.add_argument("--input-bib", default="workspace/input/references.bib")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    thesis_path = (root / args.thesis_json).resolve() if not Path(args.thesis_json).is_absolute() else Path(args.thesis_json).resolve()
    input_bib = (root / args.input_bib).resolve() if not Path(args.input_bib).is_absolute() else Path(args.input_bib).resolve()
    result = render(root, thesis_path, input_bib)
    print_json(result)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
