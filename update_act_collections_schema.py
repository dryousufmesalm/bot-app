import sys
import requests
import json
import argparse
from urllib.parse import urljoin
from pocketbase import PocketBase, Client
from Views.globals.app_configs import AppConfigs


def update_act_collections_schema(admin_email, admin_password, use_local=False):
    print("Advanced Cycles Trader Collections Schema Updater")
    print("=================================================")
    print("This script will update the Advanced Cycles Trader collections schema to add all required fields.")

    # Get base URL from app configs or use local if specified
    base_url = "https://pdapp.fppatrading.com" if use_local else AppConfigs().pb_url
    
    print(f"Using PocketBase URL: {base_url}")

    try:
        # Initialize PocketBase client
        client = PocketBase(base_url)

        # Test API connectivity
        print("Testing API connectivity...")
        try:
            collections = client.collections.get_list(1, 1)
            print(f"API connection successful. Found {collections.total_items} collections.")
        except Exception as conn_error:
            print(f"Error connecting to API: {conn_error}")
            return

        # Authenticate admin
        print(f"Authenticating as admin ({admin_email})...")
        try:
            auth_data = client.admins.auth_with_password("dev@mail.com", "1223334444")
            print("Authentication successful")
        except Exception as auth_error:
            print(f"Admin authentication failed: {auth_error}")
            return

        # Update advanced_cycles_trader_cycles collection
        update_advanced_cycles_collection(client)
        
        # Update global_loss_tracker collection
        update_global_loss_tracker_collection(client)

    except Exception as e:
        print(f"Error: {e}")


def update_advanced_cycles_collection(client):
    collection_id = "advanced_cycles_trader_cycles"
    print(f"\nUpdating collection: {collection_id}")
    
    try:
        collection_data = client.collections.get_one(collection_id)
        print(f"Found collection: {collection_data.name}")
    except Exception as coll_error:
        print(f"Error getting collection: {coll_error}")
        return

    # Define all fields for advanced_cycles_trader_cycles
    new_fields = [
        {"name": "cycle_id", "type": "text", "required": True, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "bot_id", "type": "text", "required": True, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "symbol", "type": "text", "required": True, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "magic_number", "type": "number", "required": True, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "entry_price", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "stop_loss", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "take_profit", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "lot_size", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "direction", "type": "select", "required": True, "options": {"maxSelect": 1, "values": ["BUY", "SELL"]}},
        {"name": "current_direction", "type": "select", "required": False, "options": {"maxSelect": 1, "values": ["BUY", "SELL"]}},
        {"name": "zone_base_price", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "reversal_threshold_pips", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "order_interval_pips", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "initial_order_stop_loss", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "cycle_interval", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "batch_stop_loss_pips", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "zone_range_pips", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "direction_switched", "type": "bool", "required": False},
        {"name": "direction_switches", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "done_price_levels", "type": "json", "required": False, "options": {"maxSize": 2000000}},
        {"name": "next_order_index", "type": "number", "required": False, "options": {"min": 1, "max": None, "noDecimal": True}},
        {"name": "active_orders", "type": "json", "required": False, "options": {"maxSize": 2000000}},
        {"name": "completed_orders", "type": "json", "required": False, "options": {"maxSize": 2000000}},
        {"name": "current_batch_id", "type": "text", "required": False, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "last_order_time", "type": "date", "required": False, "options": {"min": "", "max": ""}},
        {"name": "last_order_price", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "accumulated_loss", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": False}},
        {"name": "batch_losses", "type": "json", "required": False, "options": {"maxSize": 2000000}},
        {"name": "is_active", "type": "bool", "required": False},
        {"name": "is_closed", "type": "bool", "required": False},
        {"name": "close_reason", "type": "text", "required": False, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "close_time", "type": "date", "required": False, "options": {"min": "", "max": ""}},
        {"name": "total_profit", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "total_orders", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "profitable_orders", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "loss_orders", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "duration_minutes", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}}
    ]

    # Get current schema and add new fields
    current_schema = collection_data.schema
    existing_field_names = [field.get("name") for field in current_schema]
    fields_to_add = [field for field in new_fields if field["name"] not in existing_field_names]

    if not fields_to_add:
        print("All fields already exist in the advanced_cycles_trader_cycles collection")
        return

    # Add new fields to the schema
    updated_schema = current_schema + fields_to_add
    update_data = {"schema": updated_schema}

    try:
        client.collections.update(collection_id, update_data)
        print(f"Advanced cycles collection updated successfully with {len(fields_to_add)} new fields")
        for field in fields_to_add:
            print(f"  - Added field: {field['name']} ({field['type']})")
    except Exception as update_error:
        print(f"Error updating advanced cycles collection: {update_error}")


def update_global_loss_tracker_collection(client):
    collection_id = "global_loss_tracker"
    print(f"\nUpdating collection: {collection_id}")
    
    try:
        collection_data = client.collections.get_one(collection_id)
        print(f"Found collection: {collection_data.name}")
    except Exception as coll_error:
        print(f"Error getting collection: {coll_error}")
        return

    # Define all fields for global_loss_tracker
    new_fields = [
        {"name": "bot_id", "type": "text", "required": True, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "account_id", "type": "text", "required": True, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "symbol", "type": "text", "required": True, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "total_accumulated_losses", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "active_cycles_count", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "closed_cycles_count", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "initial_order_losses", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "threshold_order_losses", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "recovery_order_losses", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "last_cycle_id", "type": "text", "required": False, "options": {"min": None, "max": None, "pattern": ""}},
        {"name": "last_loss_amount", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "zone_based_losses", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "direction_switch_count", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "batch_stop_loss_triggers", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "max_single_cycle_loss", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "average_cycle_loss", "type": "number", "required": False, "options": {"min": None, "max": None, "noDecimal": False}},
        {"name": "loss_trend", "type": "select", "required": False, "options": {"maxSelect": 1, "values": ["increasing", "decreasing", "stable"]}},
        {"name": "total_cycles_processed", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "profitable_cycles", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}},
        {"name": "loss_making_cycles", "type": "number", "required": False, "options": {"min": 0, "max": None, "noDecimal": True}}
    ]

    # Get current schema and add new fields
    current_schema = collection_data.schema
    existing_field_names = [field.get("name") for field in current_schema]
    fields_to_add = [field for field in new_fields if field["name"] not in existing_field_names]

    if not fields_to_add:
        print("All fields already exist in the global_loss_tracker collection")
        return

    # Add new fields to the schema
    updated_schema = current_schema + fields_to_add
    update_data = {"schema": updated_schema}

    try:
        client.collections.update(collection_id, update_data)
        print(f"Global loss tracker collection updated successfully with {len(fields_to_add)} new fields")
        for field in fields_to_add:
            print(f"  - Added field: {field['name']} ({field['type']})")
    except Exception as update_error:
        print(f"Error updating global loss tracker collection: {update_error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update Advanced Cycles Trader collections schema")
    parser.add_argument("--email", required=True, help="Admin email for PocketBase")
    parser.add_argument("--password", required=True, help="Admin password for PocketBase")
    parser.add_argument("--local", action="store_true", help="Use local PocketBase server instead of remote")

    args = parser.parse_args()
    update_act_collections_schema(args.email, args.password, args.local) 