"""
Advanced Cycle - Organized Version

This is a clean, organized version of the AdvancedCycle with:
- Unused code removed
- Functions renamed for better readability
- Logical grouping of related functionality
- Improved documentation
"""

import datetime
import uuid
import json
import asyncio
from typing import Dict, List, Optional, Any
from Orders.order import order
import MetaTrader5 as Mt5
from DB.db_engine import engine
from cycles.CT_cycle import cycle
from Views.globals.app_logger import app_logger as logger
from helpers.sync import verify_order_status, sync_delay, MT5_LOCK


class AdvancedCycle(cycle):
    """
    Advanced Cycle with Zone-Based Trading Logic and Reversal Detection
    
    Features:
    - Zone-based order placement
    - Reversal detection and handling
    - Multi-direction trading
    - Enhanced profit/loss tracking
    - Real-time synchronization with MetaTrader
    """

    def __init__(self, cycle_data, meta_trader, bot):
        """Initialize Advanced Cycle with enhanced features"""
        self._validate_initialization_parameters(cycle_data, meta_trader, bot)
        self._initialize_base_cycle(cycle_data, meta_trader, bot)
        self._initialize_advanced_properties(cycle_data)
        self._initialize_reversal_properties(cycle_data)
        self._initialize_database_components()
        self._validate_initialization()
        
        logger.info(f"AdvancedCycle initialized with ID: {self.cycle_id}")

    # ==================== INITIALIZATION METHODS ====================

    def _validate_initialization_parameters(self, cycle_data, meta_trader, bot):
        """Validate initialization parameters"""
        if bot is None:
            logger.error("🚨 CRITICAL: Bot parameter is None during AdvancedCycle initialization!")
            raise ValueError("Bot parameter cannot be None")
        
        if meta_trader is None:
            raise ValueError("MetaTrader instance cannot be None")

    def _initialize_base_cycle(self, cycle_data, meta_trader, bot):
        """Initialize base cycle properties"""
        # Ensure cycle_data is a dictionary
        if cycle_data is None:
            cycle_data = {}
        elif not isinstance(cycle_data, dict):
            try:
                cycle_data = dict(cycle_data)
            except Exception as e:
                logger.error(f"Failed to convert cycle_data to dictionary: {e}")
                cycle_data = {}
        
        # Generate cycle ID if not provided
        if 'id' not in cycle_data or not cycle_data['id']:
            temp_id = f"temp_{uuid.uuid4().hex}"
            logger.info(f"Generating temporary cycle_id: {temp_id}")
            cycle_data['id'] = temp_id
        
        # Initialize base cycle class
        super().__init__(cycle_data, meta_trader, bot)
        
        # Set cycle ID
        self.cycle_id = cycle_data.get('id')
        self.meta_trader = meta_trader

    def _initialize_advanced_properties(self, cycle_data):
        """Initialize advanced cycle properties"""
        entry_price = cycle_data.get("entry_price", 0.0)
        
        # Zone-based properties
        self.zone_base_price = cycle_data.get("zone_base_price", entry_price if entry_price > 0 else None)
        self.initial_threshold_price = cycle_data.get("initial_threshold_price", None)
        self.current_direction = cycle_data.get("current_direction", "BUY")
        self.direction_switched = cycle_data.get("direction_switched", False)
        self.done_price_levels = cycle_data.get("done_price_levels", [])
        self.next_order_index = cycle_data.get("next_order_index", 1)
        
        # Trading parameters
        self.reversal_threshold_pips = cycle_data.get("reversal_threshold_pips", 50.0)
        self.order_interval_pips = cycle_data.get("order_interval_pips", 50.0)
        self.initial_order_stop_loss = cycle_data.get("initial_order_stop_loss", 300.0)
        self.cycle_interval = cycle_data.get("cycle_interval", 100.0)
        
        # Order management
        self.active_orders = cycle_data.get("active_orders", [])
        self.completed_orders = cycle_data.get("completed_orders", [])
        
        # Batch management
        self.current_batch_id = cycle_data.get("current_batch_id", None)
        if self.current_batch_id is None and self.cycle_id:
            self.current_batch_id = f"batch_{self.cycle_id}_1"
            logger.info(f"Generated initial batch_id: {self.current_batch_id}")
        
        self.last_order_time = cycle_data.get("last_order_time", None)
        self.last_order_price = cycle_data.get("last_order_price", None)
        
        # Loss tracking
        self.accumulated_loss = 0.0
        self.batch_losses = []
        self.direction_switches = 0
        
        # Zone state
        self.zone_activated = cycle_data.get("zone_activated", False)
        self.initial_threshold_breached = cycle_data.get("initial_threshold_breached", False)
        self.zone_based_losses = cycle_data.get("zone_based_losses", 0.0)
        self.batch_stop_loss_triggers = cycle_data.get("batch_stop_loss_triggers", 0)

    def _initialize_reversal_properties(self, cycle_data):
        """Initialize reversal trading properties"""
        self.reversal_threshold_pips = cycle_data.get("reversal_threshold_pips", 50.0)
        self.highest_buy_price = cycle_data.get("highest_buy_price", 0.0)
        self.lowest_sell_price = cycle_data.get("lowest_sell_price", float('inf'))
        self.reversal_count = cycle_data.get("reversal_count", 0)
        self.closed_orders_pl = cycle_data.get("closed_orders_pl", 0.0)
        self.open_orders_pl = cycle_data.get("open_orders_pl", 0.0)
        self.total_cycle_pl = cycle_data.get("total_cycle_pl", 0.0)
        self.last_reversal_time = cycle_data.get("last_reversal_time", None)
        self.reversal_history = cycle_data.get("reversal_history", [])
        self.initial_order_stop_loss = cycle_data.get("initial_order_stop_loss", 300.0)
        self.cycle_interval = cycle_data.get("cycle_interval", 100.0)
        
        # Recovery mode properties (NEW)
        self.in_recovery_mode = cycle_data.get("in_recovery_mode", False)
        self.recovery_zone_base_price = cycle_data.get("recovery_zone_base_price", None)
        self.initial_stop_loss_price = cycle_data.get("initial_stop_loss_price", None)

    def _initialize_database_components(self):
        """Initialize in-memory components"""
        # Cycle state
        self.is_active = True
        self.is_closed = False
        self.close_reason = None

    def _validate_initialization(self):
        """Validate initialization was successful"""
        if not self.cycle_id:
            logger.error("❌ Cycle initialization failed: No cycle_id set")
            raise ValueError("Cycle must have an ID")

    # ==================== ORDER MANAGEMENT ====================

    def add_order(self, order_input):
        """Add an order to this cycle and update database"""
        try:
            order_data = self._process_order_input(order_input)
            
            if not order_data:
                logger.error("Failed to process order input")
                return False
            
            # Add to active orders
            self.active_orders.append(order_data)
            
            # Update cycle statistics
            self._update_cycle_statistics_after_order_add(order_data)
            
            # Update price extremes based on new order
            self._update_price_extremes(0.0)  # Current price not needed for order-based calculation
            
            # Update cycle in PocketBase database
            self._update_cycle_in_database()
            
            # Log order addition
            logger.info(f"Order {order_data.get('ticket')} added to cycle {self.cycle_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding order to cycle: {e}")
            return False

    def _process_order_input(self, order_input) -> Optional[dict]:
        """Process order input and convert to standardized format"""
        try:
            if isinstance(order_input, dict):
                return order_input
            elif hasattr(order_input, '__dict__'):
                return self._convert_object_to_order_data(order_input)
            elif isinstance(order_input, (int, str)):
                return self._create_order_data_from_ticket(order_input)
            else:
                logger.error(f"Unsupported order input type: {type(order_input)}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing order input: {e}")
            return None

    def _convert_object_to_order_data(self, order_obj) -> dict:
        """Convert order object to Flutter-compatible dictionary"""
        order_data = {}
        
        # Extract common fields
        field_mappings = {
            'ticket': ['ticket', 'order_id', 'id'],
            'direction': ['direction', 'type', 'order_type'],
            'open_price': ['open_price', 'price_open', 'price'],
            'volume': ['volume', 'lot_size', 'size'],
            'profit': ['profit', 'unrealized_pnl', 'pnl'],
            'swap': ['swap'],
            'commission': ['commission'],
            'sl': ['sl', 'stop_loss'],
            'tp': ['tp', 'take_profit'],
            'magic_number': ['magic_number', 'magic'],
            'comment': ['comment', 'description']
        }
        
        for target_field, source_fields in field_mappings.items():
            for source_field in source_fields:
                if hasattr(order_obj, source_field):
                    value = getattr(order_obj, source_field)
                    if value is not None:
                        if target_field == 'comment':
                            order_data[target_field] = str(value)
                        elif target_field in ['ticket', 'magic_number']:
                            order_data[target_field] = int(value)
                        else:
                            order_data[target_field] = self._safe_float_conversion(value)
                        break
        
        # Set Flutter-compatible default values
        order_data.setdefault('ticket', 0)  # Flutter expects num, not string
        order_data.setdefault('type', 0)  # 0 = BUY, 1 = SELL
        order_data.setdefault('kind', 'initial')  # orderKind - required by Flutter
        order_data.setdefault('status', 'active')
        order_data.setdefault('open_time', datetime.datetime.now().isoformat())
        order_data.setdefault('symbol', getattr(self, 'symbol', ''))
        order_data.setdefault('open_price', 0.0)
        order_data.setdefault('volume', 0.0)
        order_data.setdefault('profit', 0.0)
        order_data.setdefault('swap', 0.0)
        order_data.setdefault('commission', 0.0)
        order_data.setdefault('magic_number', 0)
        order_data.setdefault('comment', '')
        order_data.setdefault('sl', 0.0)
        order_data.setdefault('tp', 0.0)
        order_data.setdefault('trailing_steps', 0)
        order_data.setdefault('margin', 0.0)
        order_data.setdefault('is_pending', False)
        order_data.setdefault('is_closed', False)
        order_data.setdefault('cycle_id', None)
        order_data.setdefault('cycle_create', None)
        
        # Determine order type from direction
        if 'direction' in order_data:
            direction = str(order_data['direction']).upper()
            if direction in ['BUY', '0']:
                order_data['type'] = 0
            elif direction in ['SELL', '1']:
                order_data['type'] = 1
        
        return order_data

    def _create_order_data_from_ticket(self, ticket) -> dict:
        """Create Flutter-compatible order data from ticket number"""
        direction = getattr(self, 'current_direction', 'BUY')
        return {
            'ticket': int(ticket),  # Flutter expects num, not string
            'type': 0 if direction == 'BUY' else 1,  # 0 = BUY, 1 = SELL
            'kind': 'initial',  # orderKind - required by Flutter
            'status': 'active',
            'open_time': datetime.datetime.now().isoformat(),
            'direction': direction,
            'symbol': getattr(self, 'symbol', ''),
            'open_price': 0.0,
            'volume': 0.0,
            'profit': 0.0,
            'swap': 0.0,
            'commission': 0.0,
            'magic_number': 0,
            'comment': '',
            'sl': 0.0,
            'tp': 0.0,
            'trailing_steps': 0,
            'margin': 0.0,
            'is_pending': False,
            'is_closed': False,
            'cycle_id': None,
            'cycle_create': None
        }

    def _safe_float_conversion(self, value, default=0.0) -> float:
        """Safely convert value to float with infinity handling"""
        if value is None:
            return default
        
        try:
            float_val = float(value)
            # Check for infinity or NaN
            if float_val == float('inf'):
                return 999999999.0  # Large number instead of infinity
            elif float_val == float('-inf'):
                return -999999999.0  # Large negative number instead of negative infinity
            elif float_val != float_val:  # NaN check
                return default
            else:
                return float_val
        except (ValueError, TypeError):
            return default

    def _safe_getattr_float(self, attr_name: str, default=0.0) -> float:
        """Safely get attribute as float with infinity handling"""
        value = getattr(self, attr_name, default)
        return self._safe_float_conversion(value, default)

    def _recalculate_total_profit(self):
        """Recalculate total profit from all orders"""
        try:
            logger.info(f"Recalculating total profit for cycle {self.cycle_id}")
            
            # Initialize profit components
            active_profit = 0.0
            completed_profit = 0.0
            total_swap = 0.0
            total_commission = 0.0
            
            # Calculate profit from active orders
            for order in self.active_orders:
                profit = float(order.get('profit', 0.0))
                swap = float(order.get('swap', 0.0))
                commission = float(order.get('commission', 0.0))
                
                active_profit += profit
                total_swap += swap
                total_commission += commission
                
                logger.debug(f"Active order {order.get('ticket')}: Profit={profit}, Swap={swap}, Commission={commission}")
            
            # Calculate profit from completed orders
            for order in self.completed_orders:
                profit = float(order.get('profit', 0.0))
                swap = float(order.get('swap', 0.0))
                commission = float(order.get('commission', 0.0))
                
                completed_profit += profit
                total_swap += swap
                total_commission += commission
                
                logger.debug(f"Completed order {order.get('ticket')}: Profit={profit}, Swap={swap}, Commission={commission}")
            
            # Calculate total profit
            self.total_profit = active_profit + completed_profit + total_swap + total_commission
            
            logger.info(f"Cycle {self.cycle_id} profit calculation complete:")
            logger.info(f"Active orders profit: {active_profit}")
            logger.info(f"Completed orders profit: {completed_profit}")
            logger.info(f"Total swap: {total_swap}")
            logger.info(f"Total commission: {total_commission}")
            logger.info(f"Total profit: {self.total_profit}")
            
            return self.total_profit
            
        except Exception as e:
            logger.error(f"Error calculating total profit: {e}")
            return 0.0

    def _update_cycle_statistics_after_order_add(self, order_data):
        """Update cycle statistics after adding an order"""
        try:
            # Recalculate total profit to include new order
            self._recalculate_total_profit()
            
            # Update price extremes
            self._update_price_extremes(0.0)
            
            # Update database with new profit information
            self._update_cycle_in_database()
            
        except Exception as e:
            logger.error(f"Error updating cycle statistics after order add: {e}")

    def update_orders_with_live_data(self):
        """Update orders with live data from MT5 and recalculate profits"""
        try:
            # Get current positions from MT5
            positions = self._get_mt5_positions()
            
            if not positions:
                return
            
            # Create lookup dictionary for faster access
            positions_dict = self._create_positions_lookup(positions)
            
            # Update orders with live data
            updated_count = self._update_orders_from_positions(positions_dict)
            
            # Recalculate total profit after updating orders
            self._recalculate_total_profit()
            
            # Update database with latest profit information if orders were updated
            if updated_count > 0:
                self._update_cycle_in_database()
            
        except Exception as e:
            logger.error(f"Error updating orders with live data: {e}")

    def _get_mt5_positions(self) -> List:
        """Get positions from MetaTrader"""
        positions = []
        
        if hasattr(self.meta_trader, 'get_positions'):
            positions = self.meta_trader.get_positions()
        elif hasattr(self.meta_trader, 'get_all_positions'):
            positions = self.meta_trader.get_all_positions()
        
        return positions or []

    def _create_positions_lookup(self, positions) -> dict:
        """Create lookup dictionary for positions by ticket"""
        positions_dict = {}
        for pos in positions:
            ticket = getattr(pos, 'ticket', None)
            if ticket:
                positions_dict[int(ticket)] = pos
        return positions_dict

    def _update_orders_from_positions(self, positions_dict) -> int:
        """Update orders from MT5 positions data"""
        updated_count = 0
        
        for order in self.active_orders:
            try:
                # Convert ticket to integer for dictionary lookup
                ticket = int(order.get('ticket', '0'))
                if ticket in positions_dict:
                    position = positions_dict[ticket]
                    
                    # Update order with live data
                    order['profit'] = getattr(position, 'profit', 0.0)
                    order['swap'] = getattr(position, 'swap', 0.0)
                    order['commission'] = getattr(position, 'commission', 0.0)
                    order['volume'] = getattr(position, 'volume', order.get('volume', 0.0))
                    
                    updated_count += 1
                    logger.info(f"Updated order {ticket} with profit: {order['profit']}, swap: {order['swap']}, commission: {order['commission']}")
                else:
                    logger.debug(f"Order {ticket} not found in positions dictionary. Available tickets: {list(positions_dict.keys())}")
                    
            except ValueError as ve:
                logger.error(f"Invalid ticket format for order: {order.get('ticket', 'unknown')}")
            except Exception as e:
                logger.error(f"Error updating order {order.get('ticket', 'unknown')}: {e}")
        
        logger.info(f"Updated {updated_count} orders out of {len(self.active_orders)} active orders")
        return updated_count

    # ==================== CYCLE STATUS MANAGEMENT ====================

    def update_cycle_status(self):
        """Update cycle status based on orders and conditions"""
        try:
            logger.info(f"Updating status for cycle {self.cycle_id}")
            
            # Update order statuses first
            self._update_order_statuses()
            logger.info(f"Updated order statuses for cycle {self.cycle_id}")
            
            # Check if cycle should be closed
            if self._should_close_cycle():
                logger.info(f"Cycle {self.cycle_id} meets closing conditions")
                self.close_cycle("auto_close")
            else:
                # Recalculate total profit
                self._recalculate_total_profit()
                logger.info(f"Cycle {self.cycle_id} remains active. Total profit: {self.total_profit}")
                
            # Check completion conditions
            self._check_cycle_completion_conditions()
            
            # Log final status
            logger.info(f"Cycle {self.cycle_id} status update complete. Active: {self.is_active}, Closed: {self.is_closed}, Total Profit: {self.total_profit}")
            
        except Exception as e:
            logger.error(f"Error updating cycle status: {e}")

    def _update_order_statuses(self):
        """Update the status of all orders in the cycle"""
        try:
            logger.info(f"Updating order statuses for cycle {self.cycle_id}")
            
            # Track changes
            orders_closed = 0
            orders_active = 0
            
            # Update active orders
            for order in self.active_orders[:]:  # Use slice copy to avoid modification during iteration
                if self._is_order_closed(order):
                    logger.info(f"Order {order.get('ticket')} is closed, moving to completed orders")
                    self._move_order_to_completed(order)
                    orders_closed += 1
                else:
                    orders_active += 1
            
            logger.info(f"Cycle {self.cycle_id} order status update complete. Active orders: {orders_active}, Newly closed: {orders_closed}")
            
        except Exception as e:
            logger.error(f"Error updating order statuses: {e}")

    def _is_order_closed(self, order) -> bool:
        """Check if an order is closed"""
        try:
            ticket = order.get('ticket')
            if not ticket:
                return False
            
            # Check if position still exists in MT5
            positions = self._get_mt5_positions()
            for pos in positions:
                if str(getattr(pos, 'ticket', '')) == str(ticket):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if order is closed: {e}")
            return False

    def _move_order_to_completed(self, order):
        """Move order from active to completed and update profits"""
        try:
            if order in self.active_orders:
                self.active_orders.remove(order)
            
            # Update order status
            order['status'] = 'closed'
            order['close_time'] = datetime.datetime.now().isoformat()
            order['is_closed'] = True
            
            if order not in self.completed_orders:
                self.completed_orders.append(order)
            
            # Update price extremes after removing order from active orders
            self._update_price_extremes(0.0)
            
            # Recalculate profits immediately
            self._recalculate_total_profit()
            
        except Exception as e:
            logger.error(f"Error moving order to completed: {e}")

    def _check_cycle_completion_conditions(self):
        """Check if cycle should be closed"""
        # Auto-completion disabled
        pass

    def _should_close_cycle(self) -> bool:
        """Determine if cycle should be closed based on conditions"""
        try:
            # Check if all orders are closed
            all_orders_closed = len(self.active_orders) == 0
            
            # Check if cycle is marked for closing
            marked_for_closing = getattr(self, 'force_close', False)
            
            logger.info(f"Checking if cycle {self.cycle_id} should close. All orders closed: {all_orders_closed}, Marked for closing: {marked_for_closing}")
            
            return all_orders_closed or marked_for_closing
            
        except Exception as e:
            logger.error(f"Error checking if cycle should close: {e}")
            return False

    def close_cycle(self, reason: str):
        """Close the cycle and update its status"""
        try:
            logger.info(f"Closing cycle {self.cycle_id} with reason: {reason}")
            
            # Set cycle status
            self.is_active = False
            self.is_closed = True
            self.close_reason = reason
            
            # Calculate final statistics
            self._calculate_final_statistics()
            
            # Update database
            self._update_cycle_in_database()
            
            logger.info(f"Cycle {self.cycle_id} closed successfully. Final profit: {self.total_profit}")
            
        except Exception as e:
            logger.error(f"Error closing cycle: {e}")

    def _calculate_final_statistics(self):
        """Calculate final statistics when closing a cycle"""
        try:
            # Force final profit calculation
            self._recalculate_total_profit()
            
            # Calculate other statistics
            total_orders = len(self.active_orders) + len(self.completed_orders)
            completed_orders = len(self.completed_orders)
            
            logger.info(f"Final statistics for cycle {self.cycle_id}:")
            logger.info(f"Total orders: {total_orders}")
            logger.info(f"Completed orders: {completed_orders}")
            logger.info(f"Total profit: {self.total_profit}")
            logger.info(f"Close reason: {self.close_reason}")
            
        except Exception as e:
            logger.error(f"Error calculating final statistics: {e}")

    # ==================== REVERSAL DETECTION AND HANDLING ====================

    def check_reversal_condition(self, current_price: float) -> Dict:
        """Check if reversal conditions are met"""
        try:
            result = {
                'should_reverse': False,
                'new_direction': None,
                'reversal_price': None,
                'reversal_reason': None
            }
            
            if not self.active_orders:
                return result
            
            # Update price extremes
            self._update_price_extremes(current_price)
            # Check reversal conditions based on current direction
            if self.current_direction == "BUY":
                reversal_price = self.highest_buy_price - (self.reversal_threshold_pips * self._get_pip_value())
                if current_price <= reversal_price:
                    result.update({
                        'should_reverse': True,
                        'new_direction': 'SELL',
                        'reversal_price': reversal_price,
                        'reversal_reason': f'Price dropped {self.reversal_threshold_pips} pips from highest buy price'
                    })
            
            elif self.current_direction == "SELL":
                reversal_price = self.lowest_sell_price + (self.reversal_threshold_pips * self._get_pip_value())
                if current_price >= reversal_price:
                    result.update({
                        'should_reverse': True,
                        'new_direction': 'BUY',
                        'reversal_price': reversal_price,
                        'reversal_reason': f'Price rose {self.reversal_threshold_pips} pips from lowest sell price'
                    })
            
            return result
        except Exception as e:
            logger.error(f"Error checking reversal condition: {e}")
            return {'should_reverse': False, 'new_direction': None, 'reversal_price': None, 'reversal_reason': None}

    def _update_price_extremes(self, current_price: float):
        """Update highest buy price and lowest sell price based on active orders"""
        try:
            # Update highest buy price from active buy orders
            self._update_highest_buy_price_from_orders()
            
            # Update lowest sell price from active sell orders
            self._update_lowest_sell_price_from_orders()
                    
        except Exception as e:
            logger.error(f"Error updating price extremes: {e}")
    
    def _update_highest_buy_price_from_orders(self):
        """Update highest_buy_price to be the open price of the highest active buy order"""
        try:
            buy_orders = [
                order for order in self.active_orders 
                if order.get('direction', '').upper() == 'BUY' or order.get('type', 0) == 0
            ]
            
            if buy_orders:
                # Find the order with the highest open price
                highest_order = max(buy_orders, key=lambda order: order.get('open_price', 0.0))
                self.highest_buy_price = highest_order.get('open_price', 0.0)
            else:
                self.highest_buy_price = 0.0
                
        except Exception as e:
            logger.error(f"Error updating highest buy price from orders: {e}")
    
    def _update_lowest_sell_price_from_orders(self):
        """Update lowest sell price from active sell orders"""
        try:
            # Get all active sell orders
            sell_orders = [order for order in self.active_orders if order.get('type') == 1]  # SELL = 1
            
            if sell_orders:
                # Find the order with the lowest open price
                lowest_order = min(sell_orders, key=lambda order: order.get('open_price', float('inf')))
                self.lowest_sell_price = self._safe_float_conversion(lowest_order.get('open_price', 999999999.0))
            else:
                # Use large finite number instead of infinity
                self.lowest_sell_price = 999999999.0
                
        except Exception as e:
            logger.error(f"Error updating lowest sell price from orders: {e}")
            self.lowest_sell_price = 999999999.0

    async def handle_reversal(self, current_price: float, reversal_direction: str) -> bool:
        """Handle reversal by closing orders and switching direction"""
        try:
            logger.info(f"Handling reversal from {self.current_direction} to {reversal_direction}")
            
            # Close all active orders
            closed_orders_count = await self._close_all_active_orders_for_reversal()
            
            # Update reversal statistics
            self._update_reversal_statistics(current_price, reversal_direction, closed_orders_count)
            
            # Switch direction
            self.switch_direction(reversal_direction, "reversal")
            
            # Update cycle in PocketBase database
            self._update_cycle_in_database()
            
            # Log reversal completion
            logger.info(f"Reversal completed: {closed_orders_count} orders closed, direction switched to {reversal_direction}")
            return True
            
        except Exception as e:
            logger.error(f"Error handling reversal: {e}")
            return False

    async def _close_all_active_orders_for_reversal(self) -> int:
        """Close all active orders for reversal"""
        try:
            closed_count = 0
            orders_to_close = self.active_orders.copy()
            
            for order in orders_to_close:
                try:
                    ticket = order.get('ticket')
                    if ticket and self._close_order_in_mt5(ticket):
                        self._move_order_to_completed(order)
                        closed_count += 1
                        
                except Exception as e:
                    logger.error(f"Error closing order {order.get('ticket')}: {e}")
            
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing orders for reversal: {e}")
            return 0

    def _close_order_in_mt5(self, ticket: str) -> bool:
        """Close order in MetaTrader 5"""
        try:
            if hasattr(self.meta_trader, 'close_position'):
                return self.meta_trader.close_position(int(ticket))
            else:
                logger.error("MetaTrader instance does not have close_position method")
                return False
                
        except Exception as e:
            logger.error(f"Error closing order {ticket} in MT5: {e}")
            return False

    def _update_reversal_statistics(self, current_price: float, new_direction: str, closed_orders_count: int):
        """Update reversal-related statistics"""
        try:
            # Update reversal count
            self.reversal_count += 1
            
            # Calculate P&L from closed orders
            closed_pl = sum(order.get('profit', 0.0) for order in self.completed_orders[-closed_orders_count:])
            self.closed_orders_pl += closed_pl
            
            # Update total cycle P&L
            self._update_total_cycle_pl()
            
            # Record reversal in history
            reversal_record = {
                'timestamp': datetime.datetime.now().isoformat(),
                'from_direction': self.current_direction,
                'to_direction': new_direction,
                'price': current_price,
                'closed_orders': closed_orders_count,
                'pl_impact': closed_pl
            }
            
            self.reversal_history.append(reversal_record)
            self.last_reversal_time = datetime.datetime.now()
            
            # Reset price extremes based on active orders after direction switch
            # Since orders were closed during reversal, recalculate from remaining active orders
            self._update_price_extremes(current_price)
                
        except Exception as e:
            logger.error(f"Error updating reversal statistics: {e}")

    def _update_reversal_tracking(self):
        """Update reversal tracking information"""
        try:
            # Calculate current open orders P&L
            self.open_orders_pl = sum(order.get('profit', 0.0) for order in self.active_orders)
            
            # Update total cycle P&L
            self._update_total_cycle_pl()
            
        except Exception as e:
            logger.error(f"Error updating reversal tracking: {e}")

    def _update_total_cycle_pl(self):
        """Update total cycle profit/loss"""
        try:
            self.total_cycle_pl = self.closed_orders_pl + self.open_orders_pl
            
        except Exception as e:
            logger.error(f"Error updating total cycle P&L: {e}")

    def check_take_profit(self, take_profit_amount: float) -> bool:
        """Check if take profit target is reached"""
        try:
            return self.total_cycle_pl >= take_profit_amount
            
        except Exception as e:
            logger.error(f"Error checking take profit: {e}")
            return False

    # ==================== DIRECTION MANAGEMENT ====================

    def switch_direction(self, new_direction: str, reason: str):
        """Switch trading direction"""
        try:
            old_direction = self.current_direction
            self.current_direction = new_direction
            self.direction_switched = True
            self.direction_switches += 1
            
            logger.info(f"Direction switched from {old_direction} to {new_direction}: {reason}")
            
        except Exception as e:
            logger.error(f"Error switching direction: {e}")

    # ==================== ZONE MANAGEMENT ====================

    def should_place_next_order(self, current_price: float, current_time: float) -> bool:
        """Determine if next order should be placed"""
        try:
            # Check time interval
            if self.last_order_time and (current_time - self.last_order_time) < 60:  # 1 minute minimum
                return False
            
            # Check price interval
            if self.last_order_price:
                price_diff = abs(current_price - self.last_order_price)
                pip_diff = price_diff / self._get_pip_value()
                
                if pip_diff < self.order_interval_pips:
                    return False
            
            # Check if zone is activated
            if not self.zone_activated:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if should place next order: {e}")
            return False

    def get_next_order_price(self, current_price: float) -> float:
        """Calculate the price for the next order"""
        try:
            pip_value = self._get_pip_value()
            
            if self.current_direction == "BUY":
                return current_price - (self.order_interval_pips * pip_value)
            else:  # SELL
                return current_price + (self.order_interval_pips * pip_value)
                
        except Exception as e:
            logger.error(f"Error calculating next order price: {e}")
            return current_price

    async def manage_zone_based_orders(self, order_interval_pips: float, 
                                     batch_stop_loss_pips: float, continuous_placement: bool):
        """Manage zone-based order placement"""
        try:
            # This is a placeholder for zone-based order management
            # Implementation would depend on specific zone logic
            logger.info(f"Managing zone-based orders for cycle {self.cycle_id}")
            
        except Exception as e:
            logger.error(f"Error managing zone-based orders: {e}")

    # ==================== DATABASE OPERATIONS ====================

    def _update_cycle_in_database(self):
        """Update cycle in PocketBase database with latest profit information"""
        try:
            if not self.cycle_id:
                logger.error("❌ Cannot update cycle in database: No cycle_id available")
                return False
                
            if not (hasattr(self.bot, 'api_client') and self.bot.api_client):
                logger.error("No API client available for database operations")
                return False
                
            api_client = self.bot.api_client
            
            # Ensure profits are up to date before saving
            self._recalculate_total_profit()
            
            # Prepare comprehensive update data with latest profit information
            update_data = {
                # Order data with latest information
                "active_orders": json.dumps(serialize_datetime_objects(self.active_orders)),
                "completed_orders": json.dumps(serialize_datetime_objects(self.completed_orders)),
                "orders": json.dumps(serialize_datetime_objects(self.active_orders + self.completed_orders)),
                
                # Comprehensive profit tracking
                "total_profit": self._safe_float_conversion(self.total_profit, 0.0),
                "open_orders_pl": self._safe_float_conversion(self.open_orders_pl, 0.0),
                "closed_orders_pl": self._safe_float_conversion(self.closed_orders_pl, 0.0),
                "total_cycle_pl": self._safe_float_conversion(self.total_cycle_pl, 0.0),
                
                # Order and volume statistics
                "total_orders": len(self.active_orders) + len(self.completed_orders),
                "active_orders_count": len(self.active_orders),
                "completed_orders_count": len(self.completed_orders),
                "total_volume": self._safe_float_conversion(sum(float(order.get('volume', 0.0)) for order in self.active_orders + self.completed_orders)),
                
                # Status information
                "status": "active" if self.is_active else "inactive",
                "is_closed": self.is_closed,
                "is_active": self.is_active,
                
                # Direction and trading state
                "direction": self.current_direction,
                "current_direction": self.current_direction,
                "direction_switched": bool(getattr(self, 'direction_switched', False)),
                "direction_switches": int(getattr(self, 'direction_switches', 0)),
                
                # Zone and order management
                "next_order_index": int(getattr(self, 'next_order_index', 1)),
                "accumulated_loss": self._safe_float_conversion(getattr(self, 'accumulated_loss', 0.0)),
                "last_order_price": self._safe_float_conversion(getattr(self, 'last_order_price', 0.0)),
                "zone_activated": bool(getattr(self, 'zone_activated', False)),
                "initial_threshold_breached": bool(getattr(self, 'initial_threshold_breached', False)),
                "zone_based_losses": self._safe_float_conversion(getattr(self, 'zone_based_losses', 0.0)),
                "batch_stop_loss_triggers": int(getattr(self, 'batch_stop_loss_triggers', 0)),
                "current_batch_id": str(getattr(self, 'current_batch_id', '')),
                
                # Reversal trading information
                "reversal_count": int(getattr(self, 'reversal_count', 0)),
                "highest_buy_price": self._safe_float_conversion(getattr(self, 'highest_buy_price', 0.0)),
                "lowest_sell_price": self._safe_float_conversion(getattr(self, 'lowest_sell_price', float('inf'))),
                "reversal_threshold_pips": self._safe_float_conversion(getattr(self, 'reversal_threshold_pips', 50.0)),
                
                # Recovery mode fields
                "in_recovery_mode": getattr(self, 'in_recovery_mode', False),
                "recovery_zone_base_price": self._safe_float_conversion(getattr(self, 'recovery_zone_base_price', 0.0)),
                "initial_stop_loss_price": self._safe_float_conversion(getattr(self, 'initial_stop_loss_price', 0.0)),
                
                # Configuration
                "order_interval_pips": self._safe_float_conversion(getattr(self, 'order_interval_pips', 50.0)),
                "initial_order_stop_loss": self._safe_float_conversion(getattr(self, 'initial_order_stop_loss', 300.0)),
                "cycle_interval": self._safe_float_conversion(getattr(self, 'cycle_interval', 100.0)),
                
                # Timestamp
                "updated": datetime.datetime.now().isoformat()
            }
            
            # Handle datetime fields safely
            if hasattr(self, 'last_order_time') and self.last_order_time:
                if isinstance(self.last_order_time, datetime.datetime):
                    update_data["last_order_time"] = self.last_order_time.isoformat()
                else:
                    update_data["last_order_time"] = str(self.last_order_time)
            
            # Handle reversal history
            if hasattr(self, 'reversal_history') and self.reversal_history:
                update_data["reversal_history"] = json.dumps(serialize_datetime_objects(self.reversal_history))
            
            # Handle closing fields
            if hasattr(self, 'close_reason') and self.close_reason:
                update_data["close_reason"] = str(self.close_reason)
            
            if hasattr(self, 'closed_by') and self.closed_by:
                update_data["closed_by"] = str(self.closed_by)
            
            if hasattr(self, 'close_time') and self.close_time:
                if isinstance(self.close_time, datetime.datetime):
                    update_data["close_time"] = self.close_time.isoformat()
                else:
                    update_data["close_time"] = str(self.close_time)

            # Update using the unified cycle_id
            try:
                api_client.update_ACT_cycle_by_id(self.cycle_id, update_data)
                return True
            except Exception as e:
                logger.error(f"Error updating ACT cycle in database: {e}")
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
            account_id = str(getattr(self.bot.account, 'id', None)) if hasattr(self.bot.account, 'id') else None
            
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
                logger.info(f"Generating temporary cycle_id: {self.cycle_id}")
            
            # Generate initial batch_id
            if not hasattr(self, 'current_batch_id') or not self.current_batch_id:
                self.current_batch_id = f"batch_{self.cycle_id}_1"
                logger.info(f"Generated initial batch_id: {self.current_batch_id}")
            
            # Prepare cycle data for PocketBase
            creation_data = {
                "cycle_id": str(self.cycle_id),
                "bot": bot_id,
                "account": account_id,
                "symbol": str(self.symbol),
                "magic_number": int(getattr(self, 'magic_number', 0)),
                "entry_price": self._safe_getattr_float('entry_price', 0.0),
                "stop_loss": self._safe_getattr_float('stop_loss', 0.0),
                "take_profit": self._safe_getattr_float('take_profit', 0.0),
                "lot_size": self._safe_getattr_float('lot_size', 0.01),
                "direction": str(self.current_direction) if hasattr(self, 'current_direction') else "BUY",
                "current_direction": str(self.current_direction) if hasattr(self, 'current_direction') else "BUY",
                "zone_base_price": self._safe_getattr_float('zone_base_price', 0.0),
                "initial_threshold_price": self._safe_getattr_float('initial_threshold_price', 0.0),
                "reversal_threshold_pips": self._safe_getattr_float('reversal_threshold_pips', 50.0),
                "order_interval_pips": self._safe_getattr_float('order_interval_pips', 50.0),
                "initial_order_stop_loss": self._safe_getattr_float('initial_order_stop_loss', 300.0),
                "cycle_interval": self._safe_getattr_float('cycle_interval', 100.0),
                "zone_activated": bool(getattr(self, 'zone_activated', False)),
                "initial_threshold_breached": bool(getattr(self, 'initial_threshold_breached', False)),
                "direction_switched": bool(getattr(self, 'direction_switched', False)),
                "direction_switches": int(getattr(self, 'direction_switches', 0)),
                "next_order_index": int(getattr(self, 'next_order_index', 1)),
                "active_orders": json.dumps(getattr(self, 'active_orders', [])),
                "completed_orders": json.dumps(getattr(self, 'completed_orders', [])),
                "orders": json.dumps(getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', [])),
                "done_price_levels": json.dumps(getattr(self, 'done_price_levels', [])),
                "total_orders": len(getattr(self, 'active_orders', [])) + len(getattr(self, 'completed_orders', [])),
                "total_volume": self._safe_float_conversion(sum(float(order.get('volume', 0.0)) for order in getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', []))),
                "total_profit": self._safe_getattr_float('total_profit', 0.0),
                "accumulated_loss": self._safe_getattr_float('accumulated_loss', 0.0),
                "zone_based_losses": self._safe_getattr_float('zone_based_losses', 0.0),
                "batch_stop_loss_triggers": int(getattr(self, 'batch_stop_loss_triggers', 0)),
                "is_active": bool(getattr(self, 'is_active', True)),
                "is_closed": bool(getattr(self, 'is_closed', False)),
                "status": "active" if getattr(self, 'is_active', True) else "inactive",
                "current_batch_id": str(self.current_batch_id),
                "last_order_price": self._safe_getattr_float('last_order_price', 0.0),
                "last_order_time": getattr(self, 'last_order_time', None),
                "initial_order_stop_loss": self._safe_getattr_float('initial_order_stop_loss', 300.0),
                "cycle_interval": self._safe_getattr_float('cycle_interval', 100.0),
                "opened_by":self.opened_by,
                "close_reason":self.close_reason,
                "closing_method":self.closing_method,
               
             
            }
            # Handle datetime fields
            if hasattr(self, 'last_order_time') and self.last_order_time:
                if isinstance(self.last_order_time, datetime.datetime):
                    creation_data["last_order_time"] = self.last_order_time.isoformat()
                else:
                    creation_data["last_order_time"] = str(self.last_order_time)
            
            # Create the cycle in PocketBase
            try:
                logger.debug(f"Creating ACT cycle with data keys: {list(creation_data.keys())}")
                
                result = api_client.create_ACT_cycle(creation_data)
                if result and hasattr(result, 'id'):
                    # Update the cycle ID with the one from PocketBase
                    self.cycle_id = result.id
                    logger.info(f"🎯 Successfully created ACT cycle with ID: {self.cycle_id}")
                    
                    # Generate batch ID now that we have cycle_id
                    if not self.current_batch_id or "temp_" in self.current_batch_id:
                        self.current_batch_id = f"batch_{self.cycle_id}_1"
                        
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

    def _prepare_cycle_data_for_database(self) -> dict:
        """Prepare cycle data for database storage"""
        try:
            return {
                'id': self.cycle_id,
                'current_direction': self.current_direction,
                'entry_price': getattr(self, 'entry_price', 0.0),
                'zone_base_price': self.zone_base_price,
                'initial_threshold_price': self.initial_threshold_price,
                'reversal_threshold_pips': self.reversal_threshold_pips,
                'order_interval_pips': self.order_interval_pips,
                'batch_stop_loss_pips': getattr(self, 'batch_stop_loss_pips', 50.0),
                'highest_buy_price': self.highest_buy_price,
                'lowest_sell_price': self.lowest_sell_price,
                'reversal_count': self.reversal_count,
                'closed_orders_pl': self.closed_orders_pl,
                'open_orders_pl': self.open_orders_pl,
                'total_cycle_pl': self.total_cycle_pl,
                'last_reversal_time': self.last_reversal_time,
                'reversal_history': json.dumps(self.reversal_history),
                'active_orders': json.dumps(self._serialize_orders(self.active_orders)),
                'completed_orders': json.dumps(self._serialize_orders(self.completed_orders)),
                'zone_activated': self.zone_activated,
                'initial_threshold_breached': self.initial_threshold_breached,
                'direction_switched': self.direction_switched,
                'direction_switches': self.direction_switches,
                'total_orders': len(self.active_orders) + len(self.completed_orders),
                'total_volume': sum(order.get('volume', 0.0) for order in self.active_orders + self.completed_orders),
                'total_profit': getattr(self, 'total_profit', 0.0),
                'is_closed': self.is_closed,
                'close_reason': getattr(self, 'close_reason', None),
                # Recovery mode fields (NEW)
                'in_recovery_mode': getattr(self, 'in_recovery_mode', False),
                'recovery_zone_base_price': getattr(self, 'recovery_zone_base_price', None),
                'initial_stop_loss_price': getattr(self, 'initial_stop_loss_price', None),
                'updated_at': datetime.datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error preparing cycle data for database: {e}")
            return {}

    def _serialize_orders(self, orders: List[dict]) -> List[dict]:
        """Serialize orders for database storage"""
        try:
            serialized_orders = []
            
            for order in orders:
                serialized_order = {}
                for key, value in order.items():
                    if isinstance(value, datetime.datetime):
                        serialized_order[key] = value.isoformat()
                    elif isinstance(value, (int, float, str, bool, type(None))):
                        serialized_order[key] = value
                    else:
                        serialized_order[key] = str(value)
                
                serialized_orders.append(serialized_order)
            
            return serialized_orders
            
        except Exception as e:
            logger.error(f"Error serializing orders: {e}")
            return []

    # ==================== UTILITY METHODS ====================

    def _get_pip_value(self) -> float:
        """Get pip value for the current symbol"""
        try:
            symbol = getattr(self, 'symbol', '')
            try:
                # Get symbol point from MT5 and multiply by 100 for pip value
                symbol_info = self.meta_trader.get_symbol_info(symbol)
                return symbol_info.point * 100
            except Exception as inner_e:
                logger.warning(f"Could not get symbol point from MT5: {inner_e}, using fallback")
                return 0.0001
        except Exception as e:
            logger.error(f"Error getting pip value: {e}")
            return 0.0001

    def force_sync_with_mt5(self):
        """Force synchronization with MetaTrader 5"""
        try:
            self.update_orders_with_live_data()
            logger.debug(f"Cycle {self.cycle_id} force synced with MT5")
            
        except Exception as e:
            logger.error(f"Error force syncing with MT5: {e}")

    def get_cycle_statistics(self) -> dict:
        """Get comprehensive cycle statistics"""
        try:
            return {
                'cycle_id': self.cycle_id,
                'current_direction': self.current_direction,
                'active_orders_count': len(self.active_orders),
                'completed_orders_count': len(self.completed_orders),
                'total_profit': self.total_profit,
                'reversal_count': self.reversal_count,
                'direction_switches': self.direction_switches,
                'zone_activated': self.zone_activated,
                'is_closed': self.is_closed,
                'total_cycle_pl': self.total_cycle_pl,
                'highest_buy_price': self.highest_buy_price,
                'lowest_sell_price': self.lowest_sell_price,
                'last_update': datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting cycle statistics: {e}")
            return {}

    def validate_cycle_state(self) -> bool:
        """Validate cycle state consistency"""
        try:
            # Check basic requirements
            if not self.cycle_id:
                logger.error("Cycle has no ID")
                return False
            
            if not self.current_direction:
                logger.error("Cycle has no direction")
                return False
            
            # Check order consistency
            total_orders = len(self.active_orders) + len(self.completed_orders)
            if hasattr(self, 'total_orders') and self.total_orders != total_orders:
                logger.warning(f"Order count mismatch: expected {self.total_orders}, actual {total_orders}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating cycle state: {e}")
            return False

    def reset_cycle_state(self):
        """Reset cycle to initial state"""
        try:
            self.active_orders.clear()
            self.completed_orders.clear()
            self.reversal_history.clear()
            self.reversal_count = 0
            self.direction_switches = 0
            self.total_profit = 0.0
            self.closed_orders_pl = 0.0
            self.open_orders_pl = 0.0
            self.total_cycle_pl = 0.0
            self.zone_activated = False
            self.initial_threshold_breached = False
            self.direction_switched = False
            
            logger.info(f"Cycle {self.cycle_id} state reset")
            
        except Exception as e:
            logger.error(f"Error resetting cycle state: {e}")

    def debug_order_status(self):
        """Debug method to log order status"""
        try:
            logger.info(f"Cycle {self.cycle_id} Order Status:")
            logger.info(f"  Active Orders: {len(self.active_orders)}")
            logger.info(f"  Completed Orders: {len(self.completed_orders)}")
            logger.info(f"  Total Profit: {self.total_profit}")
            logger.info(f"  Direction: {self.current_direction}")
            logger.info(f"  Reversal Count: {self.reversal_count}")
            
            for i, order in enumerate(self.active_orders):
                logger.info(f"    Active[{i}]: {order.get('ticket')} - {order.get('profit', 0.0)}")
            
        except Exception as e:
            logger.error(f"Error debugging order status: {e}")


# ==================== UTILITY FUNCTIONS ====================

def serialize_datetime_objects(obj):
    """Recursively serialize datetime objects and other complex types"""
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
    elif hasattr(obj, '__dict__'):
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
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            return str(data) 