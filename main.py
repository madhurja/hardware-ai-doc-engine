from __future__ import annotations

import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from core.exporter import PDFExporter
from core.generator import DocGenerationEngine
from core.parser import HardwareManifestParser


DOCUMENT_TYPES = ("user_manual", "test_report", "compliance_brief", "bom")
TYPE_CHOICES = (*DOCUMENT_TYPES, "all")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local hardware documentation PDFs.")
    parser.add_argument("--type", choices=TYPE_CHOICES, default="user_manual", help="Document package type.")
    parser.add_argument("--code-dir", default="input_drop/code", help="Folder containing firmware source files.")
    parser.add_argument("--schematic-dir", default="input_drop/schematics", help="Folder containing schematic manifests.")
    parser.add_argument("--pcb-dir", default="input_drop/pcb", help="Folder containing PCB/BOM manifests.")
    parser.add_argument("--output-dir", default="output_packages", help="Folder for generated deliverables.")
    parser.add_argument("--html-only", action="store_true", help="Write HTML instead of PDF.")
    parser.add_argument("--local-only", action="store_true", help="Never call external AI APIs; generate from local evidence only.")
    parser.add_argument("--skip-git", action="store_true", help="Skip the local git snapshot step.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args()

    print_progress(1, "Scanning local input folders")
    parser = HardwareManifestParser(args.code_dir, args.schematic_dir, args.pcb_dir)
    hardware_profile = parser.compile_hardware_profile()

    targets = DOCUMENT_TYPES if args.type == "all" else (args.type,)

    print_progress(2, "Generating bounded technical draft")
    generator = DocGenerationEngine(api_key="" if args.local_only else None)

    print_progress(3, "Compiling enterprise document")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    exporter = PDFExporter()
    output_paths = []
    for document_type in targets:
        markdown = generator.generate_document(document_type, hardware_profile)
        title = document_type.replace("_", " ").title()
        if args.html_only:
            output_path = exporter.export_html(title, markdown, output_dir / f"{document_type}_{timestamp}.html")
        else:
            output_path = exporter.export_pdf(title, markdown, output_dir / f"{document_type}_{timestamp}.pdf")
        output_paths.append(output_path)

    print_progress(4, "Recording local portfolio snapshot")
    if not args.skip_git:
        git_snapshot()

    print("\nDone. Documents created:")
    for output_path in output_paths:
        print(f"- {output_path}")
    if not args.skip_git:
        print("GitHub setup tip: add your remote with `git remote add origin <YOUR_GITHUB_REPOSITORY_URL>` when ready.")
    return 0


def print_progress(step: int, message: str) -> None:
    total = 4
    filled = int((step / total) * 24)
    bar = "#" * filled + "-" * (24 - filled)
    print(f"[{bar}] {step}/{total} {message}")


def git_snapshot() -> None:
    if not Path(".git").exists():
        run_git(["git", "init"])

    run_git(["git", "add", "."])
    if has_staged_changes():
        run_git(["git", "commit", "-m", "feat: complete stable production deployment of local AI documentation node"])
    else:
        print("No git changes to commit.")


def has_staged_changes() -> bool:
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    return result.returncode == 1


def run_git(command: list[str]) -> None:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        logging.warning("Git command failed: %s", (result.stderr or result.stdout).strip())


if __name__ == "__main__":
    raise SystemExit(main())
