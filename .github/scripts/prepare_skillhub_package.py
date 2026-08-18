#!/usr/bin/env python3
"""Build a validated, SkillHub-specific copy of a canonical Agent Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import NoReturn

EXCLUDED_DIRECTORIES = {".git", ".idea", ".vscode", "__pycache__", "node_modules"}
EXCLUDED_FILES = {".DS_Store", "Thumbs.db"}
MAX_FILE_COUNT = 200
MAX_TOTAL_BYTES = 10 * 1024 * 1024
RESERVED_FIELDS = {
    "displayName",
    "homepage",
    "license",
    "slug",
    "summary",
    "tags",
    "version",
}
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def fail(message: str) -> NoReturn:
    raise SystemExit(f"error: {message}")


def decode_scalar(raw_value: str, *, field: str) -> str:
    value = raw_value.strip()
    if not value:
        fail(f"{field} must be a non-empty single-line scalar")

    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            fail(f"{field} contains an invalid double-quoted scalar: {exc}")
        if not isinstance(decoded, str):
            fail(f"{field} must be a string")
        value = decoded
    elif value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            fail(f"{field} contains an invalid single-quoted scalar")
        value = value[1:-1].replace("''", "'")
    elif value[0] in "[{|>":
        fail(f"{field} must use a simple single-line scalar")
    else:
        value = value.split(" #", maxsplit=1)[0].rstrip()

    if not value or any(character in value for character in "\r\n\0"):
        fail(f"{field} must be a non-empty single-line scalar")
    return value


def read_frontmatter(skill_md: Path) -> tuple[list[str], int, dict[str, str]]:
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read {skill_md}: {exc}")

    if not lines or lines[0].strip() != "---":
        fail(f"{skill_md} must start with YAML frontmatter")

    end_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        -1,
    )
    if end_index < 0:
        fail(f"{skill_md} has no closing frontmatter marker")

    fields: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines[1:end_index], start=2):
        line = raw_line.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() or ":" not in line:
            fail(f"{skill_md}:{line_number} is not a simple top-level field")
        key, raw_value = line.split(":", maxsplit=1)
        key = key.strip()
        if not key or key in fields:
            fail(f"{skill_md}:{line_number} contains an empty or duplicate field")
        fields[key] = raw_value.strip()

    return lines, end_index, fields


def read_interface_fields(openai_yaml: Path) -> dict[str, str]:
    try:
        lines = openai_yaml.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read {openai_yaml}: {exc}")

    try:
        interface_index = next(
            index
            for index, line in enumerate(lines)
            if line.strip() == "interface:" and not line[:1].isspace()
        )
    except StopIteration:
        fail(f"{openai_yaml} has no top-level interface mapping")

    fields: dict[str, str] = {}
    for raw_line in lines[interface_index + 1 :]:
        if raw_line.strip() and not raw_line[:1].isspace():
            break
        match = re.fullmatch(r" {2}([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*", raw_line)
        if not match:
            continue
        key, raw_value = match.groups()
        if key in fields:
            fail(f"{openai_yaml} contains duplicate interface.{key}")
        fields[key] = decode_scalar(raw_value, field=f"interface.{key}")

    for required in ("display_name", "short_description"):
        if required not in fields:
            fail(f"{openai_yaml} has no interface.{required}")
    return fields


def validate_icon_references(source: Path, interface_fields: dict[str, str]) -> None:
    for field in ("icon_small", "icon_large"):
        raw_path = interface_fields.get(field)
        if raw_path is None:
            continue
        relative_path = PurePosixPath(raw_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            fail(f"interface.{field} must point to a file inside the Skill package")
        target = source.joinpath(*relative_path.parts)
        if not target.is_file():
            fail(f"interface.{field} points to a missing file: {raw_path}")


def validate_source_tree(source: Path) -> None:
    for root, directory_names, file_names in os.walk(source, followlinks=False):
        root_path = Path(root)
        directory_names[:] = [name for name in directory_names if name not in EXCLUDED_DIRECTORIES]
        for name in directory_names + file_names:
            path = root_path / name
            if path.is_symlink():
                fail(
                    f"symlinks are not allowed in the publishing source: {path.relative_to(source)}"
                )
        for name in file_names:
            path = root_path / name
            if not path.is_file():
                fail(f"non-regular files are not allowed: {path.relative_to(source)}")


def copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in EXCLUDED_DIRECTORIES or name in EXCLUDED_FILES or name.endswith(".pyc")
    }


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def inject_skillhub_frontmatter(
    skill_md: Path,
    *,
    slug: str,
    version: str,
    display_name: str,
    summary: str,
    license_name: str,
    homepage: str,
    tags: list[str],
) -> None:
    lines, end_index, fields = read_frontmatter(skill_md)
    conflicts = sorted(RESERVED_FIELDS.intersection(fields))
    if conflicts:
        fail(f"canonical SKILL.md already defines SkillHub fields: {', '.join(conflicts)}")

    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    additions = [
        f"slug: {yaml_string(slug)}{newline}",
        f"version: {yaml_string(version)}{newline}",
        f"displayName: {yaml_string(display_name)}{newline}",
        f"summary: {yaml_string(summary)}{newline}",
        f"license: {yaml_string(license_name)}{newline}",
        f"homepage: {yaml_string(homepage)}{newline}",
        f"tags: [{', '.join(yaml_string(tag) for tag in tags)}]{newline}",
    ]
    try:
        skill_md.write_text(
            "".join(lines[:end_index] + additions + lines[end_index:]), encoding="utf-8"
        )
    except OSError as exc:
        fail(f"cannot update staged SKILL.md: {exc}")


def inventory_tree(root: Path) -> tuple[int, int, str]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    total_bytes = sum(path.stat().st_size for path in files)
    if len(files) > MAX_FILE_COUNT:
        fail(f"package has {len(files)} files; limit is {MAX_FILE_COUNT}")
    if total_bytes > MAX_TOTAL_BYTES:
        fail(f"package is {total_bytes} bytes; limit is {MAX_TOTAL_BYTES}")

    digest = hashlib.sha256()
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return len(files), total_bytes, digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a temporary SkillHub publishing package without changing the canonical Skill."
    )
    parser.add_argument("source", type=Path, help="Canonical Skill directory")
    parser.add_argument("destination", type=Path, help="New staging directory")
    parser.add_argument("--version", required=True, help="Release version without a leading v")
    parser.add_argument(
        "--license", dest="license_name", required=True, help="SPDX license identifier"
    )
    parser.add_argument("--homepage", required=True, help="Public project homepage")
    parser.add_argument(
        "--tag", dest="tags", action="append", required=True, help="SkillHub search tag"
    )
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()

    if not source.is_dir():
        fail(f"source is not a directory: {source}")
    if destination.exists():
        fail(f"destination already exists: {destination}")
    if source == destination or source in destination.parents:
        fail("destination must not be inside the source directory")
    if not SEMVER_PATTERN.fullmatch(args.version):
        fail(f"version is not valid SemVer: {args.version}")
    if not args.license_name.strip() or not args.homepage.strip():
        fail("license and homepage must be non-empty")

    tags = list(dict.fromkeys(tag.strip() for tag in args.tags if tag.strip()))
    if not tags:
        fail("at least one non-empty tag is required")

    skill_md = source / "SKILL.md"
    openai_yaml = source / "agents" / "openai.yaml"
    _, _, canonical_fields = read_frontmatter(skill_md)
    if "name" not in canonical_fields:
        fail(f"{skill_md} has no name field")
    slug = decode_scalar(canonical_fields["name"], field="name")
    if not SLUG_PATTERN.fullmatch(slug) or not 2 <= len(slug) <= 128:
        fail(f"name cannot be used as a SkillHub slug: {slug}")

    interface_fields = read_interface_fields(openai_yaml)
    validate_icon_references(source, interface_fields)
    validate_source_tree(source)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=copy_ignore)
    inject_skillhub_frontmatter(
        destination / "SKILL.md",
        slug=slug,
        version=args.version,
        display_name=interface_fields["display_name"],
        summary=interface_fields["short_description"],
        license_name=args.license_name.strip(),
        homepage=args.homepage.strip(),
        tags=tags,
    )

    file_count, total_bytes, tree_sha256 = inventory_tree(destination)
    report = {
        "destination": str(destination),
        "displayName": interface_fields["display_name"],
        "fileCount": file_count,
        "slug": slug,
        "totalBytes": total_bytes,
        "treeSha256": tree_sha256,
        "version": args.version,
    }
    rendered_report = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered_report, encoding="utf-8")
    sys.stdout.write(rendered_report)


if __name__ == "__main__":
    main()
