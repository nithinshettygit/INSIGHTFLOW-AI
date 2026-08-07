import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createChart,
  detectIntent,
  getDatasetProfile,
  getErrorMessage,
  healthCheck,
  listDatasets,
  runAnalytics,
  uploadDataset,
} from "./api/client";
import ChartPanel from "./components/ChartPanel";
import ChatPanel from "./components/ChatPanel";
import DatasetPanel from "./components/DatasetPanel";
import ResultsPanel from "./components/ResultsPanel";
import {
  buildAnalyticsPayload,
  buildVisualizationPayload,
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
  const [apiStatus, setApiStatus] = useState("checking");
  const [chart, setChart] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [lastIntent, setLastIntent] = useState(null);
  const [error, setError] = useState("");

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
      const intent = await detectIntent(text, selectedId);
      setLastIntent(intent);

      const engine = intent.target_engine;
      const provider = intent.orchestration?.provider || "unknown";
      let assistantContent = `Routed to ${engine} (${intent.intent}, ${provider}).`;
      let meta = intent.routing?.message || "";

      if (engine === "visualization") {
        const payload = buildVisualizationPayload(selectedId, intent);
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
        assistantContent = `Built a ${chartResult.chart_type} chart: ${chartResult.title}`;
        meta = `rows plotted: ${chartResult.applied?.row_count_plotted ?? "—"}`;
      } else if (engine === "analytics") {
        const payload = buildAnalyticsPayload(selectedId, intent);
        const analyticsResult = await runAnalytics(payload);
        setAnalytics(analyticsResult);
        assistantContent = `Analytics complete — ${analyticsResult.result_count} result rows.`;
        meta = `filtered ${analyticsResult.row_count_after_filter}/${analyticsResult.row_count_before} rows`;
      } else if (engine === "profiling") {
        const profileResult = await getDatasetProfile(selectedId);
        setProfile(profileResult);
        setAnalytics(null);
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
    <div className="relative min-h-screen px-4 py-5 md:px-6 lg:px-8">
      <header className="mx-auto mb-5 max-w-[1400px]">
        <div className="panel overflow-hidden rounded-3xl px-6 py-6 md:px-8 md:py-7">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
                Business Intelligence Platform
              </p>
              <h1 className="brand-mark mt-2 font-display text-4xl font-extrabold text-ink md:text-5xl">
                InsightFlow AI
              </h1>
              <p className="mt-3 max-w-2xl text-sm text-muted md:text-base">
                Upload business data, ask questions, and get routed insights —
                analytics and charts first, LLM only when reasoning is required.
              </p>
            </div>
            <div className="text-sm text-muted">
              <div>
                API:{" "}
                <span
                  className={
                    apiStatus === "online"
                      ? "font-semibold text-accent"
                      : "font-semibold text-[var(--warn)]"
                  }
                >
                  {apiStatus}
                </span>
              </div>
              <div className="mt-1">
                Dataset:{" "}
                <span className="font-semibold text-ink">
                  {selectedDataset?.original_filename || "none selected"}
                </span>
              </div>
            </div>
          </div>
        </div>
        {error && (
          <div className="mt-3 rounded-xl border border-[var(--warn)]/30 bg-[#fff7ed] px-4 py-3 text-sm text-[var(--warn)]">
            {error}
          </div>
        )}
      </header>

      <main className="mx-auto grid max-w-[1400px] gap-4 lg:grid-cols-[280px_minmax(0,1fr)_320px] lg:grid-rows-[minmax(420px,1fr)_300px]">
        <div className="lg:row-span-2 h-[520px] lg:h-auto min-h-[520px]">
          <DatasetPanel
            datasets={datasets}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onUpload={handleUpload}
            uploading={uploading}
            profile={profile}
          />
        </div>

        <div className="min-h-[420px]">
          <ChartPanel chart={chart} />
        </div>

        <div className="min-h-[300px] lg:row-span-2 lg:min-h-0">
          <ChatPanel
            messages={messages}
            query={query}
            setQuery={setQuery}
            onSubmit={handleSubmit}
            busy={busy}
            disabled={!selectedId || apiStatus !== "online"}
          />
        </div>

        <div className="min-h-[280px]">
          <ResultsPanel
            analytics={analytics}
            profileDetail={profile}
            intent={lastIntent}
          />
        </div>
      </main>
    </div>
  );
}
