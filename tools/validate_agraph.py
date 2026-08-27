#!/usr/bin/env python3
"""Reference validator for Agentic Graph Specification (AGS) 1.0 documents.

Implements all three validation layers described in SPEC.md section 18:

  Layer 1  structural  -- JSON Schema validation                 (AG0xx)
  Layer 2  referential -- cross-reference and topology checks     (AG1xx)
  Layer 3  semantic    -- AGX expression and dataflow analysis    (AG2xx)
  advisory -- quality warnings that never block execution         (AG9xx)

This is a reference implementation, not a normative one: SPEC.md is normative.
It exists so that spec, schema and examples can be checked against each other.

Usage:
    python3 tools/validate_agraph.py examples/*.agraph.yaml
    python3 tools/validate_agraph.py --strict path/to/graph.agraph.json
    python3 tools/validate_agraph.py --quiet examples/    # exit code only

Requires: jsonschema, PyYAML.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "agentic-graph-1.0.schema.json"

SUPPORTED_MAJOR = 1
SUPPORTED_MINOR = 0

TIER_LEVEL = {"minimal": 1, "standard": 2, "advanced": 3, "frontier": 4}


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    code: str
    severity: str  # "error" | "warning"
    message: str
    pointer: str = ""

    def __str__(self) -> str:
        loc = f" at {self.pointer}" if self.pointer else ""
        return f"[{self.severity.upper():7}] {self.code}: {self.message}{loc}"


@dataclass
class Report:
    path: Path
    findings: list[Finding] = field(default_factory=list)

    def add(self, code: str, severity: str, message: str, pointer: str = "") -> None:
        self.findings.append(Finding(code, severity, message, pointer))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


# --------------------------------------------------------------------------- #
# AGX expression parser
# --------------------------------------------------------------------------- #

FUNCTIONS = {
    "len": 1, "count": 1, "contains": 2, "startswith": 2, "endswith": 2,
    "lower": 1, "upper": 1, "trim": 1, "matches": 2, "split": 2, "join": 2,
    "int": 1, "float": 1, "bool": 1, "str": 1, "json": 1,
    "get": (2, 3), "default": 2, "any": 1, "all": 1,
    "succeeded": 1, "failed": 1, "skipped": 1, "output": 2,
}

TOKEN_RE = re.compile(
    r"""
    \s*(?:
      (?P<number>-?\d+\.\d+|-?\d+)
    | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
    | (?P<op>&&|\|\||==|!=|<=|>=|[-+*/%<>!()\[\],.])
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)

KEYWORDS = {"true", "false", "null", "and", "or", "not", "in"}


class AgxError(ValueError):
    pass


@dataclass
class Reference:
    """A dotted name reference found in an expression, e.g. nodes.build.outputs.log."""

    parts: list[str]

    @property
    def root(self) -> str:
        return self.parts[0]

    def __str__(self) -> str:
        return ".".join(self.parts)


class AgxParser:
    """Recursive-descent parser. Validates syntax and collects references."""

    def __init__(self, text: str) -> None:
        self.tokens = self._tokenize(text)
        self.pos = 0
        self.references: list[Reference] = []
        self.calls: list[tuple[str, int]] = []

    @staticmethod
    def _tokenize(text: str) -> list[tuple[str, str]]:
        tokens: list[tuple[str, str]] = []
        index = 0
        while index < len(text):
            if text[index].isspace():
                index += 1
                continue
            match = TOKEN_RE.match(text, index)
            if not match or match.end() == index:
                raise AgxError(f"unexpected character {text[index]!r} at offset {index}")
            index = match.end()
            for kind in ("number", "string", "op", "name"):
                value = match.group(kind)
                if value is not None:
                    tokens.append((kind, value))
                    break
        return tokens

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        if self.pos >= len(self.tokens):
            raise AgxError("unexpected end of expression")
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect_op(self, op: str) -> None:
        token = self.take()
        if token != ("op", op):
            raise AgxError(f"expected {op!r}, found {token[1]!r}")

    def parse(self) -> None:
        self.parse_or()
        if self.pos != len(self.tokens):
            raise AgxError(f"trailing input at token {self.tokens[self.pos][1]!r}")

    def parse_or(self) -> None:
        self.parse_and()
        while self._match_op("||") or self._match_name("or"):
            self.parse_and()

    def parse_and(self) -> None:
        self.parse_in()
        while self._match_op("&&") or self._match_name("and"):
            self.parse_in()

    def parse_in(self) -> None:
        self.parse_equality()
        while self._match_name("in"):
            self.parse_equality()

    def parse_equality(self) -> None:
        self.parse_comparison()
        while self._match_op("==") or self._match_op("!="):
            self.parse_comparison()

    def parse_comparison(self) -> None:
        self.parse_additive()
        while any(self._match_op(op) for op in ("<=", ">=", "<", ">")):
            self.parse_additive()

    def parse_additive(self) -> None:
        self.parse_multiplicative()
        while self._match_op("+") or self._match_op("-"):
            self.parse_multiplicative()

    def parse_multiplicative(self) -> None:
        self.parse_unary()
        while any(self._match_op(op) for op in ("*", "/", "%")):
            self.parse_unary()

    def parse_unary(self) -> None:
        if self._match_op("!") or self._match_op("-") or self._match_name("not"):
            self.parse_unary()
            return
        self.parse_primary()

    def parse_primary(self) -> None:
        token = self.peek()
        if token is None:
            raise AgxError("unexpected end of expression")
        kind, value = token
        if kind in ("number", "string"):
            self.take()
            return
        if kind == "op" and value == "(":
            self.take()
            self.parse_or()
            self.expect_op(")")
            return
        if kind == "op" and value == "[":
            self.take()
            if self.peek() != ("op", "]"):
                self.parse_or()
                while self._match_op(","):
                    self.parse_or()
            self.expect_op("]")
            return
        if kind == "name":
            self.take()
            if value in ("true", "false", "null"):
                return
            if value in ("and", "or", "not", "in"):
                raise AgxError(f"unexpected keyword {value!r}")
            nxt = self.peek()
            if nxt == ("op", "("):
                self.take()
                arity = 0
                if self.peek() != ("op", ")"):
                    self.parse_or()
                    arity = 1
                    while self._match_op(","):
                        self.parse_or()
                        arity += 1
                self.expect_op(")")
                self.calls.append((value, arity))
                return
            parts = [value]
            while self.peek() == ("op", "."):
                self.take()
                seg = self.take()
                if seg[0] != "name":
                    raise AgxError(f"expected identifier after '.', found {seg[1]!r}")
                parts.append(seg[1])
            self.references.append(Reference(parts))
            return
        raise AgxError(f"unexpected token {value!r}")

    def _match_op(self, op: str) -> bool:
        if self.peek() == ("op", op):
            self.take()
            return True
        return False

    def _match_name(self, name: str) -> bool:
        if self.peek() == ("name", name):
            self.take()
            return True
        return False


def parse_expression(text: str) -> AgxParser:
    parser = AgxParser(text)
    parser.parse()
    return parser


TEMPLATE_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)


# --------------------------------------------------------------------------- #
# Scope model
# --------------------------------------------------------------------------- #


@dataclass
class Scope:
    """One node namespace: the root graph, or a loop/map/subgraph fragment."""

    name: str
    pointer: str
    nodes: dict[str, Any]
    edges: list[dict[str, Any]]
    entrypoints: list[str]
    param_names: set[str]
    outputs_spec: dict[str, Any] = field(default_factory=dict)
    extra_bindings: set[str] = field(default_factory=set)
    is_root: bool = False

    effective_edges: list[tuple[str, str, str, str | None]] = field(default_factory=list)
    predecessors: dict[str, set[str]] = field(default_factory=dict)


def implicit_outputs(node: dict[str, Any]) -> set[str]:
    """Output names a node exposes beyond its declared `outputs` map."""
    names: set[str] = set()
    node_type = node.get("type", "task")
    if node_type in ("decision", "gate"):
        names.add("decision")
    if node_type == "gate":
        gate = node.get("gate") or {}
        names.update((gate.get("collect") or {}).keys())
        if gate.get("mode") == "review":
            # review mode writes edited values back under the presented names;
            # they must still be declared, so nothing implicit is added here.
            pass
    if node_type == "loop":
        names.update(((node.get("loop") or {}).get("collect") or {}).keys())
    if node_type == "map":
        names.update(((node.get("map") or {}).get("collect") or {}).keys())
    if node_type == "subgraph":
        names.update(((node.get("subgraph") or {}).get("outputs_from") or {}).keys())
    return names


def declared_outputs(node: dict[str, Any]) -> set[str]:
    return set((node.get("outputs") or {}).keys()) | implicit_outputs(node)


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


class _NoDuplicateLoader(yaml.SafeLoader if yaml else object):  # type: ignore[misc]
    pass


def _no_duplicates(loader, node, deep=False):  # type: ignore[no-untyped-def]
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"duplicate key {key!r}", key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


if yaml is not None:
    # PyYAML defaults to YAML 1.1 booleans. AGS requires YAML 1.2 core
    # semantics, where yes/no/on/off remain strings.
    for _first in "yYnNoO":
        _NoDuplicateLoader.yaml_implicit_resolvers.pop(_first, None)
    _NoDuplicateLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates
    )


def load_document(path: Path, report: Report) -> Any | None:
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix in (".yaml", ".yml"):
            if yaml is None:
                report.add("AG001", "error", "PyYAML is not installed; cannot read YAML.")
                return None
            return yaml.load(text, Loader=_NoDuplicateLoader)
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a document error
        message = str(exc).replace("\n", " ")
        code = "AG005" if "duplicate key" in message else "AG001"
        report.add(code, "error", f"parse error: {message}")
        return None


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #


class Validator:
    def __init__(self, document: Any, report: Report) -> None:
        self.doc = document
        self.report = report
        self.scopes: list[Scope] = []
        self.scopes_by_pointer: dict[str, Scope] = {}
        self.graph_params: set[str] = set()
        self.context_names: set[str] = set()
        self.attachment_names: set[str] = set()
        self.secret_names: set[str] = set()
        self.read_outputs: set[tuple[str, str]] = set()

    # -- layer 1 ---------------------------------------------------------- #

    @staticmethod
    def _schema_diagnostic(error: Any) -> str:
        """Map structural failures that have dedicated catalogue codes."""
        path = list(error.absolute_path)
        if error.validator == "additionalProperties":
            return "AG003"
        if error.validator == "enum":
            return "AG004"
        if len(path) >= 2 and path[-2:] == ["intelligence", "tier"]:
            return "AG004"
        if "edges" in path and error.validator in {"not", "allOf"}:
            return "AG103"
        if "inputs" in path and error.validator in {"oneOf", "maxProperties"}:
            return "AG104"
        return "AG001"

    def check_schema(self) -> bool:
        if jsonschema is None:
            self.report.add("AG001", "warning", "jsonschema is not installed; skipping layer 1.")
            return True
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        ok = True
        for error in sorted(validator.iter_errors(self.doc), key=lambda e: list(e.absolute_path)):
            ok = False
            pointer = "/" + "/".join(str(p) for p in error.absolute_path)
            self.report.add(self._schema_diagnostic(error), "error", error.message, pointer)
        return ok

    def check_version(self) -> None:
        raw = str(self.doc.get("ags_version", ""))
        match = re.fullmatch(r"(\d+)\.(\d+)", raw)
        if not match:
            self.report.add("AG002", "error", f"unparsable ags_version {raw!r}")
            return
        major, minor = int(match.group(1)), int(match.group(2))
        if major != SUPPORTED_MAJOR:
            self.report.add("AG002", "error", f"unsupported major spec version {major}")
        elif minor > SUPPORTED_MINOR:
            self.report.add(
                "AG002", "error",
                f"document targets 1.{minor}, validator knows 1.{SUPPORTED_MINOR}; unsupported versions fail closed",
            )

    # -- scope construction ------------------------------------------------ #

    def build_scopes(self) -> None:
        self.graph_params = set((self.doc.get("params") or {}).keys())
        self.context_names = set((self.doc.get("context") or {}).keys())
        self.attachment_names = {a["name"] for a in (self.doc.get("attachments") or []) if "name" in a}
        self.secret_names = {s["name"] for s in (self.doc.get("secrets") or []) if "name" in s}

        root = Scope(
            name="<root>",
            pointer="",
            nodes=self.doc.get("nodes") or {},
            edges=list(self.doc.get("edges") or []),
            entrypoints=list(self.doc.get("entrypoints") or []),
            param_names=self.graph_params,
            outputs_spec=dict(self.doc.get("outputs") or {}),
            is_root=True,
        )
        self.scopes.append(root)
        self._collect_fragments(root)

        for name, fragment in (self.doc.get("subgraphs") or {}).items():
            self._add_fragment(f"subgraphs.{name}", f"/subgraphs/{name}", fragment, set())

    def _collect_fragments(self, scope: Scope) -> None:
        for node_id, node in scope.nodes.items():
            base = f"{scope.pointer}/nodes/{node_id}"
            node_type = node.get("type", "task")
            if node_type == "loop":
                block = node.get("loop") or {}
                extra = {"loop"}
                if "body" in block:
                    self._add_fragment(f"{scope.name}:{node_id}.loop", f"{base}/loop/body", block["body"], extra)
            elif node_type == "map":
                block = node.get("map") or {}
                extra = {block.get("as", "item"), block.get("index_as", "index")}
                if "body" in block:
                    self._add_fragment(f"{scope.name}:{node_id}.map", f"{base}/map/body", block["body"], extra)
            elif node_type == "subgraph":
                block = node.get("subgraph") or {}
                if "inline" in block:
                    self._add_fragment(f"{scope.name}:{node_id}.subgraph", f"{base}/subgraph/inline", block["inline"], set())

    def _add_fragment(self, name: str, pointer: str, fragment: Any, extra: set[str]) -> None:
        if not isinstance(fragment, dict):
            return
        params = set((fragment.get("params") or {}).keys())
        scope = Scope(
            name=name,
            pointer=pointer,
            nodes=fragment.get("nodes") or {},
            edges=list(fragment.get("edges") or []),
            entrypoints=list(fragment.get("entrypoints") or []),
            param_names=params or self.graph_params,
            outputs_spec=dict(fragment.get("outputs") or {}),
            extra_bindings=extra,
        )
        self.scopes.append(scope)
        self.scopes_by_pointer[pointer] = scope
        self._collect_fragments(scope)

    # -- layer 2 ----------------------------------------------------------- #

    def check_topology(self) -> None:
        self._check_named_fragment_recursion()
        for scope in self.scopes:
            self._check_scope_topology(scope)

    def _check_named_fragment_recursion(self) -> None:
        fragments = self.doc.get("subgraphs") or {}
        dependencies: dict[str, set[str]] = {name: set() for name in fragments}
        for name, fragment in fragments.items():
            for node in (fragment.get("nodes") or {}).values():
                for block_name in ("loop", "map", "subgraph"):
                    use = (node.get(block_name) or {}).get("use")
                    if isinstance(use, str):
                        dependencies[name].add(use)

        visited: set[str] = set()
        active: list[str] = []

        def visit(name: str) -> None:
            if name in active:
                cycle = active[active.index(name):] + [name]
                self.report.add(
                    "AG131", "error", "recursive subgraph reference: " + " -> ".join(cycle),
                    f"/subgraphs/{name}",
                )
                return
            if name in visited or name not in dependencies:
                return
            active.append(name)
            for dependency in sorted(dependencies[name]):
                visit(dependency)
            active.pop()
            visited.add(name)

        for name in sorted(dependencies):
            visit(name)

    def _check_scope_topology(self, scope: Scope) -> None:
        ids = set(scope.nodes)
        edges: list[tuple[str, str, str, str | None]] = []

        for node_id, node in scope.nodes.items():
            for dep in node.get("depends_on") or []:
                if dep not in ids:
                    self.report.add("AG114", "error", f"depends_on references unknown node {dep!r}",
                                    f"{scope.pointer}/nodes/{node_id}")
                    continue
                edges.append((dep, node_id, "sequence", None))

        for index, edge in enumerate(scope.edges):
            src, dst = edge.get("from"), edge.get("to")
            pointer = f"{scope.pointer}/edges/{index}"
            missing = [n for n in (src, dst) if n not in ids]
            if missing:
                self.report.add("AG113", "error", f"edge references unknown node(s) {missing}", pointer)
                continue
            edges.append((src, dst, edge.get("kind", "sequence"), edge.get("when")))

        deduped = list(dict.fromkeys(edges))
        scope.effective_edges = deduped

        pairs_from_depends = {(s, d) for (s, d, k, w) in edges if k == "sequence" and w is None}
        explicit_pairs = [(e.get("from"), e.get("to")) for e in scope.edges]
        for node_id, node in scope.nodes.items():
            for dep in node.get("depends_on") or []:
                if (dep, node_id) in explicit_pairs:
                    self.report.add("AG901", "warning",
                                    f"{dep} -> {node_id} declared by both depends_on and an explicit edge",
                                    f"{scope.pointer}/nodes/{node_id}")
        del pairs_from_depends

        # entrypoints
        incoming: dict[str, list[tuple[str, str, str, str | None]]] = {n: [] for n in ids}
        outgoing: dict[str, list[str]] = {n: [] for n in ids}
        for src, dst, kind, when in deduped:
            incoming[dst].append((src, dst, kind, when))
            outgoing[src].append(dst)

        for entry in scope.entrypoints:
            if entry not in ids:
                code = "AG133" if not scope.is_root else "AG115"
                self.report.add(code, "error", f"entrypoint {entry!r} is not a node in this scope", scope.pointer)
            elif incoming[entry]:
                self.report.add("AG112", "error", f"entrypoint {entry!r} has incoming edges", scope.pointer)

        # cycles
        cycle = self._find_cycle(ids, outgoing)
        if cycle:
            self.report.add("AG111", "error", f"cycle in effective edge set: {' -> '.join(cycle)}", scope.pointer)
            scope.predecessors = {n: set() for n in ids}
        else:
            scope.predecessors = self._transitive_predecessors(ids, deduped)

        # reachability
        reachable: set[str] = set()
        stack = [e for e in scope.entrypoints if e in ids]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(outgoing[current])
        for node_id in sorted(ids - reachable):
            self.report.add("AG903", "warning", f"node {node_id!r} is unreachable from any entrypoint",
                            f"{scope.pointer}/nodes/{node_id}")

        # joins
        for node_id, node in scope.nodes.items():
            if node.get("join") == "n_of":
                count = node.get("join_count", 0)
                if count > len(incoming[node_id]):
                    self.report.add("AG116", "error",
                                    f"join_count {count} exceeds {len(incoming[node_id])} incoming edges",
                                    f"{scope.pointer}/nodes/{node_id}")

        self._check_nodes(scope, ids)

    @staticmethod
    def _find_cycle(ids: set[str], outgoing: dict[str, list[str]]) -> list[str] | None:
        WHITE, GREY, BLACK = 0, 1, 2
        color = dict.fromkeys(ids, WHITE)
        path: list[str] = []

        def visit(node: str) -> list[str] | None:
            color[node] = GREY
            path.append(node)
            for nxt in outgoing.get(node, []):
                if color[nxt] == GREY:
                    return path[path.index(nxt):] + [nxt]
                if color[nxt] == WHITE:
                    found = visit(nxt)
                    if found:
                        return found
            path.pop()
            color[node] = BLACK
            return None

        for node in sorted(ids):
            if color[node] == WHITE:
                found = visit(node)
                if found:
                    return found
        return None

    @staticmethod
    def _transitive_predecessors(
        ids: set[str], edges: list[tuple[str, str, str, str | None]]
    ) -> dict[str, set[str]]:
        direct: dict[str, set[str]] = {n: set() for n in ids}
        for src, dst, _kind, _when in edges:
            direct[dst].add(src)
        memo: dict[str, set[str]] = {}

        def resolve(node: str, seen: frozenset[str]) -> set[str]:
            if node in memo:
                return memo[node]
            if node in seen:
                return set()
            result: set[str] = set()
            for parent in direct[node]:
                result.add(parent)
                result |= resolve(parent, seen | {node})
            memo[node] = result
            return result

        return {n: resolve(n, frozenset()) for n in ids}

    def _check_nodes(self, scope: Scope, ids: set[str]) -> None:
        for node_id, node in scope.nodes.items():
            pointer = f"{scope.pointer}/nodes/{node_id}"
            node_type = node.get("type", "task")
            outputs = node.get("outputs") or {}

            if node_id == "self":
                self.report.add("AG117", "error",
                                "'self' is a reserved namespace root and cannot be a node id", pointer)

            for other in ("loop", "map", "subgraph", "gate", "decision"):
                if other in node and other != node_type:
                    self.report.add("AG101", "error",
                                    f"node of type {node_type!r} declares a {other!r} block", pointer)
            if node_type == "gate" and "intelligence" in node:
                self.report.add("AG102", "error", "gate nodes must not declare intelligence", pointer)

            if node_type in ("decision", "gate") and "decision" in outputs:
                self.report.add("AG122", "error",
                                "'decision' is a reserved output name on decision and gate nodes", pointer)

            for name, spec in (node.get("inputs") or {}).items():
                present = [k for k in ("from", "template", "value") if k in spec]
                if len(present) > 1:
                    self.report.add("AG104", "error",
                                    f"input {name!r} declares {present}; at most one is allowed",
                                    f"{pointer}/inputs/{name}")

            if node_type == "decision":
                self._check_decision(node, pointer)

            self._check_intelligence(node.get("intelligence"), pointer)

            failure = node.get("failure") or {}
            for index, step in enumerate(failure.get("fallback") or []):
                fp = f"{pointer}/failure/fallback/{index}"
                strategy = step.get("strategy")
                if strategy == "alternate_node":
                    alt = step.get("node")
                    if alt not in ids:
                        self.report.add("AG113", "error", f"fallback node {alt!r} does not exist", fp)
                    else:
                        required = {n for n, s in outputs.items() if s.get("required", True)}
                        provided = declared_outputs(scope.nodes[alt])
                        missing = required - provided
                        if missing:
                            self.report.add("AG151", "error",
                                            f"fallback node {alt!r} does not declare required outputs {sorted(missing)}",
                                            fp)
                elif strategy == "relax_criteria":
                    declared = {c["id"] for c in ((node.get("success") or {}).get("criteria") or [])}
                    unknown = set(step.get("criteria") or []) - declared
                    if unknown:
                        self.report.add("AG153", "error", f"unknown criteria {sorted(unknown)}", fp)
                elif strategy == "degrade_outputs":
                    unknown = set(step.get("outputs") or []) - set(outputs)
                    if unknown:
                        self.report.add("AG153", "error", f"unknown outputs {sorted(unknown)}", fp)

            comp = failure.get("compensation")
            if comp is not None:
                if comp not in ids:
                    self.report.add("AG113", "error", f"compensation node {comp!r} does not exist", pointer)
                elif ((scope.nodes[comp].get("failure") or {}).get("compensation")) is not None:
                    self.report.add("AG152", "error",
                                    f"compensation node {comp!r} declares its own compensation", pointer)

            escalation = failure.get("escalation") or {}
            if escalation.get("to") == "node" and escalation.get("node") not in ids:
                self.report.add("AG113", "error",
                                f"escalation node {escalation.get('node')!r} does not exist", pointer)

            if node_type in ("loop", "map", "subgraph"):
                self._check_fragment_use(node, node_type, pointer)

            self._advisories(node, node_id, pointer)

    def _check_decision(self, node: dict[str, Any], pointer: str) -> None:
        block = node.get("decision") or {}
        branches = block.get("branches") or []
        labels = [b.get("label") for b in branches]
        duplicates = {label for label in labels if labels.count(label) > 1}
        if duplicates:
            self.report.add("AG124", "error", f"duplicate branch labels {sorted(duplicates)}", pointer)
        if block.get("evaluator", "agent") == "expression":
            for index, branch in enumerate(branches):
                if "when" not in branch:
                    self.report.add("AG121", "error",
                                    f"branch {branch.get('label')!r} has no `when` but evaluator is 'expression'",
                                    f"{pointer}/decision/branches/{index}")
        default = block.get("default_branch")
        if default is not None and default not in labels:
            self.report.add("AG123", "error", f"default_branch {default!r} is not a declared label", pointer)

    def _check_intelligence(self, block: Any, pointer: str) -> None:
        if not isinstance(block, dict):
            return
        tier = block.get("tier")
        level = block.get("level")
        if tier and level is not None and TIER_LEVEL.get(tier) != level:
            self.report.add("AG141", "error", f"tier {tier!r} and level {level} disagree", pointer)
        escalate = block.get("escalate_to")
        if tier and escalate and TIER_LEVEL.get(escalate, 0) < TIER_LEVEL.get(tier, 0):
            self.report.add("AG142", "error",
                            f"escalate_to {escalate!r} is below tier {tier!r}", pointer)
        if tier == "frontier" and not block.get("rationale"):
            self.report.add("AG905", "warning", "frontier-tier node has no rationale", pointer)

    def _check_fragment_use(self, node: dict[str, Any], node_type: str, pointer: str) -> None:
        block = node.get(node_type) or {}
        use = block.get("use")
        if use is not None and use not in (self.doc.get("subgraphs") or {}):
            self.report.add("AG132", "error", f"'{node_type}.use' names unknown fragment {use!r}", pointer)
        ref = block.get("ref") or {}
        uri = ref.get("uri")
        if uri and not uri.startswith((".", "/")) and "integrity" not in ref:
            self.report.add("AG909", "warning",
                            f"non-local subgraph reference {uri!r} has no integrity digest", pointer)

    def _advisories(self, node: dict[str, Any], node_id: str, pointer: str) -> None:
        requirements = node.get("requirements") or {}
        mutating = requirements.get("workspace") == "read_write" or any(
            p.startswith(("fs:write", "fs:delete", "git:commit", "git:push", "shell:exec"))
            for p in requirements.get("permissions") or []
        )
        success = node.get("success")
        if mutating and not success and node.get("type", "task") == "task":
            self.report.add("AG902", "warning",
                            "side-effecting node declares no success block", pointer)
        if success:
            kinds = {c.get("kind") for c in success.get("criteria") or []
                     if c.get("severity", "required") == "required"}
            if kinds and kinds <= {"llm_judge", "human"}:
                self.report.add("AG906", "warning",
                                "success block has no deterministic required criterion", pointer)
        constraints = node.get("constraints") or {}
        if constraints.get("determinism") == "strict" and "seed" not in constraints:
            self.report.add("AG907", "warning", "determinism 'strict' without a seed", pointer)

    # -- layer 3 ------------------------------------------------------------ #

    def check_expressions(self) -> None:
        for scope in self.scopes:
            for node_id, node in scope.nodes.items():
                self._walk_node_expressions(scope, node_id, node)
            for index, edge in enumerate(scope.edges):
                when = edge.get("when")
                if when:
                    anchor = edge.get("from")
                    self._check_expr(scope, when, f"{scope.pointer}/edges/{index}/when", anchor, inclusive=True)
            if not scope.is_root:
                for name, spec in scope.outputs_spec.items():
                    self._check_expr(scope, spec.get("from", ""),
                                     f"{scope.pointer}/outputs/{name}/from", None)
                self._walk_success(scope, None, f"{scope.pointer}/success", None)

        for name, spec in (self.doc.get("outputs") or {}).items():
            self._check_expr(self.scopes[0], spec.get("from", ""), f"/outputs/{name}/from", None)
        self._walk_success(self.scopes[0], self.doc.get("success"), "/success", None)

        self._check_unread_outputs()

    def _walk_node_expressions(self, scope: Scope, node_id: str, node: dict[str, Any]) -> None:
        base = f"{scope.pointer}/nodes/{node_id}"

        for name, spec in (node.get("inputs") or {}).items():
            if "from" in spec:
                self._check_expr(scope, spec["from"], f"{base}/inputs/{name}/from", node_id)
            if "template" in spec:
                self._check_template(scope, spec["template"], f"{base}/inputs/{name}/template", node_id)

        if "when" in node:
            self._check_expr(scope, node["when"], f"{base}/when", node_id)
        if "instructions" in node:
            self._check_template(scope, node["instructions"], f"{base}/instructions", node_id)

        self._walk_success(scope, node.get("success"), f"{base}/success", node_id)

        for index, checkpoint in enumerate(node.get("human") or []):
            cp = f"{base}/human/{index}"
            if "when" in checkpoint:
                self._check_expr(scope, checkpoint["when"], f"{cp}/when", node_id)
            if "prompt" in checkpoint:
                self._check_template(scope, checkpoint["prompt"], f"{cp}/prompt", node_id)

        failure = node.get("failure") or {}
        for index, step in enumerate(failure.get("fallback") or []):
            if "when" in step:
                self._check_expr(scope, step["when"], f"{base}/failure/fallback/{index}/when", node_id)
        message = (failure.get("escalation") or {}).get("message")
        if message:
            self._check_template(scope, message, f"{base}/failure/escalation/message", node_id)

        node_type = node.get("type", "task")
        if node_type == "gate":
            gate = node.get("gate") or {}
            if "prompt" in gate:
                self._check_template(scope, gate["prompt"], f"{base}/gate/prompt", node_id)
            for index, expr in enumerate(gate.get("present") or []):
                self._check_expr(scope, expr, f"{base}/gate/present/{index}", node_id)
        elif node_type == "decision":
            block = node.get("decision") or {}
            if "question" in block:
                self._check_template(scope, block["question"], f"{base}/decision/question", node_id)
            for index, branch in enumerate(block.get("branches") or []):
                if "when" in branch:
                    self._check_expr(scope, branch["when"], f"{base}/decision/branches/{index}/when", node_id)
        elif node_type == "loop":
            block = node.get("loop") or {}
            body = self._body_scope(block, f"{base}/loop/body")
            if "condition" in block:
                self._check_expr(body or scope, block["condition"], f"{base}/loop/condition",
                                 None, fragment_ok=True)
            for name, expr in (block.get("collect") or {}).items():
                self._check_expr(body or scope, expr, f"{base}/loop/collect/{name}",
                                 None, fragment_ok=True)
            self._check_carry(block, body, f"{base}/loop")
        elif node_type == "map":
            block = node.get("map") or {}
            body = self._body_scope(block, f"{base}/map/body")
            if "over" in block:
                self._check_expr(scope, block["over"], f"{base}/map/over", node_id)
            for name, expr in (block.get("collect") or {}).items():
                self._check_expr(body or scope, expr, f"{base}/map/collect/{name}",
                                 None, fragment_ok=True)
        elif node_type == "subgraph":
            block = node.get("subgraph") or {}
            for name, expr in (block.get("params") or {}).items():
                self._check_expr(scope, expr, f"{base}/subgraph/params/{name}", node_id)
            for name, expr in (block.get("outputs_from") or {}).items():
                self._check_expr(scope, expr, f"{base}/subgraph/outputs_from/{name}", node_id, child_ok=True)

    def _body_scope(self, block: dict[str, Any], inline_pointer: str) -> Scope | None:
        """Resolve the fragment a loop/map node iterates over, inline or by name."""
        if "body" in block:
            return self.scopes_by_pointer.get(inline_pointer)
        use = block.get("use")
        if use:
            return self.scopes_by_pointer.get(f"/subgraphs/{use}")
        return None

    def _check_carry(self, block: dict[str, Any], body: Scope | None, pointer: str) -> None:
        """loop.carry maps a body output name onto a body param name."""
        if body is None:
            return
        produced: set[str] = set()
        for node in body.nodes.values():
            produced |= declared_outputs(node)
        for source, target in (block.get("carry") or {}).items():
            if source not in produced:
                self.report.add("AG206", "error",
                                f"carry source {source!r} is not produced by any node in the loop body",
                                f"{pointer}/carry/{source}")
            if target not in body.param_names:
                self.report.add("AG203", "error",
                                f"carry target {target!r} is not a param of the loop body",
                                f"{pointer}/carry/{source}")

    def _walk_success(self, scope: Scope, success: Any, base: str, node_id: str | None) -> None:
        if not isinstance(success, dict):
            return
        for index, criterion in enumerate(success.get("criteria") or []):
            cp = f"{base}/criteria/{index}"
            if "expr" in criterion:
                self._check_expr(scope, criterion["expr"], f"{cp}/expr", node_id, self_outputs=True)
            if "target" in criterion:
                self._check_expr(scope, criterion["target"], f"{cp}/target", node_id, self_outputs=True)
            for i, expr in enumerate(criterion.get("inputs") or []):
                self._check_expr(scope, expr, f"{cp}/inputs/{i}", node_id, self_outputs=True)
            for key in ("rubric", "prompt"):
                if key in criterion:
                    self._check_template(scope, criterion[key], f"{cp}/{key}", node_id, self_outputs=True)
            if node_id is not None and criterion.get("kind") in ("artifact_present", "json_schema", "regex"):
                out = criterion.get("output")
                if out and out not in declared_outputs(scope.nodes[node_id]):
                    self.report.add("AG206", "error",
                                    f"criterion references undeclared output {out!r}", cp)

    def _check_template(self, scope: Scope, text: Any, pointer: str,
                        node_id: str | None, self_outputs: bool = False) -> None:
        if not isinstance(text, str):
            return
        for match in TEMPLATE_RE.finditer(text):
            self._check_expr(scope, match.group(1).strip(), pointer, node_id,
                             self_outputs=self_outputs, in_template=True)

    def _check_expr(self, scope: Scope, text: Any, pointer: str, node_id: str | None,
                    inclusive: bool = False, self_outputs: bool = False,
                    fragment_ok: bool = False, child_ok: bool = False,
                    in_template: bool = False) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        if not in_template and TEMPLATE_RE.search(text):
            self.report.add("AG211", "error",
                            "'${{ }}' interpolation used in expression position", pointer)
            return
        try:
            parser = parse_expression(text)
        except AgxError as exc:
            self.report.add("AG204", "error", f"invalid expression: {exc}", pointer)
            return

        for name, arity in parser.calls:
            expected = FUNCTIONS.get(name)
            if expected is None:
                self.report.add("AG204", "error", f"unknown function {name!r}", pointer)
            elif isinstance(expected, tuple):
                if not expected[0] <= arity <= expected[1]:
                    self.report.add("AG204", "error",
                                    f"{name}() takes {expected[0]}-{expected[1]} arguments, got {arity}", pointer)
            elif arity != expected:
                self.report.add("AG204", "error",
                                f"{name}() takes {expected} arguments, got {arity}", pointer)

        for ref in parser.references:
            self._check_reference(scope, ref, pointer, node_id, inclusive, self_outputs, fragment_ok, child_ok)

    def _check_reference(self, scope: Scope, ref: Reference, pointer: str, node_id: str | None,
                         inclusive: bool, self_outputs: bool, fragment_ok: bool, child_ok: bool) -> None:
        root = ref.root
        parts = ref.parts

        if root == "secrets":
            self.report.add("AG205", "error", "expressions must not reference secrets.*", pointer)
            return
        if root == "graph":
            if len(parts) > 1 and parts[1] not in ("id", "title", "objective", "version", "description"):
                self.report.add("AG203", "error", f"unknown graph field {parts[1]!r}", pointer)
            return
        if root == "params":
            if len(parts) > 1 and parts[1] not in scope.param_names:
                self.report.add("AG203", "error", f"undeclared param {parts[1]!r}", pointer)
            return
        if root == "context":
            if len(parts) > 1 and parts[1] not in self.context_names:
                self.report.add("AG203", "error", f"undeclared context key {parts[1]!r}", pointer)
            return
        if root == "attachments":
            if len(parts) > 1 and parts[1] not in self.attachment_names:
                self.report.add("AG203", "error", f"undeclared attachment {parts[1]!r}", pointer)
            return
        if root == "env":
            declared: set[str] = set()
            if node_id and node_id in scope.nodes:
                declared = set(((scope.nodes[node_id].get("requirements") or {}).get("environment")) or [])
            if len(parts) > 1 and parts[1] not in declared:
                self.report.add("AG203", "error",
                                f"env.{parts[1]} is not declared in requirements.environment", pointer)
            return
        if root == "outputs":
            if child_ok:
                return
            if scope.is_root and node_id is None:
                if len(parts) > 1 and parts[1] not in (self.doc.get("outputs") or {}):
                    self.report.add("AG203", "error", f"undeclared graph output {parts[1]!r}", pointer)
                return
            self.report.add("AG203", "error", "'outputs' is only available in graph-level scope", pointer)
            return
        if root == "loop":
            if not fragment_ok and not scope.extra_bindings & {"loop"}:
                self.report.add("AG203", "error", "'loop' is only available inside a loop body", pointer)
            return
        if root == "self":
            if node_id is None:
                self.report.add("AG203", "error", "'self' is only available within a node", pointer)
                return
            if len(parts) > 2 and parts[1] == "outputs":
                if parts[2] not in declared_outputs(scope.nodes[node_id]):
                    self.report.add("AG206", "error",
                                    f"self.outputs.{parts[2]} is not a declared output", pointer)
                else:
                    self.read_outputs.add((f"{scope.pointer}:{node_id}", parts[2]))
            elif len(parts) > 1 and parts[1] not in ("id", "attempt", "inputs", "outputs"):
                self.report.add("AG203", "error", f"unknown self field {parts[1]!r}", pointer)
            return
        if root == "nodes":
            if len(parts) < 2:
                return
            target = parts[1]
            if target == "self":
                if node_id is None:
                    self.report.add("AG203", "error", "'nodes.self' is only available within a node", pointer)
                    return
                target = node_id
            if target not in scope.nodes:
                if node_id is not None and not scope.is_root:
                    self.report.add("AG202", "error",
                                    f"fragment expression references node {target!r} outside the fragment", pointer)
                else:
                    self.report.add("AG203", "error", f"unknown node {target!r}", pointer)
                return
            if len(parts) > 3 and parts[2] == "outputs":
                if parts[3] not in declared_outputs(scope.nodes[target]):
                    self.report.add("AG206", "error",
                                    f"node {target!r} does not declare output {parts[3]!r}", pointer)
                else:
                    self.read_outputs.add((f"{scope.pointer}:{target}", parts[3]))
            elif len(parts) > 2 and parts[2] not in ("status", "outputs", "attempts", "duration_seconds", "decision"):
                self.report.add("AG203", "error", f"unknown node field {parts[2]!r}", pointer)
            if node_id is not None and target != node_id:
                allowed = scope.predecessors.get(node_id, set())
                if inclusive:
                    allowed = allowed | {node_id}
                if target not in allowed:
                    self.report.add("AG201", "error",
                                    f"node {node_id!r} reads outputs of {target!r}, which is not a transitive predecessor",
                                    pointer)
            return
        if root in scope.extra_bindings:
            return
        self.report.add("AG203", "error", f"unknown reference root {root!r}", pointer)

    def _check_unread_outputs(self) -> None:
        graph_bound: set[tuple[str, str]] = set()
        for spec in (self.doc.get("outputs") or {}).values():
            try:
                parser = parse_expression(spec.get("from", ""))
            except AgxError:
                continue
            for ref in parser.references:
                if ref.root == "nodes" and len(ref.parts) > 3 and ref.parts[2] == "outputs":
                    graph_bound.add((f":{ref.parts[1]}", ref.parts[3]))
        for scope in self.scopes:
            for node_id, node in scope.nodes.items():
                for name in (node.get("outputs") or {}):
                    key = (f"{scope.pointer}:{node_id}", name)
                    if key not in self.read_outputs and key not in graph_bound:
                        self.report.add("AG904", "warning",
                                        f"output {name!r} of node {node_id!r} is never read",
                                        f"{scope.pointer}/nodes/{node_id}/outputs/{name}")

    def check_cost_previewable(self) -> None:
        constraints = self.doc.get("constraints") or {}
        if "max_cost_usd" in constraints:
            return
        for scope in self.scopes:
            for node in scope.nodes.values():
                if node.get("estimate"):
                    return
        self.report.add("AG908", "warning",
                        "graph has neither constraints.max_cost_usd nor any node estimate; "
                        "its cost cannot be previewed")

    def run(self) -> None:
        if not isinstance(self.doc, dict):
            self.report.add("AG001", "error", "document root must be an object")
            return
        schema_ok = self.check_schema()
        self.check_version()
        if not schema_ok:
            return
        self.build_scopes()
        self.check_topology()
        self.check_expressions()
        self.check_cost_previewable()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def expand(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*") if q.suffix in (".json", ".yaml", ".yml")))
        else:
            out.append(p)
    return [p for p in out if p.name != "package.json"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agentic Graph (AGS 1.0) documents.")
    parser.add_argument("paths", nargs="+", help="Files or directories to validate.")
    parser.add_argument("--strict", action="store_true", help="Treat advisory warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Print only the summary line.")
    args = parser.parse_args(argv)

    total_errors = 0
    total_warnings = 0
    reports: list[Report] = []

    for path in expand(args.paths):
        report = Report(path)
        document = load_document(path, report)
        if document is not None:
            Validator(document, report).run()
        reports.append(report)
        total_errors += len(report.errors)
        total_warnings += len(report.warnings)

    for report in reports:
        status = "FAIL" if report.errors else ("WARN" if report.warnings else "OK")
        if not args.quiet:
            print(f"\n=== {report.path}  [{status}]")
            for finding in report.findings:
                print(f"  {finding}")
        elif status != "OK":
            print(f"{report.path}: {status} ({len(report.errors)} errors, {len(report.warnings)} warnings)")

    print(f"\n{len(reports)} document(s): {total_errors} error(s), {total_warnings} warning(s)")
    if total_errors:
        return 1
    if args.strict and total_warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
