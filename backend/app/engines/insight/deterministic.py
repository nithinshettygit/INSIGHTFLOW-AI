"""Deterministic insight generation when Groq is unavailable."""

from __future__ import annotations

from typing import Any


def build_deterministic_insight(
    *,
    question: str,
    mode: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    kpis = evidence.get("kpis") or {}
    contrasts = evidence.get("segment_contrasts") or []
    profile = evidence.get("profile") or {}
    ml_context = evidence.get("ml_context") or []
    notes = evidence.get("notes") or []

    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    root_causes: list[dict[str, Any]] = []

    if profile.get("missing_values_total"):
        findings.append(
            {
                "title": "Missing values present",
                "detail": (
                    f"Dataset reports {profile.get('missing_values_total')} missing "
                    f"values across {profile.get('column_count')} columns."
                ),
                "severity": "medium"
                if int(profile.get("missing_values_total") or 0) > 0
                else "low",
            }
        )

    for name, stats in list(kpis.items())[:3]:
        findings.append(
            {
                "title": f"{name} snapshot",
                "detail": (
                    f"sum={stats.get('sum')}, mean={stats.get('mean')}, "
                    f"min={stats.get('min')}, max={stats.get('max')} "
                    f"(n={stats.get('non_null')})."
                ),
                "severity": "low",
            }
        )

    for contrast in contrasts[:3]:
        top = contrast.get("top_segment") or {}
        bottom = contrast.get("bottom_segment") or {}
        metric = contrast.get("metric")
        dim = contrast.get("dimension")
        detail = (
            f"On {dim}, '{top.get('value')}' leads {metric} "
            f"(sum={top.get('sum')}, share={top.get('share')}) while "
            f"'{bottom.get('value')}' is lowest (sum={bottom.get('sum')})."
        )
        findings.append(
            {
                "title": f"{metric} varies by {dim}",
                "detail": detail,
                "severity": "high",
            }
        )
        root_causes.append(
            {
                "cause": (
                    f"Performance gap between '{top.get('value')}' and "
                    f"'{bottom.get('value')}' on {dim}"
                ),
                "evidence": detail,
                "confidence": 0.62,
            }
        )
        recommendations.append(
            {
                "action": (
                    f"Investigate drivers behind low {metric} in "
                    f"'{bottom.get('value')}' ({dim})"
                ),
                "rationale": detail,
                "priority": 1,
            }
        )

    for item in ml_context[:2]:
        task = item.get("task")
        summary = item.get("summary") or {}
        findings.append(
            {
                "title": f"Recent ML context: {task}",
                "detail": str(summary)[:400],
                "severity": "medium",
            }
        )
        if task == "anomaly" and summary.get("anomaly_count"):
            recommendations.append(
                {
                    "action": "Review flagged anomaly rows with the ops team",
                    "rationale": (
                        f"Last anomaly run found {summary.get('anomaly_count')} "
                        f"outliers (rate={summary.get('anomaly_rate')})."
                    ),
                    "priority": 2,
                }
            )
        if task == "forecast" and summary.get("forecast_mean") is not None:
            recommendations.append(
                {
                    "action": "Align inventory/staffing to the forecast trajectory",
                    "rationale": (
                        f"Forecast mean={summary.get('forecast_mean')} over "
                        f"horizon={summary.get('horizon')}."
                    ),
                    "priority": 2,
                }
            )

    if not findings:
        findings.append(
            {
                "title": "Limited evidence",
                "detail": "Not enough structured KPI/segment signals were available.",
                "severity": "medium",
            }
        )
        notes_text = "; ".join(notes) if notes else "Upload a richer tabular dataset."
        recommendations.append(
            {
                "action": "Enrich the analysis inputs",
                "rationale": notes_text,
                "priority": 3,
            }
        )

    if mode == "recommendation" and not recommendations:
        recommendations.append(
            {
                "action": "Prioritize the highest-impact segment gap",
                "rationale": "Use segment contrasts and KPI gaps as the first triage list.",
                "priority": 2,
            }
        )

    if mode == "root_cause" and not root_causes:
        root_causes.append(
            {
                "cause": "Insufficient contrast evidence for a confident root cause",
                "evidence": "No clear top/bottom segment gap was computed.",
                "confidence": 0.25,
            }
        )

    headline = {
        "explanation": "Data-backed explanation from profile and KPI evidence",
        "recommendation": "Recommended next actions from current evidence",
        "root_cause": "Likely drivers based on segment and KPI contrasts",
    }.get(mode, "Business insight")

    explanation_parts = [
        f"Question: {question.strip()}",
        f"Mode: {mode}.",
    ]
    if kpis:
        explanation_parts.append(
            "Key metrics summarized: " + ", ".join(sorted(kpis.keys())) + "."
        )
    if contrasts:
        explanation_parts.append(
            f"{len(contrasts)} segment contrast(s) used to highlight uneven performance."
        )
    if ml_context:
        explanation_parts.append(
            f"Included {len(ml_context)} recent ML summary artifact(s)."
        )
    explanation_parts.append(
        "This deterministic insight was generated without an LLM because "
        "Groq synthesis was unavailable or disabled."
    )

    # Keep lists focused by mode.
    if mode == "explanation":
        recommendations = recommendations[:1]
        root_causes = root_causes[:1]
    elif mode == "recommendation":
        root_causes = root_causes[:1]
        recommendations = recommendations[:3]
    else:
        recommendations = recommendations[:2]
        root_causes = root_causes[:3]

    return {
        "headline": headline,
        "explanation": " ".join(explanation_parts),
        "findings": findings[:6],
        "recommendations": recommendations,
        "root_causes": root_causes,
        "provider": "deterministic",
    }
