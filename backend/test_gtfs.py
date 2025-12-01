"""
GTFS-RTデータ取得のテストスクリプト
山手線の列車位置情報を取得して表示する
"""
import sys
import logging
from dotenv import load_dotenv
from gtfs_client import GtfsClient

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    # 環境変数を読み込む
    load_dotenv()
    
    # GtfsClientを初期化
    client = GtfsClient()
    
    # VehiclePositionを取得
    logger.info("Fetching vehicle positions...")
    entities = client.fetch_vehicle_positions()
    
    if not entities:
        logger.error("No entities received. Check API key and network connection.")
        return
    
    logger.info(f"Fetched {len(entities)} entities")
    
    # 山手線の列車を抽出
    yamanote_trains = []
    
    for entity in entities:
        # TripUpdateを持つentityのみ処理
        if not entity.HasField('trip_update'):
            continue
        
        trip_update = entity.trip_update
        trip = trip_update.trip
        
        # trip_idを取得（getattr で安全にアクセス）
        trip_id = getattr(trip, 'trip_id', "") or ""
        route_id = getattr(trip, 'route_id', "") or ""
        
        # ODPT APIではroute_idが空の場合が多い
        # trip_idの形式から山手線を特定する必要がある
        # とりあえず全ての列車を収集（デバッグ用）
        yamanote_trains.append((entity, trip_update, trip))
        
        # 最初の10件のみを表示（デバッグ用）
        if len(yamanote_trains) >= 10:
            break
    
    # 山手線の列車情報を表示
    logger.info(f"\n{'='*60}")
    logger.info(f"Found {len(yamanote_trains)} JR-East trains (showing first 10)")
    logger.info(f"{'='*60}\n")
    
    if not yamanote_trains:
        logger.warning("No trains found.")
        return
    
    for idx, (entity, trip_update, trip) in enumerate(yamanote_trains, 1):
        
        print(f"\n--- JR-East Train #{idx} ---")
        print(f"Entity ID:     {entity.id}")
        # getattr で安全にアクセス
        t_id = getattr(trip, 'trip_id', "N/A")
        r_id = getattr(trip, 'route_id', "N/A")
        d_id = getattr(trip, 'direction_id', "N/A")
        
        print(f"Trip ID:       {t_id}")
        print(f"Route ID:      {r_id}")
        print(f"Direction ID:  {d_id}")
        print(f"Stop Updates:  {len(trip_update.stop_time_update)}")
        
        # Show first stop time update if available
        if len(trip_update.stop_time_update) > 0:
            stu = trip_update.stop_time_update[0]
            if stu.HasField('stop_id'):
                print(f"First Stop:    {stu.stop_id}")
            if stu.HasField('arrival'):
                if stu.arrival.HasField('delay'):
                    print(f"Arrival Delay: {stu.arrival.delay} seconds")
    
    # サマリー
    print(f"\n{'='*60}")
    print(f"SUMMARY: Successfully fetched {len(yamanote_trains)} JR-East trains")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
