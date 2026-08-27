# Versioning and publication

`ags_version` is the `MAJOR.MINOR` data-model version. Repository and support-library releases use `MAJOR.MINOR.PATCH`. AGS 1.0 maintenance release 1.0.1 still reads and writes `ags_version: "1.0"`.

Patch releases correct wording, tests, schemas, diagnostics, and reference tools without adding document fields. A new optional standard field requires AGS 1.1 and a separately published schema. An incompatible field or execution behavior requires AGS 2.0. Unsupported document versions fail closed.

Every release includes an immutable Git tag, schemas, source and wheel archives for the support library, conformance fixtures, checksums, release notes, and successful CI. Schema `$id` values resolve to immutable tagged content.
