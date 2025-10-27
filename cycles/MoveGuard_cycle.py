"""
MoveGuard Cycle - Grid-Based Trading Cycle

This is a specialized cycle class for the MoveGuard strategy with:
- Grid-based order placement and management
- Adaptive zone management with movement modes
- Multiple stop-loss configurations (Initial, Cycle, Recovery)
- Zone movement modes (No Move, Move Up Only, Move Down Only, Move Both Sides)
- Trade limits and cycle management
- Real-time synchronization with MetaTrader and database
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


class MoveGuardCycle(cycle):
    """
    MoveGuard Cycle with Grid-Based Trading Logic and Adaptive Zone Management
    
    Features:
    - Grid-based order placement with specific intervals
    - Adaptive zone management with movement modes
    - Multiple stop-loss configurations (Initial, Cycle, Recovery)
    - Zone movement modes (No Move, Move Up Only, Move Down Only, Move Both Sides)
    - Trade limits and cycle management
    - Real-time synchronization with MetaTrader
    """

    def __init__(self, cycle_data=None, meta_trader=None, bot=None):
        """Initialize MoveGuard Cycle with enhanced features"""
        self.bot = bot
        self.meta_trader = meta_trader
        
        # Initialize all fields with defaults
        self._initialize_defaults()
        
        # If cycle data provided, initialize from it
        if cycle_data:
            self._initialize_cycle_data(cycle_data)
            
        logger.info(f"MoveGuardCycle initialized with ID: {getattr(self, 'cycle_id', 'NEW')}")
        
    def _validate_cycle_data(self, cycle_data):
        """Validate required fields in cycle data"""
        required_fields = ['symbol', 'direction']
        for field in required_fields:
            if field not in cycle_data:
                raise ValueError(f"Missing required field: {field}")
                
    def _parse_json_field(self, field_value, default_value=None):
        """Parse a JSON field safely"""
        try:
            if isinstance(field_value, str):
                return json.loads(field_value)
            elif field_value is None:
                return default_value
            return field_value
        except Exception as e:
            logger.error(f"Error parsing JSON field: {e}")
            return default_value
            
    def _initialize_cycle_data(self, cycle_data):
        """Initialize cycle data from database record"""
        try:
            # Initialize defaults first
            self._initialize_defaults()
            
            # Basic cycle info
            self.cycle_id = cycle_data.get('id')
            self.account_id = cycle_data.get('account')
            self.bot_id = cycle_data.get('bot')
            self.is_closed = bool(cycle_data.get('is_closed', False))
            self.is_favorite = bool(cycle_data.get('is_favorite', False))
            self.symbol = cycle_data.get('symbol')
            self.price_level = float(cycle_data.get('price_level', 0.0))
            
            # Status handling
            self.status = cycle_data.get('status', 'ACTIVE')
            self.is_active = not self.is_closed and self.status == 'ACTIVE'
            
            # JSON fields
            self.opened_by = self._parse_json_field(cycle_data.get('opened_by'), {})
            self.closing_method = self._parse_json_field(cycle_data.get('closing_method'), {})
            self.orders = self._parse_json_field(cycle_data.get('orders'), [])
            self.orders_config = self._parse_json_field(cycle_data.get('orders_config'), {})
            self.active_orders = self._parse_json_field(cycle_data.get('active_orders'), [])
            self.completed_orders = self._parse_json_field(cycle_data.get('completed_orders'), [])
            self.done_price_levels = self._parse_json_field(cycle_data.get('done_price_levels'), [])
            
            # Load pending orders data for MoveGuard strategy
            self.pending_orders = self._parse_json_field(cycle_data.get('pending_orders'), [])
            pending_levels_data = self._parse_json_field(cycle_data.get('pending_order_levels'), [])
            self.pending_order_levels = set(pending_levels_data) if isinstance(pending_levels_data, list) else set()
            
            # Direction and zone settings
            self.direction = cycle_data.get('direction', 'BUY')
            self.current_direction = cycle_data.get('current_direction', self.direction)
            self.zone_base_price = float(cycle_data.get('zone_base_price', 0.0))
            self.initial_threshold_price = float(cycle_data.get('initial_threshold_price', 0.0))
            self.zone_threshold_pips = float(cycle_data.get('zone_threshold_pips', 0.0))
            self.order_interval_pips = float(cycle_data.get('order_interval_pips', 0.0))
            self.batch_stop_loss_pips = float(cycle_data.get('batch_stop_loss_pips', 0.0))
            self.zone_range_pips = float(cycle_data.get('zone_range_pips', 0.0))
            self.total_volume = float(cycle_data.get('total_volume', 0.0))
            self.total_profit = float(cycle_data.get('total_profit', 0.0))
           
            # Price bounds and levels
            self.lower_bound = float(cycle_data.get('lower_bound', 0.0))
            self.upper_bound = float(cycle_data.get('upper_bound', 0.0))
            self.entry_price = float(cycle_data.get('entry_price', 0.0))
            self.stop_loss = float(cycle_data.get('stop_loss', 0.0))
            self.take_profit = float(cycle_data.get('take_profit', 0.0))
            self.lot_size = float(cycle_data.get('lot_size', 0.0))
            
            # Order tracking
            self.next_order_index = int(cycle_data.get('next_order_index', 0))
            self.current_batch_id = cycle_data.get('current_batch_id')
            self.last_order_price = float(cycle_data.get('last_order_price', 0.0))
            self.last_order_time = cycle_data.get('last_order_time')
            
            # Loss tracking
            self.accumulated_loss = float(cycle_data.get('accumulated_loss', 0.0))
            self.batch_losses = float(cycle_data.get('batch_losses', 0.0))
            
            # Closing info
            self.close_reason = cycle_data.get('close_reason', '')
            self.close_time = cycle_data.get('close_time')
            
            # Order statistics
            self.total_orders = int(cycle_data.get('total_orders', 0))
            self.profitable_orders = int(cycle_data.get('profitable_orders', 0))
            self.loss_orders = int(cycle_data.get('loss_orders', 0))
            self.duration_minutes = int(cycle_data.get('duration_minutes', 0))
            
            # MoveGuard-specific fields
            self.grid_data = self._parse_json_field(cycle_data.get('grid_data'), {})
            self.zone_data = self._parse_json_field(cycle_data.get('zone_data'), {})
            self.recovery_data = self._parse_json_field(cycle_data.get('recovery_data'), {})
            self.grid_interval_pips = float(cycle_data.get('grid_interval_pips', 50.0))
            self.entry_interval_pips = float(cycle_data.get('entry_interval_pips', 10.0))
            self.initial_stop_loss_pips = float(cycle_data.get('initial_stop_loss_pips', 300.0))
            self.cycle_stop_loss_pips = float(cycle_data.get('cycle_stop_loss_pips', 200.0))
            self.recovery_stop_loss_pips = float(cycle_data.get('recovery_stop_loss_pips', 150.0))
            self.cycle_take_profit_pips = float(cycle_data.get('cycle_take_profit_pips', 100.0))
            self.max_trades_per_cycle = int(cycle_data.get('max_trades_per_cycle', 10))
            self.zone_movement_mode = cycle_data.get('zone_movement_mode', 'NO_MOVE')
            self.recovery_enabled = bool(cycle_data.get('recovery_enabled', True))
            
            # Recovery mode
            self.in_recovery_mode = bool(cycle_data.get('in_recovery_mode', False))
            self.recovery_activated = bool(cycle_data.get('recovery_activated', False))
            self.recovery_direction = cycle_data.get('recovery_direction')
            self.initial_direction = cycle_data.get('initial_direction', cycle_data.get('direction', 'BUY'))
            self.placed_levels = self._parse_json_field(cycle_data.get('placed_levels'), [])
            self.initial_order_data = self._parse_json_field(cycle_data.get('initial_order_data'), {})
            self.recovery_zone_base_price = float(cycle_data.get('recovery_zone_base_price', 0.0))
            self.initial_stop_loss_price = float(cycle_data.get('initial_stop_loss_price', 0.0))
            self.initial_order_open_price = float(cycle_data.get('initial_order_open_price', 0.0))
            self.initial_order_stop_loss = float(cycle_data.get('initial_order_stop_loss', 0.0))
            self.lot_idx = int(cycle_data.get('lot_idx', 0))
            
            # Configuration
            self.cycle_type = cycle_data.get('cycle_type', 'MoveGuard')
            self.magic_number = int(cycle_data.get('magic_number', 0))
            
            # Cycle-specific configuration
            self.cycle_config = self._parse_json_field(cycle_data.get('cycle_config'), {})
            
            # Trailing stop-loss and price tracking fields
            self.trailing_stop_loss = float(cycle_data.get('trailing_stop_loss', 0.0))
            self.highest_buy_price = float(cycle_data.get('highest_buy_price', 0.0))
            # Use a very large number instead of infinity for database compatibility
            self.lowest_sell_price = float(cycle_data.get('lowest_sell_price', 999999.0))
            
            logger.info(f"Successfully initialized MoveGuardCycle {self.cycle_id} from database record")
            
        except Exception as e:
            logger.error(f"Error initializing MoveGuardCycle data: {e}")
            raise

    def _initialize_defaults(self):
        """Initialize all fields with default values"""
        # Basic cycle info
        self.cycle_id = None
        self.account_id = None
        self.bot_id = None
        self.is_closed = False
        self.is_favorite = False
        self.is_active = True  # Default to active
        self.symbol = None
        self.opened_by = {}
        self.closing_method = {}
        self.lot_idx = 0
        self.status = 'ACTIVE'
        self.initial_order_open_datetime = None 
        
        # Price bounds
        self.lower_bound = 0.0
        self.upper_bound = 0.0
        
        # Volume and profit
        self.total_volume = 0.0
        self.total_profit = 0.0
        
        # Orders and configuration
        self.orders = []
        self.orders_config = {}
        self.cycle_type = 'MoveGuard'
        self.magic_number = 0
        
        # Pending orders tracking for MoveGuard strategy
        self.pending_orders = []
        self.pending_order_levels = set()
        
        # Cycle-specific configuration
        self.cycle_config = {}
        
        # Price levels
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.lot_size = 0.0
        self.price_level = 0.0
        
        # Direction and zone settings
        self.direction = 'BUY'
        self.current_direction = 'BUY'
        self.zone_base_price = 0.0
        self.initial_threshold_price = 0.0
        self.zone_threshold_pips = 0.0
        self.order_interval_pips = 0.0
        self.batch_stop_loss_pips = 0.0
        self.zone_range_pips = 0.0
        
        # Order tracking
        self.next_order_index = 0
        self.done_price_levels = []
        self.active_orders = []
        self.completed_orders = []
        self.current_batch_id = None
        
        # Last order info
        self.last_order_price = 0.0
        self.last_order_time = None
        
        # Loss tracking
        self.accumulated_loss = 0.0
        self.batch_losses = 0.0
        
        # Closing info
        self.close_reason = ''
        self.close_time = None
        
        # Order statistics
        self.total_orders = 0
        self.profitable_orders = 0
        self.loss_orders = 0
        self.duration_minutes = 0
        
        # MoveGuard-specific fields
        self.grid_data = {
            'current_level': 0,
            'grid_direction': 'BUY',
            'last_grid_price': 0.0,
            'grid_orders': []
        }
        self.zone_data = {
            'base_price': 0.0,
            'upper_boundary': 0.0,
            'lower_boundary': 0.0,
            'movement_mode': 'NO_MOVE',
            'last_movement': None
        }
        self.recovery_data = {
            'recovery_orders': [],
            'recovery_activated': False,
            'recovery_direction': None
        }
        self.grid_interval_pips = 50.0
        self.entry_interval_pips = 10.0
        self.initial_stop_loss_pips = 300.0
        self.cycle_stop_loss_pips = 200.0
        self.recovery_stop_loss_pips = 150.0
        self.cycle_take_profit_pips = 100.0
        self.max_trades_per_cycle = 10
        self.zone_movement_mode = 'NO_MOVE'
        self.recovery_enabled = True
        
        # Recovery mode
        self.in_recovery_mode = False
        self.recovery_zone_base_price = 0.0
        self.initial_stop_loss_price = 0.0
        self.initial_order_stop_loss = 0.0
        self.recovery_activated = False
        self.recovery_direction = None
        self.initial_direction = None
        self.initial_order_open_price = 0.0
        self.placed_levels = []
        self.initial_order_data = {}
        
        # Trailing stop-loss and price tracking fields
        self.trailing_stop_loss = 0.0
        self.highest_buy_price = 0.0
        # Use a very large number instead of infinity for database compatibility
        self.lowest_sell_price = 999999.0

    # ==================== GRID MANAGEMENT ====================

    def add_grid_order(self, order_data: dict, grid_level: int):
        """Add a grid order to the cycle"""
        try:
            # Add grid-specific information
            order_data['grid_level'] = grid_level
            order_data['order_type'] = 'grid'
            order_data['placed_at'] = datetime.datetime.now().isoformat()
            
            # Add to active orders
            self.active_orders.append(order_data)
            
            # Update grid data
            if not isinstance(self.grid_data, dict):
                self.grid_data = {}
            
            self.grid_data['current_level'] = grid_level
            self.grid_data['last_grid_price'] = order_data.get('price', 0.0)
            self.grid_data['grid_orders'].append(order_data)
            
            # Update cycle statistics
            self.total_orders += 1
            self.total_volume += order_data.get('lot_size', 0.0)
            
            logger.info(f"Grid order added to cycle {self.cycle_id}: level {grid_level}, ticket {order_data.get('ticket')}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding grid order: {e}")
            return False

    def get_grid_level(self, current_price: float) -> int:
        """Calculate current grid level based on price movement from entry"""
        try:
            if not self.entry_price:
                return 0
            
            # Calculate price difference in pips
            pip_value = self._get_pip_value()
            price_diff = abs(current_price - self.entry_price)
            pips_diff = price_diff / pip_value
            
            # Calculate grid level based on interval
            grid_level = int(pips_diff / self.grid_interval_pips)
            
            # Ensure grid level is non-negative
            grid_level = max(0, grid_level)
            
            return grid_level
            
        except Exception as e:
            logger.error(f"Error calculating grid level: {e}")
            return 0

    def should_place_grid_order(self, current_price: float, grid_level: int) -> bool:
        """Check if a grid order should be placed"""
        try:
            # Check if we've reached max trades per cycle
            if len(self.active_orders) >= self.max_trades_per_cycle:
                return False
            
            # Check if grid level is higher than current level
            current_grid_level = self.grid_data.get('current_level', 0)
            if grid_level <= current_grid_level:
                return False
            
            # Check if current price is near the grid level
            grid_price = self._calculate_grid_price(grid_level)
            price_diff = abs(current_price - grid_price)
            pip_diff = price_diff / self._get_pip_value()
            
            return pip_diff <= self.entry_interval_pips
            
        except Exception as e:
            logger.error(f"Error checking if should place grid order: {e}")
            return False

    def _calculate_grid_price(self, grid_level: int) -> float:
        """Calculate the price for a specific grid level"""
        try:
            pip_value = self._get_pip_value()
            grid_pips = grid_level * self.grid_interval_pips
            
            if self.direction == 'BUY':
                # For BUY cycles, place orders at lower prices (below entry)
                return self.entry_price - (grid_pips * pip_value)
            else:  # SELL
                # For SELL cycles, place orders at higher prices (above entry)
                return self.entry_price + (grid_pips * pip_value)
                
        except Exception as e:
            logger.error(f"Error calculating grid price: {e}")
            return self.entry_price

    # ==================== ZONE MANAGEMENT ====================

    def initialize_zone_data(self, base_price: float, threshold_pips: float):
        """Initialize zone data for the cycle"""
        try:
            pip_value = self._get_pip_value()
            
            self.zone_data = {
                'base_price': base_price,
                'upper_boundary': base_price + (threshold_pips * pip_value),
                'lower_boundary': base_price - (threshold_pips * pip_value),
                'movement_mode': self.zone_movement_mode,
                'last_movement': None
            }
            
            logger.info(f"Zone data initialized for cycle {self.cycle_id}: base_price={base_price}, threshold_pips={threshold_pips}")
            
        except Exception as e:
            logger.error(f"Error initializing zone data: {e}")

    def check_zone_movement(self, current_price: float) -> dict:
        """Check if zone should be moved based on current price"""
        try:
            if not self.zone_data:
                return {'should_move': False, 'direction': None}
            
            base_price = self.zone_data['base_price']
            upper_boundary = self.zone_data['upper_boundary']
            lower_boundary = self.zone_data['lower_boundary']
            movement_mode = self.zone_data['movement_mode']
            
            should_move = False
            direction = None
            
            if movement_mode == 'NO_MOVE':
                return {'should_move': False, 'direction': None}
            
            elif movement_mode == 'MOVE_UP_ONLY':
                if current_price > upper_boundary:
                    should_move = True
                    direction = 'UP'
            
            elif movement_mode == 'MOVE_DOWN_ONLY':
                if current_price < lower_boundary:
                    should_move = True
                    direction = 'DOWN'
            
            elif movement_mode == 'MOVE_BOTH_SIDES':
                if current_price > upper_boundary:
                    should_move = True
                    direction = 'UP'
                elif current_price < lower_boundary:
                    should_move = True
                    direction = 'DOWN'
            
            return {
                'should_move': should_move,
                'direction': direction,
                'current_price': current_price,
                'base_price': base_price,
                'upper_boundary': upper_boundary,
                'lower_boundary': lower_boundary
            }
            
        except Exception as e:
            logger.error(f"Error checking zone movement: {e}")
            return {'should_move': False, 'direction': None}

    def move_zone(self, direction: str, current_price: float):
        """Move the zone in the specified direction"""
        try:
            if not self.zone_data:
                logger.warning("No zone data to move")
                return False
            
            pip_value = self._get_pip_value()
            threshold_pips = self.zone_threshold_pips
            
            if direction == 'UP':
                new_base_price = current_price + (threshold_pips * pip_value)
            elif direction == 'DOWN':
                new_base_price = current_price - (threshold_pips * pip_value)
            else:
                logger.error(f"Invalid zone movement direction: {direction}")
                return False
            
            # Update zone data
            self.zone_data['base_price'] = new_base_price
            self.zone_data['upper_boundary'] = new_base_price + (threshold_pips * pip_value)
            self.zone_data['lower_boundary'] = new_base_price - (threshold_pips * pip_value)
            self.zone_data['last_movement'] = {
                'direction': direction,
                'price': current_price,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            logger.info(f"Zone moved {direction} for cycle {self.cycle_id}: new_base_price={new_base_price}")
            return True
            
        except Exception as e:
            logger.error(f"Error moving zone: {e}")
            return False

    # ==================== RECOVERY MANAGEMENT ====================

    def initialize_recovery_mode(self, recovery_direction: str, recovery_price: float):
        """Initialize recovery mode for the cycle"""
        try:
            self.in_recovery_mode = True
            self.recovery_activated = True
            self.recovery_direction = recovery_direction
            self.recovery_zone_base_price = recovery_price
            
            self.recovery_data = {
                'recovery_orders': [],
                'recovery_activated': True,
                'recovery_direction': recovery_direction,
                'recovery_start_price': recovery_price,
                'recovery_start_time': datetime.datetime.now().isoformat()
            }
            
            logger.info(f"Recovery mode initialized for cycle {self.cycle_id}: direction={recovery_direction}, price={recovery_price}")
            
        except Exception as e:
            logger.error(f"Error initializing recovery mode: {e}")

    def add_recovery_order(self, order_data: dict):
        """Add a recovery order to the cycle"""
        try:
            # Add recovery-specific information
            order_data['order_type'] = 'recovery'
            order_data['placed_at'] = datetime.datetime.now().isoformat()
            
            # Add to active orders
            self.active_orders.append(order_data)
            
            # Add to recovery data
            if not isinstance(self.recovery_data, dict):
                self.recovery_data = {}
            
            self.recovery_data['recovery_orders'].append(order_data)
            
            # Update cycle statistics
            self.total_orders += 1
            self.total_volume += order_data.get('lot_size', 0.0)
            
            logger.info(f"Recovery order added to cycle {self.cycle_id}: ticket {order_data.get('ticket')}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding recovery order: {e}")
            return False

    def check_recovery_conditions(self, current_price: float) -> bool:
        """Check if recovery conditions are met"""
        try:
            if not self.recovery_enabled or not self.in_recovery_mode:
                return False
            
            # Check if current price is favorable for recovery
            if self.recovery_direction == 'BUY' and current_price < self.recovery_zone_base_price:
                return True
            elif self.recovery_direction == 'SELL' and current_price > self.recovery_zone_base_price:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking recovery conditions: {e}")
            return False

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
            self.total_orders += 1
            self.total_volume += order_data.get('lot_size', 0.0)
            
            # Update grid data if it's a grid order
            if order_data.get('order_type') == 'grid':
                grid_level = order_data.get('grid_level', 0)
                self.grid_data['current_level'] = grid_level
                self.grid_data['grid_orders'].append(order_data)
            
            # Update recovery data if it's a recovery order
            if order_data.get('order_type') == 'recovery':
                if not isinstance(self.recovery_data, dict):
                    self.recovery_data = {}
                self.recovery_data['recovery_orders'].append(order_data)
            
            logger.info(f"Order {order_data.get('ticket')} added to MoveGuardCycle {self.cycle_id}")
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
        """Convert order object to standardized dictionary format"""
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
            'comment': ['comment', 'description'],
            'open_time': ['time_setup', 'time_setup_msc', 'time', 'open_time', 'placed_at', 'open_datetime'],
            'placed_at': ['time_setup', 'time_setup_msc', 'time', 'placed_at', 'open_time', 'placed_datetime']
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
                        elif target_field in ['open_time', 'placed_at']:
                            # Convert MT5 timestamp to ISO format
                            order_data[target_field] = self._convert_timestamp_to_iso(value)
                        else:
                            order_data[target_field] = self._safe_float_conversion(value)
                        break
        
        # Set default values
        order_data.setdefault('ticket', 0)
        order_data.setdefault('direction', self.direction)
        order_data.setdefault('status', 'active')
        # CRITICAL FIX: Only set open_time if it doesn't exist, preserve original timestamp
        if 'open_time' not in order_data:
            order_data['open_time'] = datetime.datetime.now().isoformat()
        order_data.setdefault('symbol', self.symbol)
        order_data.setdefault('open_price', 0.0)
        order_data.setdefault('volume', 0.0)
        order_data.setdefault('profit', 0.0)
        order_data.setdefault('swap', 0.0)
        order_data.setdefault('commission', 0.0)
        order_data.setdefault('magic_number', 0)
        order_data.setdefault('comment', '')
        order_data.setdefault('sl', 0.0)
        order_data.setdefault('tp', 0.0)
        
        return order_data

    def _create_order_data_from_ticket(self, ticket) -> dict:
        """Create order data from ticket number"""
        return {
            'ticket': int(ticket),
            'direction': self.direction,
            'status': 'active',
            'open_time': datetime.datetime.now().isoformat(),
            'symbol': self.symbol,
            'open_price': 0.0,
            'volume': 0.0,
            'profit': 0.0,
            'swap': 0.0,
            'commission': 0.0,
            'magic_number': 0,
            'comment': '',
            'sl': 0.0,
            'tp': 0.0
        }

    def _safe_float_conversion(self, value, default=0.0) -> float:
        """Safely convert a value to float"""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _convert_timestamp_to_iso(self, timestamp_value) -> str:
        """Convert MT5 timestamp to ISO format string"""
        try:
            # If already a string (ISO format), return as-is
            if isinstance(timestamp_value, str):
                return timestamp_value
            
            # If it's a datetime object, convert to ISO string
            if isinstance(timestamp_value, datetime.datetime):
                return timestamp_value.isoformat()
            
            # If it's a numeric timestamp (Unix time), convert to datetime then ISO
            if isinstance(timestamp_value, (int, float)):
                # MT5 timestamps are Unix timestamps (seconds since epoch)
                dt = datetime.datetime.fromtimestamp(timestamp_value)
                return dt.isoformat()
            
            # Fallback to current time if conversion fails
            logger.warning(f"Could not convert timestamp value {timestamp_value} to ISO format, using current time")
            return datetime.datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"Error converting timestamp to ISO: {e}")
            return datetime.datetime.now().isoformat()

    # ==================== DATABASE OPERATIONS ====================

    def _create_cycle_in_database(self):
        """Create cycle in PocketBase database"""
        try:
            if not (hasattr(self.bot, 'api_client') and self.bot.api_client):
                logger.error("No API client available for database operations")
                return False
                
            api_client = self.bot.api_client
            
            # Ensure bot and account are valid relation IDs
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
                self.cycle_id = f"MG_{uuid.uuid4().hex}"
                logger.info(f"Generating temporary cycle_id: {self.cycle_id}")
            
            # Prepare cycle data for PocketBase
            creation_data = {
                "cycle_id": str(self.cycle_id),
                "bot": bot_id,
                "account": account_id,
                "symbol": str(self.symbol),
                "magic_number": int(getattr(self, 'magic_number', 0)),
                "entry_price": self._safe_float_conversion(getattr(self, 'entry_price', 0.0)),
                "stop_loss": self._safe_float_conversion(getattr(self, 'stop_loss', 0.0)),
                "take_profit": self._safe_float_conversion(getattr(self, 'take_profit', 0.0)),
                "lot_size": self._safe_float_conversion(getattr(self, 'lot_size', 0.01)),
                "direction": str(self.direction),
                "current_direction": str(self.current_direction),
                "zone_base_price": self._safe_float_conversion(getattr(self, 'zone_base_price', 0.0)),
                "initial_threshold_price": self._safe_float_conversion(getattr(self, 'initial_threshold_price', 0.0)),
                "grid_interval_pips": self._safe_float_conversion(getattr(self, 'grid_interval_pips', 50.0)),
                "entry_interval_pips": self._safe_float_conversion(getattr(self, 'entry_interval_pips', 10.0)),
                "initial_stop_loss_pips": self._safe_float_conversion(getattr(self, 'initial_stop_loss_pips', 300.0)),
                "cycle_stop_loss_pips": self._safe_float_conversion(getattr(self, 'cycle_stop_loss_pips', 200.0)),
                "recovery_stop_loss_pips": self._safe_float_conversion(getattr(self, 'recovery_stop_loss_pips', 150.0)),
                "cycle_take_profit_pips": self._safe_float_conversion(getattr(self, 'cycle_take_profit_pips', 100.0)),
                "max_trades_per_cycle": int(getattr(self, 'max_trades_per_cycle', 10)),
                "zone_movement_mode": getattr(self, 'zone_movement_mode', 'NO_MOVE'),
                "recovery_enabled": bool(getattr(self, 'recovery_enabled', True)),
                "active_orders": json.dumps(getattr(self, 'active_orders', [])),
                "completed_orders": json.dumps(getattr(self, 'completed_orders', [])),
                "orders": json.dumps(getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', [])),
                "grid_data": json.dumps(getattr(self, 'grid_data', {})),
                "zone_data": json.dumps(getattr(self, 'zone_data', {})),
                "recovery_data": json.dumps(getattr(self, 'recovery_data', {})),
                "total_orders": len(getattr(self, 'active_orders', [])) + len(getattr(self, 'completed_orders', [])),
                "total_volume": self._safe_float_conversion(sum(float(order.get('volume', 0.0)) for order in getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', []))),
                "total_profit": self._safe_float_conversion(getattr(self, 'total_profit', 0.0)),
                "is_active": bool(getattr(self, 'is_active', True)),
                "is_closed": bool(getattr(self, 'is_closed', False)),
                "status": "active" if getattr(self, 'is_active', True) else "inactive",
                "cycle_type": "MoveGuard"
            }
            
            # Create the cycle in PocketBase
            try:
                logger.debug(f"Creating MoveGuard cycle with data keys: {list(creation_data.keys())}")
                
                result = api_client.create_MG_cycle(creation_data)
                if result and hasattr(result, 'id'):
                    # Update the cycle ID with the one from PocketBase
                    self.cycle_id = result.id
                    logger.info(f"🎯 Successfully created MoveGuard cycle with ID: {self.cycle_id}")
                    return True
                else:
                    logger.error("Failed to create MoveGuard cycle: No result or result.id")
                    return False
                    
            except Exception as e:
                logger.error(f"Error creating MoveGuard cycle: {e}")
                logger.error(f"Data keys sent: {list(creation_data.keys())}")
                return False
                
        except Exception as e:
            logger.error(f"Error in _create_cycle_in_database: {e}")
            return False

    def _update_cycle_in_database(self):
        """Update cycle in database"""
        try:
            if not self.cycle_id:
                logger.error("❌ Cannot update cycle in database: No cycle_id available")
                return False
                
            if not (hasattr(self.bot, 'api_client') and self.bot.api_client):
                logger.error("No API client available for database operations")
                return False
                
            api_client = self.bot.api_client
            
            # Prepare data for database update
            data = {
                'id': self.cycle_id,
                'bot': str(self.bot_id),
                'account': str(self.account_id),
                'symbol': self.symbol,
                'is_closed': self.is_closed,
                'is_favorite': getattr(self, 'is_favorite', False),
                'status': getattr(self, 'status', 'closed' if self.is_closed else 'active'),
                'magic_number': getattr(self, 'magic_number', 0),
                'entry_price': self._safe_float_conversion(getattr(self, 'entry_price', 0.0)),
                'stop_loss': self._safe_float_conversion(getattr(self, 'stop_loss', 0.0)),
                'take_profit': self._safe_float_conversion(getattr(self, 'take_profit', 0.0)),
                'lot_size': self._safe_float_conversion(getattr(self, 'lot_size', 0.01)),
                'direction': self.direction,
                'current_direction': self.current_direction,
                'zone_base_price': self._safe_float_conversion(getattr(self, 'zone_base_price', 0.0)),
                'initial_threshold_price': self._safe_float_conversion(getattr(self, 'initial_threshold_price', 0.0)),
                'grid_interval_pips': self._safe_float_conversion(getattr(self, 'grid_interval_pips', 50.0)),
                'entry_interval_pips': self._safe_float_conversion(getattr(self, 'entry_interval_pips', 10.0)),
                'initial_stop_loss_pips': self._safe_float_conversion(getattr(self, 'initial_stop_loss_pips', 300.0)),
                'cycle_stop_loss_pips': self._safe_float_conversion(getattr(self, 'cycle_stop_loss_pips', 200.0)),
                'recovery_stop_loss_pips': self._safe_float_conversion(getattr(self, 'recovery_stop_loss_pips', 150.0)),
                'cycle_take_profit_pips': self._safe_float_conversion(getattr(self, 'cycle_take_profit_pips', 100.0)),
                'max_trades_per_cycle': int(getattr(self, 'max_trades_per_cycle', 10)),
                'zone_movement_mode': getattr(self, 'zone_movement_mode', 'NO_MOVE'),
                'recovery_enabled': bool(getattr(self, 'recovery_enabled', True)),
                'total_orders': len(getattr(self, 'active_orders', [])) + len(getattr(self, 'completed_orders', [])),
                'total_volume': self._safe_float_conversion(getattr(self, 'total_volume', 0.0)),
                'total_profit': self._safe_float_conversion(getattr(self, 'total_profit', 0.0)),
                'is_active': bool(getattr(self, 'is_active', True)),
                'is_closed': bool(getattr(self, 'is_closed', False)),
                'orders': json.dumps(getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', [])),
                'active_orders': json.dumps(getattr(self, 'active_orders', [])),
                'completed_orders': json.dumps(getattr(self, 'completed_orders', [])),
                'pending_orders': json.dumps(getattr(self, 'pending_orders', [])),
                'pending_order_levels': json.dumps(list(getattr(self, 'pending_order_levels', set()))),
                'grid_data': json.dumps(getattr(self, 'grid_data', {})),
                'zone_data': json.dumps(getattr(self, 'zone_data', {})),
                'recovery_data': json.dumps(getattr(self, 'recovery_data', {})),
                'cycle_type': 'MoveGuard',
                'upper_bound': self._safe_float_conversion(getattr(self, 'zone_data', {}).get('upper_boundary', 0.0)),
                'lower_bound': self._safe_float_conversion(getattr(self, 'zone_data', {}).get('lower_boundary', 0.0)),
            
            }
            
            # Update the record in PocketBase
            api_client.update_MG_cycle_by_id(data['id'], data)
            
            logger.info(f"✅ Successfully updated MoveGuard cycle {data['id']} in database")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating MoveGuard cycle {self.cycle_id} in database: {e}")
            return False

    # ==================== UTILITY METHODS ====================

    def _get_pip_value(self) -> float:
        """Get pip value for the current symbol"""
        try:
            symbol = getattr(self, 'symbol', '')
            try:
                # Get symbol point from MT5 and multiply by 10 for pip value
                symbol_info = self.meta_trader.get_symbol_info(symbol)
                return symbol_info.point * 10
            except Exception as inner_e:
                logger.warning(f"Could not get symbol point from MT5: {inner_e}, using fallback")
                return 0.0001
        except Exception as e:
            logger.error(f"Error getting pip value: {e}")
            return 0.0001

    def get_cycle_statistics(self) -> dict:
        """Get comprehensive cycle statistics"""
        try:
            return {
                'cycle_id': self.cycle_id,
                'current_direction': self.current_direction,
                'active_orders_count': len(self.active_orders),
                'completed_orders_count': len(self.completed_orders),
                'total_profit': self.total_profit,
                'grid_level': self.grid_data.get('current_level', 0),
                'zone_movement_mode': self.zone_movement_mode,
                'recovery_enabled': self.recovery_enabled,
                'in_recovery_mode': self.in_recovery_mode,
                'is_closed': self.is_closed,
                'total_volume': self.total_volume,
                'total_orders': self.total_orders,
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
            if self.total_orders != total_orders:
                logger.warning(f"Order count mismatch: expected {self.total_orders}, actual {total_orders}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating cycle state: {e}")
            return False

    def close_cycle(self, reason: str):
        """Close the cycle and update its status"""
        try:
            logger.info(f"Closing MoveGuard cycle {self.cycle_id} with reason: {reason}")
            
            # Set cycle status
            self.is_active = False
            self.is_closed = True
            self.close_reason = reason
            self.close_time = datetime.datetime.now().isoformat()
            
            # Update database
            self._update_cycle_in_database()
            
            logger.info(f"MoveGuard cycle {self.cycle_id} closed successfully. Final profit: {self.total_profit}")
            
        except Exception as e:
            logger.error(f"Error closing cycle: {e}")

    def debug_cycle_status(self):
        """Debug method to log cycle status"""
        try:
            logger.info(f"MoveGuard Cycle {self.cycle_id} Status:")
            logger.info(f"  Active Orders: {len(self.active_orders)}")
            logger.info(f"  Completed Orders: {len(self.completed_orders)}")
            logger.info(f"  Total Profit: {self.total_profit}")
            logger.info(f"  Direction: {self.current_direction}")
            logger.info(f"  Grid Level: {self.grid_data.get('current_level', 0)}")
            logger.info(f"  Zone Movement Mode: {self.zone_movement_mode}")
            logger.info(f"  Recovery Mode: {self.in_recovery_mode}")
            logger.info(f"  Is Closed: {self.is_closed}")
            
        except Exception as e:
            logger.error(f"Error debugging cycle status: {e}")

    # ==================== CYCLE CONFIGURATION MANAGEMENT ====================

    def get_cycle_config_value(self, config_key, default_value=None):
        """Get configuration value from cycle-specific config"""
        try:
            if not hasattr(self, 'cycle_config') or not self.cycle_config:
                logger.debug(f"📋 No cycle config available for {config_key}, using default: {default_value}")
                return default_value
            
            # Parse JSON if it's a string
            cycle_config = self.cycle_config
            if isinstance(cycle_config, str):
                try:
                    cycle_config = json.loads(cycle_config)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in cycle_config for {self.cycle_id}")
                    return default_value
            
            if config_key in cycle_config:
                value = cycle_config[config_key]
                logger.debug(f"📋 Using cycle-specific config for {config_key}: {value}")
                return value
            else:
                logger.debug(f"📋 Config key {config_key} not found in cycle config, using default: {default_value}")
                return default_value
                
        except Exception as e:
            logger.error(f"❌ Error getting cycle config value for {config_key}: {str(e)}")
            return default_value

    def has_cycle_config(self):
        """Check if cycle has specific configuration"""
        try:
            if not hasattr(self, 'cycle_config') or not self.cycle_config:
                return False
            
            # Parse JSON if it's a string
            cycle_config = self.cycle_config
            if isinstance(cycle_config, str):
                try:
                    cycle_config = json.loads(cycle_config)
                except json.JSONDecodeError:
                    return False
            
            return len(cycle_config) > 0
            
        except Exception as e:
            logger.error(f"❌ Error checking cycle config: {str(e)}")
            return False

    def get_cycle_config_summary(self):
        """Get a summary of cycle-specific configuration"""
        try:
            if not self.has_cycle_config():
                return "No cycle-specific configuration"
            
            # Parse JSON if it's a string
            cycle_config = self.cycle_config
            if isinstance(cycle_config, str):
                try:
                    cycle_config = json.loads(cycle_config)
                except json.JSONDecodeError:
                    return "Invalid cycle configuration"
            
            # Get key configuration values
            summary = {
                'config_saved_at': cycle_config.get('config_saved_at', 'Unknown'),
                'config_version': cycle_config.get('config_version', 'Unknown'),
                'lot_size': cycle_config.get('lot_size', 'Default'),
                'grid_interval_pips': cycle_config.get('grid_interval_pips', 'Default'),
                'zone_threshold_pips': cycle_config.get('zone_threshold_pips', 'Default'),
                'max_trades_per_cycle': cycle_config.get('max_trades_per_cycle', 'Default'),
                'zone_movement_mode': cycle_config.get('zone_movement_mode', 'Default')
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error getting cycle config summary: {str(e)}")
            return "Error retrieving configuration summary"
