#!/usr/bin/env python3
"""
Live Order Data Update Script
Adds functionality to update order data with live MetaTrader information
"""

import sys
import os
import datetime
import logging

# Add the bot app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Views.globals.app_logger import logger

def add_live_data_update_to_cycle():
    """Add live data update method to ACT_cycle.py"""
    
    cycle_file_path = "cycles/ACT_cycle.py"
    
    # Read the current file
    try:
        with open(cycle_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if the method already exists
        if "def update_orders_with_live_data(self):" in content:
            logger.info("✅ Live data update method already exists in ACT_cycle.py")
            return True
        
        # Find the update_cycle_status method and modify it
        old_method = '''    def update_cycle_status(self):
        """Update the cycle status and check for completion"""
        try:
            if self.is_closed:
                return
            
            # Check order statuses
            self._update_order_statuses()
            
            # Check if cycle should be closed
            if self._should_close_cycle():
                self.close_cycle("natural_completion")
            
            # Update database
            self._update_cycle_in_database()
            
        except Exception as e:
            logger.error(f"Error updating cycle status: {e}")'''
        
        new_method = '''    def update_cycle_status(self):
        """Update the cycle status and check for completion"""
        try:
            if self.is_closed:
                return
            
            # Update orders with live data from MetaTrader
            self.update_orders_with_live_data()
            
            # Check order statuses
            self._update_order_statuses()
            
            # Check if cycle should be closed
            if self._should_close_cycle():
                self.close_cycle("natural_completion")
            
            # Update database
            self._update_cycle_in_database()
            
        except Exception as e:
            logger.error(f"Error updating cycle status: {e}")

    def update_orders_with_live_data(self):
        """Update all active orders with live data from MetaTrader"""
        try:
            if not self.active_orders:
                return
            
            # Get all current positions from MetaTrader
            positions = []
            if hasattr(self.meta_trader, 'get_positions'):
                positions = self.meta_trader.get_positions()
            elif hasattr(self.meta_trader, 'get_all_positions'):
                positions = self.meta_trader.get_all_positions()
            
            if not positions:
                logger.debug(f"No positions found in MetaTrader for cycle {self.id}")
                return
            
            # Create a lookup dict for positions by ticket
            positions_dict = {}
            for pos in positions:
                ticket = getattr(pos, 'ticket', None)
                if ticket:
                    positions_dict[int(ticket)] = pos
            
            # Update each active order with live data
            updated_count = 0
            total_profit_updated = 0.0
            
            for order in self.active_orders:
                try:
                    ticket = order.get('ticket')
                    if not ticket or int(ticket) not in positions_dict:
                        continue
                    
                    # Get live position data
                    live_pos = positions_dict[int(ticket)]
                    
                    # Store old profit for comparison
                    old_profit = order.get('profit', 0.0)
                    
                    # Update order with live data
                    order['profit'] = float(getattr(live_pos, 'profit', order.get('profit', 0.0)))
                    order['swap'] = float(getattr(live_pos, 'swap', order.get('swap', 0.0)))
                    order['commission'] = float(getattr(live_pos, 'commission', order.get('commission', 0.0)))
                    
                    # Update open price if it was 0 or missing
                    live_open_price = float(getattr(live_pos, 'price_open', 0.0))
                    if live_open_price > 0 and order.get('open_price', 0.0) == 0.0:
                        order['open_price'] = live_open_price
                        logger.info(f"Updated order {ticket} open price: {live_open_price}")
                    
                    # Update volume if it was missing
                    live_volume = float(getattr(live_pos, 'volume', 0.0))
                    if live_volume > 0 and order.get('volume', 0.0) == 0.0:
                        order['volume'] = live_volume
                        logger.info(f"Updated order {ticket} volume: {live_volume}")
                    
                    # Update SL/TP if they exist
                    order['sl'] = float(getattr(live_pos, 'sl', order.get('sl', 0.0)))
                    order['tp'] = float(getattr(live_pos, 'tp', order.get('tp', 0.0)))
                    
                    # Add current price for reference
                    current_price = float(getattr(live_pos, 'price_current', 0.0))
                    if current_price > 0:
                        order['current_price'] = current_price
                    
                    # Log profit changes
                    if abs(order['profit'] - old_profit) > 0.01:  # If profit changed by more than 1 cent
                        logger.debug(f"Order {ticket} profit updated: {old_profit:.2f} -> {order['profit']:.2f}")
                    
                    total_profit_updated += order['profit']
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Error updating order {order.get('ticket', 'unknown')}: {e}")
            
            # Calculate and update total profit for the cycle
            total_profit = sum(order.get('profit', 0.0) for order in self.active_orders)
            total_profit += sum(order.get('profit', 0.0) for order in self.completed_orders)
            self.total_profit = total_profit
            
            if updated_count > 0:
                logger.debug(f"Cycle {self.id}: Updated {updated_count} orders, Total profit: {total_profit:.2f}")
            
        except Exception as e:
            logger.error(f"Error updating orders with live data: {e}")'''
        
        # Replace the method
        if old_method in content:
            content = content.replace(old_method, new_method)
            
            # Write back to file
            with open(cycle_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info("✅ Successfully added live data update functionality to ACT_cycle.py")
            logger.info("📊 Orders will now be updated with:")
            logger.info("   - Real-time profit/loss")
            logger.info("   - Actual open prices") 
            logger.info("   - Live swap and commission")
            logger.info("   - Current market prices")
            logger.info("   - Volume and SL/TP data")
            
            return True
        else:
            logger.error("❌ Could not find update_cycle_status method to modify")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error updating ACT_cycle.py: {e}")
        return False

def main():
    """Main function"""
    logger.info("🔧 Adding Live Order Data Update Functionality")
    logger.info("=" * 50)
    
    success = add_live_data_update_to_cycle()
    
    if success:
        logger.info("\n✅ SUCCESS!")
        logger.info("The ACT system will now:")
        logger.info("1. Fetch live order data from MetaTrader every cycle update")
        logger.info("2. Update profit/loss in real-time")
        logger.info("3. Fill in missing open prices and volumes")
        logger.info("4. Save updated data to the database")
        logger.info("\nYou should now see real order data instead of zeros in the database!")
    else:
        logger.error("\n❌ FAILED!")
        logger.error("Could not add live data functionality.")
        logger.error("Please check the file manually.")

if __name__ == "__main__":
    main() 