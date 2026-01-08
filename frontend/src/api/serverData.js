// frontend/src/api/serverData.js

// TODO (MS3 以降):
// - VITE_API_BASE など .env 経由で API ベースURLを指定する設計に移行する
// - ここではデフォルト値を "http://localhost:8000" とし、
//   環境変数があればそちらを優先する。
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function fetchLinesFromApi() {
  try {
    const res = await fetch(`${API_BASE}/api/lines?operator=JR-East`);
    if (!res.ok) {
      console.error("Failed to fetch lines from API", res.status);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.error("Error fetching lines from API", err);
    return null;
  }
}

/**
 * 駅名で駅を検索する（部分一致）
 * @param {string} query - 検索キーワード
 * @param {number} limit - 最大件数（デフォルト10）
 * @returns {Promise<{query: string, count: number, stations: Array}>}
 */
export async function searchStations(query, limit = 10) {
  try {
    const res = await fetch(
      `${API_BASE}/api/stations/search?q=${encodeURIComponent(query)}&limit=${limit}`
    );
    if (!res.ok) {
      console.error("Failed to search stations", res.status);
      return { query, count: 0, stations: [] };
    }
    return await res.json();
  } catch (err) {
    console.error("Error searching stations", err);
    return { query, count: 0, stations: [] };
  }
}

/**
 * 経路検索を実行する
 * @param {Object} params - 検索パラメータ
 * @param {string} params.fromStation - 出発駅名
 * @param {string} params.toStation - 到着駅名
 * @param {string} params.date - 日付 (YYYY-MM-DD)
 * @param {string} params.time - 時刻 (HH:MM)
 * @param {boolean} params.arriveBy - 到着時刻指定フラグ
 * @returns {Promise<{status: string, query: Object, itineraries: Array}>}
 */
export async function searchRoute({ fromStation, toStation, date, time, arriveBy = false }) {
  try {
    const params = new URLSearchParams({
      from_station: fromStation,
      to_station: toStation,
      date,
      time,
      arrive_by: arriveBy.toString(),
    });
    const res = await fetch(`${API_BASE}/api/route/search?${params}`);
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      console.error("Failed to search route", res.status, errorData);
      // エラーメッセージを文字列に変換
      const errorMsg = typeof errorData.detail === "string"
        ? errorData.detail
        : errorData.detail?.message || JSON.stringify(errorData.detail) || "検索に失敗しました";
      return { status: "error", error: errorMsg, itineraries: [] };
    }
    return await res.json();
  } catch (err) {
    console.error("Error searching route", err);
    return { status: "error", error: err.message || "ネットワークエラー", itineraries: [] };
  }
}
