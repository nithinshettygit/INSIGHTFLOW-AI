"""Rule definitions for keyword / phrase intent matching."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.intent import IntentName, TargetEngine


@dataclass(frozen=True)
class IntentRule:
    """A weighted keyword/phrase rule mapped to an intent."""

    intent: IntentName
    target_engine: TargetEngine
    keywords: tuple[str, ...]
    weight: float = 1.0
    priority: int = 100


# Higher priority wins on confidence ties.
# More specific multi-word phrases are preferred via longer keyword matches.
INTENT_RULES: tuple[IntentRule, ...] = (
    # Visualization
    IntentRule(
        intent="visualization",
        target_engine="visualization",
        keywords=(
            "bar chart",
            "line chart",
            "pie chart",
            "scatter plot",
            "scatter chart",
            "histogram",
            "plot a",
            "draw a chart",
            "show chart",
            "visualize",
            "visualise",
            "graph of",
            "chart of",
            "plot of",
            "dashboard chart",
        ),
        weight=1.4,
        priority=90,
    ),
    IntentRule(
        intent="visualization",
        target_engine="visualization",
        keywords=("chart", "graph", "plot", "visualize", "visualise"),
        weight=1.0,
        priority=80,
    ),
    # ML
    IntentRule(
        intent="ml",
        target_engine="ml",
        keywords=(
            "forecast",
            "predict",
            "prediction",
            "anomaly",
            "anomalies",
            "outlier",
            "segmentation",
            "segment customers",
            "customer segmentation",
            "clustering",
            "cluster",
            "time series",
            "next month",
            "future sales",
        ),
        weight=1.3,
        priority=85,
    ),
    # RAG / documents
    IntentRule(
        intent="rag",
        target_engine="rag",
        keywords=(
            "according to the document",
            "according to the pdf",
            "in the document",
            "in the pdf",
            "from the pdf",
            "from the document",
            "document says",
            "pdf says",
            "search the document",
            "search the pdf",
            "what does the document",
            "what does the pdf",
            "quote from",
        ),
        weight=1.5,
        priority=95,
    ),
    IntentRule(
        intent="rag",
        target_engine="rag",
        keywords=("document", "pdf", "report says", "contract", "policy"),
        weight=0.9,
        priority=70,
    ),
    # Insight / LLM reasoning
    IntentRule(
        intent="insight",
        target_engine="insight",
        keywords=(
            "root cause",
            "why did",
            "why is",
            "explain why",
            "recommend",
            "recommendation",
            "suggestions",
            "suggest",
            "what should we",
            "business insight",
            "insights",
            "interpret",
            "rationale",
        ),
        weight=1.3,
        priority=88,
    ),
    IntentRule(
        intent="insight",
        target_engine="insight",
        keywords=("explain", "why", "recommend", "insight"),
        weight=1.0,
        priority=75,
    ),
    # Profile / data understanding
    IntentRule(
        intent="profile",
        target_engine="profiling",
        keywords=(
            "missing values",
            "null values",
            "duplicate rows",
            "data profile",
            "dataset profile",
            "column types",
            "schema",
            "how many columns",
            "how many rows",
            "data quality",
            "profile the dataset",
            "summarize the dataset",
            "summarise the dataset",
        ),
        weight=1.4,
        priority=92,
    ),
    IntentRule(
        intent="profile",
        target_engine="profiling",
        keywords=("profile", "columns", "rows", "duplicates", "missing"),
        weight=0.9,
        priority=65,
    ),
    # Analytics / KPIs
    IntentRule(
        intent="analytics",
        target_engine="analytics",
        keywords=(
            "total sales",
            "average",
            "mean",
            "median",
            "sum of",
            "count of",
            "how many",
            "aggregate",
            "aggregation",
            "filter by",
            "group by",
            "sorted by",
            "top 10",
            "top ten",
            "kpi",
            "revenue by",
            "sales by",
            "percentage of",
            "min ",
            "max ",
            "minimum",
            "maximum",
        ),
        weight=1.2,
        priority=82,
    ),
    IntentRule(
        intent="analytics",
        target_engine="analytics",
        keywords=(
            "total",
            "sum",
            "count",
            "average",
            "filter",
            "aggregate",
            "kpi",
            "metric",
        ),
        weight=0.9,
        priority=60,
    ),
)


INTENT_CATALOG = (
    {
        "intent": "analytics",
        "target_engine": "analytics",
        "description": "Aggregations, filters, sorting, and KPI calculations.",
        "example_queries": [
            "What is total sales by region?",
            "Show average revenue for 2024",
            "Count orders where profit is negative",
        ],
    },
    {
        "intent": "visualization",
        "target_engine": "visualization",
        "description": "Chart and plot requests.",
        "example_queries": [
            "Show a bar chart of sales by category",
            "Plot a line chart of monthly revenue",
            "Create a pie chart of market share",
        ],
    },
    {
        "intent": "ml",
        "target_engine": "ml",
        "description": "Forecasting, segmentation, and anomaly detection.",
        "example_queries": [
            "Forecast next month sales",
            "Segment customers by spending",
            "Detect anomalies in daily orders",
        ],
    },
    {
        "intent": "rag",
        "target_engine": "rag",
        "description": "Questions over uploaded PDF/document content.",
        "example_queries": [
            "What does the PDF say about Q3 targets?",
            "Search the document for refund policy",
            "According to the report, what are risks?",
        ],
    },
    {
        "intent": "insight",
        "target_engine": "insight",
        "description": "Explanations, recommendations, and root-cause reasoning.",
        "example_queries": [
            "Why did profit drop last quarter?",
            "Recommend actions to improve margin",
            "Explain the root cause of declining sales",
        ],
    },
    {
        "intent": "profile",
        "target_engine": "profiling",
        "description": "Dataset structure and data-quality questions.",
        "example_queries": [
            "How many rows and columns are in the dataset?",
            "Show missing values and duplicates",
            "Profile the dataset schema",
        ],
    },
    {
        "intent": "unknown",
        "target_engine": "none",
        "description": "Fallback when no rule matches confidently.",
        "example_queries": ["Hello", "Help"],
    },
)


ENGINE_ROUTING = {
    "analytics": {
        "status": "ready",
        "phase": "Phase 5",
        "message": "Routed to Analytics Engine. Use POST /analytics/query.",
    },
    "visualization": {
        "status": "ready",
        "phase": "Phase 6",
        "message": "Routed to Visualization Engine. Use POST /visualization/chart.",
    },
    "ml": {
        "status": "ready",
        "phase": "Phase 9",
        "message": "Routed to ML Engine. Use POST /ml/run.",
    },
    "rag": {
        "status": "ready",
        "phase": "Phase 8",
        "message": "Routed to RAG Engine. Use POST /rag/query.",
    },
    "insight": {
        "status": "ready",
        "phase": "Phase 10",
        "message": "Routed to Insight Engine. Use POST /insight/analyze.",
    },
    "profiling": {
        "status": "ready",
        "phase": "Phase 3",
        "message": "Routed to profiling service. Use GET /datasets/{id}/profile.",
    },
    "none": {
        "status": "planned",
        "phase": None,
        "message": "No engine matched. Refine the query or try a supported intent.",
    },
}
