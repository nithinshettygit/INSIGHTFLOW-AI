import Plot from "react-plotly.js";

export default function ChartPanel({ chart, emptyHint, compact = false }) {
  const figure = chart?.plotly_figure;

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden rounded-2xl">
      <div
        className={`panel-header shrink-0 border-b border-line px-4 md:px-5 ${
          compact ? "py-2.5" : "py-4"
        }`}
      >
        <h2 className="font-display text-base tracking-tight text-ink md:text-lg">
          {chart?.title || "Visualization"}
        </h2>
        <p className="mt-0.5 text-xs text-muted md:text-sm">
          {chart
            ? `${chart.chart_type} · Plotly`
            : "Charts appear here after visualization or ML intents."}
        </p>
      </div>

      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden p-2 md:p-3">
        {figure ? (
          <Plot
            data={figure.data}
            layout={{
              ...figure.layout,
              autosize: true,
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: "rgba(0,0,0,0)",
              colorway: [
                "#0f766e",
                "#1e3a5f",
                "#b08d57",
                "#047857",
                "#64748b",
                "#8c6b3a",
              ],
              font: {
                family: "Manrope, sans-serif",
                color: "#06101c",
                size: compact ? 11 : 12,
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
