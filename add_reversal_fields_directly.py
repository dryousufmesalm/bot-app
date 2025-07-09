#!/usr/bin/env python3
"""
Directly add reversal trading fields to PocketBase collection schema
"""

import os
import sys
import requests
import json
import logging
from datetime import datetime
from Views.globals.app_logger import app_logger as logger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def add_reversal_fields():
    """Add reversal trading fields directly to collection schema"""
    try:
        # Get PocketBase URL from environment or use default
        pb_url = os.environ.get("POCKETBASE_URL", "https://pdapp.fppatrading.com")
        
        # Admin credentials
        admin_email = os.environ.get("POCKETBASE_ADMIN_EMAIL", "dev@mail.com")
        admin_password = os.environ.get("POCKETBASE_ADMIN_PASSWORD", "1223334444")
        
        # Authenticate as admin using the superusers collection
        auth_data = {
            "identity": admin_email,
            "password": admin_password
        }
        
        logger.info(f"Authenticating to PocketBase at {pb_url}")
        auth_response = requests.post(f"{pb_url}/api/collections/_superusers/auth-with-password", json=auth_data)
        
        if auth_response.status_code != 200:
            # Try standard admin authentication if superusers fails
            logger.warning("Superusers authentication failed, trying standard admin authentication")
            admin_auth_response = requests.post(f"{pb_url}/api/admins/auth-with-password", json={
                "email": admin_email,
                "password": admin_password
            })
            
            if admin_auth_response.status_code != 200:
                logger.error(f"All authentication methods failed: {auth_response.text}")
                return False
                
            auth_token = admin_auth_response.json().get("token")
        else:
            auth_token = auth_response.json().get("token")
        
        if not auth_token:
            logger.error("No authentication token received")
            return False
        
        logger.info("Authentication successful")
        
        # Set up headers for API requests
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        
        # Get list of collections to find the cycles collection
        logger.info("Getting list of collections")
        collections_response = requests.get(f"{pb_url}/api/collections", headers=headers)
        
        if collections_response.status_code != 200:
            logger.error(f"Failed to get collections: {collections_response.text}")
            return False
        
        collections = collections_response.json().get("items", [])
        collection_names = [c.get("name") for c in collections]
        logger.info(f"Available collections: {collection_names}")
        
        # Try to find the cycles collection with the correct name
        target_collection_name = "advanced_cycles_trader_cycles"
        cycles_collection = next((c for c in collections if c.get("name") == target_collection_name), None)
        
        if not cycles_collection:
            logger.error(f"Collection '{target_collection_name}' not found")
            logger.info("Trying alternative collection names...")
            
            # Try alternative collection names if the primary one is not found
            alternative_names = ["cycles", "cycle", "Cycles", "ACT_cycles"]
            
            for name in alternative_names:
                cycles_collection = next((c for c in collections if c.get("name") == name), None)
                if cycles_collection:
                    logger.info(f"Found alternative collection with name: {name}")
                    break
        
        if not cycles_collection:
            logger.error("Cycles collection not found with any expected name")
            return False
        
        cycles_id = cycles_collection.get("id")
        cycles_name = cycles_collection.get("name")
        logger.info(f"Using collection: {cycles_name} (ID: {cycles_id})")
        
        # Get current schema
        logger.info(f"Getting current schema for collection {cycles_name}")
        schema_response = requests.get(f"{pb_url}/api/collections/{cycles_id}", headers=headers)
        
        if schema_response.status_code != 200:
            logger.error(f"Failed to get collection schema: {schema_response.text}")
            return False
        
        collection_data = schema_response.json()
        schema = collection_data.get("schema", [])
        
        # Define new fields to add
        new_fields = [
            {
                "name": "reversal_threshold_pips",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": 0, "max": 10000, "noDecimal": False}
            },
            {
                "name": "highest_buy_price",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": 0, "max": None, "noDecimal": False}
            },
            {
                "name": "lowest_sell_price",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": 0, "max": None, "noDecimal": False}
            },
            {
                "name": "reversal_count",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": 0, "max": None, "noDecimal": True}
            },
            {
                "name": "closed_orders_pl",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": None, "max": None, "noDecimal": False}
            },
            {
                "name": "open_orders_pl",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": None, "max": None, "noDecimal": False}
            },
            {
                "name": "total_cycle_pl",
                "type": "number",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": None, "max": None, "noDecimal": False}
            },
            {
                "name": "last_reversal_time",
                "type": "date",
                "system": False,
                "required": False,
                "unique": False,
                "options": {"min": "", "max": ""}
            },
            {
                "name": "reversal_history",
                "type": "json",
                "system": False,
                "required": False,
                "unique": False,
                "options": {}
            }
        ]
        
        # Check if fields already exist and add only new ones
        existing_field_names = [field.get("name") for field in schema]
        fields_to_add = []
        
        for field in new_fields:
            if field["name"] not in existing_field_names:
                fields_to_add.append(field)
                logger.info(f"Adding field: {field['name']}")
            else:
                logger.info(f"Field already exists: {field['name']}")
        
        if not fields_to_add:
            logger.info("All fields already exist in the schema")
            return True
        
        # Add new fields to schema
        schema.extend(fields_to_add)
        
        # Update collection schema
        logger.info(f"Updating schema for collection {cycles_name}")
        update_data = {
            "schema": schema
        }
        
        update_response = requests.patch(
            f"{pb_url}/api/collections/{cycles_id}",
            headers=headers,
            json=update_data
        )
        
        # If PATCH fails, try PUT instead
        if update_response.status_code >= 400:
            logger.warning(f"PATCH request failed with status {update_response.status_code}. Trying PUT request.")
            update_response = requests.put(
                f"{pb_url}/api/collections/{cycles_id}",
                headers=headers,
                json=collection_data  # Send the full collection data for PUT
            )
        
        if update_response.status_code < 400:
            logger.info("Schema updated successfully")
            
            # Verify fields were added
            verify_response = requests.get(
                f"{pb_url}/api/collections/{cycles_id}",
                headers=headers
            )
            
            if verify_response.status_code == 200:
                updated_schema = verify_response.json().get("schema", [])
                updated_field_names = [field.get("name") for field in updated_schema]
                
                all_fields_added = True
                for field in fields_to_add:
                    if field["name"] not in updated_field_names:
                        logger.warning(f"Field not found after update: {field['name']}")
                        all_fields_added = False
                    else:
                        logger.info(f"Field verified: {field['name']}")
                
                if all_fields_added:
                    logger.info("All fields were successfully added to the schema")
                    return True
                else:
                    logger.error("Some fields were not added to the schema")
                    return False
            else:
                logger.error(f"Failed to verify schema update: {verify_response.text}")
                return False
        else:
            logger.error(f"Failed to update schema: {update_response.text}")
            try:
                error_content = update_response.text
                logger.error(f"Error response: {error_content}")
            except:
                pass
            return False
        
    except Exception as e:
        logger.error(f"Error adding reversal fields: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    logger.info("Starting direct addition of reversal trading fields")
    success = add_reversal_fields()
    
    if success:
        logger.info("Reversal trading fields added successfully")
        sys.exit(0)
    else:
        logger.error("Failed to add reversal trading fields")
        sys.exit(1) 