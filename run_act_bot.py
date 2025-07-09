#!/usr/bin/env python3
"""
Simple script to run the Advanced Cycles Trader bot without GUI
This demonstrates the ACT strategy working with minimal setup
"""

import sys
import time
import logging
from datetime import datetime
from unittest.mock import Mock, MagicMock

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('act_bot_demo.log')
    ]
)

logger = logging.getLogger(__name__)

def create_mock_metatrader():
    """Create a mock MetaTrader instance for demonstration"""
    mt = Mock()
    mt.account_id = "12345"
    mt.account_info.return_value = {
        'balance': 10000.0,
        'equity': 10000.0,
        'margin': 0.0,
        'free_margin': 10000.0,
        'margin_level': 0.0
    }
    mt.symbol_info.return_value = {
        'bid': 1.1000,
        'ask': 1.1002,
        'spread': 2,
        'digits': 5,
        'point': 0.00001
    }
    mt.symbol_info_tick.return_value = {
        'bid': 1.1000,
        'ask': 1.1002,
        'time': datetime.now().timestamp()
    }
    mt.copy_rates_from_pos.return_value = [
        {
            'time': datetime.now().timestamp(),
            'open': 1.1000,
            'high': 1.1010,
            'low': 1.0990,
            'close': 1.1005,
            'tick_volume': 1000,
            'spread': 2,
            'real_volume': 0
        }
    ]
    
    # Add the get_bid and get_ask methods that AdvancedCyclesTrader expects
    mt.get_bid.return_value = 1.1000
    mt.get_ask.return_value = 1.1002
    
    return mt

def create_mock_bot():
    """Create a mock bot instance"""
    bot = Mock()
    bot.id = "test_bot_123"
    bot.magic_number = 12345  # This is the key fix!
    bot.strategy_name = "Advanced Cycles Trader"
    bot.symbol_name = "EURUSD"
    return bot

def create_mock_client():
    """Create a mock PocketBase client"""
    client = Mock()
    client.get_account_bots_by_id.return_value = [Mock()]
    client.get_strategy_by_id.return_value = [Mock()]
    return client

def run_act_demo():
    """Run the Advanced Cycles Trader demonstration"""
    try:
        logger.info("🚀 Starting Advanced Cycles Trader Demo")
        logger.info("=" * 50)
        
        # Create mock components
        meta_trader = create_mock_metatrader()
        bot = create_mock_bot()
        client = create_mock_client()
        
        # Configuration for ACT strategy
        config = {
            "symbol": "EURUSD",
            "zone_threshold_pips": 50.0,
            "order_interval_pips": 25.0,
            "batch_stop_loss_pips": 200.0,
            "zone_range_pips": 100.0,
            "lot_size": 0.01,
            "take_profit_pips": 100.0,
            "stop_loss_pips": 50.0
        }
        
        logger.info(f"📊 Configuration: {config}")
        
        # Import and initialize the Advanced Cycles Trader
        from Strategy.AdvancedCyclesTrader_Organized import AdvancedCyclesTrader
        
        logger.info("🏗️  Initializing Advanced Cycles Trader...")
        strategy = AdvancedCyclesTrader(
            meta_trader=meta_trader,
            config=config,
            client=client,
            symbol="EURUSD",
            bot=bot
        )
        
        # Initialize the strategy
        logger.info("⚙️  Initializing strategy components...")
        if strategy.initialize():
            logger.info("✅ Strategy initialized successfully!")
        else:
            logger.error("❌ Strategy initialization failed!")
            return False
        
        # Set entry price to start monitoring
        entry_price = 1.1000
        strategy.set_entry_price(entry_price)
        logger.info(f"📌 Entry price set to: {entry_price}")
        
        # Start the strategy
        logger.info("🎯 Starting strategy...")
        if strategy.start_strategy():
            logger.info("✅ Strategy started successfully!")
        else:
            logger.error("❌ Strategy start failed!")
            return False
        
        # Run for a short demonstration period
        logger.info("⏱️  Running strategy for 10 seconds...")
        demo_duration = 10
        
        for i in range(demo_duration):
            time.sleep(1)
            logger.info(f"⏰ Demo running... {i+1}/{demo_duration} seconds")
            
            # Simulate price movement
            current_price = entry_price + (0.0005 * (i % 3))  # Small price fluctuations
            strategy.current_market_price = current_price
            
            if i == 5:
                # Simulate threshold breach at 5 seconds
                threshold_price = entry_price + 0.0050  # 50 pips
                strategy.current_market_price = threshold_price
                logger.info(f"📈 Simulated price movement to {threshold_price} (threshold breach)")
        
        # Stop the strategy
        logger.info("🛑 Stopping strategy...")
        if strategy.stop_strategy():
            logger.info("✅ Strategy stopped successfully!")
        else:
            logger.error("❌ Strategy stop failed!")
        
        # Get final statistics
        stats = strategy.get_strategy_statistics()
        logger.info("📊 Final Statistics:")
        for key, value in stats.items():
            logger.info(f"   {key}: {value}")
        
        logger.info("=" * 50)
        logger.info("🎉 Advanced Cycles Trader Demo Completed Successfully!")
        return True
        
    except Exception as e:
        logger.error(f"💥 Demo failed with error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = run_act_demo()
    if success:
        print("\n✅ Demo completed successfully! Check 'act_bot_demo.log' for detailed logs.")
        sys.exit(0)
    else:
        print("\n❌ Demo failed! Check 'act_bot_demo.log' for error details.")
        sys.exit(1) 