# Hardware AI Documentation Engine

A local-first workstation for turning firmware, schematic PDFs, PCB/BOM manifests, and hardware evidence into polished engineering documentation packages.

The project is designed for productized documentation work: run the engine locally, keep customer inputs private, generate clean PDF deliverables, and publish only the tool itself to GitHub.

## What It Generates

- Detailed user manuals
- Functional test reports
- Compliance briefs
- Draft BOM summaries
- Schematic analysis summaries with power rails, subsystem coverage, key parts, test focus, and review flags

## UI Dashboard

Start the local dashboard:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

The dashboard provides:

- File intake for schematics, firmware, and PCB/BOM manifests
- Local-only generation toggle
- Detected rails, interfaces, key parts, and review flags
- PDF generation controls
- Download links for generated packages

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

Generate the full package without any API calls:

```powershell
.\.venv\Scripts\python.exe main.py --type all --local-only
```

If no API key is configured, the engine produces a local draft document so the parsing and PDF flow can still be tested.

## Privacy Model

- `.env` is ignored so API keys are not committed.
- `input_drop/` is ignored so customer source files and schematics are not committed.
- `output_packages/` is ignored so generated client deliverables are not committed.
- The UI defaults to local-only generation.

## Safety Rules

`input_drop/` and `output_packages/` are ignored by git to avoid committing client intellectual property or deliverables.

## Repository Push

After creating a GitHub repository, add the remote and push:

```powershell
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git branch -M main
git push -u origin main
```
