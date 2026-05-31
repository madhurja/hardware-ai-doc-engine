from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus


@dataclass(frozen=True)
class PluginAction:
    label: str
    url: str
    kind: str = "open"


@dataclass(frozen=True)
class PluginDefinition:
    id: str
    name: str
    category: str
    description: str
    mode: str
    setup: str
    internet_required: bool = False
    requires_key: bool = False
    actions: list[PluginAction] = field(default_factory=list)


class PluginRegistry:
    """Catalogs safe local and internet-assisted integrations for the app."""

    def build_catalog(self, profile: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        plugins = [self._plugin_payload(plugin, analysis) for plugin in self._definitions()]
        research_pack = self.build_research_pack(profile, analysis)
        categories = sorted({plugin["category"] for plugin in plugins})
        return {
            "plugins": plugins,
            "categories": categories,
            "research_pack": research_pack,
            "summary": {
                "total": len(plugins),
                "internet_enabled": sum(1 for plugin in plugins if plugin["internet_required"]),
                "api_ready": sum(1 for plugin in plugins if plugin["requires_key"]),
                "research_links": sum(len(item["links"]) for item in research_pack["parts"])
                + len(research_pack["standards"])
                + len(research_pack["cad"]),
            },
        }

    def build_research_pack(self, profile: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        key_parts = self._key_part_queries(profile, analysis)
        groups = {group.get("name") for group in analysis.get("interface_groups", [])}
        gates = {gate.get("title") for gate in analysis.get("skill_review_gates", [])}

        parts = [
            {
                "reference": part["reference"],
                "query": part["query"],
                "links": self._part_links(part["query"]),
            }
            for part in key_parts[:10]
        ]

        standards = [
            {
                "label": "FCC equipment authorization",
                "reason": "Use for US radio and intentional/unintentional radiator research.",
                "url": "https://www.fcc.gov/oet/ea",
            },
            {
                "label": "EU harmonised standards",
                "reason": "Use for CE pathway and applicable directive/standard discovery.",
                "url": "https://single-market-economy.ec.europa.eu/single-market/european-standards/harmonised-standards_en",
            },
            {
                "label": "RoHS restricted substances",
                "reason": "Use for material compliance evidence planning.",
                "url": "https://environment.ec.europa.eu/topics/waste-and-recycling/rohs-directive_en",
            },
        ]
        if "Wireless/SIM" in groups:
            standards.append(
                {
                    "label": "Cellular module certification search",
                    "reason": "Wireless/SIM sections need module, antenna, carrier, and regional evidence.",
                    "url": self._search_url("cellular module certification antenna carrier requirements"),
                }
            )
        if {"USB", "HDMI", "PCIe", "Ethernet", "SD/eMMC"} & groups or "Signal Integrity Gate" in gates:
            standards.append(
                {
                    "label": "High-speed interface validation search",
                    "reason": "Use for impedance, length-match, return-path, and ESD evidence planning.",
                    "url": self._search_url("high speed PCB differential pair impedance length matching ESD validation"),
                }
            )

        cad = [
            {
                "label": "KiCad CLI documentation",
                "reason": "Use for future automated ERC, DRC, BOM, netlist, and plot/export plugins.",
                "url": "https://docs.kicad.org/master/en/cli/cli.html",
            },
            {
                "label": "KiCad PCB DRC command reference",
                "reason": "Use when native KiCad project files are added to the intake.",
                "url": "https://docs.kicad.org/master/en/cli/cli.html#_pcb_drc",
            },
        ]

        return {
            "parts": parts,
            "standards": standards,
            "cad": cad,
            "note": "Internet links open in the user's browser. API automation is prepared but requires provider credentials.",
        }

    @staticmethod
    def _definitions() -> list[PluginDefinition]:
        return [
            PluginDefinition(
                id="octopart_nexar",
                name="Octopart / Nexar",
                category="Supply Chain",
                description="Find datasheets, pricing, availability, manufacturer details, and alternates from part numbers.",
                mode="Internet search now, API-ready later",
                setup="Browser links work immediately. API automation needs Nexar credentials.",
                internet_required=True,
                requires_key=True,
                actions=[
                    PluginAction("Open Octopart", "https://octopart.com/"),
                    PluginAction("Nexar API info", "https://octopart.com/my/api"),
                ],
            ),
            PluginDefinition(
                id="digikey",
                name="DigiKey",
                category="Supply Chain",
                description="Check distributor product data, stock, pricing, lifecycle evidence, and datasheets.",
                mode="Internet search now, API-ready later",
                setup="Browser links work immediately. Product Information API use needs a DigiKey developer account.",
                internet_required=True,
                requires_key=True,
                actions=[
                    PluginAction("DigiKey API solutions", "https://www.digikey.com/en/resources/api-solutions"),
                    PluginAction("DigiKey developer portal", "https://developer.digikey.com/products"),
                ],
            ),
            PluginDefinition(
                id="mouser",
                name="Mouser",
                category="Supply Chain",
                description="Open part searches for pricing, stock, lifecycle clues, datasheets, and alternates.",
                mode="Internet search",
                setup="No local setup required for browser search links.",
                internet_required=True,
                actions=[PluginAction("Open Mouser", "https://www.mouser.com/")],
            ),
            PluginDefinition(
                id="lcsc",
                name="LCSC",
                category="Manufacturing",
                description="Check low-cost part availability and assembly-oriented supplier evidence.",
                mode="Internet search",
                setup="No local setup required for browser search links.",
                internet_required=True,
                actions=[PluginAction("Open LCSC", "https://www.lcsc.com/")],
            ),
            PluginDefinition(
                id="kicad_cli",
                name="KiCad CLI",
                category="EDA / CAD",
                description="Future-ready local automation for ERC, DRC, BOM, netlist, Gerber, and PDF exports.",
                mode="Local tool integration",
                setup="Install KiCad and make kicad-cli available on PATH for direct local automation.",
                actions=[PluginAction("KiCad CLI docs", "https://docs.kicad.org/master/en/cli/cli.html")],
            ),
            PluginDefinition(
                id="compliance_references",
                name="Compliance Reference Pack",
                category="Compliance",
                description="Quick access to FCC, CE, RoHS, EMC, and release-evidence research starting points.",
                mode="Internet reference",
                setup="No local setup required.",
                internet_required=True,
                actions=[
                    PluginAction("FCC equipment authorization", "https://www.fcc.gov/oet/ea"),
                    PluginAction("EU harmonised standards", "https://single-market-economy.ec.europa.eu/single-market/european-standards/harmonised-standards_en"),
                    PluginAction("RoHS directive", "https://environment.ec.europa.eu/topics/waste-and-recycling/rohs-directive_en"),
                ],
            ),
            PluginDefinition(
                id="openai_assisted_drafting",
                name="OpenAI Assisted Drafting",
                category="AI Drafting",
                description="Optional API-assisted drafting after local evidence extraction and quality audit.",
                mode="Optional API",
                setup="Set OPENAI_API_KEY only when cloud-assisted drafting is desired.",
                requires_key=True,
                actions=[PluginAction("OpenAI platform", "https://platform.openai.com/")],
            ),
            PluginDefinition(
                id="pwa_app_mode",
                name="PWA App Mode",
                category="App Access",
                description="Installable browser-app shell for easy Windows and Android access on the same network.",
                mode="Local browser app",
                setup="Run the Windows launcher, then install from Chrome or Edge.",
                actions=[PluginAction("Web app manifest reference", "https://developer.mozilla.org/en-US/docs/Web/Manifest")],
            ),
            PluginDefinition(
                id="quality_audit",
                name="Internal Quality Audit",
                category="Quality",
                description="Built-in blocker, major flaw, minor flaw, release status, and next-action scoring.",
                mode="Built in",
                setup="Always active; no internet or credentials required.",
            ),
        ]

    def _plugin_payload(self, plugin: PluginDefinition, analysis: dict[str, Any]) -> dict[str, Any]:
        status = "Ready"
        if plugin.id == "kicad_cli":
            status = "Installed" if shutil.which("kicad-cli") else "Not detected"
        elif plugin.id == "openai_assisted_drafting":
            status = "Configured" if os.getenv("OPENAI_API_KEY") else "Optional key missing"
        elif plugin.requires_key:
            status = "Browser ready; API key optional"

        actions = [{"label": action.label, "url": action.url, "kind": action.kind} for action in plugin.actions]
        if plugin.id in {"octopart_nexar", "digikey", "mouser", "lcsc"}:
            top_part = self._first_key_part(analysis)
            if top_part:
                actions.extend(self._supplier_actions(plugin.id, top_part))

        return {
            "id": plugin.id,
            "name": plugin.name,
            "category": plugin.category,
            "description": plugin.description,
            "mode": plugin.mode,
            "setup": plugin.setup,
            "internet_required": plugin.internet_required,
            "requires_key": plugin.requires_key,
            "status": status,
            "actions": actions,
        }

    def _key_part_queries(self, profile: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, str]]:
        parts = analysis.get("key_parts") or []
        if not parts:
            for manifest in [*profile.get("schematics", []), *profile.get("pcb", [])]:
                for component in manifest.get("detected_components") or []:
                    parts.append(component)
        queries = []
        seen: set[str] = set()
        for part in parts:
            reference = str(part.get("reference") or "").strip()
            value = str(part.get("value_or_part") or "").strip()
            if not reference and not value:
                continue
            query = value if value and value.lower() != "not provided" else reference
            if len(query) < 3 or query.upper() in seen:
                continue
            seen.add(query.upper())
            queries.append({"reference": reference or query, "query": query})
        return queries

    @staticmethod
    def _first_key_part(analysis: dict[str, Any]) -> str | None:
        parts = analysis.get("key_parts") or []
        for part in parts:
            value = str(part.get("value_or_part") or "").strip()
            reference = str(part.get("reference") or "").strip()
            if value and value.lower() != "not provided":
                return value
            if reference:
                return reference
        return None

    @classmethod
    def _part_links(cls, query: str) -> list[dict[str, str]]:
        encoded = quote_plus(query)
        return [
            {"label": "Datasheet search", "url": cls._search_url(f"{query} datasheet")},
            {"label": "Octopart", "url": f"https://octopart.com/search?q={encoded}"},
            {"label": "DigiKey", "url": f"https://www.digikey.com/en/products?keywords={encoded}"},
            {"label": "Mouser", "url": f"https://www.mouser.com/c/?q={encoded}"},
            {"label": "LCSC", "url": f"https://www.lcsc.com/search?q={encoded}"},
        ]

    @classmethod
    def _supplier_actions(cls, plugin_id: str, query: str) -> list[dict[str, str]]:
        lookup = {
            "octopart_nexar": ("Search top part", f"https://octopart.com/search?q={quote_plus(query)}"),
            "digikey": ("Search top part", f"https://www.digikey.com/en/products?keywords={quote_plus(query)}"),
            "mouser": ("Search top part", f"https://www.mouser.com/c/?q={quote_plus(query)}"),
            "lcsc": ("Search top part", f"https://www.lcsc.com/search?q={quote_plus(query)}"),
        }
        label, url = lookup[plugin_id]
        return [{"label": label, "url": url, "kind": "open"}]

    @staticmethod
    def _search_url(query: str) -> str:
        return f"https://www.google.com/search?q={quote_plus(query)}"
