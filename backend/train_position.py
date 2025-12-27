# backend/train_position.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, List, Tuple
import logging
import math

if TYPE_CHECKING:
    from data_cache import DataCache

logger = logging.getLogger(__name__)

@dataclass
class TrainPosition:
    """
    列車の「地図上の位置」と付随情報
    """
    train_id: str
    base_id: str
    number: str
    service_type: str
    line_id: str
    direction: str
    is_stopped: bool
    station_id: Optional[str]
    from_station_id: Optional[str]
    to_station_id: Optional[str]
    progress: float
    lon: float
    lat: float
    current_time_sec: int
    is_scheduled: bool = True
    delay_seconds: int = 0
    departure_time: Optional[int] = None
    data_quality: str = "timetable_only"
    gtfs_stop_sequence: Optional[int] = None
    gtfs_status: Optional[int] = None
    timetable_lat: Optional[float] = None
    timetable_lon: Optional[float] = None
    gtfs_lat: Optional[float] = None
    gtfs_lon: Optional[float] = None


def _get_station_coord(station_id: Optional[str], cache: DataCache) -> Optional[tuple[float, float]]:
    if not station_id:
        return None
    return cache.station_positions.get(station_id)


def _get_path_points(
    start_idx: int,
    end_idx: int,
    direction: str,
    track_points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not track_points:
        return []

    # 簡易的な方向判定（環状線対応は呼び出し元で制御するか、ここで詳細化が必要）
    # ここではインデックスの大小で単純に取得する
    if direction in ["OuterLoop", "Outbound", "Descending"]:
        # 順方向
        if start_idx <= end_idx:
            return track_points[start_idx : end_idx + 1]
        else:
            # ラップアラウンド（終点→始点）
            return track_points[start_idx:] + track_points[: end_idx + 1]
    else:
        # 逆方向
        if start_idx >= end_idx:
            if end_idx == 0:
                return track_points[start_idx::-1]
            else:
                return track_points[start_idx : end_idx - 1 : -1]
        else:
            p1 = track_points[start_idx::-1]
            p2 = track_points[: end_idx - 1 : -1] if end_idx > 0 else track_points[::-1]
            return p1 + p2


def _get_point_on_path(path: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    if not path:
        return (0.0, 0.0)
    if len(path) < 2:
        return path[0]
    
    progress = max(0.0, min(1.0, progress))
    if progress == 0.0: return path[0]
    if progress == 1.0: return path[-1]

    distances = []
    total_dist = 0.0
    for i in range(len(path) - 1):
        d = math.hypot(path[i][0] - path[i+1][0], path[i][1] - path[i+1][1])
        distances.append(d)
        total_dist += d

    if total_dist == 0:
        return path[0]

    target_dist = progress * total_dist
    current_dist = 0.0
    
    for i, d in enumerate(distances):
        if current_dist + d >= target_dist:
            ratio = (target_dist - current_dist) / d if d > 0 else 0
            p1 = path[i]
            p2 = path[i+1]
            return (
                p1[0] + (p2[0] - p1[0]) * ratio,
                p1[1] + (p2[1] - p1[1]) * ratio
            )
        current_dist += d
        
    return path[-1]


def _interpolate_coords(
    from_station_id: Optional[str],
    to_station_id: Optional[str],
    progress: float,
    direction: str,
    cache: DataCache,
) -> Optional[tuple[float, float]]:
    """
    駅間補間ロジック（汎用版）
    """
    if not from_station_id or not to_station_id:
        return None

    # 線路データが利用可能かチェック
    use_track_points = (
        cache.track_points 
        and from_station_id in cache.station_track_indices 
        and to_station_id in cache.station_track_indices
    )

    if not use_track_points:
        # 直線補間
        s = _get_station_coord(from_station_id, cache)
        e = _get_station_coord(to_station_id, cache)
        if s and e:
            return (
                s[0] + (e[0] - s[0]) * progress,
                s[1] + (e[1] - s[1]) * progress
            )
        return None

    # 線路形状に沿った補間
    start_idx = cache.station_track_indices[from_station_id]
    end_idx = cache.station_track_indices[to_station_id]
    path = _get_path_points(start_idx, end_idx, direction, cache.track_points)
    return _get_point_on_path(path, progress)


# ============================================================================
# 汎用化された Neighbor Search (GTFS座標マッチング用)
# ============================================================================

def get_line_station_order(line_id: str, cache: DataCache) -> List[str]:
    """DataCacheから指定路線の駅順序リストを取得"""
    # cache.railways はリスト構造と想定
    railway = next((r for r in cache.railways if r.get("id") == line_id), None)
    if railway:
        return railway.get("stations", [])
    return []

def get_adjacent_segments(
    from_station_id: str,
    to_station_id: str,
    direction: str,
    line_id: str,  # ★追加: 路線ID
    cache: DataCache # ★追加
) -> list[tuple[str, str]]:
    """
    指定路線の駅順序に基づいて、前後区間を探索対象として返す
    """
    station_order = get_line_station_order(line_id, cache)
    if not station_order:
        # 駅順が不明なら本来の区間のみ返す
        return [(from_station_id, to_station_id)]
    
    # ID -> Index マップ
    s_idx = {sid: i for i, sid in enumerate(station_order)}
    
    if from_station_id not in s_idx or to_station_id not in s_idx:
        return [(from_station_id, to_station_id)]

    idx_from = s_idx[from_station_id]
    idx_to = s_idx[to_station_id]
    n = len(station_order)
    segments = []

    # 1. 本来の区間
    segments.append((from_station_id, to_station_id))

    # 2. 前後の区間（簡易ロジック: 方向に基づいてインデックスをずらす）
    is_forward = direction in ["OuterLoop", "Outbound", "Descending"]
    
    if is_forward:
        # 前: (idx_from - 1) -> from
        prev_idx = (idx_from - 1 + n) % n
        segments.append((station_order[prev_idx], from_station_id))
        # 次: to -> (idx_to + 1)
        next_idx = (idx_to + 1) % n
        segments.append((to_station_id, station_order[next_idx]))
    else:
        # 逆方向
        # 前: (idx_from + 1) -> from
        prev_idx = (idx_from + 1) % n
        segments.append((station_order[prev_idx], from_station_id))
        # 次: to -> (idx_to - 1)
        next_idx = (idx_to - 1 + n) % n
        segments.append((to_station_id, station_order[next_idx]))

    return segments


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))


def point_to_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return haversine_distance(py, px, ay, ax), ax, ay, 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)
    t = max(0.0, min(1.0, t))
    nx, ny = ax + t*dx, ay + t*dy
    return haversine_distance(py, px, ny, nx), nx, ny, t


def get_segment_coords(from_id: str, to_id: str, direction: str, cache: DataCache) -> Optional[list[list[float]]]:
    # 線路データ取得（変更なし）
    if not cache.track_points: return None
    f_idx = cache.station_track_indices.get(from_id)
    t_idx = cache.station_track_indices.get(to_id)
    if f_idx is None or t_idx is None: return None
    
    path = _get_path_points(f_idx, t_idx, direction, cache.track_points)
    return [[p[0], p[1]] for p in path]


def estimate_segment_progress_extended(segment_coords, target_lat, target_lon, max_dist=500.0):
    if not segment_coords or len(segment_coords) < 2: return None
    
    # 区間全長計算
    dists = [0.0]
    for i in range(len(segment_coords)-1):
        d = haversine_distance(segment_coords[i][1], segment_coords[i][0], 
                               segment_coords[i+1][1], segment_coords[i+1][0])
        dists.append(dists[-1] + d)
    total_len = dists[-1]
    if total_len < 1.0: return None

    min_d = float('inf')
    best_t_global = 0.0
    best_pt = (0,0)

    for i in range(len(segment_coords)-1):
        d, nx, ny, t_local = point_to_segment_distance(
            target_lon, target_lat,
            segment_coords[i][0], segment_coords[i][1],
            segment_coords[i+1][0], segment_coords[i+1][1]
        )
        if d < min_d:
            min_d = d
            best_pt = (nx, ny)
            seg_start_d = dists[i]
            seg_len = dists[i+1] - dists[i]
            best_t_global = (seg_start_d + t_local * seg_len) / total_len

    if min_d > max_dist: return None
    
    return {
        'progress': max(0.0, min(1.0, best_t_global)),
        'distance_m': min_d,
        'lon': best_pt[0],
        'lat': best_pt[1]
    }


def find_train_on_segments(
    gtfs_lat: float,
    gtfs_lon: float,
    from_station_id: str,
    to_station_id: str,
    direction: str,
    line_id: str,      # ★追加
    cache: DataCache,  # ★追加
    max_distance_m: float = 500.0
) -> dict | None:
    """
    汎用化された探索関数
    """
    # 汎用ロジックで探索すべき区間リストを取得
    segments = get_adjacent_segments(from_station_id, to_station_id, direction, line_id, cache)
    
    best_res = None
    best_dist = float('inf')
    
    for idx, (sf, st) in enumerate(segments):
        coords = get_segment_coords(sf, st, direction, cache)
        if not coords: continue
        
        res = estimate_segment_progress_extended(coords, gtfs_lat, gtfs_lon, max_distance_m)
        if res and res['distance_m'] < best_dist:
            best_dist = res['distance_m']
            best_res = {
                'segment': (sf, st),
                'progress': res['progress'],
                'distance_m': res['distance_m'],
                'lon': res['lon'],
                'lat': res['lat'],
                'is_neighbor': (idx > 0) # 0番目以外は隣接区間とみなす
            }
            
    return best_res