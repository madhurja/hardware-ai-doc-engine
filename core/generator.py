from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.audit import QualityAuditEngine
from core.drc import DrcRuleEngine
from core.improvement import ImprovementMemory
from core.plugins import PluginRegistry


class HardwareProfile(BaseModel):
    detected_pins: list[dict[str, Any]] = Field(default_factory=list)
    peripherals: list[dict[str, Any]] = Field(default_factory=list)
    schematics: list[dict[str, Any]] = Field(default_factory=list)
    pcb: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocGenerationEngine:
    def __init__(
        self,
        prompts_path: str | Path = "config/prompts.json",
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._load_env_file()
        self.prompts_path = Path(prompts_path)
        self.prompts = self._load_prompts()
        self.api_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def generate_document(self, document_type: str, hardware_profile: dict[str, Any]) -> str:
        profile = HardwareProfile.model_validate(hardware_profile)
        prompt = self.prompts.get(document_type, self.prompts["user_manual"])

        if not self.api_key:
            return self._generate_local_draft(document_type, profile)

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Target Hardware Profile:\n"
                        f"{profile.model_dump_json(indent=2)}\n\n"
                        "Generate structured technical documentation in Markdown."
                    ),
                },
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def _load_prompts(self) -> dict[str, str]:
        if not self.prompts_path.exists():
            raise FileNotFoundError(f"Prompt config not found: {self.prompts_path}")
        prompts = json.loads(self.prompts_path.read_text(encoding="utf-8"))
        if "user_manual" not in prompts:
            raise ValueError("Prompt config must include a user_manual entry.")
        return prompts

    @staticmethod
    def _load_env_file() -> None:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            env_path = Path(".env")
            if not env_path.exists():
                return
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    def _generate_local_draft(self, document_type: str, profile: HardwareProfile) -> str:
        pin_rows = "\n".join(
            f"| {self._md_cell(pin.get('signal_name', 'unknown'))} | {self._md_cell(pin.get('physical_pin', 'unknown'))} | {self._md_cell(pin.get('source_file', ''))} |"
            for pin in profile.detected_pins
        ) or "| No pin mappings detected | Not provided | Not provided |"

        peripheral_rows = "\n".join(
            f"| {self._md_cell(item.get('name', 'unknown'))} | {self._md_cell(item.get('configuration', 'not provided'))} | {self._md_cell(item.get('source_file', ''))} |"
            for item in profile.peripherals
        ) or "| No peripherals detected | Not provided | Not provided |"

        combined_analysis = self._collect_analysis(profile)
        schematic_sections = self._format_manifest_sections(
            profile.schematics,
            "Schematic",
            combined_analysis,
            profile.metadata,
        )
        pcb_sections = self._format_manifest_sections(profile.pcb, "PCB", combined_analysis, profile.metadata)
        guidance = self._document_type_guidance(document_type)
        detailed_sections = self._format_user_manual_sections(profile) if document_type == "user_manual" else ""
        drc_sections = self._format_drc_report_sections(profile) if document_type == "drc_report" else ""
        adaptive_notes = self._format_adaptive_notes()
        quality_audit = self._format_quality_audit(profile)
        plugin_notes = self._format_plugin_notes(profile)

        return f"""# {document_type.replace('_', ' ').title()}

## Scope
This local draft was generated from the supplied hardware evidence. It preserves strict technical bounds and marks anything not present in the source files as evidence required.

## Hardware Profile Summary
- Code files scanned: {profile.metadata.get('code_files_scanned', 0)}
- Schematic files scanned: {profile.metadata.get('schematic_files_scanned', 0)}
- PCB files scanned: {profile.metadata.get('pcb_files_scanned', 0)}
- Detected pins: {profile.metadata.get('pin_count', len(profile.detected_pins))}
- Detected peripherals: {profile.metadata.get('peripheral_count', len(profile.peripherals))}

{adaptive_notes}

{quality_audit}

{plugin_notes}

{drc_sections}

## Detected Pin Map
| Signal | Physical Pin | Source |
| --- | --- | --- |
{pin_rows}

## Detected Peripheral Map
| Peripheral | Configuration | Source |
| --- | --- | --- |
{peripheral_rows}

{detailed_sections}

{schematic_sections}

{pcb_sections}

## Documentation Guidance
{guidance}

## Evidence Required
- Add verified electrical limits before customer delivery.
- Add board revision, firmware version, and validation date.
- Review generated output manually before sending to a client.
"""

    @staticmethod
    def _format_manifest_sections(
        manifests: list[dict[str, Any]],
        label: str,
        global_analysis: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not manifests:
            return f"## {label} Evidence\nNo {label.lower()} manifest data detected."

        sections: list[str] = [f"## {label} Evidence"]
        for manifest in manifests:
            source = manifest.get("source_file", "not provided")
            page_count = manifest.get("page_count")
            sections.append(f"### Source: {source}")
            if page_count:
                sections.append(f"- PDF pages scanned: {page_count}")

            dates = manifest.get("document_dates") or {}
            if dates:
                sections.append(f"- Created: {dates.get('created', 'not provided')}")
                sections.append(f"- Updated: {dates.get('updated', 'not provided')}")

            analysis = manifest.get("analysis") or {}
            if analysis:
                analysis = dict(analysis)
                if global_analysis and analysis.get("drc_findings"):
                    analysis["drc_findings"] = DrcRuleEngine.reconcile_findings(
                        analysis["drc_findings"],
                        global_analysis.get("interface_groups", []),
                        global_analysis.get("power_rails", []),
                        metadata,
                    )
                sections.extend(DocGenerationEngine._format_analysis(analysis))

            nets = manifest.get("detected_nets") or []
            if nets:
                sections.append("#### Detected Nets")
                sections.append(", ".join(nets[:55]))

            components = manifest.get("detected_components") or []
            if components:
                sections.append("#### Component Snapshot")
                sections.append("| Reference | Value / Part |")
                sections.append("| --- | --- |")
                for component in components[:28]:
                    sections.append(
                        f"| {DocGenerationEngine._md_cell(component.get('reference', 'unknown'))} | {DocGenerationEngine._md_cell(component.get('value_or_part', 'not provided'))} |"
                    )

            pages = manifest.get("pages") or []
            if pages:
                sections.append("#### Page Index")
                sections.append("| Page | Inferred Title | Extracted Evidence |")
                sections.append("| --- | --- | --- |")
                for page in pages[:12]:
                    excerpt = DocGenerationEngine._md_cell(page.get("text_excerpt", ""))[:180]
                    sections.append(
                        f"| {DocGenerationEngine._md_cell(page.get('page'))} | {DocGenerationEngine._md_cell(page.get('title', 'Untitled'))} | {excerpt} |"
                    )

        return "\n".join(sections)

    @staticmethod
    def _format_adaptive_notes() -> str:
        summary = ImprovementMemory().summary()
        if not summary.get("runs_total"):
            return "## Adaptive Precision Notes\nNo previous local runs have been recorded yet. This run will seed the local improvement memory."

        sections = [
            "## Adaptive Precision Notes",
            f"- Previous local runs recorded: {summary.get('runs_total', 0)}",
            f"- Average readiness score: {summary.get('average_readiness_score', 0)}/100",
            f"- Best readiness score: {summary.get('best_readiness_score', 0)}/100",
        ]
        for hint in summary.get("adaptive_hints", [])[:5]:
            sections.append(f"- {hint}")
        return "\n".join(sections)

    @staticmethod
    def _format_quality_audit(profile: HardwareProfile) -> str:
        analysis = DocGenerationEngine._collect_analysis(profile)
        audit = QualityAuditEngine().build_audit(profile.model_dump(), analysis)
        sections = [
            "## Evidence Quality And Flaw Audit",
            f"- Release status: {audit['release_status']}",
            f"- Quality score: {audit['quality_score']}/100",
            f"- Open blockers: {audit['counts']['blocker']}",
            f"- Open major flaws: {audit['counts']['major']}",
            f"- Open minor flaws: {audit['counts']['minor']}",
        ]
        flaws = audit.get("flaws", [])
        if flaws:
            sections.append("| Severity | Area | Flaw | Required Fix |")
            sections.append("| --- | --- | --- | --- |")
            for flaw in flaws[:10]:
                sections.append(
                    "| "
                    + " | ".join(
                        DocGenerationEngine._md_cell(flaw.get(field, ""))
                        for field in ("severity", "area", "flaw", "fix")
                    )
                    + " |"
                )
        else:
            sections.append("- No release-blocking evidence flaws were found from the current local inputs.")
        return "\n".join(sections)

    @staticmethod
    def _format_plugin_notes(profile: HardwareProfile) -> str:
        analysis = DocGenerationEngine._collect_analysis(profile)
        catalog = PluginRegistry().build_catalog(profile.model_dump(), analysis)
        summary = catalog.get("summary", {})
        sections = [
            "## Internet And Plugin Research Pack",
            f"- Installed plugin definitions: {summary.get('total', 0)}",
            f"- Internet-enabled plugins: {summary.get('internet_enabled', 0)}",
            f"- API-ready plugins: {summary.get('api_ready', 0)}",
            "- Internet actions are convenience links for research and evidence gathering; they do not replace datasheet, CAD, lab, or compliance review.",
        ]
        parts = catalog.get("research_pack", {}).get("parts", [])
        if parts:
            sections.append("| Part / Query | Research Links |")
            sections.append("| --- | --- |")
            for part in parts[:8]:
                links = ", ".join(f"{link['label']}: {link['url']}" for link in part.get("links", [])[:3])
                sections.append(
                    f"| {DocGenerationEngine._md_cell(part.get('query', 'unknown'))} | {DocGenerationEngine._md_cell(links)} |"
                )
        return "\n".join(sections)

    @staticmethod
    def _md_cell(value: Any) -> str:
        return str(value).replace("|", "/").replace("\r", " ").replace("\n", " ").strip()

    @staticmethod
    def _format_analysis(analysis: dict[str, Any]) -> list[str]:
        sections: list[str] = []

        power_rails = analysis.get("power_rails") or []
        if power_rails:
            sections.append("#### Power Rail Map")
            sections.append("| Net | Inferred Role |")
            sections.append("| --- | --- |")
            for rail in power_rails[:18]:
                sections.append(
                    f"| {DocGenerationEngine._md_cell(rail.get('net', 'unknown'))} | {DocGenerationEngine._md_cell(rail.get('role', 'Power rail'))} |"
                )

        interface_groups = analysis.get("interface_groups") or []
        if interface_groups:
            sections.append("#### Interface Coverage")
            sections.append("| Subsystem | Evidence | Confidence |")
            sections.append("| --- | --- | --- |")
            for group in interface_groups[:14]:
                evidence = ", ".join(group.get("evidence", []))
                sections.append(
                    f"| {DocGenerationEngine._md_cell(group.get('name', 'Unknown'))} | {DocGenerationEngine._md_cell(evidence)} | {DocGenerationEngine._md_cell(group.get('confidence', 0))}% |"
                )

        component_counts = analysis.get("component_counts") or {}
        if component_counts:
            sections.append("#### Component Family Counts")
            sections.append("| Family | Count |")
            sections.append("| --- | --- |")
            for family, count in component_counts.items():
                sections.append(
                    f"| {DocGenerationEngine._md_cell(family.replace('_', ' ').title())} | {DocGenerationEngine._md_cell(count)} |"
                )

        key_parts = analysis.get("key_parts") or []
        if key_parts:
            sections.append("#### Key Part Candidates")
            sections.append("| Reference | Candidate Part / Value |")
            sections.append("| --- | --- |")
            for part in key_parts[:20]:
                sections.append(
                    f"| {DocGenerationEngine._md_cell(part.get('reference', 'unknown'))} | {DocGenerationEngine._md_cell(part.get('value_or_part', 'not provided'))} |"
                )

        test_focus = analysis.get("test_focus") or []
        if test_focus:
            sections.append("#### Functional Test Focus")
            sections.extend(f"- {item}" for item in test_focus[:12])

        risk_flags = analysis.get("risk_flags") or []
        if risk_flags:
            sections.append("#### Engineering Review Flags")
            sections.extend(f"- {item}" for item in risk_flags[:8])

        optimization_actions = analysis.get("optimization_actions") or []
        if optimization_actions:
            sections.append("#### Optimization Actions")
            sections.append("| Priority | Area | Recommendation |")
            sections.append("| --- | --- | --- |")
            for action in optimization_actions[:8]:
                sections.append(
                    f"| {DocGenerationEngine._md_cell(action.get('priority', 'P2'))} | {DocGenerationEngine._md_cell(action.get('area', 'Engineering'))} | {DocGenerationEngine._md_cell(action.get('recommendation', 'Review required.'))} |"
                )

        validation_matrix = analysis.get("validation_matrix") or []
        if validation_matrix:
            sections.append("#### Validation Matrix")
            sections.append("| Subsystem | Objective | Method | Acceptance |")
            sections.append("| --- | --- | --- | --- |")
            for item in validation_matrix[:8]:
                sections.append(
                    f"| {DocGenerationEngine._md_cell(item.get('subsystem', 'Subsystem'))} | {DocGenerationEngine._md_cell(item.get('objective', 'Confirm behavior'))} | {DocGenerationEngine._md_cell(item.get('method', 'Test required.'))} | {DocGenerationEngine._md_cell(item.get('acceptance', 'Evidence recorded.'))} |"
                )

        bringup_sequence = analysis.get("bringup_sequence") or []
        if bringup_sequence:
            sections.append("#### Bring-Up Sequence")
            sections.extend(f"- {item}" for item in bringup_sequence[:10])

        readiness_score = analysis.get("readiness_score")
        if isinstance(readiness_score, (int, float)):
            sections.append("#### Evidence Readiness Score")
            sections.append(
                f"- Current score: {round(readiness_score)}/100. This is an evidence completeness indicator, not a certification result."
            )

        skill_review_gates = analysis.get("skill_review_gates") or []
        if skill_review_gates:
            sections.append("#### Skill Pack Review Gates")
            sections.append("| Priority | Gate | Source Skill | Evidence |")
            sections.append("| --- | --- | --- | --- |")
            for gate in skill_review_gates[:8]:
                sections.append(
                    f"| {DocGenerationEngine._md_cell(gate.get('priority', 'P2'))} | {DocGenerationEngine._md_cell(gate.get('title', 'Review Gate'))} | {DocGenerationEngine._md_cell(gate.get('source_skill', 'skill-pack'))} | {DocGenerationEngine._md_cell(gate.get('evidence', 'project evidence present'))} |"
                )

        drc_findings = analysis.get("drc_findings") or []
        if drc_findings:
            sections.append("#### DRC/ERC Findings")
            sections.append("| Severity | Rule | Domain | Finding |")
            sections.append("| --- | --- | --- | --- |")
            for finding in drc_findings[:10]:
                sections.append(
                    f"| {DocGenerationEngine._md_cell(finding.get('severity', 'info'))} | {DocGenerationEngine._md_cell(finding.get('id', 'DRC'))} | {DocGenerationEngine._md_cell(finding.get('domain', 'General'))} | {DocGenerationEngine._md_cell(finding.get('finding', 'Review required'))} |"
                )

        return sections

    @classmethod
    def _format_user_manual_sections(cls, profile: HardwareProfile) -> str:
        analysis = cls._collect_analysis(profile)
        sections: list[str] = []

        sections.append("## Detailed System Overview")
        sections.append(
            "This manual describes the board from the available schematic evidence. It is suitable for engineering bring-up, service review, and customer-facing draft preparation after connector labels and firmware behavior are confirmed."
        )
        sections.append(f"- Source files reviewed: {', '.join(analysis['sources']) or 'not provided'}")
        sections.append(f"- Total schematic pages reviewed: {analysis['page_count']}")
        sections.append(f"- Major detected subsystems: {', '.join(group['name'] for group in analysis['interface_groups'][:12]) or 'not detected'}")
        sections.append(f"- Power rails detected: {', '.join(rail['net'] for rail in analysis['power_rails'][:12]) or 'not detected'}")
        sections.append(f"- Evidence readiness score: {analysis['readiness_score']}/100")
        sections.append("### How This Manual Is Organized")
        sections.append("- System overview explains what the board appears to contain based on detected schematic evidence.")
        sections.append("- Functional block guide explains each major block, what it is used for, how it works, how to use it, and how to verify it.")
        sections.append("- Power and bring-up sections define the safest order for first operation.")
        sections.append("- Troubleshooting and maintenance sections convert the schematic analysis into practical service actions.")
        sections.append("- Optimization and validation sections turn schematic findings into release work packages.")

        sections.append("### Evidence Readiness Interpretation")
        sections.append("- 0-39 means the engine has too little named evidence for professional release documents.")
        sections.append("- 40-69 means the generated package is useful for internal review and bring-up planning.")
        sections.append("- 70-89 means the evidence is strong enough for structured customer-draft preparation after manual review.")
        sections.append("- 90-100 means the source package is highly complete, but final approval still requires measured lab evidence.")

        if analysis["skill_review_gates"]:
            sections.append("## Integrated Schematic And PCB Skill Pack")
            sections.append(
                "The review gates below are distilled from the provided Schematics-and-PCB skill pack and are triggered by detected rails, interfaces, components, and risk evidence."
            )
            sections.append("| Priority | Gate | Source Skill | Why It Was Triggered |")
            sections.append("| --- | --- | --- | --- |")
            for gate in analysis["skill_review_gates"][:14]:
                sections.append(
                    f"| {cls._md_cell(gate.get('priority', 'P2'))} | {cls._md_cell(gate.get('title', 'Review Gate'))} | {cls._md_cell(gate.get('source_skill', 'skill-pack'))} | {cls._md_cell(gate.get('evidence', 'project evidence present'))} |"
                )
            sections.append("### Skill Gate Action Checklist")
            for gate in analysis["skill_review_gates"][:8]:
                sections.append(f"#### {gate.get('title', 'Review Gate')}")
                sections.append(f"- Objective: {gate.get('objective', 'Review required.')}")
                for item in gate.get("checklist", [])[:5]:
                    sections.append(f"- {item}")

        if analysis["interface_groups"]:
            sections.append("### Functional Block Summary")
            sections.append("| Block | Detected Evidence | Manual Interpretation |")
            sections.append("| --- | --- | --- |")
            for group in analysis["interface_groups"][:14]:
                evidence = ", ".join(group.get("evidence", []))
                sections.append(
                    f"| {cls._md_cell(group.get('name', 'Unknown'))} | {cls._md_cell(evidence)} | {cls._md_cell(cls._manual_note_for_group(group.get('name', 'Unknown')))} |"
                )

        if analysis["interface_groups"]:
            sections.append("## Professional Functional Block Guide")
            for group in analysis["interface_groups"][:14]:
                name = group.get("name", "Unknown")
                profile = cls._block_profile_for_group(name)
                sections.append(f"### {name}")
                sections.append(f"- Description: {profile['description']}")
                sections.append(f"- Primary use: {profile['use']}")
                sections.append(f"- How it works: {profile['how_it_works']}")
                sections.append(f"- How to use it: {profile['how_to_use']}")
                sections.append(f"- Verification method: {profile['verification']}")

        if analysis["power_rails"]:
            sections.append("## Power Input, Rail Checks, And Bring-Up")
            sections.append(
                "Before attaching external modules, displays, USB devices, fans, field wiring, or radio hardware, power the board in a controlled bench setup and verify the rails below."
            )
            sections.append("| Rail | Inferred Role | Bring-Up Check |")
            sections.append("| --- | --- | --- |")
            for rail in analysis["power_rails"][:16]:
                sections.append(
                    f"| {cls._md_cell(rail.get('net', 'unknown'))} | {cls._md_cell(rail.get('role', 'Power rail'))} | Confirm voltage, ramp stability, no excessive current draw, and no local heating. |"
                )
            sections.append("### Recommended Power-Up Sequence")
            sections.append("- Inspect the board for assembly damage, solder bridges, missing jumpers, and connector contamination.")
            sections.append("- Connect a current-limited bench supply to the expected input rail and start with conservative current limiting.")
            sections.append("- Power the board without external peripherals first, then verify each detected rail with a meter.")
            sections.append("- Confirm power-good, enable, reset, and status LED behavior before attaching high-current or high-speed devices.")
            sections.append("- Add peripherals one group at a time: USB, HDMI/display, Ethernet, wireless/SIM, fan, then field buses.")
            sections.append("- Record measured rail values, current draw, board temperature, and any LED state at each step.")

        if analysis["bringup_sequence"]:
            sections.append("## Guided Bring-Up Sequence")
            for index, step in enumerate(analysis["bringup_sequence"], 1):
                sections.append(f"- Step {index}: {step}")

        sections.append("## Operating Procedure")
        sections.append("### Pre-Operation Inspection")
        sections.append("- Confirm the board revision and schematic source match the hardware under test.")
        sections.append("- Verify that the CM4 module, SIM/modem module, fan, headers, and field connectors are mechanically seated.")
        sections.append("- Confirm that no cables are attached to unknown headers until their signal names are reviewed.")
        sections.append("- Confirm that ESD precautions are active before handling HDMI, USB, Ethernet, SIM, camera, display, and GPIO connectors.")
        sections.append("### Normal Start-Up")
        sections.append("- Apply the validated input supply and observe current draw for abnormal spikes.")
        sections.append("- Check status indicators and control nets such as run, reset, power LED, activity LED, wireless enable, and modem status lines when present.")
        sections.append("- Attach communication interfaces only after the base rails are stable.")
        sections.append("- For wireless/SIM variants, verify SIM card orientation, modem supply stability, and antenna connection requirements before network testing.")
        sections.append("### Normal Shutdown")
        sections.append("- Stop active communication traffic before disconnecting USB, Ethernet, modem, RS485, or fan loads.")
        sections.append("- Remove external field wiring and high-current loads before removing the main input supply.")
        sections.append("- Wait for local storage, modem, and RTC-sensitive operations to finish before power removal.")

        if analysis["interface_groups"]:
            sections.append("## Interface Operation Guide")
            sections.append("| Interface | Operator Notes | First Validation Action |")
            sections.append("| --- | --- | --- |")
            for group in analysis["interface_groups"][:14]:
                name = group.get("name", "Unknown")
                sections.append(
                    f"| {cls._md_cell(name)} | {cls._md_cell(cls._operator_note_for_group(name))} | {cls._md_cell(cls._validation_note_for_group(name))} |"
                )

        sections.append("## Subsystem Service Notes")
        for group in analysis["interface_groups"][:12]:
            name = group.get("name", "Unknown")
            sections.append(f"### {name}")
            sections.extend(f"- {item}" for item in cls._subsystem_notes(name, analysis))

        if analysis["key_parts"]:
            sections.append("## Key Component Reference")
            sections.append("| Reference | Candidate Part / Value | Why It Matters |")
            sections.append("| --- | --- | --- |")
            for part in analysis["key_parts"][:24]:
                reference = part.get("reference", "unknown")
                value = part.get("value_or_part", "not provided")
                sections.append(
                    f"| {cls._md_cell(reference)} | {cls._md_cell(value)} | {cls._md_cell(cls._key_part_note(reference, value))} |"
                )

        if analysis["test_focus"]:
            sections.append("## Commissioning Checklist")
            sections.append("| Step | Check | Acceptance Evidence |")
            sections.append("| --- | --- | --- |")
            for index, item in enumerate(analysis["test_focus"][:14], 1):
                sections.append(
                    f"| {index} | {cls._md_cell(item)} | Measurement, visual state, or continuity result recorded. |"
                )

        if analysis["validation_matrix"]:
            sections.append("## Professional Validation Matrix")
            sections.append("| Subsystem | Objective | Method | Acceptance Criteria |")
            sections.append("| --- | --- | --- | --- |")
            for item in analysis["validation_matrix"][:16]:
                sections.append(
                    f"| {cls._md_cell(item.get('subsystem', 'Subsystem'))} | {cls._md_cell(item.get('objective', 'Confirm behavior'))} | {cls._md_cell(item.get('method', 'Test required.'))} | {cls._md_cell(item.get('acceptance', 'Evidence recorded.'))} |"
                )

        if analysis["optimization_actions"]:
            sections.append("## 200 Percent Optimization Roadmap")
            sections.append(
                "The roadmap below is prioritized for turning an extracted schematic package into a professional software-like documentation workflow with stronger release evidence."
            )
            sections.append("| Priority | Area | Action | Why It Improves The Engine Output | Evidence Trigger |")
            sections.append("| --- | --- | --- | --- | --- |")
            for action in analysis["optimization_actions"][:12]:
                sections.append(
                    f"| {cls._md_cell(action.get('priority', 'P2'))} | {cls._md_cell(action.get('area', 'Engineering'))} | {cls._md_cell(action.get('recommendation', 'Review required.'))} | {cls._md_cell(action.get('why', 'Improves release confidence.'))} | {cls._md_cell(action.get('evidence', 'Detected evidence'))} |"
                )

        sections.append("## Troubleshooting Matrix")
        sections.append("| Symptom | Likely Area | First Checks |")
        sections.append("| --- | --- | --- |")
        for symptom, area, checks in cls._troubleshooting_rows(analysis):
            sections.append(f"| {cls._md_cell(symptom)} | {cls._md_cell(area)} | {cls._md_cell(checks)} |")

        if analysis["risk_flags"]:
            sections.append("## Handling And Engineering Warnings")
            sections.extend(f"- {flag}" for flag in analysis["risk_flags"])
        sections.append("- Do not connect unknown loads to GPIO, RS485, fan, or power headers until pin direction and voltage level are confirmed.")
        sections.append("- Do not assume compliance status from schematic review alone; lab evidence is required for external release claims.")

        sections.append("## Maintenance And Service Notes")
        sections.append("- Inspect high-use connectors for mechanical wear, bent pins, cracked solder joints, and shield continuity.")
        sections.append("- Recheck input protection, ESD devices, and field-bus termination after surge or wiring fault events.")
        sections.append("- Keep the schematic revision, board revision, firmware image, and test report together for traceability.")
        sections.append("- Replace coin-cell or backup battery components only with confirmed polarity, chemistry, and footprint compatibility.")

        sections.append("## Manual Completion Items")
        sections.append("- Add product name, enclosure photos, connector location diagrams, and final customer-facing labels.")
        sections.append("- Add rated input voltage, maximum current, environmental limits, and approved accessory list.")
        sections.append("- Add firmware-specific behavior for LEDs, buttons, modem control, boot mode, and recovery procedures.")
        sections.append("- Add safety statements required by the target market and regulatory pathway.")

        return "\n".join(sections)

    @classmethod
    def _format_drc_report_sections(cls, profile: HardwareProfile) -> str:
        analysis = cls._collect_analysis(profile)
        audit = QualityAuditEngine().build_audit(profile.model_dump(), analysis)
        sections: list[str] = []

        sections.append("## Schematic DRC/ERC Review")
        sections.append(
            "This report is a PDF-based design-rule and electrical-rule review. It can identify likely risk areas, missing evidence, open gates, and release blockers. It is not a native CAD ERC/DRC pass until schematic/netlist files are supplied."
        )
        sections.append(f"- Release status: {audit['release_status']}")
        sections.append(f"- DRC quality score: {audit['quality_score']}/100")
        sections.append(f"- Evidence readiness score: {analysis['readiness_score']}/100")
        sections.append(f"- Schematic sources reviewed: {', '.join(analysis['sources']) or 'not provided'}")
        sections.append(f"- Schematic pages reviewed: {analysis['page_count']}")
        drc_findings = analysis.get("drc_findings", [])
        drc_summary = analysis.get("drc_summary", {})
        drc_coverage = analysis.get("drc_coverage", [])
        if drc_summary:
            sections.append(f"- Rule-engine DRC score: {drc_summary.get('score', 0)}/100")
            sections.append(f"- Rule-engine findings: {drc_summary.get('finding_count', len(drc_findings))}")

        sections.append("### DRC Capability Boundary")
        sections.append("| Check Type | PDF-Based Result | Native CAD Requirement |")
        sections.append("| --- | --- | --- |")
        boundary_rows = [
            ("Power rail discovery", "Supported from visible net labels", "Native netlist required for exhaustive rail connectivity"),
            ("Interface and connector risk", "Supported from signal/component evidence", "Native schematic required for pin-by-pin connection checks"),
            ("Shorts, no-connects, and floating pins", "Not authoritative from PDF", "Run ERC in KiCad, Altium, EasyEDA, or exported netlist"),
            ("Differential pair and impedance DRC", "Risk can be flagged", "PCB layout, stackup, and rule constraints required"),
            ("BOM and footprint correctness", "Candidate parts can be extracted", "Native BOM/placement/CAD library evidence required"),
        ]
        for check_type, pdf_result, native_requirement in boundary_rows:
            sections.append(
                f"| {cls._md_cell(check_type)} | {cls._md_cell(pdf_result)} | {cls._md_cell(native_requirement)} |"
            )

        if drc_coverage:
            sections.append("### Evidence Coverage Matrix")
            sections.append("| Domain | Status | Evidence | Next Step |")
            sections.append("| --- | --- | --- | --- |")
            for row in drc_coverage:
                sections.append(
                    f"| {cls._md_cell(row.get('domain'))} | {cls._md_cell(row.get('status'))} | {cls._md_cell(row.get('evidence'))} | {cls._md_cell(row.get('next_step'))} |"
                )

        if analysis["power_rails"]:
            sections.append("### Power Rule Checks")
            sections.append("| Rail | DRC Concern | Required Evidence |")
            sections.append("| --- | --- | --- |")
            for rail in analysis["power_rails"][:14]:
                sections.append(
                    f"| {cls._md_cell(rail.get('net', 'unknown'))} | Confirm source, load path, sequencing, enable/PG behavior, and over-current protection. | Measured voltage, current limit, ramp, ripple, and thermal data. |"
                )

        if analysis["interface_groups"]:
            sections.append("### Interface Rule Checks")
            sections.append("| Interface | DRC Concern | Required Evidence |")
            sections.append("| --- | --- | --- |")
            for group in analysis["interface_groups"][:14]:
                name = group.get("name", "Unknown")
                sections.append(
                    f"| {cls._md_cell(name)} | {cls._md_cell(cls._drc_concern_for_group(name))} | {cls._md_cell(cls._drc_evidence_for_group(name))} |"
                )

        if audit["flaws"]:
            sections.append("### Open DRC Findings")
            sections.append("| Severity | Area | Finding | Required Fix |")
            sections.append("| --- | --- | --- | --- |")
            for flaw in audit["flaws"][:16]:
                sections.append(
                    f"| {cls._md_cell(flaw.get('severity'))} | {cls._md_cell(flaw.get('area'))} | {cls._md_cell(flaw.get('flaw'))} | {cls._md_cell(flaw.get('fix'))} |"
                )

        if drc_findings:
            sections.append("### Rule-Engine Findings")
            sections.append("| Severity | Rule ID | Domain | Check | Finding | Impact | Required Fix | Confidence |")
            sections.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for finding in drc_findings[:18]:
                sections.append(
                    f"| {cls._md_cell(finding.get('severity'))} | {cls._md_cell(finding.get('id'))} | {cls._md_cell(finding.get('domain'))} | {cls._md_cell(finding.get('check'))} | {cls._md_cell(finding.get('finding'))} | {cls._md_cell(finding.get('impact'))} | {cls._md_cell(finding.get('fix'))} | {cls._md_cell(finding.get('confidence'))}% |"
                )

            sections.append("### Evidence Snippets")
            sections.append("| Rule ID | Extracted Evidence |")
            sections.append("| --- | --- |")
            for finding in drc_findings[:12]:
                sections.append(
                    f"| {cls._md_cell(finding.get('id'))} | {cls._md_cell(finding.get('evidence'))[:260]} |"
                )

        if analysis["skill_review_gates"]:
            sections.append("### Rule Gates To Close")
            sections.append("| Priority | Gate | Evidence Trigger |")
            sections.append("| --- | --- | --- |")
            for gate in analysis["skill_review_gates"][:12]:
                sections.append(
                    f"| {cls._md_cell(gate.get('priority', 'P2'))} | {cls._md_cell(gate.get('title', 'Review Gate'))} | {cls._md_cell(gate.get('evidence', 'project evidence present'))} |"
                )

        sections.append("### Native DRC/ERC Upgrade Path")
        sections.append("- Upload native schematic files, netlists, PCB layout exports, BOM, and rule reports when available.")
        sections.append("- For KiCad projects, use `kicad-cli sch erc` and `kicad-cli pcb drc`, then attach the generated reports to the intake folder.")
        sections.append("- For Altium, EasyEDA, OrCAD, or other EDA tools, export ERC/DRC reports plus netlists and BOM data.")
        sections.append("- Treat this PDF-based report as a professional pre-check and evidence planner until native CAD evidence is attached.")

        return "\n".join(sections)

    @classmethod
    def _collect_analysis(cls, profile: HardwareProfile) -> dict[str, Any]:
        collected = {
            "sources": [],
            "page_count": 0,
            "power_rails": [],
            "interface_groups": [],
            "key_parts": [],
            "test_focus": [],
            "risk_flags": [],
            "optimization_actions": [],
            "validation_matrix": [],
            "bringup_sequence": [],
            "skill_review_gates": [],
            "drc_findings": [],
            "readiness_scores": [],
        }
        seen = {
            key: set()
            for key in (
                "power_rails",
                "interface_groups",
                "key_parts",
                "test_focus",
                "risk_flags",
                "optimization_actions",
                "validation_matrix",
                "bringup_sequence",
                "skill_review_gates",
                "drc_findings",
            )
        }
        for manifest in [*profile.schematics, *profile.pcb]:
            source = manifest.get("source_file")
            if source:
                collected["sources"].append(source)
            collected["page_count"] += int(manifest.get("page_count") or 0)
            analysis = manifest.get("analysis") or {}
            score = analysis.get("readiness_score")
            if isinstance(score, (int, float)):
                collected["readiness_scores"].append(score)
            for rail in analysis.get("power_rails") or []:
                key = cls._normalize_rail_key(rail.get("net", ""))
                if key and key not in seen["power_rails"]:
                    collected["power_rails"].append(rail)
                    seen["power_rails"].add(key)
            for group in analysis.get("interface_groups") or []:
                key = group.get("name")
                if key and key not in seen["interface_groups"]:
                    collected["interface_groups"].append(group)
                    seen["interface_groups"].add(key)
            for part in analysis.get("key_parts") or []:
                key = part.get("reference")
                if key and key not in seen["key_parts"]:
                    collected["key_parts"].append(part)
                    seen["key_parts"].add(key)
            for field in ("test_focus", "risk_flags"):
                for item in analysis.get(field) or []:
                    if item not in seen[field]:
                        collected[field].append(item)
                        seen[field].add(item)
            for action in analysis.get("optimization_actions") or []:
                key = (action.get("area"), action.get("recommendation"))
                if key not in seen["optimization_actions"]:
                    collected["optimization_actions"].append(action)
                    seen["optimization_actions"].add(key)
            for item in analysis.get("validation_matrix") or []:
                key = (item.get("subsystem"), item.get("method"))
                if key not in seen["validation_matrix"]:
                    collected["validation_matrix"].append(item)
                    seen["validation_matrix"].add(key)
            for item in analysis.get("bringup_sequence") or []:
                if item not in seen["bringup_sequence"]:
                    collected["bringup_sequence"].append(item)
                    seen["bringup_sequence"].add(item)
            for gate in analysis.get("skill_review_gates") or []:
                key = gate.get("id")
                if key and key not in seen["skill_review_gates"]:
                    collected["skill_review_gates"].append(gate)
                    seen["skill_review_gates"].add(key)
            for finding in analysis.get("drc_findings") or []:
                key = (finding.get("id"), finding.get("finding"))
                if key not in seen["drc_findings"]:
                    collected["drc_findings"].append(finding)
                    seen["drc_findings"].add(key)
        scores = collected.pop("readiness_scores")
        collected["drc_findings"] = DrcRuleEngine.reconcile_findings(
            collected["drc_findings"],
            collected["interface_groups"],
            collected["power_rails"],
            profile.metadata,
        )
        collected["drc_summary"] = cls._summarize_drc_findings(collected["drc_findings"])
        collected["drc_coverage"] = DrcRuleEngine.build_coverage_matrix(
            collected["drc_findings"],
            collected["interface_groups"],
            collected["power_rails"],
            profile.metadata,
        )
        collected["readiness_score"] = round(sum(scores) / len(scores)) if scores else 0
        return collected

    @staticmethod
    def _summarize_drc_findings(findings: list[dict[str, Any]]) -> dict[str, Any]:
        severity_counts: dict[str, int] = {}
        domain_counts: dict[str, int] = {}
        for finding in findings:
            severity = finding.get("severity", "info")
            domain = finding.get("domain", "General")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        penalty = severity_counts.get("blocker", 0) * 25 + severity_counts.get("major", 0) * 8 + severity_counts.get("minor", 0) * 3
        return {
            "finding_count": len(findings),
            "score": max(0, 100 - penalty),
            "by_severity": severity_counts,
            "by_domain": domain_counts,
        }

    @staticmethod
    def _normalize_rail_key(value: str) -> str:
        return str(value).upper().replace(".", "").lstrip("+")

    @staticmethod
    def _manual_note_for_group(name: str) -> str:
        notes = {
            "Power": "Defines the board supply rails and must be verified before every interface test.",
            "Ethernet": "Wired network path with magnetics, MDI pairs, shield, and LED behavior.",
            "USB": "Host/device data path and VBUS distribution requiring current-limit review.",
            "HDMI": "Display interface with DDC, hotplug, 5 V, and high-speed differential pairs.",
            "Wireless/SIM": "Modem/SIM control path requiring RF, SIM, enable, reset, and power validation.",
            "RS485": "Field-wiring interface requiring line polarity, termination, surge, and grounding review.",
            "GPIO Header": "Expansion header exposing logic-level signals; voltage and direction must be confirmed.",
            "RTC": "Timekeeping and backup supply area requiring battery and I2C checks.",
            "Fan": "Thermal output path requiring fan voltage, tachometer, and load current validation.",
            "Protection/ESD": "Protection devices around external connectors and field wiring.",
        }
        return notes.get(name, "Detected functional block requiring schematic-to-hardware confirmation.")

    @staticmethod
    def _block_profile_for_group(name: str) -> dict[str, str]:
        profiles = {
            "Power": {
                "description": "Power entry and distribution section feeding the logic, modem, interface, fan, and auxiliary rails.",
                "use": "Provides stable voltage domains for the board and defines the order in which peripherals can be safely enabled.",
                "how_it_works": "Input power is distributed through rails, regulators, switches, protection devices, and decoupling networks before reaching each subsystem.",
                "how_to_use": "Begin with a current-limited supply, verify unloaded rails, then attach peripherals one block at a time.",
                "verification": "Measure each rail for voltage, ripple, ramp behavior, current draw, and temperature under staged load.",
            },
            "Ethernet": {
                "description": "Wired network interface including differential pairs, magnetics/RJ45 path, LEDs, and shield-related signals.",
                "use": "Connects the board to a LAN for network communication, configuration, diagnostics, or data transfer.",
                "how_it_works": "Transmit and receive pairs route through controlled differential paths and magnetics before reaching the external connector.",
                "how_to_use": "Use a known-good Ethernet cable and switch after confirming pair continuity and shield policy.",
                "verification": "Check link negotiation, LEDs, packet transfer, pair mapping, and connector shield continuity.",
            },
            "USB": {
                "description": "USB host/device connectivity, hub routing, downstream ports, VBUS distribution, and ESD protection.",
                "use": "Supports USB peripherals, modem data paths, service tools, storage, or firmware/debug workflows.",
                "how_it_works": "Differential data pairs and VBUS pass through switching, hub, and protection circuitry before reaching connectors or modules.",
                "how_to_use": "Attach one USB device at a time during bring-up and avoid exceeding the validated VBUS current budget.",
                "verification": "Confirm VBUS voltage, D+/D- continuity, hub reset, enumeration, and current-limit behavior.",
            },
            "HDMI": {
                "description": "Display output section with high-speed lanes, hotplug detect, DDC, CEC, and HDMI 5 V support.",
                "use": "Drives an external monitor for UI, commissioning, diagnostics, or product display output.",
                "how_it_works": "High-speed TMDS pairs carry video while DDC and hotplug lines coordinate display detection and configuration.",
                "how_to_use": "Use a short known-good cable and connect the display after base rails are stable.",
                "verification": "Check HDMI 5 V, hotplug, DDC SCL/SDA, CEC continuity, and stable display detection.",
            },
            "Wireless/SIM": {
                "description": "Cellular/GNSS or wireless modem area with SIM card, enable/reset pins, status LEDs, UART/USB paths, and modem power.",
                "use": "Provides cellular data, GNSS location, network telemetry, remote monitoring, or field connectivity.",
                "how_it_works": "The host controls modem power/reset/enable lines while SIM, USB/UART, and antenna paths support network registration and data transfer.",
                "how_to_use": "Install approved antenna and SIM hardware, verify modem supply, then test registration using the intended firmware.",
                "verification": "Check modem rails, SIM voltage, SIM clock/data/reset, UART/USB communication, status LEDs, and RF certification evidence.",
            },
            "RS485": {
                "description": "Industrial differential serial bus with transceiver, A/B lines, termination, surge/ESD protection, and direction control.",
                "use": "Connects to field devices, meters, controllers, sensors, or industrial communication networks.",
                "how_it_works": "The transceiver converts logic TX/RX into differential A/B signaling while termination and protection handle cable behavior.",
                "how_to_use": "Confirm A/B polarity, cable shield/grounding policy, and termination before connecting field wiring.",
                "verification": "Perform idle bias, termination, loopback, DE/RE timing, surge-protection, and cable communication tests.",
            },
            "GPIO Header": {
                "description": "Expansion header exposing logic-level signals and board control lines.",
                "use": "Supports sensors, indicators, debug wiring, low-speed controls, or customer expansion hardware.",
                "how_it_works": "Header pins connect host GPIO or bus signals to external circuits with voltage and direction constraints.",
                "how_to_use": "Treat every pin as engineering-only until voltage, direction, pull state, and firmware mapping are confirmed.",
                "verification": "Measure idle voltage, confirm pull-ups/pull-downs, check firmware mapping, and test one signal at a time.",
            },
            "RTC": {
                "description": "Real-time clock section with oscillator, backup battery path, I2C control, and optional interrupt.",
                "use": "Maintains time across power cycles and supports scheduled wake, logs, or timestamped events.",
                "how_it_works": "A low-power clock IC uses a crystal and backup source to preserve time when main power is removed.",
                "how_to_use": "Install the approved backup cell, initialize time over I2C, and validate retention after power removal.",
                "verification": "Check oscillator start, I2C address, backup voltage, retention time, and interrupt behavior.",
            },
            "Fan": {
                "description": "Thermal management interface with fan supply, tachometer, PWM/control, and controller or header pins.",
                "use": "Controls airflow for thermal stability in an enclosure or high-load operating mode.",
                "how_it_works": "The controller or host drives fan power/control and reads tach or alert feedback for fault detection.",
                "how_to_use": "Use a fan within the validated voltage/current rating and confirm direction before enclosure operation.",
                "verification": "Measure fan voltage/current, tach signal, speed response, stalled fan behavior, and alarm reporting.",
            },
            "PCIe": {
                "description": "High-speed expansion interface with clock, reset, transmit, receive, and request/control signals.",
                "use": "Supports high-speed expansion cards, modems, storage, or specialized peripheral modules.",
                "how_it_works": "Differential TX/RX lanes and reference clock lines provide high-speed communication under strict routing constraints.",
                "how_to_use": "Attach only compatible PCIe hardware after power and reset timing are validated.",
                "verification": "Check reset timing, reference clock, lane continuity, impedance review, and host enumeration.",
            },
            "Protection/ESD": {
                "description": "Protection network around external connectors and field wiring.",
                "use": "Reduces risk from ESD, surge, cable faults, and transient events during handling or installation.",
                "how_it_works": "TVS/ESD devices clamp transient voltages and route fault energy away from sensitive IC pins.",
                "how_to_use": "Do not bypass protection devices; connect external cables only after grounding and shield strategy are confirmed.",
                "verification": "Review diode orientation, continuity, leakage, connector location, and pre-compliance surge/ESD evidence.",
            },
        }
        return profiles.get(
            name,
            {
                "description": "Detected schematic block that requires hardware-specific confirmation.",
                "use": "Supports a board function inferred from signal names and component evidence.",
                "how_it_works": "Signals and support components route between the host, connectors, protection devices, and peripheral circuitry.",
                "how_to_use": "Use only after voltage level, direction, connector role, and firmware behavior are confirmed.",
                "verification": "Perform continuity, voltage, functional smoke, and documentation traceability checks.",
            },
        )

    @staticmethod
    def _operator_note_for_group(name: str) -> str:
        notes = {
            "Power": "Use only the validated input supply and current limit during first power-up.",
            "Ethernet": "Connect only to standard Ethernet equipment after pair and shield checks.",
            "USB": "Avoid overloading VBUS; attach one USB device at a time during commissioning.",
            "HDMI": "Use short known-good cables for initial display bring-up.",
            "Wireless/SIM": "Install SIM and antennas before modem network tests if required by the module.",
            "RS485": "Connect A/B field wiring only after polarity and termination are confirmed.",
            "GPIO Header": "Treat all header pins as engineering signals until labeled in the final product.",
            "RTC": "Fit backup battery only after polarity and battery type are confirmed.",
            "Fan": "Use a fan within the rated supply and current limit.",
        }
        return notes.get(name, "Operate only after connector role and voltage level are confirmed.")

    @staticmethod
    def _validation_note_for_group(name: str) -> str:
        notes = {
            "Power": "Measure all rails at no load, then with staged peripherals.",
            "Ethernet": "Check link LED, link negotiation, and continuity through magnetics.",
            "USB": "Check VBUS, D+/D- continuity, hub reset, and device enumeration.",
            "HDMI": "Check hotplug, DDC lines, 5 V switch, and display detection.",
            "Wireless/SIM": "Check modem power, UART/USB lines, SIM voltage, reset, and status LEDs.",
            "RS485": "Check idle bias, termination, TX/RX direction control, and loopback.",
            "GPIO Header": "Check pin voltage, direction, pull state, and mapping against firmware.",
            "RTC": "Check oscillator, backup supply, I2C access, and interrupt line.",
            "Fan": "Check fan voltage, tach signal, PWM/control behavior, and alarm path.",
        }
        return notes.get(name, "Perform continuity, voltage, and functional smoke tests.")

    @staticmethod
    def _drc_concern_for_group(name: str) -> str:
        concerns = {
            "Power": "Rail source, load capacity, sequencing, enable pins, PGOOD, shorts, and decoupling coverage.",
            "Regulators/Power Control": "Feedback network, compensation, thermal margin, inductor/diode ratings, and fault behavior.",
            "USB": "VBUS current limit, D+/D- polarity, ESD placement, shield policy, and controlled routing.",
            "Ethernet": "MDI pair mapping, magnetics, shield/chassis connection, ESD, and LED polarity.",
            "PCIe": "Reference clock, reset, lane polarity, impedance, return path, and length matching.",
            "CAN/Fieldbus": "CANH/CANL polarity, termination, transceiver supply, surge protection, and ground reference.",
            "RS485": "A/B polarity, termination, biasing, DE/RE direction control, TVS orientation, and isolation strategy.",
            "Debug/Programming": "Reset/boot straps, connector pinout, voltage level, pull state, and programming access.",
            "Protection/ESD": "Clamp direction, capacitance suitability, short return path, and protected-net coverage.",
        }
        return concerns.get(name, "Pin direction, voltage level, no-connect intent, pull state, protection, and firmware ownership.")

    @staticmethod
    def _drc_evidence_for_group(name: str) -> str:
        evidence = {
            "Power": "Rail budget, measured ramp/current/ripple data, regulator datasheets, and scope captures.",
            "Regulators/Power Control": "Datasheet design calculations, thermal estimate, BOM ratings, and bench fault tests.",
            "USB": "Layout rules, VBUS measurement, enumeration log, ESD part datasheet, and current-limit test.",
            "Ethernet": "Magnetics datasheet, pair continuity, link test, shield policy, and EMC pre-check.",
            "PCIe": "PCB stackup, impedance report, length-match report, reset timing, and enumeration log.",
            "CAN/Fieldbus": "Termination measurement, transceiver datasheet, loopback log, and surge/ESD evidence.",
            "RS485": "Termination/bias measurement, polarity test, loopback log, protection datasheet, and grounding plan.",
            "Debug/Programming": "Pinout table, programming log, reset/boot strap measurements, and firmware mapping.",
            "Protection/ESD": "Protected-net table, diode orientation check, leakage measurement, and pre-compliance evidence.",
        }
        return evidence.get(name, "Native schematic/netlist evidence, measured behavior, and owner-approved acceptance criteria.")

    @classmethod
    def _subsystem_notes(cls, name: str, analysis: dict[str, Any]) -> list[str]:
        rails = ", ".join(rail["net"] for rail in analysis["power_rails"][:8]) or "not detected"
        notes = {
            "Power": [
                f"Detected rails include {rails}. Verify voltage level and sequence before attaching peripherals.",
                "Use current-limited bring-up and record steady-state current after each peripheral is attached.",
                "Any unexpected current jump should stop the procedure until short circuits or incorrect loads are ruled out.",
            ],
            "Ethernet": [
                "Review differential pair mapping, magnetics, RJ45 shield connection, and LED indicator routing.",
                "Confirm link negotiation and packet transfer with a known-good cable and switch.",
                "Check shield/chassis connection policy before compliance testing.",
            ],
            "USB": [
                "Validate VBUS distribution, current limiting, ESD protection, and hub reset behavior.",
                "Attach downstream devices one at a time and confirm enumeration after each attachment.",
                "Check high-speed pair continuity and orientation before connecting external USB equipment.",
            ],
            "HDMI": [
                "Confirm HDMI 5 V, hotplug detect, DDC I2C, CEC, and differential pair continuity.",
                "Start with a short known-good HDMI cable and a tolerant display during first bring-up.",
                "Do not make EMC claims until cable emission and ESD behavior are tested.",
            ],
            "Wireless/SIM": [
                "Confirm modem supply, SIM voltage, SIM reset/clock/data routing, enable pins, reset pins, and status LEDs.",
                "Attach antennas and SIM hardware according to module requirements before network registration testing.",
                "Wireless operation requires carrier, antenna, RF exposure, and regional certification review.",
            ],
            "RS485": [
                "Confirm A/B polarity, 120 ohm termination, biasing, surge/TVS protection, and direction-control timing.",
                "Test loopback locally before connecting field wiring.",
                "Review grounding and surge protection before deployment in noisy environments.",
            ],
            "RTC": [
                "Confirm backup battery polarity, oscillator start-up, I2C address, and interrupt behavior.",
                "Record time retention behavior after main power is removed.",
            ],
            "Fan": [
                "Confirm fan supply voltage, load current, tachometer feedback, and control signal behavior.",
                "Test stalled or disconnected fan behavior before enclosure release.",
            ],
        }
        return notes.get(name, ["Confirm voltage level, connector role, firmware behavior, and safe operating limits."])

    @staticmethod
    def _key_part_note(reference: str, value: str) -> str:
        value_upper = value.upper()
        if "SIM" in reference or "SIM" in value_upper:
            return "Wireless/SIM module or connector candidate; confirm modem, SIM, and antenna requirements."
        if "USB" in reference or "USB" in value_upper:
            return "USB path component; confirm VBUS, ESD, and data-pair behavior."
        if "HDMI" in reference or "HDMI" in value_upper:
            return "Display path component; confirm HDMI 5 V, DDC, HPD, and cable behavior."
        if reference.startswith("U"):
            return "Integrated circuit candidate; confirm datasheet ratings and required support components."
        if reference.startswith(("H", "J", "RJ")):
            return "Connector/header candidate; confirm pinout, labeling, and mating hardware."
        return "Review against native CAD BOM before release."

    @staticmethod
    def _troubleshooting_rows(analysis: dict[str, Any]) -> list[tuple[str, str, str]]:
        rows = [
            ("Board does not power up", "Power input / rails", "Check input voltage, current limit, rail shorts, enable pins, and regulator heating."),
            ("CM4 does not boot", "CM4 power and reset", "Check CM4_5V, CM4_3V3, CM4_1V8, RUN/PG, GLOBAL_EN, boot mode, and module seating."),
            ("USB device not detected", "USB hub / VBUS", "Check VBUS, hub reset, D+/D- continuity, ESD devices, and one-device-at-a-time enumeration."),
            ("No HDMI display", "HDMI path", "Check HDMI_5V, hotplug, DDC SCL/SDA, cable quality, and display mode support."),
            ("Ethernet link missing", "Ethernet PHY/magnetics", "Check MDI pair routing, RJ45 magnetics, link LEDs, shield policy, and cable."),
            ("Modem/SIM not responding", "Wireless/SIM", "Check VBAT or modem supply, SIM1_VCC, reset, enable pins, UART/USB lines, and antenna/SIM seating."),
            ("RS485 communication fails", "RS485 transceiver", "Check A/B polarity, termination, DE/RE control, TVS devices, and field ground reference."),
            ("Fan does not spin or alarm active", "Fan controller/output", "Check FAN_VCC, fan load current, tach line, controller supply, and connector pinout."),
            ("RTC loses time", "RTC backup", "Check battery polarity, backup voltage, oscillator, I2C access, and RTC interrupt path."),
        ]
        group_names = {group.get("name") for group in analysis.get("interface_groups", [])}
        if "Wireless/SIM" not in group_names:
            rows = [row for row in rows if row[1] != "Wireless/SIM"]
        if "RS485" not in group_names:
            rows = [row for row in rows if row[1] != "RS485 transceiver"]
        if "Fan" not in group_names:
            rows = [row for row in rows if row[1] != "Fan controller/output"]
        return rows

    @staticmethod
    def _document_type_guidance(document_type: str) -> str:
        guidance = {
            "user_manual": (
                "- Present the board as an interface/base assembly until product enclosure, connector labeling, and firmware behavior are confirmed.\n"
                "- Use the power rail map and interface coverage sections as the primary operator-facing structure.\n"
                "- Keep unresolved high-speed, wireless, and field-wiring behaviors marked as engineering review items."
            ),
            "test_report": (
                "- Turn each functional test focus item into a measured pass/fail row before production release.\n"
                "- Verify every named rail at power-up before attaching external loads.\n"
                "- Record measured voltages, signal continuity, protection behavior, thermal state, and board revision."
            ),
            "drc_report": (
                "- Treat PDF-based DRC as a professional pre-check, not an authoritative native CAD DRC pass.\n"
                "- Close every blocker and major flaw with schematic, netlist, PCB, BOM, or bench evidence.\n"
                "- Run native ERC/DRC in the source EDA tool when project files are available."
            ),
            "compliance_brief": (
                "- Treat CE/FCC/RoHS status as not certified unless formal lab evidence is supplied.\n"
                "- Prioritize pre-compliance review around high-speed interfaces, wireless modules, field wiring, and ESD/surge protection.\n"
                "- Confirm all part-level regulatory and material declarations from supplier documentation."
            ),
            "bom": (
                "- Use the key part candidates and component family counts as a draft BOM seed only.\n"
                "- Reconcile every reference designator against the native CAD BOM export before procurement.\n"
                "- Confirm manufacturer part numbers, package codes, tolerances, ratings, and lifecycle status."
            ),
        }
        return guidance.get(document_type, "- Review source evidence and confirm missing engineering values before release.")
