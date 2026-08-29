#!/usr/bin/env python3
"""Fail when AGS support-library release versions drift across languages."""

from __future__ import annotations

import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def extracted(path: str, pattern: str) -> str:
    match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"could not extract version from {path}")
    return match.group(1)


def main() -> int:
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    pom = ET.parse(ROOT / "java" / "pom.xml").getroot()
    cargo_lock = tomllib.loads((ROOT / "rust/Cargo.lock").read_text(encoding="utf-8"))
    cargo_locked = next(item["version"] for item in cargo_lock["package"] if item["name"] == "agentic-graph-spec")
    package_lock = json.loads((ROOT / "typescript/package-lock.json").read_text(encoding="utf-8"))
    versions = {
        "Python export": extracted("ags/__init__.py", r'__version__\s*=\s*"([^"]+)"'),
        "TypeScript package": json.loads((ROOT / "typescript/package.json").read_text())["version"],
        "TypeScript lock": package_lock["packages"][""]["version"],
        "TypeScript export": extracted("typescript/src/index.ts", r'SUPPORT_VERSION\s*=\s*"([^"]+)"'),
        "Go export": extracted("ags.go", r'SupportVersion\s*=\s*"([^"]+)"'),
        "Rust package": tomllib.loads((ROOT / "rust/Cargo.toml").read_text())["package"]["version"],
        "Rust lock": cargo_locked,
        "Rust export": extracted("rust/src/lib.rs", r'SUPPORT_VERSION:\s*&str\s*=\s*"([^"]+)"'),
        "Java package": pom.findtext("m:version", namespaces=namespace) or "",
        "Java SCM tag": (pom.findtext("m:scm/m:tag", namespaces=namespace) or "").removeprefix("v"),
        "Java export": extracted("java/src/main/java/io/github/alexmercedcoder/ags/Ags.java", r'SUPPORT_VERSION\s*=\s*"([^"]+)"'),
    }
    failures = [f"{name}: {version} != {EXPECTED}" for name, version in versions.items() if version != EXPECTED]
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"All AGS support libraries identify release {EXPECTED}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
