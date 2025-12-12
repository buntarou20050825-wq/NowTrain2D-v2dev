# stop_sequence_check.py
import os
import requests
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('ODPT_API_KEY', '').strip()

# VehiclePosition から stop_sequence と座標を取得
url = 'https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_vehicle'
response = requests.get(url, params={'acl:consumerKey': api_key}, timeout=30)
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

# 山手線の駅座標（APIから取得）
stations_resp = requests.get('http://localhost:8000/api/stations?lineId=JR-East.Yamanote')
stations = stations_resp.json()['stations']

print('=== 山手線駅の座標 ===')
for i, st in enumerate(stations):
    coord = st['coord']
    print(f'{i+1:2d}. {st["name_ja"]:10s} lat={coord["lat"]:.4f}, lon={coord["lon"]:.4f}')

print()
print('=== GTFS-RT stop_sequence と座標 ===')
print('外回り (4201/4202):')
for entity in feed.entity:
    if not entity.HasField('vehicle'):
        continue
    vp = entity.vehicle
    trip_id = vp.trip.trip_id
    if not trip_id.endswith('G'):
        continue
    if trip_id.startswith('4201') or trip_id.startswith('4202'):
        print(f'  seq={vp.current_stop_sequence:2d} lat={vp.position.latitude:.4f} lon={vp.position.longitude:.4f} ({trip_id})')

print()
print('内回り (4211/4212):')
for entity in feed.entity:
    if not entity.HasField('vehicle'):
        continue
    vp = entity.vehicle
    trip_id = vp.trip.trip_id
    if not trip_id.endswith('G'):
        continue
    if trip_id.startswith('4211') or trip_id.startswith('4212'):
        print(f'  seq={vp.current_stop_sequence:2d} lat={vp.position.latitude:.4f} lon={vp.position.longitude:.4f} ({trip_id})')