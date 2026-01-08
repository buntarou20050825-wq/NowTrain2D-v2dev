import { useEffect, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { AVAILABLE_LINES } from "../constants/lines";
import RouteSearchPanel from "./RouteSearchPanel";
import { extractTrainNumber, isSameTrain } from "../utils/trainUtils";

const TRAIN_UPDATE_INTERVAL_MS = 2000;

const formatTime = (ts) => {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

// ========== 経路表示用ヘルパー関数 ==========

// 最近傍座標インデックスを検索
const findClosestIndex = (coords, target) => {
  let minDist = Infinity;
  let closestIdx = 0;
  for (let i = 0; i < coords.length; i++) {
    const dist = (coords[i][0] - target[0]) ** 2 + (coords[i][1] - target[1]) ** 2;
    if (dist < minDist) {
      minDist = dist;
      closestIdx = i;
    }
  }
  return closestIdx;
};

// 路線を3セグメントに分割
const splitLineAtStations = (coords, fromIdx, toIdx) => {
  const start = Math.min(fromIdx, toIdx);
  const end = Math.max(fromIdx, toIdx);

  const before = coords.slice(0, start + 1);
  const active = coords.slice(start, end + 1);
  const after = coords.slice(end);

  return [before, active, after];
};

// LineString Feature を作成
const createLineFeature = (coordinates) => ({
  type: "Feature",
  geometry: {
    type: "LineString",
    coordinates: coordinates,
  },
  properties: {},
});

// OTP数字ID → 路線IDマッピング（JR東日本GTFSデータ）
const OTP_NUMERIC_ROUTE_MAP = {
  "10": "yamanote",
  "11": "chuo_rapid",
  "12": "sobu_local",
  "22": "keihin_tohoku",
  "13": "tokaido",
  "14": "yokosuka",
  "15": "sobu_rapid",
  "16": "joban_rapid",
  "17": "joban_local",
  "18": "keiyo",
  "19": "musashino",
  "20": "nambu",
  "21": "yokohama",
  "23": "saikyo",
  "24": "shonan_shinjuku",
  "25": "chuo",
  "26": "ome",
  "27": "itsukaichi",
  "28": "utsunomiya",
  "29": "takasaki",
  "30": "joetsu",
  "31": "ryomo",
  "32": "nikko",
  "33": "joban",
  "34": "mito",
  "35": "sobu",
  "36": "narita",
  "37": "narita_airport",
  "38": "narita_abiko",
  "39": "kashima",
  "40": "togane",
  "41": "uchibo",
  "42": "sotobo",
  "43": "kururi",
  "44": "ito",
  "45": "keiyo_koya",
  "46": "keiyo_futamata",
  "47": "kawagoe",
  "48": "musashino_kunitachi",
  "49": "musashino_omiya",
  "50": "musashino_nishiurawa",
  "51": "nambu_branch",
  "52": "tsurumi",
  "53": "tsurumi_umishibaura",
  "54": "tsurumi_okawa",
  "55": "sagami",
  "56": "hachiko",
  "57": "sotetsu_direct",
  "58": "yamanote_freight",
  "59": "tokaido_freight",
  "60": "osaki_branch",
};

// 英語路線名 → 路線IDマッピング
const ENGLISH_LINE_NAME_MAP = {
  "yamanote": "yamanote",
  "chuo rapid": "chuo_rapid",
  "chuo-sobu local": "sobu_local",
  "keihin-tohoku": "keihin_tohoku",
  "negishi": "keihin_tohoku",
  "tokaido": "tokaido",
  "yokosuka": "yokosuka",
  "sobu rapid": "sobu_rapid",
  "joban rapid": "joban_rapid",
  "joban local": "joban_local",
  "keiyo": "keiyo",
  "musashino": "musashino",
  "nambu": "nambu",
  "yokohama": "yokohama",
  "saikyo": "saikyo",
  "kawagoe": "kawagoe",
  "shonan-shinjuku": "shonan_shinjuku",
  "chuo": "chuo",
  "ome": "ome",
  "itsukaichi": "itsukaichi",
  "utsunomiya": "utsunomiya",
  "takasaki": "takasaki",
  "joetsu": "joetsu",
  "ryomo": "ryomo",
  "nikko": "nikko",
  "joban": "joban",
  "mito": "mito",
  "sobu": "sobu",
  "narita": "narita",
  "kashima": "kashima",
  "togane": "togane",
  "uchibo": "uchibo",
  "sotobo": "sotobo",
  "kururi": "kururi",
  "ito": "ito",
  "sagami": "sagami",
  "hachiko": "hachiko",
  "tsurumi": "tsurumi",
};

// OTP route から路線情報を取得（long_name を優先）
const getLineInfoFromRoute = (route) => {
  if (!route) return null;

  // 1. route.long_name から推測（最優先）
  const longName = (route.long_name || route.longName || "").toLowerCase();
  if (longName) {
    // 英語名マッピングをチェック
    for (const [keyword, lineId] of Object.entries(ENGLISH_LINE_NAME_MAP)) {
      if (longName.includes(keyword)) {
        const line = AVAILABLE_LINES.find((l) => l.id === lineId);
        if (line) {
          return { id: line.id, railwayId: line.railwayId, color: line.color };
        }
      }
    }

    // 日本語名でマッチング
    const line = AVAILABLE_LINES.find(
      (l) => longName.includes(l.name.toLowerCase()) || l.name.toLowerCase().includes(longName)
    );
    if (line) {
      return { id: line.id, railwayId: line.railwayId, color: line.color };
    }
  }

  // 2. gtfs_id から "JR-East.Xxx" 形式を抽出
  if (route.gtfs_id) {
    const parts = route.gtfs_id.split(":");
    if (parts.length > 1) {
      const routeIdPart = parts[1];
      if (routeIdPart.startsWith("JR-East.")) {
        const line = AVAILABLE_LINES.find((l) => l.railwayId === routeIdPart);
        if (line) {
          return { id: line.id, railwayId: line.railwayId, color: line.color };
        }
      }
    }
  }

  // 3. route.short_name から推測
  const shortName = route.short_name || route.shortName || "";
  if (shortName) {
    const line = AVAILABLE_LINES.find(
      (l) => l.name.includes(shortName) || shortName.includes(l.name)
    );
    if (line) {
      return { id: line.id, railwayId: line.railwayId, color: line.color };
    }
  }

  console.warn("[getLineInfoFromRoute] Could not match route:", route);
  return null;
};

// 路線の駅リストをフェッチ
const fetchStationsForLine = async (lineId) => {
  try {
    const res = await fetch(`/api/stations?lineId=${lineId}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.stations || [];
  } catch (err) {
    console.error("[fetchStationsForLine] Error:", err);
    return [];
  }
};

// 名前を正規化（ハイフン、スペース、長音記号を除去）
const normalizeName = (name) => {
  if (!name) return "";
  return name
    .toLowerCase()
    .replace(/[-\s・ー]/g, "")  // ハイフン、スペース、中点、長音を除去
    .replace(/駅$/, "")
    .replace(/ station$/i, "")
    .replace(/ō/g, "o")  // ō → o
    .replace(/ū/g, "u"); // ū → u
};

// 駅名から駅リスト内のインデックスを検索（日本語名・英語名両方に対応）
const findStationIndex = (stations, stationName) => {
  if (!stationName || !stations.length) return -1;

  const normalizedSearch = normalizeName(stationName);

  // 1. 正規化後の完全一致
  let idx = stations.findIndex((s) => {
    const normalizedJa = normalizeName(s.name_ja);
    const normalizedEn = normalizeName(s.name_en);
    return normalizedJa === normalizedSearch || normalizedEn === normalizedSearch;
  });
  if (idx >= 0) return idx;

  // 2. 含む検索（正規化後）
  idx = stations.findIndex((s) => {
    const normalizedJa = normalizeName(s.name_ja);
    const normalizedEn = normalizeName(s.name_en);
    return (
      normalizedJa.includes(normalizedSearch) ||
      normalizedSearch.includes(normalizedJa) ||
      normalizedEn.includes(normalizedSearch) ||
      normalizedSearch.includes(normalizedEn)
    );
  });
  return idx;
};

// 駅座標から路線形状の最近傍インデックスを取得
const getShapeIndexForStation = (shapeCoords, stationCoord) => {
  let minDist = Infinity;
  let closestIdx = 0;
  for (let i = 0; i < shapeCoords.length; i++) {
    const dist =
      (shapeCoords[i][0] - stationCoord.lon) ** 2 +
      (shapeCoords[i][1] - stationCoord.lat) ** 2;
    if (dist < minDist) {
      minDist = dist;
      closestIdx = i;
    }
  }
  return closestIdx;
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

  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
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

  const bbox = coordCount >= 2 ? [minLng, minLat, maxLng, maxLat] : null;

  return {
    featureCount: geo?.features?.length ?? 0,
    coordCount,
    propLineId,
    bbox,
  };
};

function MapView() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);

  // ========== 状態管理 ==========
  const [selectedLine, setSelectedLine] = useState("yamanote");
  const selectedLineRef = useRef("yamanote");

  const [trackedTrain, setTrackedTrain] = useState(null);
  const trackedTrainRef = useRef(null);

  const [searchQuery, setSearchQuery] = useState("");
  const searchQueryRef = useRef("");

  const [displayMode, setDisplayMode] = useState("all");
  const displayModeRef = useRef("all");

  const [showRouteSearch, setShowRouteSearch] = useState(false);

  // ========== My Train 状態管理 ==========
  // My Train の trip_id リスト（複数路線の乗り換えに対応）
  const [myTrainIds, setMyTrainIds] = useState([]);
  const myTrainIdsRef = useRef([]);

  // My Train の路線ID リスト（該当路線の電車のみ表示用）
  const [myTrainLineIds, setMyTrainLineIds] = useState([]);
  const myTrainLineIdsRef = useRef([]);

  // 選択された itinerary
  const [selectedItinerary, setSelectedItinerary] = useState(null);

  // デバッグ対象列車
  const [debugTrainNumber, setDebugTrainNumber] = useState("");
  const debugTrainNumberRef = useRef("");
  const [debugTrainData, setDebugTrainData] = useState(null);

  const [mapReady, setMapReady] = useState(false);
  const [debugHud, setDebugHud] = useState({
    lineId: selectedLine,
    shapes: { ok: null, status: null, ms: null, featureCount: 0, coordCount: 0, propLineId: null, bbox: null, err: null },
    stations: { ok: null, status: null, ms: null, count: 0, err: null },
    map: { hasSource: null, hasLayer: null, paintColor: null, lastSetDataAt: null },
  });

  // ========== アニメーション管理 ==========
  const animationRef = useRef(null);
  const trainPositionsRef = useRef({});

  useEffect(() => {
    selectedLineRef.current = selectedLine;
  }, [selectedLine]);
  useEffect(() => {
    trackedTrainRef.current = trackedTrain;
  }, [trackedTrain]);
  useEffect(() => {
    searchQueryRef.current = searchQuery;
  }, [searchQuery]);
  useEffect(() => {
    displayModeRef.current = displayMode;
  }, [displayMode]);
  useEffect(() => {
    debugTrainNumberRef.current = debugTrainNumber;
  }, [debugTrainNumber]);
  useEffect(() => {
    myTrainIdsRef.current = myTrainIds;
  }, [myTrainIds]);
  useEffect(() => {
    myTrainLineIdsRef.current = myTrainLineIds;
  }, [myTrainLineIds]);

  // ========== 経路表示関数 ==========

  // 動的に追加されたレイヤーとソースをクリア
  const clearRouteLayers = () => {
    const map = mapRef.current;
    if (!map) return;

    const style = map.getStyle();
    if (!style) return;

    // "route-" で始まるレイヤーを削除
    const layersToRemove = style.layers
      .filter((l) => l.id.startsWith("route-"))
      .map((l) => l.id);

    layersToRemove.forEach((id) => {
      if (map.getLayer(id)) map.removeLayer(id);
    });

    // "route-" で始まるソースを削除
    const sourcesToRemove = Object.keys(style.sources).filter((s) => s.startsWith("route-"));

    sourcesToRemove.forEach((id) => {
      if (map.getSource(id)) map.removeSource(id);
    });
  };

  // セグメントレイヤーを追加
  const addRouteSegmentLayers = (map, routeId, segments, color) => {
    const layerPrefix = `route-${routeId.replace(/[^a-zA-Z0-9]/g, "-")}`;

    // 薄いセグメント（乗車前 + 降車後）
    const fadedFeatures = [
      segments.before.length > 1 ? createLineFeature(segments.before) : null,
      segments.after.length > 1 ? createLineFeature(segments.after) : null,
    ].filter(Boolean);

    if (fadedFeatures.length > 0) {
      map.addSource(`${layerPrefix}-faded`, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: fadedFeatures,
        },
      });

      map.addLayer(
        {
          id: `${layerPrefix}-faded-layer`,
          type: "line",
          source: `${layerPrefix}-faded`,
          paint: {
            "line-color": color,
            "line-width": 3,
            "line-opacity": 0.3,
          },
        },
        "trains-layer"
      );
    }

    // 強調セグメント（乗車区間）
    if (segments.active.length > 1) {
      map.addSource(`${layerPrefix}-active`, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [createLineFeature(segments.active)],
        },
      });

      // 発光エフェクト用のぼかしレイヤー
      map.addLayer(
        {
          id: `${layerPrefix}-glow`,
          type: "line",
          source: `${layerPrefix}-active`,
          paint: {
            "line-color": color,
            "line-width": 14,
            "line-opacity": 0.35,
            "line-blur": 6,
          },
        },
        "trains-layer"
      );

      // メインの強調レイヤー
      map.addLayer(
        {
          id: `${layerPrefix}-active-layer`,
          type: "line",
          source: `${layerPrefix}-active`,
          paint: {
            "line-color": color,
            "line-width": 6,
            "line-opacity": 1.0,
          },
        },
        "trains-layer"
      );
    }
  };

  // 経路を強調表示（路線全体を表示し、乗車区間のみハイライト）
  const displayRouteWithHighlight = async (itinerary) => {
    const map = mapRef.current;
    if (!map || !itinerary) return;

    // 既存の経路レイヤーをクリア
    clearRouteLayers();

    // 全座標を収集（fitBounds用）
    const allCoordinates = [];

    // 各leg（乗り換え区間）を処理
    for (const leg of itinerary.legs) {
      if (leg.mode === "WALK") continue; // 徒歩は除外

      // 1. 路線情報を特定
      const lineInfo = getLineInfoFromRoute(leg.route);

      if (!lineInfo) {
        console.warn("[displayRouteWithHighlight] Could not determine lineInfo for route:", leg.route);
        continue;
      }

      try {
        // 2. 路線形状と駅リストを並行取得
        const [shapeRes, stations] = await Promise.all([
          fetch(`/api/shapes?lineId=${lineInfo.id}`),
          fetchStationsForLine(lineInfo.id),
        ]);

        if (!shapeRes.ok) {
          console.warn("[displayRouteWithHighlight] Failed to fetch shapes for:", lineInfo.id);
          continue;
        }
        const shapeData = await shapeRes.json();
        const fullCoords = shapeData.features?.[0]?.geometry?.coordinates;

        if (!fullCoords || fullCoords.length < 2) {
          console.warn("[displayRouteWithHighlight] No coordinates in shape data for:", lineInfo.id);
          continue;
        }

        // 3. 駅名でマッチング
        const fromName = leg.from.name;
        const toName = leg.to.name;

        const fromStationIdx = findStationIndex(stations, fromName);
        const toStationIdx = findStationIndex(stations, toName);

        // 4. 駅が見つかった場合、その駅座標から形状インデックスを取得
        let fromShapeIdx, toShapeIdx;

        if (fromStationIdx >= 0 && stations[fromStationIdx]?.coord) {
          fromShapeIdx = getShapeIndexForStation(fullCoords, stations[fromStationIdx].coord);
        } else {
          // フォールバック: OTP座標を使用
          fromShapeIdx = findClosestIndex(fullCoords, [leg.from.lon, leg.from.lat]);
        }

        if (toStationIdx >= 0 && stations[toStationIdx]?.coord) {
          toShapeIdx = getShapeIndexForStation(fullCoords, stations[toStationIdx].coord);
        } else {
          // フォールバック: OTP座標を使用
          toShapeIdx = findClosestIndex(fullCoords, [leg.to.lon, leg.to.lat]);
        }

        // 5. 3つのセグメントに分割
        const [beforeCoords, activeCoords, afterCoords] = splitLineAtStations(
          fullCoords,
          fromShapeIdx,
          toShapeIdx
        );

        // 6. 各セグメントをレイヤーとして追加（路線カラーを使用）
        const routeId = leg.route?.gtfs_id || `leg-${Date.now()}`;
        addRouteSegmentLayers(
          map,
          routeId,
          {
            before: beforeCoords,
            active: activeCoords,
            after: afterCoords,
          },
          lineInfo.color
        );

        // fitBounds用に座標を収集
        allCoordinates.push(...fullCoords);
      } catch (err) {
        console.error("[displayRouteWithHighlight] Error processing leg:", err);
      }
    }

    // 7. 全体が見えるようにズーム
    if (allCoordinates.length >= 2) {
      const bounds = allCoordinates.reduce(
        (b, c) => b.extend(c),
        new mapboxgl.LngLatBounds(allCoordinates[0], allCoordinates[0])
      );
      map.fitBounds(bounds, { padding: 60, duration: 500 });
    }
  };

  const clearRoute = () => {
    clearRouteLayers();
  };

  // ========== My Train 経路選択ハンドラ ==========
  const handleRouteSelect = async (itinerary) => {
    // 1. 経路を地図に表示
    await displayRouteWithHighlight(itinerary);

    // 2. 選択された itinerary を保存
    setSelectedItinerary(itinerary);

    // 3. My Train の trip_id を抽出
    const tripIds = [];
    const lineIds = [];

    for (const leg of itinerary.legs) {
      if (leg.mode === "WALK") continue;

      // trip_id から正規化された列車番号を抽出
      // "1:1111406H" → "406H" (OTP と ODPT の共通フォーマット)
      const tripGtfsId = leg.trip_id || "";
      const normalizedTrainNumber = extractTrainNumber(tripGtfsId);

      if (normalizedTrainNumber) {
        tripIds.push(normalizedTrainNumber);
        console.log("[My Train] Extracted train_number:", normalizedTrainNumber, "from", tripGtfsId);
      }

      // 路線IDも収集
      const lineInfo = getLineInfoFromRoute(leg.route);
      if (lineInfo) {
        lineIds.push(lineInfo.id);
        console.log("[My Train] Extracted lineId:", lineInfo.id);
      }
    }

    // 重複を除去して設定
    setMyTrainIds(tripIds);
    setMyTrainLineIds([...new Set(lineIds)]);
    console.log("[My Train] Tracking trains:", tripIds, "on lines:", [...new Set(lineIds)]);
  };

  // 経路検索パネルを閉じる時にクリア
  const handleCloseRouteSearch = () => {
    setShowRouteSearch(false);
    clearRoute();
    setMyTrainIds([]);
    setMyTrainLineIds([]);
    setSelectedItinerary(null);
    console.log("[My Train] Cleared tracking");
  };

  // ========== 60fps アニメーションループ ==========
  useEffect(() => {
    const animateTrains = () => {
      const map = mapRef.current;
      const src = map?.getSource("trains-source");

      if (!src || Object.keys(trainPositionsRef.current).length === 0) {
        animationRef.current = requestAnimationFrame(animateTrains);
        return;
      }

      const now = performance.now();
      const duration = TRAIN_UPDATE_INTERVAL_MS;

      // My Train モード中かどうか
      const isMyTrainMode = myTrainIdsRef.current.length > 0;

      const features = Object.keys(trainPositionsRef.current).map((key) => {
        const train = trainPositionsRef.current[key];
        const t = Math.min(1.0, (now - train.startTime) / duration);

        const lon = train.current[0] + (train.target[0] - train.current[0]) * t;
        const lat = train.current[1] + (train.target[1] - train.current[1]) * t;

        // デバッグ対象かどうかフラグを追加
        const isDebugTarget = debugTrainNumberRef.current &&
          key.toUpperCase() === debugTrainNumberRef.current.trim().toUpperCase();

        // My Train 判定
        // 正規化された列車番号で比較 (例: "406H" === "406H")
        const trainNumber = train.properties?.trainNumber || key;
        const isMyTrain = isMyTrainMode && myTrainIdsRef.current.some(
          (savedTrainNumber) => isSameTrain(trainNumber, savedTrainNumber)
        );

        // My Train モード中の他の電車
        const isOtherTrain = isMyTrainMode && !isMyTrain;

        return {
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: {
            ...train.properties,
            lon,
            lat,
            isDebugTarget,
            isMyTrain,
            isOtherTrain,
          },
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
      center: [139.7, 35.68],
      zoom: 11,
    });

    mapRef.current = map;

    map.on("load", () => {
      map.addSource("railway-line", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer(
        {
          id: "railway-line-layer",
          type: "line",
          source: "railway-line",
          paint: {
            "line-color": "#80C342",
            "line-width": 4,
          },
        },
        "road-label"
      );

      map.addSource("stations", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
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

      // 矢印アイコンを生成して登録
      const width = 48;
      const height = 48;
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");

      // 矢印を描画 (上向き = 0度)
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.moveTo(width / 2, 4);
      ctx.lineTo(width - 8, height - 8);
      ctx.lineTo(width / 2, height - 16); // くびれ
      ctx.lineTo(8, height - 8);
      ctx.closePath();
      ctx.fill();

      // 外枠
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#000000";
      ctx.stroke();

      const imageData = ctx.getImageData(0, 0, width, height);
      map.addImage("train-arrow", imageData, { sdf: true }); // SDF有効化で着色可能に

      map.addSource("trains-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "trains-layer",
        type: "symbol",
        source: "trains-source",
        layout: {
          "icon-image": "train-arrow",
          "icon-size": [
            "case",
            // My Train: より大きく表示
            ["==", ["get", "isMyTrain"], true],
            0.8,
            0.6
          ],
          "icon-rotate": ["get", "bearing"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-color": [
            "case",
            // My Train: 赤色（最優先）
            ["==", ["get", "isMyTrain"], true],
            "#FF0000",
            // デバッグ対象: 紫色
            ["==", ["get", "isDebugTarget"], true],
            "#9b59b6",
            // My Train モード中の他の電車: グレー
            ["==", ["get", "isOtherTrain"], true],
            "#888888",
            // 追跡対象: 赤色
            ["==", ["get", "trainNumber"], trackedTrain || ""],
            "#FF0000",
            ["==", ["get", "dataQuality"], "rejected"],
            "#9C27B0",
            // 通常モード: 遅延に基づく色分け
            ["step", ["get", "delaySeconds"], "#00B140", 60, "#FFA500", 300, "#FF4500"],
          ],
          "icon-opacity": [
            "case",
            ["==", ["get", "isMyTrain"], true],
            1.0,
            ["==", ["get", "isOtherTrain"], true],
            0.4,
            1.0
          ],
          "icon-halo-color": [
            "case",
            // My Train: 赤い発光
            ["==", ["get", "isMyTrain"], true],
            "#FF0000",
            ["==", ["get", "isDebugTarget"], true],
            "#ffffff",
            "#ffffff"
          ],
          "icon-halo-width": [
            "case",
            // My Train: 大きな発光効果
            ["==", ["get", "isMyTrain"], true],
            6,
            ["==", ["get", "isDebugTarget"], true],
            3,
            1
          ],
          "icon-halo-blur": [
            "case",
            // My Train: ぼかし効果
            ["==", ["get", "isMyTrain"], true],
            4,
            0
          ],
        },
      });

      // 検索経路表示用レイヤー
      map.addSource("searched-route", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer(
        {
          id: "searched-route-layer",
          type: "line",
          source: "searched-route",
          paint: {
            "line-color": "#e74c3c",
            "line-width": 6,
            "line-opacity": 0.8,
          },
        },
        "trains-layer"
      );

      const popup = new mapboxgl.Popup({ closeButton: false, closeOnClick: false });

      map.on("mouseenter", "trains-layer", (e) => {
        map.getCanvas().style.cursor = "pointer";
        const coordinates = e.features[0].geometry.coordinates.slice();
        const props = e.features[0].properties;

        const html = `
          <div style="font-size:12px; color:black;">
            <strong>${props.trainNumber}</strong><br/>
            ${props.isStopped ? "停車中" : "走行中"}<br/>
            遅延: ${Math.floor(props.delaySeconds / 60)}分
          </div>
        `;
        popup.setLngLat(coordinates).setHTML(html).addTo(map);
      });

      map.on("mouseleave", "trains-layer", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });

      initLineDataV2(selectedLine);
      setMapReady(true);
    });
  }, []);

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
      map.addLayer(
        {
          id: "railway-line-layer",
          type: "line",
          source: "railway-line",
          paint: { "line-color": "#80C342", "line-width": 4 },
        },
        map.getLayer("road-label") ? "road-label" : undefined
      );
    }
  };

  const initLineData = async (lineId) => {
    const map = mapRef.current;
    if (!map) return;

    ensureLineLayer(map);

    const config = AVAILABLE_LINES.find((l) => l.id === lineId) || AVAILABLE_LINES[0];

    if (map.getLayer("railway-line-layer")) {
      map.setPaintProperty("railway-line-layer", "line-color", ["coalesce", ["get", "color"], config.color]);
      map.setPaintProperty("railway-line-layer", "line-width", 6);
    }

    const lineSource = map.getSource("railway-line");
    if (lineSource) {
      lineSource.setData({ type: "FeatureCollection", features: [] });
    }

    try {
      console.log(`[initLineData] Fetching static data for: ${lineId}`);

      const shapesRes = await fetch(`/api/shapes?lineId=${lineId}`, { cache: "no-store" });
      if (shapesRes.ok) {
        const shapesData = await shapesRes.json();

        console.log("[line switch]", {
          selected: lineId,
          propLineId: shapesData?.features?.[0]?.properties?.line_id,
          hasSource: !!map.getSource("railway-line"),
          hasLayer: !!map.getLayer("railway-line-layer"),
        });

        if (lineSource) {
          lineSource.setData(shapesData);
          map.triggerRepaint();

          try {
            const coords = shapesData?.features?.[0]?.geometry?.coordinates || [];
            if (coords.length >= 2) {
              let minLng = Infinity;
              let minLat = Infinity;
              let maxLng = -Infinity;
              let maxLat = -Infinity;
              for (const [lng, lat] of coords) {
                if (lng < minLng) minLng = lng;
                if (lat < minLat) minLat = lat;
                if (lng > maxLng) maxLng = lng;
                if (lat > maxLat) maxLat = lat;
              }
              map.fitBounds(
                [
                  [minLng, minLat],
                  [maxLng, maxLat],
                ],
                { padding: 40, duration: 600 }
              );
            }
          } catch (e) {
            console.warn("[railway-line] fitBounds failed:", e);
          }
        }
      } else {
        console.error("Failed to fetch shapes:", shapesRes.status);
      }

      const stationsRes = await fetch(`/api/stations?lineId=${lineId}`, { cache: "no-store" });
      if (stationsRes.ok) {
        const stationsJson = await stationsRes.json();
        console.log("[initLineData] stationsJson:", stationsJson);

        const stationFeatures = (stationsJson.stations || []).map((st) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [st.coord.lon, st.coord.lat],
          },
          properties: { name: st.name_ja },
        }));

        const stationSource = map.getSource("stations");
        if (stationSource) {
          stationSource.setData({
            type: "FeatureCollection",
            features: stationFeatures,
          });
        }
      } else {
        console.error("Failed to fetch stations:", stationsRes.status);
      }
    } catch (e) {
      console.error("Static data load error:", e);
    }

    trainPositionsRef.current = {};

    const trainsSrc = map.getSource("trains-source");
    if (trainsSrc) {
      trainsSrc.setData({ type: "FeatureCollection", features: [] });
    }
  };

  const initLineDataV2 = async (lineId) => {
    const map = mapRef.current;
    if (!map) return;
    ensureLineLayer(map);
    const config = AVAILABLE_LINES.find((l) => l.id === lineId) || AVAILABLE_LINES[0];

    const hasSource = !!map.getSource("railway-line");
    const hasLayer = !!map.getLayer("railway-line-layer");
    const paintColor = hasLayer ? map.getPaintProperty("railway-line-layer", "line-color") : null;

    setDebugHud((prev) => ({
      ...prev,
      lineId,
      map: { ...prev.map, hasSource, hasLayer, paintColor },
    }));

    if (hasLayer) {
      map.setPaintProperty("railway-line-layer", "line-color", ["coalesce", ["get", "color"], config.color]);
      map.setPaintProperty("railway-line-layer", "line-width", 6);
    }

    const lineSource = map.getSource("railway-line");
    lineSource?.setData({ type: "FeatureCollection", features: [] });

    try {
      const r = await safeFetchJson(`/api/shapes?lineId=${lineId}`, { timeoutMs: 8000 });
      const sum = summarizeLineGeojson(r.json);
      setDebugHud((prev) => ({ ...prev, shapes: { ok: true, status: r.status, ms: r.ms, ...sum, err: null } }));
      if (!sum.coordCount || !sum.bbox) throw new Error(`SHAPES_INVALID coordCount=${sum.coordCount} bbox=${sum.bbox}`);

      lineSource?.setData(r.json);
      map.triggerRepaint();
      setDebugHud((prev) => ({ ...prev, map: { ...prev.map, lastSetDataAt: new Date().toLocaleTimeString() } }));

      const [minLng, minLat, maxLng, maxLat] = sum.bbox;
      map.fitBounds(
        [
          [minLng, minLat],
          [maxLng, maxLat],
        ],
        { padding: 40, duration: 500 }
      );
      console.log("[railway-line] setData done", { lineId, propLineId: sum.propLineId, coordCount: sum.coordCount, bbox: sum.bbox });
    } catch (e) {
      setDebugHud((prev) => ({ ...prev, shapes: { ...prev.shapes, ok: false, err: String(e) } }));
      console.error("[shapes] failed:", e);
    }

    try {
      const r = await safeFetchJson(`/api/stations?lineId=${lineId}`, { timeoutMs: 8000 });
      const stationsJson = r.json || {};
      const count = stationsJson.stations?.length || 0;
      setDebugHud((prev) => ({ ...prev, stations: { ok: true, status: r.status, ms: r.ms, count, err: null } }));
      const stationFeatures = (stationsJson.stations || []).map((st) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [st.coord.lon, st.coord.lat] },
        properties: { name: st.name_ja },
      }));
      const stationSource = map.getSource("stations");
      if (stationSource) stationSource.setData({ type: "FeatureCollection", features: stationFeatures });
    } catch (e) {
      setDebugHud((prev) => ({ ...prev, stations: { ...prev.stations, ok: false, err: String(e) } }));
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

      // My Train モードの場合、該当路線のデータを取得
      // そうでなければ、選択された路線のデータを取得
      const lineIdsToFetch = myTrainLineIdsRef.current.length > 0
        ? myTrainLineIdsRef.current
        : [selectedLineRef.current];

      try {
        const allPositions = [];

        // 複数路線を並行取得
        const fetchPromises = lineIdsToFetch.map(async (lineId) => {
          try {
            const res = await fetch(`/api/trains/${lineId}/positions/v4`);
            if (res.ok) {
              const json = await res.json();
              return json.positions || [];
            }
          } catch (err) {
            console.error(`[My Train] Failed to fetch positions for ${lineId}:`, err);
          }
          return [];
        });

        const results = await Promise.all(fetchPromises);
        results.forEach((positions) => allPositions.push(...positions));

        const now = performance.now();

        const query = searchQueryRef.current.trim().toUpperCase();
        const filteredPositions = query
          ? allPositions.filter((p) => p.train_number && p.train_number.includes(query))
          : allPositions;

        const activeKeys = new Set();

        filteredPositions.forEach((p) => {
          if (!p.location) return;
          const { latitude, longitude, bearing } = p.location;
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
          const key = p.train_number;
          activeKeys.add(key);

          const newTarget = [longitude, latitude];

          const props = {
            trainNumber: p.train_number,
            delaySeconds: p.delay || 0,
            isStopped: p.status === "stopped",
            dataQuality: "good",
            bearing: bearing || 0,
          };

          if (!trainPositionsRef.current[key]) {
            trainPositionsRef.current[key] = {
              current: newTarget,
              target: newTarget,
              startTime: now,
              properties: props,
            };
          } else {
            const old = trainPositionsRef.current[key];
            trainPositionsRef.current[key] = {
              current: old.target,
              target: newTarget,
              startTime: now,
              properties: props,
            };
          }
        });

        Object.keys(trainPositionsRef.current).forEach((key) => {
          if (!activeKeys.has(key)) delete trainPositionsRef.current[key];
        });

        // デバッグ対象列車のデータを抽出
        const debugTarget = debugTrainNumberRef.current.trim().toUpperCase();
        if (debugTarget) {
          const targetTrain = allPositions.find((p) => p.train_number === debugTarget);
          if (targetTrain) {
            setDebugTrainData(targetTrain);
          } else {
            setDebugTrainData({ error: `Train ${debugTarget} not found in current data` });
          }
        } else {
          setDebugTrainData(null);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    };

    fetchAndUpdate();
    intervalId = setInterval(fetchAndUpdate, TRAIN_UPDATE_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, []);

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh" }}>
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          zIndex: 1000,
          background: "rgba(255, 255, 255, 0.95)",
          padding: "15px",
          borderRadius: "8px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          width: "250px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "16px", borderBottom: "2px solid #ddd", paddingBottom: "5px" }}>
          NowTrain コントロール
        </h2>

        <div>
          <label style={{ display: "block", fontSize: "12px", fontWeight: "bold", marginBottom: "4px" }}>
            ?? 路線選択:
          </label>
          <select
            value={selectedLine}
            onChange={(e) => setSelectedLine(e.target.value)}
            style={{ width: "100%", padding: "6px", fontSize: "14px", borderRadius: "4px" }}
          >
            {AVAILABLE_LINES.map((line) => (
              <option key={line.id} value={line.id}>
                {line.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "12px", fontWeight: "bold", marginBottom: "4px" }}>
            ?? 列車番号検索:
          </label>
          <div style={{ display: "flex", gap: "5px" }}>
            <input
              type="text"
              placeholder="例: 1234G"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
              style={{ flex: 1, padding: "4px", borderRadius: "4px", border: "1px solid #ccc" }}
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} style={{ cursor: "pointer" }}>
                ×
              </button>
            )}
          </div>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "12px", fontWeight: "bold", marginBottom: "4px" }}>
            ?? 自動追跡:
          </label>
          <input
            type="text"
            placeholder="追跡する列車番号"
            onChange={(e) => setTrackedTrain(e.target.value.toUpperCase() || null)}
            style={{ width: "100%", padding: "4px", borderRadius: "4px", border: "1px solid #ccc" }}
          />
        </div>

        <div>
          <label style={{ display: "block", fontSize: "12px", fontWeight: "bold", marginBottom: "4px", color: "#9b59b6" }}>
            🔍 デバッグ対象:
          </label>
          <div style={{ display: "flex", gap: "5px" }}>
            <input
              type="text"
              placeholder="例: 1127K"
              value={debugTrainNumber}
              onChange={(e) => setDebugTrainNumber(e.target.value.toUpperCase())}
              style={{ flex: 1, padding: "4px", borderRadius: "4px", border: "1px solid #9b59b6" }}
            />
            {debugTrainNumber && (
              <button onClick={() => setDebugTrainNumber("")} style={{ cursor: "pointer" }}>
                ×
              </button>
            )}
          </div>
        </div>

        <button
          onClick={() => setShowRouteSearch(!showRouteSearch)}
          style={{
            width: "100%",
            padding: "10px",
            borderRadius: "6px",
            border: "none",
            background: showRouteSearch ? "#6c757d" : "#2d9cdb",
            color: "#fff",
            fontSize: "14px",
            fontWeight: "bold",
            cursor: "pointer",
            marginTop: "5px",
          }}
        >
          {showRouteSearch ? "経路検索を閉じる" : "経路検索"}
        </button>
      </div>

      {showRouteSearch && (
        <RouteSearchPanel
          onClose={handleCloseRouteSearch}
          onRouteSelect={handleRouteSelect}
        />
      )}

      <div
        style={{
          position: "absolute",
          right: 10,
          bottom: 10,
          zIndex: 2000,
          background: "rgba(0,0,0,0.85)",
          color: "#fff",
          padding: "10px",
          borderRadius: "8px",
          fontSize: "11px",
          width: "380px",
          maxHeight: "400px",
          overflowY: "auto",
          whiteSpace: "pre-wrap",
          fontFamily: "monospace",
        }}
      >
        {debugTrainData ? (
          <>
            <div style={{ color: "#9b59b6", fontWeight: "bold", marginBottom: "5px" }}>
              🔍 Debug: {debugTrainNumber}
            </div>
            {JSON.stringify(debugTrainData, null, 2)}
          </>
        ) : (
          JSON.stringify(debugHud, null, 2)
        )}
      </div>
      <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}

export default MapView;
