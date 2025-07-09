#!/usr/bin/env python3
"""
Script to manually create the advanced_cycles_trader_cycles collection
"""

import requests
import json

def create_collection_schema():
    """Create the advanced_cycles_trader_cycles collection with proper schema"""
    
    base_url = "https://pdapp.fppatrading.com"
    admin_email = "dev@mail.com"
    admin_password = "1223334444"
    
    # Authenticate as admin
    print("Authenticating as admin...")
    auth_response = requests.post(
        f"{base_url}/api/admins/auth-with-password",
        json={
            "identity": admin_email,
            "password": admin_password
        }
    )
    
    if auth_response.status_code != 200:
        print(f"❌ Admin authentication failed: {auth_response.text}")
        return False
    
    auth_data = auth_response.json()
    admin_token = auth_data.get('token')
    print("✅ Admin authentication successful!")
    
    # Headers for admin requests
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    # Check if collection already exists
    print("\n🔍 Checking if collection exists...")
    collections_response = requests.get(
        f"{base_url}/api/collections",
        headers=headers
    )
    
    if collections_response.status_code == 200:
        collections = collections_response.json()
        existing_collection = None
        
        for collection in collections:
            if collection.get('name') == 'advanced_cycles_trader_cycles':
                existing_collection = collection
                break
        
        if existing_collection:
            print(f"📋 Collection exists with ID: {existing_collection['id']}")
            print("🗑️ Deleting existing collection to recreate with correct schema...")
            
            delete_response = requests.delete(
                f"{base_url}/api/collections/{existing_collection['id']}",
                headers=headers
            )
            
            if delete_response.status_code == 204:
                print("✅ Existing collection deleted successfully")
            else:
                print(f"⚠️ Warning: Could not delete existing collection: {delete_response.text}")
    
    # Define the collection schema based on our migration
    collection_data = {
        "name": "advanced_cycles_trader_cycles",
        "type": "base",
        "system": False,
        "schema": [
            {
                "name": "cycle_id",
                "type": "text",
                "required": True,
                "unique": True,
                "options": {}
            },
            {
                "name": "bot_id", 
                "type": "text",
                "required": True,
                "options": {}
            },
            {
                "name": "account",
                "type": "text", 
                "required": True,
                "options": {}
            },
            {
                "name": "symbol",
                "type": "text",
                "required": True,
                "options": {}
            },
            {
                "name": "magic_number",
                "type": "number",
                "required": True,
                "options": {"noDecimal": True}
            },
            {
                "name": "entry_price",
                "type": "number",
                "required": True,
                "options": {}
            },
            {
                "name": "stop_loss",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "take_profit",
                "type": "number", 
                "required": False,
                "options": {}
            },
            {
                "name": "lot_size",
                "type": "number",
                "required": True,
                "options": {}
            },
            {
                "name": "direction",
                "type": "select",
                "required": True,
                "options": {
                    "maxSelect": 1,
                    "values": ["BUY", "SELL"]
                }
            },
            {
                "name": "current_direction",
                "type": "select",
                "required": True,
                "options": {
                    "maxSelect": 1,
                    "values": ["BUY", "SELL"]
                }
            },
            {
                "name": "zone_base_price",
                "type": "number",
                "required": True,
                "options": {}
            },
            {
                "name": "initial_threshold_price",
                "type": "number",
                "required": True,
                "options": {}
            },
            {
                "name": "zone_threshold_pips",
                "type": "number",
                "required": True,
                "options": {}
            },
            {
                "name": "order_interval_pips",
                "type": "number",
                "required": True,
                "options": {}
            },
            {
                "name": "batch_stop_loss_pips",
                "type": "number",
                "required": True,
                "options": {}
            },
            # Optional fields
            {
                "name": "zone_range_pips",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "direction_switched",
                "type": "bool",
                "required": False,
                "options": {}
            },
            {
                "name": "direction_switches",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            {
                "name": "done_price_levels",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "next_order_index",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            {
                "name": "active_orders",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "completed_orders",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "current_batch_id",
                "type": "text",
                "required": False,
                "options": {}
            },
            {
                "name": "last_order_time",
                "type": "date",
                "required": False,
                "options": {}
            },
            {
                "name": "last_order_price",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "accumulated_loss",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "batch_losses",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "is_active",
                "type": "bool",
                "required": False,
                "options": {}
            },
            {
                "name": "is_closed",
                "type": "bool",
                "required": False,
                "options": {}
            },
            {
                "name": "close_reason",
                "type": "text",
                "required": False,
                "options": {}
            },
            {
                "name": "close_time",
                "type": "date",
                "required": False,
                "options": {}
            },
            {
                "name": "total_profit",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "total_orders",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            {
                "name": "profitable_orders",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            {
                "name": "loss_orders",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            {
                "name": "duration_minutes",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            # Additional fields that might be needed
            {
                "name": "is_favorite",
                "type": "bool",
                "required": False,
                "options": {}
            },
            {
                "name": "opened_by",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "closing_method",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "lot_idx",
                "type": "number",
                "required": False,
                "options": {"noDecimal": True}
            },
            {
                "name": "status",
                "type": "text",
                "required": False,
                "options": {}
            },
            {
                "name": "lower_bound",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "upper_bound",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "total_volume",
                "type": "number",
                "required": False,
                "options": {}
            },
            {
                "name": "orders",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "orders_config",
                "type": "json",
                "required": False,
                "options": {}
            },
            {
                "name": "cycle_type",
                "type": "text",
                "required": False,
                "options": {}
            }
        ]
    }
    
    # Create the collection
    print("\n🚀 Creating collection with schema...")
    create_response = requests.post(
        f"{base_url}/api/collections",
        headers=headers,
        json=collection_data
    )
    
    if create_response.status_code == 200:
        result = create_response.json()
        print(f"✅ Collection created successfully!")
        print(f"   ID: {result.get('id')}")
        print(f"   Name: {result.get('name')}")
        print(f"   Fields: {len(result.get('schema', []))}")
        return True
    else:
        print(f"❌ Failed to create collection: {create_response.text}")
        return False

if __name__ == "__main__":
    success = create_collection_schema()
    if success:
        print("\n🎉 Collection schema created successfully!")
        print("You can now test cycle creation again.")
    else:
        print("\n❌ Failed to create collection schema!") 