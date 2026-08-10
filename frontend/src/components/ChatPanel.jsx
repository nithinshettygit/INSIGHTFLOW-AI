import { useEffect, useRef } from "react";

export default function ChatPanel({
  messages,
  query,
  setQuery,
  onSubmit,
  busy,
  disabled,
}) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden rounded-[14px]">
      <div className="panel-header-chat shrink-0 border-b border-line px-4 py-3 md:px-5">
        <div className="flex items-start gap-2.5">
          <span className="icon-bubble icon-bubble-ai mt-0.5" aria-hidden>
            <AiSparkIcon />
          </span>
          <div>
            <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
              Ask InsightFlow
            </h2>
            <p className="mt-1 text-xs text-muted md:text-sm">
              Ask for KPIs, charts, forecasts, document QA, or insights.
            </p>
          </div>
        </div>
      </div>

      <div className="chat-scroll min-h-0 flex-1 space-y-3 overflow-y-auto bg-panel px-3 py-3 md:px-4">
        {messages.length === 0 && (
          <div className="suggest-box rounded-[12px] px-4 py-3 text-sm">
            <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ai">
              <BulbIcon />
              Try asking
            </div>
            <p className="leading-relaxed">
              “Bar chart of sales by region”, “Forecast next month sales”, or
              “Why is profit uneven across regions?”
            </p>
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[92%] rounded-[12px] px-4 py-3 text-sm leading-relaxed ${
              message.role === "user" ? "bubble-user ml-auto" : "bubble-assistant"
            }`}
          >
            <div className="whitespace-pre-wrap">{message.content}</div>
            {message.meta && (
              <div
                className={`mt-2 border-t pt-2 text-xs font-medium ${
                  message.role === "user"
                    ? "border-white/25 text-white/90"
                    : "border-line text-muted"
                }`}
              >
                {message.meta}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="bubble-assistant rounded-[12px] px-4 py-3 text-sm text-muted">
            <span className="inline-flex items-center gap-2">
              <span className="ai-dot" aria-hidden />
              Routing and running engines…
            </span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="composer shrink-0 border-t border-line p-3 md:p-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            disabled={disabled || busy}
            placeholder={
              disabled ? "Select a dataset first" : "Ask a business question…"
            }
            className="input-field min-w-0 flex-1 rounded-[12px] px-3 py-3 text-sm"
          />
          <button
            type="submit"
            disabled={disabled || busy || !query.trim()}
            className="btn-ai inline-flex items-center gap-1.5 rounded-[12px] px-4 py-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SendIcon />
            Send
          </button>
        </div>
      </form>
    </section>
  );
}

function AiSparkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3 13.4 8.6 19 10 13.4 11.4 12 17 10.6 11.4 5 10 10.6 8.6 12 3Z"
        fill="currentColor"
      />
    </svg>
  );
}

function BulbIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M9 18h6M10 21h4M8 14c-1.5-1-2.5-2.6-2.5-4.5a6.5 6.5 0 1 1 13 0c0 1.9-1 3.5-2.5 4.5-.7.5-1.2 1.2-1.4 2H9.9c-.2-.8-.7-1.5-1.4-2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 12 20 4l-6 16-2.5-6.5L4 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
