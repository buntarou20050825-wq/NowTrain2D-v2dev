import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AVAILABLE_LINES } from "../constants/lines";
import "./AdminPanel.css";

const DEFAULT_RANK = "B";
const DEFAULT_DWELL = "20";
const RANK_OPTIONS = ["S", "A", "B"];

const formatTime = (dt) => {
  if (!dt) return "--:--";
  return dt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
};

function AdminPanel() {
  const [lineId, setLineId] = useState(AVAILABLE_LINES[0]?.id ?? "");
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [statusById, setStatusById] = useState({});
  const [lastLoadedAt, setLastLoadedAt] = useState(null);

  const selectedLine = useMemo(
    () => AVAILABLE_LINES.find((line) => line.id === lineId),
    [lineId]
  );

  const loadStations = async () => {
    if (!lineId) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/stations?lineId=${encodeURIComponent(lineId)}`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`HTTP_${res.status}`);
      }
      const data = await res.json();
      const nextStations = (data.stations || []).map((st) => ({
        id: st.id,
        name: st.name_ja || st.name_en || st.id,
        name_en: st.name_en || "",
        rank: st.rank || DEFAULT_RANK,
        dwell_time: Number.isFinite(st.dwell_time) ? String(st.dwell_time) : DEFAULT_DWELL,
      }));
      setStations(nextStations);
      setLastLoadedAt(new Date());
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStations();
  }, [lineId]);

  const updateStation = (stationId, patch) => {
    setStations((prev) =>
      prev.map((st) => (st.id === stationId ? { ...st, ...patch } : st))
    );
  };

  const saveStation = async (station) => {
    const dwellValue = Number.parseInt(station.dwell_time, 10);
    if (!Number.isFinite(dwellValue) || dwellValue < 0) {
      setStatusById((prev) => ({
        ...prev,
        [station.id]: { state: "error", message: "dwell_time must be >= 0" },
      }));
      return;
    }

    setStatusById((prev) => ({ ...prev, [station.id]: { state: "saving" } }));

    try {
      const res = await fetch(`/api/stations/${encodeURIComponent(station.id)}/rank`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rank: station.rank, dwell_time: dwellValue }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP_${res.status}`);
      }
      setStatusById((prev) => ({
        ...prev,
        [station.id]: { state: "saved", message: "Saved" },
      }));
    } catch (err) {
      setStatusById((prev) => ({
        ...prev,
        [station.id]: { state: "error", message: err?.message || "Update failed" },
      }));
    }
  };

  return (
    <div className="admin-page">
      <div className="admin-shell">
        <header className="admin-header">
          <div>
            <div className="admin-eyebrow">NowTrain Control Deck</div>
            <h1 className="admin-title">Station Rank Console</h1>
            <div className="admin-subtitle">
              Live rank and dwell time tuning for the selected line.
            </div>
          </div>
          <div className="admin-nav">
            <div className="admin-timestamp">
              Updated: {formatTime(lastLoadedAt)}
            </div>
            <Link className="admin-link" to="/">
              Back to Map
            </Link>
          </div>
        </header>

        <section className="admin-controls">
          <div className="control-block">
            <label className="control-label" htmlFor="line-select">
              Line
            </label>
            <select
              id="line-select"
              value={lineId}
              onChange={(e) => setLineId(e.target.value)}
              className="control-input"
            >
              {AVAILABLE_LINES.map((line) => (
                <option key={line.id} value={line.id}>
                  {line.name}
                </option>
              ))}
            </select>
          </div>
          <div className="control-meta">
            <div className="meta-title">Active line</div>
            <div className="meta-value">{selectedLine?.railwayId || "-"}</div>
          </div>
          <button className="control-button" type="button" onClick={loadStations}>
            Refresh
          </button>
        </section>

        <section className="station-panel">
          <div className="panel-header">
            <div className="panel-title">Stations</div>
            <div className="panel-meta">
              {loading ? "Loading..." : `${stations.length} stations`}
            </div>
          </div>

          {error && <div className="panel-error">Fetch failed: {error}</div>}

          <div className="station-grid station-grid--header">
            <div className="cell">Station</div>
            <div className="cell">Rank</div>
            <div className="cell">Dwell (s)</div>
            <div className="cell">Action</div>
            <div className="cell">Status</div>
          </div>

          {stations.map((station, idx) => {
            const status = statusById[station.id] || { state: "idle" };
            return (
              <div
                className="station-grid station-row"
                key={station.id}
                style={{ animationDelay: `${idx * 15}ms` }}
              >
                <div className="cell" data-label="Station">
                  <div className="station-name">{station.name}</div>
                  <div className="station-sub">{station.name_en}</div>
                </div>
                <div className="cell" data-label="Rank">
                  <select
                    className="control-input"
                    value={station.rank}
                    onChange={(e) => updateStation(station.id, { rank: e.target.value })}
                  >
                    {RANK_OPTIONS.map((rank) => (
                      <option key={rank} value={rank}>
                        {rank}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="cell" data-label="Dwell (s)">
                  <input
                    className="control-input"
                    type="number"
                    min="0"
                    step="5"
                    value={station.dwell_time}
                    onChange={(e) => updateStation(station.id, { dwell_time: e.target.value })}
                  />
                </div>
                <div className="cell" data-label="Action">
                  <button
                    className="save-button"
                    type="button"
                    onClick={() => saveStation(station)}
                    disabled={status.state === "saving"}
                  >
                    {status.state === "saving" ? "Saving..." : "Save"}
                  </button>
                </div>
                <div className={`cell status status--${status.state}`} data-label="Status">
                  {status.state === "saved" && "Saved"}
                  {status.state === "error" && status.message}
                  {status.state === "saving" && "Writing..."}
                </div>
              </div>
            );
          })}
        </section>
      </div>
    </div>
  );
}

export default AdminPanel;
