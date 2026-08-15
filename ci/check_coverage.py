#!/usr/bin/env python3
"""Check that every top-level test directory/file added upstream is covered by our CI.

Covered paths are DERIVED from the workflow's ci matrix test_path entries
(single source of truth, no manual manifest to keep in sync). Exclusions live
in ci/test_exclusions.txt.

Usage:
    TEST_DIR=<path-to-transformers-tests> python3 ci/check_coverage.py

Exits non-zero when new uncovered top-level test items exist or covered items vanished.
New tests/models/* directories are informational only (models are selected on purpose).
"""

import os
import re
import sys

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml is required (pip install pyyaml)")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUSIONS = os.path.join(SCRIPT_DIR, "test_exclusions.txt")
WORKFLOW = os.environ.get(
    "WORKFLOW_FILE",
    os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".github", "workflows", "sync-and-ci.yml")),
)
TEST_DIR = os.environ.get("TEST_DIR", "tests")
PREFIX = "tests/"


def load_exclusions() -> set[str]:
    excluded: set[str] = set()
    with open(EXCLUSIONS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            excluded.add(line)
    return excluded


def load_covered_from_workflow() -> set[str]:
    """Extract covered test paths from the ci matrix test_path entries.

    The workflow matrix uses `include: ${{ fromJSON(...) }}`, so the parsed
    value may be an expression string instead of a list. Fall back to scanning
    the raw workflow text for every test_path inside the matrix JSON literals
    (union of debug and normal entries, so coverage never vanishes).
    """
    with open(WORKFLOW, encoding="utf-8") as f:
        text = f.read()
    covered: set[str] = set()
    data = yaml.safe_load(text)
    include = data["jobs"]["ci"]["strategy"]["matrix"]["include"]
    if isinstance(include, list):
        for entry in include:
            if isinstance(entry, dict):
                for item in entry.get("test_path", "").split():
                    covered.add(item)
    if not covered:
        for item in re.findall(r'"test_path":"([^"]+)"', text):
            covered.update(item.split())
    return covered


def to_rel(item: str) -> str:
    return item[len(PREFIX):] if item.startswith(PREFIX) else item


def main() -> int:
    covered = load_covered_from_workflow()
    excluded = load_exclusions()
    covered_rel = {to_rel(c) for c in covered}
    excluded_rel = {to_rel(e) for e in excluded}

    if not os.path.isdir(TEST_DIR):
        print(f"FAIL: test dir {TEST_DIR} not found")
        return 1

    new_uncovered: list[str] = []
    missing_covered: list[str] = []
    for entry in sorted(os.listdir(TEST_DIR)):
        if entry == "models":
            continue
        path = os.path.join(TEST_DIR, entry)
        if os.path.isdir(path):
            if entry not in covered_rel and entry not in excluded_rel:
                new_uncovered.append(PREFIX + entry + "/")
        elif entry.startswith("test_") and entry.endswith(".py"):
            if entry not in covered_rel and entry not in excluded_rel:
                new_uncovered.append(PREFIX + entry)

    for item in sorted(covered):
        rel = to_rel(item)
        if not os.path.exists(os.path.join(TEST_DIR, rel)):
            missing_covered.append(item)

    models_dir = os.path.join(TEST_DIR, "models")
    models_count = len(os.listdir(models_dir)) if os.path.isdir(models_dir) else 0
    models_covered = sum(1 for c in covered if c.startswith("tests/models/"))

    lines = ["## Transformers CI Coverage Watch", ""]
    if not new_uncovered and not missing_covered:
        lines.append(f"- 全部顶层测试项均已覆盖（tests/models 目录 {models_count} 个，当前覆盖 {models_covered} 个）")
    if new_uncovered:
        lines.append(f"### 新增未覆盖（{len(new_uncovered)} 项，需加入 workflow test_path 或 ci/test_exclusions.txt）")
        lines.extend(f"- `{item}`" for item in new_uncovered)
    if missing_covered:
        lines.append(f"### workflow 中已消失的路径（{len(missing_covered)} 项，上游可能删除/改名）")
        lines.extend(f"- `{item}`" for item in missing_covered)

    summary = "\n".join(lines)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(summary + "\n")

    return 1 if (new_uncovered or missing_covered) else 0


if __name__ == "__main__":
    sys.exit(main())
