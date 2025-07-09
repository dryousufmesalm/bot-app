import sys
import requests
import json
import argparse
from urllib.parse import urljoin
from Api.APIHandler import API
from Views.globals.app_configs import AppConfigs


def update_pocketbase_schema(admin_email, admin_password):
    print("PocketBase Schema Updater")
    print("=========================")
    print("This script will update the 'cycles_trader_cycles' collection schema to add new fields.")

    # Get base URL from app configs
    base_url = AppConfigs().pb_url
    collection_id = "cycles_trader_cycles"  # The ID of the collection

    print(f"Using PocketBase URL: {base_url}")

    # First, authenticate to get a token
    auth_url = urljoin(
        base_url, "/api/collections/_superusers/auth-with-password")
    auth_data = {
        "identity": admin_email,
        "password": admin_password
    }

    try:
        auth_response = requests.post(auth_url, json=auth_data)
        auth_response.raise_for_status()

        # Extract the token
        token = auth_response.json()["token"]
        print("Authentication successful")

        # Get the collection details first
        collection_url = urljoin(base_url, f"/api/collections/{collection_id}")
        headers = {"Authorization": f"Bearer {token}"}

        collection_response = requests.get(collection_url, headers=headers)
        collection_response.raise_for_status()

        collection_data = collection_response.json()
        print(f"Found collection: {collection_data['name']}")

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
        current_schema = collection_data.get("schema", [])

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

        update_response = requests.patch(
            collection_url,
            headers=headers,
            json=update_data
        )
        update_response.raise_for_status()

        print(
            f"Collection schema updated successfully with {len(fields_to_add)} new fields")

        # List the added fields
        for field in fields_to_add:
            print(f"  - Added field: {field['name']} ({field['type']})")

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Error status code: {e.response.status_code}")
                print(f"Error response: {e.response.text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update PocketBase schema")
    parser.add_argument("--email", required=True,
                        help="Admin email for PocketBase")
    parser.add_argument("--password", required=True,
                        help="Admin password for PocketBase")

    args = parser.parse_args()
    update_pocketbase_schema(args.email, args.password)
