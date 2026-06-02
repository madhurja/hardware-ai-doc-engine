# Schematic DRC/ERC Mode

The engine can generate a schematic DRC/ERC pre-check report from PDFs, schematics, and supporting evidence.

## PDF-Based DRC

For schematic PDFs, the tool can flag:

- Rule IDs with severity, domain, confidence, evidence snippets, impact, and required fixes
- Multi-sheet reconciliation, so evidence found in one PDF can suppress false positives from another PDF
- Evidence coverage matrix for power, firmware, PCB/BOM, high-speed layout, field-bus, debug, and protection domains
- Named power rails and mixed-voltage risks
- High-speed interface risks
- Field-bus polarity, termination, surge, and grounding risks
- Protection/ESD evidence gaps
- I2C pull-up evidence gaps
- USB VBUS evidence gaps
- Ethernet pair/magnetics evidence gaps
- PCIe reset, clock, lane, and layout evidence requirements
- Decoupling and regulator support evidence gaps
- Supply-chain and BOM evidence gaps
- Missing firmware, PCB, BOM, and measured validation evidence
- Review gates that must be closed before release

## Native CAD DRC

True pass/fail DRC/ERC requires native schematic or netlist evidence. For release-grade checks, also provide:

- KiCad `.kicad_sch`, `.kicad_pcb`, ERC, and DRC reports
- Altium, EasyEDA, OrCAD, Eagle, or other EDA ERC/DRC exports
- Netlists, PCB layout, BOM, placement, stackup, and fabrication constraints
- Bench measurements and validation logs

## Command

```powershell
python main.py --type drc_report --local-only
```

Use `--type full` to include the DRC report with the full documentation package.
