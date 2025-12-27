#!/usr/bin/env python
"""Debug: Check if station IDs are being set correctly"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gtfs_rt_tripupdate import fetch_trip_updates
from data_cache import DataCache
import httpx


async def main():
    api_key = os.getenv('ODPT_API_KEY')
    if not api_key:
        print("ERROR: ODPT_API_KEY not set")
        return
    
    cache = DataCache(Path(__file__).parent.parent / 'data')
    cache.load_all()
    
    async with httpx.AsyncClient() as client:
        schedules = await fetch_trip_updates(
            client,
            api_key,
            cache,
            target_route_id='JR-East.ChuoRapid',
            mt3d_prefix='JR-East.ChuoRapid'
        )
    
    print(f"Total schedules: {len(schedules)}")
    
    if schedules:
        trip_id = list(schedules.keys())[0]
        schedule = schedules[trip_id]
        print(f"\nSample trip: {trip_id}")
        print(f"Train number: {schedule.train_number}")
        print(f"Direction: {schedule.direction}")
        print(f"Station count: {len(schedule.schedules_by_seq)}")
        
        for seq, stu in list(schedule.schedules_by_seq.items())[:5]:
            print(f"  seq={seq}: station_id={stu.station_id}, raw={stu.raw_stop_id}, resolved={stu.resolved}")


if __name__ == "__main__":
    asyncio.run(main())
