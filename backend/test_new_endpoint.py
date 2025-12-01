import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ODPT_API_KEY", "").strip()
base_url = "https://api-tokyochallenge.odpt.org/api/v4"

# Try different endpoint formats with new base URL
endpoints = [
    f"{base_url}/gtfs/realtime/VehiclePosition_JREast.pb",
    f"{base_url}/gtfs/realtime/JR-East",
    f"{base_url}/gtfs/realtime/VehiclePosition",
    f"{base_url}/gtfs/realtime",
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
            except Exception as e:
                print(f"  × Not valid GTFS-RT: {e}")
            break
        else:
            print(f"  Error: {resp.text[:200]}")
    except Exception as e:
        print(f"  Exception: {type(e).__name__}: {e}")

print("\nDone.")
