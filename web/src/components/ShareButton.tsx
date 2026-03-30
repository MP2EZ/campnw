import { useState } from "react";
import { createShareLink } from "../api";

interface ShareButtonProps {
  watchId?: number;
  tripId?: number;
}

export function ShareButton({ watchId, tripId }: ShareButtonProps) {
  const [status, setStatus] = useState<"idle" | "copying" | "copied">("idle");

  const handleShare = async () => {
    setStatus("copying");
    try {
      const { uuid } = await createShareLink({
        watch_id: watchId,
        trip_id: tripId,
      });
      const url = `${window.location.origin}/shared/${uuid}`;
      await navigator.clipboard.writeText(url);
      setStatus("copied");
      setTimeout(() => setStatus("idle"), 4000);
    } catch {
      setStatus("idle");
    }
  };

  if (status === "copied") {
    return <span className="share-copied">Link copied</span>;
  }

  return (
    <button
      className="share-btn"
      onClick={handleShare}
      disabled={status === "copying"}
      title="Copy share link"
    >
      Share
    </button>
  );
}
