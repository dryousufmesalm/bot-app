import sys
import os
import json
import logging
import datetime
from Api.APIHandler import API

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])

def serialize_datetime_objects(obj):
    """Helper function to serialize datetime objects for JSON"""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return obj

def create_minimal_cycle_data():
    """Create minimal data required for cycle creation"""
    return {
        "cycle_id": f"test_cycle_{int(datetime.datetime.now().timestamp())}",
        "bot": "REPLACE_WITH_VALID_BOT_ID",  # Replace with a valid bot ID
        "account": "REPLACE_WITH_VALID_ACCOUNT_ID",  # Replace with a valid account ID
        "symbol": "EURUSD",
        "magic_number": 12345,
        "direction": "BUY",
        "current_direction": "BUY",
        "entry_price": 1.1234,
        "lot_size": 0.01,
        "zone_base_price": 1.1234,
        "initial_threshold_price": 1.1234,
        "zone_threshold_pips": 50.0,
        "order_interval_pips": 10.0,
        "batch_stop_loss_pips": 100.0,
        "is_closed": False,
        "is_active": True,
        # JSON fields that need serialization
        "active_orders": json.dumps([]),
        "completed_orders": json.dumps([]),
        "orders": json.dumps([]),
        "done_price_levels": json.dumps([]),
        "opened_by": json.dumps({"user": "diagnostic_script"}),
        "closing_method": json.dumps({}),
        "batch_losses": json.dumps([]),
        "orders_config": json.dumps({})
    }

def get_collection_schema(api_client, collection_name):
    """Get the schema for a specific collection"""
    try:
        collections = api_client.get_all_collections()
        for collection in collections:
            if collection.name == collection_name:
                return collection.schema
        logging.error(f"Collection {collection_name} not found")
        return None
    except Exception as e:
        logging.error(f"Error getting collection schema: {e}")
        return None

def validate_data_against_schema(data, schema):
    """Validate data against schema and return issues"""
    issues = []
    
    if not schema:
        issues.append("Schema not available for validation")
        return issues
    
    # Check required fields
    for field in schema:
        if field.get('required', False) and field['name'] not in data:
            issues.append(f"Required field '{field['name']}' is missing")
        
        # Check field types
        if field['name'] in data:
            value = data[field['name']]
            field_type = field.get('type')
            
            # Check select fields
            if field_type == 'select' and value not in field.get('options', {}).get('values', []):
                issues.append(f"Field '{field['name']}' has invalid value '{value}'. Allowed values: {field.get('options', {}).get('values', [])}")
            
            # Check number fields
            if field_type == 'number' and not isinstance(value, (int, float)):
                issues.append(f"Field '{field['name']}' should be a number, got {type(value).__name__}")
            
            # Check JSON fields
            if field_type == 'json' and not isinstance(value, str):
                issues.append(f"Field '{field['name']}' should be a JSON string, got {type(value).__name__}")
    
    return issues

def test_cycle_creation(api_client):
    """Test cycle creation with minimal data and diagnose issues"""
    try:
        # Get the schema
        schema = get_collection_schema(api_client, "advanced_cycles_trader_cycles")
        if not schema:
            logging.error("Could not retrieve schema for validation")
            return False
        
        # Create minimal data
        data = create_minimal_cycle_data()
        
        # Validate against schema
        issues = validate_data_against_schema(data, schema)
        if issues:
            logging.error("Schema validation issues:")
            for issue in issues:
                logging.error(f"- {issue}")
            return False
        
        # Try to create the cycle
        logging.info("Attempting to create test cycle...")
        result = api_client.create_ACT_cycle(data)
        
        if result:
            logging.info(f"✅ Test cycle created successfully with ID: {result.id}")
            return True
        else:
            logging.error("❌ Failed to create test cycle")
            return False
            
    except Exception as e:
        logging.error(f"Error in test_cycle_creation: {e}")
        return False

def main():
    """Main function"""
    try:
        # Initialize API client
        base_url = input("Enter PocketBase URL (default: http://127.0.0.1:8090): ") or "http://127.0.0.1:8090"
        api_client = API(base_url)
        
        # Login
        username = input("Enter username: ")
        password = input("Enter password: ")
        login_result = api_client.login(username, password)
        
        if not login_result:
            logging.error("Failed to login")
            return
        
        logging.info("Login successful")
        
        # Get a valid bot ID and account ID
        bot_id = input("Enter a valid bot ID: ")
        account_id = input("Enter a valid account ID: ")
        
        # Update the test data with valid IDs
        test_data = create_minimal_cycle_data()
        test_data["bot"] = bot_id
        test_data["account"] = account_id
        
        # Print the test data
        logging.info("Test data:")
        logging.info(json.dumps(test_data, indent=2, default=serialize_datetime_objects))
        
        # Confirm before proceeding
        confirm = input("Proceed with test? (y/n): ").lower()
        if confirm != 'y':
            logging.info("Test cancelled")
            return
        
        # Run the test
        test_result = test_cycle_creation(api_client)
        
        if test_result:
            logging.info("Diagnostic test completed successfully")
        else:
            logging.error("Diagnostic test failed")
            
    except Exception as e:
        logging.error(f"Error in main: {e}")

if __name__ == "__main__":
    main() 