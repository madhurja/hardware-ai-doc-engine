# Quality And Flaw Audit

The engine now runs a flaw audit beside every schematic/documentation analysis.

## What It Checks

- Missing schematic evidence
- Missing power rail evidence
- Missing firmware pin/boot evidence
- Missing PCB, BOM, routing, or manufacturing evidence
- Readiness score risk
- High-speed interface routing gaps
- Wireless/SIM release gaps
- Field-bus surge, grounding, and termination gaps
- Open priority review gates

## How To Read It

- `blocker` means the package should not be treated as release-ready.
- `major` means engineering review or missing evidence can affect trust.
- `minor` means the item should be closed before a professional handoff.

The audit produces a release status, quality score, flaw list, and next actions. These show in the app dashboard and are inserted into generated local documents.

## Trust Boundary

The audit is an evidence checker, not a certification authority. It helps decide what still needs proof before a manual, test report, compliance brief, or BOM can be trusted.
