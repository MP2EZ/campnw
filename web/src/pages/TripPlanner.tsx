import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { planChat } from "../api";
import type { ChatMessage, ToolCall } from "../api";

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
          <Markdown
            components={{
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noopener">
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </Markdown>
        )}
      </div>
    </div>
  );
}

export default function TripPlanner() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [apiMessages, setApiMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    setError(null);

    try {
      const response = await planChat(nextApiMessages);
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: response.content,
      };
      setApiMessages((prev) => [...prev, assistantMessage]);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.content,
          tool_calls: response.tool_calls,
        },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: message,
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
      // Return focus to input after response
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="trip-planner">
      {isEmpty && (
        <div className="chat-welcome">
          <h2>Plan a camping trip</h2>
          <p>Describe where and when you want to go — I'll search for available campsites and put together a trip plan.</p>
          <div className="chat-examples">
            <p className="chat-examples-label">Try asking:</p>
            <ul>
              <li>"Find me a lakeside campsite in WA this weekend"</li>
              <li>"I want 2 nights near Rainier in July, what's available?"</li>
              <li>"Family camping within 2 hours of Seattle, long weekend in August"</li>
            </ul>
          </div>
        </div>
      )}

      <div
        className="chat-messages"
        role="log"
        aria-label="Trip planner conversation"
        aria-live="polite"
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
    </div>
  );
}
