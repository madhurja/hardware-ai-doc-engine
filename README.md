# Hardware AI Documentation Engine

A local-first workstation for turning firmware, schematic PDFs, PCB/BOM manifests, and hardware evidence into polished engineering documentation packages.

The project is designed for productized documentation work: run the engine locally, keep customer inputs private, generate clean PDF deliverables, and publish only the tool itself to GitHub.

## What It Generates

- Detailed user manuals
- Functional test reports
- Compliance briefs
- Draft BOM summaries
- Schematic analysis summaries with power rails, subsystem coverage, key parts, test focus, and review flags

## Browser App

Start the local software-style app on Windows:

```powershell
.\run_windows.ps1
```

Then open the local HTTP link:

```text
http://127.0.0.1:8000
```

The app can also be installed from Chrome or Edge as a PWA. On Android, keep the Windows server running, connect the phone to the same Wi-Fi, then open the LAN link printed by the startup script.

Manual server start is also supported:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

The browser app provides:

- File intake for schematics, firmware, and PCB/BOM manifests
- Local-only generation toggle
- Detected rails, interfaces, key parts, and review flags
- Readiness score, optimization queue, validation matrix, and bring-up sequence
- PDF generation controls
- Download links for generated packages
- Windows and Android local run links

## Quick Start

1. Run `.\run_windows.ps1`.
2. Open `http://127.0.0.1:8000`.
3. Upload files through the app, or place non-confidential/client-provided files in:
   - `input_drop/code/`
   - `input_drop/schematics/`
   - `input_drop/pcb/`
4. Generate one PDF or the full package from the app.

Command-line generation remains available:

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

## Engine Tuning

The local engine now produces a stronger release-planning profile:

- Evidence readiness score
- Power rail and subsystem maps
- Prioritized optimization actions
- Professional validation matrix
- Guided bring-up sequence
- Risk flags for high-speed, wireless, field wiring, ESD, fan, and mixed-voltage sections

These fields appear in the app and inside generated manuals/test documents.

## Windows And Android App Mode

For detailed setup, see [docs/LOCAL_APP_GUIDE.md](docs/LOCAL_APP_GUIDE.md).

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
