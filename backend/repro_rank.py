# backend/repro_rank.py
import logging
from backend.data_cache import DataCache
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def repro():
    # 1. Init Cache
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    cache = DataCache(DATA_DIR)
    
    # 2. Get Stations for Yamanote (where ranks exist)
    line_id = "JR-East.Yamanote"
    stations = cache.get_stations_by_line(line_id)
    
    if not stations:
        logger.error("No stations found for Yamanote line. DB might be empty?")
        return
        
    # 3. Check for rank field
    logger.info(f"Checking first station: {stations[0]}")
    if "rank" in stations[0]:
        logger.info(f"SUCCESS: 'rank' field found: {stations[0]['rank']}")
    else:
        logger.error("FAILURE: 'rank' field MISSING in get_stations_by_line result.")

if __name__ == "__main__":
    repro()
