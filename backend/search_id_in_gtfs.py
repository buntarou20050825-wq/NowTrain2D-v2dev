import os
import requests
import json
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('ODPT_API_KEY', '').strip()

# 1. Get Timetable Train Numbers
print("Fetching Timetable...")
try:
    r = requests.get('http://localhost:8000/api/yamanote/positions')
    timetable_data = r.json()
    timetable_numbers = [p['number'] for p in timetable_data.get('positions', [])]
    print(f"Found {len(timetable_numbers)} timetable trains. Examples: {timetable_numbers[:5]}")
except Exception as e:
    print(f"Failed to fetch timetable: {e}")
    timetable_numbers = []

# 2. Get GTFS-RT Data
print("\nFetching GTFS-RT...")
url = 'https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle'
response = requests.get(url, params={'acl:consumerKey': api_key})
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

# 3. Search for matches
print("\nSearching for matches...")
found_count = 0
total_gtfs = 0

for entity in feed.entity:
    if not entity.HasField('vehicle'):
        continue
    
    vp = entity.vehicle
    trip_id = vp.trip.trip_id
    if not trip_id.endswith('G'):
        continue
        
    total_gtfs += 1
    
    # Convert entity to string to search everywhere
    entity_str = str(entity)
    
    # Check each timetable number
    matches = []
    for num in timetable_numbers:
        if num in entity_str:
            matches.append(num)
            
    if matches:
        found_count += 1
        print(f"MATCH FOUND! GTFS Entity {trip_id} contains {matches}")
        # Print the field that matched if possible (simple string check for now)
        # print(entity_str) 

print(f"\nSummary:")
print(f"Total GTFS-RT Yamanote trains: {total_gtfs}")
print(f"Total Timetable trains: {len(timetable_numbers)}")
print(f"Matches found: {found_count}")

if found_count == 0:
    print("\nNo direct ID matches found in any field.")
    print("Checking for partial matches (e.g. 1830 in 4201830G)...")
    
    # Check for numeric part match
    partial_matches = 0
    for entity in feed.entity:
        if not entity.HasField('vehicle'): continue
        vp = entity.vehicle
        trip_id = vp.trip.trip_id
        if not trip_id.endswith('G'): continue
        
        gtfs_num = ''.join(filter(str.isdigit, trip_id))
        
        for num in timetable_numbers:
            tt_num = ''.join(filter(str.isdigit, num))
            if tt_num in gtfs_num or gtfs_num in tt_num:
                # print(f"Partial match: GTFS {trip_id} ({gtfs_num}) <-> TT {num} ({tt_num})")
                partial_matches += 1
                
    print(f"Potential partial matches based on digits: {partial_matches}")
