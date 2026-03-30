import { useEffect, useState } from "react";
import { getTrips, createTrip, addCampgroundToTrip, track } from "../api";
import type { TripData } from "../api";
import { useAuth } from "../hooks/useAuth";

interface SaveToTripButtonProps {
  facilityId: string;
  source: string;
  name: string;
}

export function SaveToTripButton({ facilityId, source, name }: SaveToTripButtonProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [trips, setTrips] = useState<TripData[]>([]);
  const [saved, setSaved] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    if (open && user) {
      getTrips().then(setTrips);
    }
  }, [open, user]);

  if (!user) return null;

  const handleSave = async (tripId: number, tripName: string) => {
    try {
      await addCampgroundToTrip(tripId, facilityId, source, name);
      track("save_to_trip", { facility_id: facilityId });
      setSaved(tripName);
      setTimeout(() => { setSaved(null); setOpen(false); }, 1500);
    } catch {
      // Likely duplicate — already in trip
      setSaved("Already added");
      setTimeout(() => setSaved(null), 1500);
    }
  };

  const handleCreateAndSave = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    const trip = await createTrip(newName.trim());
    await addCampgroundToTrip(trip.id, facilityId, source, name);
    setSaved(newName.trim());
    setNewName("");
    setCreating(false);
    setTimeout(() => { setSaved(null); setOpen(false); }, 1500);
  };

  if (saved) {
    return <span className="save-to-trip-saved">Saved to {saved}</span>;
  }

  return (
    <span className="save-to-trip-wrapper">
      <button
        className="save-to-trip-btn"
        onClick={() => setOpen(!open)}
        type="button"
        title="Save to trip"
        aria-expanded={open}
        aria-haspopup="true"
      >
        + Trip
      </button>
      {open && (
        <div className="save-to-trip-dropdown" role="menu">
          {trips.length > 0 && (
            <ul className="save-to-trip-list">
              {trips.map((t) => (
                <li key={t.id}>
                  <button onClick={() => handleSave(t.id, t.name)}>{t.name}</button>
                </li>
              ))}
            </ul>
          )}
          <div className="save-to-trip-create">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="New trip..."
              maxLength={200}
              onKeyDown={(e) => e.key === "Enter" && handleCreateAndSave()}
            />
            <button
              onClick={handleCreateAndSave}
              disabled={creating || !newName.trim()}
            >
              Create
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
