export default function DatasetPanel({
  datasets,
  selectedId,
  onSelect,
  onUpload,
  uploading,
  profile,
}) {
  return (
    <aside className="panel flex h-full flex-col overflow-hidden rounded-2xl">
      <div className="border-b border-line px-5 py-4">
        <h2 className="font-display text-lg font-bold tracking-tight">Datasets</h2>
        <p className="mt-1 text-sm text-muted">
          Upload CSV, Excel, or PDF. Profiling runs automatically.
        </p>
      </div>

      <label className="mx-5 mt-4 block cursor-pointer rounded-xl border border-dashed border-line bg-soft/70 px-4 py-3 text-sm transition hover:border-accent hover:bg-soft">
        <span className="font-semibold text-accent">
          {uploading ? "Uploading…" : "Choose file to upload"}
        </span>
        <input
          type="file"
          accept=".csv,.xlsx,.pdf"
          className="hidden"
          disabled={uploading}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
            event.target.value = "";
          }}
        />
      </label>

      <div className="side-scroll mt-3 flex-1 overflow-y-auto px-3 pb-4">
        {datasets.length === 0 ? (
          <p className="px-2 py-6 text-sm text-muted">No datasets yet.</p>
        ) : (
          <ul className="space-y-2">
            {datasets.map((item) => {
              const active = item.dataset_id === selectedId;
              return (
                <li key={item.dataset_id}>
                  <button
                    type="button"
                    onClick={() => onSelect(item.dataset_id)}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                      active
                        ? "border-accent bg-accent/10"
                        : "border-transparent bg-white/50 hover:border-line hover:bg-white/80"
                    }`}
                  >
                    <div className="truncate text-sm font-semibold">
                      {item.original_filename}
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {item.dataset_type.toUpperCase()}
                      {item.extra?.row_count != null
                        ? ` · ${item.extra.row_count} rows`
                        : ""}
                      {item.extra?.page_count != null
                        ? ` · ${item.extra.page_count} pages`
                        : ""}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {profile?.profile && (
        <div className="border-t border-line px-5 py-4 text-xs text-muted">
          <div className="font-semibold text-ink">Profile snapshot</div>
          <div className="mt-2 space-y-1">
            <div>Rows: {profile.profile.row_count ?? "—"}</div>
            <div>Columns: {profile.profile.column_count ?? "—"}</div>
            <div>Missing: {profile.profile.missing_values_total ?? "—"}</div>
            <div>Duplicates: {profile.profile.duplicate_rows ?? "—"}</div>
          </div>
        </div>
      )}
    </aside>
  );
}
