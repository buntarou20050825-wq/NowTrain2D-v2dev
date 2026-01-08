"""
GTFS-RT VehiclePosition から山手線の列車位置を取得
"""
import os
import re
import httpx
import asyncio
from google.transit import gtfs_realtime_pb2
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class YamanoteTrainPosition:
    """山手線の列車位置"""
    trip_id: str           # 例: "4201301G"
    train_number: str      # 例: "301G"
    direction: str         # "OuterLoop" or "InnerLoop"
    latitude: float
    longitude: float
    stop_sequence: int
    status: int            # 1=STOPPED_AT, 2=IN_TRANSIT_TO
    timestamp: int


@dataclass
class YamanoteTrainPositionWithSchedule:
    """山手線の列車位置（出発時刻付き）"""
    trip_id: str
    train_number: str
    direction: str
    latitude: float
    longitude: float
    stop_sequence: int
    status: int
    timestamp: int
    # 新規追加
    departure_time: Optional[int] = None  # 現在駅の出発時刻（UNIXタイムスタンプ）
    next_arrival_time: Optional[int] = None  # 次駅の到着時刻


def is_yamanote(trip_id: str) -> bool:
    """山手線かどうか判定"""
    return trip_id.endswith('G')


def identify_route_by_trip_id(trip_id: str) -> str | None:
    """
    trip_idのサフィックスから路線を推定する（後方互換性用）。
    新規コードは identify_routes_by_trip_id() を使用してください。
    """
    routes = identify_routes_by_trip_id(trip_id)
    return routes[0] if routes else None


def identify_routes_by_trip_id(trip_id: str) -> list[str]:
    """
    trip_idのサフィックスから候補となる路線リストを返す。

    ODPT APIのGTFS-RTはroute_idが空で返されるため、
    trip_idの末尾文字から路線を推定する必要がある。
    同じサフィックスが複数路線で使用されるため、リストで返す。

    JR東日本のtrip_id命名規則:
    - G: 山手線
    - H/T: 中央線快速, 横須賀線
    - A/B: 京浜東北線, 中央・総武各駅停車
    - C: 中央・総武各駅停車
    - K: 横浜線, 埼京線
    - F: 南武線, 埼京線, 総武快速線
    - M: 常磐線, 京葉線, 東海道線, 総武本線 等
    - Y: 横須賀線, 京葉線, 東海道線
    - S: 埼京線, 横須賀線
    - E: 武蔵野線, 東海道線
    """
    if not trip_id:
        return []

    suffix = trip_id[-1].upper() if trip_id else ""

    SUFFIX_TO_ROUTES = {
        'G': ["JR-East.Yamanote"],
        'H': ["JR-East.ChuoRapid", "JR-East.Yokosuka"],
        'T': ["JR-East.ChuoRapid"],
        'A': ["JR-East.KeihinTohokuNegishi", "JR-East.ChuoSobuLocal"],
        'B': ["JR-East.KeihinTohokuNegishi", "JR-East.ChuoSobuLocal"],
        'C': ["JR-East.ChuoSobuLocal"],
        'K': ["JR-East.Yokohama", "JR-East.SaikyoKawagoe"],
        'F': ["JR-East.Nambu", "JR-East.SaikyoKawagoe", "JR-East.SobuRapid"],
        'M': ["JR-East.Joban", "JR-East.JobanRapid", "JR-East.SaikyoKawagoe",
              "JR-East.Keiyo", "JR-East.Tokaido", "JR-East.Sobu", "JR-East.SobuRapid"],
        'Y': ["JR-East.Yokosuka", "JR-East.Keiyo", "JR-East.Tokaido", "JR-East.ChuoSobuLocal"],
        'S': ["JR-East.SaikyoKawagoe", "JR-East.Yokosuka"],
        'E': ["JR-East.Musashino", "JR-East.Tokaido"],
    }

    return SUFFIX_TO_ROUTES.get(suffix, [])


def get_direction(trip_id: str, route_id: str = None) -> str:
    """
    方向を取得する。

    NOTE: この関数は山手線専用のプレフィックス判定を含みます。
    他の路線では列車番号の偶奇で判定しますが、これはフォールバックであり
    正確性は保証されません。

    JR東日本の慣例:
    - 奇数=下り（OuterLoop相当）
    - 偶数=上り（InnerLoop相当）
    """
    # 山手線: プレフィックスで判定
    if trip_id.startswith('4201'):
        return 'OuterLoop'
    elif trip_id.startswith('4211'):
        return 'InnerLoop'

    # Fallback: 列車番号の偶奇で判定
    # JR一般路線: 下り=奇数, 上り=偶数
    is_odd = None
    try:
        # trip_id の後半部分から数字を抽出 (例: "4200461G" -> "461")
        # プレフィックス4桁を除いた部分を使用
        suffix = trip_id[4:]
        num_part = ''.join(filter(str.isdigit, suffix))
        if num_part:
            num = int(num_part)
            is_odd = (num % 2 == 1)
    except Exception:
        pass

    if is_odd is None:
        return 'Unknown'

    # route_id がある場合、路線ごとの direction 名にマッピング
    # 静的時刻表データの direction 値に合わせる
    # 奇数=下り(Outbound系), 偶数=上り(Inbound系)
    DIRECTION_MAP = {
        # route_id: (奇数=下り, 偶数=上り)
        "JR-East.Yamanote": ("OuterLoop", "InnerLoop"),
        "JR-East.ChuoRapid": ("Outbound", "Inbound"),
        "JR-East.KeihinTohokuNegishi": ("Southbound", "Northbound"),
        "JR-East.ChuoSobuLocal": ("Westbound", "Eastbound"),
        "JR-East.Yokohama": ("Outbound", "Inbound"),
        "JR-East.SaikyoKawagoe": ("Northbound", "Southbound"),
        "JR-East.Nambu": ("Outbound", "Inbound"),
        "JR-East.Joban": ("Outbound", "Inbound"),
        "JR-East.JobanRapid": ("Outbound", "Inbound"),
        "JR-East.JobanLocal": ("Outbound", "Inbound"),
        "JR-East.Keiyo": ("Outbound", "Inbound"),
        "JR-East.Musashino": ("Outbound", "Inbound"),
        "JR-East.SobuRapid": ("Outbound", "Inbound"),
        "JR-East.Tokaido": ("Outbound", "Inbound"),
        "JR-East.Yokosuka": ("Southbound", "Northbound"),
        "JR-East.Takasaki": ("Outbound", "Inbound"),
        "JR-East.Utsunomiya": ("Outbound", "Inbound"),
        "JR-East.ShonanShinjuku": ("Southbound", "Northbound"),
    }
    
    if route_id and route_id in DIRECTION_MAP:
        outbound, inbound = DIRECTION_MAP[route_id]
        return outbound if is_odd else inbound
    
    # デフォルト
    return 'Outbound' if is_odd else 'Inbound'


def get_train_number(trip_id: str) -> str:
    """
    Trip ID から列車番号を抽出する（正規化対応版）
    
    プレフィックスの長さに依存せず、末尾の「3〜4桁の数字 + 英字」パターンを抽出する。
    これにより "4201103G" から "1103G" を、"4200906G" から "906G" を正しく取得できる。
    
    Args:
        trip_id: GTFS Trip ID (例: "4201301G", "42001103G")
    
    Returns:
        正規化された列車番号 (例: "301G", "1103G")
    """
    # 末尾にある "3〜4桁の数字 + 英字1文字" を検索
    # (\d{3,4}) : 3桁または4桁の数字（山手線の列車番号は3〜4桁）
    # ([A-Z])   : 英字1文字 (G)
    # $         : 末尾
    match = re.search(r'(\d{3,4})([A-Z])$', trip_id)
    
    if match:
        number_part = match.group(1)
        suffix = match.group(2)
        
        # 数値化して先頭の0を削除（例: "0906" -> 906 -> "906"）
        normalized_number = str(int(number_part))
        
        return f"{normalized_number}{suffix}"
    
    # マッチしない場合は、安全策として元の値をそのまま返す
    # (無理にスライスすると情報が壊れる可能性があるため)
    return trip_id


async def fetch_yamanote_positions(api_key: str) -> list[YamanoteTrainPosition]:
    """
    GTFS-RT VehiclePosition から山手線の列車位置を取得
    
    Args:
        api_key: ODPT APIキー
    
    Returns:
        山手線列車位置のリスト
    """
    url = "https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params={"acl:consumerKey": api_key},
            timeout=30.0
        )
        response.raise_for_status()
    
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    
    positions = []
    
    for entity in feed.entity:
        if not entity.HasField('vehicle'):
            continue
        
        vp = entity.vehicle
        trip_id = vp.trip.trip_id
        
        # 山手線フィルタ
        if not is_yamanote(trip_id):
            continue
        
        positions.append(YamanoteTrainPosition(
            trip_id=trip_id,
            train_number=get_train_number(trip_id),
            direction=get_direction(trip_id),
            latitude=vp.position.latitude,
            longitude=vp.position.longitude,
            stop_sequence=vp.current_stop_sequence,
            status=vp.current_status,
            timestamp=vp.timestamp
        ))
    
    return positions


# 同期版（テスト用）
def fetch_yamanote_positions_sync(api_key: str) -> list[YamanoteTrainPosition]:
    """同期版の位置取得"""
    import requests
    
    url = "https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle"
    
    response = requests.get(
        url,
        params={"acl:consumerKey": api_key},
        timeout=30.0
    )
    response.raise_for_status()
    
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    
    positions = []
    
    for entity in feed.entity:
        if not entity.HasField('vehicle'):
            continue
        
        vp = entity.vehicle
        trip_id = vp.trip.trip_id
        
        if not is_yamanote(trip_id):
            continue
        
        positions.append(YamanoteTrainPosition(
            trip_id=trip_id,
            train_number=get_train_number(trip_id),
            direction=get_direction(trip_id),
            latitude=vp.position.latitude,
            longitude=vp.position.longitude,
            stop_sequence=vp.current_stop_sequence,
            status=vp.current_status,
            timestamp=vp.timestamp
        ))
    
    return positions


async def fetch_yamanote_positions_with_schedule(api_key: str) -> list[YamanoteTrainPositionWithSchedule]:
    """
    VehiclePosition と TripUpdate を統合して、出発時刻付きの位置情報を返す
    """
    # 1. VehiclePosition を取得
    vehicle_url = "https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle"
    
    # 2. TripUpdate を取得
    trip_update_url = "https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_trip_update"
    
    async with httpx.AsyncClient() as client:
        vehicle_resp, trip_resp = await asyncio.gather(
            client.get(vehicle_url, params={"acl:consumerKey": api_key}, timeout=30.0),
            client.get(trip_update_url, params={"acl:consumerKey": api_key}, timeout=30.0),
        )
    
    # VehiclePosition をパース
    vehicle_feed = gtfs_realtime_pb2.FeedMessage()
    vehicle_feed.ParseFromString(vehicle_resp.content)
    
    # TripUpdate をパースしてマップ化
    trip_feed = gtfs_realtime_pb2.FeedMessage()
    trip_feed.ParseFromString(trip_resp.content)
    
    # trip_id → {stop_sequence: {arrival, departure}} のマップ
    trip_schedules = {}
    for entity in trip_feed.entity:
        if not entity.HasField('trip_update'):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        if not is_yamanote(trip_id):
            continue
        
        schedules = {}
        for stu in tu.stop_time_update:
            schedules[stu.stop_sequence] = {
                'arrival': stu.arrival.time if stu.HasField('arrival') else None,
                'departure': stu.departure.time if stu.HasField('departure') else None,
            }
        trip_schedules[trip_id] = schedules
    
    # VehiclePosition と TripUpdate を統合
    positions = []
    for entity in vehicle_feed.entity:
        if not entity.HasField('vehicle'):
            continue
        
        vp = entity.vehicle
        trip_id = vp.trip.trip_id
        
        if not is_yamanote(trip_id):
            continue
        
        # TripUpdate から出発時刻を取得
        departure_time = None
        next_arrival_time = None
        if trip_id in trip_schedules:
            current_seq = vp.current_stop_sequence
            if current_seq in trip_schedules[trip_id]:
                departure_time = trip_schedules[trip_id][current_seq].get('departure')
            next_seq = current_seq + 1
            if next_seq in trip_schedules[trip_id]:
                next_arrival_time = trip_schedules[trip_id][next_seq].get('arrival')
        
        positions.append(YamanoteTrainPositionWithSchedule(
            trip_id=trip_id,
            train_number=get_train_number(trip_id),
            direction=get_direction(trip_id),
            latitude=vp.position.latitude,
            longitude=vp.position.longitude,
            stop_sequence=vp.current_stop_sequence,
            status=vp.current_status,
            timestamp=vp.timestamp,
            departure_time=departure_time,
            next_arrival_time=next_arrival_time,
        ))
    
    return positions
