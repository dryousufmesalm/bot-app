#!/usr/bin/env python
"""
Test script for MoveGuard symbol update functionality
This script tests the new symbol update capability in the MoveGuard strategy
"""

import sys
import os
import asyncio
from Views.globals.app_logger import app_logger as logger

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Strategy.MoveGuard import MoveGuard
from MetaTrader.MT5 import MetaTrader
from Bots.account import Account
from Api.APIHandler import API

class MockBot:
    """Mock bot object for testing"""
    def __init__(self, magic_number=12345):
        self.id = "test_bot_123"
        self.magic_number = magic_number
        self.account = None

class MockClient:
    """Mock API client for testing"""
    def __init__(self):
        pass
    
    def update_bot_magic_number(self, bot_id, magic_number):
        """Mock magic number update"""
        logger.info(f"Mock: Updated bot {bot_id} magic number to {magic_number}")
        return True

class MockMetaTrader:
    """Mock MetaTrader for testing"""
    def __init__(self):
        self.magic_number = 12345
        self.symbols = {
            'EURUSD': MockSymbolInfo('EURUSD', 0.0001),
            'GBPUSD': MockSymbolInfo('GBPUSD', 0.0001),
            'USDJPY': MockSymbolInfo('USDJPY', 0.01)
        }
    
    def initialize(self, path):
        """Mock initialization"""
        return True
    
    def get_symbol_info(self, symbol):
        """Mock symbol info retrieval"""
        return self.symbols.get(symbol)
    
    def get_bid(self, symbol):
        """Mock bid price"""
        if symbol == 'EURUSD':
            return 1.0850
        elif symbol == 'GBPUSD':
            return 1.2650
        elif symbol == 'USDJPY':
            return 148.50
        return None
    
    def get_ask(self, symbol):
        """Mock ask price"""
        if symbol == 'EURUSD':
            return 1.0852
        elif symbol == 'GBPUSD':
            return 1.2652
        elif symbol == 'USDJPY':
            return 148.52
        return None

class MockSymbolInfo:
    """Mock symbol information"""
    def __init__(self, name, point):
        self.name = name
        self.point = point

async def test_symbol_update():
    """Test the MoveGuard symbol update functionality"""
    try:
        logger.info("🧪 Starting MoveGuard symbol update test")
        
        # Create mock objects
        mock_bot = MockBot()
        mock_client = MockClient()
        mock_mt = MockMetaTrader()
        
        # Create test configuration
        test_config = {
            'lot_size': 0.01,
            'initial_entry_interval_pips': 50.0,
            'subsequent_entry_interval_pips': 50.0,
            'initial_order_sl_pips': 100.0,
            'recovery_sl_pips': 200.0,
            'cycle_take_profit_pips': 100.0,
            'zone_size_pips': 300.0,
            'max_cycles': 3,
            'max_trades_per_cycle': 50
        }
        
        # Initialize MoveGuard strategy with EURUSD
        logger.info("🔄 Initializing MoveGuard strategy with EURUSD")
        strategy = MoveGuard(mock_mt, test_config, mock_client, "EURUSD", mock_bot)
        
        # Verify initial symbol
        initial_symbol = strategy.symbol
        logger.info(f"✅ Initial symbol: {initial_symbol}")
        assert initial_symbol == "EURUSD", f"Expected EURUSD, got {initial_symbol}"
        
        # Test symbol update to GBPUSD
        logger.info("🔄 Testing symbol update to GBPUSD")
        update_config = test_config.copy()
        update_config['symbol'] = 'GBPUSD'
        
        # Call the configuration update method
        strategy._initialize_strategy_configuration(update_config)
        
        # Verify symbol was updated
        updated_symbol = strategy.symbol
        logger.info(f"✅ Updated symbol: {updated_symbol}")
        assert updated_symbol == "GBPUSD", f"Expected GBPUSD, got {updated_symbol}"
        
        # Test symbol update to USDJPY
        logger.info("🔄 Testing symbol update to USDJPY")
        update_config['symbol'] = 'USDJPY'
        
        # Call the configuration update method
        strategy._initialize_strategy_configuration(update_config)
        
        # Verify symbol was updated
        final_symbol = strategy.symbol
        logger.info(f"✅ Final symbol: {final_symbol}")
        assert final_symbol == "USDJPY", f"Expected USDJPY, got {final_symbol}"
        
        # Test invalid symbol (should fail gracefully)
        logger.info("🔄 Testing invalid symbol update")
        invalid_config = test_config.copy()
        invalid_config['symbol'] = 'INVALID_SYMBOL'
        
        # Call the configuration update method
        strategy._initialize_strategy_configuration(invalid_config)
        
        # Verify symbol was NOT updated (should remain USDJPY)
        current_symbol = strategy.symbol
        logger.info(f"✅ Current symbol after invalid update: {current_symbol}")
        assert current_symbol == "USDJPY", f"Expected USDJPY to remain unchanged, got {current_symbol}"
        
        logger.info("🎉 All MoveGuard symbol update tests passed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting MoveGuard Symbol Update Test Suite")
    
    try:
        # Run the async test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test_symbol_update())
        loop.close()
        
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

