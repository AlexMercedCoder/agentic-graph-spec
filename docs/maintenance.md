# Agentic Graph Specification maintenance tracker

Audited 2026-11-24 against checkout `f72490e`. Python support suite passed all 28 tests. Additional checks exercised the validator script and ags.validate_path on temporary inputs.

Claim a row by entering your name or task ID and setting the status to **In progress**. Use **Blocked** with the missing dependency if needed. Set **Done** after the acceptance check passes and record the fix commit or PR, the command or manual check, and its result. If a newer revision already resolves the item, record that evidence and close it. Keep status in this table.

| ID | Priority | Status | Owner | Fix and verification |
| --- | --- | --- | --- | --- |
| AGS-01 | P1 | Done | — | `22cee59`. CLI and SDK reject null JSON and empty YAML. Tests passed. |
| AGS-02 | P2 | Done | — | `22cee59`. CLI rejects missing files, invalid UTF-8 and empty batches. 29 Python tests passed across AGS. |

### AGS-01 · Reject JSON null and empty YAML as graph roots

**Reproduced.** A file containing only `null` printed `[OK]` and exited 0. `ags.validate_path` also returned zero errors. In [tools/validate_agraph.py](../tools/validate_agraph.py), the CLI skips validation when the parser returns None. [ags/__init__.py](../ags/__init__.py) repeats that branch.

**Acceptance check.** Add fixtures for JSON null, YAML null and empty YAML. The CLI and SDK must return a document-root error for each. Keep [examples/minimal.agraph.yaml](../examples/minimal.agraph.yaml) valid and keep existing parse-error diagnostics singular.

### AGS-02 · Distinguish missing inputs and empty batches from successful validation

**Reproduced.** An empty directory printed `0 document(s): 0 error(s)` and exited 0. A missing path raised FileNotFoundError before the parser’s exception handler in [tools/validate_agraph.py](../tools/validate_agraph.py).

**Acceptance check.** Exercise an empty directory, absent path, unreadable encoding and a mixed valid/missing batch. Return nonzero with the path or empty-batch reason, process remaining documents, and emit no traceback.
