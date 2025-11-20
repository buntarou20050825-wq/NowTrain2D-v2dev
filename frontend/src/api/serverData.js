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
