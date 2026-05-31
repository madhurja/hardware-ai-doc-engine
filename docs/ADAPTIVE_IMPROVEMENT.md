# Adaptive Improvement Memory

The software now improves its guidance after every document or test-package generation.

It does this with a local memory file at `local_state/improvement_memory.json`. That file is ignored by git, because it may contain project-specific signals, output names, and recurring risk information.

## What It Learns

- Previous readiness scores
- Recurring schematic/PCB skill gates
- Recurring risk flags
- Recurring evidence gaps
- Document package history
- Adaptive hints for the next run

## What It Does Not Do

- It does not silently rewrite source code.
- It does not claim certification without lab evidence.
- It does not upload private files.
- It does not treat generated text as final engineering approval.

## Why This Is Safer

Self-modifying engineering software can become unpredictable. This project instead uses traceable adaptive memory: every future run can use previous quality signals while still keeping source code deterministic, testable, and reviewable.

## How It Helps Accuracy

If repeated runs show missing PCB/BOM exports, recurring high-speed routing risks, or recurring supply-chain gates, the generated manuals add adaptive precision notes. The app also shows the learning history in the Self-Improvement Memory panel.
