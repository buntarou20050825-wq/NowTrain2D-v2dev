# backend/otp_client.py
"""
OpenTripPlanner GraphQL API クライアント

OTP 2.x では REST API が廃止され、GraphQL API のみ使用可能。
エンドポイント: http://localhost:8080/otp/routers/default/index/graphql
"""
from __future__ import annotations

import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# OTP GraphQL エンドポイント
OTP_GRAPHQL_ENDPOINT = "http://localhost:8080/otp/routers/default/index/graphql"

# 経路検索用 GraphQL クエリ
PLAN_QUERY = """
query PlanRoute($fromLat: Float!, $fromLon: Float!, $toLat: Float!, $toLon: Float!, $date: String!, $time: String!, $arriveBy: Boolean!) {
  plan(
    from: {lat: $fromLat, lon: $fromLon}
    to: {lat: $toLat, lon: $toLon}
    date: $date
    time: $time
    arriveBy: $arriveBy
    numItineraries: 5
    transportModes: [{mode: WALK}, {mode: TRANSIT}]
  ) {
    itineraries {
      startTime
      endTime
      duration
      legs {
        mode
        startTime
        endTime
        duration
        distance
        route {
          gtfsId
          shortName
          longName
        }
        trip {
          gtfsId
        }
        from {
          name
          lat
          lon
          stop {
            gtfsId
          }
        }
        to {
          name
          lat
          lon
          stop {
            gtfsId
          }
        }
        intermediateStops {
          name
          lat
          lon
          gtfsId
        }
      }
    }
  }
}
"""


async def search_route(
    client: httpx.AsyncClient,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    date: str,  # YYYY-MM-DD
    time: str,  # HH:MM
    arrive_by: bool = False
) -> Dict[str, Any]:
    """
    OTP GraphQL API で経路検索を実行

    Args:
        client: httpx.AsyncClient インスタンス
        from_lat: 出発地の緯度
        from_lon: 出発地の経度
        to_lat: 目的地の緯度
        to_lon: 目的地の経度
        date: 日付 (YYYY-MM-DD 形式)
        time: 時刻 (HH:MM 形式)
        arrive_by: True の場合は到着時刻指定、False の場合は出発時刻指定

    Returns:
        経路検索結果 (OTP の生レスポンス)
    """
    variables = {
        "fromLat": from_lat,
        "fromLon": from_lon,
        "toLat": to_lat,
        "toLon": to_lon,
        "date": date,
        "time": time,
        "arriveBy": arrive_by
    }

    payload = {
        "query": PLAN_QUERY,
        "variables": variables
    }

    try:
        response = await client.post(
            OTP_GRAPHQL_ENDPOINT,
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        logger.error("OTP request timed out")
        return {"errors": [{"message": "OTP request timed out"}]}
    except httpx.HTTPStatusError as e:
        logger.error(f"OTP HTTP error: {e.response.status_code}")
        return {"errors": [{"message": f"OTP HTTP error: {e.response.status_code}"}]}
    except Exception as e:
        logger.error(f"OTP request failed: {e}")
        return {"errors": [{"message": str(e)}]}


def parse_otp_response(otp_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    OTP GraphQL レスポンスを解析し、経路情報を抽出

    Args:
        otp_response: OTP からの生レスポンス

    Returns:
        パース済みの経路リスト
    """
    if "errors" in otp_response:
        logger.error(f"OTP returned errors: {otp_response['errors']}")
        return []

    data = otp_response.get("data", {})
    plan = data.get("plan", {})
    itineraries = plan.get("itineraries", [])

    results = []
    for itin in itineraries:
        # Unix ミリ秒をISO形式に変換
        start_time = _ms_to_iso(itin.get("startTime"))
        end_time = _ms_to_iso(itin.get("endTime"))
        duration_seconds = itin.get("duration", 0)

        legs = []
        for leg in itin.get("legs", []):
            parsed_leg = _parse_leg(leg)
            legs.append(parsed_leg)

        results.append({
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": duration_seconds // 60,
            "legs": legs
        })

    return results


def _ms_to_iso(ms: Optional[int]) -> Optional[str]:
    """Unix ミリ秒を ISO 8601 形式に変換"""
    if ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(ms / 1000)
        return dt.isoformat()
    except Exception:
        return None


def _parse_leg(leg: Dict[str, Any]) -> Dict[str, Any]:
    """
    経路の1区間 (leg) をパースする
    """
    mode = leg.get("mode", "")
    start_time = _ms_to_iso(leg.get("startTime"))
    end_time = _ms_to_iso(leg.get("endTime"))
    duration_seconds = leg.get("duration", 0)

    from_place = leg.get("from", {})
    to_place = leg.get("to", {})

    parsed = {
        "mode": mode,
        "start_time": start_time,
        "end_time": end_time,
        "duration_minutes": duration_seconds // 60,
        "from": {
            "name": from_place.get("name", ""),
            "lat": from_place.get("lat"),
            "lon": from_place.get("lon"),
            "stop_id": _extract_stop_id(from_place)
        },
        "to": {
            "name": to_place.get("name", ""),
            "lat": to_place.get("lat"),
            "lon": to_place.get("lon"),
            "stop_id": _extract_stop_id(to_place)
        }
    }

    # 公共交通機関モードの場合、路線・列車情報を追加
    # OTPは RAIL, BUS, SUBWAY, TRAM 等の具体的なモードを返す
    transit_modes = {"RAIL", "BUS", "SUBWAY", "TRAM", "FERRY", "CABLE_CAR", "GONDOLA", "FUNICULAR", "TRANSIT"}
    if mode in transit_modes:
        route = leg.get("route", {}) or {}
        trip = leg.get("trip", {}) or {}

        parsed["route"] = {
            "gtfs_id": route.get("gtfsId", ""),
            "short_name": route.get("shortName", ""),
            "long_name": route.get("longName", "")
        }
        parsed["trip_id"] = trip.get("gtfsId", "") if trip else ""

        # 中間駅
        intermediate = leg.get("intermediateStops", [])
        parsed["intermediate_stops"] = [
            {
                "name": stop.get("name", ""),
                "lat": stop.get("lat"),
                "lon": stop.get("lon"),
                "gtfs_id": stop.get("gtfsId", "")
            }
            for stop in intermediate
        ]

    return parsed


def _extract_stop_id(place: Dict[str, Any]) -> Optional[str]:
    """停留所のGTFS IDを抽出"""
    stop = place.get("stop")
    if stop:
        return stop.get("gtfsId")
    return None


def extract_trip_ids(itineraries: List[Dict[str, Any]]) -> List[str]:
    """
    経路検索結果から全ての trip_id を抽出

    Args:
        itineraries: parse_otp_response() の戻り値

    Returns:
        trip_id のリスト (重複なし)
    """
    trip_ids = set()
    for itin in itineraries:
        for leg in itin.get("legs", []):
            trip_id = leg.get("trip_id")
            if trip_id:
                trip_ids.add(trip_id)
    return list(trip_ids)
