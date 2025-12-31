import { useEffect, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

// ==========================================
// 設定: 対応路線リスト
// ==========================================
const AVAILABLE_LINES = [
  { id: 'yamanote', name: '山手線', railwayId: 'JR-East.Yamanote', color: '#80C342' },
  { id: 'chuo_rapid', name: '中央線快速', railwayId: 'JR-East.ChuoRapid', color: '#EB5C01' },
  { id: 'keihin_tohoku', name: '京浜東北線', railwayId: 'JR-East.KeihinTohokuNegishi', color: '#00A7E3' },
  { id: 'sobu_local', name: '総武線各駅停車', railwayId: 'JR-East.ChuoSobuLocal', color: '#FFE500' },
];

const TRAIN_UPDATE_INTERVAL_MS = 2000;

const formatTime = (ts) => {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString('ja-JP', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
};

const safeFetchJson = async (url, { timeoutMs = 8000 } = {}) => {
  const controller = new AbortController();
  const t0 = performance.now();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { signal: controller.signal, cache: "no-store" });
    const text = await res.text();

    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      throw new Error(`JSON_PARSE_FAILED status=${res.status} head=${text.slice(0, 180)}`);
    }

    if (!res.ok) {
      throw new Error(`HTTP_${res.status} detail=${json?.detail ?? text?.slice(0, 180)}`);
    }

    return { ok: true, status: res.status, ms: Math.round(performance.now() - t0), json };
  } catch (e) {
    const isAbort = e?.name === "AbortError";
    throw new Error(isAbort ? `TIMEOUT_${timeoutMs}ms` : (e?.message || String(e)));
  } finally {
    clearTimeout(timer);
  }
};

const summarizeLineGeojson = (geo) => {
  const feat = geo?.features?.[0];
  const coords = feat?.geometry?.coordinates || [];
  const propLineId = feat?.properties?.line_id ?? null;

  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
  let coordCount = 0;

  for (const c of coords) {
    if (!Array.isArray(c) || c.length < 2) continue;
    const [lng, lat] = c;
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
    coordCount++;
    minLng = Math.min(minLng, lng);
    minLat = Math.min(minLat, lat);
    maxLng = Math.max(maxLng, lng);
    maxLat = Math.max(maxLat, lat);
  }

  const bbox = (coordCount >= 2) ? [minLng, minLat, maxLng, maxLat] : null;

  return {
    featureCount: geo?.features?.length ?? 0,
    coordCount,
    propLineId,
    bbox,
  };
};


function App() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);

  // ========== 状態管理 ==========
  const [selectedLine, setSelectedLine] = useState('yamanote'); // 現在の路線ID
  const selectedLineRef = useRef('yamanote'); // ポーリング内で参照するためRefも使う

  const [trackedTrain, setTrackedTrain] = useState(null);
  const trackedTrainRef = useRef(null);

  const [searchQuery, setSearchQuery] = useState("");
  const searchQueryRef = useRef("");

  const [displayMode, setDisplayMode] = useState("all");
  const displayModeRef = useRef("all");

  const [mapReady, setMapReady] = useState(false);
  const [debugHud, setDebugHud] = useState({
    lineId: selectedLine,
    shapes: { ok: null, status: null, ms: null, featureCount: 0, coordCount: 0, propLineId: null, bbox: null, err: null },
    stations: { ok: null, status: null, ms: null, count: 0, err: null },
    map: { hasSource: null, hasLayer: null, paintColor: null, lastSetDataAt: null },
  });

  // ========== アニメーション管理 ==========
  const animationRef = useRef(null);
  const trainPositionsRef = useRef({}); // { trainNumber: { current, target, startTime, properties } }

  // State同期 (useEffect内での参照用)
  useEffect(() => { selectedLineRef.current = selectedLine; }, [selectedLine]);
  useEffect(() => { trackedTrainRef.current = trackedTrain; }, [trackedTrain]);
  useEffect(() => { searchQueryRef.current = searchQuery; }, [searchQuery]);
  useEffect(() => { displayModeRef.current = displayMode; }, [displayMode]);

  // ========== 60fps アニメーションループ ==========
  useEffect(() => {
    const animateTrains = () => {
      const map = mapRef.current;
      // 現在の路線のソースを取得
      const src = map?.getSource("trains-source");

      if (!src || Object.keys(trainPositionsRef.current).length === 0) {
        animationRef.current = requestAnimationFrame(animateTrains);
        return;
      }

      const now = performance.now();
      const duration = TRAIN_UPDATE_INTERVAL_MS;

      const features = Object.keys(trainPositionsRef.current).map(key => {
        const train = trainPositionsRef.current[key];
        const t = Math.min(1.0, (now - train.startTime) / duration);

        const lon = train.current[0] + (train.target[0] - train.current[0]) * t;
        const lat = train.current[1] + (train.target[1] - train.current[1]) * t;

        return {
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: { ...train.properties, lon, lat },
        };
      });

      src.setData({ type: "FeatureCollection", features });
      animationRef.current = requestAnimationFrame(animateTrains);
    };

    animationRef.current = requestAnimationFrame(animateTrains);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  // ========== マップ初期化 (初回のみ) ==========
  useEffect(() => {
    if (mapRef.current) return;

    mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/streets-v12",
      center: [139.70, 35.68], // 東京周辺
      zoom: 11,
    });

    mapRef.current = map;

    map.on("load", () => {
      // 共通ソース: 路線図 (LineString)
      map.addSource("railway-line", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addLayer({
        id: "railway-line-layer",
        type: "line",
        source: "railway-line",
        paint: {
          "line-color": "#80C342", // 初期値
          "line-width": 4,
        },
      }, 'road-label'); // 道路ラベルの下に表示

      // 共通ソース: 駅 (Point)
      map.addSource("stations", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addLayer({
        id: "stations-circle",
        type: "circle",
        source: "stations",
        paint: {
          "circle-radius": 3,
          "circle-color": "#ffffff",
          "circle-stroke-color": "#000000",
          "circle-stroke-width": 1,
        },
      });

      // 共通ソース: 列車位置 (Point)
      map.addSource("trains-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });

      // 列車マーカー設定
      map.addLayer({
        id: "trains-layer",
        type: "circle",
        source: "trains-source",
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["zoom"],
            10, 4,
            14, 8,
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-color": [
            "case",
            ["==", ["get", "trainNumber"], trackedTrain || ""], "#FF0000", // 追跡中
            ["==", ["get", "dataQuality"], "rejected"], "#9C27B0", // 無効データ
            // 遅延による色分け
            ["step", ["get", "delaySeconds"],
              "#00B140", 60, // 定刻
              "#FFA500", 300, // 1分遅延
              "#FF4500" // 5分以上遅延
            ]
          ],
        },
      });

      // ポップアップ設定
      const popup = new mapboxgl.Popup({ closeButton: false, closeOnClick: false });

      map.on('mouseenter', 'trains-layer', (e) => {
        map.getCanvas().style.cursor = 'pointer';
        const coordinates = e.features[0].geometry.coordinates.slice();
        const props = e.features[0].properties;

        const html = `
          <div style="font-size:12px; color:black;">
            <strong>${props.trainNumber}</strong><br/>
            ${props.isStopped ? '停車中' : '走行中'}<br/>
            遅延: ${Math.floor(props.delaySeconds / 60)}分
          </div>
        `;
        popup.setLngLat(coordinates).setHTML(html).addTo(map);
      });

      map.on('mouseleave', 'trains-layer', () => {
        map.getCanvas().style.cursor = '';
        popup.remove();
      });

      // 初期ロード完了後にデータ取得を開始
      initLineDataV2(selectedLine);
      setMapReady(true);
    });

  }, []); // eslint-disable-line react-hooks/exhaustive-deps


  // ========== 路線切り替え時の処理 ==========
  useEffect(() => {
    if (!mapReady) return;
    initLineDataV2(selectedLine);
  }, [mapReady, selectedLine]);


  const ensureLineLayer = (map) => {
    if (!map.getSource("railway-line")) {
      map.addSource("railway-line", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
    }
    if (!map.getLayer("railway-line-layer")) {
      map.addLayer({
        id: "railway-line-layer",
        type: "line",
        source: "railway-line",
        paint: { "line-color": "#80C342", "line-width": 4 },
      }, map.getLayer("road-label") ? "road-label" : undefined);
    }
  };

  // 路線データ(形状・駅)の読み込み
  const initLineData = async (lineId) => {
    const map = mapRef.current;
    if (!map) return;

    ensureLineLayer(map);

    const config = AVAILABLE_LINES.find(l => l.id === lineId) || AVAILABLE_LINES[0];

    // 1. 地図上の線の色を変更 (GeoJSONのcolor優先 + config.colorフォールバック)
    // 視認性を上げるために太さを6に設定
    if (map.getLayer('railway-line-layer')) {
      map.setPaintProperty('railway-line-layer', 'line-color', [
        "coalesce",
        ["get", "color"],
        config.color,
      ]);
      map.setPaintProperty("railway-line-layer", "line-width", 6);
    }

    // ★古い線が残って誤認しないように一旦クリア
    const lineSource = map.getSource('railway-line');
    if (lineSource) {
      lineSource.setData({ type: "FeatureCollection", features: [] });
    }

    try {
      console.log(`[initLineData] Fetching static data for: ${lineId}`);

      // 2. 線路形状の取得 (相対パス・キャッシュなし)
      const shapesRes = await fetch(`/api/shapes?lineId=${lineId}`, { cache: "no-store" });
      if (shapesRes.ok) {
        const shapesData = await shapesRes.json();

        // ログ出力（調査用）
        console.log("[line switch]", {
          selected: lineId,
          propLineId: shapesData?.features?.[0]?.properties?.line_id,
          hasSource: !!map.getSource("railway-line"),
          hasLayer: !!map.getLayer("railway-line-layer"),
        });

        if (lineSource) {
          lineSource.setData(shapesData);
          map.triggerRepaint();

          // ==== 切替確認用: fitBounds ====
          try {
            const coords = shapesData?.features?.[0]?.geometry?.coordinates || [];
            if (coords.length >= 2) {
              let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
              for (const [lng, lat] of coords) {
                if (lng < minLng) minLng = lng;
                if (lat < minLat) minLat = lat;
                if (lng > maxLng) maxLng = lng;
                if (lat > maxLat) maxLat = lat;
              }
              map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 40, duration: 600 });
            }
          } catch (e) {
            console.warn("[railway-line] fitBounds failed:", e);
          }
        }
      } else {
        console.error("Failed to fetch shapes:", shapesRes.status);
      }

      // 3. 駅情報の取得 (相対パス・キャッシュなし)
      const stationsRes = await fetch(`/api/stations?lineId=${lineId}`, { cache: "no-store" });
      if (stationsRes.ok) {
        const stationsJson = await stationsRes.json();
        console.log('[initLineData] stationsJson:', stationsJson);

        const stationFeatures = (stationsJson.stations || []).map(st => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [st.coord.lon, st.coord.lat]
          },
          properties: { name: st.name_ja }
        }));

        const stationSource = map.getSource('stations');
        if (stationSource) {
          stationSource.setData({
            type: "FeatureCollection",
            features: stationFeatures
          });
        }
      } else {
        console.error("Failed to fetch stations:", stationsRes.status);
      }

    } catch (e) {
      console.error("Static data load error:", e);
    }

    // アニメーション用バッファをクリア
    trainPositionsRef.current = {};

    // 既存の列車マーカーを一旦消す
    const trainsSrc = map.getSource("trains-source");
    if (trainsSrc) {
      trainsSrc.setData({ type: "FeatureCollection", features: [] });
    }
  };



  // 路線データ(形状・駅)の読み込み (V2: Robust & HUD enabled)
  const initLineDataV2 = async (lineId) => {
    const map = mapRef.current;
    if (!map) return;
    ensureLineLayer(map);
    const config = AVAILABLE_LINES.find(l => l.id === lineId) || AVAILABLE_LINES[0];

    const hasSource = !!map.getSource("railway-line");
    const hasLayer = !!map.getLayer("railway-line-layer");
    const paintColor = hasLayer ? map.getPaintProperty("railway-line-layer", "line-color") : null;

    setDebugHud(prev => ({
      ...prev,
      lineId,
      map: { ...prev.map, hasSource, hasLayer, paintColor }
    }));

    if (hasLayer) {
      map.setPaintProperty("railway-line-layer", "line-color", [
        "coalesce",
        ["get", "color"],
        config.color,
      ]);
      map.setPaintProperty("railway-line-layer", "line-width", 6);
    }

    const lineSource = map.getSource("railway-line");
    lineSource?.setData({ type: "FeatureCollection", features: [] });

    try {
      const r = await safeFetchJson(`/api/shapes?lineId=${lineId}`, { timeoutMs: 8000 });
      const sum = summarizeLineGeojson(r.json);
      setDebugHud(prev => ({ ...prev, shapes: { ok: true, status: r.status, ms: r.ms, ...sum, err: null } }));
      if (!sum.coordCount || !sum.bbox) throw new Error(`SHAPES_INVALID coordCount=${sum.coordCount} bbox=${sum.bbox}`);

      lineSource?.setData(r.json);
      map.triggerRepaint();
      setDebugHud(prev => ({ ...prev, map: { ...prev.map, lastSetDataAt: new Date().toLocaleTimeString() } }));

      const [minLng, minLat, maxLng, maxLat] = sum.bbox;
      map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 40, duration: 500 });
      console.log("[railway-line] setData done", { lineId, propLineId: sum.propLineId, coordCount: sum.coordCount, bbox: sum.bbox });
    } catch (e) {
      setDebugHud(prev => ({ ...prev, shapes: { ...prev.shapes, ok: false, err: String(e) } }));
      console.error("[shapes] failed:", e);
    }

    try {
      const r = await safeFetchJson(`/api/stations?lineId=${lineId}`, { timeoutMs: 8000 });
      const stationsJson = r.json || {};
      const count = stationsJson.stations?.length || 0;
      setDebugHud(prev => ({ ...prev, stations: { ok: true, status: r.status, ms: r.ms, count, err: null } }));
      const stationFeatures = (stationsJson.stations || []).map(st => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [st.coord.lon, st.coord.lat] },
        properties: { name: st.name_ja }
      }));
      const stationSource = map.getSource('stations');
      if (stationSource) stationSource.setData({ type: "FeatureCollection", features: stationFeatures });
    } catch (e) {
      setDebugHud(prev => ({ ...prev, stations: { ...prev.stations, ok: false, err: String(e) } }));
      console.error("[stations] failed:", e);
    }

    trainPositionsRef.current = {};
    const trainsSrc = map.getSource("trains-source");
    if (trainsSrc) trainsSrc.setData({ type: "FeatureCollection", features: [] });
  };


  // ========== データポーリング (定期実行) ==========
  useEffect(() => {
    let intervalId = null;

    const fetchAndUpdate = async () => {
      const map = mapRef.current;
      if (!map || !map.getSource("trains-source")) return;

      const currentLineId = selectedLineRef.current; // Refから最新の値を取得

      try {
        // ★ API呼び出し: 選択中の路線IDを使う
        const res = await fetch(`/api/trains/${currentLineId}/positions/v4`);
        if (!res.ok) return;
        const json = await res.json();
        const positions = json.positions || [];

        // GeoJSON変換 & アニメーション目標更新
        const now = performance.now();

        // 検索フィルタ
        const query = searchQueryRef.current.trim().toUpperCase();
        const filteredPositions = query
          ? positions.filter(p => p.train_number && p.train_number.includes(query))
          : positions;

        const activeKeys = new Set();

        filteredPositions.forEach(p => {
          if (!p.location) return;
          const { latitude, longitude } = p.location;
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
          const key = p.train_number;
          activeKeys.add(key);

          const newTarget = [longitude, latitude];

          // データ補正 (プロパティを扱いやすい形に)
          const props = {
            trainNumber: p.train_number,
            delaySeconds: p.delay || 0,
            isStopped: p.status === 'stopped',
            dataQuality: 'good'
          };

          if (!trainPositionsRef.current[key]) {
            // 新規列車
            trainPositionsRef.current[key] = {
              current: newTarget,
              target: newTarget,
              startTime: now,
              properties: props
            };
          } else {
            // 更新
            const old = trainPositionsRef.current[key];
            trainPositionsRef.current[key] = {
              current: old.target, // 前回ターゲットを現在地とする
              target: newTarget,
              startTime: now,
              properties: props
            };
          }
        });

        // 消失した列車を削除
        Object.keys(trainPositionsRef.current).forEach(key => {
          if (!activeKeys.has(key)) delete trainPositionsRef.current[key];
        });

      } catch (err) {
        console.error("Polling error:", err);
      }
    };

    // 初回実行と定期実行
    fetchAndUpdate();
    intervalId = setInterval(fetchAndUpdate, TRAIN_UPDATE_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, []); // 依存配列は空 (内部でRefを使って最新の路線IDを見るため)


  return (
    <div style={{ position: 'relative', width: "100vw", height: "100vh" }}>
      {/* コントロールパネル */}
      <div style={{
        position: 'absolute',
        top: 10,
        left: 10,
        zIndex: 1000,
        background: 'rgba(255, 255, 255, 0.95)',
        padding: '15px',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        width: '250px'
      }}>
        <h2 style={{ margin: 0, fontSize: '16px', borderBottom: '2px solid #ddd', paddingBottom: '5px' }}>
          NowTrain コントロール
        </h2>

        {/* 1. 路線選択 (MS11の核心) */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}>
            🛤 路線選択:
          </label>
          <select
            value={selectedLine}
            onChange={(e) => setSelectedLine(e.target.value)}
            style={{ width: '100%', padding: '6px', fontSize: '14px', borderRadius: '4px' }}
          >
            {AVAILABLE_LINES.map(line => (
              <option key={line.id} value={line.id}>
                {line.name}
              </option>
            ))}
          </select>
        </div>

        {/* 2. 列車検索 */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}>
            🔍 列車番号検索:
          </label>
          <div style={{ display: 'flex', gap: '5px' }}>
            <input
              type="text"
              placeholder="例: 1234G"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
              style={{ flex: 1, padding: '4px', borderRadius: '4px', border: '1px solid #ccc' }}
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} style={{ cursor: 'pointer' }}>×</button>
            )}
          </div>
        </div>

        {/* 3. 追跡 */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}>
            📍 自動追跡:
          </label>
          <input
            type="text"
            placeholder="追跡する列車番号"
            onChange={(e) => setTrackedTrain(e.target.value.toUpperCase() || null)}
            style={{ width: '100%', padding: '4px', borderRadius: '4px', border: '1px solid #ccc' }}
          />
        </div>

      </div>

      <div style={{
        position: "absolute",
        right: 10,
        bottom: 10,
        zIndex: 2000,
        background: "rgba(0,0,0,0.75)",
        color: "#fff",
        padding: "10px",
        borderRadius: "8px",
        fontSize: "12px",
        width: "360px",
        whiteSpace: "pre-wrap",
      }}>
        {JSON.stringify(debugHud, null, 2)}
      </div>
      <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}

export default App;
