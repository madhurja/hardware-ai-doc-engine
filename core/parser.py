from __future__ import annotations

import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedPin:
    signal_name: str
    physical_pin: str
    source_file: str
    line_number: int


@dataclass(frozen=True)
class DetectedPeripheral:
    name: str
    configuration: str
    source_file: str
    line_number: int


class HardwareManifestParser:
    """Builds a structured hardware profile from local firmware and manifests."""

    CODE_EXTENSIONS = {".c", ".h", ".cpp", ".ino"}
    MANIFEST_EXTENSIONS = {".csv", ".tsv", ".json", ".xml", ".net"}

    PIN_PATTERN = re.compile(r"#define\s+(\w+)\s+(GPIO_PIN_\d+|PA_\d+|PB_\d+|\d+)")
    SERIAL_PATTERN = re.compile(r"\bSerial(?:\d*)\.begin\((\d+)\)")
    SPI_PATTERN = re.compile(r"\bSPI\.begin\(\)")
    I2C_PATTERN = re.compile(r"\bWire\.begin\(([^)]*)\)")

    def __init__(
        self,
        code_dir: str | Path = "input_drop/code",
        schematic_dir: str | Path = "input_drop/schematics",
        pcb_dir: str | Path = "input_drop/pcb",
    ) -> None:
        self.code_dir = Path(code_dir)
        self.schematic_dir = Path(schematic_dir)
        self.pcb_dir = Path(pcb_dir)

    def compile_hardware_profile(self) -> dict[str, Any]:
        code_files = self._list_files(self.code_dir, self.CODE_EXTENSIONS)
        schematic_files = self._list_files(self.schematic_dir, self.MANIFEST_EXTENSIONS)
        pcb_files = self._list_files(self.pcb_dir, self.MANIFEST_EXTENSIONS)

        if not code_files and not schematic_files and not pcb_files:
            LOGGER.warning("No source files were found in input_drop folders.")

        detected_pins, peripherals = self._scan_code_files(code_files)
        schematic_parts = self._scan_manifest_files(schematic_files)
        pcb_parts = self._scan_manifest_files(pcb_files)

        return {
            "detected_pins": [asdict(pin) for pin in detected_pins],
            "peripherals": [asdict(peripheral) for peripheral in peripherals],
            "schematics": schematic_parts,
            "pcb": pcb_parts,
            "metadata": {
                "code_files_scanned": len(code_files),
                "schematic_files_scanned": len(schematic_files),
                "pcb_files_scanned": len(pcb_files),
                "pin_count": len(detected_pins),
                "peripheral_count": len(peripherals),
            },
        }

    def _scan_code_files(
        self,
        files: list[Path],
    ) -> tuple[list[DetectedPin], list[DetectedPeripheral]]:
        detected_pins: list[DetectedPin] = []
        peripherals: list[DetectedPeripheral] = []

        for path in files:
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line_number, line in enumerate(handle, 1):
                        pin_match = self.PIN_PATTERN.search(line)
                        if pin_match:
                            detected_pins.append(
                                DetectedPin(
                                    signal_name=pin_match.group(1),
                                    physical_pin=pin_match.group(2),
                                    source_file=str(path),
                                    line_number=line_number,
                                )
                            )

                        for peripheral in self._detect_peripherals(line, path, line_number):
                            peripherals.append(peripheral)
            except OSError as exc:
                LOGGER.warning("Could not read source file %s: %s", path, exc)

        return detected_pins, peripherals

    def _detect_peripherals(
        self,
        line: str,
        path: Path,
        line_number: int,
    ) -> list[DetectedPeripheral]:
        peripherals: list[DetectedPeripheral] = []

        serial_match = self.SERIAL_PATTERN.search(line)
        if serial_match:
            peripherals.append(
                DetectedPeripheral("Serial", f"baud={serial_match.group(1)}", str(path), line_number)
            )

        if self.SPI_PATTERN.search(line):
            peripherals.append(DetectedPeripheral("SPI", "begin()", str(path), line_number))

        i2c_match = self.I2C_PATTERN.search(line)
        if i2c_match:
            config = i2c_match.group(1).strip() or "default"
            peripherals.append(DetectedPeripheral("I2C", config, str(path), line_number))

        return peripherals

    def _scan_manifest_files(self, files: list[Path]) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        for path in files:
            try:
                if path.suffix.lower() in {".csv", ".tsv"}:
                    manifests.extend(self._read_table_manifest(path))
                elif path.suffix.lower() == ".json":
                    manifests.append({"source_file": str(path), "data": json.loads(path.read_text(encoding="utf-8"))})
                else:
                    manifests.append(self._read_xml_like_manifest(path))
            except (OSError, json.JSONDecodeError, ET.ParseError, UnicodeDecodeError) as exc:
                LOGGER.warning("Could not parse manifest %s: %s", path, exc)
        return manifests

    def _read_table_manifest(self, path: Path) -> list[dict[str, Any]]:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                rows.append({"source_file": str(path), "row": {key: value for key, value in row.items() if key}})
        return rows

    def _read_xml_like_manifest(self, path: Path) -> dict[str, Any]:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
        components = []
        for element in root.iter():
            attributes = dict(element.attrib)
            if attributes:
                components.append({"tag": self._strip_namespace(element.tag), "attributes": attributes})
        return {"source_file": str(path), "components": components[:250]}

    def _list_files(self, directory: Path, extensions: set[str]) -> list[Path]:
        if not directory.exists():
            LOGGER.warning("Input directory does not exist: %s", directory)
            return []
        files = [
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions and not path.name.startswith(".")
        ]
        if not files:
            LOGGER.debug("No supported files found in %s", directory)
        return sorted(files)

    @staticmethod
    def _strip_namespace(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
