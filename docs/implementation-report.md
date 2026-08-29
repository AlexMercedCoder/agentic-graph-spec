# Implementation report

This report tracks implementation evidence for AGS 1.0 maintenance release 1.0.1. Listings are not certifications.

| Implementation | Repository | Observed surface | Verification status |
| --- | --- | --- | --- |
| Loro | https://github.com/alexmerced-oss/loro | Validator, evaluator, scheduler, criteria, loops/maps/subgraphs, run records and resume | Self-declared Level 3 result, schema and level surface verified at fixture revision `f180a4d` |
| MagAgent | https://github.com/AlexMercedCoder/MagAgent | Authoring, validator, evaluator, executor, criteria and run records | Self-declared Level 3 result, schema and level surface verified at fixture revision `f180a4d` |
| Merced-AI | https://github.com/AlexMercedCoder/merced-ai | Deterministic reader/planner; execution deliberately unsupported | Self-declared Level 0 result, schema and level surface verified at fixture revision `f180a4d` |

The checked-in records are in [`conformance/results/`](../conformance/results/) and are verified in CI by `tools/verify_conformance_results.py`. They are historical, self-declared evidence against the exact fixture commit named in each record; they do not claim the expanded 1.0.4 release-candidate corpus until each implementation reruns it.

Advancing AGS beyond Draft still requires implementations maintained independently of the specification authors to publish machine-readable results against the same fixture revision and produce compatible execution traces for the level they claim.
