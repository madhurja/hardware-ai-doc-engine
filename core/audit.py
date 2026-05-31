from __future__ import annotations

from collections import Counter
from typing import Any


class QualityAuditEngine:
    """Finds evidence flaws that block professional hardware documentation."""

    RELEASE_BLOCKED = "Blocked: evidence required before release"
    ENGINEERING_REVIEW = "Engineering review required"
    DRAFT_READY = "Draft ready after manual review"
    STRONG_EVIDENCE = "Strong evidence package"

    def build_audit(self, profile: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        flaws: list[dict[str, str]] = []
        metadata = profile.get("metadata") or {}
        groups = {group.get("name") for group in analysis.get("interface_groups", [])}
        rails = analysis.get("power_rails") or []
        readiness = int(analysis.get("readiness_score") or 0)

        def add(severity: str, area: str, flaw: str, impact: str, fix: str, evidence: str) -> None:
            flaws.append(
                {
                    "severity": severity,
                    "area": area,
                    "flaw": flaw,
                    "impact": impact,
                    "fix": fix,
                    "evidence": evidence,
                }
            )

        if not metadata.get("schematic_files_scanned"):
            add(
                "blocker",
                "Evidence intake",
                "No schematic evidence was scanned.",
                "The engine cannot safely infer rails, interfaces, connectors, or review gates.",
                "Upload at least one schematic PDF or exported schematic manifest.",
                "schematic_files_scanned=0",
            )
        if not rails:
            add(
                "blocker",
                "Power safety",
                "No named power rails were detected.",
                "Bring-up instructions and acceptance checks cannot be trusted without voltage-domain evidence.",
                "Add or export explicit rail labels such as 3V3, 5V, VBAT, VDD_1V8, or board-specific rail names.",
                "power_rails=0",
            )
        if not metadata.get("code_files_scanned"):
            add(
                "major",
                "Firmware traceability",
                "No firmware source was included.",
                "Pin maps, boot behavior, status LEDs, reset handling, and interface use remain unverified.",
                "Add firmware source or a pin/function manifest for the board revision under test.",
                "code_files_scanned=0",
            )
        if not metadata.get("pcb_files_scanned"):
            add(
                "major",
                "PCB/BOM traceability",
                "No PCB or BOM export was included.",
                "Footprints, routing, alternate parts, and manufacturing readiness cannot be confirmed.",
                "Add native BOM, placement, netlist, PCB, or fabrication exports.",
                "pcb_files_scanned=0",
            )
        if readiness < 40:
            add(
                "blocker",
                "Readiness score",
                "Evidence readiness is below professional draft level.",
                "Generated text would be too speculative for customer or release use.",
                "Increase evidence coverage with schematic, firmware, PCB/BOM, and measured test data.",
                f"readiness_score={readiness}",
            )
        elif readiness < 70:
            add(
                "major",
                "Readiness score",
                "Evidence readiness is still low.",
                "The package is useful for internal review but not release-grade.",
                "Resolve the largest evidence gaps before using the output externally.",
                f"readiness_score={readiness}",
            )

        for risk in analysis.get("risk_flags") or []:
            severity = "major"
            if any(token in risk.lower() for token in ("high-speed", "wireless", "mixed-voltage", "field wiring")):
                severity = "major"
            add(
                severity,
                "Engineering risk",
                risk,
                "This risk can create board-spin, field-failure, compliance, or support problems if not tested.",
                "Convert this risk into a measured validation row with owner, method, acceptance, and evidence attachment.",
                "risk_flags",
            )

        high_speed_groups = {"USB", "HDMI", "PCIe", "Ethernet", "SD/eMMC"} & groups
        if high_speed_groups and not metadata.get("pcb_files_scanned"):
            add(
                "major",
                "Signal integrity",
                "High-speed interfaces are present but PCB routing evidence is missing.",
                "Impedance, length matching, pair polarity, return paths, and ESD placement cannot be reviewed.",
                "Add layout, stackup, differential-pair constraints, or SI validation evidence.",
                ", ".join(sorted(high_speed_groups)),
            )
        if "Wireless/SIM" in groups:
            add(
                "major",
                "Wireless release",
                "Wireless/SIM evidence needs a separate RF and carrier-readiness gate.",
                "A schematic-only wireless section cannot prove antenna, RF exposure, carrier, or regional compliance.",
                "Attach module datasheets, approved antenna data, SIM tests, registration logs, and certification assumptions.",
                "Wireless/SIM detected",
            )
        if {"RS485", "CAN/Fieldbus"} & groups:
            add(
                "major",
                "Field wiring",
                "Field-bus wiring needs surge, grounding, isolation, and termination proof.",
                "Installation variation can cause failures even when the schematic is logically correct.",
                "Record A/B or CAN polarity, termination, biasing, cable shield strategy, and protection tests.",
                ", ".join(sorted({"RS485", "CAN/Fieldbus"} & groups)),
            )

        p1_gates = [gate for gate in analysis.get("skill_review_gates", []) if gate.get("priority") == "P1"]
        if p1_gates:
            gate_names = ", ".join(gate.get("title", "P1 gate") for gate in p1_gates[:4])
            add(
                "minor",
                "Review gates",
                "Priority review gates are open.",
                "The document should stay in engineering-review status until the gates have measured evidence.",
                "Attach test results or CAD/BOM proof for each P1 gate.",
                gate_names,
            )

        counts = Counter(flaw["severity"] for flaw in flaws)
        release_status = self._release_status(counts, readiness)
        return {
            "release_status": release_status,
            "quality_score": self._quality_score(counts, readiness),
            "counts": {
                "blocker": counts.get("blocker", 0),
                "major": counts.get("major", 0),
                "minor": counts.get("minor", 0),
            },
            "flaws": flaws[:24],
            "next_actions": [flaw["fix"] for flaw in flaws[:6]],
        }

    @classmethod
    def _release_status(cls, counts: Counter[str], readiness: int) -> str:
        if counts.get("blocker", 0):
            return cls.RELEASE_BLOCKED
        if counts.get("major", 0) or readiness < 80:
            return cls.ENGINEERING_REVIEW
        if readiness < 92:
            return cls.DRAFT_READY
        return cls.STRONG_EVIDENCE

    @staticmethod
    def _quality_score(counts: Counter[str], readiness: int) -> int:
        penalty = counts.get("blocker", 0) * 20 + counts.get("major", 0) * 8 + counts.get("minor", 0) * 3
        return max(0, min(100, readiness - penalty))
