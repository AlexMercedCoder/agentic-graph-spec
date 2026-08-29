from __future__ import annotations

from pathlib import Path

import pytest

from ags import canonical_json, graph_digest, validate_path

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        ({"b": 2, "a": 1}, b'{"a":1,"b":2}'),
        ({"n": 1.0}, b'{"n":1}'),
        ({"s": "é", "z": -0.0}, '{"s":"é","z":0}'.encode()),
    ],
)
def test_jcs_vectors(value: object, canonical: bytes) -> None:
    assert canonical_json(value) == canonical


def test_digest_is_stable_across_key_order() -> None:
    assert graph_digest({"b": 2, "a": 1}) == graph_digest({"a": 1, "b": 2})


def test_public_validator_api() -> None:
    report = validate_path(ROOT / "examples" / "minimal.agraph.yaml")
    assert not report.errors


@pytest.mark.parametrize("path", sorted((ROOT / "conformance" / "invalid").glob("*.agraph.yaml")))
def test_shared_invalid_corpus(path: Path) -> None:
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("# EXPECT: "), f"{path.name} has no EXPECT header"
    expected = header.removeprefix("# EXPECT: ").strip()
    report = validate_path(path)
    assert any(f.code == expected and f.severity == "error" for f in report.findings), (
        path.name,
        expected,
        report.findings,
    )


def test_yaml_uses_1_2_boolean_rules(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.agraph.yaml").read_text(encoding="utf-8")
    source = source.replace("title: Minimal graph", "title: yes")
    path = tmp_path / "yaml12.agraph.yaml"
    path.write_text(source, encoding="utf-8")
    assert not validate_path(path).errors


def test_unsupported_minor_fails_closed(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.agraph.yaml").read_text(encoding="utf-8")
    source = source.replace('ags_version: "1.0"', 'ags_version: "1.1"')
    path = tmp_path / "future.agraph.yaml"
    path.write_text(source, encoding="utf-8")
    report = validate_path(path)
    assert any(f.code == "AG002" and f.severity == "error" for f in report.findings)


def test_every_closed_schema_object_accepts_extensions() -> None:
    import json

    for name in ("agentic-graph-1.0.schema.json", "agentic-graph-run-1.0.schema.json"):
        schema = json.loads((ROOT / "schema" / name).read_text(encoding="utf-8"))
        missing: list[str] = []

        def walk(value: object, pointer: str = "$") -> None:
            if isinstance(value, dict):
                if value.get("type") == "object" and value.get("additionalProperties") is False:
                    if "^x-" not in value.get("patternProperties", {}):
                        missing.append(pointer)
                for key, child in value.items():
                    walk(child, f"{pointer}/{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{pointer}/{index}")

        walk(schema)
        assert missing == []
