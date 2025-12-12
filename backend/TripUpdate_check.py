import os
import requests
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('ODPT_API_KEY', '').strip()

url = 'https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_trip_update'
response = requests.get(url, params={'acl:consumerKey': api_key}, timeout=30)
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

print('Total entities:', len(feed.entity))

for entity in feed.entity:
    if not entity.HasField('trip_update'):
        continue
    
    tu = entity.trip_update
    trip_id = tu.trip.trip_id
    
    if not trip_id.endswith('G'):
        continue
    
    print('Trip ID:', trip_id)
    print('Stop Time Updates:', len(tu.stop_time_update))
    
    for i, stu in enumerate(tu.stop_time_update[:3]):
        print('  Stop', i, '- ID:', stu.stop_id, 'Seq:', stu.stop_sequence)
        if stu.HasField('arrival'):
            print('    Arrival time:', stu.arrival.time, 'delay:', stu.arrival.delay)
        if stu.HasField('departure'):
            print('    Departure time:', stu.departure.time, 'delay:', stu.departure.delay)
    
    break