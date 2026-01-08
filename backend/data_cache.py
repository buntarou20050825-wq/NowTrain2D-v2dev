# backend/data_cache.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from timetable_models import StopTime, TimetableTrain
from train_state import TrainSegment, build_yamanote_segments
try:
    from .database import SessionLocal, Station, StationRank
    from .station_ranks import get_station_dwell_time as get_static_dwell_time
except ImportError:
    from database import SessionLocal, Station, StationRank
    from station_ranks import get_station_dwell_time as get_static_dwell_time

logger = logging.getLogger(__name__)


def _is_valid_coord(lon: float, lat: float) -> bool:
    """
    座標が日本付近の妥当な範囲にあるかざっくりチェックする
    """
    return (122.0 <= lon <= 154.0) and (20.0 <= lat <= 46.0)

def _parse_time_to_seconds(time_str: str) -> int:
    """
    "HH:MM" または "HH:MM:SS" 形式の文字列を 0〜86399 の秒に変換する。
    不正な形式の場合は ValueError を発生させる。

    NOTE:
      - 現状は "24:00" や "24:xx" は **不正な形式として扱いエラー** にします。
      - 実データに "24:00" などが含まれている場合は、ログに警告が出て
        該当の stop はスキップされます。
      - TODO(MS3 以降):
        - "24:00" を 00:00 + 24h として解釈するか、
        - 23:59:59 に clamp するか、
        - 仕様として明確に決める必要があります。
    """
    if not time_str:
        raise ValueError("Empty time string")

    parts = time_str.split(":")
    if len(parts) == 2:
        h, m = parts
        s = "0"
    elif len(parts) == 3:
        h, m, s = parts
    else:
        raise ValueError(f"Invalid time format: {time_str} (expected HH:MM or HH:MM:SS)")

    try:
        hour = int(h)
        minute = int(m)
        second = int(s)
    except ValueError as e:
        raise ValueError(f"Invalid time components in '{time_str}': {e}")

    if not (0 <= hour <= 23):
        raise ValueError(f"Invalid hour {hour} in '{time_str}' (must be 0-23)")
    if not (0 <= minute <= 59):
        raise ValueError(f"Invalid minute {minute} in '{time_str}' (must be 0-59)")
    if not (0 <= second <= 59):
        raise ValueError(f"Invalid second {second} in '{time_str}' (must be 0-59)")

    return hour * 3600 + minute * 60 + second


def _normalize_stop_times(raw_tt: List[Dict[str, Any]]) -> List[StopTime]:
    """
    raw_tt: [{"s": station_id, "d": "HH:MM", "a": "HH:MM" 省略可}, ...]
    を StopTime のリストに変換し、
    列車内で時刻が単調増加になるように日跨ぎ（+24h）補正を行う。

    NOTE:
      - 「代表時刻（rep_sec）」として、発車があれば発車、それ以外は到着を使います。
      - 代表時刻が前より小さくなった場合、日付を跨いだとみなして day_offset += 24h。
      - arrival/dep 両方 None の stop は、日跨ぎ判定の起点にはなりません。
        （意図的に「時間情報なしの行は日跨ぎ判定の対象外」としています）
    """
    result: List[StopTime] = []

    day_offset = 0
    prev_rep_sec: int | None = None  # 代表時刻（比較用）

    for i, row in enumerate(raw_tt):
        station_id = row.get("s")
        if not station_id:
            logger.warning("Timetable row %d has no station id 's', skipping", i)
            continue

        dep_str = row.get("d")
        arr_str = row.get("a")

        # 両方とも None の場合は、その駅の時間情報がない → そのまま None で登録
        if dep_str is None and arr_str is None:
            result.append(
                StopTime(
                    station_id=station_id,
                    arrival_sec=None,
                    departure_sec=None,
                )
            )
            # NOTE:
            #   - この stop は rep_sec を持たず、日跨ぎ判定の起点にもなりません。
            continue

        try:
            dep_sec: int | None = _parse_time_to_seconds(dep_str) if dep_str else None
            arr_sec: int | None = _parse_time_to_seconds(arr_str) if arr_str else None
        except ValueError as e:
            logger.warning(
                "[Yamanote timetable] Failed to parse time at stop %d (station %s): %s",
                i,
                station_id,
                e,
            )
            dep_sec = None
            arr_sec = None

        # 代表時刻（比較用）：発車があれば発車、それ以外は到着
        rep_sec: int | None = dep_sec if dep_sec is not None else arr_sec

        # 代表時刻が前より小さい → 日付を跨いだとみなす（+24時間）
        if rep_sec is not None and prev_rep_sec is not None and rep_sec < prev_rep_sec:
            day_offset += 24 * 3600

        if dep_sec is not None:
            dep_sec += day_offset
        if arr_sec is not None:
            arr_sec += day_offset

        if rep_sec is not None:
            prev_rep_sec = rep_sec + day_offset

        result.append(
            StopTime(
                station_id=station_id,
                arrival_sec=arr_sec,
                departure_sec=dep_sec,
            )
        )

    return result


def _validate_train_data(train: TimetableTrain) -> List[str]:
    """
    列車データの簡易妥当性チェック。
    問題があれば warning メッセージのリストを返す。
    """
    warnings: List[str] = []

    # 1. 停車駅数
    if len(train.stops) < 2:
        warnings.append(f"too few stops: {len(train.stops)}")

    # 2. 時刻の単調増加チェック（日跨ぎ補正後）
    prev_sec: int | None = None
    for i, stop in enumerate(train.stops):
        sec = stop.departure_sec if stop.departure_sec is not None else stop.arrival_sec
        if sec is None:
            continue
        if prev_sec is not None and sec < prev_sec:
            warnings.append(f"non-monotonic time at stop index {i} ({stop.station_id})")
            break
        prev_sec = sec

    # 3. 始発駅と最初の stop の一致チェック
    if train.origin_stations and train.stops:
        first_stop_id = train.stops[0].station_id
        if first_stop_id not in train.origin_stations:
            warnings.append(
                f"first stop {first_stop_id} not in origin_stations {train.origin_stations}"
            )

    return warnings


def _parse_yamanote_timetables(raw_data: List[Dict[str, Any]]) -> List[TimetableTrain]:
    """
    jreast-yamanote.json の配列を TimetableTrain リストに変換する。
    不正なデータはスキップし、警告ログを出す。

    NOTE:
      - service_type は id の末尾から推定（例: "Weekday", "Holiday"）。
      - 上記に当てはまらない場合は "Unknown" としてログに警告を出す。
      - destination_stations:
          - ds が存在すれば ds をそのまま使用（複数あれば複数のまま保持）。
          - ds が無い場合は、tt の最後の station_id を終着駅とみなす。
    """
    trains: List[TimetableTrain] = []
    skipped_count = 0

    for idx, row in enumerate(raw_data):
        try:
            full_id: str = row.get("id", "")
            if not full_id:
                logger.warning("Train at index %d has no 'id', skipping", idx)
                skipped_count += 1
                continue

            base_id: str = row.get("t", full_id)
            line_id: str = row.get("r", "")
            number: str = row.get("n", "")
            train_type: str = row.get("y", "")
            direction: str = row.get("d", "")

            # service_type を id の末尾から推定
            service_type = "Unknown"
            if "." in full_id:
                suffix = full_id.split(".")[-1]
                service_type = suffix
                if suffix not in ("Weekday", "Holiday"):
                    logger.info(
                        "Yamanote train %s has non-standard service_type suffix '%s'; "
                        "service_type will be '%s'",
                        full_id,
                        suffix,
                        service_type,
                    )
            else:
                logger.info(
                    "Yamanote train %s has no '.' in id, service_type set to 'Unknown'",
                    full_id,
                )

            origin_stations = row.get("os") or []

            # 終着駅：
            # 1. tt の最後の駅を候補にする
            # 2. ds フィールドがあれば ds を優先（複数あれば複数のまま）
            destination_stations: List[str] = []
            raw_tt = row.get("tt") or []
            if raw_tt:
                last_stop = raw_tt[-1]
                last_station = last_stop.get("s")
                if last_station:
                    destination_stations = [last_station]

            if "ds" in row and row["ds"]:
                # ds が複数ある場合、そのまま複数保持する
                destination_stations = list(row["ds"])

            stops = _normalize_stop_times(raw_tt)

            # 最低限のデータ検証
            if not stops:
                logger.warning("Train %s has no valid stops, skipping", full_id)
                skipped_count += 1
                continue

            train = TimetableTrain(
                base_id=base_id,
                service_type=service_type,
                line_id=line_id,
                number=number,
                train_type=train_type,
                direction=direction,
                origin_stations=origin_stations,
                destination_stations=destination_stations,
                stops=stops,
            )

            # 簡易検証（任意）
            warnings = _validate_train_data(train)
            if warnings:
                logger.warning(
                    "Train %s validation warnings: %s", full_id, "; ".join(warnings)
                )

            trains.append(train)

        except Exception as e:
            logger.error("Failed to parse train at index %d: %s", idx, e)
            skipped_count += 1
            continue

    if skipped_count > 0:
        logger.warning("Skipped %d Yamanote timetable trains due to errors", skipped_count)

    return trains


class DataCache:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.railways: List[Dict[str, Any]] = []
        self.stations: List[Dict[str, Any]] = []
        self.coordinates: Dict[str, Any] = {}

        # MS3-1: 山手線の時刻表（TimetableTrain の配列）
        self.yamanote_trains: List[TimetableTrain] = []

        # MS3-2: 山手線のセグメント（TrainSegment の配列）
        self.yamanote_segments: List[TrainSegment] = []

        # MS3-3: 駅座標インデックス
        self.station_positions: Dict[str, tuple[float, float]] = {}

        # 駅ランクキャッシュ (station_id -> {"rank": str, "dwell_time": int})
        self.station_rank_cache: Dict[str, Dict[str, Any]] = {}

        # MS3-5: 線路形状追従用
        self.track_points: List[tuple[float, float]] = []  # 山手線全周の座標リスト
        self.station_track_indices: Dict[str, int] = {}    # 駅ID → track_pointsのインデックス

        # MS1-TripUpdate: 列車番号から静的列車データへのインデックス
        # key: (train_number, service_type, direction), value: TimetableTrain
        self._train_lookup: Dict[tuple[str, str, str], TimetableTrain] = {}
        # key: (train_number, service_type, direction), value: {stop_sequence: station_id}
        self._seq_to_station_cache: Dict[tuple[str, str, str], Dict[int, str]] = {}

        # 駅名検索用インデックス
        # key: 駅名（日本語/英語）, value: 駅情報のリスト
        self.station_search_index: List[Dict[str, Any]] = []

        # TODO (MS6): パフォーマンス最適化
        # self.railways_by_id: Dict[str, Dict[str, Any]] = {}
        # self.stations_by_id: Dict[str, Dict[str, Any]] = {}

    def _load_json(self, rel_path: str) -> Any:
        path = self.data_dir / rel_path
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def load_all(self) -> None:
        """全ての静的データを読み込む（MS1+MS2+MS3-1 用）"""
        # 1) MS2 までのデータ
        self.railways = self._load_json("mini-tokyo-3d/railways.json")
        # Step 2: Stop loading stations.json
        # self.stations = self._load_json("mini-tokyo-3d/stations.json")
        self.coordinates = self._load_json("mini-tokyo-3d/coordinates.json")

        logger.info("Loaded %d railways", len(self.railways))

        # 2) 複数路線の時刻表をロード
        # JR East の主要路線（ODPT API でサポートされている路線）
        TIMETABLE_FILES = [
            "jreast-yamanote.json",
            "jreast-chuorapid.json",
            "jreast-keihintohokunegishi.json",
            "jreast-chuosobulocal.json",
            "jreast-yokohama.json",
            "jreast-saikyokawagoe.json",
            "jreast-nambu.json",
            "jreast-joban.json",
            "jreast-jobanrapid.json",
            "jreast-jobanlocal.json",
            "jreast-keiyo.json",
            "jreast-musashino.json",
            "jreast-soburapid.json",
            "jreast-tokaido.json",
            "jreast-yokosuka.json",
            "jreast-takasaki.json",
            "jreast-utsunomiya.json",
            "jreast-shonanshinjuku.json",
        ]
        
        self.all_trains: List[TimetableTrain] = []
        total_loaded = 0
        
        for filename in TIMETABLE_FILES:
            try:
                raw_data = self._load_json(f"mini-tokyo-3d/train-timetables/{filename}")
                trains = _parse_yamanote_timetables(raw_data)  # Generic parser
                self.all_trains.extend(trains)
                total_loaded += len(trains)
                logger.info("Loaded %d trains from %s", len(trains), filename)
            except FileNotFoundError:
                logger.warning("Timetable file not found: %s (skipping)", filename)
            except Exception as e:
                logger.error("Failed to load %s: %s", filename, e)
        
        logger.info("Loaded %d total timetable trains from %d files", 
                    total_loaded, len(TIMETABLE_FILES))
        
        # 後方互換性のため yamanote_trains も維持
        self.yamanote_trains = [t for t in self.all_trains if "Yamanote" in t.line_id]
        logger.info("Of which %d are Yamanote trains", len(self.yamanote_trains))
        
        if self.all_trains:
            service_types = {t.service_type for t in self.all_trains}
            logger.info("Service types found: %s", sorted(service_types))

        # MS3-2: 山手線のセグメントを構築
        self.yamanote_segments = build_yamanote_segments(self.yamanote_trains)
        logger.info("Built %d Yamanote train segments", len(self.yamanote_segments))

        # MS1-TripUpdate: 列車検索インデックスを構築 (全路線対象)
        self._build_train_lookup_index()

        # MS3-3: 駅座標インデックスの構築 (DBから)
        self.load_station_positions_from_db()

        # 駅ランクの読み込み (DBから)
        self.load_station_ranks_from_db()

        # 駅名検索インデックスの構築 (DBから)
        self.build_station_search_index()

        # MS3-5: 線路形状データの読み込みと駅マッピング
        self._load_track_coordinates()

        # MS3-3: 山手線時刻表の駅IDが station_positions に存在するか検証
        if not self.yamanote_trains:
            logger.info("Skipping Yamanote station position validation (no timetable data).")
            return

        missing_station_ids: set[str] = set()

        for train in self.yamanote_trains:
            for stop in train.stops:
                if stop.station_id not in self.station_positions:
                    missing_station_ids.add(stop.station_id)

        if missing_station_ids:
            logger.warning(
                "Missing positions for %d station IDs used in Yamanote timetable "
                "(first 10): %s",
                len(missing_station_ids),
                sorted(list(missing_station_ids))[:10],
            )
        else:
            logger.info("All Yamanote timetable station IDs have positions")

    def _load_track_coordinates(self) -> None:
        """
        MS3-5: coordinates.json から山手線の線路座標を読み込み、
        各駅の最寄りインデックスを計算する。
        """
        # 1. coordinates.json をロード（既に load_all で self.coordinates にロード済み）
        if not self.coordinates:
            logger.warning("Coordinates data not loaded, skipping track loading")
            return

        # 2. JR-East.Yamanote の座標データを抽出
        yamanote_coords: List[tuple[float, float]] = []
        railways_coords = self.coordinates.get("railways", [])
        
        target_railway = None
        for r in railways_coords:
            if r.get("id") == "JR-East.Yamanote":
                target_railway = r
                break
        
        if not target_railway:
            logger.warning("JR-East.Yamanote not found in coordinates.json")
            return

        sublines = target_railway.get("sublines", [])
        for subline in sublines:
            coords = subline.get("coords", [])
            # リストのリストになっている場合があるので注意（データ構造依存）
            # coordinates.json の仕様では coords は [[lon, lat], ...]
            for c in coords:
                if len(c) >= 2:
                    yamanote_coords.append((float(c[0]), float(c[1])))

        # 3. 隣接する重複座標を除去
        self.track_points = []
        for coord in yamanote_coords:
            if not self.track_points or self.track_points[-1] != coord:
                self.track_points.append(coord)
        
        logger.info("Loaded %d track points for Yamanote Line", len(self.track_points))

        # 4. 各駅の最寄りインデックスを計算
        self.station_track_indices = {}
        
        # 山手線の駅のみ対象
        yamanote_station_ids = set()
        for train in self.yamanote_trains:
            for stop in train.stops:
                yamanote_station_ids.add(stop.station_id)
        
        mapped_count = 0
        for station_id in yamanote_station_ids:
            coord = self.station_positions.get(station_id)
            if not coord:
                continue
            
            # 最も近い点を探索
            min_dist = float('inf')
            min_idx = 0
            
            for i, track_coord in enumerate(self.track_points):
                # ユークリッド距離の2乗で比較（平方根計算を省略）
                dist_sq = (coord[0] - track_coord[0]) ** 2 + (coord[1] - track_coord[1]) ** 2
                if dist_sq < min_dist:
                    min_dist = dist_sq
                    min_idx = i
            
            self.station_track_indices[station_id] = min_idx
            mapped_count += 1
            
        logger.info("Mapped %d stations to track indices", mapped_count)

    # ========================================================================
    # MS1-TripUpdate: 列車検索・駅マッピングメソッド
    # ========================================================================

    def _build_train_lookup_index(self) -> None:
        """
        列車番号+サービスタイプから TimetableTrain を引けるインデックスを構築する。
        同時に stop_sequence -> station_id のマップもキャッシュする。
        """
        self._train_lookup.clear()
        self._seq_to_station_cache.clear()

        for train in self.all_trains:
            # direction を含めてキーを構築
            key = (train.number, train.service_type, train.direction)
            
            # 同一キーが重複する場合は最初のものを使用
            if key not in self._train_lookup:
                self._train_lookup[key] = train
                
                # stop_sequence -> station_id マップを構築
                # TimetableTrain.stops には stop_sequence がないので、
                # enumerate で 1 始まりの連番を生成する
                seq_map: Dict[int, str] = {}
                for seq, stop in enumerate(train.stops, start=1):
                    seq_map[seq] = stop.station_id
                
                self._seq_to_station_cache[key] = seq_map

        logger.info(
            "Built train lookup index: %d entries, %d seq-to-station maps",
            len(self._train_lookup),
            len(self._seq_to_station_cache)
        )

    def get_static_train(
        self, train_number: str | None, service_type: str | None, direction: str | None = None
    ) -> TimetableTrain | None:
        """
        列車番号から静的時刻表データを検索する。
        
        Args:
            train_number: 列車番号 (例: "301G")
            service_type: サービスタイプ (例: "Weekday", "SaturdayHoliday")
            direction: 方向 (例: "Inbound", "Outbound")
        
        Returns:
            見つかった TimetableTrain、見つからない場合は None
        """
        if not train_number:
            return None
        
        # 1. 完全一致を試す (direction 含む)
        if service_type and direction:
            result = self._train_lookup.get((train_number, service_type, direction))
            if result:
                return result
        
        # 2. フォールバック検索
        for (num, st, d), train in self._train_lookup.items():
            if num == train_number:
                if service_type and st != service_type:
                    continue
                if direction and d != direction:
                    continue
                return train
        
        return None

    def get_seq_to_station_map(
        self, train_number: str | None, service_type: str | None, direction: str | None = None
    ) -> Dict[int, str] | None:
        """
        列車の stop_sequence -> station_id マップを取得する。
        
        Args:
            train_number: 列車番号 (例: "301G")
            service_type: サービスタイプ (例: "Weekday")
            direction: 方向 (例: "Inbound", "Outbound")
        
        Returns:
            {stop_sequence: station_id} のマップ、見つからない場合は None
        """
        if not train_number:
            return None
        
        # 1. 完全一致を試す
        if service_type and direction:
            result = self._seq_to_station_cache.get((train_number, service_type, direction))
            if result:
                return result
        
        # 2. フォールバック検索
        for (num, st, d), seq_map in self._seq_to_station_cache.items():
            if num == train_number:
                if service_type and st != service_type:
                    continue
                if direction and d != direction:
                    continue
                return seq_map
        
        return None

    # ========================================================================
    # MS12: SQLite DB Access
    # ========================================================================
    
    def get_stations_by_line(self, line_id: str) -> List[Dict[str, Any]]:
        """
        DBから特定路線の駅リストを取得する。
        既存のJSON互換形式（dict）で返す。
        StationRankとも結合して、最新のランク情報を付与する。
        """
        # SessionLocal() はリクエストごとに作るのが理想だが、
        # ここでは簡易的にコンテキストマネージャで都度生成・破棄する。
        with SessionLocal() as db:
            # Station と StationRank を左外部結合 (Outer Join)
            rows = (
                db.query(Station, StationRank)
                .outerjoin(StationRank, Station.id == StationRank.station_id)
                .filter(Station.line_id == line_id)
                .all()
            )
            
            result = []
            for s, r in rows:
                station_dict = {
                    "id": s.id,
                    "railway": s.line_id,
                    "title": {"ja": s.name_ja, "en": s.name_en},
                    "coord": [s.lon, s.lat] if s.lon is not None else [],
                    # StationRank の値があれば使い、なければデフォルト
                    "rank": r.rank if r else "B",
                    "dwell_time": r.dwell_time if r else 20,
                }
                result.append(station_dict)
            
            return result

    def get_station_rank_data(self, station_id: str) -> Dict[str, Any] | None:
        """
        DBから駅ランクを取得する。
        """
        with SessionLocal() as db:
            r = db.query(StationRank).filter(StationRank.station_id == station_id).first()
            if not r:
                return None
            return {"rank": r.rank, "dwell_time": r.dwell_time}

    def get_station_dwell_time(self, station_id: str | None) -> int:
        """
        駅IDから停車時間を取得する (DBキャッシュ優先)。
        """
        if not station_id:
            return get_static_dwell_time(station_id)
        cached = self.station_rank_cache.get(station_id)
        if cached:
            return int(cached.get("dwell_time", get_static_dwell_time(station_id)))
        return get_static_dwell_time(station_id)

    def load_station_positions_from_db(self) -> None:
        """DBから駅座標キャッシュを構築する (Step 2)"""
        self.station_positions.clear()
        with SessionLocal() as db:
            # 高速化のため必要なカラムのみ取得
            rows = db.query(Station.id, Station.lon, Station.lat).all()
            for s_id, lon, lat in rows:
                if lon is None or lat is None:
                    continue
                # 簡易チェック
                if not _is_valid_coord(lon, lat):
                    continue
                self.station_positions[s_id] = (lon, lat)
        
        logger.info("Loaded %d station positions from DB", len(self.station_positions))

    def load_station_ranks_from_db(self) -> None:
        """DBから駅ランクキャッシュを構築する"""
        self.station_rank_cache.clear()
        with SessionLocal() as db:
            rows = db.query(StationRank.station_id, StationRank.rank, StationRank.dwell_time).all()
            for station_id, rank, dwell_time in rows:
                if not station_id:
                    continue
                self.station_rank_cache[station_id] = {
                    "rank": rank,
                    "dwell_time": int(dwell_time),
                }
        logger.info("Loaded %d station ranks from DB", len(self.station_rank_cache))

    def build_station_search_index(self) -> None:
        """
        駅名検索用インデックスを構築する。
        DBから全駅情報を取得し、検索に使いやすい形式でキャッシュする。
        """
        self.station_search_index.clear()

        with SessionLocal() as db:
            rows = db.query(
                Station.id,
                Station.line_id,
                Station.name_ja,
                Station.name_en,
                Station.lon,
                Station.lat
            ).all()

            # 同じ駅名で複数路線がある場合をグループ化
            station_by_name: Dict[str, Dict[str, Any]] = {}

            for s_id, line_id, name_ja, name_en, lon, lat in rows:
                if lon is None or lat is None:
                    continue
                if not _is_valid_coord(lon, lat):
                    continue

                # 駅名をキーにグループ化（同じ駅でも路線が違う場合がある）
                key = name_ja or name_en or s_id
                if key not in station_by_name:
                    station_by_name[key] = {
                        "id": s_id,
                        "name_ja": name_ja or "",
                        "name_en": name_en or "",
                        "coord": {"lon": lon, "lat": lat},
                        "lines": [line_id] if line_id else [],
                    }
                else:
                    # 同じ駅名で別路線がある場合、路線リストに追加
                    if line_id and line_id not in station_by_name[key]["lines"]:
                        station_by_name[key]["lines"].append(line_id)

            # リスト形式に変換
            self.station_search_index = list(station_by_name.values())

        logger.info("Built station search index with %d stations", len(self.station_search_index))

    def search_stations_by_name(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        駅名で駅を検索する（部分一致）。

        Args:
            query: 検索キーワード（日本語または英語）
            limit: 最大件数

        Returns:
            マッチした駅のリスト
        """
        if not query:
            return []

        query_lower = query.lower()
        results = []

        for station in self.station_search_index:
            name_ja = station.get("name_ja", "")
            name_en = station.get("name_en", "")

            # 完全一致を優先、次に部分一致
            if name_ja == query or name_en.lower() == query_lower:
                results.insert(0, station)  # 完全一致は先頭に
            elif query in name_ja or query_lower in name_en.lower():
                results.append(station)

            if len(results) >= limit:
                break

        return results[:limit]

    def get_station_coord_by_name(self, name: str) -> tuple[float, float] | None:
        """
        駅名から座標を取得する。

        Args:
            name: 駅名（日本語または英語）

        Returns:
            (lat, lon) タプル。見つからない場合は None。
        """
        results = self.search_stations_by_name(name, limit=1)
        if results:
            coord = results[0].get("coord", {})
            lat = coord.get("lat")
            lon = coord.get("lon")
            if lat is not None and lon is not None:
                return (lat, lon)
        return None

    def get_station_coord(self, station_id: str) -> tuple[float, float] | None:
        """
        駅座標を取得する (Unified Accessor)
        """
        return self.station_positions.get(station_id)

    def update_station_rank(self, station_id: str, rank: str, dwell_time: int) -> None:
        """
        駅ランク情報を更新する (Upsert)
        """
        with SessionLocal() as db:
            # 既に存在するか確認
            existing = db.query(StationRank).filter(StationRank.station_id == station_id).first()
            if existing:
                existing.rank = rank
                existing.dwell_time = dwell_time
            else:
                new_rank = StationRank(station_id=station_id, rank=rank, dwell_time=dwell_time)
                db.add(new_rank)
            
            db.commit()
            logger.info(f"Updated station rank for {station_id}: rank={rank}, dwell={dwell_time}")

        self.station_rank_cache[station_id] = {
            "rank": rank,
            "dwell_time": int(dwell_time),
        }
