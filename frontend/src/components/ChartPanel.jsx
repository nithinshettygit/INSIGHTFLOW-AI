import Plot from "react-plotly.js";

export default function ChartPanel({ chart, emptyHint }) {
  const figure = chart?.plotly_figure;

  return (
    <section className="panel flex h-full min-h-[320px] flex-col overflow-hidden rounded-2xl">
      <div className="border-b border-line px-5 py-4">
        <h2 className="font-display text-lg tracking-tight">
          {chart?.title || "Visualization"}
        </h2>
        <p className="mt-1 text-sm text-muted">
          {chart
            ? `${chart.chart_type} · Plotly`
            : "Charts appear here after a visualization intent."}
        </p>
      </div>

      <div className="flex flex-1 items-center justify-center p-3">
        {figure ? (
          <Plot
            data={figure.data}
            layout={{
              ...figure.layout,
              autosize: true,
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: "rgba(0,0,0,0)",
              font: { family: "Manrope, sans-serif", color: "#12202a" },
              margin: { l: 48, r: 24, t: 36, b: 48 },
            }}
            config={{ displayModeBar: false, responsive: true }}
            useResizeHandler
            style={{ width: "100%", height: "100%", minHeight: 360 }}
          />
        ) : (
          <p className="max-w-sm px-6 text-center text-sm text-muted">
            {emptyHint ||
              "Ask for a bar, line, pie, or scatter chart once a dataset is selected."}
          </p>
        )}
      </div>
    </section>
  );
}
