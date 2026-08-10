/**
 * Human-readable dataset profile (replaces raw JSON dumps).
 */
export default function ProfileCard({ profile, source }) {
  if (!profile) return null;

  const isPdf = profile.dataset_type === "pdf";
  const columns = profile.columns || [];
  const pageCount = profile.metadata?.page_count;
  const note = profile.metadata?.note;

  const stats = [
    { label: "Rows", value: formatNumber(profile.row_count) },
    { label: "Columns", value: formatNumber(profile.column_count) },
    { label: "Missing", value: formatNumber(profile.missing_values_total) },
    { label: "Duplicates", value: formatNumber(profile.duplicate_rows) },
  ];

  if (isPdf) {
    stats[0] = { label: "Pages", value: formatNumber(pageCount) };
    stats[1] = { label: "Type", value: "PDF" };
    stats[2] = { label: "Rows", value: "—" };
    stats[3] = { label: "Columns", value: "—" };
  }

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="font-semibold text-ink">Dataset profile</div>
          <p className="mt-0.5 text-xs text-muted">
            {profile.dataset_type?.toUpperCase() || "DATA"}
            {source ? ` · ${source}` : ""}
            {profile.profiled_at
              ? ` · ${new Date(profile.profiled_at).toLocaleString()}`
              : ""}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map((item) => (
          <div
            key={item.label}
            className="stat-tile rounded-xl px-3 py-2.5"
          >
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">
              {item.label}
            </div>
            <div className="mt-1 font-display text-lg font-bold text-ink tabular-nums">
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {isPdf && (
        <div className="rounded-xl bg-soft/80 px-3 py-2 text-xs text-muted">
          {note ||
            "PDF document profile. Ask document questions to use RAG search."}
        </div>
      )}

      {!isPdf && columns.length > 0 && (
        <div className="overflow-hidden rounded-xl ring-1 ring-line">
          <div className="border-b border-line bg-soft/80 px-3 py-2 text-xs font-semibold text-ink">
            Columns ({columns.length})
          </div>
          <div className="max-h-56 overflow-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-white/95">
                <tr className="text-muted">
                  <th className="px-3 py-2 font-semibold">Name</th>
                  <th className="px-3 py-2 font-semibold">Type</th>
                  <th className="px-3 py-2 font-semibold">Unique</th>
                  <th className="px-3 py-2 font-semibold">Missing</th>
                  <th className="px-3 py-2 font-semibold">Summary</th>
                </tr>
              </thead>
              <tbody>
                {columns.map((col) => (
                  <tr key={col.name} className="border-t border-line bg-white/70">
                    <td className="px-3 py-2 font-semibold text-ink">{col.name}</td>
                    <td className="px-3 py-2">
                      <TypeBadge dtype={col.dtype} />
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted">
                      {formatNumber(col.unique_count)}
                    </td>
                    <td className="px-3 py-2 min-w-[110px]">
                      <NullBar percent={col.null_percentage} count={col.null_count} />
                    </td>
                    <td className="px-3 py-2 text-muted">
                      {summarizeColumn(col)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function TypeBadge({ dtype }) {
  const label = shortDtype(dtype);
  const tone =
    label === "number"
      ? "bg-accent/10 text-accent"
      : label === "date"
        ? "bg-[#9a5b1d]/10 text-[var(--warn)]"
        : "bg-soft text-muted";
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase ${tone}`}>
      {label}
    </span>
  );
}

function NullBar({ percent, count }) {
  const pct = Math.max(0, Math.min(100, Number(percent) || 0));
  return (
    <div>
      <div className="mb-1 flex justify-between gap-2 tabular-nums text-[10px] text-muted">
        <span>{pct.toFixed(1)}%</span>
        <span>{formatNumber(count)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-soft">
        <div
          className={`h-full rounded-full ${pct > 20 ? "bg-[var(--warn)]" : "bg-accent"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function summarizeColumn(col) {
  const stats = col.stats || {};
  if (stats.mean != null || stats.min != null) {
    const parts = [];
    if (stats.min != null) parts.push(`min ${formatCompact(stats.min)}`);
    if (stats.mean != null) parts.push(`avg ${formatCompact(stats.mean)}`);
    if (stats.max != null) parts.push(`max ${formatCompact(stats.max)}`);
    return parts.join(" · ") || "—";
  }
  const top = stats.top_values;
  if (Array.isArray(top) && top.length) {
    const first = top[0];
    if (first && typeof first === "object") {
      return `${first.value ?? first.label ?? "—"} (${formatNumber(first.count)})`;
    }
    return String(first);
  }
  return "—";
}

function shortDtype(dtype) {
  const text = String(dtype || "").toLowerCase();
  if (/(int|float|double|decimal|number)/.test(text)) return "number";
  if (/(datetime|date|time)/.test(text)) return "date";
  if (/bool/.test(text)) return "bool";
  return "text";
}

function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString();
}

function formatCompact(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const num = Number(value);
  if (Math.abs(num) >= 1000) return num.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return Number.isInteger(num) ? String(num) : num.toFixed(2);
}
