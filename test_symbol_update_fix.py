#!/usr/bin/env python
"""
Test script for MoveGuard symbol update fix
This script tests that the 404 errors in symbol updates have been resolved
"""

import sys
import os
from Views.globals.app_logger import app_logger as logger

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Api.APIHandler import API

class MockPocketBaseClient:
    """Mock PocketBase client for testing"""
    def __init__(self):
        self.symbols = [
            MockSymbol("sym1", "EURUSD", "acc1"),
            MockSymbol("sym2", "GBPUSD", "acc1"),
            MockSymbol("sym3", "BTCUSDm", "acc1")
        ]
    
    def collection(self, collection_name):
        if collection_name == "symbols":
            return MockSymbolsCollection(self.symbols)
        return None

class MockSymbolsCollection:
    """Mock symbols collection"""
    def __init__(self, symbols):
        self.symbols = symbols
    
    def get_full_list(self, limit, filters=None):
        if filters and "name = " in str(filters):
            # Extract symbol name from filter
            import re
            match = re.search(r"name = '([^']+)'", str(filters))
            if match:
                symbol_name = match.group(1)
                # Find symbol by name
                for symbol in self.symbols:
                    if symbol.name == symbol_name:
                        return [symbol]
        return []
    
    def update(self, symbol_id, data):
        # Find symbol by ID
        for symbol in self.symbols:
            if symbol.id == symbol_id:
                # Update the symbol data
                for key, value in data.items():
                    setattr(symbol, key, value)
                return True
        return False

class MockSymbol:
    """Mock symbol object"""
    def __init__(self, symbol_id, name, account):
        self.id = symbol_id
        self.name = name
        self.account = account
        self.price = 1.0

def test_symbol_update_fix():
    """Test that the symbol update fix works correctly"""
    try:
        logger.info("🧪 Testing MoveGuard symbol update fix")
        
        # Create mock client
        mock_client = MockPocketBaseClient()
        
        # Create API handler with mock client
        api = API("https://test.com")
        api.client = mock_client
        
        # Test getting symbol by name
        logger.info("🔄 Testing get_symbol_by_name method")
        symbol_records = api.get_symbol_by_name("EURUSD", "acc1")
        
        if symbol_records and len(symbol_records) > 0:
            logger.info(f"✅ Successfully found symbol: {symbol_records[0].name}")
            symbol_record = symbol_records[0]
            
            # Test updating symbol
            logger.info("🔄 Testing symbol update")
            symbol_data = {"price": 1.0850}
            result = api.update_symbol(symbol_record.id, symbol_data)
            
            if result:
                logger.info(f"✅ Successfully updated symbol price to {symbol_data['price']}")
            else:
                logger.error("❌ Failed to update symbol")
                return False
        else:
            logger.error("❌ Failed to find symbol by name")
            return False
        
        # Test with non-existent symbol
        logger.info("🔄 Testing with non-existent symbol")
        non_existent_symbols = api.get_symbol_by_name("INVALID", "acc1")
        if not non_existent_symbols or len(non_existent_symbols) == 0:
            logger.info("✅ Correctly handled non-existent symbol")
        else:
            logger.error("❌ Unexpectedly found non-existent symbol")
            return False
        
        logger.info("🎉 All symbol update fix tests passed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting MoveGuard Symbol Update Fix Test Suite")
    
    try:
        result = test_symbol_update_fix()
        
        if result:
            logger.info("✅ All tests completed successfully!")
            return True
        else:
            logger.error("❌ Some tests failed!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test suite failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

