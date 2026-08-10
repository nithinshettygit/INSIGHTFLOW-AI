/**
 * Map intent detection output into engine API calls.
 */

const CHART_TYPES = new Set(["bar", "line", "pie", "scatter"]);

export function buildVisualizationPayload(datasetId, intentResult, queryText) {
  const entities = intentResult.entities || {};
  const query = queryText || intentResult.query || "";
  const chartType = CHART_TYPES.has(entities.chart_type)
    ? entities.chart_type
    : "bar";
  const extreme = inferExtreme(query);
  const metrics = entities.metrics || [];
  const dimensions = entities.dimensions || [];
  const filters = normalizeFilters(entities.filters);
  const title = buildEntityTitle(chartType, metrics, dimensions, filters, query);

  return {
    dataset_id: datasetId,
    chart_type: chartType,
    metrics,
    dimensions,
    filters,
    aggregation: "sum",
    limit: extreme ? 15 : 50,
    sort_order: extreme?.order || "desc",
    title,
  };
}

export function buildAnalyticsPayload(datasetId, intentResult, queryText) {
  const entities = intentResult.entities || {};
  const query = queryText || intentResult.query || "";
  const metrics = entities.metrics || [];
  const dimensions = entities.dimensions || [];
  const extreme = inferExtreme(query);
  const sortBy = [];

  if (extreme && metrics.length) {
    const field = dimensions.length ? `${metrics[0]}_sum` : metrics[0];
    sortBy.push({
      field,
      order: extreme.order,
    });
  }

  return {
    dataset_id: datasetId,
    metrics,
    dimensions,
    filters: normalizeFilters(entities.filters),
    aggregations: ["sum", "mean", "count"],
    sort_by: sortBy,
    limit: extreme ? Math.max(extreme.limit, 1) : 50,
    include_kpis: true,
  };
}

export function buildMlPayload(datasetId, intentResult, queryText) {
  const entities = intentResult.entities || {};
  const metrics = entities.metrics || [];
  const dimensions = entities.dimensions || [];
  const query = queryText || intentResult.query || "";
  const task =
    entities.ml_task ||
    entities.task ||
    inferMlTask(query);

  return {
    dataset_id: datasetId,
    task,
    query,
    target: metrics[0] || null,
    time_column: dimensions[0] || entities.time_column || null,
    features: metrics.length ? metrics : [],
    horizon: Number(entities.horizon) || 7,
    n_clusters: Number(entities.n_clusters) || 3,
    contamination: Number(entities.contamination) || 0.05,
    limit: 50,
  };
}

export function buildInsightPayload(datasetId, intentResult, queryText) {
  const entities = intentResult.entities || {};
  const metrics = entities.metrics || [];
  const dimensions = entities.dimensions || [];
  const query = queryText || intentResult.query || "";
  const mode =
    entities.insight_mode ||
    entities.mode ||
    inferInsightMode(query);

  return {
    dataset_id: datasetId,
    question: query,
    mode,
    focus_metrics: metrics,
    focus_dimensions: dimensions,
    include_ml_context: true,
  };
}

/**
 * Build a plain-language answer that names the extreme segment
 * (e.g. "Central has the lowest sales: 12,450").
 */
export function summarizeExtremeAnswer(queryText, intentResult, rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;

  const entities = intentResult?.entities || {};
  const metrics = entities.metrics || [];
  const dimensions = entities.dimensions || [];
  const extreme = inferExtreme(queryText || intentResult?.query || "");
  if (!extreme) return null;

  const row = rows[0];
  const keys = Object.keys(row);
  const keyLookup = Object.fromEntries(
    keys.map((key) => [String(key).toLowerCase(), key]),
  );

  const dimensionKey =
    dimensions
      .map((name) => keyLookup[String(name).toLowerCase()])
      .find(Boolean) ||
    keys.find(
      (key) =>
        !/_sum$|_mean$|_count$|_min$|_max$|_median$/i.test(key) &&
        key !== "kind" &&
        !metrics.some(
          (metric) => String(metric).toLowerCase() === String(key).toLowerCase(),
        ),
    );

  const metricKey =
    metrics
      .map((name) => keyLookup[`${String(name).toLowerCase()}_sum`])
      .find(Boolean) ||
    metrics
      .map((name) => keyLookup[String(name).toLowerCase()])
      .find(Boolean) ||
    keys.find((key) => /_sum$/i.test(key)) ||
    keys.find((key) => typeof row[key] === "number" && key !== dimensionKey);

  if (dimensionKey == null || metricKey == null) return null;
  if (String(dimensionKey).toLowerCase() === String(metricKey).toLowerCase()) {
    return null;
  }

  const label = formatValue(row[dimensionKey]);
  const value = formatValue(row[metricKey]);
  if (label === "—" || label === "") return null;

  const metricLabel = String(metricKey).replace(/_sum$/i, "");
  const adjective = extreme.order === "asc" ? "lowest" : "highest";

  return `${label} has the ${adjective} ${metricLabel}: ${value}.`;
}

function inferExtreme(query) {
  const text = String(query || "").toLowerCase();
  const segmentPattern =
    /(which|what).*(region|country|category|segment|city|state|product|market|sub[_ -]?category)/;
  if (
    /(lowest|smallest|minimum|min\b|least|bottom|worst|poorest)/.test(
      text,
    )
  ) {
    const limit = /\btop\s+(\d+)\b/.test(text)
      ? Number(text.match(/\btop\s+(\d+)\b/)[1])
      : segmentPattern.test(text)
        ? 1
        : 5;
    return { order: "asc", limit };
  }
  if (/(highest|largest|maximum|max\b|most|top\b|best)/.test(text)) {
    const topMatch = text.match(/\btop\s+(\d+)\b/);
    const limit = topMatch
      ? Number(topMatch[1])
      : segmentPattern.test(text)
        ? 1
        : 5;
    return { order: "desc", limit };
  }
  return null;
}

function inferMlTask(query) {
  const text = String(query || "").toLowerCase();
  if (/(segment|cluster|segmentation|customer group)/.test(text)) {
    return "segmentation";
  }
  if (/(anomal|outlier|unusual|fraud)/.test(text)) {
    return "anomaly";
  }
  return "forecast";
}

function inferInsightMode(query) {
  const text = String(query || "").toLowerCase();
  if (/(root cause|why did|why is|why are|what caused|driver)/.test(text)) {
    return "root_cause";
  }
  if (/(recommend|suggest|what should|next step|how can we improve)/.test(text)) {
    return "recommendation";
  }
  return "explanation";
}

function normalizeFilters(filters) {
  if (!Array.isArray(filters)) return [];
  return filters
    .map((item) => {
      if (typeof item === "string") {
        return null;
      }
      if (item && typeof item === "object") {
        const field = item.field || item.column || item.name;
        if (!field) return null;
        return {
          field,
          op: item.op || "eq",
          value: item.value,
        };
      }
      return null;
    })
    .filter(Boolean);
}

function buildEntityTitle(chartType, metrics, dimensions, filters, fallback) {
  const metric = metrics[0];
  const dimension = dimensions[0];
  if (metric && dimension) {
    const filterBits = (filters || [])
      .filter((item) => item && item.field != null && item.value != null)
      .map((item) => `${item.field}=${item.value}`);
    const suffix = filterBits.length ? ` (${filterBits.join(", ")})` : "";
    return `${chartType} chart of ${metric} by ${dimension}${suffix}`;
  }
  return fallback || "chart";
}

function formatValue(value) {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}
