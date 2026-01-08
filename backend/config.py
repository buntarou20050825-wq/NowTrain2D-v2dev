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
    # ===== 既存4路線 =====
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
    # ===== 追加47路線 =====
    # 中央線系統
    "chuo": LineConfig(
        name="中央本線",
        gtfs_route_id="JR-East.Chuo",
        mt3d_id="JR-East.Chuo"
    ),
    "ome": LineConfig(
        name="青梅線",
        gtfs_route_id="JR-East.Ome",
        mt3d_id="JR-East.Ome"
    ),
    "itsukaichi": LineConfig(
        name="五日市線",
        gtfs_route_id="JR-East.Itsukaichi",
        mt3d_id="JR-East.Itsukaichi"
    ),
    # 東海道・横須賀線系統
    "tokaido": LineConfig(
        name="東海道線",
        gtfs_route_id="JR-East.Tokaido",
        mt3d_id="JR-East.Tokaido"
    ),
    "yokosuka": LineConfig(
        name="横須賀線",
        gtfs_route_id="JR-East.Yokosuka",
        mt3d_id="JR-East.Yokosuka"
    ),
    "shonan_shinjuku": LineConfig(
        name="湘南新宿ライン",
        gtfs_route_id="JR-East.ShonanShinjuku",
        mt3d_id="JR-East.ShonanShinjuku"
    ),
    "ito": LineConfig(
        name="伊東線",
        gtfs_route_id="JR-East.Ito",
        mt3d_id="JR-East.Ito"
    ),
    # 宇都宮・高崎線系統
    "utsunomiya": LineConfig(
        name="宇都宮線",
        gtfs_route_id="JR-East.Utsunomiya",
        mt3d_id="JR-East.Utsunomiya"
    ),
    "takasaki": LineConfig(
        name="高崎線",
        gtfs_route_id="JR-East.Takasaki",
        mt3d_id="JR-East.Takasaki"
    ),
    "joetsu": LineConfig(
        name="上越線",
        gtfs_route_id="JR-East.Joetsu",
        mt3d_id="JR-East.Joetsu"
    ),
    "ryomo": LineConfig(
        name="両毛線",
        gtfs_route_id="JR-East.Ryomo",
        mt3d_id="JR-East.Ryomo"
    ),
    "nikko": LineConfig(
        name="日光線",
        gtfs_route_id="JR-East.Nikko",
        mt3d_id="JR-East.Nikko"
    ),
    # 常磐線系統
    "joban": LineConfig(
        name="常磐線",
        gtfs_route_id="JR-East.Joban",
        mt3d_id="JR-East.Joban"
    ),
    "joban_rapid": LineConfig(
        name="常磐線快速",
        gtfs_route_id="JR-East.JobanRapid",
        mt3d_id="JR-East.JobanRapid"
    ),
    "joban_local": LineConfig(
        name="常磐線各駅停車",
        gtfs_route_id="JR-East.JobanLocal",
        mt3d_id="JR-East.JobanLocal"
    ),
    "mito": LineConfig(
        name="水戸線",
        gtfs_route_id="JR-East.Mito",
        mt3d_id="JR-East.Mito"
    ),
    # 総武線系統
    "sobu_rapid": LineConfig(
        name="総武快速線",
        gtfs_route_id="JR-East.SobuRapid",
        mt3d_id="JR-East.SobuRapid"
    ),
    "sobu": LineConfig(
        name="総武本線",
        gtfs_route_id="JR-East.Sobu",
        mt3d_id="JR-East.Sobu"
    ),
    "narita": LineConfig(
        name="成田線",
        gtfs_route_id="JR-East.Narita",
        mt3d_id="JR-East.Narita"
    ),
    "narita_airport": LineConfig(
        name="成田線空港支線",
        gtfs_route_id="JR-East.NaritaAirportBranch",
        mt3d_id="JR-East.NaritaAirportBranch"
    ),
    "narita_abiko": LineConfig(
        name="成田線我孫子支線",
        gtfs_route_id="JR-East.NaritaAbikoBranch",
        mt3d_id="JR-East.NaritaAbikoBranch"
    ),
    "kashima": LineConfig(
        name="鹿島線",
        gtfs_route_id="JR-East.Kashima",
        mt3d_id="JR-East.Kashima"
    ),
    "togane": LineConfig(
        name="東金線",
        gtfs_route_id="JR-East.Togane",
        mt3d_id="JR-East.Togane"
    ),
    # 房総系統
    "uchibo": LineConfig(
        name="内房線",
        gtfs_route_id="JR-East.Uchibo",
        mt3d_id="JR-East.Uchibo"
    ),
    "sotobo": LineConfig(
        name="外房線",
        gtfs_route_id="JR-East.Sotobo",
        mt3d_id="JR-East.Sotobo"
    ),
    "kururi": LineConfig(
        name="久留里線",
        gtfs_route_id="JR-East.Kururi",
        mt3d_id="JR-East.Kururi"
    ),
    # 京葉線系統
    "keiyo": LineConfig(
        name="京葉線",
        gtfs_route_id="JR-East.Keiyo",
        mt3d_id="JR-East.Keiyo"
    ),
    "keiyo_koya": LineConfig(
        name="京葉線高谷支線",
        gtfs_route_id="JR-East.KeiyoKoyaBranch",
        mt3d_id="JR-East.KeiyoKoyaBranch"
    ),
    "keiyo_futamata": LineConfig(
        name="京葉線二俣支線",
        gtfs_route_id="JR-East.KeiyoFutamataBranch",
        mt3d_id="JR-East.KeiyoFutamataBranch"
    ),
    # 埼京線・川越線系統
    "saikyo": LineConfig(
        name="埼京線・川越線",
        gtfs_route_id="JR-East.SaikyoKawagoe",
        mt3d_id="JR-East.SaikyoKawagoe"
    ),
    "kawagoe": LineConfig(
        name="川越線",
        gtfs_route_id="JR-East.Kawagoe",
        mt3d_id="JR-East.Kawagoe"
    ),
    # 武蔵野線系統
    "musashino": LineConfig(
        name="武蔵野線",
        gtfs_route_id="JR-East.Musashino",
        mt3d_id="JR-East.Musashino"
    ),
    "musashino_kunitachi": LineConfig(
        name="武蔵野線国立支線",
        gtfs_route_id="JR-East.MusashinoKunitachiBranch",
        mt3d_id="JR-East.MusashinoKunitachiBranch"
    ),
    "musashino_omiya": LineConfig(
        name="武蔵野線大宮支線",
        gtfs_route_id="JR-East.MusashinoOmiyaBranch",
        mt3d_id="JR-East.MusashinoOmiyaBranch"
    ),
    "musashino_nishiurawa": LineConfig(
        name="武蔵野線西浦和支線",
        gtfs_route_id="JR-East.MusashinoNishiUrawaBranch",
        mt3d_id="JR-East.MusashinoNishiUrawaBranch"
    ),
    # 南武線・鶴見線系統
    "nambu": LineConfig(
        name="南武線",
        gtfs_route_id="JR-East.Nambu",
        mt3d_id="JR-East.Nambu"
    ),
    "nambu_branch": LineConfig(
        name="南武線浜川崎支線",
        gtfs_route_id="JR-East.NambuBranch",
        mt3d_id="JR-East.NambuBranch"
    ),
    "tsurumi": LineConfig(
        name="鶴見線",
        gtfs_route_id="JR-East.Tsurumi",
        mt3d_id="JR-East.Tsurumi"
    ),
    "tsurumi_umishibaura": LineConfig(
        name="鶴見線海芝浦支線",
        gtfs_route_id="JR-East.TsurumiUmiShibauraBranch",
        mt3d_id="JR-East.TsurumiUmiShibauraBranch"
    ),
    "tsurumi_okawa": LineConfig(
        name="鶴見線大川支線",
        gtfs_route_id="JR-East.TsurumiOkawaBranch",
        mt3d_id="JR-East.TsurumiOkawaBranch"
    ),
    # 横浜線・相模線系統
    "yokohama": LineConfig(
        name="横浜線",
        gtfs_route_id="JR-East.Yokohama",
        mt3d_id="JR-East.Yokohama"
    ),
    "sagami": LineConfig(
        name="相模線",
        gtfs_route_id="JR-East.Sagami",
        mt3d_id="JR-East.Sagami"
    ),
    # 八高線
    "hachiko": LineConfig(
        name="八高線",
        gtfs_route_id="JR-East.Hachiko",
        mt3d_id="JR-East.Hachiko"
    ),
    # 相鉄直通
    "sotetsu_direct": LineConfig(
        name="相鉄直通線",
        gtfs_route_id="JR-East.SotetsuDirect",
        mt3d_id="JR-East.SotetsuDirect"
    ),
    # 貨物線・支線
    "yamanote_freight": LineConfig(
        name="山手貨物線",
        gtfs_route_id="JR-East.YamanoteFreight",
        mt3d_id="JR-East.YamanoteFreight"
    ),
    "tokaido_freight": LineConfig(
        name="東海道貨物線",
        gtfs_route_id="JR-East.TokaidoFreight",
        mt3d_id="JR-East.TokaidoFreight"
    ),
    "osaki_branch": LineConfig(
        name="大崎支線",
        gtfs_route_id="JR-East.OsakiBranch",
        mt3d_id="JR-East.OsakiBranch"
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
