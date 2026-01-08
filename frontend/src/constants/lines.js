export const AVAILABLE_LINES = [
  // ===== 主要路線（既存4路線 + 人気路線を先頭に） =====
  { id: "yamanote", name: "山手線", railwayId: "JR-East.Yamanote", color: "#80C342" },
  { id: "chuo_rapid", name: "中央線快速", railwayId: "JR-East.ChuoRapid", color: "#EB5C01" },
  { id: "keihin_tohoku", name: "京浜東北線・根岸線", railwayId: "JR-East.KeihinTohokuNegishi", color: "#00A7E3" },
  { id: "sobu_local", name: "総武線各駅停車", railwayId: "JR-East.ChuoSobuLocal", color: "#FFE500" },
  { id: "saikyo", name: "埼京線・川越線", railwayId: "JR-East.SaikyoKawagoe", color: "#009944" },
  { id: "shonan_shinjuku", name: "湘南新宿ライン", railwayId: "JR-East.ShonanShinjuku", color: "#E76E3C" },
  { id: "tokaido", name: "東海道線", railwayId: "JR-East.Tokaido", color: "#F78422" },
  { id: "yokosuka", name: "横須賀線", railwayId: "JR-East.Yokosuka", color: "#0075C2" },
  { id: "sobu_rapid", name: "総武快速線", railwayId: "JR-East.SobuRapid", color: "#0075C2" },
  { id: "joban_rapid", name: "常磐線快速", railwayId: "JR-East.JobanRapid", color: "#00A960" },
  { id: "joban_local", name: "常磐線各駅停車", railwayId: "JR-East.JobanLocal", color: "#B5B5AC" },
  { id: "keiyo", name: "京葉線", railwayId: "JR-East.Keiyo", color: "#C9242F" },
  { id: "musashino", name: "武蔵野線", railwayId: "JR-East.Musashino", color: "#EE6B23" },
  { id: "nambu", name: "南武線", railwayId: "JR-East.Nambu", color: "#FFD400" },
  { id: "yokohama", name: "横浜線", railwayId: "JR-East.Yokohama", color: "#7FC342" },

  // ===== 中央線系統 =====
  { id: "chuo", name: "中央本線", railwayId: "JR-East.Chuo", color: "#EB5C01" },
  { id: "ome", name: "青梅線", railwayId: "JR-East.Ome", color: "#EB5C01" },
  { id: "itsukaichi", name: "五日市線", railwayId: "JR-East.Itsukaichi", color: "#EB5C01" },

  // ===== 宇都宮・高崎線系統 =====
  { id: "utsunomiya", name: "宇都宮線", railwayId: "JR-East.Utsunomiya", color: "#F78422" },
  { id: "takasaki", name: "高崎線", railwayId: "JR-East.Takasaki", color: "#F78422" },
  { id: "joetsu", name: "上越線", railwayId: "JR-East.Joetsu", color: "#F78422" },
  { id: "ryomo", name: "両毛線", railwayId: "JR-East.Ryomo", color: "#F78422" },
  { id: "nikko", name: "日光線", railwayId: "JR-East.Nikko", color: "#F78422" },

  // ===== 常磐線系統 =====
  { id: "joban", name: "常磐線", railwayId: "JR-East.Joban", color: "#00A960" },
  { id: "mito", name: "水戸線", railwayId: "JR-East.Mito", color: "#00A960" },

  // ===== 総武・成田線系統 =====
  { id: "sobu", name: "総武本線", railwayId: "JR-East.Sobu", color: "#0075C2" },
  { id: "narita", name: "成田線", railwayId: "JR-East.Narita", color: "#0075C2" },
  { id: "narita_airport", name: "成田線空港支線", railwayId: "JR-East.NaritaAirportBranch", color: "#0075C2" },
  { id: "narita_abiko", name: "成田線我孫子支線", railwayId: "JR-East.NaritaAbikoBranch", color: "#0075C2" },
  { id: "kashima", name: "鹿島線", railwayId: "JR-East.Kashima", color: "#0075C2" },
  { id: "togane", name: "東金線", railwayId: "JR-East.Togane", color: "#0075C2" },

  // ===== 房総系統 =====
  { id: "uchibo", name: "内房線", railwayId: "JR-East.Uchibo", color: "#0075C2" },
  { id: "sotobo", name: "外房線", railwayId: "JR-East.Sotobo", color: "#0075C2" },
  { id: "kururi", name: "久留里線", railwayId: "JR-East.Kururi", color: "#0075C2" },

  // ===== 東海道・伊東線系統 =====
  { id: "ito", name: "伊東線", railwayId: "JR-East.Ito", color: "#F78422" },

  // ===== 京葉線系統 =====
  { id: "keiyo_koya", name: "京葉線高谷支線", railwayId: "JR-East.KeiyoKoyaBranch", color: "#C9242F" },
  { id: "keiyo_futamata", name: "京葉線二俣支線", railwayId: "JR-East.KeiyoFutamataBranch", color: "#C9242F" },

  // ===== 川越線系統 =====
  { id: "kawagoe", name: "川越線", railwayId: "JR-East.Kawagoe", color: "#009944" },

  // ===== 武蔵野線支線 =====
  { id: "musashino_kunitachi", name: "武蔵野線国立支線", railwayId: "JR-East.MusashinoKunitachiBranch", color: "#EE6B23" },
  { id: "musashino_omiya", name: "武蔵野線大宮支線", railwayId: "JR-East.MusashinoOmiyaBranch", color: "#EE6B23" },
  { id: "musashino_nishiurawa", name: "武蔵野線西浦和支線", railwayId: "JR-East.MusashinoNishiUrawaBranch", color: "#EE6B23" },

  // ===== 南武線・鶴見線系統 =====
  { id: "nambu_branch", name: "南武線浜川崎支線", railwayId: "JR-East.NambuBranch", color: "#FFD400" },
  { id: "tsurumi", name: "鶴見線", railwayId: "JR-East.Tsurumi", color: "#FFD400" },
  { id: "tsurumi_umishibaura", name: "鶴見線海芝浦支線", railwayId: "JR-East.TsurumiUmiShibauraBranch", color: "#FFD400" },
  { id: "tsurumi_okawa", name: "鶴見線大川支線", railwayId: "JR-East.TsurumiOkawaBranch", color: "#FFD400" },

  // ===== 横浜線・相模線系統 =====
  { id: "sagami", name: "相模線", railwayId: "JR-East.Sagami", color: "#7FC342" },

  // ===== 八高線 =====
  { id: "hachiko", name: "八高線", railwayId: "JR-East.Hachiko", color: "#8B7355" },

  // ===== 相鉄直通 =====
  { id: "sotetsu_direct", name: "相鉄直通線", railwayId: "JR-East.SotetsuDirect", color: "#0072BC" },

  // ===== 貨物線・支線 =====
  { id: "yamanote_freight", name: "山手貨物線", railwayId: "JR-East.YamanoteFreight", color: "#80C342" },
  { id: "tokaido_freight", name: "東海道貨物線", railwayId: "JR-East.TokaidoFreight", color: "#F78422" },
  { id: "osaki_branch", name: "大崎支線", railwayId: "JR-East.OsakiBranch", color: "#80C342" },
];
