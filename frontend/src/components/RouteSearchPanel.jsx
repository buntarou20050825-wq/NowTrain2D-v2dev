// frontend/src/components/RouteSearchPanel.jsx
import { useState, useEffect, useRef, useCallback } from "react";
import { searchStations, searchRoute } from "../api/serverData";
import "./RouteSearchPanel.css";

/**
 * 経路検索パネルコンポーネント
 */
export default function RouteSearchPanel({ onClose, onRouteSelect }) {
  // 入力状態
  const [fromInput, setFromInput] = useState("");
  const [toInput, setToInput] = useState("");
  const [selectedFrom, setSelectedFrom] = useState(null);
  const [selectedTo, setSelectedTo] = useState(null);
  const [date, setDate] = useState(() => {
    const now = new Date();
    return now.toISOString().split("T")[0];
  });
  const [time, setTime] = useState(() => {
    const now = new Date();
    return now.toTimeString().slice(0, 5);
  });
  const [arriveBy, setArriveBy] = useState(false);

  // オートコンプリート状態
  const [fromSuggestions, setFromSuggestions] = useState([]);
  const [toSuggestions, setToSuggestions] = useState([]);
  const [showFromSuggestions, setShowFromSuggestions] = useState(false);
  const [showToSuggestions, setShowToSuggestions] = useState(false);

  // 検索結果状態
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState(null);
  const [selectedItineraryIndex, setSelectedItineraryIndex] = useState(null);

  // デバウンス用ref
  const fromDebounceRef = useRef(null);
  const toDebounceRef = useRef(null);

  // 駅名検索（デバウンス付き）
  const searchStationsDebounced = useCallback((query, setSuggestions, setShow) => {
    if (query.length < 1) {
      setSuggestions([]);
      setShow(false);
      return;
    }
    searchStations(query, 8).then((data) => {
      setSuggestions(data.stations || []);
      setShow(true);
    });
  }, []);

  // 出発駅入力変更
  const handleFromInputChange = (e) => {
    const value = e.target.value;
    setFromInput(value);
    setSelectedFrom(null);

    if (fromDebounceRef.current) clearTimeout(fromDebounceRef.current);
    fromDebounceRef.current = setTimeout(() => {
      searchStationsDebounced(value, setFromSuggestions, setShowFromSuggestions);
    }, 300);
  };

  // 到着駅入力変更
  const handleToInputChange = (e) => {
    const value = e.target.value;
    setToInput(value);
    setSelectedTo(null);

    if (toDebounceRef.current) clearTimeout(toDebounceRef.current);
    toDebounceRef.current = setTimeout(() => {
      searchStationsDebounced(value, setToSuggestions, setShowToSuggestions);
    }, 300);
  };

  // 駅選択
  const handleSelectFrom = (station) => {
    setFromInput(station.name_ja);
    setSelectedFrom(station);
    setShowFromSuggestions(false);
  };

  const handleSelectTo = (station) => {
    setToInput(station.name_ja);
    setSelectedTo(station);
    setShowToSuggestions(false);
  };

  // 経路検索実行
  const handleSearch = async () => {
    const fromStation = selectedFrom?.name_ja || fromInput;
    const toStation = selectedTo?.name_ja || toInput;

    if (!fromStation || !toStation) {
      setError("出発駅と到着駅を入力してください");
      return;
    }

    setLoading(true);
    setError("");
    setResults(null);

    const result = await searchRoute({
      fromStation,
      toStation,
      date,
      time,
      arriveBy,
    });

    setLoading(false);

    if (result.status === "error") {
      // result.error がオブジェクトの場合は message を取得
      const errorMsg = typeof result.error === "object"
        ? result.error?.message || JSON.stringify(result.error)
        : result.error || "経路検索に失敗しました";
      setError(errorMsg);
    } else if (result.itineraries?.length === 0) {
      setError("経路が見つかりませんでした");
    } else {
      setResults(result);
    }
  };

  // 時刻フォーマット
  const formatTime = (isoString) => {
    if (!isoString) return "";
    const date = new Date(isoString);
    return date.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
  };

  // 所要時間フォーマット
  const formatDuration = (minutes) => {
    if (minutes < 60) return `${minutes}分`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}時間${m}分` : `${h}時間`;
  };

  return (
    <div className="route-search-panel">
      <div className="route-search-header">
        <span className="route-search-title">経路検索</span>
        {onClose && (
          <button className="route-search-close" onClick={onClose}>
            ×
          </button>
        )}
      </div>

      <div className="route-search-form">
        {/* 出発駅 */}
        <div className="route-search-field">
          <label>出発駅</label>
          <div className="autocomplete-wrapper">
            <input
              type="text"
              value={fromInput}
              onChange={handleFromInputChange}
              onFocus={() => fromSuggestions.length > 0 && setShowFromSuggestions(true)}
              onBlur={() => setTimeout(() => setShowFromSuggestions(false), 200)}
              placeholder="駅名を入力..."
            />
            {showFromSuggestions && fromSuggestions.length > 0 && (
              <ul className="autocomplete-suggestions">
                {fromSuggestions.map((station) => (
                  <li key={station.id} onMouseDown={() => handleSelectFrom(station)}>
                    <span className="station-name">{station.name_ja}</span>
                    <span className="station-lines">
                      {station.lines?.slice(0, 2).join(", ")}
                      {station.lines?.length > 2 && "..."}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* 到着駅 */}
        <div className="route-search-field">
          <label>到着駅</label>
          <div className="autocomplete-wrapper">
            <input
              type="text"
              value={toInput}
              onChange={handleToInputChange}
              onFocus={() => toSuggestions.length > 0 && setShowToSuggestions(true)}
              onBlur={() => setTimeout(() => setShowToSuggestions(false), 200)}
              placeholder="駅名を入力..."
            />
            {showToSuggestions && toSuggestions.length > 0 && (
              <ul className="autocomplete-suggestions">
                {toSuggestions.map((station) => (
                  <li key={station.id} onMouseDown={() => handleSelectTo(station)}>
                    <span className="station-name">{station.name_ja}</span>
                    <span className="station-lines">
                      {station.lines?.slice(0, 2).join(", ")}
                      {station.lines?.length > 2 && "..."}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* 日時 */}
        <div className="route-search-datetime">
          <div className="route-search-field">
            <label>日付</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="route-search-field">
            <label>時刻</label>
            <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
        </div>

        {/* 到着時刻指定 */}
        <div className="route-search-checkbox">
          <label>
            <input
              type="checkbox"
              checked={arriveBy}
              onChange={(e) => setArriveBy(e.target.checked)}
            />
            到着時刻で検索
          </label>
        </div>

        {/* 検索ボタン */}
        <button className="route-search-button" onClick={handleSearch} disabled={loading}>
          {loading ? "検索中..." : "検索"}
        </button>

        {/* エラー表示 */}
        {error && <div className="route-search-error">{error}</div>}
      </div>

      {/* 検索結果 */}
      {results && results.itineraries && (
        <div className="route-search-results">
          <div className="results-header">検索結果 ({results.itineraries.length}件) - クリックで地図に表示</div>
          {results.itineraries.map((itinerary, idx) => (
            <div
              key={idx}
              className={`itinerary-card ${selectedItineraryIndex === idx ? "selected" : ""}`}
              onClick={() => {
                setSelectedItineraryIndex(idx);
                if (onRouteSelect) {
                  onRouteSelect(itinerary);
                }
              }}
              style={{ cursor: "pointer" }}
            >
              <div className="itinerary-summary">
                <span className="itinerary-time">
                  {formatTime(itinerary.start_time)} → {formatTime(itinerary.end_time)}
                </span>
                <span className="itinerary-duration">
                  ({formatDuration(itinerary.duration_minutes)})
                </span>
              </div>
              <div className="itinerary-legs">
                {itinerary.legs
                  .filter((leg) => leg.mode !== "WALK" || leg.duration_minutes > 2)
                  .map((leg, legIdx) => (
                    <div key={legIdx} className={`leg-item leg-${leg.mode.toLowerCase()}`}>
                      {leg.mode === "WALK" ? (
                        <span className="leg-walk">徒歩 {leg.duration_minutes}分</span>
                      ) : (
                        <>
                          <span className="leg-stations">
                            {leg.from?.name} → {leg.to?.name}
                          </span>
                          <span className="leg-route">
                            {leg.route?.long_name || leg.route?.short_name || ""}
                          </span>
                          <span className="leg-times">
                            {formatTime(leg.start_time)} - {formatTime(leg.end_time)}
                          </span>
                          {leg.current_position && (
                            <span
                              className={`leg-status leg-status-${leg.current_position.status}`}
                            >
                              {leg.current_position.status === "running"
                                ? "運行中"
                                : leg.current_position.status === "stopped"
                                ? "停車中"
                                : ""}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
