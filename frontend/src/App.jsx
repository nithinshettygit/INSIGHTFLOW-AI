import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  analyzeInsight,
  createChart,
  deleteDataset,
  detectIntent,
  getDatasetProfile,
  getErrorMessage,
  healthCheck,
  listDatasets,
  queryRag,
  runAnalytics,
  runMl,
  uploadDataset,
} from "./api/client";
import ChartPanel from "./components/ChartPanel";
import ChatPanel from "./components/ChatPanel";
import DatasetPanel from "./components/DatasetPanel";
import ResultsPanel from "./components/ResultsPanel";
import {
  buildAnalyticsPayload,
  buildInsightPayload,
  buildMlPayload,
  buildVisualizationPayload,
  summarizeExtremeAnswer,
} from "./lib/queryRouter";

let messageSeq = 0;
function nextId() {
  messageSeq += 1;
  return `m-${messageSeq}`;
}

export default function App() {
  const [datasets, setDatasets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [apiStatus, setApiStatus] = useState("checking");
  const [chart, setChart] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [ragResult, setRagResult] = useState(null);
  const [mlResult, setMlResult] = useState(null);
  const [insightResult, setInsightResult] = useState(null);
  const [lastIntent, setLastIntent] = useState(null);
  const [error, setError] = useState("");
  const [datasetsOpen, setDatasetsOpen] = useState(false);
  const [sessionId] = useState(() => createSessionId());
  const visualizationRef = useRef(null);

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.dataset_id === selectedId) || null,
    [datasets, selectedId],
  );

  const refreshDatasets = useCallback(async (preferId) => {
    const data = await listDatasets();
    setDatasets(data.datasets || []);
    if (preferId) {
      setSelectedId(preferId);
      return preferId;
    }
    setSelectedId((current) => {
      if (current && data.datasets?.some((item) => item.dataset_id === current)) {
        return current;
      }
      return data.datasets?.[0]?.dataset_id || null;
    });
    return preferId || data.datasets?.[0]?.dataset_id || null;
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await healthCheck();
        if (!active) return;
        setApiStatus("online");
        await refreshDatasets();
      } catch (err) {
        if (!active) return;
        setApiStatus("offline");
        setError(getErrorMessage(err));
      }
    })();
    return () => {
      active = false;
    };
  }, [refreshDatasets]);

  useEffect(() => {
    if (!selectedId) {
      setProfile(null);
      return;
    }
    let active = true;
    (async () => {
      try {
        const data = await getDatasetProfile(selectedId);
        if (active) setProfile(data);
      } catch (err) {
        if (active) {
          setProfile(null);
          setError(getErrorMessage(err));
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedId]);

  async function handleUpload(file) {
    setUploading(true);
    setError("");
    try {
      const uploaded = await uploadDataset(file);
      const id = uploaded.dataset.dataset_id;
      await refreshDatasets(id);
      setDatasetsOpen(true);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: `Uploaded and profiled ${uploaded.dataset.original_filename}.`,
          meta: `${uploaded.dataset.dataset_type} · ${uploaded.dataset.size_bytes} bytes`,
        },
      ]);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteDataset(item) {
    const name = item.original_filename || "this dataset";
    const confirmed = window.confirm(
      `Delete "${name}"? This removes the upload, profile, and any RAG index.`,
    );
    if (!confirmed) return;

    setDeletingId(item.dataset_id);
    setError("");
    try {
      await deleteDataset(item.dataset_id);
      const wasSelected = selectedId === item.dataset_id;
      await refreshDatasets(wasSelected ? null : selectedId);
      if (wasSelected) {
        setChart(null);
        setAnalytics(null);
        setRagResult(null);
        setMlResult(null);
        setInsightResult(null);
        setLastIntent(null);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: `Deleted ${name}.`,
        },
      ]);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDeletingId(null);
    }
  }

  function handleSelectDataset(id) {
    setSelectedId(id);
    setDatasetsOpen(false);
  }

  function scrollToVisualization() {
    visualizationRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleSubmit() {
    const text = query.trim();
    if (!text || !selectedId || busy) return;

    setBusy(true);
    setError("");
    setQuery("");
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", content: text },
    ]);

    try {
      const intent = await detectIntent(text, selectedId, sessionId);
      setLastIntent(intent);

      const engine = intent.target_engine;
      const provider = intent.orchestration?.provider || "unknown";
      let assistantContent = `Routed to ${engine} (${intent.intent}, ${provider}).`;
      let meta = intent.routing?.message || "";

      if (engine === "none" || intent.intent === "unknown") {
        assistantContent =
          intent.reply ||
          intent.routing?.message ||
          "I'm not sure how to help with that yet. Try a KPI, chart, forecast, or insight question.";
        meta = intent.memory_applied ? "unknown · memory idle" : "unknown";
      } else if (engine === "visualization") {
        const payload = buildVisualizationPayload(selectedId, intent, text);
        const needsPair =
          payload.chart_type === "scatter"
            ? payload.metrics.length >= 2 ||
              (payload.metrics.length >= 1 && payload.dimensions.length >= 1)
            : payload.metrics.length >= 1 && payload.dimensions.length >= 1;
        if (!needsPair) {
          throw new Error(
            "Visualization needs grounded metrics/dimensions from the dataset schema.",
          );
        }
        const chartResult = await createChart(payload);
        setChart(chartResult);
        setAnalytics(null);
        setRagResult(null);
        setMlResult(null);
        setInsightResult(null);
        const extremeAnswer = summarizeExtremeAnswer(
          text,
          intent,
          chartResult.data_preview || [],
        );
        assistantContent =
          extremeAnswer ||
          `Built a ${chartResult.chart_type} chart: ${
            chartResult.title || text
          }`;
        meta = `rows plotted: ${chartResult.applied?.row_count_plotted ?? "—"}`;
        if (intent.memory_applied) {
          meta = `${meta} · memory`;
        }
      } else if (engine === "analytics") {
        const payload = buildAnalyticsPayload(selectedId, intent, text);
        const analyticsResult = await runAnalytics(payload);
        setAnalytics(analyticsResult);
        setRagResult(null);
        setMlResult(null);
        setInsightResult(null);
        const extremeAnswer = summarizeExtremeAnswer(
          text,
          intent,
          analyticsResult.results || [],
        );
        assistantContent =
          extremeAnswer ||
          `Analytics complete — ${analyticsResult.result_count} result rows.`;
        meta = `filtered ${analyticsResult.row_count_after_filter}/${analyticsResult.row_count_before} rows`;
        if (intent.memory_applied) {
          meta = `${meta} · memory`;
        }      } else if (engine === "rag") {
        const rag = await queryRag({
          dataset_id: selectedId,
          question: text,
        });
        setRagResult(rag);
        setAnalytics(null);
        setMlResult(null);
        setInsightResult(null);
        setChart(null);
        assistantContent = rag.answer;
        meta = `${rag.sources?.length || 0} sources · ${rag.provider}`;
      } else if (engine === "ml") {
        const payload = buildMlPayload(selectedId, intent, text);
        const ml = await runMl(payload);
        setMlResult(ml);
        setAnalytics(null);
        setRagResult(null);
        setInsightResult(null);
        if (ml.plotly_figure) {
          setChart({
            chart_type: ml.task,
            title: `${ml.task} · ${ml.model}`,
            plotly_figure: ml.plotly_figure,
            applied: ml.applied,
          });
        } else {
          setChart(null);
        }
        assistantContent = `ML ${ml.task} complete via ${ml.model}.`;
        meta = summarizeMl(ml);
      } else if (engine === "insight") {
        const payload = buildInsightPayload(selectedId, intent, text);
        const insight = await analyzeInsight(payload);
        setInsightResult(insight);
        setAnalytics(null);
        setRagResult(null);
        setMlResult(null);
        assistantContent = `${insight.headline}\n\n${insight.explanation}`;
        meta = `${insight.mode} · ${insight.provider} · ${insight.findings?.length || 0} findings`;
      } else if (engine === "profiling") {
        const profileResult = await getDatasetProfile(selectedId);
        setProfile(profileResult);
        setAnalytics(null);
        setRagResult(null);
        setMlResult(null);
        setInsightResult(null);
        assistantContent = "Loaded dataset profile.";
        meta = `rows ${profileResult.profile?.row_count ?? "—"} · cols ${profileResult.profile?.column_count ?? "—"}`;
      } else {
        assistantContent = intent.routing?.message || "That engine is not ready yet.";
        meta = `status: ${intent.routing?.status || "planned"}`;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: assistantContent,
          meta,
        },
      ]);
    } catch (err) {
      const detail = getErrorMessage(err);
      setError(detail);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: `Could not complete that request: ${detail}`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell relative">
      {/* Page 1: Results + Chat */}
      <section className="relative flex h-dvh max-h-dvh flex-col overflow-hidden px-3 py-3 md:px-5 md:py-4">
        <header className="mx-auto w-full max-w-[1500px] shrink-0">
          <div className="panel flex items-center gap-3 rounded-2xl px-3 py-3.5 md:gap-4 md:px-5 md:py-4">
            <div className="brand-rail shrink-0" aria-hidden />

            <div className="min-w-0 flex-1">
              <h1 className="brand-mark truncate font-display text-[1.65rem] font-extrabold text-ink sm:text-3xl md:text-[2.05rem]">
                InsightFlow AI
              </h1>
              <p className="mt-1 text-[11px] font-semibold tracking-[0.02em] text-ink/80 md:text-sm">
                Business intelligence · ask data, charts, forecasts & insights
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 sm:hidden">
                <span className="status-pill">
                  <span
                    className={`status-dot ${apiStatus === "online" ? "is-online" : ""}`}
                  />
                  API {apiStatus}
                </span>
                <span className="status-pill max-w-[12rem] truncate">
                  {selectedDataset?.original_filename || "No dataset"}
                </span>
              </div>
            </div>

            <div className="hidden shrink-0 items-end gap-2 sm:flex sm:flex-col">
              <span className="status-pill">
                <span
                  className={`status-dot ${apiStatus === "online" ? "is-online" : ""}`}
                />
                API {apiStatus}
              </span>
              <span className="status-pill max-w-[240px] truncate" title={selectedDataset?.original_filename || ""}>
                {selectedDataset?.original_filename || "No dataset selected"}
              </span>
            </div>

            <button
              type="button"
              aria-label={datasetsOpen ? "Close datasets menu" : "Open datasets menu"}
              aria-expanded={datasetsOpen}
              onClick={() => setDatasetsOpen((open) => !open)}
              className={`inline-flex h-12 shrink-0 items-center gap-2.5 rounded-xl border px-3.5 text-sm font-semibold transition ${
                datasetsOpen
                  ? "border-accent-deep bg-accent text-white shadow-md"
                  : "border-accent/40 bg-accent-soft text-accent-deep hover:border-accent hover:bg-accent hover:text-white"
              }`}
            >
              <HamburgerIcon open={datasetsOpen} light={datasetsOpen} />
              <span className="hidden sm:inline">
                {datasetsOpen ? "Close" : "Datasets"}
              </span>
              {datasets.length > 0 && (
                <span
                  className={`inline-flex min-w-[1.35rem] items-center justify-center rounded-full px-1.5 text-[11px] font-bold ${
                    datasetsOpen
                      ? "bg-white/20 text-white"
                      : "bg-accent text-white"
                  }`}
                >
                  {datasets.length}
                </span>
              )}
            </button>
          </div>

          {error && (
            <div className="mt-2 rounded-xl border border-[var(--warn)]/30 bg-[#fff7ed] px-4 py-2.5 text-sm text-[var(--warn)]">
              {error}
              <button
                type="button"
                className="ml-3 text-xs font-semibold underline"
                onClick={() => setError("")}
              >
                Dismiss
              </button>
            </div>
          )}
        </header>

        <div className="relative mx-auto mt-3 flex min-h-0 w-full max-w-[1500px] flex-1 gap-3 pb-14">
          <div
            className={`fixed inset-0 z-40 bg-ink/25 transition-opacity duration-200 ${
              datasetsOpen ? "opacity-100" : "pointer-events-none opacity-0"
            }`}
            onClick={() => setDatasetsOpen(false)}
            aria-hidden={!datasetsOpen}
          />
          <aside
            className={`fixed inset-y-3 right-3 z-50 w-[min(320px,88vw)] shrink-0 transform transition-transform duration-200 ease-out md:inset-y-4 md:right-5 md:w-[300px] ${
              datasetsOpen ? "translate-x-0" : "translate-x-[120%]"
            }`}
          >
            <DatasetPanel
              datasets={datasets}
              selectedId={selectedId}
              onSelect={handleSelectDataset}
              onUpload={handleUpload}
              onDelete={handleDeleteDataset}
              uploading={uploading}
              deletingId={deletingId}
              profile={profile}
              onClose={() => setDatasetsOpen(false)}
            />
          </aside>

          <main className="grid min-h-0 min-w-0 flex-1 grid-rows-[minmax(0,1fr)_minmax(260px,36%)] gap-3 lg:grid-cols-[minmax(0,1fr)_340px] lg:grid-rows-none">
            <section className="min-h-0 min-w-0 overflow-hidden">
              <ResultsPanel
                analytics={analytics}
                ragResult={ragResult}
                mlResult={mlResult}
                insightResult={insightResult}
                profileDetail={profile}
                intent={lastIntent}
              />
            </section>

            <section className="min-h-0 min-w-0 overflow-hidden">
              <ChatPanel
                messages={messages}
                query={query}
                setQuery={setQuery}
                onSubmit={handleSubmit}
                busy={busy}
                disabled={!selectedId || apiStatus !== "online"}
              />
            </section>
          </main>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-3 z-30 flex justify-center px-3">
          <button
            type="button"
            onClick={scrollToVisualization}
            className="scroll-cue pointer-events-auto inline-flex items-center gap-2 rounded-full border border-accent/35 bg-white/95 px-4 py-2.5 text-sm font-semibold text-accent-deep shadow-lg backdrop-blur transition hover:border-accent hover:bg-accent-soft"
          >
            <span className="scroll-cue-arrow" aria-hidden>
              ↓
            </span>
            Scroll down to view Visualization
          </button>
        </div>
      </section>

      {/* Page 2: Visualization */}
      <section
        id="visualization"
        ref={visualizationRef}
        className="min-h-dvh px-3 py-4 md:px-5 md:py-6"
      >
        <div className="mx-auto flex h-[calc(100dvh-2rem)] max-w-[1500px] flex-col gap-3 md:h-[calc(100dvh-3rem)]">
          <div className="panel flex shrink-0 items-center justify-between gap-3 rounded-2xl px-4 py-3 md:px-5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="brand-rail h-10 min-h-0" aria-hidden />
              <div className="min-w-0">
                <h2 className="font-display text-xl font-bold text-ink md:text-2xl">
                  Visualization
                </h2>
                <p className="mt-0.5 text-xs text-muted md:text-sm">
                  Charts from your latest visualization or ML run
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                window.scrollTo({ top: 0, behavior: "smooth" })
              }
              className="shrink-0 rounded-full border border-line bg-white/90 px-3 py-2 text-xs font-semibold text-muted transition hover:border-accent hover:bg-accent-soft hover:text-accent-deep"
            >
              ↑ Back to Results
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            <ChartPanel chart={chart} />
          </div>
        </div>
      </section>
    </div>
  );
}

function createSessionId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function HamburgerIcon({ open, light = false }) {
  const bar = light ? "bg-white" : "bg-accent";
  return (
    <span className="relative block h-[14px] w-[18px]" aria-hidden>
      <span
        className={`absolute left-0 top-0 h-[2.5px] w-[18px] rounded-full transition ${bar} ${
          open ? "translate-y-[6px] rotate-45" : ""
        }`}
      />
      <span
        className={`absolute left-0 top-[6px] h-[2.5px] w-[18px] rounded-full transition ${bar} ${
          open ? "opacity-0" : ""
        }`}
      />
      <span
        className={`absolute left-0 top-[12px] h-[2.5px] w-[18px] rounded-full transition ${bar} ${
          open ? "-translate-y-[6px] -rotate-45" : ""
        }`}
      />
    </span>
  );
}

function summarizeMl(ml) {
  if (!ml) return "";
  if (ml.task === "forecast") {
    return `horizon ${ml.summary?.horizon ?? "—"} · MAE ${ml.summary?.train_mae ?? "—"}`;
  }
  if (ml.task === "segmentation") {
    return `${ml.summary?.n_clusters ?? "—"} clusters · ${ml.summary?.row_count ?? "—"} rows`;
  }
  if (ml.task === "anomaly") {
    return `${ml.summary?.anomaly_count ?? 0} anomalies · rate ${ml.summary?.anomaly_rate ?? "—"}`;
  }
  return ml.model || "";
}
