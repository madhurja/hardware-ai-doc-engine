from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SkillRuleEngine:
    """Evidence-triggered review gates distilled from the schematic/PCB skill pack."""

    DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "skill_rules.json"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = Path(rules_path) if rules_path else self.DEFAULT_RULES_PATH
        self.rules = self._load_rules()

    def build_review_gates(
        self,
        text: str,
        power_rails: list[dict[str, str]],
        interface_groups: list[dict[str, Any]],
        component_counts: dict[str, int],
        key_parts: list[dict[str, str]],
        risk_flags: list[str],
    ) -> list[dict[str, Any]]:
        normalized_text = text.upper()
        group_names = {str(group.get("name", "")).upper() for group in interface_groups}
        gates = []

        for rule in self.rules.get("gates", []):
            matched = self._match_rule(rule, normalized_text, group_names, component_counts, key_parts)
            if not matched:
                continue

            evidence = self._evidence_for_rule(
                rule,
                matched,
                power_rails,
                interface_groups,
                component_counts,
                key_parts,
                risk_flags,
            )
            gates.append(
                {
                    "id": rule["id"],
                    "title": rule["title"],
                    "priority": rule.get("priority", "P2"),
                    "domain": rule.get("domain", "Engineering"),
                    "source_skill": rule.get("source_skill", "skill-pack"),
                    "objective": rule.get("objective", "Review required."),
                    "checklist": rule.get("checklist", [])[:6],
                    "evidence": evidence,
                }
            )

        return sorted(gates, key=lambda gate: (self._priority_rank(gate["priority"]), gate["title"]))[:18]

    @staticmethod
    def summarize_gates(gates: list[dict[str, Any]]) -> dict[str, Any]:
        by_domain: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        for gate in gates:
            by_domain[gate.get("domain", "Engineering")] = by_domain.get(gate.get("domain", "Engineering"), 0) + 1
            by_priority[gate.get("priority", "P2")] = by_priority.get(gate.get("priority", "P2"), 0) + 1
        return {
            "gate_count": len(gates),
            "by_domain": by_domain,
            "by_priority": by_priority,
        }

    def _load_rules(self) -> dict[str, Any]:
        if not self.rules_path.exists():
            return {"version": "missing", "gates": []}
        return json.loads(self.rules_path.read_text(encoding="utf-8"))

    @staticmethod
    def _match_rule(
        rule: dict[str, Any],
        normalized_text: str,
        group_names: set[str],
        component_counts: dict[str, int],
        key_parts: list[dict[str, str]],
    ) -> dict[str, list[str]] | None:
        matched_groups = [
            group for group in rule.get("trigger_groups", []) if str(group).upper() in group_names
        ]
        matched_keywords = [
            keyword
            for keyword in rule.get("trigger_keywords", [])
            if re.search(rf"(?<![A-Z0-9_]){re.escape(str(keyword).upper())}(?![A-Z0-9_])", normalized_text)
        ]
        matched_families = [
            family
            for family in rule.get("trigger_component_families", [])
            if component_counts.get(family, 0) > 0
        ]

        if rule.get("trigger_always") and (normalized_text or group_names or component_counts or key_parts):
            return {
                "groups": matched_groups,
                "keywords": matched_keywords,
                "families": matched_families,
                "always": ["project evidence present"],
            }
        if matched_groups or matched_keywords or matched_families:
            return {"groups": matched_groups, "keywords": matched_keywords, "families": matched_families}
        return None

    @staticmethod
    def _evidence_for_rule(
        rule: dict[str, Any],
        matched: dict[str, list[str]],
        power_rails: list[dict[str, str]],
        interface_groups: list[dict[str, Any]],
        component_counts: dict[str, int],
        key_parts: list[dict[str, str]],
        risk_flags: list[str],
    ) -> str:
        evidence = []
        if matched.get("groups"):
            evidence.append("groups: " + ", ".join(matched["groups"][:4]))
        if matched.get("keywords"):
            evidence.append("keywords: " + ", ".join(matched["keywords"][:5]))
        if matched.get("families"):
            families = [
                f"{family}={component_counts.get(family, 0)}" for family in matched["families"][:4]
            ]
            evidence.append("components: " + ", ".join(families))
        if rule["id"] == "power-integrity-pdn" and power_rails:
            evidence.append("rails: " + ", ".join(rail["net"] for rail in power_rails[:5]))
        if rule["id"] == "supply-chain-bom" and key_parts:
            evidence.append("key parts: " + ", ".join(part["reference"] for part in key_parts[:5]))
        if rule["id"] in {"emi-emc-external-ports", "protection-cascade"} and risk_flags:
            evidence.append("risk flags present")
        if not evidence and interface_groups:
            evidence.append("subsystems: " + ", ".join(group["name"] for group in interface_groups[:4]))
        return "; ".join(evidence) or "project evidence present"

    @staticmethod
    def _priority_rank(priority: str) -> int:
        return {"P1": 0, "P2": 1, "P3": 2}.get(priority, 3)
