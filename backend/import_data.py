# backend/import_data.py
import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session

# backendパッケージとして実行されることを想定 (python -m backend.import_data)
from .database import SessionLocal, init_db, Station, StationRank
from .station_ranks import STATION_RANKS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def import_stations(db: Session, json_path: Path):
    if not json_path.exists():
        logger.error(f"File not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for item in data:
        # JSON fields
        s_id = item.get("id")
        railway = item.get("railway")
        coord = item.get("coord")
        title = item.get("title", {})

        if not s_id:
            continue

        # Step 1: 単一路線前提。配列なら先頭を使う
        line_id = ""
        if isinstance(railway, list):
            if len(railway) > 0:
                line_id = railway[0]
                # 複数ある場合は警告（頻発するのでINFOレベルか、初回のみ出すなど工夫してもよいが、今回はそのまま）
                # logger.warning(f"Station {s_id} belongs to multiple lines {railway}, using first: {line_id}")
            else:
                line_id = ""
        elif isinstance(railway, str):
            line_id = railway
        
        lon, lat = None, None
        if coord and len(coord) >= 2:
            lon = float(coord[0])
            lat = float(coord[1])

        # Model instance
        station = Station(
            id=s_id,
            line_id=line_id,
            name_ja=title.get("ja"),
            name_en=title.get("en"),
            lon=lon,
            lat=lat,
        )
        
        # Upsert (merge)
        db.merge(station)
        count += 1
    
    db.commit()
    logger.info(f"Imported/Updated {count} stations.")

def import_ranks(db: Session):
    count = 0
    for s_id, dwell in STATION_RANKS.items():
        # Rank判定 (簡易ロジック: 50=S, 35=A, 20=B, check definition)
        # station_ranks.py comments:
        # 50: S, 35: A, 20: B(Default)
        # ここでは dwell_time を正として、rank カラムは補足情報的に入れる
        
        rank_char = "B"
        if dwell >= 50:
            rank_char = "S"
        elif dwell >= 35:
            rank_char = "A"
        
        rank_obj = StationRank(
            station_id=s_id,
            rank=rank_char,
            dwell_time=dwell
        )
        db.merge(rank_obj)
        count += 1
        
    db.commit()
    logger.info(f"Imported/Updated {count} station ranks.")

def main():
    logger.info("Initializing database...")
    init_db()
    
    db = SessionLocal()
    try:
        # 1. Stations
        # プロジェクトルートからの相対パス
        stations_json_path = Path("data/mini-tokyo-3d/stations.json")
        logger.info(f"Importing stations from {stations_json_path}...")
        import_stations(db, stations_json_path)
        
        # 2. Ranks
        logger.info("Importing station ranks...")
        import_ranks(db)
        
        logger.info("Data import completed successfully.")
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
