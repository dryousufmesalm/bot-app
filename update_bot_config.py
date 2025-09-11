#!/usr/bin/env python
"""
Script to update bot configuration for Advanced Cycles Trader
Usage: python update_bot_config.py <bot_id> [--zone-threshold=300] [--order-interval=50] [--lot-size=0.01]
"""

import sys
import argparse
from Views.globals.app_logger import app_logger as logger
from DB.db_engine import engine
from Api.APIHandler import API
from Bots.account import Account
from MetaTrader.MT5 import MetaTrader
import asyncio
import json

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Update bot configuration')
    parser.add_argument('bot_id', help='Bot ID to update')
    parser.add_argument('--symbol', help='Trading symbol (e.g., EURUSD, GBPUSD)')
    parser.add_argument('--zone-threshold', type=float, help='Zone threshold in pips')
    parser.add_argument('--order-interval', type=float, help='Order interval in pips')
    parser.add_argument('--lot-size', type=float, help='Lot size')
    parser.add_argument('--max-cycles', type=int, help='Maximum active cycles')
    parser.add_argument('--take-profit', type=float, help='Take profit in pips')
    parser.add_argument('--stop-loss', type=float, help='Stop loss in pips')
    parser.add_argument('--config-file', help='JSON file with configuration updates')
    parser.add_argument('--server-url', default='https://patrick-display-server.pockethost.io', help='PocketBase server URL')
    
    return parser.parse_args()

async def update_bot_configuration(bot_id, config_updates, server_url):
    """Update bot configuration"""
    try:
        # Initialize API client
        api_client = API(server_url)
        
        # Get bot data
        bot_data = api_client.get_account_bots_by_id(bot_id)
        if not bot_data or len(bot_data) == 0:
            logger.error(f"Bot {bot_id} not found")
            return False
            
        bot_info = bot_data[0]
        
        # Get account data
        account_id = bot_info.account
        account_data = api_client.get_accounts_by_id(account_id)
        if not account_data or len(account_data) == 0:
            logger.error(f"Account {account_id} not found")
            return False
            
        account_info = account_data[0]
        
        # Get MT5 login info from account data directly
        # The API class doesn't have a get_mt5_login_by_id method
        mt_login_info = account_info
        
        # Connect to MetaTrader
        meta_trader = MetaTrader(
            username=mt_login_info.username,
            password=mt_login_info.password,
            server=mt_login_info.server
        )
        
        # Initialize MetaTrader
        if not meta_trader.initialize(""):
            logger.error("Failed to initialize MetaTrader")
            return False
            
        # Create account object
        account = Account(api_client, account_info.id)
        
        # Initialize account
        if not account.initialize():
            logger.error(f"Failed to initialize account {account_info.id}")
            return False
            
        # Get bot
        bot = account.get_bot_by_id(bot_id)
        if not bot:
            logger.error(f"Failed to get bot {bot_id}")
            return False
            
        # Initialize bot
        if not bot.initialize():
            logger.error(f"Failed to initialize bot {bot_id}")
            return False
            
        # Check if bot is Advanced Cycles Trader
        if bot.strategy_name != "Advanced Cycles Trader":
            logger.error(f"Bot {bot_id} is not an Advanced Cycles Trader bot")
            return False
            
        # Update bot configuration
        if not hasattr(bot.strategy, "update_bot_config"):
            logger.error(f"Bot {bot_id} does not support dynamic configuration updates")
            return False
            
        # Update configuration
        result = await bot.strategy.update_bot_config(config_updates)
        
        if result:
            logger.info(f"✅ Bot {bot_id} configuration updated successfully")
            return True
        else:
            logger.error(f"❌ Failed to update bot {bot_id} configuration")
            return False
            
    except Exception as e:
        logger.error(f"Error updating bot configuration: {e}")
        return False

def main():
    """Main function"""
    args = parse_arguments()
    
    # Build configuration updates dictionary
    config_updates = {}
    
    # Load from config file if provided
    if args.config_file:
        try:
            with open(args.config_file, 'r') as f:
                file_config = json.load(f)
                config_updates.update(file_config)
        except Exception as e:
            logger.error(f"Error loading configuration file: {e}")
            return False
    
    # Add command line arguments
    if args.symbol is not None:
        config_updates["symbol"] = args.symbol
    if args.zone_threshold is not None:
        config_updates["zone_threshold_pips"] = args.zone_threshold
    if args.order_interval is not None:
        config_updates["order_interval_pips"] = args.order_interval
    if args.lot_size is not None:
        config_updates["lot_size"] = args.lot_size
    if args.max_cycles is not None:
        config_updates["max_active_cycles"] = args.max_cycles
    if args.take_profit is not None:
        config_updates["take_profit_pips"] = args.take_profit
    if args.stop_loss is not None:
        config_updates["stop_loss_pips"] = args.stop_loss
        
    if not config_updates:
        logger.error("No configuration updates provided")
        return False
        
    # Print configuration updates
    logger.info(f"Updating bot {args.bot_id} with configuration:")
    for key, value in config_updates.items():
        logger.info(f"  {key}: {value}")
    
    # Use the proper event loop handling
    try:
        # Get the current event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create a new event loop if none exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run the update function
    result = loop.run_until_complete(update_bot_configuration(args.bot_id, config_updates, args.server_url))
    
    if result:
        logger.info("Bot configuration updated successfully")
        return True
    else:
        logger.error("Failed to update bot configuration")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 