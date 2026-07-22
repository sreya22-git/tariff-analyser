import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.llm_service import LLMService, DashboardLLM, generate_schema_overview
from services.parser import (
    build_sheets_payload,
    parse_llm_overview,
    normalize_overview,
    heuristic_relationships,
    enrich_relationships_llm_first,
)
from services.tariff_analysis import analyze_cost_impact, analyze_supplier_risk, analyze_duty_optimization

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DEMO_FILE = DATA_DIR / "procurement_demo.xlsx"

app = FastAPI(title="Tariff Impact Analyzer — Procurement")

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/demo-data", StaticFiles(directory=str(DATA_DIR)), name="demo_data")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _resolve_data_path(file: str | None) -> Path:
    if file:
        candidate = DATA_DIR / os.path.basename(file)
        if candidate.exists():
            return candidate
    return DEMO_FILE


# --- Page routes -----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def ingestion_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/analysisDetails", response_class=HTMLResponse)
async def analysis_details_page(request: Request):
    return templates.TemplateResponse("analysis_details.html", {"request": request})


# --- Document upload + agentic processing endpoint --------------------------

@app.post("/api/upload/analyze")
async def upload_and_analyze(file: UploadFile = File(...)) -> Dict:
    """Accept an uploaded procurement workbook (xlsx/csv), persist it, and run the
    agentic schema + relationship inference pipeline (LLM-first, heuristic fallback)."""
    filename = file.filename or "uploaded"
    safe_name = os.path.basename(filename)
    raw = await file.read()

    try:
        (DATA_DIR / safe_name).write_bytes(raw)
    except Exception:
        pass

    sheets_payload = build_sheets_payload(raw, filename)

    if OPENAI_API_KEY:
        content = await generate_schema_overview(sheets_payload, OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL)
        parsed = parse_llm_overview(content)
        if isinstance(parsed, dict) and parsed.get("sheets"):
            normalized = normalize_overview(parsed, sheets_payload)
            enriched = await enrich_relationships_llm_first(normalized, OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL)
            return enriched

    # Deterministic fallback: guess STRING type for every column, then infer relationships heuristically.
    local = {
        "sheets": [
            {
                "name": sp["name"],
                "columns": [
                    {"name": h or f"col{i + 1}", "type": "STRING", "nullable": False, "desc": ""}
                    for i, h in enumerate(sp.get("headers", []))
                ],
            }
            for sp in sheets_payload
        ]
    }
    local["relationships"] = heuristic_relationships(local)
    return local


# --- Dashboard (agentic one-shot) -------------------------------------------

@app.get("/api/dashboard-llm-run", response_class=JSONResponse)
async def dashboard_llm_run(file: str | None = None):
    data_path = _resolve_data_path(file)
    dllm = DashboardLLM(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    raw = data_path.read_bytes()
    parsed = await dllm.run(raw, data_path.name, data_path)
    return JSONResponse(content={"ok": True, "data": parsed})


# --- Analysis Details reports ------------------------------------------------

@app.get("/api/cost-impact-report", response_class=JSONResponse)
async def cost_impact_report(file: str | None = None):
    data_path = _resolve_data_path(file)
    report = analyze_cost_impact(data_path)
    llm = LLMService(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    report["llm_summary"] = await llm.summarize_findings("CostImpactPrompt.md", _bucket_context(report))
    return JSONResponse(content=report)


@app.get("/api/supplier-risk-report", response_class=JSONResponse)
async def supplier_risk_report(file: str | None = None):
    data_path = _resolve_data_path(file)
    report = analyze_supplier_risk(data_path)
    llm = LLMService(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    report["llm_summary"] = await llm.summarize_findings("SupplierRiskPrompt.md", _bucket_context(report))
    return JSONResponse(content=report)


@app.get("/api/duty-optimization-report", response_class=JSONResponse)
async def duty_optimization_report(file: str | None = None):
    data_path = _resolve_data_path(file)
    report = analyze_duty_optimization(data_path)
    llm = LLMService(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    report["llm_summary"] = await llm.summarize_findings("DutyOptimizationPrompt.md", _bucket_context(report))
    return JSONResponse(content=report)


def _bucket_context(report: Dict) -> str:
    lines = []
    for bucket, items in (report.get("issues_by_bucket") or {}).items():
        for it in items:
            lines.append(f"[{bucket}] {it.get('table', '-')}: {it.get('description', '-')} (found: {it.get('value_found', '-')})")
    return "\n".join(lines)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8003, reload=True)
