# Hardware AI Documentation Engine

A local-first workstation for turning firmware, schematic PDFs, PCB/BOM manifests, and hardware evidence into polished engineering documentation packages.

The project is designed for productized documentation work: run the engine locally, keep customer inputs private, generate clean PDF deliverables, and publish only the tool itself to GitHub.

## What It Generates

- Detailed user manuals
- Datasheet-style product briefs with board visuals and port maps
- Functional test reports
- Schematic DRC/ERC pre-check reports
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
- Plugin hub with internet research links for parts, datasheets, CAD, and compliance references
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
   Supported hardware evidence includes PDFs, CSV/JSON/XML/netlists, EasyEDA `.epro2` packages, Gerber ZIP archives, manufacturing notes, and board render images.
4. Generate one PDF or the full package from the app.

Command-line generation remains available:

```powershell
python main.py --type user_manual
python main.py --type product_brief
python main.py --type test_report
python main.py --type drc_report
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
- Integrated schematic/PCB skill-pack review gates
- Adaptive improvement memory after every generation/test package
- Flaw audit with blockers, major gaps, release status, and next actions

These fields appear in the app and inside generated manuals/test documents.

## Product Brief Mode

`product_brief` creates a compact Chargebyte-style documentation sheet with board renders, key features, a technical snapshot, port/interface map, production evidence, and release gates.

See [docs/BOARD_A_V04_PRODUCT_BRIEF.md](docs/BOARD_A_V04_PRODUCT_BRIEF.md) for the Board A V0.4 example.

## Schematic And PCB Skill Pack

The provided `Schematics-and-PCB-Skills-main.zip` has been integrated as a distilled review-gate engine. The app now triggers professional schematic, PCB, DFM, DFT, EMC, thermal, supply-chain, wireless, and safety gates from local evidence.

See [docs/SKILL_PACK_INTEGRATION.md](docs/SKILL_PACK_INTEGRATION.md).

## Adaptive Improvement

After every document or test-package generation, the engine records local quality signals and uses them in future runs. This makes the tool more precise over time while staying safe and deterministic.

See [docs/ADAPTIVE_IMPROVEMENT.md](docs/ADAPTIVE_IMPROVEMENT.md).

## Quality And Flaw Audit

The dashboard and generated documents now include a flaw radar that flags missing evidence, high-speed routing gaps, wireless/SIM release gaps, field-bus robustness items, and open review gates.

See [docs/QUALITY_AUDIT.md](docs/QUALITY_AUDIT.md).

For the latest software audit pass, see [docs/PROJECT_AUDIT_REPORT.md](docs/PROJECT_AUDIT_REPORT.md).

## Plugin Hub

The app includes a plugin hub for Octopart/Nexar, DigiKey, Mouser, LCSC, KiCad CLI, compliance references, optional OpenAI drafting, PWA app access, and internal quality audit.

See [docs/PLUGIN_HUB.md](docs/PLUGIN_HUB.md).

## Schematic DRC/ERC Mode

The app can generate a PDF-based schematic DRC/ERC pre-check report and clearly separates inferred findings from native CAD DRC requirements.

See [docs/SCHEMATIC_DRC.md](docs/SCHEMATIC_DRC.md).

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
