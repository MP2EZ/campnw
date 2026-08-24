import { useEffect, useState } from "react";
import { Helmet } from "react-helmet-async";
import { Link } from "react-router-dom";
import { getTrips, createTrip, deleteTrip, track } from "../api";
import type { TripData } from "../api";
import { useAuth } from "../hooks/useAuth";

function formatDate(iso: string): string {
  if (!iso) return "";
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function TripsPage() {
  const { user } = useAuth();
  const [trips, setTrips] = useState<TripData[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  // Deleting a trip is irreversible and the button sits ~22px tall directly
  // beside the full-row link, so a mis-tap destroyed data with no undo.
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    getTrips().then(setTrips).finally(() => setLoading(false));
  }, [user]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    const trip = await createTrip(newName.trim());
    setTrips((prev) => [trip, ...prev]);
    track("trip_created", {});
    setNewName("");
    setCreating(false);
  };

  const handleDelete = async (tripId: number) => {
    setConfirmingDelete(null);
    setDeleteError(null);
    try {
      await deleteTrip(tripId);
    } catch {
      // Previously the row was removed optimistically with no catch, so a
      // failed delete left the user believing it had succeeded.
      setDeleteError("Couldn't delete that trip. Please try again.");
      return;
    }
    setTrips((prev) => prev.filter((t) => t.id !== tripId));
    track("trip_deleted", { trip_id: tripId });
  };

  if (!user) {
    return (
      <div className="trips-page">
        <h2>My Trips</h2>
        <p className="trips-empty">Sign in to save and manage trips.</p>
      </div>
    );
  }

  return (
    <div className="trips-page">
      <Helmet>
        <title>My Trips — Campable</title>
        <meta name="description" content="Manage your camping trips and itineraries." />
      </Helmet>
      <h2>My Trips</h2>
      {deleteError && (
        <div className="error-banner" role="alert">{deleteError}</div>
      )}

      <div className="trip-create-row">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New trip name..."
          aria-label="New trip name"
          maxLength={200}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          className="trip-name-input"
        />
        <button
          onClick={handleCreate}
          disabled={creating || !newName.trim()}
          className="btn-primary"
        >
          Create
        </button>
      </div>

      {loading ? (
        <p className="trips-loading">Loading trips...</p>
      ) : trips.length === 0 ? (
        <p className="trips-empty">
          No trips yet. Create one above, or save campgrounds from search results.
        </p>
      ) : (
        <ul className="trip-list">
          {trips.map((trip) => (
            <li key={trip.id} className="trip-list-item">
              <Link to={`/trips/${trip.id}`} className="trip-link">
                <span className="trip-name">{trip.name}</span>
                <span className="trip-meta">
                  {trip.campground_count ?? 0} campground{(trip.campground_count ?? 0) !== 1 ? "s" : ""}
                  {trip.start_date && (
                    <> &middot; {formatDate(trip.start_date)}</>
                  )}
                  {trip.end_date && trip.start_date && (
                    <> &ndash; {formatDate(trip.end_date)}</>
                  )}
                </span>
              </Link>
              {confirmingDelete === trip.id ? (
                <span className="trip-delete-confirm">
                  <button
                    className="trip-delete-btn danger"
                    onClick={(e) => { e.preventDefault(); handleDelete(trip.id); }}
                    aria-label={`Confirm delete ${trip.name}`}
                  >
                    Delete
                  </button>
                  <button
                    className="trip-delete-btn"
                    onClick={(e) => { e.preventDefault(); setConfirmingDelete(null); }}
                    aria-label="Cancel delete"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
              <button
                className="trip-delete-btn"
                onClick={(e) => {
                  e.preventDefault();
                  setConfirmingDelete(trip.id);
                }}
                title="Delete trip"
                aria-label={`Delete ${trip.name}`}
              >
                &times;
              </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
