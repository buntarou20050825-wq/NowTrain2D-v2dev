import requests
import json

try:
    r = requests.get('http://localhost:8000/api/yamanote/positions')
    data = r.json()
    if data['positions']:
        p = data['positions'][0]
        print("=== Timetable API Response Sample ===")
        print(json.dumps(p, indent=2, ensure_ascii=False))
    else:
        print("No positions found in API response")
except Exception as e:
    print(f"Error: {e}")
