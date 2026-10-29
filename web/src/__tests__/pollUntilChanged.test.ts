import { describe, test, expect, vi } from "vitest";
import { pollUntilChanged } from "../lib/pollUntilChanged";

/**
 * After a Stripe Customer Portal return the webhook usually hasn't landed
 * yet, so the first status read is stale. These pin the stop conditions of
 * the bounded re-read that covers that gap.
 */

const noSleep = () => Promise.resolve();

describe("pollUntilChanged", () => {
  test("stops at the first value that differs from the initial one", async () => {
    const fetchOnce = vi
      .fn()
      .mockResolvedValueOnce("pro")
      .mockResolvedValueOnce("pro_until_nov")
      .mockResolvedValueOnce("never_read");
    const onValue = vi.fn();

    const result = await pollUntilChanged({
      initial: "pro",
      fetchOnce,
      delaysMs: [1, 1, 1, 1],
      onValue,
      sleep: noSleep,
    });

    expect(result).toBe("pro_until_nov");
    expect(fetchOnce).toHaveBeenCalledTimes(2);
    expect(onValue).toHaveBeenLastCalledWith("pro_until_nov");
  });

  test("gives up after the schedule when nothing changes", async () => {
    const fetchOnce = vi.fn().mockResolvedValue("pro");
    const result = await pollUntilChanged({
      initial: "pro",
      fetchOnce,
      delaysMs: [1, 1, 1],
      onValue: vi.fn(),
      sleep: noSleep,
    });
    expect(result).toBe("pro");
    expect(fetchOnce).toHaveBeenCalledTimes(3);
  });

  test("waits each delay before its read", async () => {
    const sleep = vi.fn().mockResolvedValue(undefined);
    await pollUntilChanged({
      initial: "a",
      fetchOnce: vi.fn().mockResolvedValue("a"),
      delaysMs: [2000, 4000],
      onValue: vi.fn(),
      sleep,
    });
    expect(sleep.mock.calls.map((c) => c[0])).toEqual([2000, 4000]);
  });

  test("compares by key, not identity", async () => {
    // Every fetch returns a fresh object; identity would never match.
    const fetchOnce = vi.fn().mockImplementation(async () => ({ s: "pro" }));
    await pollUntilChanged({
      initial: { s: "pro" },
      fetchOnce,
      key: (v) => v.s,
      delaysMs: [1, 1],
      onValue: vi.fn(),
      sleep: noSleep,
    });
    expect(fetchOnce).toHaveBeenCalledTimes(2);
  });

  test("a failed read is skipped, not fatal", async () => {
    const fetchOnce = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce("changed");
    const result = await pollUntilChanged({
      initial: "pro",
      fetchOnce,
      delaysMs: [1, 1],
      onValue: vi.fn(),
      sleep: noSleep,
    });
    expect(result).toBe("changed");
  });
});
