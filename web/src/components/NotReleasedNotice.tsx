import { memo } from "react";
import type { NotReleasedSummary } from "../api";
import { notReleasedMessage } from "../lib/notReleased";

export const NotReleasedNotice = memo(function NotReleasedNotice({
  summary,
}: {
  summary: Partial<NotReleasedSummary>;
}) {
  const message = notReleasedMessage(summary);
  if (!message) return null;
  return <p className="not-released-notice">{message}</p>;
});
