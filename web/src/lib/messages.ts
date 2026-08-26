import type { ToolCall } from "../api";

/** A message as rendered in the planner transcript. */
export interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCall[];
  isError?: boolean;
}

/**
 * Patch the trailing assistant message.
 *
 * The streaming handler updates that message five separate ways — text,
 * tool calls, tool results, errors, completion — and each site had its own
 * copy of the spread-find-replace dance.
 */
export function patchLastAssistant(
  prev: DisplayMessage[],
  patch: Partial<DisplayMessage>,
): DisplayMessage[] {
  const last = prev[prev.length - 1];
  if (!last || last.role !== "assistant") return prev;
  const updated = [...prev];
  updated[updated.length - 1] = { ...last, ...patch };
  return updated;
}

