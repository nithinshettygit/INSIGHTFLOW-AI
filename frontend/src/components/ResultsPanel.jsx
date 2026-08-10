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

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden rounded-2xl">
      <div className="panel-header-results shrink-0 border-b border-line px-4 py-3 md:px-5 md:py-4">
        <h2 className="font-display text-lg tracking-tight text-ink">Results</h2>
        <p className="mt-1 text-sm text-muted">
          Profile, analytics, ML outputs, RAG sources, and routing details.
        </p>
      </div>

      <div className="side-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        {intent && (
          <div className="rounded-xl bg-platinum-deep/90 p-3 ring-1 ring-champagne/25">
            <div className="font-semibold text-ink">Last intent</div>
            <div className="mt-1 text-muted">
              {intent.intent} → {intent.target_engine} ({intent.orchestration?.provider})
              {intent.confidence != null ? ` · ${(intent.confidence * 100).toFixed(0)}%` : ""}
            </div>
            {intent.rationale && (
              <div className="mt-2 text-muted">{intent.rationale}</div>
            )}
          </div>
        )}

        {insightResult && (
          <div className="space-y-3">
            <div className="rounded-xl bg-soft/80 p-3">
              <div className="font-semibold">
                Insight · {insightResult.mode} ({insightResult.provider})
              </div>
              <div className="mt-2 font-medium text-ink">{insightResult.headline}</div>
              <p className="mt-2 whitespace-pre-wrap text-muted">
                {insightResult.explanation}
              </p>
            </div>

            {findings.length > 0 && (
              <div className="rounded-xl ring-1 ring-line bg-white/70 p-3">
                <div className="font-semibold">Findings</div>
                <ul className="mt-2 space-y-2">
                  {findings.map((item, index) => (
                    <li key={`${item.title}-${index}`} className="text-xs text-muted">
                      <span className="font-semibold text-ink">{item.title}</span>
                      {" · "}
                      {item.severity}
                      <div className="mt-1">{item.detail}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {rootCauses.length > 0 && (
              <div className="rounded-xl ring-1 ring-line bg-white/70 p-3">
                <div className="font-semibold">Root causes</div>
                <ul className="mt-2 space-y-2">
                  {rootCauses.map((item, index) => (
                    <li key={`${item.cause}-${index}`} className="text-xs text-muted">
                      <span className="font-semibold text-ink">{item.cause}</span>
                      {item.confidence != null
                        ? ` · confidence ${(Number(item.confidence) * 100).toFixed(0)}%`
                        : ""}
                      <div className="mt-1">{item.evidence}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {recommendations.length > 0 && (
              <div className="rounded-xl ring-1 ring-line bg-white/70 p-3">
                <div className="font-semibold">Recommendations</div>
                <ul className="mt-2 space-y-2">
                  {recommendations.map((item, index) => (
                    <li key={`${item.action}-${index}`} className="text-xs text-muted">
                      <span className="font-semibold text-ink">
                        P{item.priority}: {item.action}
                      </span>
                      <div className="mt-1">{item.rationale}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {mlResult && (
          <div className="rounded-xl bg-soft/80 p-3">
            <div className="font-semibold">
              ML · {mlResult.task} ({mlResult.model})
            </div>
            <pre className="mt-2 overflow-x-auto text-xs text-muted">
              {JSON.stringify(mlResult.summary || {}, null, 2)}
            </pre>
          </div>
        )}

        {ragResult && (
          <div className="rounded-xl bg-soft/80 p-3">
            <div className="font-semibold">Document answer</div>
            <p className="mt-2 whitespace-pre-wrap text-muted">{ragResult.answer}</p>
            <div className="mt-2 text-xs text-muted">
              provider: {ragResult.provider}
              {ragResult.applied?.chunk_count != null
                ? ` · index chunks: ${ragResult.applied.chunk_count}`
                : ""}
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="space-y-2">
            <div className="font-semibold">Sources</div>
            {sources.map((source) => (
              <div
                key={source.chunk_id}
                className="rounded-xl ring-1 ring-line bg-white/70 p-3"
              >
                <div className="text-xs text-muted">
                  {source.page_number != null ? `page ${source.page_number}` : "page —"}
                  {" · "}
                  score {Number(source.score).toFixed(3)}
                </div>
                <p className="mt-1 text-xs text-ink whitespace-pre-wrap">
                  {source.text.length > 320
                    ? `${source.text.slice(0, 317)}...`
                    : source.text}
                </p>
              </div>
            ))}
          </div>
        )}

        {analytics?.kpis && !mlResult && !insightResult && (
          <div className="rounded-xl bg-soft/80 p-3">
            <div className="font-semibold">KPIs</div>
            <pre className="mt-2 overflow-x-auto text-xs text-muted">
              {JSON.stringify(analytics.kpis, null, 2)}
            </pre>
          </div>
        )}

        {rows.length > 0 && !insightResult && (
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

        {showProfile && (
          <ProfileCard
            profile={profileDetail.profile}
            source={profileDetail.source}
          />
        )}

        {!intent &&
          !analytics &&
          !ragResult &&
          !mlResult &&
          !insightResult &&
          !profileDetail && (
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
