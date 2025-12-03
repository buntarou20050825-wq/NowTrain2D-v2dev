import requests
import json

try:
    r = requests.get('http://localhost:8000/api/trains/yamanote/positions/v2')
    data = r.json()
    
    print(f"Total trains: {data['count']}")
    
    if data['trains']:
        train = data['trains'][0]
        print("\nSample train data:")
        print(json.dumps(train, indent=2))
        
        # Count trains with schedule data
        with_schedule = sum(1 for t in data['trains'] if t.get('departureTime') and t.get('nextArrivalTime'))
        print(f"\nTrains with schedule data: {with_schedule}/{data['count']}")
    else:
        print("No trains found")
        
except Exception as e:
    print(f"Error: {e}")
