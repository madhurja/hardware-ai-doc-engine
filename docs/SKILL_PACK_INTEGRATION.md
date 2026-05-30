# Schematics And PCB Skill Pack Integration

This project now includes a configurable schematic/PCB review-gate layer derived from `Schematics-and-PCB-Skills-main.zip`.

The source ZIP contains Codex-style skill playbooks. Instead of copying the entire pack into the app, the generator distills the most useful engineering checks into `config/skill_rules.json` and evaluates them against detected schematic, PCB, BOM, and firmware evidence.

## What It Adds

- Schematic topology and operating-point review gates
- PCB physics review gates
- Power integrity and PDN gates
- Signal integrity gates for high-speed interfaces
- EMI/EMC and protection gates for external ports
- DFT, PCB testing, and DFM gates
- Thermal reliability gates
- Supply-chain and BOM risk gates
- Wireless/RF certification gates
- Isolation, creepage, and clearance gates

## Where It Appears

- Browser dashboard: `Schematic/PCB Skill Gates`
- Generate screen: skill-pack quality gate count
- Generated PDFs: `Integrated Schematic And PCB Skill Pack`
- API status: `analysis.skill_review_gates`

## How It Works

1. The parser extracts rails, interfaces, key parts, component families, and risk flags.
2. `core/skill_rules.py` loads `config/skill_rules.json`.
3. Each gate is triggered by subsystem names, keywords, component families, or general evidence.
4. The generator uses triggered gates to create professional checklist sections.

## Updating The Rules

Edit `config/skill_rules.json` to add or tune gates. Each gate supports:

- `id`
- `source_skill`
- `title`
- `domain`
- `priority`
- `trigger_groups`
- `trigger_keywords`
- `trigger_component_families`
- `trigger_always`
- `objective`
- `checklist`

Keep entries concise and evidence-triggered so generated manuals stay readable.
