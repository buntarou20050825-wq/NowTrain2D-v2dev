# backend/station_ranks.py

# 駅ランクごとの停車時間定義（秒）
# キーは Mini Tokyo 3D の stations.json の id です。
# S: 巨大ターミナル (50秒)
# A: 主要駅 (35秒)
# B: 一般駅 (20秒) - デフォルト

STATION_RANKS = {
    # ==========================================
    # 山手線 (Yamanote Line)
    # ==========================================
    "JR-East.Yamanote.Shinjuku": 50,  # 新宿 (JY17) - Sランク
    "JR-East.Yamanote.Tokyo": 50,  # 東京 (JY01) - Sランク
    "JR-East.Yamanote.Shibuya": 50,  # 渋谷 (JY20) - Sランク
    "JR-East.Yamanote.Ikebukuro": 50,  # 池袋 (JY13) - Sランク
    "JR-East.Yamanote.Shinagawa": 35,  # 品川 (JY25) - Aランク
    "JR-East.Yamanote.Ueno": 35,  # 上野 (JY05) - Aランク
    "JR-East.Yamanote.Akihabara": 35,  # 秋葉原 (JY03) - Aランク
    "JR-East.Yamanote.Yurakucho": 35,  # 有楽町 (JY30) - Aランク
    "JR-East.Yamanote.Shimbashi": 35,  # 新橋 (JY29) - Aランク
    "JR-East.Yamanote.Hamamatsucho": 35,  # 浜松町 (JY28) - Aランク
    "JR-East.Yamanote.Tamachi": 35,  # 田町 (JY27) - Aランク
    "JR-East.Yamanote.Osaki": 35,  # 大崎 (JY24) - Aランク
    "JR-East.Yamanote.Gotanda": 35,  # 五反田 (JY23) - Aランク
    "JR-East.Yamanote.Meguro": 35,  # 目黒 (JY22) - Aランク
    "JR-East.Yamanote.Ebisu": 35,  # 恵比寿 (JY21) - Aランク
    "JR-East.Yamanote.Harajuku": 35,  # 原宿 (JY19) - Aランク
    "JR-East.Yamanote.Yoyogi": 35,  # 代々木 (JY18) - Aランク
    "JR-East.Yamanote.Takadanobaba": 35,  # 高田馬場 (JY15) - Aランク
    "JR-East.Yamanote.Sugamo": 35,  # 巣鴨 (JY11) - Aランク
    "JR-East.Yamanote.Komagome": 35,  # 駒込 (JY10) - Aランク
    "JR-East.Yamanote.NishiNippori": 35,  # 西日暮里 (JY08) - Aランク
    "JR-East.Yamanote.Nippori": 35,  # 日暮里 (JY07) - Aランク
    "JR-East.Yamanote.Okachimachi": 35,  # 御徒町 (JY04) - Aランク
    "JR-East.Yamanote.Kanda": 35,  # 神田 (JY02) - Aランク

    # ==========================================
    # 中央線快速 (Chuo Rapid)
    # ==========================================
    "JR-East.ChuoRapid.Tokyo": 50,  # 東京 (JC01)
    "JR-East.ChuoRapid.Shinjuku": 50,  # 新宿 (JC05)
    "JR-East.ChuoRapid.Kanda": 35,  # 神田 (JC02)
    "JR-East.ChuoRapid.Ochanomizu": 35,  # 御茶ノ水 (JC03)
    "JR-East.ChuoRapid.Yotsuya": 35,  # 四ツ谷 (JC04)
    "JR-East.ChuoRapid.Nakano": 35,  # 中野 (JC06)
    "JR-East.ChuoRapid.Kichijoji": 35,  # 吉祥寺 (JC11)
    "JR-East.ChuoRapid.Mitaka": 35,  # 三鷹 (JC12)
    "JR-East.ChuoRapid.Kokubunji": 35,  # 国分寺 (JC16)
    "JR-East.ChuoRapid.Tachikawa": 35,  # 立川 (JC19)
    "JR-East.ChuoRapid.Hachioji": 35,  # 八王子 (JC22)
    "JR-East.ChuoRapid.Takao": 35,  # 高尾 (JC24)
}

def get_station_dwell_time(station_id: str) -> int:
    """
    駅IDから停車時間を取得する。
    定義がない場合はデフォルト20秒を返す。
    """
    if station_id is None:
        return 20
    return STATION_RANKS.get(str(station_id), 20)
