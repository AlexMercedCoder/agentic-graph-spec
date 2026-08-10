# Contributing to the Agentic Graph Specification

Thanks for looking. This is a specification repository, so the contribution model is a little
different from a library: most valuable contributions are *reports and cases*, not code.

## What helps most

1. **Implementation reports.** If you build a harness against AGS, open an issue saying what was
   awkward, ambiguous, or impossible. Ambiguity in a spec is a defect even when every reader
   eventually guesses right.
2. **Decompositions you cannot express.** If a real project does not fit the model, that is a spec
   bug. Include the shape you needed and what you tried.
3. **Conformance fixtures.** New cases under `conformance/invalid/`, each with an `# EXPECT: AGnnn`
   header naming the diagnostic it must produce.
4. **Examples.** A worked graph for a domain not yet covered, validating cleanly under `--strict`.

## Ground rules for changes to the data model

Any change to the data model must update **all of these together**, in one pull request:

- `SPEC.md` — the normative text, including the defaults index in Appendix A and the validation
  catalogue in §18 if you added a rule.
- `schema/agentic-graph-1.0.schema.json` — the structural definition.
- `tools/validate_agraph.py` — the reference validator.
- At least one file under `examples/` exercising the change.
- `CHANGELOG.md` under `## [Unreleased]`.

And `tools/run_checks.sh` must pass:

```bash
python3 -m pip install jsonschema pyyaml
tools/run_checks.sh
```

## Compatibility

Read [SPEC.md §21](SPEC.md#21-versioning-and-compatibility) before proposing a field change.

Within a MINOR release you may add optional fields, add enum values behind a conformance level or an
`x-` extension, add advisory validation rules, and relax constraints. You may **not** remove or
rename a field, make an optional field required, narrow an enum, change a default, or change the
meaning of an existing field. Those wait for a MAJOR release.

If you are unsure whether your idea is a field or an extension: start as an `x-` extension, ship it,
and propose promotion once something implements it. That path is described in §21.5.

## Style

- Field names are `snake_case`. This is normative, not preference.
- Normative statements use RFC 2119 keywords in capitals, and only when they carry force.
- Every new field needs a `description` in the schema and a row in the relevant SPEC.md table.
- Examples should be plausible work, not `foo`/`bar`. An example is documentation.
- Prose: American English, present tense, second person for instructions.

## Discussion before code

For anything touching execution semantics (§17), conformance levels (§19), or the expression
language (§16), open an issue first. Those sections are load-bearing for every implementation, and a
design discussion is cheaper than a rejected pull request.

## Licensing of contributions

By contributing you agree that your contributions are licensed under the Apache License 2.0
(see [LICENSE](LICENSE)), and that contributions to the specification text are additionally
available under [CC BY 4.0](LICENSE-CC-BY-4.0), consistent with the rest of the repository.
