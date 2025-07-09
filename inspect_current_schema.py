#!/usr/bin/env python3
"""
Script to inspect the current advanced_cycles_trader_cycles collection schema
"""

from Api.APIHandler import API
import json

def inspect_collection_schema():
    """Inspect the current collection schema"""
    
    # Initialize API client
    api_client = API("https://pdapp.fppatrading.com")
    
    # Authenticate
    print("Authenticating with PocketBase...")
    login_result = api_client.login("dev@mail.com", "1223334444")
    
    if not login_result:
        print("❌ Authentication failed!")
        return False
    
    print(f"✅ Authentication successful! User: {api_client.user_email}")
    
    # Try to get existing cycles to understand the current schema
    print("\n🔍 Checking existing cycles...")
    try:
        cycles = api_client.get_all_ACT_active_cycles()
        print(f"📊 Found {len(cycles)} existing cycles")
        
        if cycles:
            print("📋 Sample cycle structure:")
            sample_cycle = cycles[0]
            for key, value in sample_cycle.__dict__.items():
                print(f"  {key}: {type(value).__name__}")
        
    except Exception as e:
        print(f"⚠️ Could not fetch cycles: {e}")
    
    # Try to create a minimal test cycle to see what fields are missing
    print("\n🧪 Testing minimal cycle creation...")
    minimal_data = {
        "cycle_id": "SCHEMA_TEST_001",
        "bot_id": "test_bot",
        "account": "test_account",
        "symbol": "XAUUSD",
        "magic_number": 12345,
        "entry_price": 2650.50,
        "lot_size": 0.01,
        "direction": "BUY",
        "current_direction": "BUY",
        "zone_base_price": 2650.50,
        "initial_threshold_price": 2655.50,
        "zone_threshold_pips": 50.0,
        "order_interval_pips": 50.0,
        "batch_stop_loss_pips": 300.0
    }
    
    try:
        result = api_client.create_ACT_cycle(minimal_data)
        if result:
            print("✅ Minimal cycle creation successful!")
            print(f"   Created cycle ID: {result.id}")
            
            # Clean up
            api_client.delete_ACT_cycle(result.id)
            print("🧹 Test cycle cleaned up")
            return True
        else:
            print("❌ Minimal cycle creation failed")
            return False
            
    except Exception as e:
        error_str = str(e)
        print(f"❌ Cycle creation failed: {error_str}")
        
        # Analyze the error for clues about missing fields
        if "400" in error_str:
            print("\n💡 400 Error Analysis:")
            print("This suggests the collection exists but has validation issues.")
            print("Possible causes:")
            print("- Missing required fields in the collection schema")
            print("- Field type mismatches")
            print("- Validation rules not met")
            
        elif "404" in error_str:
            print("\n💡 404 Error Analysis:")
            print("This suggests the collection doesn't exist at all.")
            print("The migration was likely never applied to the remote instance.")
            
        return False

def test_different_field_combinations():
    """Test different field combinations to identify the exact schema"""
    
    api_client = API("https://pdapp.fppatrading.com")
    api_client.login("dev@mail.com", "1223334444")
    
    # Test with progressively more fields
    test_cases = [
        {
            "name": "Absolute minimal",
            "data": {
                "cycle_id": "TEST_MIN_001"
            }
        },
        {
            "name": "Basic required",
            "data": {
                "cycle_id": "TEST_BASIC_001",
                "bot_id": "test_bot",
                "account": "test_account",
                "symbol": "XAUUSD"
            }
        },
        {
            "name": "With numbers",
            "data": {
                "cycle_id": "TEST_NUM_001",
                "bot_id": "test_bot", 
                "account": "test_account",
                "symbol": "XAUUSD",
                "magic_number": 12345,
                "entry_price": 2650.50,
                "lot_size": 0.01
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"\n🧪 Testing: {test_case['name']}")
        try:
            result = api_client.create_ACT_cycle(test_case['data'])
            if result:
                print(f"✅ SUCCESS with {len(test_case['data'])} fields")
                api_client.delete_ACT_cycle(result.id)
                return test_case['data'].keys()
            else:
                print(f"❌ Failed with {len(test_case['data'])} fields")
        except Exception as e:
            print(f"❌ Error with {len(test_case['data'])} fields: {e}")
    
    return None

if __name__ == "__main__":
    print("🔍 COLLECTION SCHEMA INSPECTION")
    print("=" * 50)
    
    success = inspect_collection_schema()
    
    if not success:
        print("\n🧪 RUNNING PROGRESSIVE FIELD TESTS")
        print("=" * 50)
        working_fields = test_different_field_combinations()
        
        if working_fields:
            print(f"\n✅ Found working field combination: {list(working_fields)}")
        else:
            print("\n❌ No working field combination found")
            print("\n💡 RECOMMENDATION:")
            print("The collection likely doesn't exist or has a completely different schema.")
            print("You may need to create the collection manually through the PocketBase admin interface.") 