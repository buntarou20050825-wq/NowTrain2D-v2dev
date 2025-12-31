# backend/train_position_v4.py
"""
MS2: TripUpdate-only 列車位置計算エンジン

TrainSchedule（MS1の成果物）から現在区間と進捗率を計算する。
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from station_ranks import get_station_dwell_time

from gtfs_rt_tripupdate import TrainSchedule, RealtimeStationSchedule

logger = logging.getLogger(__name__)

# ============================================================================
# MS8: 物理演算ベースの台形速度制御 (E235系)
# ============================================================================

def calculate_physics_progress(elapsed_time: float, total_duration: float) -> float:
    """
    山手線E235系の性能に基づく台形速度制御で進捗率(0.0-1.0)を計算する。
    """
    if total_duration <= 0: return 1.0
    if elapsed_time <= 0: return 0.0
    if elapsed_time >= total_duration: return 1.0
    
    T_ACC = 30.0  # 加速時間 (0->90km/h)
    T_DEC = 25.0  # 減速時間 (90km/h->0)
    
    if total_duration < (T_ACC + T_DEC):
        factor = total_duration / (T_ACC + T_DEC)
        t_acc, t_dec = T_ACC * factor, T_DEC * factor
    else:
        t_acc, t_dec = T_ACC, T_DEC
    
    t_const = total_duration - t_acc - t_dec
    v_peak = 1.0 / (0.5 * t_acc + t_const + 0.5 * t_dec)
    
    if elapsed_time < t_acc:
        return 0.5 * (v_peak / t_acc) * (elapsed_time ** 2)
    elif elapsed_time < (t_acc + t_const):
        dist_acc = 0.5 * v_peak * t_acc
        return dist_acc + v_peak * (elapsed_time - t_acc)
    else:
        time_left = total_duration - elapsed_time
        return 1.0 - 0.5 * (v_peak / t_dec) * (time_left ** 2)



# ============================================================================
# Data Models
# ============================================================================

@dataclass
class SegmentProgress:
    """列車の現在位置・進捗情報"""
    trip_id: str
    train_number: Optional[str]
    direction: Optional[str]
    
    # 現在区間（前駅→次駅）
    prev_station_id: Optional[str]
    next_station_id: Optional[str]
    prev_seq: Optional[int]
    next_seq: Optional[int]
    
    # 時刻と進捗
    now_ts: int
    t0_departure: Optional[int]    # 前駅の発車時刻
    t1_arrival: Optional[int]      # 次駅の到着時刻
    progress: Optional[float]      # 0.0〜1.0（計算不能なら None）
    status: str                    # "running" / "stopped" / "unknown" / "invalid"
    
    # デバッグ用
    feed_timestamp: Optional[int] = None
    segment_count: int = 0         # 全区間数
    delay: int = 0                 # MS6: 遅延秒数


# ============================================================================
# Helper Functions
# ============================================================================

def _extract_station_rank_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    s = str(value)
    if s.isdigit():
        return s
    for sep in (".", ":"):
        if sep in s:
            tail = s.split(sep)[-1]
            if tail.isdigit():
                return tail
    return None


def _get_dwell_seconds(schedule: RealtimeStationSchedule) -> int:
    key = _extract_station_rank_key(schedule.raw_stop_id) or _extract_station_rank_key(schedule.station_id)
    return get_station_dwell_time(key if key is not None else schedule.station_id)


def _get_departure_time(schedule: RealtimeStationSchedule) -> Optional[int]:
    """
    発車時刻を取得する。
    arrival == departure の場合（GTFS時刻表の仕様）は、
    ランクごとの停車時間（station_ranks.py）を加算して返す。
    """
    arr = schedule.arrival_time
    dep = schedule.departure_time

    # 両方ある場合
    if arr is not None and dep is not None:
        # 時刻表上で到着=発車となっている場合、停車時間を足して「実質発車時刻」を作る
        if arr == dep:
            dwell = _get_dwell_seconds(schedule)
            return arr + dwell
        return dep
        
    # departureだけある
    if dep is not None:
        return dep
        
    # arrivalだけある（稀なケース）
    if arr is not None:
        dwell = _get_dwell_seconds(schedule)
        return arr + dwell

    return None

def _is_stopped_at_station(
    schedule: RealtimeStationSchedule,
    now_ts: int,
) -> bool:
    """
    現在時刻がこの駅の到着〜発車の間にあるか判定。
    """
    arr = schedule.arrival_time
    
    # 統一ロジックを使って発車時刻を取得
    effective_dep = _get_departure_time(schedule)
    
    if arr is not None and effective_dep is not None:
        return arr <= now_ts <= effective_dep
    
    return False

def _get_arrival_time(schedule: RealtimeStationSchedule) -> Optional[int]:
    """
    到着時刻を取得する。無ければ発車時刻で代替。
    """
    if schedule.arrival_time is not None:
        return schedule.arrival_time
    return schedule.departure_time


# ============================================================================
# Main Calculation Functions
# ============================================================================

def compute_progress_for_train(
    schedule: TrainSchedule,
    now_ts: Optional[int] = None,
) -> SegmentProgress:
    """
    単一列車の現在位置・進捗を計算する。
    
    Args:
        schedule: TrainSchedule（MS1の出力）
        now_ts: 現在時刻（unix seconds）。None なら time.time() を使用。
    
    Returns:
        SegmentProgress（計算結果）
    """
    # 1. now_ts の決定
    if now_ts is None:
        now_ts = int(time.time())
    
    # feed_timestamp との補正（過去に戻る防止）
    if schedule.feed_timestamp is not None and now_ts < schedule.feed_timestamp:
        now_ts = schedule.feed_timestamp
    
    # 基本情報
    trip_id = schedule.trip_id
    train_number = schedule.train_number
    direction = schedule.direction
    seqs = schedule.ordered_sequences
    schedules_by_seq = schedule.schedules_by_seq
    
    # 2. 無効チェック（区間数が2未満）
    if len(seqs) < 2:
        return SegmentProgress(
            trip_id=trip_id,
            train_number=train_number,
            direction=direction,
            prev_station_id=None,
            next_station_id=None,
            prev_seq=None,
            next_seq=None,
            now_ts=now_ts,
            t0_departure=None,
            t1_arrival=None,
            progress=None,
            status="invalid",
            feed_timestamp=schedule.feed_timestamp,
            segment_count=0,
            delay=0,
        )
    
    # 3. 停車判定（各駅の arrival <= now <= departure をチェック）
    for seq in seqs:
        stu = schedules_by_seq.get(seq)
        if stu and _is_stopped_at_station(stu, now_ts):
            return SegmentProgress(
                trip_id=trip_id,
                train_number=train_number,
                direction=direction,
                prev_station_id=stu.station_id,
                next_station_id=stu.station_id,
                prev_seq=seq,
                next_seq=seq,
                now_ts=now_ts,
                t0_departure=stu.departure_time,
                t1_arrival=stu.arrival_time,
                progress=0.0,  # 停車中は 0.0
                status="stopped",
                feed_timestamp=schedule.feed_timestamp,
                segment_count=len(seqs) - 1,
                delay=stu.delay,  # MS6: 停車中はその駅の遅延
            )
    
    # 4. 区間判定（走行中）
    # ordered_sequences を i=0..len-2 で走査
    for i in range(len(seqs) - 1):
        prev_seq = seqs[i]
        next_seq = seqs[i + 1]
        
        prev_stu = schedules_by_seq.get(prev_seq)
        next_stu = schedules_by_seq.get(next_seq)
        
        if prev_stu is None or next_stu is None:
            continue
        
        # t0 = 前駅の発車時刻、t1 = 次駅の到着時刻
        t0 = _get_departure_time(prev_stu)
        t1 = _get_arrival_time(next_stu)
        
        # 両方存在チェック
        if t0 is None or t1 is None:
            continue
        
        # 無効区間（t1 <= t0）はスキップ
        if t1 <= t0:
            continue
        
        # 現在時刻がこの区間内か判定
        if t0 <= now_ts <= t1:
            # MS8: 物理演算ベースの台形速度制御
            elapsed = now_ts - t0
            duration = t1 - t0
            eased_progress = calculate_physics_progress(elapsed, duration)
            
            return SegmentProgress(
                trip_id=trip_id,
                train_number=train_number,
                direction=direction,
                prev_station_id=prev_stu.station_id,
                next_station_id=next_stu.station_id,
                prev_seq=prev_seq,
                next_seq=next_seq,
                now_ts=now_ts,
                t0_departure=t0,
                t1_arrival=t1,
                progress=eased_progress,  # MS8: 物理演算適用済み
                status="running",
                feed_timestamp=schedule.feed_timestamp,
                segment_count=len(seqs) - 1,
                delay=next_stu.delay,  # MS6: 走行中は次駅到着遅延
            )
    
    # 5. 区間も停車も見つからない → unknown
    # デバッグ用：最初と最後の時刻を記録
    first_stu = schedules_by_seq.get(seqs[0])
    last_stu = schedules_by_seq.get(seqs[-1])
    
    first_time = None
    last_time = None
    
    if first_stu:
        first_time = first_stu.arrival_time or first_stu.departure_time
    if last_stu:
        last_time = last_stu.departure_time or last_stu.arrival_time
    
    return SegmentProgress(
        trip_id=trip_id,
        train_number=train_number,
        direction=direction,
        prev_station_id=first_stu.station_id if first_stu else None,
        next_station_id=last_stu.station_id if last_stu else None,
        prev_seq=seqs[0],
        next_seq=seqs[-1],
        now_ts=now_ts,
        t0_departure=first_time,
        t1_arrival=last_time,
        progress=None,
        status="unknown",
        feed_timestamp=schedule.feed_timestamp,
        segment_count=len(seqs) - 1,
        delay=0,
    )


def compute_all_progress(
    schedules: Dict[str, TrainSchedule],
    now_ts: Optional[int] = None,
) -> List[SegmentProgress]:
    """
    複数列車の現在位置・進捗をまとめて計算する。
    
    Args:
        schedules: {trip_id: TrainSchedule} の辞書（MS1の出力）
        now_ts: 現在時刻（unix seconds）。None なら time.time() を使用。
    
    Returns:
        SegmentProgress のリスト
    """
    # now_ts を統一（全列車で同じ時刻を使う）
    if now_ts is None:
        now_ts = int(time.time())
    
    results: List[SegmentProgress] = []
    
    for trip_id, schedule in schedules.items():
        try:
            progress = compute_progress_for_train(schedule, now_ts)
            results.append(progress)
        except Exception as e:
            logger.error(f"Failed to compute progress for {trip_id}: {e}")
            # エラーでも結果を返す
            results.append(SegmentProgress(
                trip_id=trip_id,
                train_number=schedule.train_number,
                direction=schedule.direction,
                prev_station_id=None,
                next_station_id=None,
                prev_seq=None,
                next_seq=None,
                now_ts=now_ts,
                t0_departure=None,
                t1_arrival=None,
                progress=None,
                status="invalid",
                feed_timestamp=schedule.feed_timestamp,
                segment_count=0,
            ))
    
    return results


# ============================================================================
# Debug/Test Function
# ============================================================================

def debug_progress_stats(results: List[SegmentProgress]) -> Dict[str, int]:
    """
    計算結果の統計を返す（デバッグ用）。
    """
    stats = {
        "running": 0,
        "stopped": 0,
        "unknown": 0,
        "invalid": 0,
        "total": len(results),
    }
    
    for r in results:
        if r.status in stats:
            stats[r.status] += 1
    
    return stats


# ============================================================================
# MS5: Track-Following Coordinate Calculation
# ============================================================================

# ============================================================================
# Helpers for MS3
# ============================================================================
_SHAPE_CACHE: Dict[str, List[tuple[float, float]]] = {}

def get_distance_meters(lat1, lon1, lat2, lon2):
    """Haversine formula"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_merged_coords(cache, line_id) -> List[tuple[float, float]]:
    if line_id in _SHAPE_CACHE:
        return _SHAPE_CACHE[line_id]
    
    merged: List[List[float]] = []
    # coordinates.json content is in cache.coordinates["railways"]
    railways = cache.coordinates.get("railways", [])
    for r in railways:
        if r.get("id") == line_id:
            previous_end = None
            for sl in r.get("sublines", []):
                coords = sl.get("coords") or []
                if not coords:
                    continue

                # Match /api/shapes merge order to keep sublines continuous.
                if previous_end is not None:
                    first = coords[0]
                    last = coords[-1]
                    dist_to_first = (first[0] - previous_end[0]) ** 2 + (first[1] - previous_end[1]) ** 2
                    dist_to_last = (last[0] - previous_end[0]) ** 2 + (last[1] - previous_end[1]) ** 2
                    if dist_to_last < dist_to_first:
                        coords = list(reversed(coords))

                merged.extend(coords)
                previous_end = coords[-1]
            break
            
    # Convert to list of tuples (lon, lat)
    merged_tuples = [(c[0], c[1]) for c in merged]
    
    if merged_tuples:
        _SHAPE_CACHE[line_id] = merged_tuples
        
    return merged_tuples

def _get_station_coord_v4(station_id, cache) -> Optional[tuple[float, float]]:
    # Step 2: Unified accessor (DB-backed)
    # cache.get_station_coord returns (lon, lat)
    if hasattr(cache, "get_station_coord"):
        c = cache.get_station_coord(station_id)
        if c:
             return (c[0], c[1])

    # Fallback to direct access if method missing
    coord = cache.station_positions.get(station_id)
    if coord:
        return (coord[0], coord[1])
    return None

def calculate_coordinates(
    progress_data: SegmentProgress,
    cache: "DataCache",
    line_id: str,
) -> tuple[float, float] | None:
    """
    MS3: SegmentProgress から座標を計算する（線路形状スナップ）。
    
    Args:
        progress_data: SegmentProgress（MS2の出力）
        cache: DataCache インスタンス
        line_id: 路線ID (例: "JR-East.ChuoRapid")
        
    Returns:
        (latitude, longitude) のタプル。計算不能なら None。
    """
    
    status = progress_data.status
    
    # 1) stopped: 停車駅の座標を返す
    if status == "stopped":
        station_id = progress_data.prev_station_id or progress_data.next_station_id
        if station_id:
            coord = _get_station_coord_v4(station_id, cache)
            if coord:
                lon, lat = coord
                return (lat, lon)
        return None
    
    # 2) running: 線路スナップ
    if status == "running":
        progress = progress_data.progress
        prev_station_id = progress_data.prev_station_id
        next_station_id = progress_data.next_station_id
        
        if progress is None or not prev_station_id or not next_station_id:
            return None

        # --- 直線補間 (フォールバック用関数) ---
        def linear_fallback():
            c1 = _get_station_coord_v4(prev_station_id, cache)
            c2 = _get_station_coord_v4(next_station_id, cache)
            if c1 and c2:
                lon1, lat1 = c1
                lon2, lat2 = c2
                lat = lat1 + (lat2 - lat1) * progress
                lon = lon1 + (lon2 - lon1) * progress
                return (lat, lon)
            return None

        try:
            # 線路点群の取得
            coords = get_merged_coords(cache, line_id)
            if not coords:
                return linear_fallback()

            # 前駅・次駅の座標
            s_coord = _get_station_coord_v4(prev_station_id, cache)
            e_coord = _get_station_coord_v4(next_station_id, cache)
            if not s_coord or not e_coord:
                return linear_fallback()

            s_lon, s_lat = s_coord
            e_lon, e_lat = e_coord

            # 最近傍探索 (距離ガード: 500m)
            idx_prev = -1
            min_d_prev = float('inf')
            idx_next = -1
            min_d_next = float('inf')

            # 単純全探索
            for i, (lon, lat) in enumerate(coords):
                d_prev = get_distance_meters(s_lat, s_lon, lat, lon)
                if d_prev < min_d_prev:
                    min_d_prev = d_prev
                    idx_prev = i
                
                d_next = get_distance_meters(e_lat, e_lon, lat, lon)
                if d_next < min_d_next:
                    min_d_next = d_next
                    idx_next = i

            if min_d_prev > 500 or min_d_next > 500:
                # 駅が線路から遠すぎる
                logger.debug(f"Stations too far from rail ({line_id}): {min_d_prev:.1f}m, {min_d_next:.1f}m")
                return linear_fallback()

            if idx_prev == idx_next:
                return linear_fallback()

            # パス切り出し
            if idx_prev < idx_next:
                path = coords[idx_prev : idx_next + 1]
            else:
                path = coords[idx_next : idx_prev + 1][::-1]

            # パス長計算 & 位置特定
            total_dist = 0.0
            dists = [0.0]
            for i in range(len(path) - 1):
                p1 = path[i]
                p2 = path[i+1]
                d = get_distance_meters(p1[1], p1[0], p2[1], p2[0])
                total_dist += d
                dists.append(total_dist)
            
            if total_dist <= 0:
                return linear_fallback()

            target_dist = total_dist * progress

            # target_dist に対応する区間を探す
            found_idx = 0
            for i in range(len(dists) - 1):
                if dists[i] <= target_dist <= dists[i+1]:
                    found_idx = i
                    break
            
            # 区間内補間
            d_start = dists[found_idx]
            d_end = dists[found_idx+1]
            seg_len = d_end - d_start
            
            if seg_len <= 0:
                res_lon, res_lat = path[found_idx]
                return (res_lat, res_lon)

            ratio = (target_dist - d_start) / seg_len
            p_start = path[found_idx]
            p_end = path[found_idx+1]
            
            res_lon = p_start[0] + (p_end[0] - p_start[0]) * ratio
            res_lat = p_start[1] + (p_end[1] - p_start[1]) * ratio
            
            return (res_lat, res_lon)

        except Exception as e:
            logger.debug(f"Snap failed for {line_id}, fallback: {e}")
            return linear_fallback()

    return None
