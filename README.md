# Hardware AI Documentation Engine

Local production node for generating hardware documentation packages from firmware, schematic, and PCB input folders.

## Quick Start

1. Copy `.env.example` to `.env` and add `OPENAI_API_KEY`.
2. Place non-confidential or client-provided files in:
   - `input_drop/code/`
   - `input_drop/schematics/`
   - `input_drop/pcb/`
3. Run:

```powershell
python main.py --type user_manual
python main.py --type test_report
python main.py --type compliance_brief
python main.py --type bom
```

If no API key is configured, the engine produces a local draft document so the parsing and PDF flow can still be tested.

## Safety Rules

`input_drop/` and `output_packages/` are ignored by git to avoid committing client intellectual property or deliverables.

