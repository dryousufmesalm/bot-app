#!/usr/bin/env python3

from Api.APIHandler import API
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Get PocketBase URL from environment or use default
pb_url = os.getenv('POCKETBASE_URL', 'https://pocketbase.patrickcyber.com')

# Initialize API client
api = API(pb_url)

# Try to get the specific cycle that's causing issues
cycle_id = 'm0wj65me81p2094'
print(f'Looking for cycle with ID: {cycle_id}')

try:
    result = api.get_ACT_cycle_by_id(cycle_id)
    if result:
        print(f'Found {len(result)} cycles')
        for cycle in result:
            print(f'  - ID: {cycle.id}')
            print(f'  - Symbol: {cycle.symbol}')
            print(f'  - Status: {getattr(cycle, "status", "unknown")}')
            print(f'  - Is Closed: {getattr(cycle, "is_closed", "unknown")}')
    else:
        print('No cycles found with that ID')
        
    # Also check all ACT cycles
    print('\nAll ACT cycles:')
    all_cycles = api.get_all_ACT_active_cycles()
    print(f'Found {len(all_cycles)} active ACT cycles')
    for cycle in all_cycles[:5]:  # Show first 5
        print(f'  - ID: {cycle.id}')
        print(f'  - Symbol: {getattr(cycle, "symbol", "unknown")}')
        print(f'  - Status: {getattr(cycle, "status", "unknown")}')
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc() 