from __future__ import annotations
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

_BASE_DIR = Path(__file__).resolve().parent
_PROMPTS_DIR = _BASE_DIR.parent / "prompts"


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


class LLMService:
    """Thin wrapper for an OpenAI-compatible /chat/completions LLM, with a deterministic
    non-LLM fallback so the app stays demoable without an API key configured."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model or os.getenv("OPENAI_MODEL", "stub-model")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

    async def summarize_findings(self, prompt_file: str, context: str) -> str:
        if self.api_key and self.base_url and self.model != "stub-model":
            return await self._summarize_llm(prompt_file, context)
        return self._summarize_stub(context)

    async def _summarize_llm(self, prompt_file: str, context: str) -> str:
        system = _load_prompt(prompt_file)
        if not system:
            return f"Error: {prompt_file} not found or is empty."
        async with httpx.AsyncClient(timeout=90) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": context},
                        ],
                        "temperature": 0.2,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                lines = content.splitlines()
                bullet_lines = [line for line in lines if line.strip().startswith("-")]
                return "\n".join(bullet_lines) if bullet_lines else content
            except httpx.RequestError as e:
                return f"Error calling LLM API: {e}"
            except Exception as e:
                return f"An unexpected error occurred: {e}"

    def _summarize_stub(self, context: str) -> str:
        """Deterministic, context-grounded summary parsed from the same bracketed-bucket
        lines that would otherwise be sent to the LLM (see main._bucket_context)."""
        if not context or not context.strip():
            return "No findings detected or empty context provided. Ensure a workbook has been analyzed successfully."

        lines = [ln.strip() for ln in context.splitlines() if ln.strip()]
        bucket_counts: Counter = Counter()
        table_counts: Counter = Counter()
        samples: List[str] = []

        for ln in lines:
            m = re.match(r"^\[(.*?)\]\s*(.*?):\s*(.*)$", ln)
            if not m:
                continue
            bucket, table, desc = m.groups()
            bucket_counts[bucket] += 1
            table_counts[table] += 1
            if len(samples) < 3:
                samples.append(desc.strip())

        if not lines:
            return "No findings to summarize."

        n = len(lines)
        top_buckets = ", ".join([f"{name}({cnt})" for name, cnt in bucket_counts.most_common(3)]) or "various checks"
        top_tables = ", ".join([f"{name}({cnt})" for name, cnt in table_counts.most_common(3)]) or "multiple tables/categories"

        bullets = [
            f"- Findings identified: {n} across {len(bucket_counts)} check type(s).",
            f"- Most triggered checks: {top_buckets}.",
            f"- Most affected tables/categories: {top_tables}.",
        ]
        if samples:
            bullets.append(f"- Example: {samples[0]}")
        bullets.append("- Risk: unaddressed exposure may erode margin or invite compliance penalties; prioritize remediation per the proposed actions above.")
        return "\n".join(bullets)


async def generate_schema_overview(sheets_payload: List[Dict[str, Any]], base_url: str, api_key: str, model: str) -> str:
    """Calls the LLM to generate a schema overview (columns, types, descriptions)."""
    system = _load_prompt("SchemaOverviewPrompt.md")
    user_parts: List[str] = []
    tab_sep = "\t"
    for sp in sheets_payload:
        name = sp.get("name", "")
        headers_list = sp.get("headers", []) or []
        headers_str = tab_sep.join(headers_list) if isinstance(headers_list, list) else str(headers_list)
        sample = sp.get("sample", "")
        user_parts.append(f"Sheet: {name}\nHeaders: {headers_str}\nSample:\n{sample}")

    user = (
        "Return ONLY valid JSON with this schema:\n"
        '{ "sheets": [ { "name": string, "columns": [ { "name": string, "type": string, "nullable": bool, "desc": string } ] } ] }\n\n'
        + "Data:\n" + "\n\n".join(user_parts)
    )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "{}")


async def infer_relationships(sheets: List[Dict[str, Any]], base_url: str, api_key: str, model: str) -> List[Dict[str, str]]:
    """Calls the LLM to infer foreign-key relationships between sheets."""
    system = _load_prompt("RelationshipPrompt.md")
    user = json.dumps({"sheets": sheets}, ensure_ascii=False)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            parsed = json.loads(content)
        except Exception:
            return []
        rels = parsed.get("relationships")
        return rels if isinstance(rels, list) else []


class DashboardLLM:
    """Runs the strict-JSON dashboard prompt against an uploaded/bundled workbook.
    Falls back to a deterministic payload (services.tariff_analysis.build_dashboard_payload)
    when no LLM is configured, so the dashboard is always populated."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model or os.getenv("OPENAI_MODEL", "stub-model")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

    async def run(self, raw: bytes, filename: str, file_path) -> Dict[str, Any]:
        from services.parser import build_sheets_payload, parse_llm_overview
        from services.tariff_analysis import build_dashboard_payload

        if self.api_key and self.base_url and self.model != "stub-model":
            system = _load_prompt("dashboardPrompts.md")
            if system:
                sheets_payload = build_sheets_payload(raw, filename)
                user = json.dumps({"file": filename, "sheets_payload": sheets_payload}, ensure_ascii=False)
                try:
                    async with httpx.AsyncClient(timeout=90) as client:
                        resp = await client.post(
                            f"{self.base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                            json={
                                "model": self.model,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                "temperature": 0.2,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                        parsed = parse_llm_overview(content)
                        if parsed:
                            return parsed
                except Exception:
                    pass

        # Stub / fallback path: compute the same JSON contract deterministically.
        return build_dashboard_payload(file_path)
