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
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden rounded-2xl">
      <div className="panel-header-chat shrink-0 border-b border-line px-4 py-3 md:px-5">
        <h2 className="font-display text-lg tracking-tight text-ink">Ask InsightFlow</h2>
        <p className="mt-1 text-xs text-muted md:text-sm">
          Ask for KPIs, charts, forecasts, document QA, or insights.
        </p>
      </div>

      <div className="chat-scroll min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3 md:px-4">
        {messages.length === 0 && (
          <div className="rounded-xl bg-soft/90 px-4 py-3 text-sm text-muted ring-1 ring-line/70">
            Try: “Bar chart of sales by region”, “Forecast next month sales”, or
            “Why is profit uneven across regions?”
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              message.role === "user" ? "bubble-user ml-auto" : "bubble-assistant"
            }`}
          >
            <div className="whitespace-pre-wrap">{message.content}</div>
            {message.meta && (
              <div
                className={`mt-2 border-t pt-2 text-xs font-medium ${
                  message.role === "user"
                    ? "border-white/30 text-white"
                    : "border-line text-ink"
                }`}
              >
                {message.meta}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="bubble-assistant rounded-2xl px-4 py-3 text-sm text-muted">
            Routing and running engines…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="composer shrink-0 border-t border-line p-3 backdrop-blur md:p-4"
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
            className="min-w-0 flex-1 rounded-xl border border-line bg-white/90 px-3 py-3 text-sm outline-none ring-accent focus:ring-2"
          />
          <button
            type="submit"
            disabled={disabled || busy || !query.trim()}
            className="rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:bg-accent-deep disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}
