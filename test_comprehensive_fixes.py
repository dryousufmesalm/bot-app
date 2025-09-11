#!/usr/bin/env python
"""
Comprehensive test script for MoveGuard fixes
This script tests both symbol update and magic number update functionality
"""

import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Api.APIHandler import API

class MockPocketBaseClient:
    """Mock PocketBase client for testing"""
    def __init__(self):
        self.bots = [
            MockBot("bot1", "Bot 1", "acc1", 12345),
            MockBot("bot2", "Bot 2", "acc1", 67890),
        ]
        self.symbols = [
            MockSymbol("sym1", "EURUSD", "acc1"),
            MockSymbol("sym2", "GBPUSD", "acc1"),
            MockSymbol("sym3", "BTCUSDm", "acc1")
        ]
    
    def collection(self, collection_name):
        if collection_name == "bots":
            return MockBotsCollection(self.bots)
        elif collection_name == "symbols":
            return MockSymbolsCollection(self.symbols)
        return None

class MockBotsCollection:
    """Mock bots collection"""
    def __init__(self, bots):
        self.bots = bots
    
    def get_full_list(self, limit, filters=None):
        if filters and "id = " in str(filters):
            # Extract bot ID from filter
            import re
            match = re.search(r"id = '([^']+)'", str(filters))
            if match:
                bot_id = match.group(1)
                # Find bot by ID
                for bot in self.bots:
                    if bot.id == bot_id:
                        return [bot]
        return []
    
    def update(self, bot_id, data):
        # Find bot by ID
        for bot in self.bots:
            if bot.id == bot_id:
                # Update the bot data
                for key, value in data.items():
                    setattr(bot, key, value)
                return bot
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

class MockBot:
    """Mock bot object"""
    def __init__(self, bot_id, name, account, magic_number):
        self.id = bot_id
        self.name = name
        self.account = account
        self.magic_number = magic_number

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
        logger.info("🧪 Testing symbol update fix")
        
        # Create mock client
        mock_client = MockPocketBaseClient()
        
        # Create API handler with mock client
        api = API("https://test.com")
        api.client = mock_client
        
        # Test getting symbol by name
        symbol_records = api.get_symbol_by_name("EURUSD", "acc1")
        
        if symbol_records and len(symbol_records) > 0:
            logger.info(f"✅ Successfully found symbol: {symbol_records[0].name}")
            symbol_record = symbol_records[0]
            
            # Test updating symbol
            symbol_data = {"price": 1.0850}
            result = api.update_symbol(symbol_record.id, symbol_data)
            
            if result:
                logger.info(f"✅ Successfully updated symbol price to {symbol_data['price']}")
                return True
            else:
                logger.error("❌ Failed to update symbol")
                return False
        else:
            logger.error("❌ Failed to find symbol by name")
            return False
        
    except Exception as e:
        logger.error(f"❌ Symbol update test failed: {str(e)}")
        return False

def test_magic_number_update():
    """Test that the magic number update works correctly"""
    try:
        logger.info("🧪 Testing magic number update")
        
        # Create mock client
        mock_client = MockPocketBaseClient()
        
        # Create API handler with mock client
        api = API("https://test.com")
        api.client = mock_client
        
        # Test getting bot by ID using the correct method name
        bot_records = api.get_account_bots_by_id("bot1")
        
        if bot_records and len(bot_records) > 0:
            bot_record = bot_records[0]
            old_magic = bot_record.magic_number
            logger.info(f"✅ Found bot: {bot_record.name} with magic number: {old_magic}")
            
            # Test updating magic number
            new_magic = 54321
            result = api.update_bot_magic_number("bot1", new_magic)
            
            if result:
                logger.info(f"✅ Successfully updated magic number from {old_magic} to {new_magic}")
                return True
            else:
                logger.error("❌ Failed to update magic number")
                return False
        else:
            logger.error("❌ Failed to find bot by ID")
            return False
        
    except Exception as e:
        logger.error(f"❌ Magic number update test failed: {str(e)}")
        return False

def test_error_handling():
    """Test that error handling works correctly"""
    try:
        logger.info("🧪 Testing error handling")
        
        # Create mock client
        mock_client = MockPocketBaseClient()
        
        # Create API handler with mock client
        api = API("https://test.com")
        api.client = mock_client
        
        # Test with non-existent bot
        result = api.update_bot_magic_number("nonexistent", 12345)
        if result is None:
            logger.info("✅ Correctly handled non-existent bot")
        else:
            logger.error("❌ Unexpectedly updated non-existent bot")
            return False
        
        # Test with non-existent symbol
        result = api.get_symbol_by_name("INVALID", "acc1")
        if not result or len(result) == 0:
            logger.info("✅ Correctly handled non-existent symbol")
        else:
            logger.error("❌ Unexpectedly found non-existent symbol")
            return False
        
        logger.info("✅ All error handling tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {str(e)}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting Comprehensive MoveGuard Fixes Test Suite")
    
    try:
        # Test symbol update fix
        if not test_symbol_update_fix():
            logger.error("❌ Symbol update fix test failed")
            return False
        
        # Test magic number update
        if not test_magic_number_update():
            logger.error("❌ Magic number update test failed")
            return False
        
        # Test error handling
        if not test_error_handling():
            logger.error("❌ Error handling test failed")
            return False
        
        logger.info("🎉 All comprehensive tests passed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test suite failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
