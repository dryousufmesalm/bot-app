"""
Advanced Cycles Trader Strategy - Organized Version

This is a clean, organized version of the AdvancedCyclesTrader with:
- Unused code removed
- Functions renamed for better readability
- Logical grouping of related functionality
- Improved documentation
"""

from Strategy.strategy import Strategy
import threading
from Orders.order import order
from cycles.ACT_cycle_Organized import AdvancedCycle
from DB.db_engine import engine
from Strategy.components import AdvancedOrderManager, DirectionController
from Strategy.components.multi_cycle_manager import MultiCycleManager
from Strategy.components.enhanced_zone_detection import EnhancedZoneDetection
from Strategy.components.enhanced_order_manager import EnhancedOrderManager
from Strategy.components.reversal_detector import ReversalDetector
import asyncio
import datetime
import time
from Views.globals.app_logger import app_logger as logger
from typing import Dict, List, Optional, Any
import json
import traceback


class AdvancedCyclesTrader(Strategy):
    """
    Advanced Cycles Trader Strategy with Multi-Cycle Zone-Based Reversal Logic
    
    Features:
    - Multi-cycle management
    - Zone-based order placement
    - Reversal detection and handling
    - Enhanced order management
    - Real-time synchronization with database
    """

    def __init__(self, meta_trader, config, client, symbol, bot):
        """Initialize the Advanced Cycles Trader strategy"""
        self._validate_initialization_parameters(meta_trader, config, client, symbol, bot)
        self._initialize_core_components(meta_trader, config, client, symbol, bot)
        self._initialize_strategy_configuration(config)
        self._initialize_advanced_components()
        self._initialize_trading_state()
        
    

    # ==================== INITIALIZATION METHODS ====================

    def _validate_initialization_parameters(self, meta_trader, config, client, symbol, bot):
        """Validate initialization parameters"""
        if bot is None:
            logger.error("🚨 CRITICAL: Bot parameter is None during AdvancedCyclesTrader initialization!")
            raise ValueError("Bot parameter cannot be None")
        
        if not meta_trader:
            raise ValueError("MetaTrader instance cannot be None")
        
        if not config:
            raise ValueError("Configuration cannot be None")
        
        if not client:
            raise ValueError("API client cannot be None")
        
        if not symbol:
            raise ValueError("Symbol cannot be None or empty")

    def _initialize_core_components(self, meta_trader, config, client, symbol, bot):
        """Initialize core components"""
        self.meta_trader = meta_trader
        self.config = config
        self.client = client
        self.symbol = symbol
        self.bot = bot
        
        # Initialize in-memory loss tracking
        self.loss_tracker = self._initialize_loss_tracker()
        
        # Set magic number on MetaTrader instance
        if hasattr(self.bot, 'magic_number') and self.bot.magic_number:
            self.meta_trader.magic_number = self.bot.magic_number
            logger.info(f"✅ Magic number {self.bot.magic_number} set on MetaTrader instance")
        else:
            logger.warning("⚠️ Bot has no magic number - MetaTrader will use default")
        
        # Ensure bot has access to API client
        if not hasattr(self.bot, 'api_client') or not self.bot.api_client:
            self.bot.api_client = client
            logger.info("API client assigned to bot for database operations")

    def _initialize_strategy_configuration(self, config):
        """Initialize strategy configuration parameters"""
        self.order_interval_pips = float(config.get("order_interval_pips", 50.0))
        self.lot_size = float(config.get("lot_size", 0.01))
        self.take_profit_pips = float(config.get("take_profit_pips", 100.0))
        self.stop_loss_pips = float(config.get("stop_loss_pips", 50.0))
        self.max_active_cycles = int(config.get("max_concurrent_cycles", 3))
        self.reversal_threshold_pips = float(config.get("reversal_threshold_pips", 300.0))
        self.cycle_interval = float(config.get("cycle_interval_pips", 100.0))
        self.initial_order_stop_loss = float(config.get("initial_order_stop_loss_pips", 300.0))
        self.zone_range_pips = int(config.get("zone_range_pips", 50))
        
    def _initialize_advanced_components(self):
        """Initialize advanced trading components"""
        # Multi-cycle management
        self.multi_cycle_manager = MultiCycleManager(
            self.meta_trader, self.bot, self.config, self.client
        )
        
        # Enhanced zone detection
        self.zone_engine = EnhancedZoneDetection(
            self.symbol, self.reversal_threshold_pips, self.order_interval_pips
        )
        
        # Enhanced order management
        self.order_manager = EnhancedOrderManager(
            self.meta_trader, self.symbol, self.bot.magic_number
        )
        
        # Direction controller
        self.direction_controller = DirectionController(self.symbol)
        
        # Reversal detector
        self.reversal_detector = ReversalDetector(self.reversal_threshold_pips)
        
        # Initialize direction controller with default direction
        self.direction_controller.execute_direction_switch("BUY", "strategy_initialization")
        logger.info("Direction controller initialized with default BUY direction")

    def _initialize_trading_state(self):
        """Initialize trading state variables"""
        # Cycle management
        self.cycles = {}
        self.active_cycles = []
        self.closed_cycles = []
        
        # Strategy state
        self.strategy_active = False
        self.trading_active = False
        self.monitoring_thread = None
        
        # Market data
        self.current_market_price = None
        self.last_candle_time = None
        
        # Zone state
        self.initial_threshold_breached = False
        self.zone_activated = False
        
        # Recovery zone tracking (NEW)
        self.recovery_cycles = {}  # Track cycles in recovery mode
        self.recovery_price_levels = {}  # Track placed order levels per cycle
        
        # Loss tracking is already initialized in _initialize_core_components()
        # Don't override it here
        
        # Event tracking
        self.processed_events = set()
        self.last_cycle_creation_time = 0
        self.last_cycle_price = 0
        # In-memory statistics
        self.total_cycles_created = 0
        self.total_profitable_cycles = 0
        self.total_loss_making_cycles = 0

    def initialize(self):
        """Initialize the strategy (required by Strategy base class)"""
        try:
            # Set initial entry price
            self.set_entry_price(self.meta_trader.get_bid(self.symbol))
            
            # Sync cycles with PocketBase
            self._sync_cycles_with_pocketbase()
            logger.info("AdvancedCyclesTrader initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing AdvancedCyclesTrader: {e}")
            return False

    def _sync_cycles_with_pocketbase(self):
        """Sync cycles with PocketBase database"""
        try:
            if not hasattr(self.bot, 'api_client') or not self.bot.api_client:
                logger.error("No API client available for database operations")
                return False
                
            # Get all active cycles

            cycles_response = self.bot.api_client.get_all_ACT_active_cycles_by_bot_id(self.bot.id)
            
            if not cycles_response:
                logger.warning("No cycles found in PocketBase")
                return
                
            existing_cycle_ids = set()
            synced_count = 0
            self.active_cycles = []
            self.cycles = {}
            # Process each cycle from PocketBase
            for pb_cycle in cycles_response:  # Remove .items since cycles_response is already a list
                try:
                    # Convert PocketBase cycle to local format
                    cycle_data = self._convert_pb_cycle_to_local_format(pb_cycle)
                    
                    # Create new cycle instance
                    cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
                    
                    # Verify the cycle was created properly
                    if hasattr(cycle, 'cycle_id') and cycle.cycle_id:
                        # Add to active cycles
                        self.active_cycles.append(cycle)
                        self.cycles[cycle.cycle_id] = cycle
                        existing_cycle_ids.add(cycle.cycle_id)
                        
                        logger.info(f"Synced cycle {cycle.cycle_id} from PocketBase")
                        logger.debug(f"Cycle {cycle.cycle_id} has {len(cycle.active_orders)} active orders after creation")
                        synced_count += 1
                        
                        # Check if cycle is in recovery mode
                        if cycle.in_recovery_mode:
                            logger.info(f"Cycle {cycle.cycle_id} is in recovery mode")
                            
                            # Get current price for setup
                            market_data = self._get_market_data()
                            if not market_data:
                                logger.error(f"Could not get market data for recovery setup of cycle {cycle.cycle_id}")
                                continue
                                
                            current_price = market_data.get('current_price', 0.0)
                            
                            # Find initial order
                            initial_order = None
                            all_orders = cycle.active_orders + cycle.completed_orders
                            for order in all_orders:
                                if order.get('kind', 'initial') == 'initial':
                                    initial_order = order
                                    break
                            
                            if initial_order:
                                # Restore recovery data
                                self.recovery_cycles[cycle.cycle_id] = {
                                    'cycle': cycle,
                                    'initial_direction': getattr(cycle, 'initial_direction', cycle.current_direction),
                                    'initial_order_open_price': getattr(cycle, 'initial_order_open_price', float(initial_order.get('open_price', 0.0))),
                                    'initial_stop_loss_price': getattr(cycle, 'initial_stop_loss_price', current_price),
                                    'recovery_zone_base_price': getattr(cycle, 'recovery_zone_base_price', current_price),
                                    'recovery_activated': getattr(cycle, 'recovery_activated', False),
                                    'recovery_direction': getattr(cycle, 'recovery_direction', cycle.current_direction),
                                    'placed_levels': getattr(cycle, 'placed_levels', []),
                                    'initial_order_data': getattr(cycle, 'initial_order_data', {}),
                                    'reversal_threshold_from_recovery': getattr(cycle, 'reversal_threshold_from_recovery', False)
                                }
                                logger.info(f"✅ Restored recovery data for cycle {cycle.cycle_id}")
                            else:
                                logger.warning(f"❌ Could not find initial order for recovery cycle {cycle.cycle_id}")
                                
                except Exception as cycle_error:
                    logger.error(f"Error syncing cycle from PocketBase: {cycle_error}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    continue
                    
            logger.info(f"Successfully synced {synced_count} cycles from PocketBase")
            
            # Remove any cycles that no longer exist in PocketBase
            cycles_to_remove = []
            for cycle_id in self.cycles:
                if cycle_id not in existing_cycle_ids:
                    cycles_to_remove.append(cycle_id)
                    
            for cycle_id in cycles_to_remove:
                self.cycles.pop(cycle_id, None)
                self.active_cycles = [c for c in self.active_cycles if c.cycle_id != cycle_id]
                logger.info(f"Removed cycle {cycle_id} as it no longer exists in PocketBase")
                
        except Exception as e:
            logger.error(f"Error syncing cycles with PocketBase: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
            
        return True

    def _convert_pb_cycle_to_local_format(self, pb_cycle) -> dict:
        """Convert PocketBase cycle data to local format"""
        try:
            # Debug logging to see what fields are available
            logger.debug(f"Converting PocketBase cycle with available fields: {dir(pb_cycle)}")
            
            # Extract orders data (could be stored as JSON strings)
            active_orders = []
            completed_orders = []
            
            # Try to get active orders
            try:
                active_orders_data = getattr(pb_cycle, 'active_orders', '[]')
                if isinstance(active_orders_data, str):
                    import json
                    active_orders = json.loads(active_orders_data) if active_orders_data else []
                elif isinstance(active_orders_data, list):
                    active_orders = active_orders_data
                else:
                    active_orders = []
            except Exception as e:
                logger.warning(f"Could not extract active_orders from PocketBase cycle: {e}")
                active_orders = []
            
            # Try to get completed orders
            try:
                completed_orders_data = getattr(pb_cycle, 'completed_orders', '[]')
                if isinstance(completed_orders_data, str):
                    import json
                    completed_orders = json.loads(completed_orders_data) if completed_orders_data else []
                elif isinstance(completed_orders_data, list):
                    completed_orders = completed_orders_data
                else:
                    completed_orders = []
            except Exception as e:
                logger.warning(f"Could not extract completed_orders from PocketBase cycle: {e}")
                completed_orders = []
            
            # Try to get all orders (fallback)
            try:
                all_orders_data = getattr(pb_cycle, 'orders', '[]')
                if isinstance(all_orders_data, str) and all_orders_data:
                    import json
                    all_orders = json.loads(all_orders_data)
                    # If we don't have separate active/completed, use all orders as active
                    if not active_orders and not completed_orders and all_orders:
                        active_orders = all_orders
            except Exception as e:
                logger.warning(f"Could not extract orders from PocketBase cycle: {e}")

            # Parse placed_levels and initial_order_data with safe defaults
            placed_levels = []
            try:
                placed_levels_data = getattr(pb_cycle, 'placed_levels', '[]')
                if isinstance(placed_levels_data, str):
                    import json
                    placed_levels = json.loads(placed_levels_data) if placed_levels_data else []
                elif isinstance(placed_levels_data, list):
                    placed_levels = placed_levels_data
            except Exception as e:
                logger.error(f"Error parsing JSON field placed_levels: {e}")

            initial_order_data = {}
            try:
                initial_order_data_raw = getattr(pb_cycle, 'initial_order_data', '{}')
                if isinstance(initial_order_data_raw, str):
                    import json
                    initial_order_data = json.loads(initial_order_data_raw) if initial_order_data_raw else {}
                elif isinstance(initial_order_data_raw, dict):
                    initial_order_data = initial_order_data_raw
            except Exception as e:
                logger.error(f"Error parsing JSON field initial_order_data: {e}")
            
            return {
                # Core identification - match PocketBase schema exactly
                'id': getattr(pb_cycle, 'id', '') or getattr(pb_cycle, 'cycle_id', ''),
                'cycle_id': getattr(pb_cycle, 'id', '') or getattr(pb_cycle, 'cycle_id', ''),
                'bot': getattr(pb_cycle, 'bot', ''),
                'account': getattr(pb_cycle, 'account', ''),
                'symbol': getattr(pb_cycle, 'symbol', self.symbol),
                
                # Status and control fields
                'is_closed': bool(getattr(pb_cycle, 'is_closed', False)),
                'is_favorite': bool(getattr(pb_cycle, 'is_favorite', False)),
                'status': getattr(pb_cycle, 'status', 'active'),
                
                # Trading configuration fields
                'magic_number': getattr(pb_cycle, 'magic_number', self.bot.magic_number),
                'entry_price': self._safe_float_value(getattr(pb_cycle, 'entry_price', 0.0)),
                'stop_loss': self._safe_float_value(getattr(pb_cycle, 'stop_loss', 0.0)),
                'take_profit': self._safe_float_value(getattr(pb_cycle, 'take_profit', 0.0)),
                'lot_size': self._safe_float_value(getattr(pb_cycle, 'lot_size', self.lot_size)),
                
                # Direction fields
                'direction': getattr(pb_cycle, 'direction', 'BUY'),
                'current_direction': getattr(pb_cycle, 'current_direction', getattr(pb_cycle, 'direction', 'BUY')),
                'direction_switched': bool(getattr(pb_cycle, 'direction_switched', False)),
                
                # Zone and threshold fields
                'zone_base_price': self._safe_float_value(getattr(pb_cycle, 'zone_base_price', 0.0)),
                'initial_threshold_price': self._safe_float_value(getattr(pb_cycle, 'initial_threshold_price', 0.0)),
                'zone_threshold_pips': self._safe_float_value(getattr(pb_cycle, 'zone_threshold_pips', self.reversal_threshold_pips)),
                'order_interval_pips': self._safe_float_value(getattr(pb_cycle, 'order_interval_pips', self.order_interval_pips)),
                'batch_stop_loss_pips': self._safe_float_value(getattr(pb_cycle, 'batch_stop_loss_pips', self.initial_order_stop_loss)),
                'zone_range_pips': self._safe_float_value(getattr(pb_cycle, 'zone_range_pips', self.cycle_interval)),
                
                # Cycle tracking fields
                'lot_idx': int(getattr(pb_cycle, 'lot_idx', 0)),
                'lower_bound': self._safe_float_value(getattr(pb_cycle, 'lower_bound', 0.0)),
                'upper_bound': self._safe_float_value(getattr(pb_cycle, 'upper_bound', 0.0)),
                'next_order_index': int(getattr(pb_cycle, 'next_order_index', 1)),
                'current_batch_id': str(getattr(pb_cycle, 'current_batch_id', '')),
                'last_order_price': self._safe_float_value(getattr(pb_cycle, 'last_order_price', 0.0)),
                'last_order_time': getattr(pb_cycle, 'last_order_time', None),
                
                # Volume and profit tracking
                'total_volume': self._safe_float_value(getattr(pb_cycle, 'total_volume', 0.0)),
                'total_profit': self._safe_float_value(getattr(pb_cycle, 'total_profit', 0.0)),
                'accumulated_loss': self._safe_float_value(getattr(pb_cycle, 'accumulated_loss', 0.0)),
                'batch_losses': self._safe_float_value(getattr(pb_cycle, 'batch_losses', 0.0)),
                
                # Order statistics
                'total_orders': int(getattr(pb_cycle, 'total_orders', len(active_orders) + len(completed_orders))),
                'profitable_orders': int(getattr(pb_cycle, 'profitable_orders', 0)),
                'loss_orders': int(getattr(pb_cycle, 'loss_orders', 0)),
                'duration_minutes': int(getattr(pb_cycle, 'duration_minutes', 0)),
                
                # Reversal trading fields
                'reversal_threshold_pips': self._safe_float_value(getattr(pb_cycle, 'reversal_threshold_pips', 300.0)),
                'highest_buy_price': self._safe_float_value(getattr(pb_cycle, 'highest_buy_price', 0.0)),
                'lowest_sell_price': self._safe_float_value(getattr(pb_cycle, 'lowest_sell_price', 999999999.0)),
                'reversal_count': int(getattr(pb_cycle, 'reversal_count', 0)),
                'closed_orders_pl': self._safe_float_value(getattr(pb_cycle, 'closed_orders_pl', 0.0)),
                'open_orders_pl': self._safe_float_value(getattr(pb_cycle, 'open_orders_pl', 0.0)),
                'total_cycle_pl': self._safe_float_value(getattr(pb_cycle, 'total_cycle_pl', 0.0)),
                'last_reversal_time': getattr(pb_cycle, 'last_reversal_time', None),
                
                # Recovery mode fields
                'in_recovery_mode': bool(getattr(pb_cycle, 'in_recovery_mode', False)),
                'recovery_zone_base_price': self._safe_float_value(getattr(pb_cycle, 'recovery_zone_base_price', 0.0)),
                'initial_stop_loss_price': self._safe_float_value(getattr(pb_cycle, 'initial_stop_loss_price', 0.0)),
                'recovery_activated': bool(getattr(pb_cycle, 'recovery_activated', False)),
                'recovery_direction': getattr(pb_cycle, 'recovery_direction', None),
                'initial_order_open_price': self._safe_float_value(getattr(pb_cycle, 'initial_order_open_price', 0.0)),
                'initial_direction': getattr(pb_cycle, 'initial_direction', None),
                'reversal_threshold_from_recovery': bool(getattr(pb_cycle, 'reversal_threshold_from_recovery', False)),
                
                # Parsed JSON fields with safe defaults
                'placed_levels': placed_levels,
                'initial_order_data': initial_order_data,
                'price_level': self._safe_float_value(getattr(pb_cycle, 'price_level', 0.0)),
                # Orders data
                'active_orders': active_orders,
                'completed_orders': completed_orders,
                'reversal_history': getattr(pb_cycle, 'reversal_history', []),
                
                # Cycle type
                'cycle_type': getattr(pb_cycle, 'cycle_type', 'ACT'),
                
                # Base cycle fields (required by CT_cycle base class)
                'initial': getattr(pb_cycle, 'initial', []),
                'hedge': getattr(pb_cycle, 'hedge', []),
                'recovery': getattr(pb_cycle, 'recovery', []),
                'pending': getattr(pb_cycle, 'pending', []),
                'closed': getattr(pb_cycle, 'closed', []),
                'threshold': getattr(pb_cycle, 'threshold', []),
                'zone_index': int(getattr(pb_cycle, 'zone_index', 0)),
                'threshold_upper': self._safe_float_value(getattr(pb_cycle, 'threshold_upper', 0.0)),
                'threshold_lower': self._safe_float_value(getattr(pb_cycle, 'threshold_lower', 0.0)),
                'base_threshold_lower': self._safe_float_value(getattr(pb_cycle, 'base_threshold_lower', 0.0)),
                'base_threshold_upper': self._safe_float_value(getattr(pb_cycle, 'base_threshold_upper', 0.0)),
                'opened_by': getattr(pb_cycle, 'opened_by', {}),
                'is_pending': bool(getattr(pb_cycle, 'is_pending', False)),
                
                # Status
                'is_active': bool(getattr(pb_cycle, 'is_active', True)),
                'active_orders_count': len(active_orders),
                'completed_orders_count': len(completed_orders),
                'zone_based_losses': self._safe_float_value(getattr(pb_cycle, 'zone_based_losses', 0.0)),
                'batch_stop_loss_triggers': int(getattr(pb_cycle, 'batch_stop_loss_triggers', 0)),
                
                # Zone and trading state
                'zone_activated': bool(getattr(pb_cycle, 'zone_activated', False)),
                'initial_threshold_breached': bool(getattr(pb_cycle, 'initial_threshold_breached', False)),
                'direction_switches': int(getattr(pb_cycle, 'direction_switches', 0)),
                'take_profit_pips': self._safe_float_value(getattr(pb_cycle, 'take_profit_pips', 100.0)),
                'stop_loss_pips': self._safe_float_value(getattr(pb_cycle, 'stop_loss_pips', 50.0)),
                
                # Backwards compatibility fields
                'initial_order_stop_loss': self._safe_float_value(getattr(pb_cycle, 'batch_stop_loss_pips', self.initial_order_stop_loss)),
                'cycle_interval': self._safe_float_value(getattr(pb_cycle, 'zone_range_pips', self.cycle_interval)),
                
                # Timestamps
                'created': getattr(pb_cycle, 'created', datetime.datetime.now().isoformat()),
                'updated': getattr(pb_cycle, 'updated', datetime.datetime.now().isoformat()),
                
                # Metadata
                'username': getattr(pb_cycle, 'username', 'system'),
                'user_id': getattr(pb_cycle, 'user_id', 'system'),
                'sent_by_admin': bool(getattr(pb_cycle, 'sent_by_admin', False)),
                'creation_method': getattr(pb_cycle, 'creation_method', 'manual'),
                'closing_method': getattr(pb_cycle, 'closing_method', ''),
                'closed_by': getattr(pb_cycle, 'closed_by', ''),
                'strategy_version': getattr(pb_cycle, 'strategy_version', '1.0.0'),
            }
            return cycle_data
        except Exception as e:
            logger.error(f"Error converting PocketBase cycle to local format: {e}")
            logger.error(f"PocketBase cycle data: {pb_cycle}")
            return {}

    def _safe_float_value(self, value):
        """Convert float values safely, handling infinity and NaN"""
        if value is None:
            return 0.0
        
        try:
            float_val = float(value)
            # Check for infinity or NaN
            if float_val == float('inf'):
                return 999999999.0  # Large number instead of infinity
            elif float_val == float('-inf'):
                return -999999999.0  # Large negative number instead of negative infinity
            elif float_val != float_val:  # NaN check
                return 0.0
            else:
                return float_val
        except (ValueError, TypeError):
            return 0.0

    async def _update_orders_status_to_inactive(self, cycle):
        """Update all orders in cycle to inactive status"""
        try:
            for order in cycle.active_orders:
                order['status'] = 'inactive'
                order['is_active'] = False
            
            for order in cycle.completed_orders:
                order['status'] = 'inactive' 
                order['is_active'] = False
            
            logger.debug(f"Updated orders status to inactive for cycle {cycle.cycle_id}")
            
        except Exception as e:
            logger.error(f"Error updating orders status to inactive: {e}")

    async def _update_cycle_in_database(self, cycle):
        """Update cycle in database with proper JSON serialization"""
        try:
            # Prepare cycle data for database update
            cycle_data = self._prepare_cycle_data_for_database(cycle)
            
            if not cycle_data:
                logger.error(f"Failed to prepare cycle data for database update - cycle {cycle.cycle_id}")
                return
            
            # Log the data being sent for debugging
            logger.debug(f"Updating cycle {cycle.cycle_id} with data keys: {list(cycle_data.keys())}")
            
            # Update in PocketBase
            if hasattr(self.client, 'update_ACT_cycle_by_id'):
                try:
                    result = self.client.update_ACT_cycle_by_id(cycle.cycle_id, cycle_data)
                    if result:
                        logger.debug(f"✅ Cycle {cycle.cycle_id} updated in database successfully")
                    else:
                        logger.error(f"❌ Failed to update cycle {cycle.cycle_id} in database - client returned falsy result")
                except Exception as client_error:
                    logger.error(f"❌ Client error updating cycle {cycle.cycle_id}: {client_error}")
                    # Log problematic data for debugging
                    logger.error(f"Cycle data that caused error: {cycle_data}")
                    raise
            else:
                logger.warning("Client does not have update_ACT_cycle_by_id method")
                
        except Exception as e:
            logger.error(f"❌ Error updating cycle {cycle.cycle_id} in database: {e}")
            # Log additional context for debugging
            if hasattr(cycle, 'cycle_id'):
                logger.error(f"Cycle ID: {cycle.cycle_id}")
            if hasattr(cycle, 'symbol'):
                logger.error(f"Symbol: {cycle.symbol}")
            if hasattr(cycle, 'is_closed'):
                logger.error(f"Is Closed: {cycle.is_closed}")
            raise

    def _prepare_cycle_data_for_database(self, cycle):
        """Prepare cycle data for database update"""
        try:
            data = {
                'id': cycle.cycle_id,
                'bot': str(self.bot.id),
                'account': str(self.bot.account.id),
                'symbol': cycle.symbol,
                'is_closed': cycle.is_closed,
                'is_favorite': cycle.is_favorite,
                'opened_by': self._serialize_data(cycle.opened_by),
                'closing_method': self._serialize_data(cycle.closing_method),
                'lot_idx': self._safe_int_value(cycle.lot_idx),
                'status': cycle.status,
                'lower_bound': self._safe_float_value(cycle.lower_bound),
                'upper_bound': self._safe_float_value(cycle.upper_bound),
                'total_volume': self._safe_float_value(cycle.total_volume),
                'total_profit': self._safe_float_value(cycle.total_profit),
                'orders': self._serialize_data(cycle.orders),
                'orders_config': self._serialize_data(cycle.orders_config),
                'cycle_type': cycle.cycle_type,
                'magic_number': self._safe_int_value(cycle.magic_number),
                'entry_price': self._safe_float_value(cycle.entry_price),
                'stop_loss': self._safe_float_value(cycle.stop_loss),
                'take_profit': self._safe_float_value(cycle.take_profit),
                'lot_size': self._safe_float_value(cycle.lot_size),
                'direction': cycle.direction,
                'current_direction': cycle.current_direction,
                'zone_base_price': self._safe_float_value(cycle.zone_base_price),
                'initial_threshold_price': self._safe_float_value(cycle.initial_threshold_price),
                'zone_threshold_pips': self._safe_float_value(cycle.zone_threshold_pips),
                'order_interval_pips': self._safe_float_value(cycle.order_interval_pips),
                'batch_stop_loss_pips': self._safe_float_value(cycle.batch_stop_loss_pips),
                'zone_range_pips': self._safe_float_value(cycle.zone_range_pips),
                'direction_switched': cycle.direction_switched,
                'direction_switches': self._serialize_data(cycle.direction_switches),
                'next_order_index': self._safe_int_value(cycle.next_order_index),
                'done_price_levels': self._serialize_data(cycle.done_price_levels),
                'active_orders': self._serialize_data(cycle.active_orders),
                'completed_orders': self._serialize_data(cycle.completed_orders),
                'current_batch_id': cycle.current_batch_id,
                'last_order_price': self._safe_float_value(cycle.last_order_price),
                'last_order_time': self._safe_datetime_string(cycle.last_order_time),
                'accumulated_loss': self._safe_float_value(cycle.accumulated_loss),
                'batch_losses': self._safe_float_value(cycle.batch_losses),
                'close_reason': cycle.close_reason,
                'close_time': self._safe_datetime_string(cycle.close_time),
                'total_orders': self._safe_int_value(cycle.total_orders),
                'profitable_orders': self._safe_int_value(cycle.profitable_orders),
                'loss_orders': self._safe_int_value(cycle.loss_orders),
                'duration_minutes': self._safe_int_value(cycle.duration_minutes),
                'reversal_threshold_pips': self._safe_float_value(cycle.reversal_threshold_pips),
                'highest_buy_price': self._safe_float_value(cycle.highest_buy_price),
                'lowest_sell_price': self._safe_float_value(cycle.lowest_sell_price),
                'reversal_count': self._safe_int_value(cycle.reversal_count),
                'closed_orders_pl': self._safe_float_value(cycle.closed_orders_pl),
                'open_orders_pl': self._safe_float_value(cycle.open_orders_pl),
                'total_cycle_pl': self._safe_float_value(cycle.total_cycle_pl),
                'last_reversal_time': self._safe_datetime_string(cycle.last_reversal_time),
                'reversal_history': self._serialize_data(cycle.reversal_history),
                
                # Recovery mode fields
                'in_recovery_mode': cycle.in_recovery_mode,
                'recovery_zone_base_price': self._safe_float_value(cycle.recovery_zone_base_price),
                'initial_stop_loss_price': self._safe_float_value(cycle.initial_stop_loss_price),
                'initial_order_stop_loss': self._safe_float_value(cycle.initial_order_stop_loss),
                'recovery_activated': cycle.recovery_activated,
                'reversal_threshold_from_recovery': cycle.reversal_threshold_from_recovery,
                'recovery_direction': cycle.recovery_direction,
                'initial_direction': cycle.initial_direction,
                'initial_order_open_price': self._safe_float_value(cycle.initial_order_open_price),
                'placed_levels': self._serialize_data(cycle.placed_levels),
                'initial_order_data': self._serialize_data(cycle.initial_order_data)
            }
            return data
        except Exception as e:
            logger.error(f"Error preparing cycle data for database: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _safe_datetime_string(self, dt_value):
        """Convert datetime to ISO format string safely"""
        try:
            if dt_value is None:
                return None
            if isinstance(dt_value, str):
                return dt_value
            return dt_value.isoformat()
        except (ValueError, AttributeError):
            return None

    def _serialize_data(self, data):
        """Serialize data to JSON string"""
        try:
            if data is None:
                return None
            if isinstance(data, str):
                return data
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            logger.error(f"Error serializing data: {e}")
            return None

    def _initialize_loss_tracker(self):
        """Initialize in-memory loss tracker"""
        return {
            'bot_id': str(self.bot.id),
            'account_id': str(self.meta_trader.account_id),
            'symbol': self.symbol,
            'total_accumulated_losses': 0.0,
            'active_cycles_count': 0,
            'closed_cycles_count': 0,
            'profitable_cycles': 0,
            'loss_making_cycles': 0,
            'direction_switch_count': 0,
            'batch_stop_loss_triggers': 0,
            'created_at': datetime.datetime.now(),
            'updated_at': datetime.datetime.now()
        }

    # ==================== EVENT HANDLING ====================

    async def handle_event(self, event):
        """Handle trading events (required by Strategy base class)"""
        try:
            if not self._is_event_valid(event):
                return True
            
            event_id = getattr(event, 'id', str(hash(str(event))))
            if event_id in self.processed_events:
                logger.info(f"Event {event_id} already processed, skipping")
                return True
            
            self.processed_events.add(event_id)
            
            # Extract event message and content
            message, content = self._extract_event_data(event)
            
            # Route to appropriate handler
            return await self._route_event_to_handler(message, content)
            
        except Exception as e:
            logger.error(f"Error handling event in AdvancedCyclesTrader: {e}")
            return False

    def _is_event_valid(self, event) -> bool:
        """Check if event is valid for processing"""
        return event is not None

    def _extract_event_data(self, event) -> tuple:
        """Extract message and content from event"""
        if hasattr(event, 'action'):
            message = event.action
            content = event.content
        else:
            content = event.content if hasattr(event, 'content') else {}
            message = content.get("message", "unknown")
        
        return message, content

    async def _route_event_to_handler(self, message: str, content: dict) -> bool:
        """Route event to appropriate handler based on message type"""
        event_handlers = {
            "open_order": self._handle_open_order_event,
            "close_cycle": self._handle_close_cycle_event,
            "close_order": self._handle_close_order_event,
            "stop_bot": lambda _: self.stop_strategy(),
            "start_bot": lambda _: self.start_strategy(),
        }
        
        handler = event_handlers.get(message)
        if handler:
            if asyncio.iscoroutinefunction(handler):
                return await handler(content)
            else:
                return handler(content)
        else:
            logger.info(f"Unhandled event message: {message}")
            return True

    # ==================== ORDER MANAGEMENT ====================

    async def _handle_open_order_event(self, content: dict) -> bool:
        """Handle open order event"""
        try:
            order_params = self._extract_order_parameters(content)
            current_prices = self._get_current_market_prices()
            
            if not current_prices:
                logger.error("Failed to get market prices")
                return False
            
            return await self._place_order_by_type(order_params, current_prices)
            
        except Exception as e:
            logger.error(f"Error handling open order event: {e}")
            return False

    def _extract_order_parameters(self, content: dict) -> dict:
        """Extract order parameters from event content"""
        return {
            'username': content.get("user_name", "system"),
            'sent_by_admin': content.get("sent_by_admin", False),
            'user_id': content.get("user_id", "system"),
            'cycle_type': content.get('type', 0),
            'price': content.get('price', 0),
            'create_cycle_in_database': content.get('create_cycle_in_database', True)
        }

    def _get_current_market_prices(self) -> Optional[dict]:
        """Get current market prices"""
        current_bid = self.meta_trader.get_bid(self.symbol)
        current_ask = self.meta_trader.get_ask(self.symbol)
        
        if current_bid is None or current_ask is None:
            return None
        
        return {'bid': current_bid, 'ask': current_ask}

    async def _place_order_by_type(self, order_params: dict, current_prices: dict) -> bool:
        """Place order based on cycle type"""
        cycle_type = order_params['cycle_type']
        
        if cycle_type == 0:  # BUY
            return await self._place_buy_order(order_params, current_prices['ask'])
        elif cycle_type == 1:  # SELL
            return await self._place_sell_order(order_params, current_prices['bid'])
        elif cycle_type == 2:  # BUY&SELL (dual orders)
            return await self._place_dual_orders(order_params, current_prices)
        else:
            logger.warning(f"Unknown cycle type: {cycle_type}")
            return False

    async def _place_buy_order(self, order_params: dict, current_ask: float) -> bool:
        """Place a buy order"""
        try:
            # Create order in meta trader with all required parameters
            order_data = self.meta_trader.buy(
                symbol=self.symbol,
                volume=self.lot_size,
                magic=self.bot.magic_number,
                sl=0.0,
                tp=0.0,
                sltp_type="PIPS",
                slippage=20,
                comment=f"ACT_BUY_{self.bot.id}"
            )
            
            # Check if order was successful
            if not order_data or len(order_data) == 0:
                logger.error("Buy order failed - no order data returned")
                return False
                
            # Create order data structure for cycle creation
            processed_order_data = {
                'price': current_ask,
                'ticket': str(order_data[0].ticket),
                'volume': self.lot_size,
                'symbol': self.symbol,
                'type': 0,  # BUY = 0
                'magic_number': self.bot.magic_number,
                'comment': f"ACT_BUY_{self.bot.id}",
                'sl': 0.0,
                'tp': 0.0
            }
            
            return await self._create_manual_cycle(
                processed_order_data, "BUY", order_params['username'], 
                order_params['sent_by_admin'], order_params['user_id']
            )
        except Exception as e:
            logger.error(f"Error placing buy order: {e}")
            return False

    async def _place_sell_order(self, order_params: dict, current_bid: float) -> bool:
        """Place a sell order"""
        try:
            # Create order in meta trader with all required parameters
            order_data = self.meta_trader.sell(
                symbol=self.symbol,
                volume=self.lot_size,
                magic=self.bot.magic_number,
                sl=0.0,
                tp=0.0,
                sltp_type="PIPS",
                slippage=20,
                comment=f"ACT_SELL_{self.bot.id}"
            )
            
            # Check if order was successful
            if not order_data or len(order_data) == 0:
                logger.error("Sell order failed - no order data returned")
                return False
                
            # Create order data structure for cycle creation
            processed_order_data = {
                'price': current_bid,
                'ticket': str(order_data[0].ticket),
                'volume': self.lot_size,
                'symbol': self.symbol,
                'type': 1,  # SELL = 1
                'magic_number': self.bot.magic_number,
                'comment': f"ACT_SELL_{self.bot.id}",
                'sl': 0.0,
                'tp': 0.0
            }
            
            return await self._create_manual_cycle(
                processed_order_data, "SELL", order_params['username'], 
                order_params['sent_by_admin'], order_params['user_id']
            )
        except Exception as e:
            logger.error(f"Error placing sell order: {e}")
            return False

    async def _place_dual_orders(self, order_params: dict, current_prices: dict) -> bool:
        """Place dual orders (both BUY and SELL)"""
        try:
            # Place buy order
            buy_success = await self._place_buy_order(order_params, current_prices['ask'])
            
            # Place sell order
            sell_success = await self._place_sell_order(order_params, current_prices['bid'])
            
            return buy_success and sell_success
        except Exception as e:
            logger.error(f"Error placing dual orders: {e}")
            return False

    def _create_order_data(self, direction: str, price: float, current_price: float) -> dict:
        """Create order data structure"""
        #
        return {
            'direction': direction,
            'price': price,
            'current_price': current_price,
            'lot_size': self.lot_size,
            'symbol': self.symbol,
            'timestamp': datetime.datetime.now()
        }

    def _create_manual_cycle(self, order_data: dict, direction: str, 
                                 username: str, sent_by_admin: bool, user_id: str) -> bool:
        """Create a manual cycle with the given order"""
        try:
            # Create cycle data
            cycle_data = self._build_cycle_data(order_data, username, user_id, direction)
            
            # Create cycle instance
            cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
            
            # Add the order to the cycle before creating in database
            # Create Flutter-compatible order structure
            order_for_cycle = {
                'ticket': int(order_data.get('ticket', 0)),
                'type': order_data.get('type', 0),  # 0 = BUY, 1 = SELL
                'kind': 'initial',  # orderKind - required by Flutter
                'direction': direction,
                'open_price': float(order_data.get('price', 0.0)),
                'volume': float(order_data.get('volume', 0.0)),
                'symbol': str(order_data.get('symbol', '')),
                'status': 'active',
                'profit': 0.0,
                'swap': 0.0,
                'commission': 0.0,
                'magic_number': int(order_data.get('magic_number', 0)),
                'comment': str(order_data.get('comment', '')),
                'sl': float(order_data.get('sl', 0.0)),
                'tp': float(order_data.get('tp', 0.0)),
                'trailing_steps': 0,
                'margin': 0.0,
                'is_pending': False,
                'is_closed': False,
                'open_time': datetime.datetime.now().isoformat(),
                'cycle_id': None,
                'cycle_create': None
            }
            
            # Add order to cycle
            cycle.add_order(order_for_cycle)
            
            # Add cycle to active cycles
            self.active_cycles.append(cycle)
            self.cycles[cycle.cycle_id] = cycle
            
            # Update in-memory statistics
            self.total_cycles_created += 1
            self.loss_tracker['active_cycles_count'] += 1
            self.loss_tracker['updated_at'] = datetime.datetime.now()
            
            # Create cycle in PocketBase database (now with the order included)
            cycle._create_cycle_in_database()
            
            logger.info(f"Manual cycle created: {cycle.cycle_id} ({direction}) with order {order_data.get('ticket')}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating manual cycle: {e}")
            return False

    def _build_cycle_data(self, order_data, username, user_id, direction):
        """Build initial cycle data"""
        return {
            # Basic cycle info
            'symbol': self.symbol,
            'bot': str(self.bot.id),
            'account': str(self.bot.account.id),
            'is_closed': False,
            'is_favorite': False,
            'opened_by': {
                'username': username,
                'user_id': user_id
            },
            'closing_method': {},
            'lot_idx': 0,
            'status': 'ACTIVE',
            
            # Price bounds and levels
            'lower_bound': 0.0,
            'upper_bound': 0.0,
            'entry_price': order_data['price'],
            'price_level': order_data.get('price_level'),  # Store the level
            'stop_loss': 0.0,
            'take_profit': 0.0,
            'lot_size': self.lot_size,
            
            # Volume and profit tracking
            'total_volume': 0.0,
            'total_profit': 0.0,
            
            # Orders and configuration
            'orders': [],
            'orders_config': {},
            'cycle_type': 'ACT',
            'magic_number': self.bot.magic_number,
            
            # Direction and zone settings
            'direction': direction,
            'current_direction': direction,
            'direction_switches': [],
            'direction_switched': False,
            'zone_base_price': order_data['price'],
            'initial_threshold_price': 0.0,
            'zone_threshold_pips': self.reversal_threshold_pips,
            'order_interval_pips': self.order_interval_pips,
            'batch_stop_loss_pips': self.initial_order_stop_loss,
            'zone_range_pips': self.cycle_interval,
            
            # Order tracking
            'next_order_index': 1,
            'done_price_levels': [],
            'active_orders': [],
            'completed_orders': [],
            'current_batch_id': None,
            'last_order_price': order_data['price'],
            'last_order_time': datetime.datetime.now().isoformat(),
            
            # Loss tracking
            'accumulated_loss': 0.0,
            'batch_losses': 0.0,
            
            # Order statistics
            'total_orders': 0,
            'profitable_orders': 0,
            'loss_orders': 0,
            'duration_minutes': 0,
            
            # Reversal trading
            'reversal_threshold_pips': self.reversal_threshold_pips,
            'highest_buy_price': 0.0,
            'lowest_sell_price': float('inf'),
            'reversal_count': 0,
            'closed_orders_pl': 0.0,
            'open_orders_pl': 0.0,
            'total_cycle_pl': 0.0,
            'last_reversal_time': None,
            'reversal_history': [],
            
            # Recovery mode
            'in_recovery_mode': False,
            'recovery_zone_base_price': 0.0,
            'initial_stop_loss_price': 0.0,
            'initial_order_stop_loss': self.initial_order_stop_loss,
            'recovery_activated': False,
            'reversal_threshold_from_recovery': False,
            'recovery_direction': None,
            'initial_direction': direction,
            'initial_order_open_price': order_data['price'],
            'placed_levels': [],
            'initial_order_data': order_data
        }

    # ==================== CYCLE MANAGEMENT ====================

    async def _handle_close_cycle_event(self, content: dict) -> bool:
        """Handle close cycle event"""
        try:
            cycle_id = content.get("id")
            username = content.get("user_name", "system")
            
            if cycle_id == "all":
                return await self._close_all_cycles(username)
            else:
                return await self._close_single_cycle(cycle_id, username)
                
        except Exception as e:
            logger.error(f"Error handling close cycle event: {e}")
            return False

    async def _close_single_cycle(self, cycle_id: str, username: str) -> bool:
        """Close a single cycle"""
        try:
            #sync with pocketbase
            self._sync_cycles_with_pocketbase()
            cycle = self._find_cycle_by_id(cycle_id)
            if not cycle:
                logger.warning(f"Cycle not found: {cycle_id}")
                return False
            
            # Store final cycle data before closing orders
            final_cycle_data = {
                'total_profit': cycle.total_profit,
                'total_volume': cycle.total_volume,
                'direction': cycle.direction,
                'current_direction': cycle.current_direction,
                'active_orders': cycle.active_orders.copy() if hasattr(cycle, 'active_orders') else [],
                'completed_orders': cycle.completed_orders.copy() if hasattr(cycle, 'completed_orders') else [],
                'orders': cycle.orders.copy() if hasattr(cycle, 'orders') else []
            }
            
            # Close all orders in the cycle
            closed_orders = await self._close_all_cycle_orders(cycle)
            
            # Convert orders status to inactive
            await self._update_orders_status_to_inactive(cycle)
            
            # Restore final cycle data
            cycle.total_profit = final_cycle_data['total_profit']
            cycle.total_volume = final_cycle_data['total_volume']
            cycle.direction = final_cycle_data['direction']
            cycle.current_direction = final_cycle_data['current_direction']
            cycle.orders = final_cycle_data['orders']
            cycle.completed_orders = final_cycle_data['completed_orders'] + final_cycle_data['active_orders']
            cycle.active_orders = []  # Clear active orders since they're now completed
            
            # Update cycle status to closed (but don't remove from active yet)
            cycle.is_closed = True
            cycle.is_active = False
            cycle.close_reason = "manual"
            cycle.closed_by = username
            cycle.close_time = datetime.datetime.now()
            
            # Update cycle in database with is_closed=True
            await self._update_cycle_in_database(cycle)
            
            # Update in-memory statistics
            self._update_cycle_statistics_on_close(cycle)
            
            # Remove from active cycles after database update
            self._remove_cycle_from_active(cycle)
            
            logger.info(f"Cycle {cycle_id} closed successfully ({closed_orders} orders) - Database updated with is_closed=True")
            return True
        except Exception as e:
            logger.error(f"Error closing cycle {cycle_id}: {e}")
            return False

    def _update_cycle_statistics_on_close(self, cycle):
        """Update in-memory statistics when closing a cycle"""
        try:
            # Update in-memory statistics
            self.loss_tracker['closed_cycles_count'] += 1
            self.loss_tracker['active_cycles_count'] = len(self._get_only_active_cycles())
            self.loss_tracker['updated_at'] = datetime.datetime.now()
            
            # Track profitable vs loss-making cycles
            if hasattr(cycle, 'total_profit') and cycle.total_profit > 0:
                self.total_profitable_cycles += 1
                self.loss_tracker['profitable_cycles'] += 1
            else:
                self.total_loss_making_cycles += 1
                self.loss_tracker['loss_making_cycles'] += 1
            
            logger.debug(f"Updated statistics for closed cycle {cycle.cycle_id}")
            
        except Exception as e:
            logger.error(f"Error updating cycle statistics on close: {e}")

    def _update_cycle_status_on_close(self, cycle, closing_method: str, username: str = "system"):
        """Update cycle status when closing (DEPRECATED - use direct updates in close methods)"""
        try:
            cycle.is_closed = True
            cycle.is_active = False  # Ensure cycle is marked as inactive
            cycle.close_reason = closing_method
            cycle.closed_by = username
            cycle.close_time = datetime.datetime.now()
            
            # Update in-memory statistics
            self._update_cycle_statistics_on_close(cycle)
            
            logger.info(f"Cycle {cycle.cycle_id} closed: {closing_method} by {username}")
            
            # NOTE: Don't remove from active cycles here - let the calling method handle it
            # after database update is complete
            
        except Exception as e:
            logger.error(f"Error updating cycle status on close: {e}")

    async def _close_all_cycles(self, username: str) -> bool:
        """Close all active cycles"""
        try:
            cycles_to_close = self.active_cycles.copy()
            closed_count = 0
            
            for cycle in cycles_to_close:
                if await self._close_single_cycle(cycle.cycle_id, username):
                    closed_count += 1
            
            logger.info(f"Closed {closed_count} cycles")
            return True
            
        except Exception as e:
            logger.error(f"Error closing all cycles: {e}")
            return False

    async def _close_all_cycle_orders(self, cycle) -> int:
        """Close all orders in a cycle"""
        try:
            closed_count = 0
            
            for order in cycle.active_orders.copy():
                if self._close_order_in_mt5(order.get('ticket'), order):
                    closed_count += 1
                    cycle.active_orders.remove(order)
                    cycle.completed_orders.append(order)
            
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing cycle orders: {e}")
            return 0

    def _close_order_in_mt5(self, order_ticket: str, order_data: dict) -> bool:
        """Close an order in MetaTrader 5"""
        try:
            if not order_ticket:
                logger.warning("No order ticket provided for closing")
                return False
            
            # Log the closing attempt
            logger.debug(f"Attempting to close order {order_ticket}")
            
            # Use MetaTrader to close the position
            result = self.meta_trader.close_position(order_data)
            
            if result:
                logger.info(f"Order {order_ticket} closed successfully")
                return True
            else:
                logger.error(f"Failed to close order {order_ticket}")
                return False
                
        except Exception as e:
            logger.error(f"Error closing order {order_ticket}: {e}")
            return False

    def _find_cycle_by_id(self, cycle_id: str):
        """Find a cycle by its ID"""
        for cycle in self.active_cycles:
            if cycle.cycle_id == cycle_id:
                return cycle
        return None

    def _remove_cycle_from_active(self, cycle):
        """Remove a cycle from active management"""
        try:
            logger.info(f"Removing cycle {cycle.cycle_id} from active management")
            if cycle in self.active_cycles:
                self.active_cycles.remove(cycle)
                logger.info(f"Removed cycle from active_cycles list")
            if cycle.cycle_id in self.cycles:
                del self.cycles[cycle.cycle_id]
                logger.info(f"Removed cycle from cycles dictionary")
            
            # Update loss tracker
            self.loss_tracker['active_cycles_count'] = len(self.active_cycles)
            self.loss_tracker['updated_at'] = datetime.datetime.now()
            logger.info(f"Updated loss tracker. Active cycles count: {self.loss_tracker['active_cycles_count']}")
            
        except Exception as e:
            logger.error(f"Error removing cycle from active management: {e}")

    def _cleanup_closed_cycles(self):
        """Clean up closed cycles from active management"""
        try:
            logger.info(f"Starting cycle cleanup. Current active cycles: {len(self.active_cycles)}")
            cycles_to_remove = []
            
            # Find cycles that should be removed
            for cycle in self.active_cycles:
                logger.debug(f"Checking cycle {cycle.cycle_id} - closed={getattr(cycle, 'is_closed', False)}, active={getattr(cycle, 'is_active', True)}")
                if (hasattr(cycle, 'is_closed') and cycle.is_closed) or \
                   (hasattr(cycle, 'is_active') and not cycle.is_active):
                    cycles_to_remove.append(cycle)
                    logger.info(f"Marking cycle {cycle.cycle_id} for removal: closed={getattr(cycle, 'is_closed', False)}, active={getattr(cycle, 'is_active', True)}, active_orders={len(getattr(cycle, 'active_orders', []))}")
            
            # Remove closed cycles
            for cycle in cycles_to_remove:
                logger.info(f"Removing cycle {cycle.cycle_id} from active cycles")
                self._remove_cycle_from_active(cycle)
            
            if cycles_to_remove:
                logger.info(f"Cleaned up {len(cycles_to_remove)} closed cycles. Remaining active cycles: {len(self.active_cycles)}")
                
        except Exception as e:
            logger.error(f"Error cleaning up closed cycles: {e}")

    def _get_only_active_cycles(self) -> List:
        """Get only truly active cycles, filtering out closed ones"""
        try:
            active_cycles = []
            
            for cycle in self.active_cycles:
                # Check if cycle is truly active
                if (hasattr(cycle, 'is_active') and cycle.is_active) and \
                   (not hasattr(cycle, 'is_closed') or not cycle.is_closed):
                    active_cycles.append(cycle)
            
            return active_cycles
            
        except Exception as e:
            logger.error(f"Error getting active cycles: {e}")
            return []

    # ==================== STRATEGY CONTROL ====================

    def start_strategy(self):
        """Start the strategy"""
        try:
            if self.strategy_active:
                logger.info("Strategy is already active")
                return True
            
            self.strategy_active = True
            self.trading_active = True
            
            # Clean up any closed cycles before starting
            self._cleanup_closed_cycles()
            
            # Start monitoring thread with sync wrapper
            async def monitoring_wrapper():
                await self._monitoring_loop()
                
            self.monitoring_thread = threading.Thread(target=asyncio.run, args=(monitoring_wrapper(),), daemon=True)
            self.monitoring_thread.start()
            
            logger.info("AdvancedCyclesTrader strategy started")
            return True
            
        except Exception as e:
            logger.error(f"Error starting strategy: {e}")
            return False

    def stop_strategy(self):
        """Stop the strategy"""
        try:
            self.strategy_active = False
            self.trading_active = False
            
            # Wait for monitoring thread to finish
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=5)
            
            logger.info("AdvancedCyclesTrader strategy stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping strategy: {e}")
            return False

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Strategy monitoring loop started")
        
        while self.strategy_active:
            try:
                # Clean up closed cycles periodically
                self._cleanup_closed_cycles()
                
                # Update only active cycles
                self._update_active_cycles_sync()
                
                # Get market data
                market_data = self._get_market_data()
                
                if market_data:
                    # Process strategy logic
                    await self._process_strategy_logic(market_data)
                    
                    # Monitor order management
                    # self._monitor_order_management(market_data)
                
                # Sleep before next iteration
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)  # Wait longer on error
        
        logger.info("Strategy monitoring loop stopped")

    def _update_active_cycles_sync(self):
        """Update active cycles synchronously with real-time profit calculation"""
        try:
            # Get only truly active cycles
            active_cycles = self._get_only_active_cycles()
            
            # Get current market price
            current_price = self.meta_trader.get_bid(self.symbol)
            
            # Update each active cycle with live data and profit calculation
            for cycle in active_cycles.copy():
                try:
                    # Update orders with live MT5 data (includes profit recalculation)
                    cycle.update_orders_with_live_data()
                    
                    # Update cycle status (includes profit recalculation)
                    cycle.update_cycle_status()
                    
                    # Force profit recalculation to ensure accuracy
                    cycle._recalculate_total_profit()
                    
                    # Update database with latest profit information
                    cycle._update_cycle_in_database()
                        
                except Exception as e:
                    logger.error(f"Error updating cycle {cycle.cycle_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error updating active cycles: {e}")

    async def _process_strategy_logic(self, market_data: dict):
        """Process main strategy logic"""
        try:
            current_price = market_data.get('current_price')
            if not current_price:
                return
            
            # Update current market price
            self.current_market_price = current_price
            
            # Only process logic for truly active cycles
            active_cycles = self._get_only_active_cycles()
            
            # Check for take profit conditions first
            for cycle in active_cycles.copy():
                if self._check_cycle_take_profit(cycle, current_price):
                    try:
                        logger.info(f"Take profit hit for cycle {cycle.cycle_id}, closing cycle")
                        await self._close_single_cycle(cycle.cycle_id,"system")
                        continue
                    except Exception as e:
                        logger.error(f"Error handling take profit for cycle {cycle.cycle_id}: {e}")
                        continue
            
            # Check for initial order stop losses
            for cycle in active_cycles.copy():
                if self._check_initial_order_stop_loss(cycle, current_price):
                    try:
                        # Always handle stop loss synchronously to avoid MetaTrader attribute issues
                        logger.warning(f"Stop loss detected for cycle {cycle.cycle_id}, handling synchronously")
                        self._close_initial_order_stop_loss_sync(cycle, current_price)
                        continue
                    except Exception as e:
                        logger.error(f"Error handling stop loss for cycle {cycle.cycle_id}: {e}")
                        continue
            
            # Update active cycles list after potential closures
            active_cycles = self._get_only_active_cycles()
            
            # NEW: Check for post-stop-loss recovery zone activation
            self._check_post_stop_loss_recovery(current_price, market_data)
            
            # Check for interval-based cycle creation
            #self._check_interval_based_cycle_creation(current_price, market_data)
            self._check_cycle_intervals(current_price)
            # Filter cycles for breach and reversal checks - exclude cycles in recovery mode without recovery orders
            cycles_for_breach_reversal = self._filter_cycles_for_breach_reversal_checks(active_cycles)
            
            # Continue with other strategy logic using filtered cycles
            self._check_reversal_conditions_for_cycles(current_price, market_data, cycles_for_breach_reversal)
            self._check_zone_breaches(current_price, market_data, cycles_for_breach_reversal)
            # self._manage_continuous_orders_for_cycles(current_price, market_data, active_cycles)
            
        except Exception as e:
            logger.error(f"Error processing strategy logic: {e}")

    def _filter_cycles_for_breach_reversal_checks(self, active_cycles: List) -> List:
        """
        Filter cycles for breach and reversal checks.
        Exclude cycles that are in recovery mode but haven't placed recovery orders yet.
        """
        try:
            filtered_cycles = []
            
            for cycle in active_cycles:
                # Check if cycle is in recovery mode
                if hasattr(cycle, 'in_recovery_mode') and cycle.in_recovery_mode:
                    cycle_id = cycle.cycle_id
                    
                    # Check if cycle has recovery data
                    if cycle_id in self.recovery_cycles:
                        recovery_data = self.recovery_cycles[cycle_id]
                        
                        # Only include if recovery zone is activated and has recovery orders
                        if recovery_data.get('recovery_activated', False):
                            # Check if cycle has recovery orders
                            recovery_orders = [
                                order for order in cycle.active_orders + cycle.completed_orders
                                if order.get('kind') == 'recovery'
                            ]
                            
                            if recovery_orders:
                                # Recovery zone is active and has orders - include in checks
                                filtered_cycles.append(cycle)
                                logger.debug(f"Cycle {cycle_id} included in breach/reversal checks - has {len(recovery_orders)} recovery orders")
                            else:
                                # Recovery zone active but no orders yet - exclude from checks
                                logger.debug(f"Cycle {cycle_id} excluded from breach/reversal checks - recovery zone active but no orders placed yet")
                        else:
                            # Recovery zone not activated yet - exclude from checks
                            logger.debug(f"Cycle {cycle_id} excluded from breach/reversal checks - recovery zone not activated")
                    else:
                        # In recovery mode but no recovery data - exclude from checks
                        logger.debug(f"Cycle {cycle_id} excluded from breach/reversal checks - in recovery mode but no recovery data")
                # else:
                    # Not in recovery mode - include in normal checks
                    # filtered_cycles.append(cycle)
            
            logger.debug(f"Filtered {len(filtered_cycles)} cycles out of {len(active_cycles)} for breach/reversal checks")
            return filtered_cycles
            
        except Exception as e:
            logger.error(f"Error filtering cycles for breach/reversal checks: {e}")
            return active_cycles  # Return all cycles if filtering fails

    def _check_reversal_conditions_for_cycles(self, current_price: float, market_data: dict, active_cycles: List):
        """Check for reversal conditions for both normal and recovery cycles"""
        try:
            # Check normal active cycles (already filtered to exclude recovery cycles without orders)
            for cycle in active_cycles:
                # # Skip if cycle is in recovery mode without recovery orders (double check)
                # if self._is_cycle_in_recovery_without_orders(cycle):
                #     logger.debug(f"Skipping reversal check for cycle {cycle.cycle_id} - in recovery mode without orders")
                #     continue
                    
                reversal_info = cycle.check_reversal_condition(current_price)
                
                if reversal_info['should_reverse']:
                    logger.info(f"Reversal detected for cycle {cycle.cycle_id}")
                    # Always handle reversals synchronously in this context
                    self._handle_reversal_sync(cycle, current_price, reversal_info['new_direction'])
            
            # # Check recovery cycles for reversal conditions
            # self._check_recovery_cycles_for_reversal(current_price, market_data)
                    
        except Exception as e:
            logger.error(f"Error checking reversal conditions: {e}")

    def _check_recovery_cycles_for_reversal(self, current_price: float, market_data: dict):
        """Check recovery cycles for reversal conditions based on recovery order prices"""
        try:
            # Use list() to avoid modification during iteration since cycles may exit recovery mode
            for cycle_id, recovery_data in list(self.recovery_cycles.items()):
                # Double-check cycle still exists in recovery tracking (might have been removed)
                if cycle_id not in self.recovery_cycles:
                    continue
                    
                if not recovery_data.get('recovery_activated', False):
                    continue
                
                cycle = recovery_data['cycle']
                
                # Skip if cycle is no longer active
                if not cycle.is_active or cycle.is_closed:
                    self._cleanup_recovery_cycle(cycle_id)
                    continue
                
                # Check for reversal based on recovery orders
                reversal_info = self._check_recovery_reversal_condition(recovery_data, current_price)
                
                if reversal_info['should_reverse']:
                    logger.info(f"Recovery reversal detected for cycle {cycle_id}")
                    self._handle_recovery_reversal_sync(cycle_id, recovery_data, current_price, reversal_info['new_direction'])
                    
        except Exception as e:
            logger.error(f"Error checking recovery cycles for reversal: {e}")

    def _check_recovery_reversal_condition(self, recovery_data: dict, current_price: float) -> dict:
        """Check if recovery cycle should reverse based on recovery order prices"""
        try:
            result = {
                'should_reverse': False,
                'new_direction': None,
                'reversal_price': None,
                'reversal_reason': None
            }
            
            cycle = recovery_data['cycle']
            initial_direction = recovery_data['initial_direction']
            
            # Get recovery orders (orders placed after initial stop loss) from both active and completed orders
            all_orders = []
            if hasattr(cycle, 'active_orders'):
                all_orders.extend(cycle.active_orders)
            if hasattr(cycle, 'completed_orders'):
                all_orders.extend(cycle.completed_orders)
    
            recovery_orders = [
                order for order in all_orders
                if order.get('kind') == 'recovery'
            ]
            
            if not recovery_orders:
                return result
            pip_value = self._get_pip_value()
            reversal_distance_points = self.reversal_threshold_pips * pip_value
            
            if initial_direction == "BUY":
                # Find highest recovery buy order price among BUY orders
                buy_recovery_orders = [
                    order.get('open_price', 0.0) for order in recovery_orders 
                    if order.get('type') == 0  # BUY orders
                ]
                if buy_recovery_orders:
                    highest_recovery_price = max(buy_recovery_orders)
                    
                    if highest_recovery_price > 0:
                        reversal_price = highest_recovery_price - reversal_distance_points
                        
                        if current_price <= reversal_price:
                            result.update({
                                'should_reverse': True,
                                'new_direction': 'SELL',
                                'reversal_price': reversal_price,
                                'reversal_reason': f'Price dropped {self.reversal_threshold_pips} pips from highest recovery buy at {highest_recovery_price}'
                            })
            elif initial_direction == "SELL":
                # Find lowest recovery sell order price
                sell_recovery_orders = [
                    order.get('open_price', float('inf')) for order in recovery_orders 
                    if order.get('type') == 1  # SELL orders
                ]
                if sell_recovery_orders:
                    lowest_recovery_price = min(sell_recovery_orders)
                else:
                    lowest_recovery_price = float('inf')
                
                if lowest_recovery_price < float('inf'):
                    reversal_price = lowest_recovery_price + reversal_distance_points
                    
                    if current_price >= reversal_price:
                        result.update({
                            'should_reverse': True,
                            'new_direction': 'BUY',
                            'reversal_price': reversal_price,
                            'reversal_reason': f'Price rose {self.reversal_threshold_pips} pips from lowest recovery sell at {lowest_recovery_price}'
                        })
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking recovery reversal condition: {e}")
            return {'should_reverse': False, 'new_direction': None, 'reversal_price': None, 'reversal_reason': None}

    def _handle_recovery_reversal_sync(self, cycle_id: str, recovery_data: dict, current_price: float, new_direction: str):
        """Handle reversal for recovery cycle"""
        try:
            cycle = recovery_data['cycle']
            old_direction = recovery_data['initial_direction']
            
            logger.info(f"Handling recovery reversal for cycle {cycle_id}: {old_direction} -> {new_direction}")
            
            # Close all recovery orders
            closed_orders_count = self._close_all_cycle_orders_sync(cycle)
            
            if closed_orders_count > 0:
                # Update reversal statistics
                cycle._update_reversal_statistics(current_price, new_direction, closed_orders_count)
                
                # Switch direction
                cycle.switch_direction(new_direction, "recovery_reversal")
                
                # # Clean up recovery mode and return to normal trading
                # self._exit_recovery_mode(cycle_id, recovery_data)
                
                # # Update cycle in database
                # cycle._update_cycle_in_database()
                
                logger.info(f"Recovery reversal completed: {closed_orders_count} orders closed, direction switched to {new_direction}")
                
                # Place first order in new direction
                self._place_reversal_order_sync(cycle, current_price, new_direction)
            else:
                logger.warning(f"No orders were closed during recovery reversal for cycle {cycle_id}")
            
        except Exception as e:
            logger.error(f"Error handling recovery reversal: {e}")

    def _exit_recovery_mode(self, cycle_id: str, recovery_data: dict):
        """Exit recovery mode and return cycle to normal operation"""
        try:
            cycle = recovery_data['cycle']
            
            # Mark cycle as no longer in recovery mode
            cycle.in_recovery_mode = False
            
            # Clean up recovery tracking
            self._cleanup_recovery_cycle(cycle_id)
            
            logger.info(f"Cycle {cycle_id} exited recovery mode")
            
        except Exception as e:
            logger.error(f"Error exiting recovery mode: {e}")

    def _place_reversal_order_sync(self, cycle, price: float, direction: str):
        """Place first order after reversal in new direction"""
        try:
            if direction == "BUY":
                self._place_buy_order_sync(cycle, price)
            elif direction == "SELL":
                self._place_sell_order_sync(cycle, price)
            
            logger.info(f"Reversal order placed in {direction} direction at {price}")
            
        except Exception as e:
            logger.error(f"Error placing reversal order: {e}")

    def _handle_reversal_sync(self, cycle, current_price: float, new_direction: str):
        """Handle reversal synchronously"""
        try:
            logger.info(f"Handling reversal synchronously for cycle {cycle.cycle_id}: {cycle.current_direction} -> {new_direction}")
            
            # Close all active orders synchronously
            closed_orders_count = self._close_all_cycle_orders_sync(cycle)
            
            if closed_orders_count > 0:
                # Update reversal statistics
                cycle._update_reversal_statistics(current_price, new_direction, closed_orders_count)
                
                # Switch direction
                cycle.switch_direction(new_direction, "reversal")
                
                # Update cycle in database
                cycle._update_cycle_in_database()
                
                logger.info(f"Reversal completed: {closed_orders_count} orders closed, direction switched to {new_direction}")
            else:
                logger.warning(f"No orders were closed during reversal for cycle {cycle.cycle_id}")
            
        except Exception as e:
            logger.error(f"Error handling reversal synchronously: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")

    def _close_all_cycle_orders_sync(self, cycle) -> int:
        """Close all orders in a cycle synchronously"""
        try:
            closed_count = 0
            
            for order in cycle.active_orders.copy():
                try:
                    if self._close_order_in_mt5(order.get('ticket'), order):
                        closed_count += 1
                        
                        # Update order status to closed
                        order['status'] = 'closed'
                        order['is_closed'] = True
                        order['close_time'] = datetime.datetime.now().isoformat()
                        order['close_reason'] = 'reversal'
                        
                        # Move order from active to completed
                        cycle.active_orders.remove(order)
                        cycle.completed_orders.append(order)
                        logger.debug(f"Closed order {order.get('ticket')} successfully and updated status to closed")
                    else:
                        logger.warning(f"Failed to close order {order.get('ticket')}")
                except Exception as order_error:
                    logger.error(f"Error closing order {order.get('ticket')}: {order_error}")
                    continue
            
            # Update status of all completed orders to ensure they are marked as closed
            for order in cycle.completed_orders:
                if order.get('status') != 'closed':
                    order['status'] = 'closed'
                    order['is_closed'] = True
                    if not order.get('close_time'):
                        order['close_time'] = datetime.datetime.now().isoformat()
                    if not order.get('close_reason'):
                        order['close_reason'] = 'reversal'
            
            logger.info(f"Updated {len(cycle.completed_orders)} completed orders to closed status")
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing cycle orders synchronously: {e}")
            return 0

    def _check_zone_breaches(self, current_price: float, market_data: dict, filtered_cycles: List = None):
        """Check for zone breaches"""
        try:
            # Use filtered cycles if provided, otherwise get all active cycles
            cycles_to_check = filtered_cycles if filtered_cycles is not None else self.active_cycles
            
            # Find the cycle that should handle this breach
            target_cycle = None
            for cycle in cycles_to_check:
                # Skip if cycle is in recovery mode without recovery orders (double check)
                # if self._is_cycle_in_recovery_without_orders(cycle):
                #     continue
                #check if there are recovery orders from cycle
                recovery_orders = [
                    order for order in cycle.active_orders + cycle.completed_orders
                    if order.get('kind') == 'recovery'
                ]
        
                # Use zone engine to detect breaches
                cycle._update_price_extremes(current_price)
                if cycle.current_direction == "BUY":
                    last_buy_price = None
                    if cycle.highest_buy_price < current_price:
                        last_buy_price = cycle.highest_buy_price
                    else:
                        if cycle.lowest_buy_price > current_price:
                            last_buy_price = cycle.lowest_buy_price
                            
                    # Only check for zone breach if we have a valid reference price
                    if last_buy_price is not None:
                        zone_status = self.zone_engine.detect_zone_breach(current_price, last_buy_price, self.order_interval_pips)
                    else:
                        if len(recovery_orders) > 0:
                            zone_status = {'breach_detected': False}
                        else:
                            zone_status = {'breach_detected': True}
                        
                elif cycle.current_direction == "SELL":
                    last_sell_price = None
                    if cycle.lowest_sell_price > current_price:
                        last_sell_price = cycle.lowest_sell_price
                    else:
                        if cycle.highest_sell_price < current_price:
                            last_sell_price = cycle.highest_sell_price
                            
                    # Only check for zone breach if we have a valid reference price
                    if last_sell_price is not None:
                        zone_status = self.zone_engine.detect_zone_breach(current_price, last_sell_price, self.order_interval_pips)
                    else:
                        if len(recovery_orders) > 0:
                            zone_status = {'breach_detected': False}
                        else:
                            zone_status = {'breach_detected': True}
                
                # Get breach direction and price before checking breach detection
                breach_direction = zone_status.get('breach_direction')
                breach_price = current_price

                if zone_status.get('breach_detected', False):
                    logger.info(f"Zone breach detected: {zone_status}")
                
                # Place new order in the same direction as the cycle
                    if cycle.current_direction == "BUY":
                        self._place_buy_order_sync(cycle, breach_price)
                    elif cycle.current_direction == "SELL":
                        self._place_sell_order_sync(cycle, breach_price)
                    
                    logger.info(f"Zone breach order placed in cycle {cycle.cycle_id} direction: {breach_direction}")
                  
        except Exception as e:
            logger.error(f"Error checking zone breaches: {e}")

    def _is_cycle_in_recovery_without_orders(self, cycle) -> bool:
        """
        Check if a cycle is in recovery mode but doesn't have recovery orders yet.
        Returns True if the cycle should be excluded from breach/reversal checks.
        """
        try:
            # Check if cycle is in recovery mode
            if not (hasattr(cycle, 'in_recovery_mode') and cycle.in_recovery_mode):
                return False
            
            cycle_id = cycle.cycle_id
            
            # Check if cycle has recovery data
            if cycle_id not in self.recovery_cycles:
                return True  # In recovery mode but no recovery data
            
            recovery_data = self.recovery_cycles[cycle_id]
            
            # Check if recovery zone is activated
            if not recovery_data.get('recovery_activated', False):
                return True  # Recovery zone not activated yet
            
            # Check if cycle has recovery orders
            recovery_orders = [
                order for order in cycle.active_orders + cycle.completed_orders
                if order.get('kind') == 'recovery'
            ]
            
            if not recovery_orders:
                return True  # Recovery zone active but no orders placed yet
            
            return False  # Cycle has recovery orders, can participate in checks
            
        except Exception as e:
            logger.error(f"Error checking if cycle is in recovery without orders: {e}")
            return False  # Default to allowing checks if error occurs

    def _manage_continuous_orders_for_cycles(self, current_price: float, market_data: dict, active_cycles: List):
        """Manage continuous orders only for active cycles"""
        try:
            for cycle in active_cycles:
                if cycle.should_place_next_order(current_price, time.time()):
                    # Manage zone-based orders for this cycle
                    self._manage_zone_based_orders_sync(cycle, current_price)
                    
        except Exception as e:
            logger.error(f"Error managing continuous orders: {e}")

    def _manage_zone_based_orders_sync(self, cycle, current_price: float):
        """Manage zone-based orders synchronously"""
        try:
            logger.debug(f"Managing zone-based orders synchronously for cycle {cycle.cycle_id}")
            
            # Calculate next order price
            next_order_price = cycle.get_next_order_price(current_price)
            
            # Create order based on cycle direction
            if cycle.current_direction == "BUY":
                self._place_buy_order_sync(cycle, next_order_price)
            elif cycle.current_direction == "SELL":
                self._place_sell_order_sync(cycle, next_order_price)
            
        except Exception as e:
            logger.error(f"Error managing zone-based orders synchronously: {e}")

    def _place_buy_order_sync(self, cycle, price: float):
        """Place a buy order synchronously"""
        try:
            order_data = self.meta_trader.buy(
                symbol=self.symbol,
                volume=self.lot_size,
                magic=self.bot.magic_number,
                sl=0.0,
                tp=0.0,
                sltp_type="PIPS",
                slippage=20,
                comment=f"ACT_BUY_ZONE_{cycle.cycle_id[:8]}"
            )
            if order_data and len(order_data) > 0:
                # Add order to cycle
                order_for_cycle = {
                    'ticket': int(order_data[0].ticket),
                    'type': 0,  # BUY
                    'kind': 'recovery',
                    'direction': 'BUY',
                    'open_price': order_data[0].price_open,
                    'volume': order_data[0].volume,
                    'symbol': order_data[0].symbol,
                    'status': 'active',
                    'profit': 0.0,
                    'swap': 0.0,
                    'commission': 0.0,
                    'magic_number': order_data[0].magic,
                    'comment': f"ACT_BUY_ZONE_{cycle.cycle_id[:8]}",
                    'sl': 0.0,
                    'tp': 0.0,
                    'trailing_steps': 0,
                    'margin': 0.0,
                    'is_pending': False,
                    'is_closed': False,
                    'open_time': datetime.datetime.now().isoformat(),
                    'cycle_id': cycle.cycle_id,
                    'cycle_create': None
                }
                
                cycle.add_order(order_for_cycle)
                
                # Force profit recalculation and database update
                cycle._recalculate_total_profit()
                cycle._update_cycle_in_database()
                
                logger.info(f"Buy order placed: {order_data[0].ticket}")
                
        except Exception as e:
            logger.error(f"Error placing buy order synchronously: {e}")

    def _place_sell_order_sync(self, cycle, price: float):
        """Place a sell order synchronously"""
        try:
            order_data = self.meta_trader.sell(
                symbol=self.symbol,
                volume=self.lot_size,
                magic=self.bot.magic_number,
                sl=0.0,
                tp=0.0,
                sltp_type="PIPS",
                slippage=20,
                comment=f"ACT_SELL_ZONE_{cycle.cycle_id[:8]}"
            )
            
            if order_data and len(order_data) > 0:
                # Add order to cycle
                order_for_cycle = {
                    'ticket': int(order_data[0].ticket),
                    'type': 1,  # SELL
                    'kind': 'recovery',
                    'direction': 'SELL',
                    'open_price': price,
                    'volume': self.lot_size,
                    'symbol': self.symbol,
                    'status': 'active',
                    'profit': 0.0,
                    'swap': 0.0,
                    'commission': 0.0,
                    'magic_number': self.bot.magic_number,
                    'comment': f"ACT_SELL_ZONE_{cycle.cycle_id[:8]}",
                    'sl': 0.0,
                    'tp': 0.0,
                    'trailing_steps': 0,
                    'margin': 0.0,
                    'is_pending': False,
                    'is_closed': False,
                    'open_time': datetime.datetime.now().isoformat(),
                    'cycle_id': cycle.cycle_id,
                    'cycle_create': None
                }
                
                cycle.add_order(order_for_cycle)
                
                # Force profit recalculation and database update
                cycle._recalculate_total_profit()
                cycle._update_cycle_in_database()
                
                logger.info(f"Sell order placed: {order_data[0].ticket}")
                
        except Exception as e:
            logger.error(f"Error placing sell order synchronously: {e}")

    def _monitor_order_management(self, market_data: dict):
        """Monitor order management"""
        try:
            # Detect and organize missing orders
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._detect_and_organize_missing_orders())
                else:
                    # If no running loop, handle synchronously
                    logger.debug("No running event loop, detecting orders synchronously")
                    self._detect_and_organize_missing_orders_sync()
            except RuntimeError:
                # No event loop available, handle synchronously
                logger.debug("No event loop available, detecting orders synchronously")
                self._detect_and_organize_missing_orders_sync()
            
            # Force sync cycles with MT5 periodically
            if time.time() % 30 == 0:  # Every 30 seconds
                self._force_sync_all_cycles_with_mt5()
                
        except Exception as e:
            logger.error(f"Error monitoring order management: {e}")

    # ==================== UTILITY METHODS ====================

    def _get_market_data(self) -> Optional[dict]:
        """Get current market data"""
        try:
            bid = self.meta_trader.get_bid(self.symbol)
            ask = self.meta_trader.get_ask(self.symbol)
            
            if bid is None or ask is None:
                return None
            
            return {
                'current_price': (bid + ask) / 2,
                'bid': bid,
                'ask': ask,
                'spread': ask - bid,
                'timestamp': datetime.datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    def _get_pip_value(self) -> float:
        """Get pip value for the current symbol"""
        try:
            # Get symbol point from MetaTrader and multiply by 100
            symbol_info = self.meta_trader.get_symbol_info(self.symbol)
            if symbol_info and hasattr(symbol_info, 'point'):
                return symbol_info.point * 10
            
        except Exception as e:
            logger.error(f"Error getting pip value: {e}")
            return 0.0001

    def set_entry_price(self, price: float):
        """Set the entry price for the strategy"""
        self.entry_price = price

    async def _detect_and_organize_missing_orders(self):
        """Detect and organize missing orders"""
        try:
            # Get all positions from MT5
            positions = self.meta_trader.get_all_positions()
            if not positions:
                return
            
            # Find orders that are not in any cycle
            missing_orders = []
            for pos in positions:
                if not self._is_order_in_any_cycle(pos):
                    missing_orders.append(pos)
            
            if missing_orders:
                logger.info(f"Found {len(missing_orders)} missing orders")
                await self._process_missing_orders(missing_orders)
                
        except Exception as e:
            logger.error(f"Error detecting missing orders: {e}")

    def _detect_and_organize_missing_orders_sync(self):
        """Detect and organize missing orders synchronously"""
        try:
            # Get all positions from MT5
            positions = self.meta_trader.get_all_positions()
            if not positions:
                return
            
            # Find orders that are not in any cycle
            missing_orders = []
            for pos in positions:
                if not self._is_order_in_any_cycle(pos):
                    missing_orders.append(pos)
            
            if missing_orders:
                logger.info(f"Found {len(missing_orders)} missing orders")
                self._process_missing_orders_sync(missing_orders)
                
        except Exception as e:
            logger.error(f"Error detecting missing orders synchronously: {e}")

    def _process_missing_orders_sync(self, missing_orders: List):
        """Process missing orders synchronously by creating recovery cycles"""
        try:
            for order in missing_orders:
                self._create_recovery_cycle_for_order_sync(order)
                
        except Exception as e:
            logger.error(f"Error processing missing orders synchronously: {e}")

    def _create_recovery_cycle_for_order_sync(self, order):
        """Create a recovery cycle for a missing order synchronously"""
        try:
            # Extract order information
            ticket = getattr(order, 'ticket', None)
            order_type = getattr(order, 'type', None)
            price_open = getattr(order, 'price_open', 0.0)
            volume = getattr(order, 'volume', 0.0)
            
            if not ticket:
                return
            
            # Determine direction
            direction = "BUY" if order_type == 0 else "SELL"
            
            # Create cycle data
            cycle_data = self._build_cycle_data(
                {'price': price_open, 'current_price': price_open},
                direction,
                "system_recovery",
                "system"
            )
            
            # Create cycle
            cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
            
            # Add the order to the cycle
            order_data = {
                'ticket': int(ticket),
                'type': order_type,
                'kind': 'recovery',
                'direction': direction,
                'open_price': price_open,
                'volume': volume,
                'symbol': self.symbol,
                'status': 'active',
                'profit': 0.0,
                'swap': 0.0,
                'commission': 0.0,
                'magic_number': self.bot.magic_number,
                'comment': f"RECOVERY_{ticket}",
                'sl': 0.0,
                'tp': 0.0,
                'trailing_steps': 0,
                'margin': 0.0,
                'is_pending': False,
                'is_closed': False,
                'open_time': datetime.datetime.now().isoformat(),
                'cycle_id': cycle.cycle_id,
                'cycle_create': None
            }
            
            cycle.add_order(order_data)
            
            # Add to active cycles
            self.active_cycles.append(cycle)
            self.cycles[cycle.cycle_id] = cycle
            
            logger.info(f"Recovery cycle created synchronously for order {ticket}")
            
        except Exception as e:
            logger.error(f"Error creating recovery cycle synchronously for order: {e}")

    def _is_order_in_any_cycle(self, position) -> bool:
        """Check if an order is already in any cycle"""
        try:
            # Get ticket from position object using getattr
            position_ticket = str(getattr(position, 'ticket', ''))
            if not position_ticket:
                logger.warning(f"No ticket found in position object")
                return False
            
            for cycle in self.active_cycles:
                # Check active orders
                for order in cycle.active_orders:
                    if str(order.get('ticket', '')) == position_ticket:
                        logger.debug(f"Found order {position_ticket} in active orders of cycle {cycle.cycle_id}")
                        return True
                        
                # Check completed orders
                for order in cycle.completed_orders:
                    if str(order.get('ticket', '')) == position_ticket:
                        logger.debug(f"Found order {position_ticket} in completed orders of cycle {cycle.cycle_id}")
                        return True
            
            logger.debug(f"Order {position_ticket} not found in any cycle")
            return False
            
        except Exception as e:
            logger.error(f"Error checking if order is in any cycle: {e}")
            return False

    async def _process_missing_orders(self, missing_orders: List):
        """Process missing orders by creating recovery cycles"""
        try:
            for order in missing_orders:
                await self._create_recovery_cycle_for_order(order)
                
        except Exception as e:
            logger.error(f"Error processing missing orders: {e}")

    async def _create_recovery_cycle_for_order(self, order):
        """Create a recovery cycle for a missing order"""
        try:
            # Extract order information
            ticket = getattr(order, 'ticket', None)
            order_type = getattr(order, 'type', None)
            price_open = getattr(order, 'price_open', 0.0)
            volume = getattr(order, 'volume', 0.0)
            
            if not ticket:
                return
            
            # Determine direction
            direction = "BUY" if order_type == 0 else "SELL"
            
            # Create cycle data
            cycle_data = self._build_cycle_data(
                {'price': price_open, 'current_price': price_open},
                direction,
                "system_recovery",
                "system"
            )
            
            # Create cycle
            cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
            
            # Add the order to the cycle
            order_data = {
                'ticket': str(ticket),
                'direction': direction,
                'open_price': price_open,
                'volume': volume,
                'status': 'active'
            }
            
            cycle.add_order(order_data)
            
            # Add to active cycles
            self.active_cycles.append(cycle)
            self.cycles[cycle.cycle_id] = cycle
            
            logger.info(f"Recovery cycle created for order {ticket}")
            
        except Exception as e:
            logger.error(f"Error creating recovery cycle for order: {e}")

    def _force_sync_all_cycles_with_mt5(self):
        """Force sync all cycles with MT5"""
        try:
            for cycle in self.active_cycles:
                cycle.force_sync_with_mt5()
                
        except Exception as e:
            logger.error(f"Error force syncing cycles: {e}")

    # ==================== STATISTICS AND REPORTING ====================

    def get_strategy_statistics(self) -> dict:
        """Get comprehensive strategy statistics"""
        try:
            active_cycles_count = len(self.active_cycles)
            closed_cycles_count = len(self.closed_cycles)
            
            total_active_orders = sum(len(cycle.active_orders) for cycle in self.active_cycles)
            total_completed_orders = sum(len(cycle.completed_orders) for cycle in self.active_cycles)
            
            total_profit = sum(cycle.total_profit for cycle in self.active_cycles if hasattr(cycle, 'total_profit'))
            
            return {
                'strategy_name': 'AdvancedCyclesTrader',
                'symbol': self.symbol,
                'active_cycles': active_cycles_count,
                'closed_cycles': closed_cycles_count,
                'total_active_orders': total_active_orders,
                'total_completed_orders': total_completed_orders,
                'total_profit': total_profit,
                'strategy_active': self.strategy_active,
                'trading_active': self.trading_active,
                'current_market_price': self.current_market_price,
                'zone_activated': self.zone_activated,
                'initial_threshold_breached': self.initial_threshold_breached,
                'last_update': datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting strategy statistics: {e}")
            return {}

    def get_multi_cycle_statistics(self) -> dict:
        """Get multi-cycle specific statistics"""
        try:
            cycle_stats = []
            
            for cycle in self.active_cycles:
                if hasattr(cycle, 'get_cycle_statistics'):
                    cycle_stats.append(cycle.get_cycle_statistics())
            
            return {
                'total_cycles': len(self.active_cycles),
                'cycle_details': cycle_stats,
                'max_active_cycles': self.max_active_cycles,
                'cycles_at_capacity': len(self.active_cycles) >= self.max_active_cycles
            }
            
        except Exception as e:
            logger.error(f"Error getting multi-cycle statistics: {e}")
            return {}

    # ==================== CLEANUP AND RESET ====================

    def reset_strategy(self):
        """Reset the strategy to initial state"""
        try:
            # Stop strategy if running
            if self.strategy_active:
                self.stop_strategy()
            
            # Clear cycles
            self.cycles.clear()
            self.active_cycles.clear()
            self.closed_cycles.clear()
            
            # Reset state variables
            self.current_market_price = None
            self.last_candle_time = None
            self.initial_threshold_breached = False
            self.zone_activated = False
            self.processed_events.clear()
            self.last_cycle_creation_time = 0
            self.last_cycle_price = 0
            logger.info("Strategy reset completed")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting strategy: {e}")
            return False

    async def cleanup(self):
        """Cleanup strategy resources"""
        try:
            # Close all active cycles
            await self._close_all_cycles("system_cleanup")
            
            # Stop strategy
            self.stop_strategy()
            
            # Clear all data
            self.reset_strategy()
            
            logger.info("Strategy cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    # ==================== ASYNC UTILITIES ====================

    async def run_in_thread(self):
        """Run strategy in a separate thread"""
        try:
            def run_coroutine_in_thread(coro):
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
            
            # Run the main strategy coroutine in a thread
            import threading
            thread = threading.Thread(
                target=run_coroutine_in_thread,
                args=(self.run(),),
                daemon=True
            )
            thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Error running strategy in thread: {e}")
            return False

    async def run(self):
        """Main strategy run method"""
        try:
            logger.info("Starting AdvancedCyclesTrader main run method")
            
            # Initialize strategy
            if not self.initialize():
                logger.error("Failed to initialize strategy")
                return False
            
            # Start strategy
            if not self.start_strategy():
                logger.error("Failed to start strategy")
                return False
            
            # Keep running until stopped
            while self.strategy_active:
                await asyncio.sleep(1)
            
            logger.info("AdvancedCyclesTrader run method completed")
            return True
            
        except Exception as e:
            logger.error(f"Error in strategy run method: {e}")
            return False

    # ==================== ADDITIONAL EVENT HANDLERS ====================

    async def _handle_close_order_event(self, content: dict) -> bool:
        """Handle close order event"""
        try:
            order_ticket = content.get("order_ticket")
            username = content.get("user_name", "system")
            
            if not order_ticket:
                logger.error("No order ticket provided")
                return False
            
            # Find the cycle containing this order
            cycle = self._find_cycle_containing_order(order_ticket)
            if not cycle:
                logger.warning(f"Order {order_ticket} not found in any cycle")
                return False
            
            # Close the specific order
            success = self._close_order_in_mt5(order_ticket, {})
            
            if success:
                # Update cycle
                cycle.update_orders_with_live_data()
                logger.info(f"Order {order_ticket} closed successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Error handling close order event: {e}")
            return False

    def _find_cycle_containing_order(self, order_ticket: str):
        """Find the cycle containing a specific order"""
        for cycle in self.active_cycles:
            for order in cycle.active_orders:
                if order.get('ticket') == order_ticket:
                    return cycle
        return None

    def _check_initial_order_stop_loss(self, cycle, current_price: float) -> bool:
        """
        Check if the initial order in a cycle has hit its stop loss level
        
        Args:
            cycle: The cycle to check
            current_price: Current market price
            
        Returns:
            bool: True if stop loss is hit, False otherwise
        """
        try:
            if not cycle or not cycle.active_orders:
                return False
                
            # Get the initial order (first order in the cycle)
            initial_order =0
            for order in cycle.active_orders:
                if order['kind'] == 'initial':
                    initial_order = order
                    break

            if not initial_order:
                return False
                
            # Get order details
            order_type = initial_order['type']  # 0 for buy, 1 for sell
            open_price = float(initial_order['open_price'])
            
            # Calculate stop loss level
            stop_loss_pips = float(cycle.initial_order_stop_loss)
            pip_value = self._get_pip_value()
            stop_loss_points = stop_loss_pips * pip_value
            
            # Check if price has hit stop loss level
            if order_type == 0:  # BUY
                stop_loss_level = open_price - stop_loss_points
                if current_price <= stop_loss_level:
                    logger.info(f"🔴 BUY Stop loss hit at {current_price} (level: {stop_loss_level})")
                    return True
            else:  # SELL
                stop_loss_level = open_price + stop_loss_points
                if current_price >= stop_loss_level:
                    logger.info(f"🔴 SELL Stop loss hit at {current_price} (level: {stop_loss_level})")
                    return True
                    
            return False
                
        except Exception as e:
            logger.error(f"Error checking initial order stop loss: {e}")
            return False
            
    async def _close_initial_order_stop_loss(self, cycle, current_price: float):
        """
        Close the initial order and its cycle when stop loss is hit
        
        Args:
            cycle: The cycle containing the initial order
            current_price: Current market price
        """
        try:
            if not cycle or not cycle.active_orders:
                return
                
            # Get the initial order
            initial_order = next((order for order in cycle.active_orders if order.get('kind', '').startswith('initial')), None)
            if not initial_order:
                return
                
            logger.info(f"🔴 Initial order stop loss hit for cycle {cycle.cycle_id}")
            
            # Close the order in MT5
            order_ticket = initial_order.get('ticket')
            if order_ticket:
                # Create close order request
                close_request = {
                    'action': self.meta_trader.TRADE_ACTION_DEAL,
                    'position': int(order_ticket),
                    'magic': self.bot.magic_number,
                    'volume': float(initial_order.get('volume', 0.0)),
                    'type': 1 if initial_order.get('type') == 0 else 0,  # Reverse order type for closing
                    'price': current_price,
                    'deviation': 20,
                    'comment': f"stop_loss_{order_ticket}"
                }
                
                # Close position
                close_result = self.meta_trader.close_position(close_request)
                
                if close_result:
                    logger.info(f"✅ Closed initial order {order_ticket} at stop loss")
                    
                    # Update order status
                    initial_order['is_closed'] = True
                    initial_order['close_price'] = current_price
                    initial_order['close_time'] = datetime.datetime.now().isoformat()
                    initial_order['close_reason'] = 'stop_loss'
                    initial_order['status'] = 'closed'
                    
                    # Move order to completed orders
                    if initial_order in cycle.active_orders:
                        cycle.active_orders.remove(initial_order)
                        cycle.completed_orders.append(initial_order)
                else:
                    logger.error(f"❌ Failed to close initial order {order_ticket}")
                    return
            
            # Update cycle status
            cycle.is_closed = True
            cycle.is_active = False
            cycle.close_reason = "stop_loss"
            cycle.closed_by = "system"
            cycle.close_time = datetime.datetime.now()
            
            # Update orders status to inactive
            await self._update_orders_status_to_inactive(cycle)
            
            # Update cycle in database
            await self._update_cycle_in_database(cycle)
            
            # Remove cycle from active management
            self._remove_cycle_from_active(cycle)
            
            logger.info(f"Cycle {cycle.cycle_id} closed due to initial order stop loss")
                
        except Exception as e:
            logger.error(f"Error closing initial order on stop loss: {e}")

    def _close_initial_order_stop_loss_sync(self, cycle, current_price: float):
        """Set up recovery mode after initial order stop loss"""
        try:
            if not cycle or not cycle.active_orders:
                return
                
            # Get the initial order
            initial_order = None
            for order in cycle.active_orders:
                if order.get('kind') == 'initial':
                    initial_order = order
                    break

            if not initial_order:
                return
                
            logger.info(f"🔴 Initial order stop loss hit for cycle {cycle.cycle_id} - entering recovery mode")
            
            # Close the initial order in MT5
            order_ticket = initial_order['ticket']
            if order_ticket:
                close_result = self.meta_trader.close_position(initial_order)
                
                if close_result:
                    logger.info(f"✅ Closed initial order {order_ticket} at stop loss")
                    
                    # Update order status
                    initial_order['is_closed'] = True
                    initial_order['close_price'] = current_price
                    initial_order['close_time'] = datetime.datetime.now().isoformat()
                    initial_order['close_reason'] = 'stop_loss'
                    initial_order['status'] = 'closed'
                    
                    # Move order to completed orders
                    if initial_order in cycle.active_orders:
                        cycle.active_orders.remove(initial_order)
                        cycle.completed_orders.append(initial_order)
                        
                    # Set up recovery mode instead of closing cycle
                    self._setup_recovery_mode(cycle, current_price, initial_order)
                    
                else:
                    logger.error(f"❌ Failed to close initial order {order_ticket}")
                    return
            
            logger.info(f"Cycle {cycle.cycle_id} entered recovery mode after initial stop loss")
                
        except Exception as e:
            logger.error(f"Error handling initial order stop loss for recovery: {e}")

    def _setup_recovery_mode(self, cycle, current_price: float, initial_order: dict):
        """Set up cycle for recovery mode trading"""
        try:
            # Add cycle to recovery tracking
            self.recovery_cycles[cycle.cycle_id] = {
                'cycle': cycle,
                'initial_direction': getattr(cycle, 'initial_direction', cycle.current_direction),
                'initial_order_open_price': getattr(cycle, 'initial_order_open_price', float(initial_order['open_price'])),
                'initial_stop_loss_price': getattr(cycle, 'initial_stop_loss_price', current_price),
                'recovery_zone_base_price': getattr(cycle, 'recovery_zone_base_price', current_price),
                'recovery_activated': getattr(cycle, 'recovery_activated', False),
                'recovery_direction': getattr(cycle, 'recovery_direction', None),
                'initial_order_data': getattr(cycle, 'initial_order_data', initial_order),
                'placed_levels': set(),  # Track price levels where orders were placed
                'entry_time': datetime.datetime.now(),
                'reversal_threshold_from_recovery': getattr(cycle, 'reversal_threshold_from_recovery', False)
            }
                
            # Initialize price levels tracking for this cycle
            self.recovery_price_levels[cycle.cycle_id] = set()
            
            # Mark cycle as in recovery mode
            cycle.in_recovery_mode = True
            cycle.recovery_zone_base_price = current_price
            cycle.initial_stop_loss_price = current_price
            
            # Update cycle in database using synchronous method
            try:
                cycle._update_cycle_in_database()
                logger.info(f"✅ Database updated for recovery mode setup - cycle {cycle.cycle_id}")
            except Exception as db_error:
                logger.error(f"❌ Failed to update database for recovery mode setup - cycle {cycle.cycle_id}: {db_error}")
                # Continue with recovery mode setup even if database update fails
            
            logger.info(f"Recovery mode setup complete for cycle {cycle.cycle_id} at price {current_price}")
            
        except Exception as e:
            logger.error(f"Error setting up recovery mode: {e}")

    def _check_interval_based_cycle_creation(self, current_price: float, market_data: dict):
        """
        Check if we should create a new cycle based on price movement intervals
        """
        try:
            if not hasattr(self, 'last_cycle_price'):
                self.last_cycle_price = current_price
                return
                
            # Calculate pip difference
            pip_value = self._get_pip_value()
            price_diff_pips = abs(current_price - self.last_cycle_price) / pip_value
            
            # Check if we've moved enough pips to create a new cycle
            if price_diff_pips >= self.cycle_interval:
                direction = "BUY" if current_price > self.last_cycle_price else "SELL"
                logger.info(f"Price moved {price_diff_pips:.2f} pips {direction}, creating new cycle")
                
                # Create new cycle with initial order
                self._create_interval_cycle_sync(direction, current_price)
                
                # Update last cycle price
                self.last_cycle_price = current_price
                
        except Exception as e:
            logger.error(f"Error checking interval-based cycle creation: {e}")
            
    def _create_interval_cycle_sync(self, direction: str, price: float):
        """
        Create a new cycle with initial order based on price movement
        """
        try:
              # Check if we should create a cycle at this level
            if direction == "BUY" and price > self.meta_trader.get_ask(self.symbol):
                return  # Don't create BUY cycles below current price
            if direction == "SELL" and price < self.meta_trader.get_bid(self.symbol):
                return  # Don't create SELL cycles above current price
            # Check if we can create more cycles
            if len(self.active_cycles) >= self.max_active_cycles:
                logger.warning(f"Cannot create new cycle: max cycles ({self.max_active_cycles}) reached")
                return
        except Exception as e:
            logger.error(f"Error creating interval cycle: {e}")
            return
                
        # Create order data with enhanced error handling and validation
        order_data = {
            'symbol': self.symbol,
            'volume': self.lot_size,
            'magic': self.bot.magic_number,
            'sl': 0.0,
            'tp': 0.0,
            'sltp_type': "PIPS",
            'slippage': 20,
            'comment': f"ACT_{direction}_INTERVAL_{int(price * 10000)}",  # Include price for better tracking
        }

        # Place the order with enhanced error handling
        try:
            logger.info(f"Placing {direction} order for interval cycle at price {price}")
            
            if direction == "BUY":
                order_result = self.meta_trader.buy(**order_data)
            else:  # SELL
                order_result = self.meta_trader.sell(**order_data)
                
            # Enhanced order result validation
            if not order_result:
                logger.error(f"MetaTrader returned None for {direction} order placement")
                return
                
            if isinstance(order_result, dict) and order_result.get('retcode') != 10009:  # TRADE_RETCODE_DONE
                logger.error(f"Order placement failed with retcode: {order_result.get('retcode')} - {order_result.get('comment', 'No comment')}")
                return
                
            if isinstance(order_result, list) and len(order_result) == 0:
                logger.error(f"Empty order result list for {direction} order")
                return
            
            # Process order result into proper format
            processed_order_data = {
                'price': order_result[0].price_open,
                'ticket': str(order_result[0].ticket) ,
                'volume': order_data['volume'],
                'symbol': order_data['symbol'],
                'type': 0 if direction == "BUY" else 1,  # 0 for BUY, 1 for SELL
                'magic_number': self.bot.magic_number,
                'comment': order_data['comment'],
                'sl': 0.0,
                'tp': 0.0,
                'price_level': price  # Store the level in order data
            }
                
            logger.info(f"Successfully placed {direction} order for interval cycle")
            
            # Create cycle with enhanced tracking using synchronous version
            cycle_created = self._create_manual_cycle(
                processed_order_data, 
                direction, 
                "system", 
                True, 
                f"interval_cycle_at_{price}"
            )
            
            if cycle_created:
                # Update last cycle price
                self.last_cycle_price = price
                logger.info(f"Interval cycle created successfully for {direction} at {price}")
            else:
                logger.warning(f"Cycle creation failed despite successful order placement for {direction} at {price}")
                
        except Exception as order_error:
            logger.error(f"Exception during {direction} order placement for interval cycle: {order_error}")
            return

    def _create_manual_cycle_sync(self, order_data: dict, direction: str, 
                                username: str, sent_by_admin: bool, user_id: str) -> bool:
        """
        Synchronous version of create_manual_cycle
        """
        try:
            logger.info(f"Starting manual cycle creation with order {order_data.get('ticket')}")
            
            # Create cycle data
            cycle_data = self._build_cycle_data(order_data, direction, username, user_id)
            logger.info(f"Built cycle data: {cycle_data.get('id')}")
            
            # Create cycle instance
            cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
            logger.info(f"Created cycle instance: {cycle.cycle_id}")
            
            # Add the order to the cycle before creating in database
            # Create Flutter-compatible order structure
            order_for_cycle = {
                'ticket': int(order_data.get('ticket', 0)),
                'type': order_data.get('type', 0),  # 0 = BUY, 1 = SELL
                'kind': 'initial',  # orderKind - required by Flutter
                'direction': direction,
                'open_price': float(order_data.get('price', 0.0)),
                'volume': float(order_data.get('volume', 0.0)),
                'symbol': str(order_data.get('symbol', '')),
                'status': 'active',
                'profit': 0.0,
                'swap': 0.0,
                'commission': 0.0,
                'magic_number': int(order_data.get('magic_number', 0)),
                'comment': str(order_data.get('comment', '')),
                'sl': float(order_data.get('sl', 0.0)),
                'tp': float(order_data.get('tp', 0.0)),
                'trailing_steps': 0,
                'margin': 0.0,
                'is_pending': False,
                'is_closed': False,
                'open_time': datetime.datetime.now().isoformat(),
                'cycle_id': None,
                'cycle_create': None
            }
            
            # Add order to cycle
            cycle.add_order(order_for_cycle)
            logger.info(f"Added order {order_for_cycle.get('ticket')} to cycle {cycle.cycle_id}")
            
            # Verify cycle is not already in active cycles
            existing_cycle = next((c for c in self.active_cycles if c.cycle_id == cycle.cycle_id), None)
            if existing_cycle:
                logger.warning(f"Cycle {cycle.cycle_id} already exists in active cycles")
                return False
            
            # Add cycle to active cycles
            self.active_cycles.append(cycle)
            self.cycles[cycle.cycle_id] = cycle
            logger.info(f"Added cycle {cycle.cycle_id} to active cycles. Total active cycles: {len(self.active_cycles)}")
            
            # Update in-memory statistics
            self.total_cycles_created += 1
            self.loss_tracker['active_cycles_count'] += 1
            self.loss_tracker['updated_at'] = datetime.datetime.now()
            
            # Create cycle in PocketBase database (now with the order included)
            cycle._create_cycle_in_database()
            logger.info(f"Created cycle {cycle.cycle_id} in database")
            
            logger.info(f"Manual cycle created: {cycle.cycle_id} ({direction}) with order {order_data.get('ticket')}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating manual cycle synchronously: {e}")
            return False

    def _calculate_cycle_total_profit_pips(self, cycle, current_price: float) -> float:
        """
        Calculate total profit for a cycle in account currency from all orders (active and completed)
        
        Args:
            cycle: The cycle to calculate profit for
            current_price: Current market price for unrealized profit calculation
            
        Returns:
            float: Total profit in account currency (not pips)
        """
        try:
            # Force recalculation of cycle profits to ensure accuracy
            cycle._recalculate_total_profit()
            
            # Return the comprehensive total profit (includes profit, swap, commission)
            total_profit = cycle.total_profit
            
            return total_profit
            
        except Exception as e:
            logger.error(f"Error calculating cycle total profit: {e}")
            return 0.0

    def _check_cycle_take_profit(self, cycle, current_price: float) -> bool:
        """
        Check if a cycle has hit its take profit threshold
        
        Args:
            cycle: The cycle to check
            current_price: Current market price
            
        Returns:
            bool: True if take profit is hit, False otherwise
        """
        try:
            if not cycle or not hasattr(cycle, 'active_orders'):
                return False
            
            # Calculate total profit from all orders (active and completed) in account currency
            total_profit = self._calculate_cycle_total_profit_pips(cycle, current_price)
            
            # Check if total profit exceeds take profit threshold
            if total_profit >= self.take_profit_pips:
                logger.info(f"🟢 Take profit hit for cycle {cycle.cycle_id}: {total_profit:.2f} >= {self.take_profit_pips}")
                return True
                
            return False
                
        except Exception as e:
            logger.error(f"Error checking cycle take profit: {e}")
            return False

    def _close_cycle_take_profit_sync(self, cycle, current_price: float):
        """Close a cycle when take profit is hit (synchronous version)"""
        try:
            if not cycle:
                return
                
            logger.info(f"🟢 Closing cycle {cycle.cycle_id} due to take profit hit")
            
            # Close all active orders in the cycle
            closed_orders_count = 0
            for order in cycle.active_orders.copy():
                try:
                    order_ticket = order.get('ticket')
                    if order_ticket and self._close_order_in_mt5(order_ticket, order):
                        closed_orders_count += 1
                        logger.info(f"✅ Closed order {order_ticket} for take profit")
                        
                        # Update order status
                        order['is_closed'] = True
                        order['close_price'] = current_price
                        order['close_time'] = datetime.datetime.now().isoformat()
                        order['close_reason'] = 'take_profit'
                        order['status'] = 'closed'
                        
                        # Move order to completed orders
                        if order in cycle.active_orders:
                            cycle.active_orders.remove(order)
                            cycle.completed_orders.append(order)
                    else:
                        logger.error(f"❌ Failed to close order {order_ticket} for take profit")
                        
                except Exception as order_error:
                    logger.error(f"Error closing order {order.get('ticket')} for take profit: {order_error}")
                    continue
            
            # CRITICAL: Explicitly set cycle status to CLOSED before database update
            cycle.is_closed = True
            cycle.is_active = False
            cycle.status = 'closed'  # Explicit status field
            cycle.close_reason = "take_profit"
            cycle.closed_by = "system"
            cycle.close_time = datetime.datetime.now()
            
            # Verify critical status fields are set correctly
            logger.info(f"🔒 CYCLE STATUS VERIFICATION for {cycle.cycle_id}:")
            logger.info(f"   - is_closed: {cycle.is_closed}")
            logger.info(f"   - is_active: {cycle.is_active}")
            logger.info(f"   - status: {getattr(cycle, 'status', 'NOT_SET')}")
            logger.info(f"   - close_reason: {cycle.close_reason}")
            
            # Calculate final profit
            final_profit_pips = self._calculate_cycle_total_profit_pips(cycle, current_price)
            
            # Update orders status to inactive
            for order in cycle.active_orders + cycle.completed_orders:
                order['status'] = 'inactive'
                order['is_active'] = False
            
            # Update cycle in database using synchronous method
            try:
                # Log the status data being sent to PocketBase
                logger.info(f"📤 SENDING TO POCKETBASE for cycle {cycle.cycle_id}:")
                logger.info(f"   - is_closed: {cycle.is_closed}")
                logger.info(f"   - status: {getattr(cycle, 'status', 'NOT_SET')}")
                logger.info(f"   - close_reason: {cycle.close_reason}")
                logger.info(f"   - close_time: {cycle.close_time}")
                
                cycle._update_cycle_in_database()
                
                logger.info(f"✅ DATABASE UPDATED SUCCESSFULLY for cycle {cycle.cycle_id}")
                logger.info(f"   🔒 Cycle marked as CLOSED in PocketBase with take_profit reason")
                
            except Exception as db_error:
                logger.error(f"❌ CRITICAL: Failed to update database for cycle {cycle.cycle_id}: {db_error}")
                logger.error(f"   ⚠️  Cycle may still appear as ACTIVE in PocketBase!")
                # Continue with local cleanup even if database update fails
            
            # Update in-memory statistics
            self._update_cycle_statistics_on_close(cycle)
            
            # Remove cycle from active management
            self._remove_cycle_from_active(cycle)
            
            logger.info(f"🎯 TAKE PROFIT CYCLE CLOSURE COMPLETE for {cycle.cycle_id}:")
            logger.info(f"   📊 Orders closed: {closed_orders_count}")
            logger.info(f"   💰 Final profit: {final_profit_pips:.2f} pips")
            logger.info(f"   🔒 Cycle status: CLOSED (is_closed=True)")
            logger.info(f"   💾 Database: Updated with closed status")
                
        except Exception as e:
            logger.error(f"Error closing cycle on take profit: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    def _check_post_stop_loss_recovery(self, current_price: float, market_data: dict):
        """Check for post-stop-loss recovery zone activation"""
        try:
            if not self.recovery_cycles:
                return
            
            # Check each cycle in recovery mode
            for cycle_id, recovery_data in list(self.recovery_cycles.items()):
                cycle = recovery_data['cycle']
                
                # Skip if cycle is no longer active
                if not cycle.is_active or cycle.is_closed:
                    self._cleanup_recovery_cycle(cycle_id)
                    continue
                
                # Check if recovery zone should be activated
                if not recovery_data['recovery_activated']:
                    should_activate, activation_direction = self._should_activate_recovery_zone(recovery_data, current_price)
                    if should_activate:
                        self._activate_recovery_zone(cycle_id, recovery_data, current_price, activation_direction)
                
                # # If recovery zone is active and cycle still in recovery, manage zone-based orders
                # if cycle_id in self.recovery_cycles and recovery_data.get('recovery_activated', False):
                #     self._manage_recovery_zone_orders(cycle_id, recovery_data, current_price)
                
        except Exception as e:
            logger.error(f"Error checking post-stop-loss recovery: {e}")

    def _should_activate_recovery_zone(self, recovery_data: dict, current_price: float) -> tuple[bool, str]:
        """Check if recovery zone should be activated - SINGLE DIRECTION ONLY"""
        try:
            # If already activated, don't change direction
            if recovery_data.get('recovery_activated', False):
                return False, None
                
            # CHANGE: Use initial order open price instead of stop loss price
            initial_order_open_price = recovery_data['initial_order_open_price']
            initial_direction = recovery_data['initial_direction']
            # Calculate zone range distance from initial order open price
            pip_value = self._get_pip_value()
            zone_range_distance_points = self.zone_range_pips * pip_value
            
            # NEW: Check BOTH directions from open price
            downward_activation_price = initial_order_open_price - zone_range_distance_points
            upward_activation_price = initial_order_open_price + zone_range_distance_points
            
            # NEW: Single direction activation logic - FIRST direction to breach threshold wins
            if current_price <= downward_activation_price:
                if initial_direction == "BUY":
                    return True, "BUY"  # Price moved down, place BUY and LOCK direction
                else:
                    return True, "SELL"  # Price moved down, place SELL and LOCK direction
            elif current_price >= upward_activation_price:
                if initial_direction == "SELL":
                    return True, "SELL"  # Price moved up, place SELL and LOCK direction
                else:
                    return True, "BUY"  # Price moved up, place BUY and LOCK direction
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking recovery zone activation: {e}")
            return False, None

    def _activate_recovery_zone(self, cycle_id: str, recovery_data: dict, current_price: float, direction: str):
        """Activate recovery zone trading in specified direction"""
        try:
            recovery_data['recovery_activated'] = True
            recovery_data['activation_price'] = current_price
            recovery_data['activation_time'] = datetime.datetime.now()
            recovery_data['recovery_direction'] = direction  # NEW: Store direction
            cycle = recovery_data['cycle']
            cycle.recovery_activated = True
            cycle.recovery_direction = direction
            
            cycle._update_cycle_in_database()
            logger.info(f"🟡 Recovery zone ACTIVATED for cycle {cycle_id} at price {current_price} in {direction} direction")
            
            # Close any existing opposite direction recovery orders
            self._close_opposite_direction_recovery_orders(cycle, direction)
            
            # Place first recovery order in the determined direction
            self._place_recovery_order_with_direction(cycle_id, recovery_data, current_price, direction)
            
        except Exception as e:
            logger.error(f"Error activating recovery zone: {e}")

    def _manage_recovery_zone_orders(self, cycle_id: str, recovery_data: dict, current_price: float):
        """Manage orders in the recovery zone - SINGLE DIRECTION ONLY"""
        try:
            # Check if cycle is still in recovery mode (might have been removed after first order)
            if cycle_id not in self.recovery_cycles:
                return
                
            cycle = recovery_data['cycle']
            # CHANGE: Use stored recovery direction instead of initial direction
            recovery_direction = recovery_data.get('recovery_direction')
            
            # Validate recovery direction is set
            if not recovery_direction:
                logger.warning(f"Recovery direction not set for cycle {cycle_id}, skipping order placement")
                return
                
            placed_levels = recovery_data['placed_levels']
            
            # Calculate price level for potential order placement
            pip_value = self._get_pip_value()
            interval_points = self.order_interval_pips * pip_value
            
            # Round current price to nearest interval
            price_level = round(current_price / interval_points) * interval_points
            
            # Check if we should place an order at this level
            if price_level not in placed_levels:
                # ONLY place orders in the locked recovery direction
                self._place_recovery_order_with_direction(cycle_id, recovery_data, price_level, recovery_direction)
                placed_levels.add(price_level)
                
                logger.info(f"Recovery order placed at level {price_level} for cycle {cycle_id} in LOCKED {recovery_direction} direction")
            
        except Exception as e:
            logger.error(f"Error managing recovery zone orders: {e}")

    def _place_recovery_order(self, cycle_id: str, recovery_data: dict, price: float):
        """Place a recovery order in the same direction as initial order"""
        try:
            cycle = recovery_data['cycle']
            initial_direction = recovery_data['initial_direction']
            
            # Place order in same direction as initial order
            if initial_direction == "BUY":
                self._place_recovery_buy_order(cycle, price)
            elif initial_direction == "SELL":
                self._place_recovery_sell_order(cycle, price)
            
            # Update recovery data
            recovery_data['last_order_price'] = price
            recovery_data['last_order_time'] = datetime.datetime.now()
            
        except Exception as e:
            logger.error(f"Error placing recovery order: {e}")

    def _place_recovery_order_with_direction(self, cycle_id: str, recovery_data: dict, price: float, direction: str):
        """Place a recovery order in the specified direction (not necessarily initial direction)"""
        try:
            cycle = recovery_data['cycle']
            
            # NEW: Place order based on activation direction, not initial direction
            if direction == "BUY":
                self._place_recovery_buy_order(cycle, price)
            elif direction == "SELL":
                self._place_recovery_sell_order(cycle, price)
            
            # Update recovery data
            recovery_data['last_order_price'] = price
            recovery_data['last_order_time'] = datetime.datetime.now()
            #switch direction to the direction of the order
            cycle.switch_direction(direction,'recovery')
        except Exception as e:
            logger.error(f"Error placing directional recovery order: {e}")

    def _place_recovery_buy_order(self, cycle, price: float):
        """Place a recovery buy order"""
        try:
            order_data = self.meta_trader.buy(
                symbol=self.symbol,
                volume=self.lot_size,
                magic=self.bot.magic_number,
                sl=0.0,
                tp=0.0,
                sltp_type="PIPS",
                slippage=20,
                comment=f"ACT_RECOVERY_BUY_{cycle.cycle_id[:8]}"
            )
            
            if order_data and len(order_data) > 0:
                # Add order to cycle
                order_for_cycle = {
                    'ticket': int(order_data[0].ticket),
                    'type': 0,  # BUY
                    'kind': 'recovery',
                    'direction': 'BUY',
                    'open_price': order_data[0].price_open,
                    'volume': order_data[0].volume,
                    'symbol': order_data[0].symbol,
                    'status': 'active',
                    'profit': 0.0,
                    'swap': 0.0,
                    'commission': 0.0,
                    'magic_number': order_data[0].magic,
                    'comment': f"ACT_RECOVERY_BUY_{cycle.cycle_id[:8]}",
                    'sl': 0.0,
                    'tp': 0.0,
                    'trailing_steps': 0,
                    'margin': 0.0,
                    'is_pending': False,
                    'is_closed': False,
                    'open_time': datetime.datetime.now().isoformat(),
                    'cycle_id': cycle.cycle_id,
                    'cycle_create': None
                }
                
                cycle.add_order(order_for_cycle)
                
                # Force profit recalculation and database update
                cycle._recalculate_total_profit()
                cycle._update_cycle_in_database()
                
                logger.info(f"Recovery buy order placed: {order_data[0].ticket}")
                
        except Exception as e:
            logger.error(f"Error placing recovery buy order: {e}")

    def _place_recovery_sell_order(self, cycle, price: float):
        """Place a recovery sell order"""
        try:
            order_data = self.meta_trader.sell(
                symbol=self.symbol,
                volume=self.lot_size,
                magic=self.bot.magic_number,
                sl=0.0,
                tp=0.0,
                sltp_type="PIPS",
                slippage=20,
                comment=f"ACT_RECOVERY_SELL_{cycle.cycle_id[:8]}"
            )
            
            if order_data and len(order_data) > 0:
                # Add order to cycle
                order_for_cycle = {
                    'ticket': int(order_data[0].ticket),
                    'type': 1,  # SELL
                    'kind': 'recovery',
                    'direction': 'SELL',
                    'open_price': order_data[0].price_open,
                    'volume': order_data[0].volume,
                    'symbol': order_data[0].symbol,
                    'status': 'active',
                    'profit': 0.0,
                    'swap': 0.0,
                    'commission': 0.0,
                    'magic_number': order_data[0].magic,
                    'comment': f"ACT_RECOVERY_SELL_{cycle.cycle_id[:8]}",
                    'sl': 0.0,
                    'tp': 0.0,
                    'trailing_steps': 0,
                    'margin': 0.0,
                    'is_pending': False,
                    'is_closed': False,
                    'open_time': datetime.datetime.now().isoformat(),
                    'cycle_id': cycle.cycle_id,
                    'cycle_create': None
                }
                
                cycle.add_order(order_for_cycle)
                
                # Force profit recalculation and database update
                cycle._recalculate_total_profit()
                cycle._update_cycle_in_database()
                
                logger.info(f"Recovery sell order placed: {order_data[0].ticket}")
                
        except Exception as e:
            logger.error(f"Error placing recovery sell order: {e}")

    def _cleanup_recovery_cycle(self, cycle_id: str):
        """Clean up recovery cycle data"""
        try:
            if cycle_id in self.recovery_cycles:
                del self.recovery_cycles[cycle_id]
            if cycle_id in self.recovery_price_levels:
                del self.recovery_price_levels[cycle_id]
        except Exception as e:
            logger.error(f"Error cleaning up recovery cycle: {e}")

    def _close_opposite_direction_recovery_orders(self, cycle, recovery_direction: str):
        """Close any recovery orders in the opposite direction"""
        try:
            opposite_direction = "SELL" if recovery_direction == "BUY" else "BUY"
            orders_closed = 0
            
            # Find and close opposite direction recovery orders
            for order in cycle.active_orders:
                if (order.get('kind') == 'recovery' and 
                    order.get('direction') == opposite_direction and 
                    order.get('status') == 'active'):
                    
                    # Close the opposite direction order
                    try:
                        if order:
                            close_result = self.meta_trader.close_position({
                                'ticket': order.get('ticket'),
                                'symbol': order.get('symbol'),
                                'type': 0 if order.get('direction') == 'SELL' else 1,  # 0 for BUY, 1 for SELL
                                'volume': order.get('volume'),
                                'magic_number': order.get('magic_number')
                            })
                            if close_result:
                                order['status'] = 'closed'
                                orders_closed += 1
                                logger.info(f"Closed opposite direction recovery order {order.get('ticket')} ({opposite_direction}) when activating {recovery_direction} recovery")
                            else:
                                logger.warning(f"Failed to close opposite direction recovery order {order.get('ticket')}")
                    except Exception as close_error:
                        logger.error(f"Error closing opposite direction recovery order {order.get('ticket')}: {close_error}")
            
            if orders_closed > 0:
                logger.info(f"Closed {orders_closed} opposite direction recovery orders when locking to {recovery_direction}")
                
        except Exception as e:
            logger.error(f"Error closing opposite direction recovery orders: {e}")

    def _exit_recovery_mode_after_first_order(self, cycle_id: str, cycle):
        """Remove cycle from recovery mode after first recovery order is placed"""
        try:
            # Remove from recovery tracking
            if cycle_id in self.recovery_cycles:
                del self.recovery_cycles[cycle_id]
            if cycle_id in self.recovery_price_levels:
                del self.recovery_price_levels[cycle_id]
            
            # Update cycle state to normal operation
            cycle.in_recovery_mode = False
            
            # Update cycle in database using synchronous method
            try:
                cycle._update_cycle_in_database()
            except Exception as db_error:
                logger.error(f"❌ Failed to update database for recovery mode exit - cycle {cycle_id}: {db_error}")
                # Continue with recovery mode exit even if database update fails
            
            logger.info(f"Recovery mode exited for cycle {cycle_id}")
            
        except Exception as e:
            logger.error(f"Error exiting recovery mode for cycle {cycle_id}: {e}")

    def _parse_json_field(self, pb_cycle, field, default):
        try:
            return json.loads(getattr(pb_cycle, field, json.dumps(default)))
        except Exception as e:
            logger.error(f"Error parsing JSON field {field}: {e}")
            return default

    def _safe_int_value(self, value, default=0):
        """Safely convert a value to integer"""
        try:
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError):
            return default

    def _safe_float_value(self, value, default=0.0):
        """Safely convert a value to float"""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def _calculate_price_level(self):
        """Calculate the price level based on cycle_interval_pips"""
        pip_value = self._get_pip_value()
        if self.last_cycle_price == 0:
            self.last_cycle_price = self.meta_trader.get_ask(self.symbol)
        next_up_level= self.last_cycle_price + (self.cycle_interval*self._get_pip_value())
        next_down_level= self.last_cycle_price - (self.cycle_interval*self._get_pip_value())
        return next_up_level, next_down_level
    def _get_cycles_at_level(self, price_level, direction=None):
        """Get all cycles at a specific price level, optionally filtered by direction"""
        cycles_at_level = []
        for cycle in self.active_cycles:
            if abs(cycle.price_level - price_level) < 0.0001:  # Compare stored level directly
                if direction is None or cycle.initial_direction == direction:
                    cycles_at_level.append(cycle)
        return cycles_at_level

    def _check_cycle_intervals(self, current_price):
        """Check and create cycles at defined intervals"""
        try:
            if not current_price:
                return
            if not hasattr(self, 'last_cycle_price'):
                self.last_cycle_price = current_price
                return
            # Calculate the current price level
            next_up_level, next_down_level = self._calculate_price_level()
            current_level = next_up_level if current_price > self.last_cycle_price else next_down_level
            direction = "BUY" if current_price > self.last_cycle_price else "SELL"
            #  Check if we already have a cycle at this level
            existing_cycles = self._get_cycles_at_level(current_level, direction)
            if not existing_cycles:
        
                # Create new cycle with initial order
                self._create_interval_cycle_sync(direction, current_level)
              
          
            # # Check for BUY cycles
            # buy_levels_to_check = [
            #     current_level + (i * self.cycle_interval*self._get_pip_value())
            #     for i in range(3)  # Check next 3 levels above
            # ]
            
            # # Check for SELL cycles
            # sell_levels_to_check = [
            #     current_level - (i * self.cycle_interval*self._get_pip_value())
            #     for i in range(3)  # Check next 3 levels below
            # ]
            
            # for level in buy_levels_to_check:
            #     # Check if we already have a BUY cycle at this level
            #     existing_buy_cycles = self._get_cycles_at_level(level, "BUY")
            #     if not existing_buy_cycles:
         
            #         # Create new cycle with initial order
            #         self._create_interval_cycle_sync("BUY", level)
            # for level in sell_levels_to_check:
            #     # Check if we already have a SELL cycle at this level
            #     existing_sell_cycles = self._get_cycles_at_level(level, "SELL")
            #     if not existing_sell_cycles:
            #         # Create new SELL cycle at this level
            #         self._create_interval_cycle_sync("SELL", level)

        except Exception as e:
            logger.error(f"Error checking cycle intervals: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    def _create_cycle_at_level(self, price_level, direction):
        """Create a new cycle at the specified price level"""
        try:
            # Check if we should create a cycle at this level
            if direction == "BUY" and price_level <= self.meta_trader.get_ask(self.symbol):
                return  # Don't create BUY cycles below current price
            if direction == "SELL" and price_level >= self.meta_trader.get_bid(self.symbol):
                return  # Don't create SELL cycles above current price

            # Prepare order data
            order_data = {
                'price': price_level,
                'type': 'LIMIT',
                'direction': direction,
                'lot_size': self.lot_size,
                'symbol': self.symbol,
                'magic_number': self.bot.magic_number,
                'price_level': price_level  # Store the level in order data
            }

            # Create the cycle
            self._create_manual_cycle(
                order_data=order_data,
                direction=direction,
                username='auto cycle',
                sent_by_admin=False,
                user_id='auto cycle'
            )

            logger.info(f"Created new {direction} cycle at level {price_level}")

        except Exception as e:
            logger.error(f"Error creating cycle at level {price_level}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

   