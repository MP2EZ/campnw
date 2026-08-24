import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getTrip, updateTrip, deleteTrip, removeCampgroundFromTrip } from "../api";
import type { TripData, TripCampground } from "../api";
import { useAuth } from "../hooks/useAuth";
import { SOURCE_LABELS } from "../components/ResultCard";
import { ShareButton } from "../components/ShareButton";

export default function TripDetail() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [trip, setTrip] = useState<TripData | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  // Both destructive actions here were irreversible, unconfirmed and
  // un-caught: a failed request left the UI showing the row already gone.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!tripId || !user) return;
    getTrip(Number(tripId))
      .then(setTrip)
      .catch(() => setTrip(null))
      .finally(() => setLoading(false));
  }, [tripId, user]);

  const handleSaveName = async () => {
    if (!trip || !editName.trim()) return;
    const updated = await updateTrip(trip.id, { name: editName.trim() });
    setTrip(updated);
    setEditing(false);
  };

  const handleDelete = async () => {
    if (!trip) return;
    setConfirmingDelete(false);
    setActionError(null);
    try {
      await deleteTrip(trip.id);
    } catch {
      setActionError("Couldn't delete that trip. Please try again.");
      return;
    }
    navigate("/trips");
  };

  const handleRemoveCampground = async (cg: TripCampground) => {
    if (!trip) return;
    setActionError(null);
    try {
      await removeCampgroundFromTrip(trip.id, cg.facility_id, cg.source);
    } catch {
      setActionError(`Couldn't remove ${cg.name || "that campground"}. Please try again.`);
      return;
    }
    setTrip({
      ...trip,
      campgrounds: (trip.campgrounds || []).filter(
        (c) => !(c.facility_id === cg.facility_id && c.source === cg.source),
      ),
    });
  };

  if (!user) {
    return (
      <div className="trip-detail">
        <p>Sign in to view trips.</p>
      </div>
    );
  }

  if (loading) {
    return <div className="trip-detail"><p>Loading...</p></div>;
  }

  if (!trip) {
    return (
      <div className="trip-detail">
        <p>Trip not found.</p>
        <Link to="/trips">Back to trips</Link>
      </div>
    );
  }

  const campgrounds = trip.campgrounds || [];

  return (
    <div className="trip-detail">
      <Link to="/trips" className="trip-back-link">&larr; All trips</Link>

      {actionError && (
        <div className="error-banner" role="alert">{actionError}</div>
      )}

      <div className="trip-detail-header">
        {editing ? (
          <div className="trip-edit-name">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSaveName()}
              maxLength={200}
              className="trip-name-input"
              aria-label="Trip name"
              autoFocus
            />
            <button onClick={handleSaveName} className="btn-primary">Save</button>
            <button onClick={() => setEditing(false)} className="btn-secondary">Cancel</button>
          </div>
        ) : (
          <>
            <h2 className="trip-detail-title">{trip.name}</h2>
            <button
              className="trip-edit-btn"
              onClick={() => { setEditName(trip.name); setEditing(true); }}
              title="Edit name"
            >
              Edit
            </button>
            <ShareButton tripId={trip.id} />
            {confirmingDelete ? (
              <span className="trip-delete-confirm">
                <button
                  className="trip-delete-btn danger"
                  onClick={handleDelete}
                  aria-label="Confirm delete trip"
                >
                  Delete
                </button>
                <button
                  className="trip-delete-btn"
                  onClick={() => setConfirmingDelete(false)}
                  aria-label="Cancel delete"
                >
                  Cancel
                </button>
              </span>
            ) : (
            <button
              className="trip-delete-btn"
              onClick={() => setConfirmingDelete(true)}
              title="Delete trip"
            >
              Delete trip
            </button>
            )}
          </>
        )}
      </div>

      {trip.notes && <p className="trip-notes">{trip.notes}</p>}

      <h3>Campgrounds ({campgrounds.length})</h3>
      {campgrounds.length === 0 ? (
        <p className="trips-empty">
          No campgrounds yet. Add some from search results.
        </p>
      ) : (
        <ul className="trip-campground-list">
          {campgrounds.map((cg) => (
            <li key={`${cg.facility_id}-${cg.source}`} className="trip-campground-item">
              <div className="trip-campground-info">
                <span className="trip-campground-name">{cg.name || cg.facility_id}</span>
                <span className={`source-badge source-${cg.source}`}>
                  {SOURCE_LABELS[cg.source] || cg.source}
                </span>
              </div>
              <button
                className="trip-remove-btn"
                onClick={() => handleRemoveCampground(cg)}
                title={`Remove ${cg.name || cg.facility_id}`}
                aria-label={`Remove ${cg.name || cg.facility_id} from trip`}
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
