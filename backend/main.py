# backend/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import os
import logging
from typing import Any, Dict, List, Optional
from dataclasses import asdict
from pydantic import BaseModel

import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from data_cache import DataCache
from config import get_line_config  # MS10: 路線設定のインポート
from database import SessionLocal, StationRank

# OTP クライアント（経路検索用）
try:
    from otp_client import search_route as otp_search_route, parse_otp_response, extract_trip_ids
except ImportError as e:
    logging.warning(f"OTP client import failed: {e}. Route search will not work.")
    otp_search_route = None
    parse_otp_response = None
    extract_trip_ids = None

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class StationRankUpdate(BaseModel):
    rank: str
    dwell_time: int


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

        station_id = raw.get("id")
        rank_entry = data_cache.station_rank_cache.get(station_id) if station_id else None
        rank = rank_entry.get("rank") if rank_entry else "B"
        dwell_time = rank_entry.get("dwell_time") if rank_entry else data_cache.get_station_dwell_time(station_id)

        return {
            "id": station_id,
            "line_id": raw.get("railway"),
            "name_ja": title.get("ja", ""),
            "name_en": title.get("en", ""),
            "coord": {"lon": lon, "lat": lat},
            "rank": rank,
            "dwell_time": dwell_time,
        }

    return {"stations": [to_station(st) for st in stations]}


@app.get("/api/stations/search")
async def search_stations(
    q: str = Query(..., min_length=1, description="検索キーワード（日本語または英語）"),
    limit: int = Query(10, ge=1, le=50, description="最大件数")
):
    """
    駅名で駅を検索する（部分一致）

    Args:
        q: 検索キーワード
        limit: 最大件数（デフォルト10、最大50）

    Returns:
        マッチした駅のリスト
    """
    logger.info(f"GET /api/stations/search called with q={q}, limit={limit}")

    results = data_cache.search_stations_by_name(q, limit=limit)

    return {
        "query": q,
        "count": len(results),
        "stations": results
    }



@app.put("/api/stations/{station_id}/rank")
async def update_station_rank(
    station_id: str,
    update_data: StationRankUpdate,
    db: Session = Depends(get_db),
):
    if update_data.dwell_time < 0:
        raise HTTPException(status_code=400, detail="dwell_time must be >= 0")
    if update_data.rank not in {"S", "A", "B"}:
        raise HTTPException(status_code=400, detail="rank must be one of: S, A, B")

    rank_obj = db.query(StationRank).filter(StationRank.station_id == station_id).first()

    if not rank_obj:
        rank_obj = StationRank(station_id=station_id)
        db.add(rank_obj)

    rank_obj.rank = update_data.rank
    rank_obj.dwell_time = update_data.dwell_time

    db.commit()
    db.refresh(rank_obj)

    data_cache.station_rank_cache[station_id] = {
        "rank": rank_obj.rank,
        "dwell_time": rank_obj.dwell_time,
    }

    logger.info(
        "Station Rank Updated: %s -> %s (%ds)",
        station_id,
        update_data.rank,
        update_data.dwell_time,
    )

    return {"status": "success", "data": {
        "station_id": rank_obj.station_id,
        "rank": rank_obj.rank,
        "dwell_time": rank_obj.dwell_time,
    }}


# ============================================================
# 線路座標マージ関数 (MS12: sublinesマージロジック改善)
# ============================================================

def build_all_railways_cache(coordinates: Dict) -> Dict[str, List[List[float]]]:
    """
    全路線の座標をキャッシュに格納（Base路線含む）
    type=subの参照解決に使用する。

    Returns:
        { "Base.TabataShinagawa": [[lon, lat], ...], "JR-East.Utsunomiya": [...], ... }
    """
    cache: Dict[str, List[List[float]]] = {}
    for railway in coordinates.get("railways", []):
        railway_id = railway.get("id", "")
        sublines = railway.get("sublines", [])

        # 全sublineの座標を結合
        all_coords: List[List[float]] = []
        for sub in sublines:
            coords = sub.get("coords", [])
            all_coords.extend(coords)

        if all_coords:
            cache[railway_id] = all_coords

    return cache


def resolve_subline_coords(
    subline: Dict,
    all_railways_cache: Dict[str, List[List[float]]]
) -> List[List[float]]:
    """
    sublineの座標を解決する。
    - type=main: subline自身のcoordsを返す
    - type=sub: 参照先の路線の座標を返す（始点・終点で切り出し）

    Args:
        subline: coordinates.jsonのsublineオブジェクト
        all_railways_cache: 全路線の座標キャッシュ

    Returns:
        解決された座標リスト
    """
    subtype = subline.get("type", "main")
    coords = subline.get("coords", [])

    # mainタイプまたは十分な座標がある場合はそのまま返す
    if subtype == "main" or len(coords) > 10:
        return coords

    # subタイプ: 参照先の路線を取得
    start_ref = subline.get("start", {})
    end_ref = subline.get("end", {})
    ref_railway = start_ref.get("railway") or end_ref.get("railway")

    if not ref_railway or ref_railway not in all_railways_cache:
        # 参照先が見つからない場合は元の座標を返す
        return coords

    # 参照先の座標を取得
    ref_coords = all_railways_cache[ref_railway]

    if len(coords) < 2 or len(ref_coords) < 2:
        return coords

    # sublineの始点・終点に最も近い参照座標のインデックスを見つける
    start_point = coords[0]
    end_point = coords[-1]

    def find_nearest_idx(point, coord_list):
        min_dist = float('inf')
        min_idx = 0
        for i, c in enumerate(coord_list):
            dist = (c[0] - point[0])**2 + (c[1] - point[1])**2
            if dist < min_dist:
                min_dist = dist
                min_idx = i
        return min_idx

    start_idx = find_nearest_idx(start_point, ref_coords)
    end_idx = find_nearest_idx(end_point, ref_coords)

    # 範囲を切り出し
    if start_idx <= end_idx:
        return ref_coords[start_idx:end_idx + 1]
    else:
        # 逆方向の場合は反転
        return list(reversed(ref_coords[end_idx:start_idx + 1]))


def merge_sublines_v2(
    sublines: List[Dict],
    is_loop: bool = False,
    all_railways_cache: Optional[Dict[str, List[List[float]]]] = None
) -> List[List[float]]:
    """
    sublinesを正しい順序でマージし、連続した座標配列を返す。
    type=subのsublineは参照先の路線の座標を使用する。

    Args:
        sublines: coordinates.jsonのsublines配列
        is_loop: 環状路線かどうか
        all_railways_cache: 全路線の座標キャッシュ（参照解決用）

    Returns:
        マージされた座標のリスト [[lon, lat], ...]
    """
    if not sublines:
        return []

    if all_railways_cache is None:
        all_railways_cache = {}

    def coord_key(coord):
        """座標を丸めてハッシュ可能なキーに変換"""
        return (round(coord[0], 8), round(coord[1], 8))

    # 1. 各sublineの座標を解決（type=subなら参照先を使用）
    start_coords: Dict[tuple, List[int]] = {}  # coord_key -> [subline_index, ...]
    end_coords: Dict[tuple, List[int]] = {}    # coord_key -> [subline_index, ...]

    valid_sublines: List[tuple] = []
    for i, sub in enumerate(sublines):
        # 参照解決: type=subなら参照先の座標を使用
        coords = resolve_subline_coords(sub, all_railways_cache)
        if len(coords) >= 2:
            valid_sublines.append((i, coords))

            start_key = coord_key(coords[0])
            end_key = coord_key(coords[-1])

            start_coords.setdefault(start_key, []).append(i)
            end_coords.setdefault(end_key, []).append(i)

    if not valid_sublines:
        return []

    # 2. 接続グラフを構築（終点→始点）
    graph: Dict[int, List[int]] = {i: [] for i, _ in valid_sublines}
    in_degree: Dict[int, int] = {i: 0 for i, _ in valid_sublines}

    for i, coords in valid_sublines:
        end_key = coord_key(coords[-1])
        if end_key in start_coords:
            for j in start_coords[end_key]:
                if i != j:
                    graph[i].append(j)
                    in_degree[j] += 1

    # 3. 開始点を決定
    start_idx = None
    if is_loop:
        # 環状路線: 最初のsublineから開始
        start_idx = valid_sublines[0][0]
    else:
        # 非環状路線: 入次数0のsublineから開始
        for i, _ in valid_sublines:
            if in_degree[i] == 0:
                start_idx = i
                break
        if start_idx is None:
            start_idx = valid_sublines[0][0]

    # 4. DFSで順序を決定
    ordered_indices: List[int] = []
    visited: set = set()

    def dfs(idx: int):
        if idx in visited:
            return
        visited.add(idx)
        ordered_indices.append(idx)
        for next_idx in graph[idx]:
            if next_idx not in visited:
                dfs(next_idx)

    dfs(start_idx)

    # 未訪問のsublineも追加（孤立したセグメント対応）
    for i, _ in valid_sublines:
        if i not in visited:
            dfs(i)

    # 5. 座標をマージ（重複除去）
    merged_coords: List[List[float]] = []
    idx_to_coords = {i: coords for i, coords in valid_sublines}

    for i, idx in enumerate(ordered_indices):
        coords = idx_to_coords.get(idx, [])
        if not coords:
            continue

        if i == 0:
            merged_coords.extend(coords)
        else:
            # 重複座標の除去
            if merged_coords and coord_key(coords[0]) == coord_key(merged_coords[-1]):
                merged_coords.extend(coords[1:])
            else:
                merged_coords.extend(coords)

    return merged_coords


def merge_sublines_fallback(sublines: List[Dict]) -> List[List[float]]:
    """
    フォールバック: 距離ベースの貪欲アルゴリズムでsublineを接続する。
    グラフベースのマージが失敗した場合に使用。

    Args:
        sublines: coordinates.jsonのsublines配列

    Returns:
        マージされた座標のリスト [[lon, lat], ...]
    """
    if not sublines:
        return []

    def coord_key(coord):
        return (round(coord[0], 8), round(coord[1], 8))

    def dist_sq(c1, c2):
        return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2

    valid = [(i, sub.get("coords", [])) for i, sub in enumerate(sublines) if sub.get("coords")]
    if not valid:
        return []

    used = [False] * len(valid)
    result: List[List[float]] = []

    # 最初のsublineから開始
    used[0] = True
    coords = valid[0][1]
    result.extend(coords)
    current_end = coords[-1]

    for _ in range(len(valid) - 1):
        best_idx = -1
        best_dist = float('inf')
        best_reversed = False

        for i, (_, coords) in enumerate(valid):
            if used[i] or not coords:
                continue

            d_start = dist_sq(coords[0], current_end)
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reversed = False

            d_end = dist_sq(coords[-1], current_end)
            if d_end < best_dist:
                best_dist = d_end
                best_idx = i
                best_reversed = True

        if best_idx < 0:
            break

        used[best_idx] = True
        coords = valid[best_idx][1]
        if best_reversed:
            coords = list(reversed(coords))

        if result and coord_key(coords[0]) == coord_key(result[-1]):
            result.extend(coords[1:])
        else:
            result.extend(coords)

        current_end = result[-1]

    return result


# ============================================================
# API エンドポイント: 線路形状
# ============================================================

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

    # 3. 座標結合処理 (MS12: グラフベースのマージに改善 + 参照解決)
    sublines = entry.get("sublines", [])
    is_loop = entry.get("loop", False)

    logger.info(f"Found entry for {target_id}, has {len(sublines)} sublines, loop={is_loop}")

    # 参照解決用のキャッシュを構築（全路線の座標）
    all_railways_cache = build_all_railways_cache(data_cache.coordinates)

    # グラフベースのマージを試行（参照解決を含む）
    merged_coords = merge_sublines_v2(sublines, is_loop=is_loop, all_railways_cache=all_railways_cache)

    # フォールバック: グラフベースが失敗した場合
    if not merged_coords:
        logger.warning(f"Graph-based merge failed for {target_id}, trying fallback")
        merged_coords = merge_sublines_fallback(sublines)

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
        results = compute_all_progress(schedules, data_cache=data_cache)
        
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
        # 利用可能な路線一覧を取得
        from config import SUPPORTED_LINES
        available = ", ".join(sorted(SUPPORTED_LINES.keys())[:10]) + "..."
        raise HTTPException(
            status_code=404,
            detail=f"Line '{line_id}' is not supported. "
                   f"Available lines: {available} (51 lines total)"
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
        results = compute_all_progress(schedules, data_cache=data_cache)
        
        # 4. レスポンス構築
        positions = []
        now_ts = None

        # デバッグ: direction 分布の統計
        direction_stats = {}
        status_stats = {}

        for r in results:
            # 統計収集（invalidも含む）
            d = r.direction or "None"
            direction_stats[d] = direction_stats.get(d, 0) + 1
            status_stats[r.status] = status_stats.get(r.status, 0) + 1

            if r.status == "invalid":
                continue

            # MS5: 座標計算（線路形状追従）
            coord = calculate_coordinates(r, data_cache, line_config.mt3d_id)
            lat = coord[0] if coord else None
            lon = coord[1] if coord else None
            bearing = coord[2] if coord and len(coord) > 2 else 0.0

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
                    "bearing": round(bearing, 2) if bearing is not None else 0.0,
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
            # デバッグ情報
            "debug": {
                "direction_stats": direction_stats,
                "status_stats": status_stats,
                "schedules_count": len(schedules),
            },
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


# ============================================================================
# Route Search API (OTP + Train Position Integration)
# ============================================================================

def _identify_line_from_route_id(route_gtfs_id: str) -> Optional[str]:
    """
    OTPの route.gtfsId から路線IDを特定する。

    Args:
        route_gtfs_id: OTPの route.gtfsId (例: "1:11" または "1:JR-East.Yamanote")

    Returns:
        路線ID (例: "yamanote") または None
    """
    # "FeedId:RouteId" 形式から RouteId を抽出
    if ":" in route_gtfs_id:
        route_id = route_gtfs_id.split(":", 1)[1]
    else:
        route_id = route_gtfs_id

    # 既知の路線IDとのマッピング
    # OTPのGTFSデータでは数字IDが使われる場合がある
    route_to_line = {
        # 数字ID形式 (JR東日本GTFSデータ)
        "10": "yamanote",           # 山手線
        "11": "chuo_rapid",         # 中央線快速
        "12": "sobu_local",         # 中央・総武緩行線
        "22": "keihin_tohoku",      # 京浜東北・根岸線
        # フルID形式 (バックアップ)
        "JR-East.Yamanote": "yamanote",
        "JR-East.ChuoRapid": "chuo_rapid",
        "JR-East.KeihinTohokuNegishi": "keihin_tohoku",
        "JR-East.ChuoSobuLocal": "sobu_local",
    }

    return route_to_line.get(route_id)


def _extract_trip_id_suffix(trip_gtfs_id: str) -> str:
    """
    OTPの trip.gtfsId から trip_id サフィックスを抽出する。

    Args:
        trip_gtfs_id: OTPの trip.gtfsId (例: "1:4201301G")

    Returns:
        trip_id (例: "4201301G")
    """
    if ":" in trip_gtfs_id:
        return trip_gtfs_id.split(":", 1)[1]
    return trip_gtfs_id


async def _get_train_positions_for_lines(
    line_ids: List[str],
    client: httpx.AsyncClient,
    api_key: str
) -> Dict[str, Dict]:
    """
    指定された路線の全列車位置を取得し、trip_idでアクセス可能な辞書を返す。

    Returns:
        { "trip_id_suffix": position_dict, ... }
    """
    from gtfs_rt_tripupdate import fetch_trip_updates
    from train_position_v4 import compute_all_progress, calculate_coordinates

    all_positions: Dict[str, Dict] = {}

    for line_id in set(line_ids):  # 重複を除去
        line_config = get_line_config(line_id)
        if not line_config:
            continue

        try:
            schedules = await fetch_trip_updates(
                client,
                api_key,
                data_cache,
                target_route_id=line_config.gtfs_route_id,
                mt3d_prefix=line_config.mt3d_id
            )

            if not schedules:
                continue

            results = compute_all_progress(schedules, data_cache=data_cache)

            for r in results:
                if r.status == "invalid":
                    continue

                coord = calculate_coordinates(r, data_cache, line_config.mt3d_id)
                lat = coord[0] if coord else None
                lon = coord[1] if coord else None

                all_positions[r.trip_id] = {
                    "status": r.status,
                    "latitude": round(lat, 6) if lat is not None else None,
                    "longitude": round(lon, 6) if lon is not None else None,
                    "delay": r.delay,
                    "progress": round(r.progress, 4) if r.progress is not None else None,
                    "segment": {
                        "prev_station_id": r.prev_station_id,
                        "next_station_id": r.next_station_id,
                    }
                }
        except Exception as e:
            logger.error(f"Failed to get positions for {line_id}: {e}")
            continue

    return all_positions


@app.get("/api/route/search")
async def route_search(
    # 座標指定（駅名指定と排他）
    from_lat: Optional[float] = Query(None, description="出発地の緯度"),
    from_lon: Optional[float] = Query(None, description="出発地の経度"),
    to_lat: Optional[float] = Query(None, description="目的地の緯度"),
    to_lon: Optional[float] = Query(None, description="目的地の経度"),
    # 駅名指定（座標指定と排他）
    from_station: Optional[str] = Query(None, description="出発駅名（日本語または英語）"),
    to_station: Optional[str] = Query(None, description="到着駅名（日本語または英語）"),
    # 共通パラメータ
    date: str = Query(..., description="日付 (YYYY-MM-DD)", regex=r"^\d{4}-\d{2}-\d{2}$"),
    time: str = Query(..., description="時刻 (HH:MM)", regex=r"^\d{2}:\d{2}$"),
    arrive_by: bool = Query(False, description="True: 到着時刻指定, False: 出発時刻指定"),
):
    """
    乗換案内検索 + 使用電車の現在位置

    座標または駅名で経路検索を行い、各電車区間について現在位置を付加して返す。

    - 座標指定: from_lat, from_lon, to_lat, to_lon を使用
    - 駅名指定: from_station, to_station を使用
    """
    if otp_search_route is None:
        raise HTTPException(status_code=500, detail="OTP client not available")

    # 駅名から座標を解決
    resolved_from_station = None
    resolved_to_station = None

    if from_station:
        coord = data_cache.get_station_coord_by_name(from_station)
        if coord is None:
            raise HTTPException(
                status_code=400,
                detail=f"出発駅 '{from_station}' が見つかりません"
            )
        from_lat, from_lon = coord
        resolved_from_station = from_station

    if to_station:
        coord = data_cache.get_station_coord_by_name(to_station)
        if coord is None:
            raise HTTPException(
                status_code=400,
                detail=f"到着駅 '{to_station}' が見つかりません"
            )
        to_lat, to_lon = coord
        resolved_to_station = to_station

    # 座標のバリデーション
    if from_lat is None or from_lon is None:
        raise HTTPException(
            status_code=400,
            detail="出発地が指定されていません。from_lat/from_lon または from_station を指定してください"
        )
    if to_lat is None or to_lon is None:
        raise HTTPException(
            status_code=400,
            detail="目的地が指定されていません。to_lat/to_lon または to_station を指定してください"
        )

    api_key = os.getenv("ODPT_API_KEY", "").strip()

    try:
        client = app.state.http_client

        # 1. OTP で経路検索
        otp_response = await otp_search_route(
            client,
            from_lat, from_lon,
            to_lat, to_lon,
            date, time,
            arrive_by
        )

        if "errors" in otp_response:
            return {
                "status": "error",
                "error": otp_response["errors"],
                "query": {
                    "from": {"lat": from_lat, "lon": from_lon},
                    "to": {"lat": to_lat, "lon": to_lon},
                    "date": date,
                    "time": time,
                    "arrive_by": arrive_by
                },
                "itineraries": []
            }

        # 2. OTP レスポンスをパース
        itineraries = parse_otp_response(otp_response)

        if not itineraries:
            return {
                "status": "no_routes",
                "query": {
                    "from": {"lat": from_lat, "lon": from_lon},
                    "to": {"lat": to_lat, "lon": to_lon},
                    "date": date,
                    "time": time,
                    "arrive_by": arrive_by
                },
                "itineraries": []
            }

        # 3. 使用される路線を特定
        transit_modes = {"RAIL", "BUS", "SUBWAY", "TRAM", "FERRY", "CABLE_CAR", "GONDOLA", "FUNICULAR", "TRANSIT"}
        line_ids_needed = set()
        for itin in itineraries:
            for leg in itin.get("legs", []):
                if leg.get("mode") in transit_modes:
                    route_info = leg.get("route", {})
                    if route_info:
                        route_gtfs_id = route_info.get("gtfs_id", "")
                        line_id = _identify_line_from_route_id(route_gtfs_id)
                        if line_id:
                            line_ids_needed.add(line_id)

        # 4. 必要な路線の列車位置を取得
        train_positions = {}
        if api_key and line_ids_needed:
            train_positions = await _get_train_positions_for_lines(
                list(line_ids_needed),
                client,
                api_key
            )

        # 5. 各 leg に現在位置情報を付加
        for itin in itineraries:
            for leg in itin.get("legs", []):
                if leg.get("mode") in transit_modes:
                    trip_gtfs_id = leg.get("trip_id", "")
                    trip_id_suffix = _extract_trip_id_suffix(trip_gtfs_id)

                    position = train_positions.get(trip_id_suffix)
                    if position:
                        leg["current_position"] = position
                    else:
                        leg["current_position"] = None

        # クエリ情報を構築
        query_info = {
            "from": {"lat": from_lat, "lon": from_lon},
            "to": {"lat": to_lat, "lon": to_lon},
            "date": date,
            "time": time,
            "arrive_by": arrive_by
        }
        # 駅名で検索した場合は駅名も含める
        if resolved_from_station:
            query_info["from"]["station"] = resolved_from_station
        if resolved_to_station:
            query_info["to"]["station"] = resolved_to_station

        return {
            "status": "success",
            "query": query_info,
            "itineraries": itineraries
        }

    except Exception as e:
        logger.error(f"Route search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
