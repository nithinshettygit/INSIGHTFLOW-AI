import ProfileCard from "./ProfileCard";

export default function ResultsPanel({
  analytics,
  ragResult,
  mlResult,
  insightResult,
  profileDetail,
  intent,
}) {
  const analyticsRows = analytics?.results || [];
  const mlRows = mlResult?.results || [];
  const rows = mlRows.length ? mlRows : analyticsRows;
  const columns =
    rows.length > 0 ? Object.keys(rows[0]).filter((key) => key !== "grounding") : [];
  const sources = ragResult?.sources || [];
  const findings = insightResult?.findings || [];
  const recommendations = insightResult?.recommendations || [];
  const rootCauses = insightResult?.root_causes || [];
  const showProfile =
    Boolean(profileDetail?.profile) &&
    !analytics &&
    !ragResult &&
    !mlResult &&
    !insightResult;

  const kpiEntries = flattenKpis(analytics?.kpis);

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden rounded-[12px]">
      <div className="panel-header-results shrink-0 border-b border-line px-4 py-3 md:px-5 md:py-4">
        <div className="flex items-start gap-2.5">
          <span className="icon-bubble icon-bubble-mint mt-0.5" aria-hidden>
            <ResultsIcon />
          </span>
          <div>
            <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
              Results
            </h2>
            <p className="mt-1 text-sm text-muted">
              Profile, analytics, ML outputs, RAG sources, and routing details.
            </p>
          </div>
        </div>
      </div>

      <div className="side-scroll min-h-0 flex-1 space-y-4 overflow-y-auto bg-panel p-4 text-sm">
        {intent && (
          <div className="result-block rounded-[12px] border border-line bg-soft p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="section-label">Last intent</span>
              <EngineBadge engine={intent.target_engine || intent.intent} />
              {intent.confidence != null && (
                <span className="badge badge-neutral">
                  {(intent.confidence * 100).toFixed(0)}% confidence
                </span>
              )}
            </div>
            <div className="mt-2 font-semibold text-ink">
              {intent.intent} → {intent.target_engine}
            </div>
            <div className="mt-1 text-xs text-muted">
              {intent.orchestration?.provider || "router"}
            </div>
            {intent.rationale && (
              <div className="mt-2 text-xs leading-relaxed text-muted">
                {intent.rationale}
              </div>
            )}
          </div>
        )}

        {insightResult && (
          <div className="result-block space-y-3">
            <div className="engine-stripe engine-stripe-insight rounded-[12px] border border-line bg-white p-3 pl-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="badge badge-ai">AI Insight</span>
                <span className="badge badge-warn">{insightResult.mode}</span>
                <span className="badge badge-neutral">{insightResult.provider}</span>
              </div>
              <h3 className="mt-3 text-base font-semibold text-ink">
                {insightResult.headline}
              </h3>
              <p className="mt-2 whitespace-pre-wrap leading-relaxed text-muted">
                {insightResult.explanation}
              </p>
            </div>

            {findings.length > 0 && (
              <div className="rounded-[12px] border border-line bg-white p-3">
                <div className="section-label">Findings</div>
                <ul className="mt-2 space-y-2">
                  {findings.map((item, index) => (
                    <li
                      key={`${item.title}-${index}`}
                      className="rounded-lg border border-line bg-soft px-3 py-2 text-xs"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-ink">{item.title}</span>
                        {item.severity != null && (
                          <span className="badge badge-neutral">{item.severity}</span>
                        )}
                      </div>
                      <div className="mt-1 text-muted">{item.detail}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {rootCauses.length > 0 && (
              <div className="rounded-[12px] border border-line bg-white p-3">
                <div className="section-label">Root causes</div>
                <ul className="mt-2 space-y-2">
                  {rootCauses.map((item, index) => (
                    <li
                      key={`${item.cause}-${index}`}
                      className="rounded-lg border border-amber/20 bg-amber-soft px-3 py-2 text-xs"
                    >
                      <span className="font-semibold text-ink">{item.cause}</span>
                      {item.confidence != null ? (
                        <span className="ml-2 badge badge-warn">
                          {(Number(item.confidence) * 100).toFixed(0)}%
                        </span>
                      ) : null}
                      <div className="mt-1 text-muted">{item.evidence}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {recommendations.length > 0 && (
              <div className="rounded-[12px] border border-line bg-white p-3">
                <div className="section-label">Recommendations</div>
                <ul className="mt-2 space-y-2">
                  {recommendations.map((item, index) => (
                    <li
                      key={`${item.action}-${index}`}
                      className="rounded-lg border border-accent/20 bg-accent-soft px-3 py-2 text-xs"
                    >
                      <span className="font-semibold text-accent-deep">
                        P{item.priority}: {item.action}
                      </span>
                      <div className="mt-1 text-muted">{item.rationale}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {mlResult && (
          <div className="result-block engine-stripe engine-stripe-ml rounded-[12px] border border-line bg-white p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="badge badge-ai">ML</span>
              <span className="badge badge-neutral">{mlResult.task}</span>
              <span className="badge badge-neutral">{mlResult.model}</span>
            </div>
            <h3 className="mt-3 font-semibold text-ink">
              {mlResult.task} summary
            </h3>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(mlResult.summary || {})
                .filter(([, value]) => isPrimitive(value))
                .slice(0, 6)
                .map(([key, value]) => (
                  <div key={key} className="stat-tile rounded-[10px] px-3 py-2">
                    <div className="kpi-label">{key}</div>
                    <div className="mt-1 text-sm font-semibold text-ink tabular-nums">
                      {formatCell(value)}
                    </div>
                  </div>
                ))}
            </div>
            <pre className="mt-3 max-h-40 overflow-auto rounded-[10px] bg-soft p-2 text-[11px] text-muted">
              {JSON.stringify(mlResult.summary || {}, null, 2)}
            </pre>
          </div>
        )}

        {ragResult && (
          <div className="result-block engine-stripe engine-stripe-rag rounded-[12px] border border-line bg-white p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="badge badge-ai">Document QA</span>
              <span className="badge badge-neutral">{ragResult.provider}</span>
            </div>
            <h3 className="mt-3 font-semibold text-ink">Answer</h3>
            <p className="mt-2 whitespace-pre-wrap leading-relaxed text-ink">
              {ragResult.answer}
            </p>
            <div className="mt-2 text-xs text-muted">
              {ragResult.applied?.chunk_count != null
                ? `Index chunks: ${ragResult.applied.chunk_count}`
                : "RAG response"}
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="result-block space-y-2">
            <div className="section-label">Sources</div>
            {sources.map((source) => (
              <div
                key={source.chunk_id}
                className="rounded-[12px] border border-line bg-soft p-3"
              >
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="badge badge-neutral">
                    {source.page_number != null
                      ? `page ${source.page_number}`
                      : "page —"}
                  </span>
                  <span className="badge badge-neutral">
                    score {Number(source.score).toFixed(3)}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-ink whitespace-pre-wrap">
                  {source.text.length > 320
                    ? `${source.text.slice(0, 317)}...`
                    : source.text}
                </p>
              </div>
            ))}
          </div>
        )}

        {kpiEntries.length > 0 && !mlResult && !insightResult && (
          <div className="result-block engine-stripe rounded-[12px] border border-line bg-white p-3">
            <div className="flex items-center gap-2">
              <span className="badge badge-success">Analytics</span>
              <span className="section-label">KPIs</span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {kpiEntries.slice(0, 8).map((item) => (
                <div key={item.key} className="stat-tile rounded-[10px] px-3 py-2.5">
                  <div className="kpi-label">{item.label}</div>
                  <div
                    className={`kpi-value mt-1 text-lg ${
                      item.tone === "neg"
                        ? "text-error"
                        : item.tone === "pos"
                          ? "text-accent-deep"
                          : "text-ink"
                    }`}
                  >
                    {item.display}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {rows.length > 0 && !insightResult && (
          <div className="result-block overflow-hidden rounded-[12px] border border-line">
            <div className="border-b border-line bg-soft px-3 py-2">
              <span className="section-label">
                {mlResult ? "ML preview" : "Table"}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-soft">
                  <tr>
                    {columns.map((column) => (
                      <th
                        key={column}
                        className="px-3 py-2 font-semibold text-muted"
                      >
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 25).map((row, index) => (
                    <tr key={index} className="border-t border-line bg-white">
                      {columns.map((column) => (
                        <td
                          key={column}
                          className="px-3 py-2 whitespace-nowrap text-ink tabular-nums"
                        >
                          {formatCell(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {showProfile && (
          <div className="result-block engine-stripe engine-stripe-profile">
            <ProfileCard
              profile={profileDetail.profile}
              source={profileDetail.source}
            />
          </div>
        )}

        {!intent &&
          !analytics &&
          !ragResult &&
          !mlResult &&
          !insightResult &&
          !profileDetail && (
            <div className="empty-state">
              <div className="empty-visual" aria-hidden>
                <span className="empty-spark" />
                <span className="empty-spark" />
                <span className="empty-spark" />
                <EmptyChartIcon />
              </div>
              <p className="text-base font-semibold text-ink">
                Engine output will show up here.
              </p>
              <p className="mt-1 max-w-sm text-sm text-muted">
                Run a query to see profile details, analytics, charts, insights and
                more.
              </p>
            </div>
          )}
      </div>
    </section>
  );
}

function ResultsIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 19V10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M10 19V5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M16 19v-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M22 19H2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function EmptyChartIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 16.5 9 12l3.5 3.5L20 7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M4 20h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function EngineBadge({ engine }) {
  const key = String(engine || "").toLowerCase();
  if (key.includes("ml")) return <span className="badge badge-ai">ML</span>;
  if (key.includes("rag")) return <span className="badge badge-ai">RAG</span>;
  if (key.includes("insight")) return <span className="badge badge-warn">Insight</span>;
  if (key.includes("visual")) return <span className="badge badge-success">Visualization</span>;
  if (key.includes("profil")) return <span className="badge badge-neutral">Profile</span>;
  if (key.includes("analytic")) return <span className="badge badge-success">Analytics</span>;
  return <span className="badge badge-neutral">{engine || "engine"}</span>;
}

function flattenKpis(kpis) {
  if (!kpis || typeof kpis !== "object") return [];
  const entries = [];
  for (const [key, value] of Object.entries(kpis)) {
    if (value != null && typeof value === "object" && !Array.isArray(value)) {
      for (const [stat, nested] of Object.entries(value)) {
        if (!isPrimitive(nested)) continue;
        const num = Number(nested);
        entries.push({
          key: `${key}.${stat}`,
          label: `${key} · ${stat}`,
          display: formatCell(nested),
          tone:
            Number.isFinite(num) && num < 0
              ? "neg"
              : Number.isFinite(num) && num > 0 && /profit|growth|rate/i.test(key)
                ? "pos"
                : "neutral",
        });
      }
    } else if (isPrimitive(value)) {
      const num = Number(value);
      entries.push({
        key,
        label: key,
        display: formatCell(value),
        tone: Number.isFinite(num) && num < 0 ? "neg" : "neutral",
      });
    }
  }
  return entries;
}

function isPrimitive(value) {
  return (
    value == null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

function formatCell(value) {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
