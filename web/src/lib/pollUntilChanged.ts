interface PollOptions<T> {
  /** The value already on screen; polling stops at the first that differs. */
  initial: T;
  fetchOnce: () => Promise<T>;
  /** One read per entry, each after waiting that long. */
  delaysMs: readonly number[];
  onValue: (value: T) => void;
  key?: (value: T) => unknown;
  sleep?: (ms: number) => Promise<void>;
}

const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Re-read a value on a fixed schedule until it changes or the schedule runs
 * out. Returns the last value seen. Failed reads are skipped.
 */
export async function pollUntilChanged<T>({
  initial,
  fetchOnce,
  delaysMs,
  onValue,
  key = (v) => v,
  sleep = wait,
}: PollOptions<T>): Promise<T> {
  const before = key(initial);
  let last = initial;
  for (const ms of delaysMs) {
    await sleep(ms);
    let value: T;
    try {
      value = await fetchOnce();
    } catch {
      continue;
    }
    last = value;
    onValue(value);
    if (key(value) !== before) return value;
  }
  return last;
}
