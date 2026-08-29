# Coordinated 1.0.4 release checklist

This is a support-library and repository release. It does not change `ags_version: "1.0"` or the normative maintenance baseline 1.0.1.

## Preflight

- Confirm `main` is clean, pushed, and CI is green.
- Confirm Python, TypeScript, Rust, and Java metadata is 1.0.4 and the intended Git tag is `v1.0.4`. Go obtains its module version from that tag.
- Run `tools/run_checks.sh`, all five language validation commands below, dependency audits, and package dry-runs.
- Confirm 1.0.4 does not already exist on PyPI, npm, crates.io, or Maven Central. Registry versions are immutable.

```console
python -m pytest -q
python -m build
python -m twine check dist/*

cd typescript
npm ci
npm run check
npm run audit:prod
npm pack --dry-run

cd ..
go test -race ./...
go vet ./...
go build ./cmd/ags-validate

cd rust
cargo fmt --all --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --locked
cargo doc --locked --no-deps
cargo package --locked
cargo audit --file Cargo.lock

cd ../java
mvn -B verify
```

## Publication order

Publish from the exact commit that will be tagged. A practical order is Python, npm, crates.io, Maven Central, then the Git tag that makes the Go module available. Stop if any registry rejects the artifact; do not retag or reuse an already-published version.

```console
python -m twine upload dist/*
cd typescript && npm publish --access public
cd ../rust && cargo publish --locked
cd ../java && mvn -B deploy -Prelease -Dcentral.autoPublish=true
cd .. && git tag -s v1.0.4 -m "Agentic Graph Specification support libraries 1.0.4"
git push origin v1.0.4
```

After publication, verify clean installs from each public registry, update install snippets and registry links from 1.0.3 to 1.0.4, commit that documentation-only follow-up if needed, and create the GitHub release from the 1.0.4 changelog entry.
