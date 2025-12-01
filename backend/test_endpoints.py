import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ODPT_API_KEY", "").strip()

# Try different endpoint formats
endpoints = [
    "https://api-public.odpt.org/api/v4/gtfs/realtime/VehiclePosition_JREast.pb",
    "https://api-public.odpt.org/api/v4/gtfs/realtime/JR-East_vehicle",
    "https://api-public.odpt.org/api/v4/gtfs/realtime/JREast",
    "https://api.odpt.org/api/v4/gtfs/realtime/VehiclePosition_JREast.pb",
]

for url in endpoints:
    print(f"\nTrying: {url}")
    try:
        resp = requests.get(url, params={"acl:consumerKey": api_key}, timeout=5)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  SUCCESS! Content length: {len(resp.content)}")
            print(f"  Content type: {resp.headers.get('content-type')}")
            break
        else:
            print(f"  Error: {resp.text[:100]}")
    except Exception as e:
        print(f"  Exception: {e}")
