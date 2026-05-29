from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
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
            f"| {pin.get('signal_name', 'unknown')} | {pin.get('physical_pin', 'unknown')} | {pin.get('source_file', '')} |"
            for pin in profile.detected_pins
        ) or "| No pin mappings detected | Not provided | Not provided |"

        peripheral_rows = "\n".join(
            f"| {item.get('name', 'unknown')} | {item.get('configuration', 'not provided')} | {item.get('source_file', '')} |"
            for item in profile.peripherals
        ) or "| No peripherals detected | Not provided | Not provided |"

        schematic_sections = self._format_manifest_sections(profile.schematics, "Schematic")
        pcb_sections = self._format_manifest_sections(profile.pcb, "PCB")
        guidance = self._document_type_guidance(document_type)

        return f"""# {document_type.replace('_', ' ').title()}

## Scope
This local draft was generated from the supplied hardware evidence. It preserves strict technical bounds and marks anything not present in the source files as evidence required.

## Hardware Profile Summary
- Code files scanned: {profile.metadata.get('code_files_scanned', 0)}
- Schematic files scanned: {profile.metadata.get('schematic_files_scanned', 0)}
- PCB files scanned: {profile.metadata.get('pcb_files_scanned', 0)}
- Detected pins: {profile.metadata.get('pin_count', len(profile.detected_pins))}
- Detected peripherals: {profile.metadata.get('peripheral_count', len(profile.peripherals))}

## Detected Pin Map
| Signal | Physical Pin | Source |
| --- | --- | --- |
{pin_rows}

## Detected Peripheral Map
| Peripheral | Configuration | Source |
| --- | --- | --- |
{peripheral_rows}

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
    def _format_manifest_sections(manifests: list[dict[str, Any]], label: str) -> str:
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

            nets = manifest.get("detected_nets") or []
            if nets:
                sections.append("#### Detected Nets")
                sections.append(", ".join(nets[:40]))

            components = manifest.get("detected_components") or []
            if components:
                sections.append("#### Component Snapshot")
                sections.append("| Reference | Value / Part |")
                sections.append("| --- | --- |")
                for component in components[:35]:
                    sections.append(
                        f"| {component.get('reference', 'unknown')} | {component.get('value_or_part', 'not provided')} |"
                    )

            pages = manifest.get("pages") or []
            if pages:
                sections.append("#### Page Index")
                sections.append("| Page | Inferred Title | Extracted Evidence |")
                sections.append("| --- | --- | --- |")
                for page in pages[:12]:
                    excerpt = str(page.get("text_excerpt", "")).replace("|", "/")[:180]
                    sections.append(f"| {page.get('page')} | {page.get('title', 'Untitled')} | {excerpt} |")

        return "\n".join(sections)

    @staticmethod
    def _document_type_guidance(document_type: str) -> str:
        guidance = {
            "user_manual": (
                "- Treat the board as a hardware control/evaluation assembly until product usage context is confirmed.\n"
                "- Document power input, regulator outputs, indicator LEDs, feedback inputs, and MCU-related rails as observed.\n"
                "- Do not publish operating procedures until connector functions and firmware behavior are confirmed."
            ),
            "test_report": (
                "- Verify every named rail at power-up before attaching external loads.\n"
                "- Validate LED indicators, feedback paths, protection diodes, connectors, and regulator power-good behavior.\n"
                "- Record measured voltages, ripple, thermal state, and pass/fail evidence per board revision."
            ),
            "compliance_brief": (
                "- Treat CE/FCC/RoHS status as not certified unless formal lab evidence is supplied.\n"
                "- Use the schematic evidence to prepare pre-compliance checks for input protection, emissions risks, and restricted materials.\n"
                "- Confirm automotive or industrial rating claims from component datasheets before customer release."
            ),
            "bom": (
                "- Use the component snapshot as a draft BOM seed only.\n"
                "- Reconcile every reference designator against the native CAD BOM export before procurement.\n"
                "- Confirm manufacturer part numbers, tolerances, packages, and lifecycle status."
            ),
        }
        return guidance.get(document_type, "- Review source evidence and confirm missing engineering values before release.")
