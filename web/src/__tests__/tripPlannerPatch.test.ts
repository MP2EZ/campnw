import { describe, test, expect } from "vitest";
import { patchLastAssistant } from "../lib/messages";

/**
 * The streaming handler patched the trailing assistant message five separate
 * ways, each with its own copy of the spread-find-replace dance. TripPlanner
 * itself has no test coverage, so consolidating them into one helper needed
 * the helper pinned — a green suite proved nothing about that path.
 */

type Msg = Parameters<typeof patchLastAssistant>[0][number];

const user: Msg = { role: "user", content: "hi" } as Msg;
const assistant: Msg = { role: "assistant", content: "" } as Msg;

describe("patchLastAssistant", () => {
  test("patches the trailing assistant message", () => {
    const out = patchLastAssistant([user, assistant], { content: "hello" });
    expect(out[1].content).toBe("hello");
  });

  test("leaves earlier messages untouched", () => {
    const out = patchLastAssistant([user, assistant], { content: "hello" });
    expect(out[0]).toBe(user);
  });

  test("does not mutate the input array", () => {
    const input = [user, assistant];
    const out = patchLastAssistant(input, { content: "hello" });
    expect(out).not.toBe(input);
    expect(assistant.content).toBe("");
  });

  test("merges rather than replaces, so successive patches accumulate", () => {
    // The streaming path patches content, then tool_calls, then completion —
    // each must preserve what the previous one wrote.
    let msgs = patchLastAssistant([user, assistant], { content: "partial" });
    msgs = patchLastAssistant(msgs, { tool_calls: [{ name: "search", input: {} }] } as Partial<Msg>);
    expect(msgs[1].content).toBe("partial");
    expect((msgs[1] as { tool_calls?: unknown[] }).tool_calls).toHaveLength(1);
  });

  test("is a no-op when the last message is not an assistant", () => {
    const input = [assistant, user];
    expect(patchLastAssistant(input, { content: "x" })).toBe(input);
  });

  test("is a no-op on an empty transcript", () => {
    const input: Msg[] = [];
    expect(patchLastAssistant(input, { content: "x" })).toBe(input);
  });
});
