import os
import logging
from dotenv import load_dotenv
from gtfs_client import GtfsClient

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

client = GtfsClient()
entities = client.fetch_vehicle_positions()

print(f"Total entities: {len(entities)}\n")

# Inspect first 5 entities to understand structure
for i, entity in enumerate(entities[:5], 1):
    print(f"--- Entity #{i} ---")
    print(f"ID: {entity.id}")
    
    # Check what type of data this entity contains
    if entity.HasField('trip_update'):
        print("Type: TripUpdate")
        trip = entity.trip_update.trip
        print(f"  trip_id: {getattr(trip, 'trip_id', 'N/A')}")
        print(f"  route_id: {getattr(trip, 'route_id', 'N/A')}")
        print(f"  direction_id: {getattr(trip, 'direction_id', 'N/A')}")
        print(f"  stop_time_updates: {len(entity.trip_update.stop_time_update)}")
    elif entity.HasField('vehicle'):
        print("Type: VehiclePosition")
        vehicle = entity.vehicle
        trip = vehicle.trip
        print(f"  trip_id: {getattr(trip, 'trip_id', 'N/A')}")
        print(f"  route_id: {getattr(trip, 'route_id', 'N/A')}")
        if vehicle.HasField('position'):
            print(f"  lat: {vehicle.position.latitude}")
            print(f"  lon: {vehicle.position.longitude}")
    elif entity.HasField('alert'):
        print("Type: Alert")
    else:
        print("Type: Unknown")
    print()
