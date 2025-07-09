#!/usr/bin/env python3
"""
Missing Order Recovery Utility

This script provides manual tools to detect, organize, and recover missing orders
that exist in MT5 but aren't properly associated with cycles in the system.

Usage:
    python missing_order_recovery.py --action detect
    python missing_order_recovery.py --action recover
    python missing_order_recovery.py --action force_sync
"""

import argparse
import asyncio
import sys
import os
from datetime import datetime

# Add the bot app directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Views.globals.app_logger import app_logger as logger
from DB.db_engine import engine
from Bots.bot import Bot
from MetaTrader.MT5 import MT5


class MissingOrderRecovery:
    """Utility class for detecting and recovering missing orders"""
    
    def __init__(self):
        self.db_engine = engine
        
    async def detect_missing_orders(self, bot_id=None):
        """Detect missing orders across all bots or a specific bot"""
        try:
            logger.info("🔍 Starting missing order detection...")
            
            # Get all bots or specific bot
            if bot_id:
                bots = [Bot.get_bot_by_id(bot_id)]
                if not bots[0]:
                    logger.error(f"Bot {bot_id} not found")
                    return False
            else:
                bots = Bot.get_all_bots()
            
            total_missing = 0
            
            for bot in bots:
                try:
                    logger.info(f"🔍 Checking bot {bot.id} ({bot.name})")
                    
                    # Initialize MetaTrader connection
                    if not hasattr(bot, 'meta_trader') or not bot.meta_trader:
                        logger.warning(f"Bot {bot.id} has no MetaTrader connection")
                        continue
                    
                    # Get all MT5 positions for this bot
                    mt5_positions = bot.meta_trader.get_all_positions()
                    if not mt5_positions:
                        logger.info(f"No MT5 positions found for bot {bot.id}")
                        continue
                    
                    # Filter by magic number and symbol
                    relevant_positions = []
                    for pos in mt5_positions:
                        if (hasattr(pos, 'magic') and pos.magic == bot.magic_number and 
                            hasattr(pos, 'symbol') and pos.symbol == bot.symbol):
                            relevant_positions.append(pos)
                    
                    if not relevant_positions:
                        logger.info(f"No relevant positions for bot {bot.id}")
                        continue
                    
                    logger.info(f"Bot {bot.id} has {len(relevant_positions)} relevant MT5 positions")
                    
                    # Get tracked orders from database
                    tracked_orders = self._get_tracked_orders_from_db(bot.id)
                    tracked_tickets = {order['ticket'] for order in tracked_orders}
                    
                    logger.info(f"Bot {bot.id} tracks {len(tracked_tickets)} orders in database")
                    
                    # Find missing orders
                    missing_orders = []
                    for pos in relevant_positions:
                        ticket = getattr(pos, 'ticket', 0)
                        if ticket and int(ticket) not in tracked_tickets:
                            missing_orders.append(pos)
                    
                    if missing_orders:
                        logger.warning(f"🔍 Bot {bot.id} has {len(missing_orders)} missing orders:")
                        for pos in missing_orders:
                            logger.warning(f"   - Ticket {pos.ticket}: {getattr(pos, 'type', 'Unknown')} at {getattr(pos, 'price_open', 0.0)}")
                        total_missing += len(missing_orders)
                    else:
                        logger.info(f"✅ Bot {bot.id} has no missing orders")
                        
                except Exception as e:
                    logger.error(f"Error checking bot {bot.id}: {e}")
            
            logger.info(f"🎯 Detection complete: {total_missing} total missing orders found")
            return total_missing > 0
            
        except Exception as e:
            logger.error(f"Error in missing order detection: {e}")
            return False
    
    async def recover_missing_orders(self, bot_id=None):
        """Recover missing orders by organizing them into cycles"""
        try:
            logger.info("🔄 Starting missing order recovery...")
            
            # Get all bots or specific bot
            if bot_id:
                bots = [Bot.get_bot_by_id(bot_id)]
                if not bots[0]:
                    logger.error(f"Bot {bot_id} not found")
                    return False
            else:
                bots = Bot.get_all_bots()
            
            total_recovered = 0
            
            for bot in bots:
                try:
                    logger.info(f"🔄 Recovering missing orders for bot {bot.id} ({bot.name})")
                    
                    # Initialize strategy if not already done
                    if not hasattr(bot, 'strategy') or not bot.strategy:
                        logger.warning(f"Bot {bot.id} has no active strategy")
                        continue
                    
                    # Trigger the missing order detection and organization
                    if hasattr(bot.strategy, '_force_sync_all_cycles_with_mt5'):
                        bot.strategy._force_sync_all_cycles_with_mt5()
                        logger.info(f"✅ Force sync completed for bot {bot.id}")
                        total_recovered += 1
                    else:
                        logger.warning(f"Bot {bot.id} strategy doesn't support force sync")
                        
                except Exception as e:
                    logger.error(f"Error recovering orders for bot {bot.id}: {e}")
            
            logger.info(f"🎯 Recovery complete: {total_recovered} bots processed")
            return total_recovered > 0
            
        except Exception as e:
            logger.error(f"Error in missing order recovery: {e}")
            return False
    
    async def force_sync_all_bots(self):
        """Force synchronization of all bots with MT5"""
        try:
            logger.info("🔄 Starting force sync for all bots...")
            
            bots = Bot.get_all_bots()
            synced_count = 0
            
            for bot in bots:
                try:
                    logger.info(f"🔄 Force syncing bot {bot.id} ({bot.name})")
                    
                    # Initialize strategy if not already done
                    if not hasattr(bot, 'strategy') or not bot.strategy:
                        logger.warning(f"Bot {bot.id} has no active strategy")
                        continue
                    
                    # Trigger force sync
                    if hasattr(bot.strategy, '_force_sync_all_cycles_with_mt5'):
                        bot.strategy._force_sync_all_cycles_with_mt5()
                        logger.info(f"✅ Force sync completed for bot {bot.id}")
                        synced_count += 1
                    else:
                        logger.warning(f"Bot {bot.id} strategy doesn't support force sync")
                        
                except Exception as e:
                    logger.error(f"Error force syncing bot {bot.id}: {e}")
            
            logger.info(f"🎯 Force sync complete: {synced_count} bots synced")
            return synced_count > 0
            
        except Exception as e:
            logger.error(f"Error in force sync: {e}")
            return False
    
    def _get_tracked_orders_from_db(self, bot_id):
        """Get tracked orders from database for a specific bot"""
        try:
            # This would query the database for orders associated with the bot
            # For now, return empty list - implement based on your database schema
            return []
        except Exception as e:
            logger.error(f"Error getting tracked orders from DB: {e}")
            return []
    
    def generate_recovery_report(self, bot_id=None):
        """Generate a detailed recovery report"""
        try:
            logger.info("📊 Generating recovery report...")
            
            report = {
                'timestamp': datetime.utcnow().isoformat(),
                'bots_checked': 0,
                'total_missing_orders': 0,
                'total_recovered_orders': 0,
                'bot_details': []
            }
            
            # Get bots
            if bot_id:
                bots = [Bot.get_bot_by_id(bot_id)]
                if not bots[0]:
                    logger.error(f"Bot {bot_id} not found")
                    return report
            else:
                bots = Bot.get_all_bots()
            
            for bot in bots:
                try:
                    bot_detail = {
                        'bot_id': bot.id,
                        'bot_name': bot.name,
                        'symbol': bot.symbol,
                        'magic_number': bot.magic_number,
                        'missing_orders': 0,
                        'recovered_orders': 0,
                        'active_cycles': 0
                    }
                    
                    # Count active cycles
                    if hasattr(bot, 'strategy') and bot.strategy and hasattr(bot.strategy, 'active_cycles'):
                        bot_detail['active_cycles'] = len(bot.strategy.active_cycles)
                    
                    # Count missing orders (simplified)
                    if hasattr(bot, 'meta_trader') and bot.meta_trader:
                        mt5_positions = bot.meta_trader.get_all_positions()
                        if mt5_positions:
                            relevant_positions = [
                                pos for pos in mt5_positions
                                if (hasattr(pos, 'magic') and pos.magic == bot.magic_number and 
                                    hasattr(pos, 'symbol') and pos.symbol == bot.symbol)
                            ]
                            bot_detail['missing_orders'] = len(relevant_positions)
                    
                    report['bot_details'].append(bot_detail)
                    report['bots_checked'] += 1
                    report['total_missing_orders'] += bot_detail['missing_orders']
                    
                except Exception as e:
                    logger.error(f"Error generating report for bot {bot.id}: {e}")
            
            # Log report summary
            logger.info(f"📊 Recovery Report Summary:")
            logger.info(f"   Bots checked: {report['bots_checked']}")
            logger.info(f"   Total missing orders: {report['total_missing_orders']}")
            logger.info(f"   Total active cycles: {sum(bot['active_cycles'] for bot in report['bot_details'])}")
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating recovery report: {e}")
            return {}


async def main():
    """Main function for command-line usage"""
    parser = argparse.ArgumentParser(description='Missing Order Recovery Utility')
    parser.add_argument('--action', choices=['detect', 'recover', 'force_sync', 'report'], 
                       required=True, help='Action to perform')
    parser.add_argument('--bot-id', help='Specific bot ID to process (optional)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Set up logging
    if args.verbose:
        logger.setLevel('DEBUG')
    
    recovery = MissingOrderRecovery()
    
    try:
        if args.action == 'detect':
            success = await recovery.detect_missing_orders(args.bot_id)
            if success:
                logger.info("✅ Missing orders detected")
            else:
                logger.info("✅ No missing orders found")
                
        elif args.action == 'recover':
            success = await recovery.recover_missing_orders(args.bot_id)
            if success:
                logger.info("✅ Missing orders recovered")
            else:
                logger.warning("⚠️ No recovery performed")
                
        elif args.action == 'force_sync':
            success = await recovery.force_sync_all_bots()
            if success:
                logger.info("✅ Force sync completed")
            else:
                logger.warning("⚠️ Force sync failed")
                
        elif args.action == 'report':
            report = recovery.generate_recovery_report(args.bot_id)
            logger.info("✅ Recovery report generated")
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 