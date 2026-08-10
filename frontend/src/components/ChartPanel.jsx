import Plot from "react-plotly.js";

const CHART_COLORWAY = [
  "#059669",
  "#F59E0B",
  "#C026D3",
  "#34D399",
  "#FBBF24",
  "#E879F9",
];

export default function ChartPanel({ chart, emptyHint, compact = false }) {
  const figure = chart?.plotly_figure;
  const isMl =
    chart?.chart_type === "forecast" ||
    chart?.chart_type === "segmentation" ||
    chart?.chart_type === "anomaly";

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden rounded-[12px]">
      <div
        className={`shrink-0 border-b border-line bg-white px-4 md:px-5 ${
          compact ? "py-2.5" : "py-4"
        }`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className={`badge ${isMl ? "badge-ai" : "badge-success"}`}>
            {isMl ? "ML chart" : "Visualization"}
          </span>
          {chart?.chart_type && (
            <span className="badge badge-neutral">{chart.chart_type}</span>
          )}
        </div>
        <h2 className="mt-2 font-display text-base font-semibold tracking-tight text-ink md:text-lg">
          {chart?.title || "Visualization"}
        </h2>
        <p className="mt-0.5 text-xs text-muted md:text-sm">
          {chart
            ? `${chart.chart_type} · Plotly`
            : "Charts appear here after visualization or ML intents."}
        </p>
      </div>

      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-soft/60 p-2 md:p-3">
        {figure ? (
          <Plot
            data={(figure.data || []).map((trace, index) =>
              restyleTrace(trace, index, isMl),
            )}
            layout={{
              ...figure.layout,
              autosize: true,
              paper_bgcolor: "#FAF9F6",
              plot_bgcolor: "#FAF9F6",
              colorway: CHART_COLORWAY,
              font: {
                family: "Manrope, system-ui, sans-serif",
                color: "#18181B",
                size: compact ? 11 : 12,
              },
              xaxis: {
                ...(figure.layout?.xaxis || {}),
                gridcolor: "#E4E4E7",
                zerolinecolor: "#E4E4E7",
                linecolor: "#E4E4E7",
              },
              yaxis: {
                ...(figure.layout?.yaxis || {}),
                gridcolor: "#E4E4E7",
                zerolinecolor: "#E4E4E7",
                linecolor: "#E4E4E7",
              },
              margin: compact
                ? { l: 36, r: 12, t: 20, b: 32 }
                : { l: 48, r: 24, t: 36, b: 48 },
            }}
            config={{ displayModeBar: false, responsive: true }}
            useResizeHandler
            style={{
              width: "100%",
              height: "100%",
              minHeight: compact ? 120 : 220,
            }}
          />
        ) : (
          <p className="max-w-sm px-4 text-center text-xs text-muted md:text-sm">
            {emptyHint ||
              "Ask for a bar, line, pie, or scatter chart once a dataset is selected."}
          </p>
        )}
      </div>
    </section>
  );
}

function restyleTrace(trace, index, isMl) {
  const name = String(trace?.name || "").toLowerCase();
  const next = { ...trace };
  if (isMl && (name.includes("forecast") || name.includes("predict"))) {
    next.line = { ...(trace.line || {}), color: "#C026D3", dash: "dash" };
    next.marker = { ...(trace.marker || {}), color: "#C026D3" };
  } else if (isMl && (name.includes("history") || name.includes("actual"))) {
    next.line = { ...(trace.line || {}), color: "#059669" };
    next.marker = { ...(trace.marker || {}), color: "#059669" };
  } else if (!trace.marker?.color && !trace.line?.color) {
    next.marker = {
      ...(trace.marker || {}),
      color: CHART_COLORWAY[index % CHART_COLORWAY.length],
    };
  }
  return next;
}
