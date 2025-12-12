import os
import requests
import json
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('ODPT_API_KEY', '').strip()

# 1. Get Timetable
print("Fetching Timetable...")
r = requests.get('http://localhost:8000/api/yamanote/positions')
timetable_data = r.json()
timetable_trains = timetable_data.get('positions', [])

# 2. Get GTFS-RT
print("Fetching GTFS-RT...")
url = 'https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle'
response = requests.get(url, params={'acl:consumerKey': api_key})
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

gtfs_trains = []
for entity in feed.entity:
    if entity.HasField('vehicle') and entity.vehicle.trip.trip_id.endswith('G'):
        gtfs_trains.append(entity.vehicle)

# 3. Test Matching
print(f"\nTesting Matching (Timetable: {len(timetable_trains)}, GTFS: {len(gtfs_trains)})")
matches = 0

for tt in timetable_trains:
    tt_num = tt['number'] # e.g. "1830G"
    
    # Try to find in GTFS
    found = False
    for gtfs in gtfs_trains:
        trip_id = gtfs.trip.trip_id # e.g. "4201830G"
        
        # Check if tt_num is in trip_id
        if tt_num in trip_id:
            print(f"MATCH: TT {tt_num} -> GTFS {trip_id}")
            found = True
            matches += 1
            break
    
    if not found:
        print(f"NO MATCH: TT {tt_num}")

print(f"\nTotal Matches: {matches} / {len(timetable_trains)}")
