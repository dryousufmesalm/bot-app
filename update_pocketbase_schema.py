import sys
import requests
import json
import argparse
from urllib.parse import urljoin
from pocketbase import PocketBase, Client
from Api.APIHandler import API
from Views.globals.app_configs import AppConfigs


def update_pocketbase_schema(admin_email, admin_password, use_local=False):
    print("PocketBase Schema Updater")
    print("=========================")
    print("This script will update the 'cycles_trader_cycles' collection schema to add new fields.")

    # Get base URL from app configs or use local if specified
    base_url = "http://127.0.0.1:8090" if use_local else AppConfigs().pb_url
    collection_id = "cycles_trader_cycles"  # The ID of the collection

    print(f"Using PocketBase URL: {base_url}")

    try:
        # Initialize PocketBase client
        client = PocketBase(base_url)

        # Try to list the collections first to verify connectivity
        print("Testing API connectivity...")
        try:
            collections = client.collections.get_list(1, 1)
            print(
                f"API connection successful. Found {collections.total_items} collections.")
        except Exception as conn_error:
            print(f"Error connecting to API: {conn_error}")
            return

        # Authenticate admin
        print(f"Authenticating as admin ({admin_email})...")
        try:
            auth_data = client.admins.auth_with_password(
                admin_email, admin_password)
            print("Authentication successful")
        except Exception as auth_error:
            print(f"Admin authentication failed: {auth_error}")
            return

        # Get the collection details
        print(f"Getting collection: {collection_id}")
        try:
            collection_data = client.collections.get_one(collection_id)
            print(f"Found collection: {collection_data.name}")
        except Exception as coll_error:
            print(f"Error getting collection: {coll_error}")
            return

        # Define new schema fields to add
        new_fields = [
            {
                "name": "done_price_levels",
                "type": "json",
                "required": False
            },
            {
                "name": "current_direction",
                "type": "text",
                "required": False,
                "options": {
                    "default": "BUY"
                }
            },
            {
                "name": "initial_threshold_price",
                "type": "number",
                "required": False,
                "options": {
                    "default": 0.0
                }
            },
            {
                "name": "direction_switched",
                "type": "bool",
                "required": False,
                "options": {
                    "default": False
                }
            },
            {
                "name": "next_order_index",
                "type": "number",
                "required": False,
                "options": {
                    "default": 0,
                    "min": 0
                }
            }
        ]

        # Get current schema
        current_schema = collection_data.schema

        # Check for fields that already exist
        existing_field_names = [field.get("name") for field in current_schema]
        fields_to_add = [field for field in new_fields
                         if field["name"] not in existing_field_names]

        if not fields_to_add:
            print("All fields already exist in the collection schema")
            return

        # Add new fields to the schema
        updated_schema = current_schema + fields_to_add

        # Update the collection schema
        update_data = {
            "schema": updated_schema
        }

        try:
            client.collections.update(collection_id, update_data)
            print(
                f"Collection schema updated successfully with {len(fields_to_add)} new fields")

            # List the added fields
            for field in fields_to_add:
                print(f"  - Added field: {field['name']} ({field['type']})")
        except Exception as update_error:
            print(f"Error updating collection schema: {update_error}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update PocketBase schema")
    parser.add_argument("--email", required=True,
                        help="Admin email for PocketBase")
    parser.add_argument("--password", required=True,
                        help="Admin password for PocketBase")
    parser.add_argument("--local", action="store_true",
                        help="Use local PocketBase server instead of remote")

    args = parser.parse_args()
    update_pocketbase_schema(args.email, args.password, args.local)
