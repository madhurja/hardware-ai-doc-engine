from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


class ImprovementMemory:
    """Local run memory that improves future guidance without self-modifying code."""

    DEFAULT_PATH = Path(__file__).resolve().parents[1] / "local_state" / "improvement_memory.json"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else self.DEFAULT_PATH

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_memory()
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_memory()

    def summary(self) -> dict[str, Any]:
        memory = self.load()
        return {
            "runs_total": memory.get("runs_total", 0),
            "average_readiness_score": memory.get("average_readiness_score", 0),
            "best_readiness_score": memory.get("best_readiness_score", 0),
            "last_run": memory.get("last_run"),
            "recurring_risks": self._top_counter(memory.get("recurring_risks", {}), 5),
            "recurring_gates": self._top_counter(memory.get("recurring_gates", {}), 6),
            "recurring_gaps": self._top_counter(memory.get("recurring_gaps", {}), 6),
            "adaptive_hints": memory.get("adaptive_hints", [])[:6],
        }

    def record_generation(
        self,
        profile: dict[str, Any],
        document_types: list[str] | tuple[str, ...],
        outputs: list[dict[str, Any]] | list[Path],
        run_label: str = "document_generation",
    ) -> dict[str, Any]:
        memory = self.load()
        analysis = self._collect_analysis(profile)
        run = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "label": run_label,
            "document_types": list(document_types),
            "outputs": [self._output_name(item) for item in outputs],
            "readiness_score": analysis["readiness_score"],
            "evidence_gaps": analysis["evidence_gaps"],
            "risk_flags": analysis["risk_flags"],
            "skill_gates": analysis["skill_gates"],
            "subsystems": analysis["subsystems"],
            "rails": analysis["rails"],
        }

        runs = memory.setdefault("runs", [])
        runs.append(run)
        memory["runs"] = runs[-25:]
        memory["runs_total"] = int(memory.get("runs_total", 0)) + 1
        memory["last_run"] = run

        scores = [item.get("readiness_score", 0) for item in memory["runs"] if item.get("readiness_score")]
        memory["average_readiness_score"] = round(sum(scores) / len(scores)) if scores else 0
        memory["best_readiness_score"] = max(scores) if scores else 0

        memory["recurring_risks"] = self._merge_counter(memory.get("recurring_risks", {}), analysis["risk_flags"])
        memory["recurring_gates"] = self._merge_counter(memory.get("recurring_gates", {}), analysis["skill_gates"])
        memory["recurring_gaps"] = self._merge_counter(memory.get("recurring_gaps", {}), analysis["evidence_gaps"])
        memory["adaptive_hints"] = self._build_hints(memory)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(memory, indent=2), encoding="utf-8")
        return self.summary()

    @staticmethod
    def _collect_analysis(profile: dict[str, Any]) -> dict[str, Any]:
        manifests = [*profile.get("schematics", []), *profile.get("pcb", [])]
        readiness_scores = []
        risk_flags = []
        gates = []
        subsystems = []
        rails = []
        gaps = []

        for manifest in manifests:
            analysis = manifest.get("analysis") or {}
            score = analysis.get("readiness_score")
            if isinstance(score, (int, float)):
                readiness_scores.append(int(score))
            for risk in analysis.get("risk_flags") or []:
                if risk not in risk_flags:
                    risk_flags.append(risk)
            for gate in analysis.get("skill_review_gates") or []:
                title = gate.get("title")
                if title and title not in gates:
                    gates.append(title)
            for group in analysis.get("interface_groups") or []:
                name = group.get("name")
                if name and name not in subsystems:
                    subsystems.append(name)
            for rail in analysis.get("power_rails") or []:
                net = rail.get("net")
                if net and net not in rails:
                    rails.append(net)

        metadata = profile.get("metadata") or {}
        if not metadata.get("code_files_scanned"):
            gaps.append("No firmware source was included for pin and boot-behavior verification.")
        if not metadata.get("pcb_files_scanned"):
            gaps.append("No PCB/BOM export was included for footprint, layout, and supply-chain confirmation.")
        if not rails:
            gaps.append("No named power rails were detected.")
        if not gates:
            gaps.append("No schematic/PCB skill gates were triggered.")
        if not any(name in subsystems for name in ("Debug/Programming", "UART", "JTAG")):
            gaps.append("Debug or programming evidence is incomplete.")

        return {
            "readiness_score": round(sum(readiness_scores) / len(readiness_scores)) if readiness_scores else 0,
            "risk_flags": risk_flags[:12],
            "skill_gates": gates[:18],
            "subsystems": subsystems[:18],
            "rails": rails[:18],
            "evidence_gaps": gaps[:12],
        }

    @classmethod
    def _build_hints(cls, memory: dict[str, Any]) -> list[str]:
        risks = Counter(memory.get("recurring_risks", {}))
        gates = Counter(memory.get("recurring_gates", {}))
        gaps = Counter(memory.get("recurring_gaps", {}))
        hints = []

        if risks:
            hints.append("Recurring risk focus: " + risks.most_common(1)[0][0])
        if gates:
            hints.append("Most common review gate: " + gates.most_common(1)[0][0])
        if gaps:
            hints.append("Most common evidence gap: " + gaps.most_common(1)[0][0])
        if memory.get("average_readiness_score", 0) < 70:
            hints.append("Improve precision by adding PCB/BOM exports, firmware pin maps, and measured rail data.")
        else:
            hints.append("Maintain precision by reconciling generated gates against CAD, BOM, and bench evidence.")
        hints.append("Never promote generated text to release status until measurements and revision data are attached.")
        return hints[:6]

    @staticmethod
    def _merge_counter(existing: dict[str, int], values: list[str]) -> dict[str, int]:
        counter = Counter(existing)
        counter.update(values)
        return dict(counter.most_common(30))

    @staticmethod
    def _top_counter(counter: dict[str, int], limit: int) -> list[dict[str, Any]]:
        return [{"item": key, "count": value} for key, value in Counter(counter).most_common(limit)]

    @staticmethod
    def _output_name(item: dict[str, Any] | Path) -> str:
        if isinstance(item, Path):
            return item.name
        return str(item.get("name") or item.get("url") or item)

    @staticmethod
    def _empty_memory() -> dict[str, Any]:
        return {
            "runs_total": 0,
            "average_readiness_score": 0,
            "best_readiness_score": 0,
            "runs": [],
            "recurring_risks": {},
            "recurring_gates": {},
            "recurring_gaps": {},
            "adaptive_hints": [],
            "last_run": None,
        }
