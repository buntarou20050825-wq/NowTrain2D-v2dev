import os
import requests
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('ODPT_API_KEY', '').strip()

url = 'https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle'
response = requests.get(url, params={'acl:consumerKey': api_key})

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

print("=== GTFS-RT Raw Data Inspection ===")
count = 0
for entity in feed.entity:
    if not entity.HasField('vehicle'):
        continue
    
    vp = entity.vehicle
    trip_id = vp.trip.trip_id
    
    # Only check Yamanote line (ends with G)
    if not trip_id.endswith('G'):
        continue
        
    count += 1
    print(f"\n--- Train {count}: {trip_id} ---")
    print(f"Trip ID: {vp.trip.trip_id}")
    print(f"Route ID: {vp.trip.route_id}")
    print(f"Direction ID: {vp.trip.direction_id}")
    print(f"Start Time: {vp.trip.start_time}")
    print(f"Start Date: {vp.trip.start_date}")
    print(f"Schedule Relationship: {vp.trip.schedule_relationship}")
    
    print(f"Vehicle ID: {vp.vehicle.id}")
    print(f"Vehicle Label: {vp.vehicle.label}")
    print(f"License Plate: {vp.vehicle.license_plate}")
    
    print(f"Current Stop Sequence: {vp.current_stop_sequence}")
    print(f"Stop ID: {vp.stop_id}")
    print(f"Current Status: {vp.current_status}")
    
    # Check for extensions or unknown fields if possible (basic print)
    print(f"Full Entity: {entity}")
    
    if count >= 5:
        break
