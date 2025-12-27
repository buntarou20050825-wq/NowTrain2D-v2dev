# backend/config.py
"""
MS10: 路線定義モジュール

サポートする路線のID定義を管理する。
新しい路線を追加する際は SUPPORTED_LINES に追記する。
"""
from typing import Dict, Optional
from pydantic import BaseModel


class LineConfig(BaseModel):
    """路線ごとの設定"""
    name: str           # 日本語路線名
    gtfs_route_id: str  # GTFS route_id (例: "JR-East.Yamanote")
    mt3d_id: str        # MiniTokyo3D railways.json のキー


# サポートする路線の定義
SUPPORTED_LINES: Dict[str, LineConfig] = {
    "yamanote": LineConfig(
        name="山手線",
        gtfs_route_id="JR-East.Yamanote",
        mt3d_id="JR-East.Yamanote"
    ),
    "chuo_rapid": LineConfig(
        name="中央線快速",
        gtfs_route_id="JR-East.ChuoRapid",
        mt3d_id="JR-East.ChuoRapid"
    ),
    "keihin_tohoku": LineConfig(
        name="京浜東北線・根岸線",
        gtfs_route_id="JR-East.KeihinTohokuNegishi",
        mt3d_id="JR-East.KeihinTohokuNegishi"
    ),
    "sobu_local": LineConfig(
        name="総武線各駅停車",
        gtfs_route_id="JR-East.ChuoSobuLocal",
        mt3d_id="JR-East.ChuoSobuLocal"
    ),
}


def get_line_config(line_id: str) -> Optional[LineConfig]:
    """
    路線IDから設定を取得する。
    
    Args:
        line_id: URL パラメータの路線ID (例: "yamanote", "chuo_rapid")
    
    Returns:
        対応する LineConfig、未サポートの場合は None
    """
    return SUPPORTED_LINES.get(line_id)
