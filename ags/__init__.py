"""Public support API for Agentic Graph Specification 1.0."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

import rfc8785

__version__ = "1.0.4"
AGS_VERSION = "1.0"


def canonical_json(value: Any) -> bytes:
    """Serialize a JSON value using RFC 8785 JCS."""
    return rfc8785.dumps(value)


def graph_digest(document: dict[str, Any]) -> str:
    """Return the normative ``sha256-<base64>`` AGS digest."""
    digest = hashlib.sha256(canonical_json(document)).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


@lru_cache(maxsize=1)
def reference_validator() -> ModuleType:
    """Load the bundled reference validator without making it normative API."""
    package_root = Path(__file__).resolve().parent
    source = package_root / "reference_validator.py"
    if not source.exists():
        source = package_root.parent / "tools" / "validate_agraph.py"
    spec = importlib.util.spec_from_file_location("ags.reference_validator", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the AGS reference validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.SCHEMA_PATH = package_root / "schema" / "agentic-graph-1.0.schema.json"
    if not module.SCHEMA_PATH.exists():
        module.SCHEMA_PATH = package_root.parent / "schema" / "agentic-graph-1.0.schema.json"
    return module


def validate_path(path: str | Path) -> Any:
    """Validate one graph and return the reference validator's Report object."""
    module = reference_validator()
    target = Path(path)
    report = module.Report(target)
    document = module.load_document(target, report)
    if document is not None:
        module.Validator(document, report).run()
    return report


def main() -> int:
    """Run the bundled ``ags-validate`` command."""
    return int(reference_validator().main())


__all__ = ["AGS_VERSION", "__version__", "canonical_json", "graph_digest", "validate_path"]
