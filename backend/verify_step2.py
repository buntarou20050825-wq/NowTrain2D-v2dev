# backend/verify_step2.py
import logging
from pathlib import Path
from backend.data_cache import DataCache
from backend.train_position_v4 import _get_station_coord_v4

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify():
    logger.info("Starting Step 2 Verification...")
    
    # 1. Initialize Cache
    root_dir = Path("data")
    if not root_dir.exists():
        # Adjust if running from project root
        root_dir = Path(".") / "data"
    
    cache = DataCache(root_dir)
    
    # 2. Load All (Should trigger load_station_positions_from_db)
    logger.info("Calling cache.load_all()...")
    cache.load_all()
    
    # Check station_positions count
    count = len(cache.station_positions)
    logger.info(f"Station Positions Count: {count}")
    if count == 0:
        logger.error("Station positions is EMPTY! DB load failed?")
        return
    else:
        logger.info("Station positions loaded successfully (from DB).")

    # 3. Test get_stations_by_line (simulating /api/stations)
    line_id = "JR-East.ChuoRapid"
    stations = cache.get_stations_by_line(line_id)
    logger.info(f"Stations for {line_id}: {len(stations)}")
    if len(stations) == 0:
        logger.error(f"No stations found for {line_id}! get_stations_by_line failed?")
    else:
        sample = stations[0]
        logger.info(f"Sample station: {sample}")
        if "coord" in sample:
             logger.info("Station has coord. OK.")
        else:
             logger.error("Station missing coord!")

    # 4. Test train_position_v4 accessor
    # Use a known station ID (e.g. Tokyo for Chuo Rapid? JC01 -> 1101?)
    # Let's use ID from sample
    test_id = sample["id"]
    coord = _get_station_coord_v4(test_id, cache)
    logger.info(f"Coord for {test_id} via train_position_v4: {coord}")
    
    if coord and len(coord) == 2:
        logger.info("train_position_v4 accessor check PASSED.")
    else:
        logger.error("train_position_v4 accessor check FAILED.")
        
    logger.info("Step 2 Verification Completed.")

if __name__ == "__main__":
    verify()
