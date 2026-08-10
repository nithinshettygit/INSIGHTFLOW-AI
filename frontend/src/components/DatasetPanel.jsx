export default function DatasetPanel({
  datasets,
  selectedId,
  onSelect,
  onUpload,
  onDelete,
  uploading,
  deletingId,
  profile,
  onClose,
}) {
  return (
    <aside className="panel flex h-full flex-col overflow-hidden rounded-[12px] shadow-panel">
      <div className="flex items-start justify-between gap-2 border-b border-line bg-white px-4 py-4 md:px-5">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
            Datasets
          </h2>
          <p className="mt-1 text-sm text-muted">
            Upload CSV, Excel, or PDF. Profiling runs automatically.
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary rounded-lg px-2.5 py-1 text-xs font-semibold"
            aria-label="Close datasets panel"
          >
            Close
          </button>
        )}
      </div>

      <label className="mx-4 mt-4 block cursor-pointer rounded-[12px] border border-dashed border-line bg-soft px-4 py-3 text-sm transition hover:border-accent hover:bg-accent-soft md:mx-5">
        <span className="font-semibold text-accent-deep">
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

      <div className="side-scroll mt-3 min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {datasets.length === 0 ? (
          <p className="px-2 py-6 text-sm text-muted">No datasets yet.</p>
        ) : (
          <ul className="space-y-2">
            {datasets.map((item) => {
              const active = item.dataset_id === selectedId;
              const deleting = deletingId === item.dataset_id;
              return (
                <li key={item.dataset_id}>
                  <div
                    className={`flex items-stretch gap-1 rounded-[12px] border transition ${
                      active
                        ? "border-accent bg-accent-soft"
                        : "border-line bg-white hover:border-accent/40 hover:bg-soft"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelect(item.dataset_id)}
                      className="min-w-0 flex-1 px-3 py-3 text-left"
                    >
                      <div className="truncate text-sm font-semibold text-ink">
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
                    {onDelete && (
                      <button
                        type="button"
                        title={`Delete ${item.original_filename}`}
                        aria-label={`Delete ${item.original_filename}`}
                        disabled={deleting || uploading}
                        onClick={(event) => {
                          event.stopPropagation();
                          onDelete(item);
                        }}
                        className="m-1.5 shrink-0 self-center rounded-lg border border-transparent px-2.5 py-1.5 text-xs font-semibold text-error transition hover:border-error/30 hover:bg-[#fef2f2] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {deleting ? "…" : "Delete"}
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {profile?.profile && (
        <div className="shrink-0 border-t border-line bg-soft px-5 py-4 text-xs text-muted">
          <div className="font-semibold text-ink">Profile snapshot</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
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
