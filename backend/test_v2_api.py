"""
Test script for /api/trains/yamanote/positions/v2
"""
import asyncio
from gtfs_rt_vehicle import fetch_yamanote_positions_with_schedule
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    api_key = os.getenv("ODPT_API_KEY", "").strip()
    
    print("Fetching Yamanote positions with schedule...")
    positions = await fetch_yamanote_positions_with_schedule(api_key)
    
    print(f"\nTotal trains: {len(positions)}")
    print("\nSample data (first 3 trains):")
    print("-" * 80)
    
    for i, p in enumerate(positions[:3], 1):
        print(f"\n{i}. Train {p.train_number} ({p.direction})")
        print(f"   Trip ID: {p.trip_id}")
        print(f"   Position: ({p.latitude:.5f}, {p.longitude:.5f})")
        print(f"   Stop Sequence: {p.stop_sequence}")
        print(f"   Status: {p.status} (1=STOPPED_AT, 2=IN_TRANSIT_TO)")
        print(f"   Departure Time: {p.departure_time}")
        print(f"   Next Arrival Time: {p.next_arrival_time}")
        
        if p.departure_time and p.next_arrival_time:
            duration = p.next_arrival_time - p.departure_time
            print(f"   Travel Duration: {duration}s ({duration/60:.1f}min)")
    
    # Count trains with schedule data
    with_schedule = sum(1 for p in positions if p.departure_time and p.next_arrival_time)
    print(f"\n\nTrains with schedule data: {with_schedule}/{len(positions)}")

if __name__ == "__main__":
    asyncio.run(main())
