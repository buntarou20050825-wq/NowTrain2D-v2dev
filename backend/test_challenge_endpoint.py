import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ODPT_API_KEY", "").strip()

# Correct base URL from documentation
base_url = "https://api-challenge.odpt.org/api/v4/gtfs/realtime"

# Try different GTFS-RT endpoints
endpoints = [
    f"{base_url}/jreast_odpt_train_trip_update",  # Trip updates
    f"{base_url}/jreis_odpt_train_alert",  # Alerts
]

for url in endpoints:
    print(f"\nTrying: {url}")
    try:
        resp = requests.get(url, params={"acl:consumerKey": api_key}, timeout=10)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  SUCCESS! Content length: {len(resp.content)} bytes")
            print(f"  Content type: {resp.headers.get('content-type')}")
            # Test if it's valid protobuf
            try:
                from google.transit import gtfs_realtime_pb2
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(resp.content)
                print(f"  Entities: {len(feed.entity)}")
                print(f"  ✓ Valid GTFS-RT data!")
                
                # Check for Yamanote trains
                yamanote_count = 0
                for entity in feed.entity[:10]:  # Check first 10
                    if entity.HasField('trip_update'):
                        trip = entity.trip_update.trip
                        trip_id = getattr(trip, 'trip_id', "")
                        route_id = getattr(trip, 'route_id', "")
                        if "Yamanote" in trip_id or "Yamanote" in route_id or "JY" in trip_id:
                            yamanote_count += 1
                            print(f"    Found Yamanote: trip_id={trip_id}, route_id={route_id}")
                if yamanote_count > 0:
                    print(f"  ✓ Found {yamanote_count} Yamanote trains in first 10 entities!")
                break
            except Exception as e:
                print(f"  × Parse error: {e}")
        else:
            print(f"  Error: {resp.text[:200]}")
    except Exception as e:
        print(f"  Exception: {type(e).__name__}: {e}")

print("\nDone.")
