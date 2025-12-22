import asyncio
import os
import httpx
from pathlib import Path
from dotenv import load_dotenv
from gtfs_rt_tripupdate import fetch_trip_updates
from data_cache import DataCache
from datetime import datetime

# タイムスタンプを HH:MM:SS に変換
def fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime('%H:%M:%S') if ts else "N/A"

async def watch():
    load_dotenv()
    api_key = os.getenv("ODPT_API_KEY")
    
    # ▼▼▼ パスの設定 ▼▼▼
    # backendディレクトリの親（プロジェクトルート）を取得
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # frontend/public/data を指す (Pathオブジェクトのままにする)
    DATA_DIR = BASE_DIR / "frontend" / "public" / "data"
    
    print("============================================================")
    print("  TripUpdate 更新監視ツール (MS-Debug)")
    print("============================================================")
    print(f"📂 DataCache をロード中...")
    print(f"   パス: {DATA_DIR}")

    try:
        # 修正箇所: str() を外して Pathオブジェクトのまま渡す
        cache = DataCache(DATA_DIR)
        cache.load_all()
        print("✅ データロード成功！監視を開始します。")
    except Exception as e:
        print(f"❌ データロードエラー: {e}")
        print("パス設定を確認してください。")
        return
    # ▲▲▲ 修正ここまで ▲▲▲

    print("🔄 監視開始 (Ctrl+C で停止)")
    print("-" * 60)

    prev_schedules = {}
    poll_count = 0
    
    # 共有クライアントを作成
    async with httpx.AsyncClient() as client:
        while True:
            try:
                poll_count += 1
                now_str = datetime.now().strftime('%H:%M:%S')
                
                # データ取得 (clientを渡す)
                current_schedules = await fetch_trip_updates(client, api_key, cache)
                
                print(f"\n[{now_str}] ポーリング#{poll_count} - 列車数: {len(current_schedules)}")

                # 差分チェック
                if prev_schedules:
                    changes_found = False
                    for trip_id, new_sched in current_schedules.items():
                        old_sched = prev_schedules.get(trip_id)
                        if not old_sched:
                            continue 
                        
                        # 各駅の予測時刻を比較
                        for seq, new_stop in new_sched.schedules_by_seq.items():
                            old_stop = old_sched.schedules_by_seq.get(seq)
                            if not old_stop: continue
                            
                            # 到着時刻の変化をチェック
                            if new_stop.arrival_time and old_stop.arrival_time:
                                diff = new_stop.arrival_time - old_stop.arrival_time
                                if diff != 0:
                                    st_name = new_stop.station_id.split('.')[-1] if new_stop.station_id else f"Seq{seq}"
                                    sign = "+" if diff > 0 else ""
                                    
                                    # 遅延情報の変化もあれば表示
                                    delay_info = ""
                                    if hasattr(new_stop, 'delay'):
                                        delay_info = f" (Delay: {new_stop.delay}s)"
                                        
                                    print(f"  🚅 {new_sched.train_number} {st_name}: 到着 {fmt_ts(old_stop.arrival_time)} -> {fmt_ts(new_stop.arrival_time)} ({sign}{diff}s){delay_info}")
                                    changes_found = True
                    
                    if not changes_found:
                        print("  (予測時刻の変化なし)")

                prev_schedules = current_schedules
                
            except Exception as e:
                print(f"❌ Error: {e}")

            # 20秒待機
            await asyncio.sleep(20)

if __name__ == "__main__":
    try:
        asyncio.run(watch())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")