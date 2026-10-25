"use client";

import { useEffect, useRef, useState } from "react";

type Source = { id: string; kind: "data" | "doc"; label: string; fetched_at?: string };

type AssistantResponse = {
  answer: string;
  sources: Source[];
  refused: boolean;
  grounding: {
    checked: boolean;
    ungrounded_numbers: string[];
    invalid_citations: string[];
    retried: boolean;
  };
  tool_calls: number;
  cached: boolean;
};

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; response: AssistantResponse }
  | { role: "error"; text: string };

const MAX_CHARS = 500;
const EXAMPLES = [
  "Which live pool has the highest risk score right now?",
  "What was the lead time on USDC in March 2023, and how was it measured?",
  "Why does UST show zero lead time?",
  "How many swaps did the feed observe in the last hour?",
];

function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <details className="mt-2">
      <summary className="font-mono text-[11px] text-text-muted cursor-pointer">
        Sources ({sources.length})
      </summary>
      <ul className="mt-1 space-y-0.5">
        {sources.map((s) => (
          <li key={s.id} className="font-mono text-[11px] text-text-secondary">
            <span className="text-text-primary">[{s.id}]</span> {s.label}
            {s.fetched_at && <span className="text-text-muted"> · fetched {s.fetched_at.replace("T", " ").replace("Z", " UTC")}</span>}
          </li>
        ))}
      </ul>
    </details>
  );
}

function GroundingWarning({ g }: { g: AssistantResponse["grounding"] }) {
  const numbers = g.ungrounded_numbers;
  const cites = g.invalid_citations;
  if (numbers.length === 0 && cites.length === 0) return null;
  return (
    <p className="mt-2 border border-border px-2 py-1.5 font-sans text-[12px] text-text-primary" role="note">
      Check before relying on this answer:{" "}
      {numbers.length > 0 && <>these numbers could not be matched to the data ({numbers.join(", ")}). </>}
      {cites.length > 0 && <>it cites sources that do not exist ({cites.join(", ")}).</>}
    </p>
  );
}

export default function Assistant() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, loading]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || loading) return;
    // Last two exchanges as context; the backend caps each turn at 500 chars.
    const history = messages
      .filter((m): m is Exclude<Message, { role: "error" }> => m.role !== "error")
      .slice(-4)
      .map((m) => ({ role: m.role, content: m.text.slice(0, MAX_CHARS) }));
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/api/assistant", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: q, history }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const detail =
          typeof data?.detail === "string"
            ? data.detail
            : res.status === 422
              ? "That question couldn't be processed. Try rephrasing it."
              : "Something went wrong. Please try again.";
        setMessages((m) => [...m, { role: "error", text: detail }]);
      } else {
        setMessages((m) => [...m, { role: "assistant", text: data.answer, response: data }]);
      }
    } catch {
      setMessages((m) => [
        ...m,
        { role: "error", text: "Couldn't reach the assistant. Check your connection and try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="assistant-heading" className="max-w-3xl mx-auto px-5 pt-6 pb-16">
      <h2 id="assistant-heading" className="sr-only">
        Assistant conversation
      </h2>
      <p className="font-sans text-[12.5px] text-text-muted mb-4 border border-border px-3 py-2">
        Descriptive only, not financial advice. Answers come from Meridian&apos;s own data and
        documentation, with sources listed; every number is checked against that data.
      </p>

      {messages.length === 0 && (
        <div className="mb-4">
          <p className="font-sans text-[13px] text-text-muted mb-2">Try asking:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => ask(e)}
                className="text-left font-sans text-[12.5px] text-text-primary border border-border px-2.5 py-1.5 hover:bg-fill"
              >
                {e}
              </button>
            ))}
          </div>
        </div>
      )}

      <div aria-live="polite" className="space-y-4">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={`max-w-[92%] px-3 py-2 border ${
                m.role === "user" ? "border-text-primary bg-fill" : "border-border"
              }`}
            >
              <p className="font-sans text-[13.5px] leading-relaxed text-text-primary whitespace-pre-wrap">
                {m.text}
              </p>
              {m.role === "assistant" && (
                <>
                  <GroundingWarning g={m.response.grounding} />
                  <SourceList sources={m.response.sources} />
                </>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <p className="font-mono text-[12px] text-text-muted" role="status">
            Looking at the data…
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="mt-6 flex gap-2 items-end"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <div className="flex-1">
          <label htmlFor="assistant-input" className="sr-only">
            Your question
          </label>
          <textarea
            id="assistant-input"
            value={input}
            maxLength={MAX_CHARS}
            rows={2}
            placeholder="Ask about the risk scores, a crisis, or how Meridian works"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(input);
              }
            }}
            className="w-full resize-none font-sans text-[13.5px] text-text-primary bg-surface border border-border px-3 py-2"
          />
          <div className="font-mono text-[10px] text-text-muted mt-0.5">
            {input.length}/{MAX_CHARS} · Enter to send, Shift+Enter for a new line
          </div>
        </div>
        <button
          type="submit"
          disabled={loading || input.trim() === ""}
          className="font-sans text-[13px] font-medium px-4 py-2 border border-text-primary text-text-primary hover:bg-fill disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Ask
        </button>
      </form>
    </section>
  );
}
