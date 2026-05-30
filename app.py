from __future__ import annotations

import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.exporter import PDFExporter
from core.generator import DocGenerationEngine
from core.parser import HardwareManifestParser


ROOT = Path(__file__).resolve().parent
INPUT_ROOT = ROOT / "input_drop"
OUTPUT_DIR = ROOT / "output_packages"
STATIC_DIR = ROOT / "static"
DOCUMENT_TYPES = ("user_manual", "test_report", "compliance_brief", "bom")
UPLOAD_TARGETS = {
    "code": INPUT_ROOT / "code",
    "schematics": INPUT_ROOT / "schematics",
    "pcb": INPUT_ROOT / "pcb",
}


app = FastAPI(title="Hardware AI Documentation Engine", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker() -> FileResponse:
    response = FileResponse(STATIC_DIR / "service-worker.js", media_type="text/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.get("/api/status")
def status() -> dict:
    profile = _build_profile()
    return {
        "metadata": profile["metadata"],
        "analysis": _summarize_profile(profile),
        "outputs": _list_outputs(),
        "document_types": DOCUMENT_TYPES,
        "runtime": _runtime_links(),
        "app": {
            "name": "Hardware AI Documentation Engine",
            "version": app.version,
            "mode": "Local browser app",
        },
    }


@app.post("/api/upload")
async def upload_files(
    target: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
) -> dict:
    directory = UPLOAD_TARGETS.get(target)
    if directory is None:
        raise HTTPException(status_code=400, detail="Unsupported upload target.")

    directory.mkdir(parents=True, exist_ok=True)
    saved = []
    for upload in files:
        filename = _safe_filename(upload.filename or "upload.bin")
        destination = directory / filename
        content = await upload.read()
        destination.write_bytes(content)
        saved.append({"name": filename, "size": len(content), "target": target})
    return {"saved": saved, "status": "uploaded"}


@app.post("/api/generate")
def generate_documents(
    document_type: Annotated[str, Form()] = "user_manual",
    local_only: Annotated[bool, Form()] = True,
) -> dict:
    if document_type != "all" and document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported document type.")

    profile = _build_profile()
    targets = DOCUMENT_TYPES if document_type == "all" else (document_type,)
    generator = DocGenerationEngine(api_key="" if local_only else None)
    exporter = PDFExporter()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    created = []

    for target in targets:
        markdown = generator.generate_document(target, profile)
        title = target.replace("_", " ").title()
        output = OUTPUT_DIR / f"{target}_{timestamp}.pdf"
        exporter.export_pdf(title, markdown, output)
        created.append(_output_summary(output))

    return {"created": created, "analysis": _summarize_profile(profile)}


@app.get("/api/outputs")
def outputs() -> dict:
    return {"outputs": _list_outputs()}


@app.get("/outputs/{filename}")
def download_output(filename: str) -> FileResponse:
    safe_name = _safe_filename(filename)
    path = OUTPUT_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found.")
    return FileResponse(path, media_type="application/pdf", filename=safe_name)


def _build_profile() -> dict:
    return HardwareManifestParser(
        code_dir=INPUT_ROOT / "code",
        schematic_dir=INPUT_ROOT / "schematics",
        pcb_dir=INPUT_ROOT / "pcb",
    ).compile_hardware_profile()


def _summarize_profile(profile: dict) -> dict:
    manifests = [*profile.get("schematics", []), *profile.get("pcb", [])]
    rails = []
    groups = []
    risks = []
    key_parts = []
    optimization_actions = []
    validation_matrix = []
    bringup_sequence = []
    readiness_scores = []
    seen = {
        "rails": set(),
        "groups": set(),
        "risks": set(),
        "key_parts": set(),
        "optimization_actions": set(),
        "validation_matrix": set(),
        "bringup_sequence": set(),
    }

    for manifest in manifests:
        analysis = manifest.get("analysis") or {}
        score = analysis.get("readiness_score")
        if isinstance(score, (int, float)):
            readiness_scores.append(score)
        for rail in analysis.get("power_rails") or []:
            key = rail.get("net")
            if key and key not in seen["rails"]:
                rails.append(rail)
                seen["rails"].add(key)
        for group in analysis.get("interface_groups") or []:
            key = group.get("name")
            if key and key not in seen["groups"]:
                groups.append(group)
                seen["groups"].add(key)
        for risk in analysis.get("risk_flags") or []:
            if risk not in seen["risks"]:
                risks.append(risk)
                seen["risks"].add(risk)
        for part in analysis.get("key_parts") or []:
            key = part.get("reference")
            if key and key not in seen["key_parts"]:
                key_parts.append(part)
                seen["key_parts"].add(key)
        for action in analysis.get("optimization_actions") or []:
            key = (action.get("area"), action.get("recommendation"))
            if key not in seen["optimization_actions"]:
                optimization_actions.append(action)
                seen["optimization_actions"].add(key)
        for item in analysis.get("validation_matrix") or []:
            key = (item.get("subsystem"), item.get("method"))
            if key not in seen["validation_matrix"]:
                validation_matrix.append(item)
                seen["validation_matrix"].add(key)
        for step in analysis.get("bringup_sequence") or []:
            if step not in seen["bringup_sequence"]:
                bringup_sequence.append(step)
                seen["bringup_sequence"].add(step)

    return {
        "power_rails": rails[:18],
        "interface_groups": groups[:16],
        "risk_flags": risks[:8],
        "key_parts": key_parts[:18],
        "optimization_actions": optimization_actions[:10],
        "validation_matrix": validation_matrix[:12],
        "bringup_sequence": bringup_sequence[:10],
        "readiness_score": round(sum(readiness_scores) / len(readiness_scores)) if readiness_scores else 0,
    }


def _list_outputs() -> list[dict]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(OUTPUT_DIR.glob("*.pdf"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_output_summary(path) for path in files[:20]]


def _output_summary(path: Path) -> dict:
    return {
        "name": path.name,
        "size_kb": round(path.stat().st_size / 1024, 1),
        "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "url": f"/outputs/{path.name}",
    }


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name:
        raise HTTPException(status_code=400, detail="Invalid file name.")
    return name[:120]


def _runtime_links() -> dict:
    local_url = "http://127.0.0.1:8000"
    lan_urls = []
    try:
        hostnames = {socket.gethostname(), socket.getfqdn()}
        for hostname in hostnames:
            for ip_address in socket.gethostbyname_ex(hostname)[2]:
                if ip_address and not ip_address.startswith("127.") and ":" not in ip_address:
                    lan_urls.append(f"http://{ip_address}:8000")
    except OSError:
        pass

    unique_lan_urls = list(dict.fromkeys(lan_urls))
    return {
        "local_url": local_url,
        "lan_urls": unique_lan_urls[:4],
        "windows_command": ".\\run_windows.ps1",
        "android_note": "Run the Windows host command, keep the PC and phone on the same Wi-Fi, then open the LAN URL in Android Chrome.",
    }
