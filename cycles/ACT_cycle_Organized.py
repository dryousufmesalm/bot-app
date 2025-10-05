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

    def __init__(self, cycle_data=None, meta_trader=None, bot=None):
        """Initialize Advanced Cycle with enhanced features"""
        self.bot = bot
        self.meta_trader = meta_trader
        
        # Initialize all fields with defaults
        self._initialize_defaults()
        
        # If cycle data provided, initialize from it
        if cycle_data:
            self._initialize_cycle_data(cycle_data)
            
        logger.info(f"AdvancedCycle initialized with ID: {getattr(self, 'cycle_id', 'NEW')}")
        
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
            self.initial_order_open_datetime = cycle_data.get('initial_order_open_datetime')
            
            # Ensure direction_switches is a list
            direction_switches_data = cycle_data.get('direction_switches')
            if isinstance(direction_switches_data, (int, float)):
                # Convert old integer format to list format
                self.direction_switches = []
            else:
                # Parse as JSON if it's a string, otherwise use empty list
                self.direction_switches = self._parse_json_field(direction_switches_data, [])

            # Basic cycle info
            self.cycle_id = cycle_data.get('id')
            self.account_id = cycle_data.get('account')
            self.bot_id = cycle_data.get('bot')
            self.is_closed = bool(cycle_data.get('is_closed', False))
            self.is_favorite = bool(cycle_data.get('is_favorite', False))
            self.symbol = cycle_data.get('symbol')
            self.price_level = float(cycle_data.get('price_level', 0.0))  # Added price level restoration
            
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
            
            # Reversal trading
            self.reversal_threshold_pips = float(cycle_data.get('reversal_threshold_pips', 0.0))
            self.highest_buy_price = float(cycle_data.get('highest_buy_price', 0.0))
            self.lowest_sell_price = float(cycle_data.get('lowest_sell_price', float('inf')))
            self.reversal_count = int(cycle_data.get('reversal_count', 0))
            self.closed_orders_pl = float(cycle_data.get('closed_orders_pl', 0.0))
            self.open_orders_pl = float(cycle_data.get('open_orders_pl', 0.0))
            self.total_cycle_pl = float(cycle_data.get('total_cycle_pl', 0.0))
            self.last_reversal_time = cycle_data.get('last_reversal_time')
            self.reversal_history = self._parse_json_field(cycle_data.get('reversal_history'), [])
            
            # Recovery mode
            self.in_recovery_mode = bool(cycle_data.get('in_recovery_mode', False))
            self.recovery_activated = bool(cycle_data.get('recovery_activated', False))
            self.reversal_threshold_from_recovery = bool(cycle_data.get('reversal_threshold_from_recovery', False))
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
            self.cycle_type = cycle_data.get('cycle_type', 'ACT')
            self.magic_number = int(cycle_data.get('magic_number', 0))
            
            logger.info(f"Successfully initialized cycle {self.cycle_id} from database record")
            
        except Exception as e:
            logger.error(f"Error initializing cycle data: {e}")
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
        self.cycle_type = 'ACT'
        self.magic_number = 0
        
        # Price levels
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.lot_size = 0.0
        self.price_level = 0.0  # Added price level field
        
        # Direction and zone settings
        self.direction = 'BUY'
        self.current_direction = 'BUY'
        self.direction_switches = []  # Track direction switches
        self.direction_switched = False
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
        
        # Reversal trading
        self.reversal_threshold_pips = 0.0
        self.highest_buy_price = 0.0
        self.lowest_sell_price = float('inf')
        self.reversal_count = 0
        self.closed_orders_pl = 0.0
        self.open_orders_pl = 0.0
        self.total_cycle_pl = 0.0
        self.last_reversal_time = None
        self.reversal_history = []
        
        # Recovery mode
        self.in_recovery_mode = False
        self.recovery_zone_base_price = 0.0
        self.initial_stop_loss_price = 0.0
        self.initial_order_stop_loss = 0.0
        self.recovery_activated = False
        self.reversal_threshold_from_recovery = False
        self.recovery_direction = None
        self.initial_direction = None
        self.initial_order_open_price = 0.0
        self.placed_levels = []
        self.initial_order_data = {}
        
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
        self.entry_price = cycle_data.get("entry_price", 0.0)

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
        self.direction_switches = []
        
        # Zone state
        self.zone_activated = cycle_data.get("zone_activated", False)
        self.initial_threshold_breached = cycle_data.get("initial_threshold_breached", False)
        self.zone_based_losses = cycle_data.get("zone_based_losses", 0.0)
        self.batch_stop_loss_triggers = cycle_data.get("batch_stop_loss_triggers", 0)

    def _initialize_reversal_properties(self, cycle_data):
        """Initialize reversal trading properties"""
        self.reversal_threshold_pips = cycle_data.get("reversal_threshold_pips", 50.0)
        self.highest_buy_price = cycle_data.get("highest_buy_price", 0.0)
        self.lowest_buy_price = cycle_data.get("lowest_buy_price", float('inf'))
        self.highest_sell_price = cycle_data.get("highest_sell_price", 0.0)
        self.lowest_sell_price = cycle_data.get("lowest_sell_price", float('inf'))
        self.reversal_count = cycle_data.get("reversal_count", 0)
        self.closed_orders_pl = cycle_data.get("closed_orders_pl", 0.0)
        self.open_orders_pl = cycle_data.get("open_orders_pl", 0.0)
        self.total_cycle_pl = cycle_data.get("total_cycle_pl", 0.0)
        self.last_reversal_time = cycle_data.get("last_reversal_time", None)
        
        # Ensure reversal_history is always initialized as a list
        reversal_history = cycle_data.get("reversal_history")
        self.reversal_history = reversal_history if isinstance(reversal_history, list) else []
        
        self.initial_order_stop_loss = cycle_data.get("initial_order_stop_loss", 300.0)
        self.cycle_interval = cycle_data.get("cycle_interval", 100.0)
        
        # Recovery mode properties
        self.in_recovery_mode = cycle_data.get("in_recovery_mode", False)
        self.recovery_zone_base_price = cycle_data.get("recovery_zone_base_price", None)
        self.initial_stop_loss_price = cycle_data.get("initial_stop_loss_price", None)
        self.recovery_activated = cycle_data.get("recovery_activated", False)
        self.recovery_direction = cycle_data.get("recovery_direction", None)
        self.initial_direction = cycle_data.get("initial_direction", self.current_direction)
        self.initial_order_open_price = cycle_data.get("initial_order_open_price", 0.0)
        self.initial_order_data = cycle_data.get("initial_order_data", {})
        self.placed_levels = set(cycle_data.get("placed_levels", []))
        self.reversal_threshold_from_recovery = cycle_data.get("reversal_threshold_from_recovery", False)

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
            
            # # Update cycle in PocketBase database
            # self._update_cycle_in_database()
            
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
            'comment': ['comment', 'description'],
            'open_time': ['open_time', 'placed_at', 'open_datetime'],
            'placed_at': ['placed_at', 'open_time', 'placed_datetime']
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
        # CRITICAL FIX: Only set open_time if it doesn't exist, preserve original timestamp
        if 'open_time' not in order_data:
            order_data['open_time'] = datetime.datetime.now().isoformat()
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
        """Safely convert a value to float"""
        try:
            if value is None:
                return default
            return float(value)
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
                # Handle case where order might be an integer (ticket number) instead of dict
                if isinstance(order, int):
                    logger.warning(f"Found integer ticket {order} in active_orders, skipping profit calculation")
                    continue
                elif not isinstance(order, dict):
                    logger.warning(f"Found non-dict order {type(order)} in active_orders, skipping profit calculation")
                    continue
                
                profit = float(order.get('profit', 0.0))
                swap = float(order.get('swap', 0.0))
                commission = float(order.get('commission', 0.0))
                
                active_profit += profit
                total_swap += swap
                total_commission += commission
                
                logger.debug(f"Active order {order.get('ticket')}: Profit={profit}, Swap={swap}, Commission={commission}")
            
            # Calculate profit from completed orders
            for order in self.completed_orders:
                # Handle case where order might be an integer (ticket number) instead of dict
                if isinstance(order, int):
                    logger.warning(f"Found integer ticket {order} in completed_orders, skipping profit calculation")
                    continue
                elif not isinstance(order, dict):
                    logger.warning(f"Found non-dict order {type(order)} in completed_orders, skipping profit calculation")
                    continue
                
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
            
        
            
        except Exception as e:
            logger.error(f"Error updating cycle statistics after order add: {e}")

    def update_orders_with_live_data(self):
        """Update orders with live data from MT5 and recalculate profits"""
        try:
            # Clean up order lists first to handle any integer tickets
            self.cleanup_order_lists()
            
            # Get current positions from MT5
            positions = self._get_mt5_positions()
            
            if not positions:
                return
            
            # Create lookup dictionary for faster access
            positions_dict = self._create_positions_lookup(positions)
            
             # Check for and recover mistakenly completed orders
            recovered_count = self._recover_mistakenly_completed_orders(positions_dict)
            
            # Update orders with live data
            updated_count = self._update_orders_from_positions(positions_dict)
            
            # Recalculate total profit after updating orders and recovering orders
            self._recalculate_total_profit()
            
            # Update database with latest profit information if orders were updated or recovered
            if updated_count > 0 or recovered_count > 0:
                self._update_cycle_in_database()
            
            # Validate order consistency after all updates
            self.validate_order_consistency()
            
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
                # Handle case where order might be an integer (ticket number) instead of dict
                if isinstance(order, int):
                    logger.warning(f"Found integer ticket {order} in active_orders, skipping update")
                    continue
                elif not isinstance(order, dict):
                    logger.warning(f"Found non-dict order {type(order)} in active_orders, skipping update")
                    continue
                
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

    def _recover_mistakenly_completed_orders(self, positions_dict) -> int:
        """Check completed orders and move back to active if they still exist in MT5"""
        try:
            recovered_count = 0
            
            # Check each completed order to see if it still exists in MT5 positions
            for order in self.completed_orders[:]:  # Use slice copy to avoid modification during iteration
                try:
                    ticket = int(order.get('ticket', '0'))
                    
                    # Check if this order exists in MT5 positions
                    if ticket in positions_dict:
                        logger.info(f"Order {ticket} found in MT5 positions but was in completed orders. Moving back to active orders")
                        
                        # Remove from completed orders
                        self.completed_orders.remove(order)
                        
                        # Ensure order format consistency with active orders
                        self._ensure_order_format_consistency(order)
                        
                        # Reset order status to active
                        order['status'] = 'active'
                        order['is_closed'] = False
                        
                        # Remove close_time if it exists
                        if 'close_time' in order:
                            del order['close_time']
                        
                        # Add back to active orders
                        self.active_orders.append(order)
                        
                        recovered_count += 1
                        logger.info(f"Successfully recovered order {ticket} to active orders")
                        
                except ValueError as ve:
                    logger.error(f"Invalid ticket format for completed order: {order.get('ticket', 'unknown')}")
                except Exception as e:
                    logger.error(f"Error processing completed order {order.get('ticket', 'unknown')}: {e}")
            
            if recovered_count > 0:
                logger.info(f"Recovered {recovered_count} orders from completed to active orders")
                logger.info(f"Active orders: {len(self.active_orders)}, Completed orders: {len(self.completed_orders)}")
            
            return recovered_count
            
        except Exception as e:
            logger.error(f"Error recovering mistakenly completed orders: {e}")
            return 0

    def _ensure_order_format_consistency(self, order):
        """Ensure order format matches the expected structure for active orders"""
        try:
            # Ensure all required fields are present
            required_fields = ['ticket', 'symbol', 'type', 'volume', 'price', 'status']
            for field in required_fields:
                if field not in order:
                    logger.warning(f"Missing required field '{field}' in order {order.get('ticket', 'unknown')}")
                    # Set default values for missing fields
                    if field == 'ticket':
                        order[field] = '0'
                    elif field == 'symbol':
                        order[field] = self.symbol
                    elif field == 'type':
                        order[field] = 'buy'  # Default to buy
                    elif field == 'volume':
                        order[field] = 0.01
                    elif field == 'price':
                        order[field] = 0.0
                    elif field == 'status':
                        order[field] = 'active'
            
            # Ensure numeric fields are properly typed
            numeric_fields = ['volume', 'price', 'profit', 'swap', 'commission']
            for field in numeric_fields:
                if field in order:
                    try:
                        order[field] = float(order[field])
                    except (ValueError, TypeError):
                        order[field] = 0.0
            
            # Ensure ticket is string format
            if 'ticket' in order:
                order['ticket'] = str(order['ticket'])
                
        except Exception as e:
            logger.error(f"Error ensuring order format consistency: {e}")

    # ==================== CYCLE STATUS MANAGEMENT ====================

    def update_cycle_status(self):
        """Update cycle status based on orders and conditions"""
        try:
            logger.info(f"Updating status for cycle {self.cycle_id}")
            
            # Update order statuses first
            self._update_order_statuses()
            logger.info(f"Updated order statuses for cycle {self.cycle_id}")
            
            # Only check for closing if explicitly marked
            if self._should_close_cycle():
                logger.info(f"Cycle {self.cycle_id} explicitly marked for closing")
                self.close_cycle("manual_close")
            else:
                # Recalculate total profit
                self._recalculate_total_profit()
                logger.info(f"Cycle {self.cycle_id} remains active. Active orders: {len(self.active_orders)}, Completed orders: {len(self.completed_orders)}, Total profit: {self.total_profit}")
            
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
        """Check if an order is closed with enhanced validation"""
        try:
            # Handle case where order might be an integer (ticket number) instead of dict
            if isinstance(order, int):
                logger.warning(f"Found integer ticket {order} in order check, treating as closed")
                return True
            elif not isinstance(order, dict):
                logger.warning(f"Found non-dict order {type(order)} in order check, treating as closed")
                return True
            
            ticket = order.get('ticket')
            if not ticket:
                return False
            
            # Check if position still exists in MT5 with retry logic
            positions = self._get_mt5_positions()
            position_tickets = [str(getattr(pos, 'ticket', '')) for pos in positions]
            
            # If the order is not in MT5 positions and not already marked as closed
            if str(ticket) not in position_tickets and not order.get('is_closed', False):
                # Double-check with a second position check to avoid false positives
                logger.info(f"Order {ticket} not found in MT5 positions, performing double-check")
                
                # Wait a moment and check again to avoid race conditions
                import time
                time.sleep(0.1)  # Small delay to allow for position updates
                
                # Second position check
                positions_retry = self._get_mt5_positions()
                position_tickets_retry = [str(getattr(pos, 'ticket', '')) for pos in positions_retry]
                
                if str(ticket) not in position_tickets_retry:
                    logger.info(f"Order {ticket} confirmed not found in MT5 positions after double-check")
                    return True
                else:
                    logger.info(f"Order {ticket} found in MT5 positions on retry - keeping as active")
                    return False
            
            return False
            
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
            # Check if cycle is marked for closing
            marked_for_closing = getattr(self, 'force_close', False)
            
            # Only close if explicitly marked for closing
            # Do not auto-close just because active_orders is empty
            if marked_for_closing:
                logger.info(f"Cycle {self.cycle_id} marked for closing")
                return True
                
            logger.debug(f"Cycle {self.cycle_id} not marked for closing, keeping active")
            return False
            
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
            # Update highest sell price from active sell orders
            self._update_highest_sell_price_from_orders()
            # Update lowest sell price from active sell orders
            self._update_lowest_sell_price_from_orders()
            # Update lowest buy price from active buy orders
            self._update_lowest_buy_price_from_orders()
                    
        except Exception as e:
            logger.error(f"Error updating price extremes: {e}")

    def _update_highest_sell_price_from_orders(self):
        """Update highest_sell_price to be the open price of the highest active sell order"""
        try:
            sell_orders = [
                order for order in self.active_orders 
                if order.get('direction', '').upper() == 'SELL' or order.get('type', 0) == 1
            ]
            if sell_orders:
                # Find the order with the highest open price
                highest_order = max(sell_orders, key=lambda order: order.get('open_price', 0.0))
                self.highest_sell_price = highest_order.get('open_price', 0.0)
            else:
                self.highest_sell_price = 0.0

        except Exception as e:
            logger.error(f"Error updating highest sell price from orders: {e}")
            self.highest_sell_price = 0.0

    def _update_lowest_buy_price_from_orders(self):
        """Update lowest_buy_price to be the open price of the lowest active buy order"""
        try:
            buy_orders = [
                order for order in self.active_orders 
                if order.get('direction', '').upper() == 'BUY' or order.get('type', 0) == 0
            ]
            if buy_orders:
                # Find the order with the lowest open price
                lowest_order = min(buy_orders, key=lambda order: order.get('open_price', float('inf')))
                self.lowest_buy_price = self._safe_float_conversion(lowest_order.get('open_price', 999999999.0))
            else:
                # Use large finite number instead of infinity
                self.lowest_buy_price = 999999999.0
        except Exception as e:
            logger.error(f"Error updating lowest buy price from orders: {e}")
            self.lowest_buy_price = 999999999.0

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
            
            # # Update cycle in PocketBase database
            # self._update_cycle_in_database()
            
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
        """Switch cycle direction and record the change"""
        try:
            # Ensure direction_switches is a list
            if not isinstance(self.direction_switches, list):
                self.direction_switches = []
                
            # Record the direction switch
            switch_data = {
                'from_direction': self.current_direction,
                'to_direction': new_direction,
                'reason': reason,
                'timestamp': datetime.datetime.now().isoformat(),
                'price': self.last_order_price
            }
            self.direction_switches.append(switch_data)
            
            # Update direction
            self.direction = new_direction
            self.current_direction = new_direction
            self.direction_switched = True
            
            logger.info(f"Switched direction from {switch_data['from_direction']} to {switch_data['to_direction']} - Reason: {reason}")
            
        except Exception as e:
            logger.error(f"Error switching direction: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Ensure direction_switches is a list even after error
            if not isinstance(self.direction_switches, list):
                self.direction_switches = []
            
        # Update database
        self._update_cycle_in_database()

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

    def _serialize_data(self, data):
        """Serialize data for database storage"""
        try:
            if data is None:
                return None
            if isinstance(data, (list, tuple)):
                return [self._serialize_data(item) for item in data]
            if isinstance(data, dict):
                return {k: self._serialize_data(v) for k, v in data.items()}
            if isinstance(data, (datetime.datetime, datetime.date)):
                return self._safe_datetime_string(data)
            if isinstance(data, (int, float, str, bool)):
                return data
            # Try to convert to dict if object has __dict__
            if hasattr(data, '__dict__'):
                return self._serialize_data(data.__dict__)
            return str(data)
        except Exception as e:
            logger.error(f"Error serializing data: {e}")
            return None
            
    def _update_cycle_in_database(self):
        """Update cycle in database"""
        try:
            if not self.cycle_id:
                logger.error("❌ Cannot update cycle in database: No cycle_id available")
                return False
                
            if not (hasattr(self.bot, 'client') and self.bot.client):
                logger.error("No API client available for database operations")
                return False
                
            api_client = self.bot.client
            
            # Ensure profits are up to date before saving
            self._recalculate_total_profit()
            
            # Ensure direction_switches is a list before serializing
            if not isinstance(self.direction_switches, list):
                self.direction_switches = []
            
            # Prepare data for database update
            data = {
                'id': self.cycle_id,
                'bot': str(self.bot_id),
                'account': str(self.account_id),
                'symbol': self.symbol,
                'is_closed': self.is_closed,
                'is_favorite': getattr(self, 'is_favorite', False),
                'status': getattr(self, 'status', 'closed' if self.is_closed else 'active'),
                'magic_number': getattr(self.bot, 'magic_number', 0),
                'entry_price': self._safe_float_conversion(getattr(self, 'entry_price', 0.0)),
                'price_level': self._safe_float_conversion(getattr(self, 'price_level', 0.0)),  # Added price level
                'stop_loss': self._safe_float_conversion(getattr(self, 'stop_loss', 0.0)),
                'take_profit': self._safe_float_conversion(getattr(self, 'take_profit', 0.0)),
                'lot_size': self._safe_float_conversion(getattr(self, 'lot_size', self.bot.configs['lot_size'])),
                'direction': self.current_direction,
                'current_direction': self.current_direction,
                'direction_switched': getattr(self, 'direction_switched', False),
                'direction_switches': self._serialize_data(self.direction_switches),  # Now always a list
                'zone_base_price': self._safe_float_conversion(getattr(self, 'zone_base_price', 0.0)),
                'initial_threshold_price': self._safe_float_conversion(getattr(self, 'initial_threshold_price', 0.0)),
                'zone_threshold_pips': self._safe_float_conversion(getattr(self, 'zone_threshold_pips', self.bot.configs['reversal_threshold_pips'])),
                'order_interval_pips': self._safe_float_conversion(getattr(self, 'order_interval_pips', self.bot.configs['order_interval_pips'])),
                'batch_stop_loss_pips': self._safe_float_conversion(getattr(self, 'initial_order_stop_loss', self.bot.configs['initial_order_stop_loss_pips'])),
                'zone_range_pips': self._safe_float_conversion(getattr(self, 'cycle_interval', self.bot.configs['cycle_interval_pips'])),
                'lot_idx': int(getattr(self, 'lot_idx', 0)),
                'lower_bound': self._safe_float_conversion(getattr(self, 'lower_bound', 0.0)),
                'upper_bound': self._safe_float_conversion(getattr(self, 'upper_bound', 0.0)),
                'next_order_index': int(getattr(self, 'next_order_index', 1)),
                'current_batch_id': str(getattr(self, 'current_batch_id', '')),
                'total_volume': self._safe_float_conversion(getattr(self, 'total_volume', 0.0)),
                'total_profit': self._safe_float_conversion(getattr(self, 'total_profit', 0.0)),
                'accumulated_loss': self._safe_float_conversion(getattr(self, 'accumulated_loss', 0.0)),
                'batch_losses': self._safe_float_conversion(getattr(self, 'batch_losses', 0.0)),
                'total_orders': len(getattr(self, 'active_orders', [])) + len(getattr(self, 'completed_orders', [])),
                'profitable_orders': int(getattr(self, 'profitable_orders', 0)),
                'loss_orders': int(getattr(self, 'loss_orders', 0)),
                'duration_minutes': int(getattr(self, 'duration_minutes', 0)),
                'reversal_threshold_pips': self._safe_float_conversion(getattr(self, 'reversal_threshold_pips', 300.0)),
                'highest_buy_price': self._safe_float_conversion(getattr(self, 'highest_buy_price', 0.0)),
                'lowest_sell_price': self._safe_float_conversion(getattr(self, 'lowest_sell_price', 999999999.0)),
                'reversal_count': int(getattr(self, 'reversal_count', 0)),
                'closed_orders_pl': self._safe_float_conversion(getattr(self, 'closed_orders_pl', 0.0)),
                'open_orders_pl': self._safe_float_conversion(getattr(self, 'open_orders_pl', 0.0)),
                'total_cycle_pl': self._safe_float_conversion(getattr(self, 'total_cycle_pl', 0.0)),
                'in_recovery_mode': getattr(self, 'in_recovery_mode', False),
                'recovery_zone_base_price': self._safe_float_conversion(getattr(self, 'recovery_zone_base_price', 0.0)),
                'initial_stop_loss_price': self._safe_float_conversion(getattr(self, 'initial_stop_loss_price', 0.0)),
                'recovery_activated': getattr(self, 'recovery_activated', False),
                'recovery_direction': getattr(self, 'recovery_direction', None),
                'placed_levels': self._serialize_data(getattr(self, 'placed_levels', [])),
                'initial_order_open_price': self._safe_float_conversion(getattr(self, 'initial_order_open_price', 0.0)),
                'initial_direction': getattr(self, 'initial_direction', None),
                'initial_order_data': self._serialize_data(getattr(self, 'initial_order_data', {})),
                'reversal_threshold_from_recovery': getattr(self, 'reversal_threshold_from_recovery', False),
                'last_reversal_time': self._safe_datetime_string(getattr(self, 'last_reversal_time', None)),
                'last_order_time': self._safe_datetime_string(getattr(self, 'last_order_time', None)),
                'close_time': self._safe_datetime_string(getattr(self, 'close_time', None)),
                'close_reason': getattr(self, 'close_reason', ''),
                'closing_method': self._serialize_data(getattr(self, 'closing_method', {})),
                'opened_by': self._serialize_data(getattr(self, 'opened_by', {})),
                'cycle_type': getattr(self, 'cycle_type', 'ACT'),
                'last_order_price': self._safe_float_conversion(getattr(self, 'last_order_price', 0.0)),
                'orders': self._serialize_data(getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', [])),
                'active_orders': self._serialize_data(getattr(self, 'active_orders', [])),
                'completed_orders': self._serialize_data(getattr(self, 'completed_orders', [])),
                'orders_config': self._serialize_data(getattr(self, 'orders_config', {})),
                'done_price_levels': self._serialize_data(getattr(self, 'done_price_levels', [])),
                'reversal_history': self._serialize_data(getattr(self, 'reversal_history', []))
            }
            
            # Update the record in PocketBase
            api_client.update_ACT_cycle_by_id(data['id'], data)
            
            logger.info(f"✅ Successfully updated cycle {data['id']} in database")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating cycle {data['id']} in database: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
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
                "direction": str(self.direction) if hasattr(self, 'direction') else "BUY",
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
                "initial_order_open_datetime": getattr(self, 'initial_order_open_datetime', None)
               
             
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
                return symbol_info.point * 10
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
            self.direction_switches = []
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

    def validate_order_consistency(self):
        """Validate order consistency and report any issues"""
        try:
            issues = []
            
            # Check for duplicate tickets in active orders
            active_tickets = [order.get('ticket') for order in self.active_orders]
            duplicate_active = [ticket for ticket in set(active_tickets) if active_tickets.count(ticket) > 1]
            if duplicate_active:
                issues.append(f"Duplicate tickets in active orders: {duplicate_active}")
            
            # Check for duplicate tickets in completed orders
            completed_tickets = [order.get('ticket') for order in self.completed_orders]
            duplicate_completed = [ticket for ticket in set(completed_tickets) if completed_tickets.count(ticket) > 1]
            if duplicate_completed:
                issues.append(f"Duplicate tickets in completed orders: {duplicate_completed}")
            
            # Check for orders that exist in both active and completed
            active_set = set(active_tickets)
            completed_set = set(completed_tickets)
            common_tickets = active_set.intersection(completed_set)
            if common_tickets:
                issues.append(f"Orders exist in both active and completed: {common_tickets}")
            
            # Check for orders with invalid status
            for order in self.active_orders:
                if order.get('status') != 'active':
                    issues.append(f"Active order {order.get('ticket')} has invalid status: {order.get('status')}")
            
            for order in self.completed_orders:
                if order.get('status') != 'closed':
                    issues.append(f"Completed order {order.get('ticket')} has invalid status: {order.get('status')}")
            
            if issues:
                logger.warning(f"Order consistency issues found in cycle {self.cycle_id}:")
                for issue in issues:
                    logger.warning(f"  - {issue}")
                return False
            else:
                logger.info(f"Order consistency validation passed for cycle {self.cycle_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error validating order consistency: {e}")
            return False

    def force_recovery_of_completed_orders(self):
        """Force recovery of all completed orders that might be mistakenly moved"""
        try:
            logger.info(f"Starting forced recovery of completed orders for cycle {self.cycle_id}")
            
            # Get current MT5 positions
            positions = self._get_mt5_positions()
            if not positions:
                logger.warning("No MT5 positions available for recovery check")
                return 0
            
            # Create positions lookup
            positions_dict = self._create_positions_lookup(positions)
            
            # Attempt to recover all completed orders
            recovered_count = self._recover_mistakenly_completed_orders(positions_dict)
            
            if recovered_count > 0:
                logger.info(f"Force recovery completed: {recovered_count} orders recovered")
                # Recalculate profits after recovery
                self._recalculate_total_profit()
                # Update database
                self._update_cycle_in_database()
            else:
                logger.info("No orders recovered during force recovery")
            
            return recovered_count
            
        except Exception as e:
            logger.error(f"Error during force recovery of completed orders: {e}")
            return 0

    def cleanup_order_lists(self):
        """Clean up order lists by converting integer tickets to proper order dictionaries"""
        try:
            logger.info(f"Cleaning up order lists for cycle {self.cycle_id}")
            
            # Clean up active orders
            cleaned_active = []
            for item in self.active_orders:
                if isinstance(item, int):
                    # Convert integer ticket to order dictionary
                    order_dict = self._create_order_data_from_ticket(str(item))
                    cleaned_active.append(order_dict)
                    logger.info(f"Converted integer ticket {item} to order dictionary")
                elif isinstance(item, dict):
                    cleaned_active.append(item)
                else:
                    logger.warning(f"Removing invalid order item of type {type(item)}: {item}")
            
            # Clean up completed orders
            cleaned_completed = []
            for item in self.completed_orders:
                if isinstance(item, int):
                    # Convert integer ticket to order dictionary
                    order_dict = self._create_order_data_from_ticket(str(item))
                    order_dict['status'] = 'closed'
                    order_dict['is_closed'] = True
                    cleaned_completed.append(order_dict)
                    logger.info(f"Converted integer ticket {item} to completed order dictionary")
                elif isinstance(item, dict):
                    cleaned_completed.append(item)
                else:
                    logger.warning(f"Removing invalid order item of type {type(item)}: {item}")
            
            # Update the lists
            self.active_orders = cleaned_active
            self.completed_orders = cleaned_completed
            
            logger.info(f"Order lists cleaned up. Active orders: {len(self.active_orders)}, Completed orders: {len(self.completed_orders)}")
            
        except Exception as e:
            logger.error(f"Error cleaning up order lists: {e}")

    def _update_cycle_in_database_sync(self):
        """Update cycle in database synchronously"""
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
            
            # Prepare data for database update
            data = {
                'id': self.cycle_id,
                'bot': str(self.bot.id),
                'account': str(self.bot.account.id),
                'symbol': self.symbol,
                'is_closed': self.is_closed,
                'is_favorite': getattr(self, 'is_favorite', False),
                'status': getattr(self, 'status', 'closed' if self.is_closed else 'active'),
                'magic_number': getattr(self.bot, 'magic_number', 0),
                'entry_price': self._safe_float_value(getattr(self, 'entry_price', 0.0)),
                'stop_loss': self._safe_float_value(getattr(self, 'stop_loss', 0.0)),
                'take_profit': self._safe_float_value(getattr(self, 'take_profit', 0.0)),
                'lot_size': self._safe_float_value(getattr(self, 'lot_size', self.bot.lot_size)),
                'direction': self.current_direction,
                'current_direction': self.current_direction,
                'direction_switched': getattr(self, 'direction_switched', False),
                'zone_base_price': self._safe_float_value(getattr(self, 'zone_base_price', 0.0)),
                'initial_threshold_price': self._safe_float_value(getattr(self, 'initial_threshold_price', 0.0)),
                'zone_threshold_pips': self._safe_float_value(getattr(self, 'zone_threshold_pips', self.bot.reversal_threshold_pips)),
                'order_interval_pips': self._safe_float_value(getattr(self, 'order_interval_pips', self.bot.order_interval_pips)),
                'batch_stop_loss_pips': self._safe_float_value(getattr(self, 'initial_order_stop_loss', self.bot.initial_order_stop_loss)),
                'zone_range_pips': self._safe_float_value(getattr(self, 'cycle_interval', self.bot.cycle_interval)),
                'lot_idx': int(getattr(self, 'lot_idx', 0)),
                'lower_bound': self._safe_float_value(getattr(self, 'lower_bound', 0.0)),
                'upper_bound': self._safe_float_value(getattr(self, 'upper_bound', 0.0)),
                'next_order_index': int(getattr(self, 'next_order_index', 1)),
                'current_batch_id': str(getattr(self, 'current_batch_id', '')),
                'total_volume': self._safe_float_value(getattr(self, 'total_volume', 0.0)),
                'total_profit': self._safe_float_value(getattr(self, 'total_profit', 0.0)),
                'accumulated_loss': self._safe_float_value(getattr(self, 'accumulated_loss', 0.0)),
                'batch_losses': self._safe_float_value(getattr(self, 'batch_losses', 0.0)),
                'total_orders': len(getattr(self, 'active_orders', [])) + len(getattr(self, 'completed_orders', [])),
                'profitable_orders': int(getattr(self, 'profitable_orders', 0)),
                'loss_orders': int(getattr(self, 'loss_orders', 0)),
                'duration_minutes': int(getattr(self, 'duration_minutes', 0)),
                'reversal_threshold_pips': self._safe_float_value(getattr(self, 'reversal_threshold_pips', 300.0)),
                'highest_buy_price': self._safe_float_value(getattr(self, 'highest_buy_price', 0.0)),
                'lowest_sell_price': self._safe_float_value(getattr(self, 'lowest_sell_price', 999999999.0)),
                'reversal_count': int(getattr(self, 'reversal_count', 0)),
                'closed_orders_pl': self._safe_float_value(getattr(self, 'closed_orders_pl', 0.0)),
                'open_orders_pl': self._safe_float_value(getattr(self, 'open_orders_pl', 0.0)),
                'total_cycle_pl': self._safe_float_value(getattr(self, 'total_cycle_pl', 0.0)),
                'in_recovery_mode': getattr(self, 'in_recovery_mode', False),
                'recovery_zone_base_price': self._safe_float_value(getattr(self, 'recovery_zone_base_price', 0.0)),
                'initial_stop_loss_price': self._safe_float_value(getattr(self, 'initial_stop_loss_price', 0.0)),
                'recovery_activated': getattr(self, 'recovery_activated', False),
                'recovery_direction': getattr(self, 'recovery_direction', None),
                'placed_levels': self._make_json_serializable(getattr(self, 'placed_levels', [])),
                'initial_order_open_price': self._safe_float_value(getattr(self, 'initial_order_open_price', 0.0)),
                'initial_direction': getattr(self, 'initial_direction', None),
                'initial_order_data': self._make_json_serializable(getattr(self, 'initial_order_data', {})),
                'reversal_threshold_from_recovery': getattr(self, 'reversal_threshold_from_recovery', False),
                'last_reversal_time': self._safe_datetime_string(getattr(self, 'last_reversal_time', None)),
                'last_order_time': self._safe_datetime_string(getattr(self, 'last_order_time', None)),
                'close_time': self._safe_datetime_string(getattr(self, 'close_time', None)),
                'close_reason': getattr(self, 'close_reason', ''),
                'closing_method': self._make_json_serializable(getattr(self, 'closing_method', {})),
                'opened_by': self._make_json_serializable(getattr(self, 'opened_by', {})),
                'cycle_type': getattr(self, 'cycle_type', 'ACT'),
                'last_order_price': self._safe_float_value(getattr(self, 'last_order_price', 0.0)),
                'orders': self._make_json_serializable(getattr(self, 'active_orders', []) + getattr(self, 'completed_orders', [])),
                'active_orders': self._make_json_serializable(getattr(self, 'active_orders', [])),
                'completed_orders': self._make_json_serializable(getattr(self, 'completed_orders', [])),
                'orders_config': self._make_json_serializable(getattr(self, 'orders_config', {})),
                'done_price_levels': self._make_json_serializable(getattr(self, 'done_price_levels', [])),
                'reversal_history': self._make_json_serializable(getattr(self, 'reversal_history', []))
            }
            
            # Apply recursive JSON serialization to handle any nested datetime objects
            data = self._make_json_serializable(data)
            
            # Update the record in PocketBase
            api_client.collection('cycles').update(self.cycle_id, data)
            
            logger.info(f"✅ Successfully updated cycle {self.cycle_id} in database")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating cycle {self.cycle_id} in database: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _safe_float_value(self, value, default=0.0):
        """Safely convert a value to float"""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
            
    def _safe_int_value(self, value, default=0):
        """Safely convert a value to int"""
        try:
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError):
            return default
            
    def _safe_datetime_string(self, dt_value):
        """Convert datetime to string safely"""
        if dt_value is None:
            return None
        try:
            if isinstance(dt_value, str):
                return dt_value
            if isinstance(dt_value, (datetime.datetime, datetime.date)):
                return dt_value.isoformat()
            return str(dt_value)
        except Exception as e:
            logger.error(f"Error converting datetime to string: {e}")
            return None
        

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

