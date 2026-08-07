#!/usr/bin/env python3
"""Check that every top-level test directory/file added upstream is covered by our CI.

Usage:
    TEST_DIR=<path-to-transformers-tests> python3 ci/check_coverage.py

Exits non-zero when new uncovered top-level test items exist or covered items vanished.
New tests/models/* directories are informational only (models are selected on purpose).
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(SCRIPT_DIR, "covered_tests.txt")
TEST_DIR = os.environ.get("TEST_DIR", "tests")
PREFIX = "tests/"


def load_manifest() -> tuple[set[str], set[str]]:
    covered: set[str] = set()
    excluded: set[str] = set()
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                excluded.add(line[1:])
            else:
                covered.add(line)
    return covered, excluded


def to_rel(item: str) -> str:
    return item[len(PREFIX):] if item.startswith(PREFIX) else item


def main() -> int:
    covered, excluded = load_manifest()
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
        lines.append(f"### 新增未覆盖（{len(new_uncovered)} 项，需加入 ci/covered_tests.txt 或显式排除）")
        lines.extend(f"- `{item}`" for item in new_uncovered)
    if missing_covered:
        lines.append(f"### 清单中已消失的路径（{len(missing_covered)} 项，上游可能删除/改名）")
        lines.extend(f"- `{item}`" for item in missing_covered)

    summary = "\n".join(lines)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(summary + "\n")

    return 1 if (new_uncovered or missing_covered) else 0


if __name__ == "__main__":
    sys.exit(main())
