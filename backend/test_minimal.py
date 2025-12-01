import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ODPT_API_KEY", "").strip()
print(f"API Key (first 10 chars): {api_key[:10]}...")
print(f"API Key length: {len(api_key)}")

url = "https://api-public.odpt.org/api/v4/gtfs/realtime/VehiclePosition_JREast.pb"
headers = {"acl:consumerKey": api_key}

print(f"URL: {url}")
print(f"Headers: {headers}")

try:
    print("Sending request...")
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status code: {resp.status_code}")
    print(f"Response headers: {resp.headers}")
    print(f"Content length: {len(resp.content)}")
    if resp.status_code != 200:
        print(f"Response text: {resp.text}")
    resp.raise_for_status()
    print("SUCCESS!")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
