import datetime
from Orders.order import order
import MetaTrader5 as Mt5
from DB.db_engine import engine
from DB.ct_strategy.repositories.ct_repo import CTRepo
from types import SimpleNamespace
import json
from helpers.sync import verify_order_status, sync_delay, MT5_LOCK
from cycles.CT_cycle import cycle
from Views.globals.app_logger import app_logger as logger
# ACTRepo removed - using in-memory operations
import asyncio
import uuid
from typing import Dict


def serialize_datetime_objects(obj):
    """Recursively serialize datetime objects and other complex types in data structures"""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat() if obj else None
    elif isinstance(obj, datetime.date):
        return obj.isoformat() if obj else None
    elif isinstance(obj, datetime.time):
        return obj.isoformat() if obj else None
    elif isinstance(obj, list):
        return [serialize_datetime_objects(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: serialize_datetime_objects(value) for key, value in obj.items()}
    elif hasattr(obj, '__dict__'):  # Handle custom objects
        return serialize_datetime_objects(obj.__dict__)
    else:
        return obj


def ensure_json_serializable(data):
    """Ensure all fields are JSON serializable"""
    if isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif isinstance(data, (datetime.datetime, datetime.date, datetime.time)):
        return data.isoformat() if data else None
    elif isinstance(data, list):
        return [ensure_json_serializable(item) for item in data]
    elif isinstance(data, dict):
        return {key: ensure_json_serializable(value) for key, value in data.items()}
    elif hasattr(data, '__dict__'):
        return ensure_json_serializable(data.__dict__)
    else:
        try:
            # Try to convert to JSON to test serializability
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            return str(data)  # Convert any other types to string


class AdvancedCycle(cycle):
    """Advanced Cycle with zone-based trading logic and loss accumulation"""

    def __init__(self, cycle_data, meta_trader, bot):
        """Initialize Advanced Cycle with enhanced zone-based features"""
        
        # CRITICAL DEBUG: Check bot parameter
        if bot is None:
            logger.error("🚨 CRITICAL: Bot parameter is None during AdvancedCycle initialization!")
            logger.error(f"   Cycle data: {cycle_data.get('id', 'No ID') if cycle_data else 'None'}")
            raise ValueError("Bot parameter cannot be None")
        
        logger.debug(f"🔧 Creating AdvancedCycle with bot: ID={bot.id}, Name={getattr(bot, 'name', 'Unknown')}")
        
        # CRITICAL FIX: Ensure cycle_data is a dictionary
        if cycle_data is None:
            cycle_data = {}
        elif not isinstance(cycle_data, dict):
            try:
                cycle_data = dict(cycle_data)
            except Exception as e:
                logger.error(f"Failed to convert cycle_data to dictionary: {e}")
                cycle_data = {}
        
        # CRITICAL FIX: Generate temporary cycle_id if not provided
        if 'id' not in cycle_data or not cycle_data['id']:
            temp_id = f"temp_{uuid.uuid4().hex}"
            logger.info(f"Generating temporary cycle_id: {temp_id}")
            cycle_data['id'] = temp_id
        
        # Initialize base cycle class
        super().__init__(cycle_data, meta_trader, bot)
        
        # CRITICAL FIX: Set cycle_id before any other initialization
        self.cycle_id = cycle_data.get('id')
        logger.info(f"Initializing cycle with ID: {self.cycle_id}")
        
        # Advanced Cycle specific properties - use meaningful defaults
        entry_price = cycle_data.get("entry_price", 0.0)
        self.zone_base_price = cycle_data.get("zone_base_price", entry_price if entry_price > 0 else None)
        self.initial_threshold_price = cycle_data.get("initial_threshold_price", None)
        self.current_direction = cycle_data.get("current_direction", "BUY")
        self.direction_switched = cycle_data.get("direction_switched", False)
        self.done_price_levels = cycle_data.get("done_price_levels", [])
        self.next_order_index = cycle_data.get("next_order_index", 1)
        
        # Zone-based trading parameters
        self.zone_threshold_pips = cycle_data.get("zone_threshold_pips", 50.0)
        self.order_interval_pips = cycle_data.get("order_interval_pips", 50.0)
        self.batch_stop_loss_pips = cycle_data.get("batch_stop_loss_pips", 300.0)
        
        # Order management
        self.active_orders = cycle_data.get("active_orders", [])
        self.completed_orders = cycle_data.get("completed_orders", [])
        
        # CRITICAL FIX: Initialize batch_id properly
        self.current_batch_id = cycle_data.get("current_batch_id", None)
        if self.current_batch_id is None and self.cycle_id:
            # Generate initial batch ID using cycle_id if available
            self.current_batch_id = f"batch_{self.cycle_id}_1"
            logger.info(f"Generated initial batch_id: {self.current_batch_id}")
        
        self.last_order_time = cycle_data.get("last_order_time", None)
        self.last_order_price = cycle_data.get("last_order_price", None)
        
        # Loss tracking
        self.accumulated_loss = 0.0
        self.batch_losses = []
        self.direction_switches = 0
        
        # MISSING FIELDS ADDED - Required by Flutter model
        self.zone_activated = cycle_data.get("zone_activated", False)
        self.initial_threshold_breached = cycle_data.get("initial_threshold_breached", False)
        self.zone_based_losses = cycle_data.get("zone_based_losses", 0.0)
        self.batch_stop_loss_triggers = cycle_data.get("batch_stop_loss_triggers", 0)
        
        # NEW: Reversal trading fields
        self.reversal_threshold_pips = cycle_data.get("reversal_threshold_pips", 300.0)
        self.highest_buy_price = cycle_data.get("highest_buy_price", 0.0)
        self.lowest_sell_price = cycle_data.get("lowest_sell_price", float('inf'))
        self.reversal_count = cycle_data.get("reversal_count", 0)
        self.closed_orders_pl = cycle_data.get("closed_orders_pl", 0.0)
        self.open_orders_pl = cycle_data.get("open_orders_pl", 0.0)
        self.total_cycle_pl = cycle_data.get("total_cycle_pl", 0.0)
        self.last_reversal_time = cycle_data.get("last_reversal_time", None)
        self.reversal_history = cycle_data.get("reversal_history", [])
        
        # Database repository
        # ACTRepo removed - using in-memory operations
        
        # Store meta_trader reference
        self.meta_trader = meta_trader
        
        # Cycle state
        self.is_active = True
        self.is_closed = False
        self.close_reason = None
        
        # CRITICAL FIX: Validate initialization
        if not self.cycle_id:
            logger.error("❌ Cycle initialization failed: No cycle_id set")
            raise ValueError("Cycle must have an ID")
        
    def update_orders_with_live_data(self):
        """Update all active orders with live data from MetaTrader"""
        try:
            if not self.active_orders:
                return
            
            # Helper function for safe float conversion
            def safe_float(value, default=0.0):
                """Safely convert any value to float with fallback"""
                if value is None:
                    return float(default)
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return float(default)
            
            # Get all current positions from MetaTrader
            positions = []
            if hasattr(self.meta_trader, 'get_positions'):
                positions = self.meta_trader.get_positions()
            elif hasattr(self.meta_trader, 'get_all_positions'):
                positions = self.meta_trader.get_all_positions()
            
            if not positions:
                logger.debug(f"No positions found in MetaTrader for cycle {self.cycle_id}")
                return
            
            # Create a lookup dict for positions by ticket
            positions_dict = {}
            for pos in positions:
                ticket = getattr(pos, 'ticket', None)
                if ticket:
                    positions_dict[int(ticket)] = pos
            
            # Update each active order with live data - FIXED: Use safe_float to prevent NoneType errors
            updated_count = 0
            for order in self.active_orders:
                try:
                    ticket = order.get('ticket')
                    if not ticket or int(ticket) not in positions_dict:
                        continue
                    
                    # Get live position data
                    live_pos = positions_dict[int(ticket)]
                    
                    # Update order with live data - FIXED: Use safe_float to prevent NoneType errors
                    order['profit'] = safe_float(getattr(live_pos, 'profit', order.get('profit', 0.0)), 0.0)
                    order['swap'] = safe_float(getattr(live_pos, 'swap', order.get('swap', 0.0)), 0.0)
                    order['commission'] = safe_float(getattr(live_pos, 'commission', order.get('commission', 0.0)), 0.0)
                    
                    # Update open price if it was 0 or missing
                    live_open_price = safe_float(getattr(live_pos, 'price_open', 0.0), 0.0)
                    if live_open_price > 0 and order.get('open_price', 0.0) == 0.0:
                        order['open_price'] = live_open_price
                    
                    # Update volume if it was missing
                    live_volume = safe_float(getattr(live_pos, 'volume', 0.0), 0.0)
                    if live_volume > 0 and order.get('volume', 0.0) == 0.0:
                        order['volume'] = live_volume
                    
                    # Update SL/TP if they exist
                    order['sl'] = safe_float(getattr(live_pos, 'sl', order.get('sl', 0.0)), 0.0)
                    order['tp'] = safe_float(getattr(live_pos, 'tp', order.get('tp', 0.0)), 0.0)
                    
                    # Add current price for reference
                    current_price = safe_float(getattr(live_pos, 'price_current', 0.0), 0.0)
                    if current_price > 0:
                        order['current_price'] = current_price
                    
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Error updating order {order.get('ticket', 'unknown')}: {e}")
            
            # Calculate and update total profit for the cycle
            total_profit = sum(order.get('profit', 0.0) for order in self.active_orders)
            total_profit += sum(order.get('profit', 0.0) for order in self.completed_orders)
            self.total_profit = total_profit
            
            if updated_count > 0:
                logger.debug(f"Updated {updated_count} orders with live data - Total profit: {total_profit}")
            
        except Exception as e:
            logger.error(f"Error updating orders with live data: {e}")

    def add_order(self, order_input):
        """Add an order to this cycle and update PocketBase
        
        Args:
            order_input: Should preferably be complete order data object/dict.
                        Can also be int/str ticket number as fallback.
        """
        try:
            order_data = None
            order_ticket = None
            
            # ✅ PRIORITIZE ORDER_DATA OVER TICKET NUMBERS
            if isinstance(order_input, dict):
                # We received complete order data (preferred)
                order_data = order_input
                order_ticket = order_data.get('ticket', 0)
                logger.info(f"🎯 ADDING ORDER {order_ticket} (with complete data) to cycle {self.cycle_id}")
                
            elif hasattr(order_input, '__dict__') and not isinstance(order_input, (int, str)):
                # We received order data object (preferred)
                order_data = order_input
                order_ticket = getattr(order_data, 'ticket', None) or getattr(order_data, 'order', 0)
                logger.info(f"🎯 ADDING ORDER {order_ticket} (with object data) to cycle {self.cycle_id}")
                
            elif isinstance(order_input, (int, str)):
                # Fallback: We received just a ticket number
                order_ticket = int(order_input)
                logger.warning(f"⚠️ Adding order {order_ticket} with ticket only - will fetch data from MetaTrader")
                
                # Try to get detailed order information from MetaTrader
                if hasattr(self.meta_trader, 'get_order_info'):
                    order_data = self.meta_trader.get_order_info(order_ticket)
                    
                # Fallback to position data if order info doesn't work
                if not order_data and hasattr(self.meta_trader, 'get_positions'):
                    positions = self.meta_trader.get_positions()
                    for pos in positions:
                        if getattr(pos, 'ticket', None) == order_ticket:
                            order_data = pos
                            break
                            
            else:
                logger.error(f"❌ Invalid order_input type: {type(order_input)}")
                return False
            
            # Validate we have either order_data or at least a ticket
            if not order_ticket:
                logger.error(f"❌ No valid ticket found in order input: {order_input}")
                return False
            
            logger.info(f"✅ Processing order {order_ticket} for cycle {self.cycle_id}")
            
            # Create order info in Flutter-compatible format
            current_time = datetime.datetime.utcnow()
            
            # Extract order information with safe fallbacks
            def safe_float_extract(data, key, default=0.0):
                """Safely extract and convert a value to float with fallback"""
                try:
                    if hasattr(data, '__dict__'):
                        value = getattr(data, key, default)
                    elif isinstance(data, dict):
                        value = data.get(key, default)
                    else:
                        return default
                    
                    # Check if value is a Mock object (common in tests)
                    if hasattr(value, '_mock_name'):
                        logger.warning(f"Mock object detected for {key}, using default {default}")
                        return default
                    
                    return float(value)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to extract {key} from order data: {e}, using default {default}")
                    return default
            
            if order_data is None:
                # No order data available, use defaults but log warning
                logger.warning(f"No order data available for ticket {order_ticket}, using defaults - will update with live data later")
                volume = 0.01
                price_open = 0.0
                profit = 0.0
                swap = 0.0
                commission = 0.0
                sl = 0.0
                tp = 0.0
                margin = 0.0
            else:
                # Extract order information safely
                volume = safe_float_extract(order_data, 'volume', 0.01)
                price_open = safe_float_extract(order_data, 'price_open', 0.0)
                profit = safe_float_extract(order_data, 'profit', 0.0)
                swap = safe_float_extract(order_data, 'swap', 0.0)
                commission = safe_float_extract(order_data, 'commission', 0.0)
                sl = safe_float_extract(order_data, 'sl', 0.0)
                tp = safe_float_extract(order_data, 'tp', 0.0)
                margin = safe_float_extract(order_data, 'margin', 0.0)
            
            # CRITICAL FIX: Determine order kind and comment
            is_first_order = len(self.active_orders) == 0 and len(self.completed_orders) == 0
            order_kind = "initial" if is_first_order else "recovery"
            
            # Get comment from order data if available
            comment = ""
            if hasattr(order_data, 'comment'):
                comment = getattr(order_data, 'comment', "")
            elif isinstance(order_data, dict) and 'comment' in order_data:
                comment = order_data['comment']
                
            # CRITICAL FIX: Always set initial order comment
            if is_first_order:
                comment = "initial"
            elif not comment:
                order_position = self.next_order_index + 1
                comment = f"rec{order_position}"
            
            order_info = {
                # Flutter CycleOrder required fields
                "ticket": int(order_ticket),
                "kind": order_kind,  # initial, recovery, hedge, max_recovery
                "type": 1 if self.current_direction == "SELL" else 0,  # 0=BUY, 1=SELL
                "open_time": current_time.isoformat(),
                "symbol": self.symbol,
                "volume": volume,
                "open_price": price_open,
                "profit": profit,
                "swap": swap,
                "commission": commission,
                "magic_number": int(self.bot.magic_number),
                "comment": comment,
                "sl": sl,
                "tp": tp,
                "trailing_steps": 0,
                "margin": margin,
                "is_pending": False,
                "is_closed": False,
                "cycle_id": self.cycle_id,
                "cycle_create": current_time.isoformat(),
                
                # Additional ACT-specific tracking fields
                "direction": self.current_direction,
                "batch_id": self.current_batch_id,
                "order_index": self.next_order_index,
                "status": "active"
            }
            
            # ✅ STEP 1: Add order to cycle's active orders
            self.active_orders.append(order_info)
            self.next_order_index += 1
            self.last_order_time = current_time
            
            # CRITICAL FIX: Always update last order price
            self.last_order_price = price_open
            logger.debug(f"Updated last_order_price to {self.last_order_price} for cycle {self.cycle_id}")
            
            logger.info(f"✅ Order {order_ticket} added to cycle {self.cycle_id} - Total active orders: {len(self.active_orders)}")
            logger.info(f"   Order details: {order_info['kind']} {order_info['type']} {order_info['symbol']} {order_info['volume']} @ {order_info['open_price']}")
            
            # ✅ STEP 2: Update cycle in PocketBase via API
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                try:
                    api_client = self.bot.api_client
                    
                    # Prepare update data with the new order
                    update_data = {
                        "active_orders": json.dumps(serialize_datetime_objects(self.active_orders)),
                        "orders": json.dumps(serialize_datetime_objects(self.active_orders + self.completed_orders)),
                        "total_orders": len(self.active_orders) + len(self.completed_orders),
                        "total_volume": sum(order.get('volume', 0.0) for order in self.active_orders + self.completed_orders),
                        "total_profit": sum(order.get('profit', 0.0) for order in self.active_orders + self.completed_orders),
                        "next_order_index": int(self.next_order_index),
                        "last_order_price": float(self.last_order_price) if self.last_order_price else 0.0,
                        "last_order_time": self.last_order_time.isoformat() if self.last_order_time else None,
                        "current_batch_id": str(self.current_batch_id) if self.current_batch_id else None
                    }
                    
                    # Update cycle in PocketBase
                    api_client.update_ACT_cycle_by_id(self.cycle_id, update_data)
                    logger.debug(f"✅ Cycle {self.cycle_id} updated in PocketBase with new order")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to update cycle in PocketBase: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding order to cycle: {e}")
            return False

    def update_cycle_status(self):
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

    def _update_order_statuses(self):
        """Update the status of all active orders"""
        try:
            # Helper function for safe float conversion
            def safe_float(value, default=0.0):
                """Safely convert any value to float with fallback"""
                if value is None:
                    return float(default)
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return float(default)
            
            for order in self.active_orders[:]:  # Copy to avoid modification during iteration
                try:
                    # Check order status with MetaTrader
                    if hasattr(self.meta_trader, 'get_order_info'):
                        order_info = self.meta_trader.get_order_info(order["ticket"])
                        
                        if order_info:
                            order_state = order_info.get('state', 'unknown')
                            
                            if order_state in ['filled', 'closed']:
                                # Move to completed orders - maintain Flutter format
                                order["status"] = "completed"
                                order["is_closed"] = True
                                order["close_time"] = datetime.datetime.utcnow().isoformat()
                                
                                # FIXED: Use safe float conversions to prevent NoneType errors
                                order["close_price"] = safe_float(order_info.get('price_close', 0.0), 0.0)
                                order["profit"] = safe_float(order_info.get('profit', 0.0), 0.0)
                                order["swap"] = safe_float(order_info.get('swap', order.get('swap', 0.0)), 0.0)
                                order["commission"] = safe_float(order_info.get('commission', order.get('commission', 0.0)), 0.0)
                                
                                self.completed_orders.append(order)
                                self.active_orders.remove(order)
                                
                                # Update accumulated loss if order was a loss
                                if order["profit"] < 0:
                                    self.accumulated_loss += abs(order["profit"])
                                
                                logger.info(f"Order {order['ticket']} completed with profit: {order['profit']}")
                        
                except Exception as e:
                    logger.error(f"Error updating order {order['ticket']}: {e}")
                    
        except Exception as e:
            logger.error(f"Error updating order statuses: {e}")

    def _should_close_cycle(self):
        """Determine if the cycle should be closed"""
        try:
            # Close if all orders are completed and profitable
            if len(self.active_orders) == 0 and len(self.completed_orders) > 0:
                total_profit = sum(order.get("profit", 0.0) for order in self.completed_orders)
                if total_profit > 0:
                    return True
            
            # Close if maximum loss threshold reached
            max_loss_threshold = 1000.0  # Configurable
            if self.accumulated_loss > max_loss_threshold:
                return True
            
            # Close if too many direction switches
            max_switches = 5  # Configurable
            if self.direction_switches > max_switches:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if cycle should close: {e}")
            return False

    def close_cycle(self, reason):
        """Close the cycle with specified reason and close all MT5 orders/positions"""
        try:
            if self.is_closed:
                logger.warning(f"Cycle {self.cycle_id} already closed")
                return
            
            self.is_closed = True
            self.is_active = False
            self.close_reason = reason
            self.close_time = datetime.datetime.utcnow()
            
            # Helper function for safe float conversion
            def safe_float(value, default=0.0):
                """Safely convert any value to float with fallback"""
                if value is None:
                    return float(default)
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return float(default)
            
            # Close any remaining active orders/positions in MT5
            closed_count = 0
            failed_count = 0
            
            for order in self.active_orders:
                try:
                    ticket = order.get("ticket")
                    if not ticket:
                        logger.warning(f"Order in cycle {self.cycle_id} has no ticket number")
                        continue
                    
                    # First, get the current position/order data from MT5
                    position_data = None
                    if hasattr(self.meta_trader, 'get_position_by_ticket'):
                        position_data = self.meta_trader.get_position_by_ticket(ticket)
                    
                    if position_data and len(position_data) > 0:
                        # We have an active position - close it
                        position = position_data[0] if isinstance(position_data, list) else position_data
                        
                        # Prepare position data for closing
                        position_for_close = {
                            'ticket': ticket,
                            'symbol': position.get('symbol', self.symbol),
                            'type': position.get('type', 0),  # 0=BUY, 1=SELL
                            'volume': position.get('volume', order.get('volume', 0.01)),
                            'magic_number': position.get('magic', getattr(self.bot, 'magic_number', 0))
                        }
                        
                        # Close the position with standard deviation
                        logger.info(f"🔄 Closing position {ticket} for cycle {self.cycle_id}")
                        result = self.meta_trader.close_position(position_for_close, deviation=20)
                        
                        if result and hasattr(result, 'retcode'):
                            if result.retcode == 10009:  # TRADE_RETCODE_DONE
                                logger.info(f"✅ Successfully closed position {ticket}")
                                closed_count += 1
                            else:
                                logger.error(f"❌ Failed to close position {ticket}: retcode {result.retcode}")
                                failed_count += 1
                        else:
                            logger.error(f"❌ Failed to close position {ticket}: No result or invalid result")
                            failed_count += 1
                    else:
                        # Check if it's a pending order instead
                        order_data = None
                        if hasattr(self.meta_trader, 'get_order_by_ticket'):
                            order_data = self.meta_trader.get_order_by_ticket(ticket)
                        
                        if order_data and len(order_data) > 0:
                            # We have a pending order - cancel it
                            pending_order = order_data[0] if isinstance(order_data, list) else order_data
                            
                            order_for_close = {
                                'ticket': ticket,
                                'symbol': pending_order.get('symbol', self.symbol),
                                'type': pending_order.get('type', 0),
                                'volume': pending_order.get('volume', order.get('volume', 0.01)),
                                'magic_number': pending_order.get('magic', getattr(self.bot, 'magic_number', 0))
                            }
                            
                            logger.info(f"🔄 Canceling pending order {ticket} for cycle {self.cycle_id}")
                            result = self.meta_trader.close_order(order_for_close, deviation=20)
                            
                            if result and hasattr(result, 'retcode'):
                                if result.retcode == 10009:  # TRADE_RETCODE_DONE
                                    logger.info(f"✅ Successfully canceled pending order {ticket}")
                                    closed_count += 1
                                else:
                                    logger.error(f"❌ Failed to cancel pending order {ticket}: retcode {result.retcode}")
                                    failed_count += 1
                            else:
                                logger.error(f"❌ Failed to cancel pending order {ticket}: No result or invalid result")
                                failed_count += 1
                        else:
                            # Order/position not found in MT5 - might already be closed
                            logger.warning(f"⚠️ Order/position {ticket} not found in MT5 - may already be closed")
                    
                    # Update order status in our records
                    order["status"] = "force_closed"
                    order["is_closed"] = True
                    order["close_time"] = datetime.datetime.utcnow().isoformat()
                    order["close_reason"] = reason
                    order["profit"] = safe_float(order.get("profit", 0.0), 0.0)
                    
                    # Move to completed orders
                    self.completed_orders.append(order)
                    
                except Exception as e:
                    logger.error(f"Error closing order {order.get('ticket', 'unknown')} in cycle {self.cycle_id}: {e}")
                    failed_count += 1
            
            # Clear active orders list
            self.active_orders.clear()
            
            # Log closing summary
            total_orders = closed_count + failed_count
            if total_orders > 0:
                logger.info(f"📊 Cycle {self.cycle_id} order closure summary: {closed_count} closed, {failed_count} failed out of {total_orders} total orders")
            else:
                logger.info(f"📊 Cycle {self.cycle_id} had no active orders to close")
            
            # Calculate final statistics
            self._calculate_final_statistics()
            
            # Update database
            self._update_cycle_in_database()
            
            logger.info(f"✅ Cycle {self.cycle_id} closed - Reason: {reason}")
            
        except Exception as e:
            logger.error(f"Error closing cycle {self.cycle_id}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def _calculate_final_statistics(self):
        """Calculate final cycle statistics"""
        try:
            total_orders = len(self.completed_orders)
            total_profit = sum(order.get("profit", 0.0) for order in self.completed_orders)
            winning_orders = len([o for o in self.completed_orders if o.get("profit", 0) > 0])
            losing_orders = len([o for o in self.completed_orders if o.get("profit", 0) < 0])
            
            self.final_statistics = {
                "total_orders": total_orders,
                "total_profit": total_profit,
                "winning_orders": winning_orders,
                "losing_orders": losing_orders,
                "win_rate": (winning_orders / total_orders * 100) if total_orders > 0 else 0,
                "accumulated_loss": self.accumulated_loss,
                "direction_switches": self.direction_switches,
                "duration_minutes": self._calculate_duration_minutes(),
                "price_levels_completed": len(self.done_price_levels)
            }
            
            logger.info(f"Cycle {self.cycle_id} final stats: {self.final_statistics}")
            
        except Exception as e:
            logger.error(f"Error calculating final statistics: {e}")
            self.final_statistics = {"error": str(e)}

    def _calculate_duration_minutes(self):
        """Calculate cycle duration in minutes"""
        try:
            if hasattr(self, 'start_time') and hasattr(self, 'close_time'):
                duration = self.close_time - self.start_time
                return duration.total_seconds() / 60
            return 0
        except Exception as e:
            logger.error(f"Error calculating duration: {e}")
            return 0

    def _check_and_add_missing_orders(self):
        """Check for missing orders in MT5 and add them to the cycle"""
        try:
            if not hasattr(self.meta_trader, 'get_all_positions'):
                logger.warning("MetaTrader does not support position checking")
                return
                
            # Get all positions from MT5 with our magic number
            mt5_positions = self.meta_trader.get_all_positions()
            if not mt5_positions:
                logger.debug(f"No MT5 positions found for cycle {self.cycle_id}")
                return
            
            # Filter positions by magic number and symbol
            relevant_positions = []
            for pos in mt5_positions:
                # CRITICAL FIX: Only add positions that belong to this specific cycle
                # Check magic number and symbol as basic filters
                if not (hasattr(pos, 'magic') and pos.magic == self.bot.magic_number and 
                       hasattr(pos, 'symbol') and pos.symbol == self.symbol):
                    continue
                
                # CRITICAL FIX: Additional verification to ensure order belongs to this cycle
                # Check if the order has a comment that indicates it belongs to this cycle
                comment = getattr(pos, 'comment', '')
                
                # Only add orders that have this cycle's ID in the comment
                # Or orders created during the cycle's lifetime
                if (comment and (self.cycle_id in comment or f"cycle_{self.cycle_id}" in comment)) or \
                   (hasattr(self, 'start_time') and 
                    hasattr(pos, 'time_setup') and 
                    pos.time_setup >= self.start_time.timestamp()):
                    relevant_positions.append(pos)
            
            if not relevant_positions:
                logger.debug(f"No relevant MT5 positions found for cycle {self.cycle_id} (magic: {self.bot.magic_number}, symbol: {self.symbol})")
                return
            
            # Get current order tickets in the cycle
            current_tickets = set()
            for order in self.active_orders + self.completed_orders:
                ticket = order.get('ticket', 0)
                if ticket:
                    current_tickets.add(int(ticket))
            
            logger.debug(f"Cycle {self.cycle_id} currently tracks {len(current_tickets)} orders: {sorted(current_tickets)}")
            logger.debug(f"MT5 has {len(relevant_positions)} relevant positions for this cycle")
            
            # Find missing orders
            missing_orders = []
            for pos in relevant_positions:
                ticket = getattr(pos, 'ticket', 0)
                if ticket and int(ticket) not in current_tickets:
                    missing_orders.append(pos)
            
            # Add missing orders to the cycle
            if missing_orders:
                logger.warning(f"🔍 Found {len(missing_orders)} missing orders for cycle {self.cycle_id}")
                for pos in missing_orders:
                    logger.info(f"➕ Adding missing order {pos.ticket} to cycle {self.cycle_id}")
                    
                    # Create order data from MT5 position
                    order_data = {
                        'ticket': pos.ticket,
                        'volume': getattr(pos, 'volume', 0.01),
                        'price_open': getattr(pos, 'price_open', 0.0),
                        'profit': getattr(pos, 'profit', 0.0),
                        'swap': getattr(pos, 'swap', 0.0),
                        'commission': getattr(pos, 'commission', 0.0),
                        'sl': getattr(pos, 'sl', 0.0),
                        'tp': getattr(pos, 'tp', 0.0),
                        'margin': getattr(pos, 'margin', 0.0),
                        'type': getattr(pos, 'type', 0),  # 0=BUY, 1=SELL
                        'comment': getattr(pos, 'comment', '')  # Store the comment for future reference
                    }
                    
                    # Add the order to the cycle
                    success = self.add_order(order_data)
                    if success:
                        logger.info(f"✅ Successfully added missing order {pos.ticket} to cycle {self.cycle_id}")
                        
                        # Update cycle in database immediately
                        self._update_cycle_in_database()
                    else:
                        logger.error(f"❌ Failed to add missing order {pos.ticket} to cycle {self.cycle_id}")
                        
                logger.info(f"Cycle {self.cycle_id} now has {len(self.active_orders)} active orders and {len(self.completed_orders)} completed orders")
                
                # Debug: Show all orders in cycle after adding missing ones
                self.debug_order_status()
            else:
                logger.debug(f"No missing orders found for cycle {self.cycle_id}")
                
        except Exception as e:
            logger.error(f"Error checking for missing orders in cycle {self.cycle_id}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def force_sync_with_mt5(self):
        """Force synchronization of this cycle with MT5 orders"""
        try:
            logger.info(f"🔄 Force syncing cycle {self.cycle_id} with MT5 orders")
            
            # Update orders with live data
            self.update_orders_with_live_data()
            
            # Check for missing orders
            self._check_and_add_missing_orders()
            
            # Update cycle status
            self.update_cycle_status()
            
            # Update in database
            self._update_cycle_in_database()
            
            logger.info(f"✅ Force sync completed for cycle {self.cycle_id}")
            
        except Exception as e:
            logger.error(f"Error in force sync for cycle {self.cycle_id}: {e}")

    def switch_direction(self, new_direction, reason):
        """Switch the trading direction for this cycle"""
        try:
            if new_direction == self.current_direction:
                logger.warning(f"Direction already {new_direction} for cycle {self.cycle_id}")
                return False
            
            old_direction = self.current_direction
            self.current_direction = new_direction
            self.direction_switched = True
            self.direction_switches += 1
            
            # Create new batch for new direction
            self.current_batch_id = f"batch_{self.cycle_id}_{self.direction_switches}"
            
            logger.info(f"Cycle {self.cycle_id} direction switched: {old_direction} -> {new_direction} (Reason: {reason})")
            
            # Record in loss tracker
            if hasattr(self, 'loss_tracker_id') and self.loss_tracker_id:
                # ACTRepo removed - using in-memory operations
                logger.info(f"Direction switch recorded for cycle {self.id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error switching direction: {e}")
            return False

    def add_price_level_completion(self, price_level):
        """Add a completed price level to tracking"""
        try:
            if price_level not in self.done_price_levels:
                self.done_price_levels.append(price_level)
                logger.info(f"Price level {price_level} completed for cycle {self.cycle_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error adding price level completion: {e}")
            return False

    def get_next_order_price(self, current_price):
        """Calculate the next order price based on interval"""
        try:
            if not self.last_order_price:
                return current_price
            
            pip_value = self._get_pip_value()
            interval_price = self.order_interval_pips / pip_value
            
            if self.current_direction == "BUY":
                return self.last_order_price + interval_price
            else:  # SELL
                return self.last_order_price - interval_price
                
        except Exception as e:
            logger.error(f"Error calculating next order price: {e}")
            return current_price

    def should_place_next_order(self, current_price, current_time):
        """Determine if next order should be placed based on order_interval_pips"""
        try:
            # Check time interval (minimum 1 minute between orders)
            if self.last_order_time:
                # CRITICAL FIX: Convert string to datetime if needed and handle timezone
                last_order_time = self.last_order_time
                if isinstance(last_order_time, str):
                    try:
                        # Try ISO format first (most common)
                        last_order_time = datetime.datetime.fromisoformat(last_order_time)
                    except ValueError:
                        try:
                            # Try other common formats
                            last_order_time = datetime.datetime.strptime(last_order_time, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            logger.warning(f"Could not parse last_order_time: {last_order_time}, using current time")
                            last_order_time = current_time
                
                # CRITICAL FIX: Ensure both datetimes are naive (no timezone)
                if hasattr(current_time, 'tzinfo') and current_time.tzinfo is not None:
                    current_time = current_time.replace(tzinfo=None)
                if hasattr(last_order_time, 'tzinfo') and last_order_time.tzinfo is not None:
                    last_order_time = last_order_time.replace(tzinfo=None)
                
                # Now perform the subtraction with datetime objects
                time_diff = (current_time - last_order_time).total_seconds()
                if time_diff < 60:  # 1 minute minimum
                    return False
            
            # Check price interval - FIXED: Handle None last_order_price
            last_price = self.last_order_price
            
            # If last_order_price is None, get it from the most recent active order
            if last_price is None and self.active_orders:
                # Get the most recent order price
                most_recent_order = max(self.active_orders, key=lambda x: x.get('open_time', ''))
                last_price = most_recent_order.get('open_price', 0.0)
                
            # If we still don't have a last price, this is the first order - allow it
            if last_price is None or last_price == 0.0:
                logger.info(f"No previous order price found for cycle {self.cycle_id} - allowing first order")
                return True
            
            # Check if price has moved enough pips since last order
            pip_value = self._get_pip_value()
            price_diff_pips = abs(current_price - last_price) * pip_value
            
            logger.debug(f"Price check for cycle {self.cycle_id}: current={current_price}, last={last_price}, diff={price_diff_pips:.2f} pips, required={self.order_interval_pips} pips")
            
            if price_diff_pips < self.order_interval_pips:
                logger.debug(f"Price movement insufficient: {price_diff_pips:.2f} < {self.order_interval_pips} pips")
                return False
            
            # Check maximum orders per batch
            max_orders_per_batch = 10  # Configurable
            current_batch_orders = len([o for o in self.active_orders if o.get("batch_id") == self.current_batch_id])
            
            if current_batch_orders >= max_orders_per_batch:
                logger.debug(f"Maximum orders per batch reached: {current_batch_orders}/{max_orders_per_batch}")
                return False
            
            logger.info(f"✅ Cycle {self.cycle_id} ready for next order: price moved {price_diff_pips:.2f} pips (required: {self.order_interval_pips})")
            return True
            
        except Exception as e:
            logger.error(f"Error checking if should place next order: {e}")
            return False

    def get_batch_stop_loss_price(self, current_price):
        """Calculate batch stop loss price"""
        try:
            if not self.last_order_price:
                return None
            
            pip_value = self._get_pip_value()
            sl_distance = self.batch_stop_loss_pips / pip_value
            
            if self.current_direction == "BUY":
                return self.last_order_price - sl_distance
            else:  # SELL
                return self.last_order_price + sl_distance
                
        except Exception as e:
            logger.error(f"Error calculating batch stop loss: {e}")
            return None

    def check_batch_stop_loss(self, current_price):
        """Check if batch stop loss should be triggered for initial order"""
        try:
            sl_price = self.get_batch_stop_loss_price(current_price)
            if not sl_price:
                return False
            
            # Find the initial order
            initial_order = None
            for order in self.active_orders:
                if order.get('kind') == 'initial':
                    initial_order = order
                    break
                    
            if not initial_order:
                return False  # No initial order found
                
            # Check if stop loss is hit
            sl_triggered = False
            if self.current_direction == "BUY":
                sl_triggered = current_price <= sl_price
            else:  # SELL
                sl_triggered = current_price >= sl_price
                
            if sl_triggered:
                logger.info(f"🔄 Batch stop loss triggered for initial order {initial_order['ticket']} in cycle {self.cycle_id}")
                
                try:
                    # Close only the initial order
                 
                    self.meta_trader.close_position(initial_order['ticket'])
                    logger.info(f"✅ Closed initial order {initial_order['ticket']} due to batch stop loss")
                    
                    # Move order from active to completed
                    self.active_orders.remove(initial_order)
                    initial_order['is_closed'] = True
                    initial_order['close_time'] = datetime.datetime.utcnow().isoformat()
                    initial_order['status'] = 'closed'
                    self.completed_orders.append(initial_order)
                    
                    # Update cycle in database
                    if hasattr(self.bot, 'api_client') and self.bot.api_client:
                        update_data = {
                            "active_orders": json.dumps(serialize_datetime_objects(self.active_orders)),
                            "completed_orders": json.dumps(serialize_datetime_objects(self.completed_orders)),
                            "orders": json.dumps(serialize_datetime_objects(self.active_orders + self.completed_orders)),
                            "total_orders": len(self.active_orders) + len(self.completed_orders),
                            "total_volume": sum(order.get('volume', 0.0) for order in self.active_orders + self.completed_orders),
                            "total_profit": sum(order.get('profit', 0.0) for order in self.active_orders + self.completed_orders),
                            "batch_stop_loss_triggers": int(getattr(self, 'batch_stop_loss_triggers', 0)) + 1
                        }
                        self.bot.api_client.update_ACT_cycle_by_id(self.cycle_id, update_data)
                        
                except Exception as e:
                    logger.error(f"❌ Error closing initial order: {e}")
                    return False
                    
            return sl_triggered
                
        except Exception as e:
            logger.error(f"Error checking batch stop loss: {e}")
            return False

    def _get_pip_value(self):
        """Get pip value for the symbol"""
        if "JPY" in self.symbol:
            return 100.0  # 0.01 = 1 pip for JPY pairs
        elif "XAU" in self.symbol or "GOLD" in self.symbol.upper():
            return 100.0  # 0.01 = 1 pip for gold
        elif "BTC" in self.symbol or "ETH" in self.symbol:
            return 1.0    # 1.0 = 1 pip for crypto
        else:
            return 10000.0  # 0.0001 = 1 pip for major currency pairs

    def get_cycle_statistics(self):
        """Get current cycle statistics"""
        try:
            total_profit = sum(order.get("profit", 0.0) for order in self.completed_orders)
            unrealized_profit = 0.0  # Would calculate from active orders in real implementation
            
            return {
                "cycle_id": self.cycle_id,
                "symbol": self.symbol,
                "current_direction": self.current_direction,
                "direction_switched": self.direction_switched,
                "direction_switches": self.direction_switches,
                "zone_base_price": self.zone_base_price,
                "initial_threshold_price": self.initial_threshold_price,
                "active_orders": len(self.active_orders),
                "completed_orders": len(self.completed_orders),
                "total_profit": total_profit,
                "unrealized_profit": unrealized_profit,
                "accumulated_loss": self.accumulated_loss,
                "price_levels_completed": len(self.done_price_levels),
                "next_order_index": self.next_order_index,
                "last_order_price": self.last_order_price,
                "last_order_time": self.last_order_time.isoformat() if self.last_order_time else None,
                "is_active": self.is_active,
                "is_closed": self.is_closed,
                "close_reason": self.close_reason
            }
            
        except Exception as e:
            logger.error(f"Error getting cycle statistics: {e}")
            return {"error": str(e)}

    def validate_cycle_state(self):
        """Validate the current cycle state"""
        try:
            issues = []
            
            # Check for inconsistent direction
            if self.current_direction not in ["BUY", "SELL"]:
                issues.append(f"Invalid direction: {self.current_direction}")
            
            # Check for excessive losses
            if self.accumulated_loss > 500.0:  # Configurable threshold
                issues.append(f"High accumulated loss: {self.accumulated_loss}")
            
            # Check for too many direction switches
            if self.direction_switches > 3:
                issues.append(f"Too many direction switches: {self.direction_switches}")
            
            # Check for stale orders
            if self.last_order_time:
                time_since_last = (datetime.datetime.utcnow() - self.last_order_time).total_seconds()
                if time_since_last > 3600:  # 1 hour
                    issues.append(f"No orders placed in {time_since_last/60:.1f} minutes")
            
            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "warnings": len(issues)
            }
            
        except Exception as e:
            logger.error(f"Error validating cycle state: {e}")
            return {"valid": False, "issues": [str(e)], "warnings": 1}

    def reset_cycle_state(self):
        """Reset cycle state (use with caution)"""
        try:
            # Close all active orders first
            for order in self.active_orders:
                try:
                    if hasattr(self.meta_trader, 'close_order'):
                        self.meta_trader.close_order(order["ticket"])
                except Exception as e:
                    logger.error(f"Error closing order during reset: {e}")
            
            # Reset state
            self.active_orders.clear()
            self.completed_orders.clear()
            self.done_price_levels.clear()
            self.accumulated_loss = 0.0
            self.direction_switches = 0
            self.direction_switched = False
            self.next_order_index = 1
            self.last_order_time = None
            self.last_order_price = None
            self.current_batch_id = None
            
            logger.info(f"Cycle {self.cycle_id} state reset")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting cycle state: {e}")
            return False

    async def manage_zone_based_orders(self, order_interval_pips, batch_stop_loss_pips, continuous_placement):
        """Manage orders based on zone-based trading logic"""
        try:
            logger.info(f"Managing zone-based orders for cycle {self.cycle_id}")
            
            current_price = self.meta_trader.get_ask(self.symbol) if hasattr(self.meta_trader, 'get_ask') else 0.0
            current_time = datetime.datetime.utcnow()
            
            # Check batch stop loss first - now only closes initial order if triggered
            initial_order_closed = self.check_batch_stop_loss(current_price)
            if initial_order_closed:
                logger.info(f"Initial order closed due to batch stop loss in cycle {self.cycle_id}")
                # Don't return False here - continue with order management
            
            # Check if should place next order
            if self.should_place_next_order(current_price, current_time):
                logger.info(f"Cycle {self.cycle_id} ready for next order placement")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error managing zone-based orders: {e}")
            return False

    async def manage_advanced_zone_orders(self, zone_threshold_pips, order_interval_pips, batch_stop_loss_pips):
        """Manage advanced zone orders (legacy compatibility)"""
        try:
            # Update parameters
            self.zone_threshold_pips = zone_threshold_pips
            self.order_interval_pips = order_interval_pips
            self.batch_stop_loss_pips = batch_stop_loss_pips
            
            # Delegate to zone-based order management
            return await self.manage_zone_based_orders(
                order_interval_pips, 
                batch_stop_loss_pips, 
                True  # continuous_placement
            )
            
        except Exception as e:
            logger.error(f"Error managing advanced zone orders: {e}")
            return False

    def debug_order_status(self):
        """Debug method to check order status and help troubleshoot empty orders"""
        try:
            logger.info(f"🔍 CYCLE {self.cycle_id} DEBUG INFO:")
            logger.info(f"   Active orders: {len(self.active_orders)} - {self.active_orders}")
            logger.info(f"   Completed orders: {len(self.completed_orders)} - {self.completed_orders}")
            logger.info(f"   Next order index: {self.next_order_index}")
            logger.info(f"   Last order time: {self.last_order_time}")
            logger.info(f"   Last order price: {self.last_order_price}")
            logger.info(f"   Current batch ID: {self.current_batch_id}")
            logger.info(f"   PocketBase created: {self.pocketbase_created}")
            logger.info(f"   PocketBase ID: {getattr(self, 'cycle_id', 'Not set')}")
            
            if hasattr(self.bot, 'api_client'):
                logger.info(f"   Bot has API client: Yes")
            else:
                logger.info(f"   Bot has API client: No")
                
        except Exception as e:
            logger.error(f"Error in debug_order_status: {e}")

    def _update_cycle_in_database(self):
        """Update cycle in PocketBase database"""
        try:
            if not self.cycle_id:
                logger.error("❌ Cannot update cycle in database: No cycle_id available")
                return False
                
            if not (hasattr(self.bot, 'api_client') and self.bot.api_client):
                logger.error("No API client available for database operations")
                return False
                
            api_client = self.bot.api_client
            
            # Prepare update data
            update_data = {
                "active_orders": json.dumps(serialize_datetime_objects(self.active_orders)),
                "completed_orders": json.dumps(serialize_datetime_objects(self.completed_orders)),
                "orders": json.dumps(serialize_datetime_objects(self.active_orders + self.completed_orders)),
                "total_orders": len(self.active_orders) + len(self.completed_orders),
                "total_volume": float(sum(float(order.get('volume', 0.0)) for order in self.active_orders + self.completed_orders)),
                "total_profit": float(sum(float(order.get('profit', 0.0)) for order in self.active_orders + self.completed_orders)),
                "status": "active" if self.is_active else "inactive",
                "is_closed": self.is_closed,
                "is_active": self.is_active,
                "direction": self.current_direction,
                "current_direction": self.current_direction,
                "direction_switched": bool(self.direction_switched),
                "direction_switches": int(getattr(self, 'direction_switches', 0)),
                "next_order_index": int(self.next_order_index),
                "accumulated_loss": float(self.accumulated_loss or 0.0),
                "last_order_price": float(self.last_order_price) if self.last_order_price else 0.0,
                "last_order_time": self.last_order_time.isoformat() if self.last_order_time and hasattr(self.last_order_time, 'isoformat') else str(self.last_order_time) if self.last_order_time else None,
                "zone_activated": getattr(self, 'zone_activated', False),
                "initial_threshold_breached": getattr(self, 'initial_threshold_breached', False),
                "zone_based_losses": float(getattr(self, 'zone_based_losses', 0.0) or 0.0),
                "batch_stop_loss_triggers": int(getattr(self, 'batch_stop_loss_triggers', 0)),
                "done_price_levels": json.dumps(self.done_price_levels) if hasattr(self, 'done_price_levels') else json.dumps([]),
            }

            # Add closing information if cycle is closed
            if self.is_closed:
                update_data["close_time"] = self.close_time.isoformat() if hasattr(self, 'close_time') and self.close_time else None
                update_data["close_reason"] = getattr(self, 'close_reason', 'unknown')
                closing_method = {
                    "type": getattr(self, 'close_reason', 'unknown'),
                    "timestamp": self.close_time.isoformat() if hasattr(self, 'close_time') and self.close_time else None,
                    "final_profit": float(getattr(self, 'total_profit', 0.0) or 0.0)
                }
                update_data["closing_method"] = json.dumps(closing_method)
                
            # Add batch_losses if it exists
            if hasattr(self, 'batch_losses'):
                update_data["batch_losses"] = json.dumps(self.batch_losses) if self.batch_losses else json.dumps([])
                
            # Add current_batch_id if it exists
            if hasattr(self, 'current_batch_id') and self.current_batch_id:
                update_data["current_batch_id"] = str(self.current_batch_id)

            # Update using the unified cycle_id
            try:
                api_client.update_ACT_cycle_by_id(self.cycle_id, update_data)
                logger.debug(f"[SUCCESS] ACT Cycle {self.cycle_id} updated successfully")
                return True
            except Exception as e:
                logger.error(f"Error updating ACT cycle in database: {e}")
                logger.error(f"Data keys sent: {list(update_data.keys())}")
                return False
                
        except Exception as e:
            logger.error(f"Error in _update_cycle_in_database: {e}")
            return False

    def _create_cycle_in_database(self):
        """Create cycle in PocketBase database"""
        try:
            # Import API handler here to avoid circular imports
            if not (hasattr(self.bot, 'api_client') and self.bot.api_client):
                logger.error("No API client available for database operations")
                return False
                
            api_client = self.bot.api_client
            
            # CRITICAL FIX: Ensure bot and account are valid relation IDs
            bot_id = str(self.bot.id) if hasattr(self.bot, 'id') else None
            account_id = str(getattr(self.bot.account, 'id', None))
            
            if not bot_id:
                logger.error("❌ Cannot create cycle in database: Missing bot ID")
                return False
                
            if not account_id or account_id == "None" or account_id == "Unknown":
                logger.error("❌ Cannot create cycle in database: Invalid account ID")
                return False
            
            # Generate a temporary cycle_id if not already set
            if not hasattr(self, 'cycle_id') or not self.cycle_id:
                import uuid
                self.cycle_id = f"temp_{uuid.uuid4().hex}"
            
            # CRITICAL FIX: First serialize all complex data structures
            serialized_data = {
                "active_orders": ensure_json_serializable(self.active_orders),
                "completed_orders": ensure_json_serializable(self.completed_orders),
                "done_price_levels": ensure_json_serializable(self.done_price_levels),
                "batch_losses": ensure_json_serializable(getattr(self, 'batch_losses', [])),
                "orders": ensure_json_serializable(self.active_orders + self.completed_orders)
            }
            
            # Prepare creation data with current cycle state - match the schema exactly
            creation_data = {
                "bot": bot_id,
                "account": account_id,
                "symbol": self.symbol,
                "magic_number": int(self.bot.magic_number),
                "direction": "BUY" if self.current_direction == "BUY" else "SELL",
                "current_direction": "BUY" if self.current_direction == "BUY" else "SELL",
                "entry_price": float(self.entry_price) if hasattr(self, 'entry_price') and self.entry_price else 0.0,
                "stop_loss": float(getattr(self, 'stop_loss', 0.0)),
                "take_profit": float(getattr(self, 'take_profit', 0.0)),
                "lot_size": float(getattr(self, 'lot_size', 0.01)),
                "zone_base_price": float(self.zone_base_price) if self.zone_base_price else 0.0,
                "initial_threshold_price": float(self.initial_threshold_price) if self.initial_threshold_price else 0.0,
                "status": "active",
                "is_closed": False,
                "is_active": True,
                "zone_threshold_pips": float(self.zone_threshold_pips),
                "order_interval_pips": float(self.order_interval_pips),
                "batch_stop_loss_pips": float(self.batch_stop_loss_pips),
                "direction_switched": bool(self.direction_switched),
                "direction_switches": int(getattr(self, 'direction_switches', 0)),
                "next_order_index": int(self.next_order_index),
                "total_orders": len(self.active_orders) + len(self.completed_orders),
                "total_volume": float(sum(float(order.get('volume', 0.0)) for order in self.active_orders + self.completed_orders)),
                "total_profit": float(sum(float(order.get('profit', 0.0)) for order in self.active_orders + self.completed_orders)),
                "accumulated_loss": float(self.accumulated_loss or 0.0),
                "zone_activated": bool(getattr(self, 'zone_activated', False)),
                "initial_threshold_breached": bool(getattr(self, 'initial_threshold_breached', False)),
                "zone_based_losses": float(getattr(self, 'zone_based_losses', 0.0) or 0.0),
                "batch_stop_loss_triggers": int(getattr(self, 'batch_stop_loss_triggers', 0)),
                "is_favorite": False,
                "opened_by": json.dumps({"source": "system"}),
                "closing_method": json.dumps({}),
                "lot_idx": 0,
                "lower_bound": float(getattr(self, 'stop_loss', 0.0)),
                "upper_bound": float(getattr(self, 'take_profit', 0.0)),
                "orders_config": json.dumps({}),
                "cycle_type": "ACT",
                "zone_range_pips": float(getattr(self, 'zone_range_pips', 100.0))
            }
            
            # CRITICAL FIX: Add serialized data as JSON strings
            creation_data["active_orders"] = json.dumps(serialized_data["active_orders"])
            creation_data["completed_orders"] = json.dumps(serialized_data["completed_orders"])
            creation_data["orders"] = json.dumps(serialized_data["orders"])
            creation_data["done_price_levels"] = json.dumps(serialized_data["done_price_levels"])
            creation_data["batch_losses"] = json.dumps(serialized_data["batch_losses"])
            
            # Handle datetime fields
            if hasattr(self, 'last_order_time') and self.last_order_time:
                creation_data["last_order_time"] = serialize_datetime_objects(self.last_order_time)
                
            if hasattr(self, 'last_order_price') and self.last_order_price:
                creation_data["last_order_price"] = float(self.last_order_price)
                
            if hasattr(self, 'current_batch_id') and self.current_batch_id:
                creation_data["current_batch_id"] = str(self.current_batch_id)
            
            # Create the cycle in PocketBase
            try:
                # Log the creation attempt
                logger.debug(f"Creating ACT cycle with data keys: {list(creation_data.keys())}")
                
                # CRITICAL FIX: Verify all data is JSON serializable before sending
                for key, value in creation_data.items():
                    try:
                        json.dumps(value)
                    except (TypeError, ValueError) as e:
                        logger.error(f"Non-serializable value for key {key}: {value}")
                        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
                            creation_data[key] = value.isoformat() if value else None
                        else:
                            creation_data[key] = str(value)
                
                result = api_client.create_ACT_cycle(creation_data)
                if result and hasattr(result, 'id'):
                    # Update the cycle ID with the one from PocketBase
                    self.cycle_id = result.id
                    logger.info(f"🎯 Successfully created ACT cycle with ID: {self.cycle_id}")
                    
                    # Generate batch ID now that we have cycle_id
                    if not self.current_batch_id:
                        self.current_batch_id = f"batch_{self.cycle_id}_1"
                        
                    # Update the cycle with the batch ID
                    return True
                else:
                    logger.error("Failed to create ACT cycle: No result or result.id")
                    return False
                    
            except Exception as e:
                logger.error(f"Error creating ACT cycle: {e}")
                logger.error(f"Data keys sent: {list(creation_data.keys())}")
                return False
                
        except Exception as e:
            logger.error(f"Error in _create_cycle_in_database: {e}")
            return False

    async def handle_reversal(self, current_price: float, reversal_direction: str) -> bool:
        """
        Handle a price reversal by closing orders and switching direction
        
        Args:
            current_price: Current market price
            reversal_direction: New direction after reversal
            
        Returns:
            bool: True if reversal handled successfully
        """
        try:
            if reversal_direction == self.current_direction:
                logger.warning(f"Reversal direction {reversal_direction} is same as current direction for cycle {self.cycle_id}")
                return False
            
            # Record reversal details
            old_direction = self.current_direction
            reversal_time = datetime.datetime.utcnow()
            
            # Calculate P&L of current orders before closing
            current_pl = self._calculate_current_pl()
            
            # Close all active orders
            closed_orders = await self._close_all_active_orders_for_reversal()
            
            # Update closed orders P&L
            if closed_orders > 0:
                # Calculate P&L of closed orders
                closed_pl = self._calculate_closed_orders_pl()
                
                # Add to accumulated closed P&L
                self.closed_orders_pl += closed_pl
                
                logger.info(f"Added {closed_pl:.2f} to closed orders P&L (Total: {self.closed_orders_pl:.2f})")
                
                # Record batch loss
                self.batch_losses.append({
                    "direction": old_direction,
                    "closed_time": reversal_time.isoformat(),
                    "pl_amount": closed_pl,
                    "orders_closed": closed_orders,
                    "reversal_price": current_price
                })
            
            # Switch direction
            self.switch_direction(reversal_direction, "price_reversal")
            
            # Update reversal count and history
            self.reversal_count += 1
            self.last_reversal_time = reversal_time
            
            # Record in reversal history
            self.reversal_history.append({
                "old_direction": old_direction,
                "new_direction": reversal_direction,
                "reversal_time": reversal_time.isoformat(),
                "reversal_price": current_price,
                "closed_orders": closed_orders,
                "closed_pl": closed_pl if closed_orders > 0 else 0.0,
                "accumulated_pl": self.closed_orders_pl
            })
            
            # Reset price tracking for new direction
            if reversal_direction == "BUY":
                self.highest_buy_price = current_price
                self.lowest_sell_price = float('inf')
            else:  # SELL
                self.lowest_sell_price = current_price
                self.highest_buy_price = 0.0
            
            # Update cycle in database
            self._update_cycle_in_database()
            
            logger.info(f"✅ Reversal handled for cycle {self.cycle_id}: {old_direction} → {reversal_direction} "
                       f"(Closed {closed_orders} orders, Total P&L: {self.total_cycle_pl:.2f})")
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling reversal for cycle {self.cycle_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def _close_all_active_orders_for_reversal(self) -> int:
        """
        Close all active orders during a reversal
        
        Returns:
            int: Number of orders closed
        """
        try:
            closed_count = 0
            
            # Get all active order tickets
            order_tickets = [order.get('ticket') for order in self.active_orders 
                           if order.get('ticket') and not order.get('is_closed', False)]
            
            if not order_tickets:
                logger.info(f"No active orders to close for cycle {self.cycle_id}")
                return 0
            
            # Close each order
            for ticket in order_tickets:
                try:
                    # Close the order in MT5
                    close_result = self.meta_trader.close_position(ticket)
                    
                    if close_result:
                        logger.info(f"✅ Closed order {ticket} for reversal")
                        closed_count += 1
                        
                        # Update order status
                        for order in self.active_orders:
                            if order.get('ticket') == ticket:
                                order['is_closed'] = True
                                order['close_time'] = datetime.datetime.utcnow().isoformat()
                                order['close_reason'] = "reversal"
                                order['status'] = "closed"
                                
                                # Move to completed orders
                                self.completed_orders.append(order)
                    else:
                        logger.warning(f"Failed to close order {ticket} for reversal")
                        
                except Exception as e:
                    logger.error(f"Error closing order {ticket}: {e}")
            
            # Remove closed orders from active list
            self.active_orders = [order for order in self.active_orders if not order.get('is_closed', False)]
            
            logger.info(f"Closed {closed_count}/{len(order_tickets)} orders for reversal in cycle {self.cycle_id}")
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing active orders for reversal: {e}")
            return 0
    
    def check_reversal_condition(self, current_price: float) -> Dict:
        """
        Check if price has reversed enough to trigger a direction switch
        
        Args:
            current_price: Current market price
            
        Returns:
            Dict: Reversal check results
        """
        try:
            # Skip if no orders placed yet
            if not self.active_orders and not self.completed_orders:
                return {"reversal_detected": False}
            
            # Update highest/lowest prices
            if self.current_direction == "BUY":
                if current_price > self.highest_buy_price:
                    self.highest_buy_price = current_price
            else:  # SELL
                if current_price < self.lowest_sell_price or self.lowest_sell_price == float('inf'):
                    self.lowest_sell_price = current_price
            
            # Check for reversal based on direction
            reversal_detected = False
            new_direction = None
            pip_value = self._get_pip_value()
            threshold_distance = self.reversal_threshold_pips / pip_value
            
            if self.current_direction == "BUY" and self.highest_buy_price > 0:
                # For BUY direction, check if price dropped below threshold from highest
                reversal_price = self.highest_buy_price - threshold_distance
                
                if current_price <= reversal_price:
                    reversal_detected = True
                    new_direction = "SELL"
                    logger.info(f"🔄 BUY→SELL reversal detected for cycle {self.cycle_id}: "
                               f"Price {current_price} dropped {self.reversal_threshold_pips} pips "
                               f"from highest {self.highest_buy_price}")
            
            elif self.current_direction == "SELL" and self.lowest_sell_price < float('inf'):
                # For SELL direction, check if price rose above threshold from lowest
                reversal_price = self.lowest_sell_price + threshold_distance
                
                if current_price >= reversal_price:
                    reversal_detected = True
                    new_direction = "BUY"
                    logger.info(f"🔄 SELL→BUY reversal detected for cycle {self.cycle_id}: "
                               f"Price {current_price} rose {self.reversal_threshold_pips} pips "
                               f"from lowest {self.lowest_sell_price}")
            
            return {
                "reversal_detected": reversal_detected,
                "current_direction": self.current_direction,
                "new_direction": new_direction,
                "current_price": current_price,
                "highest_buy_price": self.highest_buy_price,
                "lowest_sell_price": self.lowest_sell_price,
                "reversal_threshold_pips": self.reversal_threshold_pips
            }
            
        except Exception as e:
            logger.error(f"Error checking reversal condition: {e}")
            return {"error": str(e), "reversal_detected": False}
    
    def _calculate_current_pl(self) -> float:
        """
        Calculate current P&L of active orders
        
        Returns:
            float: Current P&L
        """
        try:
            total_pl = 0.0
            
            # Update orders with live data first
            self.update_orders_with_live_data()
            
            # Sum profit from all active orders
            for order in self.active_orders:
                profit = order.get('profit', 0.0) or 0.0
                swap = order.get('swap', 0.0) or 0.0
                commission = order.get('commission', 0.0) or 0.0
                
                # Add to total
                total_pl += profit + swap - commission
            
            # Update open orders P&L
            self.open_orders_pl = total_pl
            
            # Calculate total cycle P&L (open + closed)
            self.total_cycle_pl = self.open_orders_pl + self.closed_orders_pl
            
            return total_pl
            
        except Exception as e:
            logger.error(f"Error calculating current P&L: {e}")
            return 0.0
    
    def _calculate_closed_orders_pl(self) -> float:
        """
        Calculate P&L of recently closed orders
        
        Returns:
            float: Closed orders P&L
        """
        try:
            # Get orders closed in the last minute
            one_minute_ago = (datetime.datetime.utcnow() - datetime.timedelta(minutes=1)).isoformat()
            
            recent_closed_orders = [
                order for order in self.completed_orders
                if order.get('close_time') and order.get('close_time') > one_minute_ago
            ]
            
            total_pl = 0.0
            
            # Sum profit from recently closed orders
            for order in recent_closed_orders:
                profit = order.get('profit', 0.0) or 0.0
                swap = order.get('swap', 0.0) or 0.0
                commission = order.get('commission', 0.0) or 0.0
                
                # Add to total
                total_pl += profit + swap - commission
            
            return total_pl
            
        except Exception as e:
            logger.error(f"Error calculating closed orders P&L: {e}")
            return 0.0
    
    def check_take_profit(self, take_profit_amount: float) -> bool:
        """
        Check if cycle has reached take profit level
        
        Args:
            take_profit_amount: Take profit amount in account currency
            
        Returns:
            bool: True if take profit reached
        """
        try:
            # Calculate current P&L
            current_pl = self._calculate_current_pl()
            
            # Check if total P&L exceeds take profit
            if self.total_cycle_pl >= take_profit_amount:
                logger.info(f"🎯 Take profit reached for cycle {self.cycle_id}: "
                           f"{self.total_cycle_pl:.2f} >= {take_profit_amount:.2f}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking take profit: {e}")
            return False