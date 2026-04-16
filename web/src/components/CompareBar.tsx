import { renderMarkdown } from "../renderMarkdown";
import type { CompareResponse } from "../api";

// ---------------------------------------------------------------------------
// ComparePanel — inline results (replaces search summary banner)
// ---------------------------------------------------------------------------

interface ComparePanelProps {
  result: CompareResponse;
  onClose: () => void;
}

export function ComparePanel({ result, onClose }: ComparePanelProps) {
  return (
    <div className="compare-panel">
      <div className="compare-panel-header">
        <h3>Comparison</h3>
        <button
          className="compare-close"
          onClick={onClose}
          aria-label="Close comparison"
        >
          &times;
        </button>
      </div>
      <div className="compare-table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              <th />
              {result.campgrounds.map((cg) => (
                <th key={cg.facility_id}>{cg.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="compare-label">State</td>
              {result.campgrounds.map((cg) => (
                <td key={cg.facility_id}>{cg.state}</td>
              ))}
            </tr>
            <tr>
              <td className="compare-label">Drive</td>
              {result.campgrounds.map((cg) => (
                <td key={cg.facility_id}>
                  {cg.drive_minutes != null
                    ? cg.drive_minutes < 60
                      ? `${cg.drive_minutes}m`
                      : `${Math.floor(cg.drive_minutes / 60)}h ${cg.drive_minutes % 60}m`
                    : "—"}
                </td>
              ))}
            </tr>
            <tr>
              <td className="compare-label">Sites</td>
              {result.campgrounds.map((cg) => (
                <td key={cg.facility_id}>{cg.total_sites ?? "—"}</td>
              ))}
            </tr>
            <tr>
              <td className="compare-label">Tags</td>
              {result.campgrounds.map((cg) => (
                <td key={cg.facility_id}>{cg.tags.slice(0, 4).join(", ")}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {result.narrative && (
        <div className="compare-narrative">
          <p>{renderMarkdown(result.narrative)}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompareBar — sticky selection bar at bottom
// ---------------------------------------------------------------------------

interface CompareBarProps {
  selectedIds: Set<string>;
  onClear: () => void;
  onCompare: () => void;
  loading: boolean;
}

export function CompareBar({ selectedIds, onClear, onCompare, loading }: CompareBarProps) {
  if (selectedIds.size === 0) return null;

  return (
    <div className="compare-bar">
      <span className="compare-bar-count">
        {selectedIds.size} selected
      </span>
      <button
        className="btn-primary"
        onClick={onCompare}
        disabled={selectedIds.size < 2 || loading}
      >
        {loading ? "Comparing..." : `Compare (${selectedIds.size})`}
      </button>
      <button className="btn-secondary" onClick={onClear}>
        Clear
      </button>
    </div>
  );
}
