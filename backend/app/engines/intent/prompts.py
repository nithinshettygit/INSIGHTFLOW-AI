"""Prompts for Groq-powered intent classification."""

from __future__ import annotations

import json
from typing import Any

INTENT_SYSTEM_PROMPT = """You are the intent classifier for InsightFlow AI, a business intelligence platform.

Classify the user query into exactly ONE intent:
- analytics: aggregations, filters, sorting, KPIs, totals, averages, counts
- visualization: charts, plots, graphs (bar/line/pie/scatter)
- ml: forecast, prediction, segmentation, anomaly/outlier detection
- rag: questions about PDF/document contents
- insight: explanations, recommendations, root-cause reasoning
- profile: dataset schema/quality (rows, columns, missing, duplicates)
- unknown: greetings or unrelated text

Entity rules (critical):
1. Use ONLY the provided schema column names for metrics, dimensions, and filter fields.
2. Never invent column names that are not in the schema.
3. If a referenced business term does not match a schema column, omit it.
4. Prefer exact schema names (including spelling/case from schema).
5. chart_type may be one of: bar, line, pie, scatter, histogram, area, box, or null.
6. role_hint is guidance only (numeric/categorical/datetime); still use exact column names.
7. Prefer rag when the query is about document/PDF content.
8. Prefer visualization when the user asks to chart/plot/graph.
9. Return ONLY valid JSON. No markdown fences.

JSON schema:
{
  "intent": "analytics|visualization|ml|rag|insight|profile|unknown",
  "confidence": 0.0,
  "rationale": "short reason",
  "entities": {
    "metrics": ["exact_column_name"],
    "dimensions": ["exact_column_name"],
    "chart_type": "bar|line|pie|scatter|histogram|area|box|null",
    "filters": []
  }
}
"""


def build_user_prompt(query: str, context: dict[str, Any] | None = None) -> str:
    """Build a compact schema-focused prompt (no raw dataset rows)."""
    context = context or {}
    columns = context.get("columns") or []
    column_names = context.get("column_names") or [c.get("name") for c in columns if isinstance(c, dict)]

    payload = {
        "dataset_type": context.get("dataset_type"),
        "row_count": context.get("row_count"),
        "column_count": context.get("column_count"),
        "page_count": context.get("page_count"),
        "column_names": column_names,
        "columns": columns,
    }

    return (
        f"User query: {query}\n\n"
        "Dataset schema (metadata only — not raw rows):\n"
        f"{json.dumps(payload, ensure_ascii=True, indent=2)}\n\n"
        "Remember: metrics/dimensions/filter fields must be exact names from column_names."
    )
