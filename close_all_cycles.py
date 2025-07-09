#!/usr/bin/env python3
"""
Close All Cycles Script
Utility to close all active cycles for a bot
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# Add the bot app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Api.APIHandler import API
from Views.globals.app_logger import logger

class CycleCloser:
    def __init__(self, base_url, username, password):
        self.api = API(base_url)
        self.username = username
        self.password = password
        self.authenticated = False
    
    def authenticate(self):
        """Authenticate with PocketBase"""
        try:
            result = self.api.login(self.username, self.password)
            if result:
                self.authenticated = True
                logger.info("✅ Successfully authenticated with PocketBase")
                return True
            else:
                logger.error("❌ Failed to authenticate with PocketBase")
                return False
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            return False
    
    def close_all_cycles_for_bot(self, bot_id):
        """Close all active cycles for a specific bot"""
        try:
            if not self.authenticated:
                logger.error("Not authenticated. Cannot close cycles.")
                return False
            
            logger.info(f"🔍 Fetching all cycles for bot {bot_id}")
            
            # Get all cycles for this bot
            cycles = self.api.get_cycles_by_bot(bot_id)
            
            if not cycles:
                logger.info("No cycles found for this bot")
                return True
            
            logger.info(f"Found {len(cycles)} cycles for bot {bot_id}")
            
            closed_count = 0
            for cycle in cycles:
                try:
                    if not getattr(cycle, 'is_closed', True):  # Only close if not already closed
                        logger.info(f"Closing cycle {cycle.id} (Status: {getattr(cycle, 'status', 'unknown')})")
                        
                        # Update cycle to closed status
                        update_data = {
                            'is_closed': True,
                            'close_reason': f'manual_close_all_by_{self.username}',
                            'close_time': datetime.utcnow().isoformat(),
                            'status': 'closed'
                        }
                        
                        result = self.api.update_cycle(cycle.id, update_data)
                        if result:
                            closed_count += 1
                            logger.info(f"✅ Cycle {cycle.id} closed successfully")
                        else:
                            logger.error(f"❌ Failed to close cycle {cycle.id}")
                    else:
                        logger.info(f"Cycle {cycle.id} already closed")
                        
                except Exception as e:
                    logger.error(f"Error closing cycle {cycle.id}: {e}")
            
            logger.info(f"✅ Closed {closed_count} cycles for bot {bot_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing all cycles: {e}")
            return False
    
    def list_all_cycles_for_bot(self, bot_id):
        """List all cycles for a specific bot"""
        try:
            if not self.authenticated:
                logger.error("Not authenticated. Cannot list cycles.")
                return False
            
            logger.info(f"🔍 Listing all cycles for bot {bot_id}")
            
            # Get all cycles for this bot
            cycles = self.api.get_cycles_by_bot(bot_id)
            
            if not cycles:
                logger.info("No cycles found for this bot")
                return True
            
            logger.info(f"Found {len(cycles)} cycles for bot {bot_id}:")
            
            for i, cycle in enumerate(cycles, 1):
                status = "CLOSED" if getattr(cycle, 'is_closed', True) else "ACTIVE"
                symbol = getattr(cycle, 'symbol', 'unknown')
                direction = getattr(cycle, 'direction', 'unknown')
                entry_price = getattr(cycle, 'entry_price', 0)
                
                logger.info(f"  {i}. ID: {cycle.id}")
                logger.info(f"     Status: {status}")
                logger.info(f"     Symbol: {symbol}")
                logger.info(f"     Direction: {direction}")
                logger.info(f"     Entry Price: {entry_price}")
                logger.info("")
            
            return True
            
        except Exception as e:
            logger.error(f"Error listing cycles: {e}")
            return False

def main():
    """Main function"""
    # Configuration
    BASE_URL = "https://pocketbase.patricktrad.com"  # Update this to your PocketBase URL
    USERNAME = input("Enter PocketBase username: ").strip()
    PASSWORD = input("Enter PocketBase password: ").strip()
    
    if not USERNAME or not PASSWORD:
        print("Username and password are required")
        return
    
    # Create cycle closer
    closer = CycleCloser(BASE_URL, USERNAME, PASSWORD)
    
    # Authenticate
    if not closer.authenticate():
        print("Failed to authenticate. Exiting.")
        return
    
    # Get bot ID
    bot_id = input("Enter Bot ID (or 'list' to see all bots): ").strip()
    
    if bot_id.lower() == 'list':
        # TODO: Add functionality to list all bots
        print("Bot listing not implemented yet. Please provide the Bot ID directly.")
        return
    
    if not bot_id:
        print("Bot ID is required")
        return
    
    # Ask what to do
    action = input("Choose action: (l)ist cycles, (c)lose all cycles: ").strip().lower()
    
    if action == 'l' or action == 'list':
        closer.list_all_cycles_for_bot(bot_id)
    elif action == 'c' or action == 'close':
        confirm = input(f"Are you sure you want to close ALL cycles for bot {bot_id}? (yes/no): ").strip().lower()
        if confirm == 'yes':
            closer.close_all_cycles_for_bot(bot_id)
        else:
            print("Operation cancelled")
    else:
        print("Invalid action. Use 'l' for list or 'c' for close")

if __name__ == "__main__":
    main() 