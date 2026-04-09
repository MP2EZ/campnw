import { useEffect, useRef, useState } from "react";
import { Helmet } from "react-helmet-async";
import Markdown from "react-markdown";
import { planChatStream, track } from "../api";
import type { ChatMessage, ToolCall } from "../api";
import { ItineraryCard, parseItinerary } from "../components/ItineraryCard";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCall[];
  isError?: boolean;
}

function ToolCallBadge({ call }: { call: ToolCall }) {
  const labels: Record<string, string> = {
    search_campsites: "Searching campsites",
    check_campground: "Checking campground",
    get_drive_time: "Calculating drive time",
    list_campgrounds: "Listing campgrounds",
  };
  const label = labels[call.name] ?? call.name;
  return (
    <div className="tool-call-badge" aria-label={`Tool used: ${label}`}>
      <span className="tool-call-name">{label}</span>
      {call.result_summary && (
        <span className="tool-call-result">{call.result_summary}</span>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`chat-message ${isUser ? "user" : "assistant"}${message.isError ? " error" : ""}`}>
      {!isUser && message.tool_calls && message.tool_calls.length > 0 && (
        <div className="tool-calls">
          {message.tool_calls.map((call, i) => (
            <ToolCallBadge key={i} call={call} />
          ))}
        </div>
      )}
      <div className="chat-message-content">
        {isUser ? (
          message.content
        ) : (
          <>
            <Markdown
              components={{
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noopener">
                    {children}
                  </a>
                ),
              }}
            >
              {message.content.replace(/```itinerary\s*\n[\s\S]*?```/g, "").trim()}
            </Markdown>
            {(() => {
              const legs = parseItinerary(message.content);
              if (!legs) return null;
              return (
                <div className="itinerary-cards">
                  {legs.map((leg, i) => <ItineraryCard key={leg.facility_id} leg={leg} index={i} />)}
                </div>
              );
            })()}
          </>
        )}
      </div>
    </div>
  );
}

const EXAMPLE_PROMPTS = [
  "Lakeside campsite in WA this weekend",
  "2 nights near Rainier in July",
  "Family camping within 2 hours of Seattle, August long weekend",
];

function loadSaved<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export default function TripPlanner() {
  const [messages, setMessages] = useState<DisplayMessage[]>(
    () => loadSaved("campable-plan-messages", []),
  );
  const [apiMessages, setApiMessages] = useState<ChatMessage[]>(
    () => loadSaved("campable-plan-api-messages", []),
  );
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Persist conversation to localStorage
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem("campable-plan-messages", JSON.stringify(messages));
      localStorage.setItem("campable-plan-api-messages", JSON.stringify(apiMessages));
    }
  }, [messages, apiMessages]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    const el = transcriptRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const userMessage: ChatMessage = { role: "user", content: text };
    const nextApiMessages = [...apiMessages, userMessage];

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
    ]);
    setApiMessages(nextApiMessages);
    setInput("");
    setLoading(true);
    track("plan_message_sent", { message_count: nextApiMessages.length });
    setError(null);

    // Add a placeholder assistant message that updates as text streams in
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", tool_calls: [] },
    ]);

    const toolCalls: ToolCall[] = [];
    let fullText = "";
    let rafId = 0;
    let pendingFlush = false;

    const flushText = () => {
      rafId = 0;
      pendingFlush = false;
      const text = fullText;
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = { ...last, content: text };
        }
        return updated;
      });
    };

    await planChatStream(
      nextApiMessages,
      (chunk) => {
        fullText += chunk;
        if (!pendingFlush) {
          pendingFlush = true;
          rafId = requestAnimationFrame(flushText);
        }
      },
      (name) => {
        toolCalls.push({ name, input: {} });
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              tool_calls: [...toolCalls],
            };
          }
          return updated;
        });
      },
      (name, summary) => {
        const tc = toolCalls.find((t) => t.name === name && !t.result_summary);
        if (tc) tc.result_summary = summary;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              tool_calls: [...toolCalls],
            };
          }
          return updated;
        });
      },
      (finalContent, finalToolCalls) => {
        if (rafId) cancelAnimationFrame(rafId);
        const content = finalContent || fullText;
        setApiMessages((prev) => [
          ...prev,
          { role: "assistant", content },
        ]);
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content,
              tool_calls: finalToolCalls.length > 0 ? finalToolCalls : toolCalls,
            };
          }
          return updated;
        });
        setLoading(false);
        inputRef.current?.focus();
      },
      (err) => {
        if (rafId) cancelAnimationFrame(rafId);
        const message = err.message || "Something went wrong";
        setError(message);
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: message,
              isError: true,
            };
          }
          return updated;
        });
        setLoading(false);
        inputRef.current?.focus();
      },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const isEmpty = messages.length === 0;

  const handleNewConversation = () => {
    setMessages([]);
    setApiMessages([]);
    localStorage.removeItem("campable-plan-messages");
    localStorage.removeItem("campable-plan-api-messages");
  };

  return (
    <main id="main-content" className="trip-planner">
      <Helmet>
        <title>Trip Planner — Campable</title>
        <meta name="description" content="AI-powered camping trip planner. Get personalized campground recommendations and itineraries." />
      </Helmet>
      {!isEmpty && (
        <button
          className="chat-new-btn"
          onClick={handleNewConversation}
          disabled={loading}
        >
          New conversation
        </button>
      )}
      {isEmpty && (
        <div className="chat-welcome">
          <h2>Plan a camping trip</h2>
          <p>Describe where and when you want to go — I'll search for available campsites and put together a trip plan.</p>
          <div className="chat-examples">
            <p className="chat-examples-label">Try asking:</p>
            <div className="chat-examples-list">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  className="chat-example-btn"
                  onClick={() => {
                    setInput(prompt);
                    inputRef.current?.focus();
                  }}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div
        className="chat-messages"
        role="log"
        aria-label="Trip planner conversation"
        ref={transcriptRef}
      >
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {loading && (
          <div className="chat-message assistant chat-thinking" aria-label="Assistant is thinking">
            <div className="thinking-dots">
              <span /><span /><span />
            </div>
            <span className="thinking-label">Thinking...</span>
          </div>
        )}
      </div>

      {error && !loading && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <form className="chat-input-form" onSubmit={handleSubmit} aria-label="Send a message">
        <label htmlFor="chat-input" className="visually-hidden">
          Message
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Where do you want to camp?"
          rows={2}
          disabled={loading}
          aria-disabled={loading}
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={loading || !input.trim()}
          aria-label="Send message"
        >
          Send
        </button>
      </form>
    </main>
  );
}
