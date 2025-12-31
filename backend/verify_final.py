# backend/verify_final.py
import logging
from pathlib import Path
import sys

# Add backend to sys.path to mimic module execution if needed
sys.path.append(str(Path(__file__).parent))

from data_cache import DataCache
from train_position_v4 import _get_station_coord_v4

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify():
    logger.info("Starting Final Verification...")
    
    # 1. Initialize
    root_dir = Path("data")
    if not root_dir.exists():
        root_dir = Path(".") / "data"
    
    cache = DataCache(root_dir)
    cache.load_all()
    
    # 2. Check Memory Consumption (stations list should be empty)
    if not cache.stations:
        logger.info("SUCCESS: cache.stations is empty (stations.json not loaded to memory)")
    else:
        logger.warning(f"WARNING: cache.stations has {len(cache.stations)} items. stations.json might still be loaded?")
        # Note: If user wants strictly NO load, this should be 0.
    
    # 3. Check DB Cache
    if cache.station_positions:
        logger.info(f"SUCCESS: cache.station_positions has {len(cache.station_positions)} items (from DB)")
    else:
        logger.error("FAILURE: cache.station_positions is empty!")
        exit(1)
        
    # 4. Check Accessor
    line_id = "JR-East.ChuoRapid"
    stations = cache.get_stations_by_line(line_id)
    if stations:
        logger.info(f"SUCCESS: get_stations_by_line returned {len(stations)} stations")
    else:
        logger.error("FAILURE: get_stations_by_line returned 0 stations")
        exit(1)
        
    # 5. Check Train Position Logic
    test_id = stations[0]["id"]
    coord = _get_station_coord_v4(test_id, cache)
    if coord:
        logger.info(f"SUCCESS: _get_station_coord_v4 returned {coord}")
    else:
        logger.error("FAILURE: _get_station_coord_v4 returned None")
        exit(1)

if __name__ == "__main__":
    verify()
