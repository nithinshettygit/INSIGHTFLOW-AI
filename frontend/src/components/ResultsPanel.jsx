export default function ResultsPanel({ analytics, profileDetail, intent }) {
  const rows = analytics?.results || [];
  const columns =
    rows.length > 0 ? Object.keys(rows[0]).filter((key) => key !== "grounding") : [];

  return (
    <section className="panel flex h-full flex-col overflow-hidden rounded-2xl">
      <div className="border-b border-line px-5 py-4">
        <h2 className="font-display text-lg tracking-tight">Results</h2>
        <p className="mt-1 text-sm text-muted">
          Analytics tables, KPIs, and routing details.
        </p>
      </div>

      <div className="side-scroll flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        {intent && (
          <div className="rounded-xl bg-soft/80 p-3">
            <div className="font-semibold">Last intent</div>
            <div className="mt-1 text-muted">
              {intent.intent} → {intent.target_engine} ({intent.orchestration?.provider})
              {intent.confidence != null ? ` · ${(intent.confidence * 100).toFixed(0)}%` : ""}
            </div>
            {intent.rationale && (
              <div className="mt-2 text-muted">{intent.rationale}</div>
            )}
          </div>
        )}

        {analytics?.kpis && (
          <div className="rounded-xl bg-soft/80 p-3">
            <div className="font-semibold">KPIs</div>
            <pre className="mt-2 overflow-x-auto text-xs text-muted">
              {JSON.stringify(analytics.kpis, null, 2)}
            </pre>
          </div>
        )}

        {rows.length > 0 && (
          <div className="overflow-x-auto rounded-xl ring-1 ring-line">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-soft">
                <tr>
                  {columns.map((column) => (
                    <th key={column} className="px-3 py-2 font-semibold">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 25).map((row, index) => (
                  <tr key={index} className="border-t border-line bg-white/70">
                    {columns.map((column) => (
                      <td key={column} className="px-3 py-2 whitespace-nowrap">
                        {formatCell(row[column])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {profileDetail?.profile && !analytics && (
          <div className="rounded-xl bg-soft/80 p-3">
            <div className="font-semibold">Profile detail</div>
            <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted">
              {JSON.stringify(
                {
                  row_count: profileDetail.profile.row_count,
                  column_count: profileDetail.profile.column_count,
                  missing_values_total: profileDetail.profile.missing_values_total,
                  duplicate_rows: profileDetail.profile.duplicate_rows,
                  columns: profileDetail.profile.columns?.slice(0, 8),
                },
                null,
                2,
              )}
            </pre>
          </div>
        )}

        {!intent && !analytics && !profileDetail && (
          <p className="text-muted">Engine output will show up here.</p>
        )}
      </div>
    </section>
  );
}

function formatCell(value) {
  if (value == null) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(2);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
