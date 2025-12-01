import os
from dotenv import load_dotenv
from gtfs_client import GtfsClient

load_dotenv()

client = GtfsClient()
entities = client.fetch_vehicle_positions()

with open('entity_debug.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total entities: {len(entities)}\n\n")
    
    # Inspect first 10 entities
    for i, entity in enumerate(entities[:10], 1):
        f.write(f"--- Entity #{i} ---\n")
        f.write(f"ID: {entity.id}\n")
        
        # Check what type of data this entity contains
        if entity.HasField('trip_update'):
            f.write("Type: TripUpdate\n")
            trip = entity.trip_update.trip
            trip_id = getattr(trip, 'trip_id', 'N/A')
            route_id = getattr(trip, 'route_id', 'N/A')
            direction_id = getattr(trip, 'direction_id', 'N/A')
            
            f.write(f"  trip_id: {trip_id}\n")
            f.write(f"  route_id: {route_id}\n")
            f.write(f"  direction_id: {direction_id}\n")
            f.write(f"  stop_time_updates: {len(entity.trip_update.stop_time_update)}\n")
            
            # Check if it's Yamanote
            if "Yamanote" in str(trip_id) or "Yamanote" in str(route_id) or "JY" in str(trip_id):
                f.write(f"  >>> YAMANOTE TRAIN FOUND! <<<\n")
        elif entity.HasField('vehicle'):
            f.write("Type: VehiclePosition\n")
        elif entity.HasField('alert'):
            f.write("Type: Alert\n")
        else:
            f.write("Type: Unknown\n")
        f.write("\n")

print("Debug output written to entity_debug.txt")
