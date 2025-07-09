#!/usr/bin/env python3
"""
Apply reversal trading migration to PocketBase
"""

import os
import sys
import requests
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def apply_migration():
    """Apply reversal trading migration to PocketBase"""
    try:
        # Get PocketBase URL from environment or use default
        pb_url = os.environ.get("POCKETBASE_URL", "https://pdapp.fppatrading.com")
        
        # Admin credentials
        admin_email = os.environ.get("POCKETBASE_ADMIN_EMAIL", "dev@mail.com")
        admin_password = os.environ.get("POCKETBASE_ADMIN_PASSWORD", "1223334444")
        
        # Migration file path
        migration_file = "pb_migrations/1750743300_add_reversal_trading_fields.js"
        
        # Check if migration file exists
        if not os.path.exists(migration_file):
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        # Read migration file content
        with open(migration_file, "r") as f:
            migration_content = f.read()
            
        logger.info(f"Read migration file: {migration_file}")
        
        # Authenticate as admin
        logger.info(f"Authenticating to PocketBase at {pb_url}")
        
        # Try authentication methods in order
        auth_token = None
        
        # Method 1: Standard admin authentication
        try:
            auth_response = requests.post(
                f"{pb_url}/api/admins/auth-with-password",
                json={"email": admin_email, "password": admin_password}
            )
            
            if auth_response.status_code == 200:
                auth_token = auth_response.json().get("token")
                logger.info("Standard admin authentication successful")
            else:
                logger.warning(f"Standard admin authentication failed: {auth_response.status_code}")
        except Exception as e:
            logger.warning(f"Standard admin authentication error: {e}")
        
        # Method 2: Superusers authentication
        if not auth_token:
            try:
                auth_response = requests.post(
                    f"{pb_url}/api/collections/_superusers/auth-with-password",
                    json={"identity": admin_email, "password": admin_password}
                )
                
                if auth_response.status_code == 200:
                    auth_token = auth_response.json().get("token")
                    logger.info("Superusers authentication successful")
                else:
                    logger.warning(f"Superusers authentication failed: {auth_response.status_code}")
            except Exception as e:
                logger.warning(f"Superusers authentication error: {e}")
        
        if not auth_token:
            logger.error("All authentication methods failed")
            return False
        
        # Set up headers for API requests
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        
        # Get list of collections to find the cycles collection
        logger.info("Getting list of collections")
        collections_response = requests.get(f"{pb_url}/api/collections", headers=headers)
        
        if collections_response.status_code != 200:
            logger.error(f"Failed to get collections: {collections_response.status_code}")
            return False
        
        collections = collections_response.json().get("items", [])
        
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
        logger.info(f"Found cycles collection with ID: {cycles_id}")
        
        # Try multiple endpoints for applying migrations
        endpoints = [
            f"{pb_url}/api/collections/{cycles_id}/apply-migration",
            f"{pb_url}/api/collections/{cycles_name}/apply-migration",
            f"{pb_url}/api/migrate/apply",
            f"{pb_url}/api/migrate"
        ]
        
        success = False
        
        for endpoint in endpoints:
            try:
                logger.info(f"Trying endpoint: {endpoint}")
                
                # Prepare migration data
                migration_data = {
                    "file": migration_file,
                    "content": migration_content
                }
                
                # For the general migrate endpoint, include collection info
                if "migrate/apply" in endpoint or endpoint.endswith("/migrate"):
                    migration_data["collection"] = cycles_name
                
                # Apply migration
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=migration_data
                )
                
                if response.status_code < 400:
                    logger.info(f"Migration applied successfully via {endpoint}")
                    success = True
                    break
                else:
                    logger.warning(f"Endpoint {endpoint} failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.warning(f"Error with endpoint {endpoint}: {e}")
        
        if success:
            logger.info("Migration applied successfully")
            return True
        
        # If all endpoints fail, try direct schema update as fallback
        logger.warning("All migration endpoints failed, trying direct schema update")
        
        # Get current schema
        logger.info(f"Getting current schema for collection {cycles_name}")
        schema_response = requests.get(f"{pb_url}/api/collections/{cycles_id}", headers=headers)
        
        if schema_response.status_code != 200:
            logger.error(f"Failed to get collection schema: {schema_response.status_code}")
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
            return True
        else:
            logger.error(f"Failed to update schema: {update_response.status_code} - {update_response.text}")
            return False
        
    except Exception as e:
        logger.error(f"Error applying migration: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    logger.info("Starting reversal trading migration")
    success = apply_migration()
    
    if success:
        logger.info("Reversal trading migration completed successfully")
        sys.exit(0)
    else:
        logger.error("Reversal trading migration failed")
        sys.exit(1) 