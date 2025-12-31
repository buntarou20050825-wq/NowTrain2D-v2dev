# backend/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import os
import logging
from typing import Any, Dict, List, Optional
from dataclasses import asdict

import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

from data_cache import DataCache
from config import get_line_config  # MS10: 路線設定のインポート

# GTFS解析 & 列車位置計算 (MS11: 汎用化)
try:
    from gtfs_rt_tripupdate import fetch_trip_updates
    from train_position_v4 import compute_all_progress, calculate_coordinates
except ImportError as e:
    logging.warning(f"Module import failed: {e}. V4 API will not work.")
    fetch_trip_updates = None
    compute_all_progress = None
    calculate_coordinates = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")

load_dotenv()

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent.parent  # NowTrain-v2/
DATA_DIR = BASE_DIR / "data"

data_cache = DataCache(DATA_DIR)


# MS11: ID解決用ヘルパー関数
def resolve_line_id(input_id: str) -> str:
    """
    chuo_rapid -> JR-East.ChuoRapid のようにIDを変換する。
    設定がない場合はそのまま返す。
    """
    conf = get_line_config(input_id)
    if conf:
        return conf.mt3d_id
    return input_id


@app.on_event("startup")
async def startup_event():
    data_cache.load_all()
    logger.info(
        "Data loaded: %d railways, %d stations",
        len(data_cache.railways),
        len(data_cache.stations),
    )
    # MS1-TripUpdate: httpx.AsyncClient を作成
    app.state.http_client = httpx.AsyncClient()
    logger.info("httpx.AsyncClient initialized")


@app.on_event("shutdown")
async def shutdown_event():
    # MS1-TripUpdate: httpx.AsyncClient をクローズ
    if hasattr(app.state, "http_client"):
        await app.state.http_client.aclose()
        logger.info("httpx.AsyncClient closed")


# CORS 設定
_default_origins = "http://localhost:5173,http://localhost:5174"  # 5174を追加
_raw_origins = os.getenv("FRONTEND_URL", _default_origins)
frontend_urls = [
    origin.strip()
    for origin in _raw_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_urls,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/lines")
async def get_lines(operator: Optional[str] = None):
    logger.info("GET /api/lines called with operator=%s", operator)

    lines = data_cache.railways

    if operator:
        prefix = operator + "."
        lines = [l for l in lines if l.get("id", "").startswith(prefix)]
        # TODO (MS6): operators.json を使った厳密な事業者フィルタを検討

    def to_line_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
        title = raw.get("title", {})
        station_ids = raw.get("stations", [])
        line_id = raw.get("id", "")
        operator_id = line_id.split(".")[0] if "." in line_id else ""
        return {
            "id": line_id,
            "name_ja": title.get("ja", ""),
            "name_en": title.get("en", ""),
            "color": raw.get("color", "#000000"),
            "operator": operator_id,
            "station_count": len(station_ids),
        }

    return {"lines": [to_line_summary(l) for l in lines]}


@app.get("/api/lines/{line_id}")
async def get_line(line_id: str):
    logger.info("GET /api/lines/%s", line_id)

    # MS11: ID解決
    target_id = resolve_line_id(line_id)

    raw = next((l for l in data_cache.railways if l.get("id") == target_id), None)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Line not found: {line_id} (resolved: {target_id})")
    if not raw:
        raise HTTPException(status_code=404, detail=f"Line not found: {line_id} (resolved: {target_id})")

    title = raw.get("title", {})
    operator_id = target_id.split(".")[0] if "." in target_id else ""

    return {
        "id": raw.get("id"),
        "name_ja": title.get("ja", ""),
        "name_en": title.get("en", ""),
        "color": raw.get("color", "#000000"),
        "operator": operator_id,
        "stations": raw.get("stations", []),
        "ascending": raw.get("ascending"),
        "descending": raw.get("descending"),
        "car_composition": raw.get("carComposition"),  # 元データ camelCase → API では snake_case に揃え済み
    }


@app.get("/api/stations")
async def get_stations(
    lineId: Optional[str] = None, 
    line_id: Optional[str] = None  # エイリアス対応
):
    # 1. パラメータの正規化
    target_param = lineId or line_id
    logger.info(f"GET /api/stations called. Param: {target_param}")

    if target_param is None:
        raise HTTPException(status_code=400, detail="lineId (or line_id) query parameter is required")

    # 2. ID解決
    target_id = resolve_line_id(target_param)
    logger.info(f"Resolving Stations ID: '{target_param}' -> '{target_id}'")

    # 3. データ検索 (FROM DB)
    exists = any(l.get("id") == target_id for l in data_cache.railways)
    if not exists:
        logger.warning(f"Station lookup failed: Line ID '{target_id}' not found in railways.")
        raise HTTPException(status_code=404, detail=f"Line not found: {target_param} -> {target_id}")

    stations = data_cache.get_stations_by_line(target_id)
    logger.info(f"Found {len(stations)} stations for {target_id} (from DB)")

    def to_station(raw: Dict[str, Any]) -> Dict[str, Any]:
        title = raw.get("title", {})
        coord_raw = raw.get("coord")
        lon, lat = None, None
        if isinstance(coord_raw, (list, tuple)) and len(coord_raw) >= 2:
            lon, lat = coord_raw[0], coord_raw[1]

        return {
            "id": raw.get("id"),
            "line_id": raw.get("railway"),
            "name_ja": title.get("ja", ""),
            "name_en": title.get("en", ""),
            "coord": {"lon": lon, "lat": lat},
        }

    return {"stations": [to_station(st) for st in stations]}


# backend/main.py の get_shapes 関数を以下のように書き換えてください

@app.get("/api/shapes")
async def get_shapes(
    lineId: Optional[str] = None,
    line_id: Optional[str] = None  # エイリアス対応
):
    # 1. パラメータの正規化
    target_param = lineId or line_id
    logger.info(f"GET /api/shapes called. Param: {target_param}")

    if target_param is None:
        raise HTTPException(status_code=400, detail="lineId (or line_id) query parameter is required")

    # 2. ID解決
    target_id = resolve_line_id(target_param)
    logger.info(f"Resolving Shape ID: '{target_param}' -> '{target_id}'")

    # 3. Railwaysデータの確認
    exists = any(l.get("id") == target_id for l in data_cache.railways)
    if not exists:
        logger.error(f"Shape lookup failed: ID '{target_id}' not found in railways.")
        raise HTTPException(status_code=404, detail=f"Line not found in railways: {target_id}")

    # 2. Coordinatesデータの検索
    railway_coords = data_cache.coordinates.get("railways", [])
    entry = next((c for c in railway_coords if c.get("id") == target_id), None)
    
    if not entry:
        logger.error(f"Target ID {target_id} not found in coordinates.json")
        # デバッグ: 近いIDがないか探す
        candidates = [c.get("id") for c in railway_coords if "Chuo" in c.get("id", "")]
        logger.info(f"Did you mean one of these? {candidates}")
        raise HTTPException(status_code=404, detail=f"Shape not found in coordinates: {lineId} -> {target_id}")

    # 3. 座標結合処理 (ここが失敗している可能性あり)
    merged_coords: List[List[float]] = []
    previous_end: Optional[List[float]] = None
    sublines = entry.get("sublines", [])
    
    logger.info(f"Found entry for {target_id}, has {len(sublines)} sublines")

    for i, sub in enumerate(sublines):
        coords = sub.get("coords") or []
        if not coords:
            logger.warning(f"Subline {i} has no coords")
            continue

        if previous_end is not None:
            first = coords[0]
            last = coords[-1]

            # 単純な距離計算で反転判定
            dist_to_first = (first[0] - previous_end[0]) ** 2 + (first[1] - previous_end[1]) ** 2
            dist_to_last = (last[0] - previous_end[0]) ** 2 + (last[1] - previous_end[1]) ** 2

            if dist_to_last < dist_to_first:
                coords = list(reversed(coords))

        merged_coords.extend(coords)
        previous_end = coords[-1]

    if not merged_coords:
        logger.error(f"Merged coords empty for {target_id}")
        raise HTTPException(status_code=404, detail=f"Shape coordinates are empty: {lineId}")

    logger.info(f"Successfully merged {len(merged_coords)} points for {target_id}")

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": merged_coords,
        },
        "properties": {
            "line_id": target_id,
            "color": entry.get("color", "#000000"),
            "segment_type": "main",
        },
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
    }

# ▼▼▼ 追加: デバッグ用エンドポイント (ファイルの末尾などに追加) ▼▼▼
@app.get("/api/debug/available_shapes")
async def debug_available_shapes():
    """coordinates.json に含まれる全線路IDを返す"""
    railway_coords = data_cache.coordinates.get("railways", [])
    ids = [c.get("id") for c in railway_coords]
    return {
        "count": len(ids),
        "ids": sorted(ids),
        "chuo_related": [i for i in ids if "Chuo" in i]
    }

@app.get("/api/trains/yamanote/positions")
async def get_yamanote_positions():
    """
    山手線のリアルタイム列車位置を取得
    
    Returns:
        {
            "timestamp": 1760072237,
            "trains": [
                {
                    "tripId": "4201301G",
                    "trainNumber": "301G",
                    "direction": "OuterLoop",
                    "latitude": 35.7204,
                    "longitude": 139.7063,
                    "stopSequence": 11,
                    "status": 1
                },
                ...
            ]
        }
    """
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    
    try:
        from gtfs_rt_vehicle import fetch_yamanote_positions
        positions = await fetch_yamanote_positions(api_key)
        
        return {
            "timestamp": positions[0].timestamp if positions else 0,
            "count": len(positions),
            "trains": [
                {
                    "tripId": p.trip_id,
                    "trainNumber": p.train_number,
                    "direction": p.direction,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "stopSequence": p.stop_sequence,
                    "status": p.status
                }
                for p in positions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/trains/yamanote/positions/v2")
async def get_yamanote_positions_v2():
    """
    山手線のリアルタイム列車位置を取得（出発時刻付き）
    """
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    
    try:
        from gtfs_rt_vehicle import fetch_yamanote_positions_with_schedule
        positions = await fetch_yamanote_positions_with_schedule(api_key)
        
        return {
            "timestamp": positions[0].timestamp if positions else 0,
            "count": len(positions),
            "trains": [
                {
                    "tripId": p.trip_id,
                    "trainNumber": p.train_number,
                    "direction": p.direction,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "stopSequence": p.stop_sequence,
                    "status": p.status,
                    # 新規追加
                    "departureTime": p.departure_time,
                    "nextArrivalTime": p.next_arrival_time,
                    "timestamp": p.timestamp,  # GTFS-RT更新時刻
                }
                for p in positions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 注: v3 エンドポイントは削除されました
# 代わりに /api/trains/{line_id}/positions/v4 を使用してください


# ============================================================================
# MS1-TripUpdate: Debug Endpoint
# ============================================================================

@app.get("/api/debug/trip_updates")
async def debug_trip_updates():
    """
    MS1 TripUpdate デバッグ用エンドポイント。
    TripUpdate の取得結果をサンプルとして返す。
    """
    from gtfs_rt_tripupdate import fetch_trip_updates
    
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="ODPT_API_KEY not set")
    
    try:
        client = app.state.http_client
        schedules = await fetch_trip_updates(client, api_key, data_cache)
        
        # サンプル3件を抽出
        sample_keys = list(schedules.keys())[:3]
        samples = []
        
        for trip_id in sample_keys:
            schedule = schedules[trip_id]
            
            # schedules_by_seq を list形式に変換
            stops_list = []
            for seq in schedule.ordered_sequences:
                stu = schedule.schedules_by_seq.get(seq)
                if stu:
                    stops_list.append({
                        "stop_sequence": stu.stop_sequence,
                        "station_id": stu.station_id,
                        "arrival_time": stu.arrival_time,
                        "departure_time": stu.departure_time,
                        "resolved": stu.resolved,
                        "raw_stop_id": stu.raw_stop_id,
                    })
            
            samples.append({
                "trip_id": schedule.trip_id,
                "train_number": schedule.train_number,
                "start_date": schedule.start_date,
                "direction": schedule.direction,
                "feed_timestamp": schedule.feed_timestamp,
                "stop_count": len(schedule.ordered_sequences),
                "stops": stops_list,
            })
        
        # 統計情報
        total_count = len(schedules)
        resolved_count = 0
        direction_counts = {"InnerLoop": 0, "OuterLoop": 0, "Unknown": 0}
        
        for schedule in schedules.values():
            for stu in schedule.schedules_by_seq.values():
                if stu.resolved:
                    resolved_count += 1
            
            if schedule.direction in direction_counts:
                direction_counts[schedule.direction] += 1
            else:
                direction_counts["Unknown"] += 1
        
        return {
            "status": "success",
            "total_trains": total_count,
            "resolved_station_count": resolved_count,
            "direction_counts": direction_counts,
            "samples": samples,
        }
    
    except Exception as e:
        logger.error(f"Error in debug_trip_updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/gtfs_route_ids")
async def debug_gtfs_route_ids():
    """
    デバッグ用: GTFS-RT フィードに含まれる全 route_id を一覧表示する。
    """
    import httpx
    from google.transit import gtfs_realtime_pb2
    from constants import TRIP_UPDATE_URL
    
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="ODPT_API_KEY not set")
    
    try:
        async with httpx.AsyncClient() as client:
            url = f"{TRIP_UPDATE_URL}?acl:consumerKey={api_key}"
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            # 全 route_id を収集
            route_ids = {}
            for entity in feed.entity:
                if entity.HasField("trip_update"):
                    route_id = entity.trip_update.trip.route_id or "(empty)"
                    trip_id = entity.trip_update.trip.trip_id
                    if route_id not in route_ids:
                        route_ids[route_id] = {"count": 0, "sample_trip_ids": []}
                    route_ids[route_id]["count"] += 1
                    if len(route_ids[route_id]["sample_trip_ids"]) < 3:
                        route_ids[route_id]["sample_trip_ids"].append(trip_id)
            
            return {
                "total_entities": len(feed.entity),
                "unique_route_ids": len(route_ids),
                "route_ids": route_ids,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/gtfs_stop_ids/{line_id}")
async def debug_gtfs_stop_ids(line_id: str):
    """
    デバッグ用: 特定路線のGTFS stop_id をサンプル表示
    """
    from gtfs_rt_tripupdate import fetch_trip_updates
    
    line_config = get_line_config(line_id)
    if not line_config:
        raise HTTPException(status_code=404, detail=f"Line '{line_id}' not found")
    
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="ODPT_API_KEY not set")
    
    try:
        client = app.state.http_client
        schedules = await fetch_trip_updates(
            client,
            api_key,
            data_cache,
            target_route_id=line_config.gtfs_route_id,
            mt3d_prefix=line_config.mt3d_id
        )
        
        samples = []
        for trip_id, schedule in list(schedules.items())[:3]:
            stops = []
            for seq, stu in list(schedule.schedules_by_seq.items())[:5]:
                stops.append({
                    "seq": seq,
                    "station_id": stu.station_id,
                    "raw_stop_id": stu.raw_stop_id,
                    "resolved": stu.resolved,
                })
            samples.append({
                "trip_id": trip_id,
                "train_number": schedule.train_number,
                "stops": stops,
            })
        
        return {
            "line_id": line_id,
            "total_schedules": len(schedules),
            "samples": samples,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MS3: TripUpdate-only v4 API
# ============================================================================

def _get_station_coord(station_id: str | None) -> tuple[float, float] | None:
    """
    駅IDから座標を取得する。
    data_cache.station_positions は (lon, lat) 形式。
    返却は (lat, lon) 形式に変換。
    """
    if not station_id:
        return None
    
    coord = data_cache.station_positions.get(station_id)
    if coord:
        lon, lat = coord
        return (lat, lon)
    return None


def _calculate_position(
    status: str,
    progress: float | None,
    prev_station_id: str | None,
    next_station_id: str | None,
) -> tuple[float | None, float | None]:
    """
    列車の現在座標を計算する。
    
    Returns:
        (latitude, longitude) のタプル。計算不能なら (None, None)。
    """
    # 1) stopped: 停車駅の座標
    if status == "stopped":
        # stopped時は prev_station_id == next_station_id
        coord = _get_station_coord(prev_station_id)
        if coord:
            return coord
        # フォールバック
        coord = _get_station_coord(next_station_id)
        if coord:
            return coord
        return (None, None)
    
    # 2) running: 駅間の線形補間
    if status == "running":
        if progress is None:
            return (None, None)
        
        prev_coord = _get_station_coord(prev_station_id)
        next_coord = _get_station_coord(next_station_id)
        
        if prev_coord is None or next_coord is None:
            # どちらかの座標が取れない
            if prev_coord:
                return prev_coord
            if next_coord:
                return next_coord
            return (None, None)
        
        # 線形補間
        lat0, lon0 = prev_coord
        lat1, lon1 = next_coord
        
        lat = lat0 + (lat1 - lat0) * progress
        lon = lon0 + (lon1 - lon0) * progress
        
        return (lat, lon)
    
    # 3) unknown / invalid: 基本 null
    return (None, None)


@app.get("/api/trains/yamanote/positions/v4")
async def get_yamanote_positions_v4():
    """
    MS3/MS5: TripUpdate-only v4 API エンドポイント。
    
    TripUpdate から列車位置を計算し、線路形状に沿った座標付きで返す。
    """
    from gtfs_rt_tripupdate import fetch_trip_updates
    from train_position_v4 import compute_all_progress, calculate_coordinates
    
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    if not api_key:
        return {
            "source": "tripupdate_v4",
            "status": "error",
            "error": "ODPT_API_KEY not set",
            "timestamp": int(datetime.now(JST).timestamp()),
            "total_trains": 0,
            "positions": [],
        }
    
    try:
        # 1. MS1: TripUpdate取得
        client = app.state.http_client
        schedules = await fetch_trip_updates(client, api_key, data_cache)
        
        if not schedules:
            return {
                "source": "tripupdate_v4",
                "status": "no_data",
                "timestamp": int(datetime.now(JST).timestamp()),
                "total_trains": 0,
                "positions": [],
            }
        
        # 2. MS2: 進捗計算
        results = compute_all_progress(schedules)
        
        # 3. レスポンス構築
        positions = []
        now_ts = None
        
        for r in results:
            # invalid は除外（デバッグには残したい場合は別途）
            if r.status == "invalid":
                continue
            
            # MS5: 座標計算（線路形状追従）
            coord = calculate_coordinates(r, data_cache, "JR-East.Yamanote")
            lat = coord[0] if coord else None
            lon = coord[1] if coord else None
            
            # now_ts を最初の列車から取得
            if now_ts is None:
                now_ts = r.now_ts
            
            positions.append({
                "trip_id": r.trip_id,
                "train_number": r.train_number,
                "direction": r.direction,
                "status": r.status,
                "progress": round(r.progress, 4) if r.progress is not None else None,
                "delay": r.delay,  # MS6: 遅延秒数
                
                "location": {
                    "latitude": round(lat, 6) if lat is not None else None,
                    "longitude": round(lon, 6) if lon is not None else None,
                },
                
                "segment": {
                    "prev_seq": r.prev_seq,
                    "next_seq": r.next_seq,
                    "prev_station_id": r.prev_station_id,
                    "next_station_id": r.next_station_id,
                },
                
                "times": {
                    "now_ts": r.now_ts,
                    "t0_departure": r.t0_departure,
                    "t1_arrival": r.t1_arrival,
                },
                
                "debug": {
                    "feed_timestamp": r.feed_timestamp,
                },
            })
        
        # ソート: direction -> train_number
        positions.sort(key=lambda p: (p["direction"] or "", p["train_number"] or ""))
        
        return {
            "source": "tripupdate_v4",
            "status": "success",
            "timestamp": now_ts or int(datetime.now(JST).timestamp()),
            "total_trains": len(positions),
            "positions": positions,
        }
    
    except Exception as e:
        logger.error(f"Error in v4 endpoint: {e}")
        return {
            "source": "tripupdate_v4",
            "status": "error",
            "error": str(e),
            "timestamp": int(datetime.now(JST).timestamp()),
            "total_trains": 0,
            "positions": [],
        }


# ============================================================================
# MS10: Multi-Line Generic v4 API
# ============================================================================

@app.get("/api/trains/{line_id}/positions/v4")
async def get_train_positions_v4(line_id: str):
    """
    MS10: 汎用路線の列車位置 v4 API。
    
    URLパスパラメータから路線を動的に切り替えて列車位置を取得する。
    
    Args:
        line_id: 路線識別子 ("yamanote", "chuo_rapid", "keihin_tohoku", "sobu_local")
    """
    from gtfs_rt_tripupdate import fetch_trip_updates
    from train_position_v4 import compute_all_progress, calculate_coordinates
    
    # 1. 路線設定のロード
    line_config = get_line_config(line_id)
    if not line_config:
        raise HTTPException(
            status_code=404,
            detail=f"Line '{line_id}' is not supported. "
                   f"Available lines: yamanote, chuo_rapid, keihin_tohoku, sobu_local"
        )
    
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    if not api_key:
        return {
            "source": "tripupdate_v4",
            "line_id": line_id,
            "line_name": line_config.name,
            "status": "error",
            "error": "ODPT_API_KEY not set",
            "timestamp": int(datetime.now(JST).timestamp()),
            "total_trains": 0,
            "positions": [],
        }
    
    try:
        # 2. MS10: target_route_id を指定して TripUpdate 取得
        client = app.state.http_client
        schedules = await fetch_trip_updates(
            client,
            api_key,
            data_cache,
            target_route_id=line_config.gtfs_route_id,  # MS10: 動的に路線を指定
            mt3d_prefix=line_config.mt3d_id  # MS11: 駅IDプレフィックス
        )
        
        if not schedules:
            return {
                "source": "tripupdate_v4",
                "line_id": line_id,
                "line_name": line_config.name,
                "status": "no_data",
                "timestamp": int(datetime.now(JST).timestamp()),
                "total_trains": 0,
                "positions": [],
            }
        
        # 3. MS2: 進捗計算
        results = compute_all_progress(schedules)
        
        # 4. レスポンス構築
        positions = []
        now_ts = None
        
        for r in results:
            if r.status == "invalid":
                continue
            
            # MS5: 座標計算（線路形状追従）
            coord = calculate_coordinates(r, data_cache, line_config.mt3d_id)
            lat = coord[0] if coord else None
            lon = coord[1] if coord else None
            
            if now_ts is None:
                now_ts = r.now_ts
            
            positions.append({
                "trip_id": r.trip_id,
                "train_number": r.train_number,
                "direction": r.direction,
                "status": r.status,
                "progress": round(r.progress, 4) if r.progress is not None else None,
                "delay": r.delay,
                
                "location": {
                    "latitude": round(lat, 6) if lat is not None else None,
                    "longitude": round(lon, 6) if lon is not None else None,
                },
                
                "segment": {
                    "prev_seq": r.prev_seq,
                    "next_seq": r.next_seq,
                    "prev_station_id": r.prev_station_id,
                    "next_station_id": r.next_station_id,
                },
                
                "times": {
                    "now_ts": r.now_ts,
                    "t0_departure": r.t0_departure,
                    "t1_arrival": r.t1_arrival,
                },
                
                "debug": {
                    "feed_timestamp": r.feed_timestamp,
                },
            })
        
        # ソート: direction -> train_number
        positions.sort(key=lambda p: (p["direction"] or "", p["train_number"] or ""))
        
        return {
            "source": "tripupdate_v4",
            "line_id": line_id,
            "line_name": line_config.name,
            "status": "success",
            "timestamp": now_ts or int(datetime.now(JST).timestamp()),
            "total_trains": len(positions),
            "positions": positions,
        }
    
    except Exception as e:
        logger.error(f"Error in generic v4 endpoint for {line_id}: {e}")
        return {
            "source": "tripupdate_v4",
            "line_id": line_id,
            "line_name": line_config.name,
            "status": "error",
            "error": str(e),
            "timestamp": int(datetime.now(JST).timestamp()),
            "total_trains": 0,
            "positions": [],
        }
