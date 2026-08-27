# Implementation report

This report tracks implementation evidence for AGS 1.0 maintenance release 1.0.1. Listings are not certifications.

| Implementation | Repository | Observed surface | Verification status |
| --- | --- | --- | --- |
| Loro | https://github.com/alexmerced-oss/loro | Level 3-style validator, evaluator, scheduler, criteria, loops/maps/subgraphs, run records and resume | Rerun required against 1.0.1 corpus |
| MagAgent | https://github.com/AlexMercedCoder/MagAgent | Level 3-style authoring, validator, evaluator, executor, criteria and run records | Rerun required against 1.0.1 corpus |
| Merced-AI | https://github.com/AlexMercedCoder/merced-ai | No complete AGS runtime located | No conformance level verified |

Advancing AGS beyond Draft requires two independent implementations to publish machine-readable results against the same fixture revision and produce compatible execution traces for the level they claim.
