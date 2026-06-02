from __future__ import annotations

import re
from collections import Counter
from typing import Any


class DrcRuleEngine:
    """PDF-evidence schematic DRC/ERC pre-check rules."""

    SEVERITY_RANK = {"blocker": 0, "major": 1, "minor": 2, "info": 3}

    def build_findings(
        self,
        text: str,
        nets: list[str],
        power_rails: list[dict[str, str]],
        interface_groups: list[dict[str, Any]],
        component_counts: dict[str, int],
        key_parts: list[dict[str, str]],
        risk_flags: list[str],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        upper = text.upper()
        group_names = {group.get("name") for group in interface_groups}

        def add(
            rule_id: str,
            severity: str,
            domain: str,
            check: str,
            finding: str,
            impact: str,
            fix: str,
            evidence_terms: list[str],
            confidence: int,
        ) -> None:
            findings.append(
                {
                    "id": rule_id,
                    "severity": severity,
                    "domain": domain,
                    "check": check,
                    "finding": finding,
                    "impact": impact,
                    "fix": fix,
                    "evidence": self._evidence_snippet(text, evidence_terms),
                    "confidence": confidence,
                }
            )

        if not power_rails:
            add(
                "DRC-PWR-001",
                "blocker",
                "Power",
                "Named rail discovery",
                "No named power rails were detected in the schematic evidence.",
                "The tool cannot build a safe bring-up, load, or rail validation plan.",
                "Add explicit rail labels or supply a native netlist/ERC report.",
                ["VCC", "VDD", "VIN", "3V3", "5V"],
                95,
            )

        if "GND" not in {net.upper() for net in nets} and "GND" not in upper:
            add(
                "DRC-PWR-002",
                "blocker",
                "Power",
                "Ground reference discovery",
                "No clear ground reference was detected.",
                "Electrical checks cannot verify returns, shields, protection paths, or rail measurements.",
                "Confirm GND/chassis symbols in native schematic or export a netlist.",
                ["GND", "CHASSIS", "AGND", "DGND"],
                90,
            )

        rail_norms = [self._normalize_rail(rail.get("net", "")) for rail in power_rails]
        if len(set(rail_norms)) >= 3:
            add(
                "DRC-PWR-010",
                "major",
                "Power",
                "Multi-rail sequencing",
                "Multiple voltage domains were detected and need explicit sequencing/current validation.",
                "Incorrect enable order or load timing can prevent boot or damage downstream devices.",
                "Add rail sequence table with source, enable, PGOOD, nominal voltage, tolerance, ramp, idle current, and peak current.",
                [rail.get("net", "") for rail in power_rails[:8]] + ["PGOOD", "ENABLE", "PWR_EN"],
                88,
            )

        if "Regulators/Power Control" in group_names and component_counts.get("inductors", 0) == 0:
            add(
                "DRC-PWR-020",
                "major",
                "Power",
                "Switching regulator support evidence",
                "Regulator evidence was detected, but inductor evidence was not extracted.",
                "A buck/boost regulator cannot be validated without magnetics, feedback, diode/FET, and compensation evidence.",
                "Verify regulator topology against datasheet and attach BOM/CAD evidence for inductors, feedback, compensation, and ratings.",
                ["TPS", "LM5164", "MP1476", "LDO", "DCDC", "INDUCTOR"],
                70,
            )

        if component_counts.get("integrated_circuits", 0) and component_counts.get("capacitors", 0) < max(3, component_counts.get("integrated_circuits", 0) // 2):
            add(
                "DRC-PWR-030",
                "minor",
                "Power",
                "Decoupling evidence density",
                "The extracted capacitor count looks low compared with detected IC count.",
                "Insufficient local decoupling can cause resets, EMI, ripple, and interface instability.",
                "Use native CAD/BOM to confirm every IC power pin has local decoupling and bulk capacitance where needed.",
                ["C1", "CAP", "100nF", "0.1uF", "VDD"],
                62,
            )

        high_speed = {"USB", "HDMI", "PCIe", "Ethernet", "SD/eMMC"} & group_names
        if high_speed:
            add(
                "DRC-SI-010",
                "major",
                "Signal Integrity",
                "High-speed routing evidence",
                "High-speed interfaces are present, but PDF schematic evidence cannot prove impedance, return paths, skew, or ESD placement.",
                "The schematic may pass logical review while the PCB still fails enumeration, EMC, or reliability.",
                "Attach PCB layout, stackup, impedance constraints, differential-pair length report, and connector ESD placement evidence.",
                sorted(high_speed) + ["D+", "D-", "TRD", "PCIE", "TMDS"],
                92,
            )

        if "USB" in group_names and "VBUS" not in upper:
            add(
                "DRC-USB-001",
                "major",
                "USB",
                "VBUS evidence",
                "USB was detected but VBUS evidence was not found.",
                "USB devices may not enumerate or may overload the power path.",
                "Confirm VBUS source, current limit, ESD, connector pinout, and measured voltage under load.",
                ["USB", "VBUS", "D+", "D-"],
                86,
            )

        if "Ethernet" in group_names and not any(term in upper for term in ("TRD0", "TRD1", "MDI", "RJ45")):
            add(
                "DRC-ETH-001",
                "major",
                "Ethernet",
                "Pair/magnetics evidence",
                "Ethernet was detected but pair or magnetics evidence is incomplete in extracted text.",
                "Pair swaps, missing magnetics, or shield errors can cause link failure or EMC problems.",
                "Verify MDI pair mapping, magnetics part, Bob Smith/shield policy, LED polarity, and link test evidence.",
                ["ETH", "TRD", "MDI", "RJ45"],
                76,
            )

        if "PCIe" in group_names:
            add(
                "DRC-PCIE-001",
                "major",
                "PCIe",
                "PCIe timing and lane evidence",
                "PCIe evidence requires reset timing, reference clock, lane polarity, and impedance checks.",
                "A schematic-only review cannot prove PCIe enumeration readiness.",
                "Attach PCIe reset/clock timing notes, layout length/impedance report, and host enumeration logs.",
                ["PCIE", "PER", "PET", "CLKREQ", "REFCLK"],
                82,
            )

        fieldbus = {"RS485", "CAN/Fieldbus"} & group_names
        if fieldbus:
            if not any(term in upper for term in ("120R", "120 R", "120OHM", "120 OHM", "TERM", "TERMINATION")):
                add(
                    "DRC-FIELD-010",
                    "major",
                    "Fieldbus",
                    "Termination evidence",
                    "Field-bus interface was detected but explicit termination evidence was not found.",
                    "Missing or wrong termination can cause reflections, communication failure, and field instability.",
                    "Confirm termination value, placement, bias network, jumper/config option, and measured bus idle state.",
                    sorted(fieldbus) + ["120R", "TERM"],
                    84,
                )
            if not any(term in upper for term in ("TVS", "SMAJ", "SMBJ", "ESD", "SURGE")):
                add(
                    "DRC-FIELD-020",
                    "major",
                    "Fieldbus",
                    "Surge/ESD protection evidence",
                    "Field-bus interface was detected without clear surge/ESD protection evidence.",
                    "External wiring can inject transients that damage transceivers or cause resets.",
                    "Add or confirm TVS/surge protection, return path, connector placement, and test evidence.",
                    sorted(fieldbus) + ["TVS", "SURGE", "ESD"],
                    82,
                )
            if not any(term in upper for term in ("ISO", "ISOLATED", "ISOLATOR", "DIGITAL ISOLATOR")):
                add(
                    "DRC-FIELD-030",
                    "minor",
                    "Fieldbus",
                    "Isolation/grounding strategy",
                    "Field-bus evidence does not show whether isolation or field-ground strategy is intentional.",
                    "Ground offsets and installation faults can create communication failures or damage.",
                    "Document isolation decision, cable shield policy, field ground reference, and surge test level.",
                    sorted(fieldbus) + ["ISO", "GND", "SHIELD"],
                    72,
                )

        external_groups = {"USB", "HDMI", "Ethernet", "RS485", "CAN/Fieldbus", "GPIO Header"} & group_names
        if external_groups and "Protection/ESD" not in group_names:
            add(
                "DRC-ESD-001",
                "major",
                "Protection",
                "External port protection coverage",
                "External interfaces were detected without extracted ESD/protection evidence.",
                "Cable handling and field wiring can damage IC pins or create latent failures.",
                "Add a protected-net table with TVS part, capacitance, clamp direction, connector distance, and test evidence.",
                sorted(external_groups) + ["TVS", "ESD"],
                85,
            )
        elif external_groups:
            add(
                "DRC-ESD-010",
                "minor",
                "Protection",
                "Protection placement/orientation proof",
                "Protection devices were detected, but PDF text cannot prove clamp orientation or placement distance.",
                "A listed TVS may still fail if it is reversed, too far from the connector, or has the wrong capacitance.",
                "Confirm protected nets, diode orientation, capacitance, connector distance, and return path in native CAD.",
                ["TVS", "SMAJ", "SMBJ", "ESD"],
                78,
            )

        if "I2C" in group_names and not any(term in upper for term in ("PULL", "4.7K", "2.2K", "10K", "PU")):
            add(
                "DRC-I2C-001",
                "minor",
                "I2C",
                "Pull-up evidence",
                "I2C was detected but pull-up evidence was not clear in extracted text.",
                "Missing or wrong pull-ups can prevent bus communication.",
                "Confirm SCL/SDA pull-up values, voltage domain, bus capacitance, and address conflicts.",
                ["I2C", "SCL", "SDA", "PULL", "4.7K"],
                68,
            )

        if "Debug/Programming" not in group_names and component_counts.get("integrated_circuits", 0):
            add(
                "DRC-DBG-001",
                "minor",
                "Debug",
                "Programming/debug evidence",
                "ICs were detected but no clear debug/programming block was found.",
                "Bring-up and recovery may be difficult without a verified programming path.",
                "Confirm JTAG/SWD/UART/BOOT/RESET access and document connector pinout.",
                ["JTAG", "SWD", "BOOT", "RESET", "UART"],
                70,
            )

        if key_parts:
            generic = [part for part in key_parts if str(part.get("value_or_part", "")).lower() in {"not provided", "unknown"}]
            if generic:
                add(
                    "DRC-BOM-001",
                    "minor",
                    "BOM",
                    "Incomplete key part identity",
                    "Some key parts do not have a reliable extracted part number.",
                    "Supply-chain, footprint, and datasheet validation remain incomplete.",
                    "Attach native BOM with MPN, manufacturer, package, rating, lifecycle, and approved alternates.",
                    [part.get("reference", "") for part in generic[:6]],
                    75,
                )

        for risk in risk_flags:
            add(
                "DRC-RISK-001",
                "major",
                "Risk Register",
                "Risk flag requires closure",
                risk,
                "Unclosed risk flags should block release documentation from being treated as final.",
                "Assign owner, evidence, test method, acceptance criterion, and release disposition.",
                [risk],
                80,
            )

        unique: dict[str, dict[str, Any]] = {}
        for finding in findings:
            key = finding["id"] + finding["finding"]
            unique.setdefault(key, finding)
        return sorted(unique.values(), key=lambda item: (self.SEVERITY_RANK.get(item["severity"], 9), item["domain"], item["id"]))[:40]

    @staticmethod
    def summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(finding.get("severity", "info") for finding in findings)
        domain_counts = Counter(finding.get("domain", "General") for finding in findings)
        penalty = counts.get("blocker", 0) * 25 + counts.get("major", 0) * 8 + counts.get("minor", 0) * 3
        return {
            "finding_count": len(findings),
            "score": max(0, 100 - penalty),
            "by_severity": dict(counts),
            "by_domain": dict(domain_counts),
        }

    @classmethod
    def reconcile_findings(
        cls,
        findings: list[dict[str, Any]],
        interface_groups: list[dict[str, Any]],
        power_rails: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        group_names = {group.get("name") for group in interface_groups}
        rail_count = len(power_rails)
        resolved_ids = set()

        if "Debug/Programming" in group_names:
            resolved_ids.add("DRC-DBG-001")
        if rail_count:
            resolved_ids.add("DRC-PWR-001")

        reconciled = []
        for finding in findings:
            if finding.get("id") in resolved_ids:
                continue
            reconciled.append(finding)
        return sorted(
            reconciled,
            key=lambda item: (cls.SEVERITY_RANK.get(item.get("severity", "info"), 9), item.get("domain", ""), item.get("id", "")),
        )

    @classmethod
    def build_coverage_matrix(
        cls,
        findings: list[dict[str, Any]],
        interface_groups: list[dict[str, Any]],
        power_rails: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        metadata = metadata or {}
        group_names = {group.get("name") for group in interface_groups}
        finding_ids = {finding.get("id") for finding in findings}

        rows = [
            cls._coverage_row(
                "Power rails",
                "Detected" if power_rails else "Missing",
                ", ".join(rail.get("net", "") for rail in power_rails[:8]) or "No named rails",
                "Add native netlist and measured rail table for release.",
            ),
            cls._coverage_row(
                "Firmware traceability",
                "Detected" if metadata.get("code_files_scanned") else "Missing",
                f"{metadata.get('code_files_scanned', 0)} source file(s)",
                "Add firmware pin map, boot behavior, reset behavior, and interface ownership.",
            ),
            cls._coverage_row(
                "PCB/BOM evidence",
                "Detected" if metadata.get("pcb_files_scanned") else "Missing",
                f"{metadata.get('pcb_files_scanned', 0)} PCB/BOM file(s)",
                "Add PCB layout, BOM, placement, stackup, DRC, ERC, and fabrication outputs.",
            ),
            cls._coverage_row(
                "High-speed layout",
                "Needs native CAD" if {"USB", "HDMI", "PCIe", "Ethernet", "SD/eMMC"} & group_names else "Not detected",
                ", ".join(sorted({"USB", "HDMI", "PCIe", "Ethernet", "SD/eMMC"} & group_names)) or "No high-speed groups",
                "Attach impedance, length-match, pair-polarity, return-path, and ESD placement evidence.",
            ),
            cls._coverage_row(
                "Field-bus robustness",
                "Incomplete" if {"DRC-FIELD-010", "DRC-FIELD-020", "DRC-FIELD-030"} & finding_ids else ("Detected" if {"RS485", "CAN/Fieldbus"} & group_names else "Not detected"),
                ", ".join(sorted({"RS485", "CAN/Fieldbus"} & group_names)) or "No field bus",
                "Close termination, bias, surge/ESD, isolation, and grounding evidence.",
            ),
            cls._coverage_row(
                "Debug/programming",
                "Detected" if "Debug/Programming" in group_names else "Incomplete",
                "Debug/Programming group present" if "Debug/Programming" in group_names else "No clear debug/programming group",
                "Confirm JTAG/SWD/UART/BOOT/RESET access and connector pinout.",
            ),
            cls._coverage_row(
                "Protection/ESD",
                "Needs native CAD" if "Protection/ESD" in group_names else "Incomplete",
                "Protection devices detected" if "Protection/ESD" in group_names else "No protection group",
                "Confirm protected nets, TVS orientation, capacitance, placement distance, and return path.",
            ),
        ]
        return rows

    @staticmethod
    def _coverage_row(domain: str, status: str, evidence: str, next_step: str) -> dict[str, str]:
        return {
            "domain": domain,
            "status": status,
            "evidence": evidence,
            "next_step": next_step,
        }

    @staticmethod
    def _normalize_rail(value: str) -> str:
        return value.upper().replace(".", "").lstrip("+")

    @staticmethod
    def _evidence_snippet(text: str, terms: list[str]) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        for term in terms:
            if not term:
                continue
            match = re.search(re.escape(str(term)), compact, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 70)
                end = min(len(compact), match.end() + 100)
                return compact[start:end]
        return "Evidence inferred from extracted schematic text."
