"""
GTFS-RTデータ取得のテストスクリプト（ファイル出力版）
山手線の列車位置情報を取得して表示する
"""
import sys
import logging
from dotenv import load_dotenv
from gtfs_client import GtfsClient

# ファイルに出力
with open('test_output.txt', 'w', encoding='utf-8') as f:
    # ログをファイルに出力
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s',
        stream=f
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
            # VehiclePositionを持つentityのみ処理
            if not entity.HasField('vehicle'):
                continue
            
            vehicle = entity.vehicle
            
            # trip情報の確認
            if not vehicle.HasField('trip'):
                continue
            
            trip = vehicle.trip
            
            # trip_idまたはroute_idに"Yamanote"または"JY"が含まれるか確認
            # HasFieldでエラーが出る場合の対策として getattr を使用
            trip_id = getattr(trip, 'trip_id', "") or ""
            route_id = getattr(trip, 'route_id', "") or ""
            
            is_yamanote = (
                "Yamanote" in trip_id or 
                "Yamanote" in route_id or
                "JY" in trip_id or
                "JY" in route_id
            )
            
            if is_yamanote:
                yamanote_trains.append((entity, vehicle, trip))
        
        # 山手線の列車情報を表示
        logger.info(f"\n{'='*60}")
        logger.info(f"Found {len(yamanote_trains)} Yamanote trains")
        logger.info(f"{'='*60}\n")
        
        if not yamanote_trains:
            logger.warning("No Yamanote trains found. This may be normal during late night hours.")
            return
        
        for idx, (entity, vehicle, trip) in enumerate(yamanote_trains, 1):
            position = vehicle.position
            
            f.write(f"\n--- Yamanote Train #{idx} ---\n")
            f.write(f"Entity ID:     {entity.id}\n")
            # getattr で安全にアクセス
            t_id = getattr(trip, 'trip_id', "N/A")
            r_id = getattr(trip, 'route_id', "N/A")
            d_id = getattr(trip, 'direction_id', "N/A")
            
            f.write(f"Trip ID:       {t_id}\n")
            f.write(f"Route ID:      {r_id}\n")
            f.write(f"Direction ID:  {d_id}\n")
            
            if vehicle.HasField('vehicle'):
                f.write(f"Vehicle ID:    {vehicle.vehicle.id}\n")
            
            f.write(f"Latitude:      {position.latitude}\n")
            f.write(f"Longitude:     {position.longitude}\n")
            
            if position.HasField('bearing'):
                f.write(f"Bearing:       {position.bearing}°\n")
            if position.HasField('speed'):
                f.write(f"Speed:         {position.speed} m/s\n")
            
            if vehicle.HasField('current_status'):
                status_map = {
                    0: "INCOMING_AT",
                    1: "STOPPED_AT",
                    2: "IN_TRANSIT_TO"
                }
                status = status_map.get(vehicle.current_status, f"UNKNOWN({vehicle.current_status})")
                f.write(f"Status:        {status}\n")
            
            if vehicle.HasField('stop_id'):
                f.write(f"Stop ID:       {vehicle.stop_id}\n")
            
            if vehicle.HasField('timestamp'):
                f.write(f"Timestamp:     {vehicle.timestamp}\n")
        
        # サマリー
        f.write(f"\n{'='*60}\n")
        f.write(f"SUMMARY: Successfully fetched {len(yamanote_trains)} Yamanote trains\n")
        f.write(f"{'='*60}\n")
    
    try:
        main()
    except Exception as e:
        import traceback
        f.write(f"\n\nEXCEPTION: {e}\n")
        traceback.print_exc(file=f)

print("Output written to test_output.txt")
