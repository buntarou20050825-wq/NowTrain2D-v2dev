import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { fetchRailways, fetchStations, fetchCoordinates } from "./api/staticData";
import { fetchLinesFromApi } from "./api/serverData";

const YAMANOTE_ID = "JR-East.Yamanote";
const TRAIN_UPDATE_INTERVAL_MS = 2000;

function App() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (mapRef.current) return;

    mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/streets-v12",
      center: [139.70, 35.68],
      zoom: 11,
    });

    mapRef.current = map;

    map.on("load", async () => {
      // データ読み込み
      const railways = await fetchRailways();
      if (!railways) {
        console.error("Failed to load railways data");
        return;
      }

      const stations = await fetchStations();
      if (!stations) {
        console.error("Failed to load stations data");
        return;
      }

      const coordsData = await fetchCoordinates();
      if (!coordsData) {
        console.error("Failed to load coordinates data");
        return;
      }

      // 山手線データの抽出
      const yamanoteLine = railways.find((r) => r.id === YAMANOTE_ID);
      const yamanoteStationIds = yamanoteLine?.stations || [];

      const yamanoteStations = stations.filter((st) =>
        yamanoteStationIds.includes(st.id)
      );

      // 山手線の座標データを取得
      const railwayCoords = coordsData.railways || [];
      const yamanoteCoordsEntry = railwayCoords.find((c) => c.id === YAMANOTE_ID);

      let yamanoteCoords = [];
      if (yamanoteCoordsEntry && Array.isArray(yamanoteCoordsEntry.sublines)) {
        let previousEnd = null;

        for (const sub of yamanoteCoordsEntry.sublines) {
          if (!Array.isArray(sub.coords) || sub.coords.length === 0) continue;

          let coords = sub.coords;

          // TODO: 簡易的な順序調整
          // - 直前の終端座標(previousEnd)がある場合、
          //   sub.coords[0] と sub.coords[last] のどちらが近いか比較し、
          //   遠い方になっている場合は reverse() する、などの処理を入れられる。
          if (previousEnd) {
            const first = coords[0];
            const last = coords[coords.length - 1];

            const distFirst =
              (first[0] - previousEnd[0]) ** 2 + (first[1] - previousEnd[1]) ** 2;
            const distLast =
              (last[0] - previousEnd[0]) ** 2 + (last[1] - previousEnd[1]) ** 2;

            if (distLast < distFirst) {
              coords = [...coords].reverse();
            }
          }

          yamanoteCoords = yamanoteCoords.concat(coords);
          previousEnd = coords[coords.length - 1];
        }

        // MS1では「見た目がそれっぽければOK」。
        // 将来的にループの完全性や重複座標の整理は別マイルストーンで行う。
      }

      console.log("Yamanote Line:", yamanoteLine);
      console.log("Yamanote Stations:", yamanoteStations.length);
      console.log("Yamanote Coords:", yamanoteCoords.length);

      // GeoJSON の構築
      const yamanoteLineFeature = {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: yamanoteCoords,
        },
        properties: {
          id: YAMANOTE_ID,
          name_ja: yamanoteLine?.title?.ja || "山手線",
          name_en: yamanoteLine?.title?.en || "Yamanote Line",
        },
      };

      const yamanoteStationFeatures = yamanoteStations.map((st) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: st.coord,
        },
        properties: {
          id: st.id,
          railway: st.railway,
          name_ja: st.title?.ja || "",
          name_en: st.title?.en || "",
        },
      }));

      const yamanoteStationsCollection = {
        type: "FeatureCollection",
        features: yamanoteStationFeatures,
      };

      const yamanoteLineCollection = {
        type: "FeatureCollection",
        features: [yamanoteLineFeature],
      };

      // 山手線の線を追加
      map.addSource("yamanote-line", {
        type: "geojson",
        data: yamanoteLineCollection,
      });

      map.addLayer({
        id: "yamanote-line-layer",
        type: "line",
        source: "yamanote-line",
        paint: {
          "line-color": "#80C342", // 山手線の黄緑
          "line-width": 3,
        },
      });

      // 駅を追加
      map.addSource("yamanote-stations", {
        type: "geojson",
        data: yamanoteStationsCollection,
      });

      map.addLayer({
        id: "yamanote-stations-circle",
        type: "circle",
        source: "yamanote-stations",
        paint: {
          "circle-radius": 4,
          "circle-color": "#ffffff",
          "circle-stroke-color": "#000000",
          "circle-stroke-width": 1,
        },
      });

      map.addLayer({
        id: "yamanote-stations-label",
        type: "symbol",
        source: "yamanote-stations",
        layout: {
          "text-field": ["get", "name_ja"],
          "text-size": 10,
          "text-anchor": "top",
          "text-offset": [0, 0.6],
        },
        paint: {
          "text-color": "#000000",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1,
        },
      });

      // 列車マーカー用ソース & レイヤー追加
      if (!map.getSource("yamanote-trains")) {
        map.addSource("yamanote-trains", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: [],
          },
        });

        map.addLayer({
          id: "yamanote-trains-circle",
          type: "circle",
          source: "yamanote-trains",
          paint: {
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              10,
              4,
              14,
              8,
            ],
            "circle-stroke-width": 2,
            "circle-stroke-color": "#ffffff",
            "circle-color": [
              "case",
              ["==", ["get", "is_stopped"], true],
              "#555555",
              "#80C342",
            ],
            "circle-opacity": 0.9,
          },
        });
      }

      // MS2: API の動作確認（描画まで移行するのは MS3 以降）
      const apiData = await fetchLinesFromApi();
      console.log("API /api/lines result:", apiData);
    });



    return () => {
      // map.remove(); // StrictMode対策で削除しない
    };
  }, []);

  // ポーリング用 useEffect
  useEffect(() => {
    let intervalId = null;

    const fetchAndUpdate = async () => {
      const map = mapRef.current;
      if (!map) return;

      const src = map.getSource("yamanote-trains");
      if (!src) return;

      try {
        const res = await fetch("/api/yamanote/positions");
        if (!res.ok) {
          console.error("[yamanote] fetch error:", res.status);
          return;
        }
        const json = await res.json();
        const positions = json.positions || [];

        const features = positions.map((p) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [p.lon, p.lat],
          },
          properties: { ...p },
        }));

        src.setData({
          type: "FeatureCollection",
          features,
        });
        console.log(`[yamanote] Updated ${features.length} trains`);
      } catch (err) {
        console.error("[yamanote] error:", err);
      }
    };

    const startPolling = () => {
      fetchAndUpdate();
      intervalId = setInterval(fetchAndUpdate, TRAIN_UPDATE_INTERVAL_MS);
    };

    const map = mapRef.current;
    if (map) {
      if (map.loaded()) {
        startPolling();
      } else {
        map.on("load", startPolling);
      }
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
      if (map) map.off("load", startPolling);
    };
  }, []);

  return <div ref={mapContainerRef} style={{ width: "100vw", height: "100vh" }} />;
}

export default App;
