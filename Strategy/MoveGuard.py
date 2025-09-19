"""
MoveGuard Strategy - Grid-Based Trading System

This is a grid-based trading strategy with adaptive zones, specific entry intervals,
multiple stop-loss settings, various zone movement modes, and trade limits.

Features:
- Grid-based order placement
- Adaptive zone management
- Multiple stop-loss configurations
- Zone movement modes (No Move, Move Up Only, Move Down Only, Move Both Sides)
- Trade limits and cycle management
"""

from operator import abs
from Strategy.strategy import Strategy
import threading
from Orders.order import order
from cycles.MoveGuard_cycle import MoveGuardCycle
from DB.db_engine import engine
from Strategy.components import AdvancedOrderManager, DirectionController
from Strategy.components.multi_cycle_manager import MultiCycleManager
from Strategy.components.enhanced_zone_detection import EnhancedZoneDetection
from Strategy.components.enhanced_order_manager import EnhancedOrderManager
from Strategy.components.reversal_detector import ReversalDetector
from helpers.mt5_order_utils import MT5OrderUtils
import asyncio
import datetime
import time
from Views.globals.app_logger import app_logger as logger
from typing import Dict, List, Optional, Any
import json
import traceback


class MoveGuard(Strategy):
    """
    MoveGuard Strategy - Grid-Based Trading System with Adaptive Zones
    
    Features:
    - Grid-based order placement with specific intervals
    - Adaptive zone management with movement modes
    - Multiple stop-loss configurations (Initial, Cycle, Recovery)
    - Zone movement modes (No Move, Move Up Only, Move Down Only, Move Both Sides)
    - Trade limits and cycle management
    - Real-time synchronization with database
    """

    def __init__(self, meta_trader, config, client, symbol, bot):
        """Initialize the MoveGuard strategy"""
        self._validate_initialization_parameters(meta_trader, config, client, symbol, bot)
        self._initialize_core_components(meta_trader, config, client, symbol, bot)
        self._initialize_strategy_configuration(config)
        self._initialize_advanced_components()
        self._initialize_trading_state()
        
    

    # ==================== INITIALIZATION METHODS ====================

    def _validate_initialization_parameters(self, meta_trader, config, client, symbol, bot):
        """Validate initialization parameters"""
        if bot is None:
            logger.error("🚨 CRITICAL: Bot parameter is None during MoveGuard initialization!")
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
        """Initialize MoveGuard strategy configuration parameters from bot config"""
        cfg = dict(config) if isinstance(config, dict) else {}

        # NEW: Handle symbol updates
        if 'symbol' in cfg and cfg['symbol'] != self.symbol:
            if self._update_strategy_symbol(cfg['symbol']):
                logger.info(f"✅ Symbol updated from {self.symbol} to {cfg['symbol']}")
            else:
                logger.error(f"❌ Failed to update symbol to '{cfg['symbol']}' - keeping current symbol '{self.symbol}'")

        # Core sizing
        self.lot_size = float(cfg.get("lot_size", 0.01))

        # Entry intervals (bot uses initial/subsequent naming)
        self.entry_interval_pips = float(cfg.get("initial_entry_interval_pips", cfg.get("entry_interval_pips", 50.0)))
        self.subsequent_entry_interval_pips = float(cfg.get("subsequent_entry_interval_pips", self.entry_interval_pips))

        # Grid interval derives from subsequent entries for spacing
        self.grid_interval_pips = float(cfg.get("subsequent_entry_interval_pips", self.entry_interval_pips))

        # Stop losses and take profit
        self.initial_stop_loss_pips = float(cfg.get("initial_order_sl_pips", 100.0))
        # Use initial SL for per-grid order SL if dedicated cycle SL isn't provided in bot config
        self.cycle_stop_loss_pips = float(cfg.get("initial_order_sl_pips", self.initial_stop_loss_pips))
        self.recovery_stop_loss_pips = float(cfg.get("recovery_sl_pips", 200.0))
        # Note: cycle_take_profit_pips is now interpreted as dollars, not pips
        self.cycle_take_profit_pips = float(cfg.get("cycle_take_profit_pips", 100.0))

        # Recovery spacing for additional recovery orders
        self.recovery_interval_pips = float(cfg.get("recovery_interval_pips", cfg.get("subsequent_entry_interval_pips", self.entry_interval_pips)))

        # Zones
        self.zone_movement_mode = cfg.get("zone_movement_mode", "Move Both Sides")
        self.zone_threshold_pips = float(cfg.get("zone_size_pips", 300.0))
        self.zone_move_step_pips = float(cfg.get("zone_move_step_pips", self.zone_threshold_pips))

        # Multi-cycle limits - will be set from max_concurrent_cycles config

        # Recovery switch
        self.recovery_enabled = True

        # Attributes expected by other components
        self.order_interval_pips = float(cfg.get("order_interval_pips", self.subsequent_entry_interval_pips))
        self.reversal_threshold_pips = float(cfg.get("reversal_threshold_pips", self.zone_threshold_pips))

        # Backward-compat keys required by other components expect these in config
        if isinstance(self.config, dict):
            # Ensure MultiCycleManager sees the correct limit (will be updated after max_active_cycles is set)
            self.config["max_concurrent_cycles"] = 3  # Temporary default, will be updated later
            # Provide safe defaults if not present (used by MultiCycleManager/EnhancedZoneDetection)
            self.config.setdefault("order_interval_pips", self.order_interval_pips)
            self.config.setdefault("reversal_threshold_pips", self.reversal_threshold_pips)

        # Keep a sensible cap for per-cycle grid orders (used internally)
        self.max_trades_per_cycle = int(cfg.get("max_trades_per_cycle", 50))
        self.max_active_trades_per_cycle = int(cfg.get("max_active_trades_per_cycle", 20))

        # Recovery spacing for additional recovery orders
        self.recovery_spacing_pips = float(cfg.get("recovery_spacing_pips", 50.0))
        
        # Cycle interval configuration (duplicated from Advanced Cycles Trader)
        self.max_active_cycles = int(cfg.get("max_concurrent_cycles", 3))
        self.cycle_interval = float(cfg.get("cycle_interval_pips", 100.0))
        self.auto_place_cycles = bool(cfg.get("auto_place_cycles", True))
        
        # Update config with the correct max_concurrent_cycles value
        if isinstance(self.config, dict):
            self.config["max_concurrent_cycles"] = self.max_active_cycles
        
        # Zone movement modes

        # Update magic number in PocketBase if it has changed
        self._update_magic_number_if_needed(cfg)
        
        # Market hours and price movement optimization
        self.last_price = None
        self.last_price_update_time = 0
        self.price_movement_threshold = 0.0001  # Minimum price change to trigger updates
        self.market_hours_enabled = bool(cfg.get("market_hours_enabled", True))
        
        # Advanced optimization systems
        self.batch_update_queue = []  # Queue for batch database updates
        self.batch_update_interval = float(cfg.get("batch_update_interval", 10.0))  # Process batch updates every N seconds
        self.last_batch_update_time = 0
        self.cache = {}  # Simple cache for frequently accessed data
        self.cache_ttl = float(cfg.get("cache_ttl", 30.0))  # Cache time-to-live in seconds
        self.processing_throttle = {}  # Per-cycle processing throttling
        self.cycle_process_interval = float(cfg.get("cycle_process_interval", 2.0))  # Process each cycle every N seconds
        self.database_update_interval = float(cfg.get("database_update_interval", 5.0))  # Database update throttling interval
        self.optimization_enabled = bool(cfg.get("optimization_enabled", True))  # Enable/disable optimizations

    def _initialize_advanced_components(self):
        """Initialize advanced components for MoveGuard"""
        # Initialize multi-cycle management system
        self.multi_cycle_manager = MultiCycleManager(
            self.meta_trader, self.bot, self.config, self.client
        )
        logger.info("✅ MultiCycleManager initialized for MoveGuard")
        
        # Initialize enhanced zone detection
        self.enhanced_zone_detection = EnhancedZoneDetection(
            self.symbol, self.reversal_threshold_pips, self.order_interval_pips
        )
        logger.info("✅ EnhancedZoneDetection initialized for MoveGuard")
        
        # Initialize enhanced order manager
        self.enhanced_order_manager = EnhancedOrderManager(
            self.meta_trader, self.symbol, self.bot.magic_number
        )
        logger.info("✅ EnhancedOrderManager initialized for MoveGuard")
        
        # Initialize reversal detector
        self.reversal_detector = ReversalDetector(self.reversal_threshold_pips)
        logger.info("✅ ReversalDetector initialized for MoveGuard")
        
        # Initialize direction controller
        self.direction_controller = DirectionController(self.symbol)
        logger.info("✅ DirectionController initialized for MoveGuard")

    def _initialize_trading_state(self):
        """Initialize MoveGuard trading state"""
        self.is_running = False
        self.is_initialized = False
        self.last_cycle_creation_time = 0
        self.cycle_creation_interval = 60  # 60 seconds between cycle creations
        
        # Grid state tracking
        self.current_grid_level = 0
        self.grid_direction = None
        self.last_grid_price = 0.0
        
        # Zone state tracking
        self.active_zones = {}
        self.zone_movement_history = []
        
        # Recovery state tracking
        self.recovery_cycles = {}
        self.recovery_direction_locks = {}
        
        # Cycle level tracking to prevent duplicates
        self.active_cycle_levels = set()  # Track active cycle levels
        
        logger.info("✅ MoveGuard trading state initialized")

    def _initialize_loss_tracker(self):
        """Initialize loss tracking for MoveGuard"""
        return {
            'total_loss': 0.0,
            'cycle_losses': {},
            'recovery_losses': {},
            'grid_losses': {},
            'last_reset': datetime.datetime.now()
        }

    # ==================== STRATEGY INITIALIZATION ====================

    def initialize(self):
        """Initialize the MoveGuard strategy"""
        try:
            logger.info("🚀 Initializing MoveGuard Strategy...")
            
            # Sync with PocketBase
            self._sync_cycles_with_pocketbase()
            
            # Initialize zone boundaries for existing cycles
            self._initialize_zone_boundaries_for_existing_cycles()
            
            # Fix missing grid levels for existing cycles
            self._fix_missing_grid_levels_for_existing_cycles()
            
            # Force refresh grid levels for all existing cycles to fix any incorrect values
            self._force_refresh_grid_levels_for_all_cycles()
            
            # Initialize strategy components
            self.is_initialized = True
            logger.info("✅ MoveGuard Strategy initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize MoveGuard Strategy: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    # ==================== POCKETBASE SYNCHRONIZATION ====================

    def _sync_cycles_with_pocketbase(self):
        """Sync cycles with PocketBase for MoveGuard"""
        try:
            logger.info("🔄 MoveGuard syncing cycles with PocketBase")
            
            # Get cycles from PocketBase
            cycles_data = self.client.get_all_MG_active_cycles_by_bot_id(self.bot.id)
             
            if not cycles_data:
                logger.info("No cycles found in PocketBase for MoveGuard")
                return
            
            # Process each cycle
            for pb_cycle in cycles_data:
                try:
                    # Convert PocketBase cycle to local format
                    local_cycle_data = self._convert_pb_cycle_to_local_format(pb_cycle)
                    
                    if local_cycle_data:
                        # Check if cycle already exists locally
                        existing_cycle = None
                        for cycle in self.multi_cycle_manager.get_all_active_cycles():
                            if cycle.cycle_id == local_cycle_data.get('cycle_id'):
                                existing_cycle = cycle
                                break
                        
                        if not existing_cycle:
                            # Create new cycle
                            try:
                                cycle = MoveGuardCycle(local_cycle_data, self.meta_trader, self.bot)
                                
                                # Sync zone data and bounds after creating cycle
                                self._sync_cycle_zone_data_from_database(cycle, pb_cycle)
                                
                                self.multi_cycle_manager.add_cycle(cycle)
                                logger.info(f"✅ MoveGuard cycle {cycle.cycle_id} synced from PocketBase")
                            except Exception as e:
                                logger.error(f"❌ Error creating cycle from PocketBase data: {str(e)}")
                                continue
                        else:
                            logger.debug(f"MoveGuard cycle {local_cycle_data.get('cycle_id')} already exists locally")
                            
                except Exception as e:
                    logger.error(f"❌ Error processing PocketBase cycle: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error syncing MoveGuard cycles with PocketBase: {str(e)}")
            logger.error(traceback.format_exc())

    def _convert_pb_cycle_to_local_format(self, pb_cycle) -> dict:
        """Convert PocketBase cycle data to local format for MoveGuard"""
        try:
            # Extract basic cycle data
            cycle_id = getattr(pb_cycle, 'id', '')
            if not cycle_id:
                logger.error("❌ PocketBase cycle missing 'id' field")
                return {}
            
            cycle_data = {
                'cycle_id': cycle_id,
                'id': cycle_id,  # Add 'id' field for database compatibility
                'symbol': getattr(pb_cycle, 'symbol', self.symbol),
                'direction': getattr(pb_cycle, 'direction', 'BUY'),
                'entry_price': self._safe_float_value(getattr(pb_cycle, 'entry_price', 0.0)),
                'lot_size': self._safe_float_value(getattr(pb_cycle, 'lot_size', self.lot_size)),
                'status': getattr(pb_cycle, 'status', 'active'),
                'created_at': getattr(pb_cycle, 'created', ''),
                'updated_at': getattr(pb_cycle, 'updated', ''),
                'total_volume': self._safe_float_value(getattr(pb_cycle, 'total_volume', 0.0)),
                'total_profit': self._safe_float_value(getattr(pb_cycle, 'total_profit', 0.0)),
                'total_profit_pips': self._safe_float_value(getattr(pb_cycle, 'total_profit_pips', 0.0)),
                'username': getattr(pb_cycle, 'username', 'system'),
                'user_id': getattr(pb_cycle, 'user_id', ''),
                'sent_by_admin': getattr(pb_cycle, 'sent_by_admin', False),
                'strategy_name': 'MoveGuard',
                'cycle_type': 'MoveGuard',
                'is_closed': bool(getattr(pb_cycle, 'is_closed', False)),
                'closing_method': getattr(pb_cycle, 'closing_method', None),
                'closed_at': getattr(pb_cycle, 'closed_at', None)
            }
            
            # Handle orders data
            orders_data = getattr(pb_cycle, 'orders', '[]')
            if isinstance(orders_data, str):
                try:
                    orders_list = json.loads(orders_data)
                    cycle_data['orders'] = orders_list
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in orders data for cycle {cycle_id}")
                    cycle_data['orders'] = []
            else:
                cycle_data['orders'] = orders_data if orders_data else []
            
            # Handle active orders
            active_orders_data = getattr(pb_cycle, 'active_orders', '[]')
            if isinstance(active_orders_data, str):
                try:
                    active_orders_list = json.loads(active_orders_data)
                    cycle_data['active_orders'] = active_orders_list
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in active_orders data for cycle {cycle_id}")
                    cycle_data['active_orders'] = []
            else:
                cycle_data['active_orders'] = active_orders_data if active_orders_data else []
            
            # Handle completed orders
            completed_orders_data = getattr(pb_cycle, 'completed_orders', '[]')
            if isinstance(completed_orders_data, str):
                try:
                    completed_orders_list = json.loads(completed_orders_data)
                    cycle_data['completed_orders'] = completed_orders_list
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in completed_orders data for cycle {cycle_id}")
                    cycle_data['completed_orders'] = []
            else:
                cycle_data['completed_orders'] = completed_orders_data if completed_orders_data else []

            # Enrich orders with grid_level/is_grid/is_initial if missing
            try:
                pip_value = self._get_pip_value()
                all_orders = cycle_data.get('orders', []) or []
                entry = cycle_data.get('entry_price', 0.0) or 0.0
                
                # First, try to update order types from MT5 comments for active orders
                for o in all_orders:
                    if o.get('status') == 'active':
                        # Create a temporary cycle object to use the update method
                        temp_cycle = type('TempCycle', (), {'orders': [o], 'cycle_id': cycle_id})()
                        self._update_order_type_from_mt5_comment(o)
                for o in all_orders:
                    # Normalize price field
                    price = o.get('price')
                    if price is None:
                        price = o.get('price_open', 0.0)
                    # Compute grid_level if absent using correct MoveGuard logic
                    if o.get('grid_level') is None and pip_value and self.grid_interval_pips:
                        try:
                            # MoveGuard grid level calculation:
                            # Level 0: Entry order (within zone boundaries)
                            # Level 1: First order above upper_bound + initial_offset OR below lower_bound - initial_offset
                            # Level 2+: Each subsequent level spaced by grid_interval_pips
                            
                            entry_interval_pips = getattr(cycle_data, 'entry_interval_pips', self.entry_interval_pips)
                            direction = cycle_data.get('direction', 'BUY')
                            
                            # Get zone boundaries from cycle data
                            zone_data = cycle_data.get('zone_data', {})
                            upper_boundary = zone_data.get('upper_boundary', entry)
                            lower_boundary = zone_data.get('lower_boundary', entry)
                            
                            # Calculate grid level based on direction and zone boundaries
                            if direction == 'BUY':
                                # For BUY: Level 1 starts below lower_boundary - initial_offset
                                grid_start_price = lower_boundary - (entry_interval_pips * pip_value)
                                
                                if float(price) >= lower_boundary:
                                    # Price is within or above zone - Level 0 (entry order)
                                    level = 0
                                elif float(price) > grid_start_price:
                                    # Price is between lower_boundary and grid_start_price - Level 0
                                    level = 0
                                else:
                                    # Price is at or below grid_start_price - calculate grid level
                                    # Level 1 starts exactly at grid_start_price
                                    price_diff = grid_start_price - float(price)
                                    pips_diff = price_diff / pip_value
                                    level = int(pips_diff / float(self.grid_interval_pips)) + 1
                                    level = max(1, level)
                            else:  # SELL
                                # For SELL: Level 1 starts above upper_boundary + initial_offset
                                grid_start_price = upper_boundary + (entry_interval_pips * pip_value)
                                
                                if float(price) <= upper_boundary:
                                    # Price is within or below zone - Level 0 (entry order)
                                    level = 0
                                elif float(price) < grid_start_price:
                                    # Price is between upper_boundary and grid_start_price - Level 0
                                    level = 0
                                else:
                                    # Price is at or above grid_start_price - calculate grid level
                                    # Level 1 starts exactly at grid_start_price
                                    price_diff = float(price) - grid_start_price
                                    pips_diff = price_diff / pip_value
                                    level = int(pips_diff / float(self.grid_interval_pips)) + 1
                                    level = max(1, level)
                            
                            o['grid_level'] = level
                            logger.debug(f"📊 Computed grid_level={level} for order {o.get('order_id')} (price={price}, entry={entry}, pips_diff={pips_diff:.1f}, entry_interval={entry_interval_pips})")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to compute grid_level for order {o.get('order_id')}: {e}")
                            o['grid_level'] = 0  # Fallback to entry order
                    elif o.get('grid_level') is None:
                        # No grid interval available, mark as entry order
                        o['grid_level'] = 0
                        logger.debug(f"📊 Set grid_level=0 for order {o.get('order_id')} (no grid interval)")
                    # Tag grid orders and set order types (only if order_type is not already set from MT5 comment)
                    grid_level = int(o.get('grid_level', 0))
                    current_order_type = o.get('order_type', '')
                    
                    # Only set order_type if it's not already set from MT5 comment
                    if not current_order_type or current_order_type == 'unknown':
                        if grid_level == 0 and not o.get('is_initial'):
                            # Mark as entry order (Level 0)
                            o['is_initial'] = True
                            o['is_grid'] = True
                            o['order_type'] = 'grid_0'
                            logger.debug(f"📊 Tagged entry order: order_id={o.get('order_id')}, grid_level={grid_level}")
                        elif grid_level >= 1 and not o.get('is_grid'):
                            # Mark as grid order (Level 1+)
                            o['is_grid'] = True
                            o['is_initial'] = False
                            # Set order type based on grid level
                            if grid_level == 1:
                                o['order_type'] = 'grid_entry'
                            else:
                                o['order_type'] = f'grid_level_{grid_level}'
                            logger.debug(f"📊 Tagged grid order: order_id={o.get('order_id')}, grid_level={grid_level}, order_type={o.get('order_type')}")
                    else:
                        # Order type already set from MT5 comment, just ensure flags are correct
                        if 'grid_0' in current_order_type.lower() or 'initial' in current_order_type.lower():
                            o['is_initial'] = True
                            o['is_grid'] = True
                        elif 'grid' in current_order_type.lower():
                            o['is_grid'] = True
                            o['is_initial'] = False
                        logger.debug(f"📊 Preserved existing order_type: order_id={o.get('order_id')}, order_type={current_order_type}")
                
                # Mark entry order (Level 0) - first order with grid_level 0
                entry_order = next((o for o in all_orders if int(o.get('grid_level', 0)) == 0), None)
                if entry_order and not entry_order.get('is_initial'):
                    entry_order['is_initial'] = True
                    entry_order['order_type'] = 'grid_0'
                    entry_order['is_grid'] = True
                    logger.debug(f"📊 Marked entry order: order_id={entry_order.get('order_id')}, grid_level={entry_order.get('grid_level')}")
                
                # Log summary of order processing
                grid_orders = [o for o in all_orders if o.get('is_grid')]
                initial_orders = [o for o in all_orders if o.get('is_initial')]
                logger.info(f"📊 Order enrichment summary for cycle {cycle_id}: {len(all_orders)} total orders, {len(grid_orders)} grid orders, {len(initial_orders)} initial orders")
            except Exception:
                pass
            
            # Handle grid data
            grid_data = getattr(pb_cycle, 'grid_data', '{}')
            if isinstance(grid_data, str):
                try:
                    grid_dict = json.loads(grid_data)
                    cycle_data['grid_data'] = grid_dict
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in grid data for cycle {cycle_id}")
                    cycle_data['grid_data'] = {
                        'current_level': 0,
                        'grid_direction': cycle_data['direction'],
                        'last_grid_price': cycle_data['entry_price'],
                        'grid_orders': []
                    }
            else:
                cycle_data['grid_data'] = grid_data if grid_data else {
                    'current_level': 0,
                    'grid_direction': cycle_data['direction'],
                    'last_grid_price': cycle_data['entry_price'],
                    'grid_orders': []
                }
            
            # Handle zone data
            zone_data = getattr(pb_cycle, 'zone_data', '{}')
            if isinstance(zone_data, str):
                try:
                    zone_dict = json.loads(zone_data)
                    cycle_data['zone_data'] = zone_dict
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in zone data for cycle {cycle_id}")
                    cycle_data['zone_data'] = {
                        'base_price': cycle_data['entry_price'],
                        'upper_boundary': cycle_data['entry_price'],
                        'lower_boundary': cycle_data['entry_price'],
                        'movement_mode': 'NO_MOVE',
                        'last_movement': None
                    }
            else:
                cycle_data['zone_data'] = zone_data if zone_data else {
                    'base_price': cycle_data['entry_price'],
                    'upper_boundary': cycle_data['entry_price'],
                    'lower_boundary': cycle_data['entry_price'],
                    'movement_mode': 'NO_MOVE',
                    'last_movement': None
                }
            
            # Handle recovery data
            recovery_data = getattr(pb_cycle, 'recovery_data', '{}')
            if isinstance(recovery_data, str):
                try:
                    recovery_dict = json.loads(recovery_data)
                    cycle_data['recovery_data'] = recovery_dict
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in recovery data for cycle {cycle_id}")
                    cycle_data['recovery_data'] = {
                        'recovery_orders': [],
                        'recovery_activated': False,
                        'recovery_direction': None
                    }
            else:
                cycle_data['recovery_data'] = recovery_data if recovery_data else {
                    'recovery_orders': [],
                    'recovery_activated': False,
                    'recovery_direction': None
                }
            
            # MoveGuard-specific configuration fields
            cycle_data['grid_interval_pips'] = self._safe_float_value(getattr(pb_cycle, 'grid_interval_pips', 50.0))
            cycle_data['entry_interval_pips'] = self._safe_float_value(getattr(pb_cycle, 'entry_interval_pips', 10.0))
            cycle_data['initial_stop_loss_pips'] = self._safe_float_value(getattr(pb_cycle, 'initial_stop_loss_pips', 300.0))
            cycle_data['cycle_stop_loss_pips'] = self._safe_float_value(getattr(pb_cycle, 'initial_stop_loss_pips', 200.0))
            cycle_data['recovery_stop_loss_pips'] = self._safe_float_value(getattr(pb_cycle, 'recovery_stop_loss_pips', 150.0))
            cycle_data['cycle_take_profit_pips'] = self._safe_float_value(getattr(pb_cycle, 'cycle_take_profit_pips', 100.0))
            cycle_data['max_trades_per_cycle'] = int(getattr(pb_cycle, 'max_trades_per_cycle', 10))
            cycle_data['zone_movement_mode'] = getattr(pb_cycle, 'zone_movement_mode', 'NO_MOVE')
            cycle_data['recovery_enabled'] = bool(getattr(pb_cycle, 'recovery_enabled', True))
            
            # Recovery mode fields - Extract from JSON fields based on actual schema
            # Extract recovery data from recovery_data JSON field
            recovery_data = getattr(pb_cycle, 'recovery_data', '{}')
            if isinstance(recovery_data, str):
                try:
                    recovery_dict = json.loads(recovery_data)
                except json.JSONDecodeError:
                    recovery_dict = {}
            else:
                recovery_dict = recovery_data if recovery_data else {}
            
            # Extract zone data from zone_data JSON field
            zone_data = getattr(pb_cycle, 'zone_data', '{}')
            if isinstance(zone_data, str):
                try:
                    zone_dict = json.loads(zone_data)
                except json.JSONDecodeError:
                    zone_dict = {}
            else:
                zone_dict = zone_data if zone_data else {}
            
            cycle_data['in_recovery_mode'] = bool(recovery_dict.get('in_recovery_mode', False))
            cycle_data['recovery_activated'] = bool(recovery_dict.get('recovery_activated', False))
            cycle_data['recovery_direction'] = recovery_dict.get('recovery_direction', None)
            cycle_data['initial_direction'] = zone_dict.get('initial_direction', cycle_data['direction'])
            cycle_data['recovery_zone_base_price'] = self._safe_float_value(recovery_dict.get('recovery_zone_base_price', 0.0))
            cycle_data['initial_stop_loss_price'] = self._safe_float_value(zone_dict.get('initial_stop_loss_price', 0.0))
            cycle_data['initial_order_open_price'] = self._safe_float_value(zone_dict.get('initial_order_open_price', 0.0))
            cycle_data['initial_order_stop_loss'] = self._safe_float_value(zone_dict.get('initial_order_stop_loss', 0.0))
            
            # Add trailing stop-loss and price tracking fields
            cycle_data['trailing_stop_loss'] = self._safe_float_value(getattr(pb_cycle, 'trailing_stop_loss', 0.0))
            cycle_data['highest_buy_price'] = self._safe_float_value(getattr(pb_cycle, 'highest_buy_price', 0.0))
            cycle_data['lowest_sell_price'] = self._safe_float_value(getattr(pb_cycle, 'lowest_sell_price', 999999.0))
            
            # Add upper and lower bounds from database
            cycle_data['upper_bound'] = self._safe_float_value(getattr(pb_cycle, 'upper_bound', 0.0))
            cycle_data['lower_bound'] = self._safe_float_value(getattr(pb_cycle, 'lower_bound', 0.0))
            
            # Handle cycle_config data - CRITICAL for cycle-specific configuration
            cycle_config = getattr(pb_cycle, 'cycle_config', '{}')
            if isinstance(cycle_config, str):
                try:
                    cycle_config_dict = json.loads(cycle_config)
                    cycle_data['cycle_config'] = cycle_config_dict
                    logger.debug(f"✅ Loaded cycle_config for cycle {cycle_id} with {len(cycle_config_dict)} parameters")
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON in cycle_config for cycle {cycle_id}")
                    cycle_data['cycle_config'] = {}
            else:
                cycle_data['cycle_config'] = cycle_config if cycle_config else {}
            
            # If cycle_config is empty, create a snapshot from current bot config for backward compatibility
            if not cycle_data['cycle_config']:
                cycle_data['cycle_config'] = self._create_cycle_config_snapshot()
                logger.info(f"🔄 Created cycle_config snapshot for existing cycle {cycle_id} during sync")
            
            logger.debug(f"✅ Converted PocketBase cycle {cycle_id} to local format")
            return cycle_data
            
        except Exception as e:
            logger.error(f"❌ Failed to convert PocketBase cycle data: {str(e)}")
            logger.error(traceback.format_exc())
            return {}

    def _sync_cycle_zone_data_from_database(self, cycle, pb_cycle):
        """Sync cycle zone data and bounds from PocketBase database"""
        try:
            # Get zone data from PocketBase
            zone_data = getattr(pb_cycle, 'zone_data', '{}')
            if isinstance(zone_data, str):
                try:
                    zone_dict = json.loads(zone_data)
                except json.JSONDecodeError:
                    zone_dict = {}
            else:
                zone_dict = zone_data if zone_data else {}
            
            # Get upper and lower bounds from database
            upper_bound = self._safe_float_value(getattr(pb_cycle, 'upper_bound', 0.0))
            lower_bound = self._safe_float_value(getattr(pb_cycle, 'lower_bound', 0.0))
            
            # Get trailing stop-loss data
            trailing_stop_loss = self._safe_float_value(getattr(pb_cycle, 'trailing_stop_loss', 0.0))
            highest_buy_price = self._safe_float_value(getattr(pb_cycle, 'highest_buy_price', 0.0))
            lowest_sell_price = self._safe_float_value(getattr(pb_cycle, 'lowest_sell_price', 999999.0))
            
            # Update cycle zone data
            if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                cycle.zone_data = {}
            
            # Sync zone boundaries
            if upper_bound > 0 and lower_bound > 0:
                cycle.zone_data.update({
                    'upper_boundary': upper_bound,
                    'lower_boundary': lower_bound
                })
                logger.info(f"✅ Synced zone boundaries for cycle {cycle.cycle_id}: upper={upper_bound}, lower={lower_bound}")
            
            # Sync trailing stop-loss data
            cycle.trailing_stop_loss = trailing_stop_loss
            cycle.highest_buy_price = highest_buy_price
            cycle.lowest_sell_price = lowest_sell_price
            
            # Update zone data with trailing stop-loss info
            if trailing_stop_loss > 0:
                cycle.zone_data['trailing_stop_loss'] = trailing_stop_loss
                cycle.zone_data['highest_buy_price'] = highest_buy_price
                cycle.zone_data['lowest_sell_price'] = lowest_sell_price
                logger.info(f"✅ Synced trailing stop-loss for cycle {cycle.cycle_id}: TSL={trailing_stop_loss}, HBP={highest_buy_price}, LSP={lowest_sell_price}")
            
            # Ensure zone data has all required fields
            if 'base_price' not in cycle.zone_data:
                cycle.zone_data['base_price'] = cycle.entry_price
            if 'movement_mode' not in cycle.zone_data:
                cycle.zone_data['movement_mode'] = getattr(pb_cycle, 'zone_movement_mode', 'NO_MOVE')
            if 'last_movement' not in cycle.zone_data:
                cycle.zone_data['last_movement'] = None
            
            logger.info(f"✅ Successfully synced zone data for cycle {cycle.cycle_id} from database")
            
        except Exception as e:
            logger.error(f"❌ Error syncing zone data for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {str(e)}")
            logger.error(traceback.format_exc())

    def _initialize_zone_boundaries_for_existing_cycles(self):
        """Initialize zone boundaries for existing cycles that don't have them set"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            current_price = self._get_current_price()
            
            if not current_price:
                logger.warning("⚠️ Cannot initialize zone boundaries: no current price available")
                return
            
            for cycle in active_cycles:
                try:
                    # Check if zone boundaries need to be initialized
                    if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                        cycle.zone_data = {}
                    
                    # Check if upper/lower boundaries are missing or zero
                    upper_boundary = cycle.zone_data.get('upper_boundary', 0.0)
                    lower_boundary = cycle.zone_data.get('lower_boundary', 0.0)
                    
                    if upper_boundary <= 0 or lower_boundary <= 0:
                        # Calculate proper boundaries
                        # self._calculate_proper_boundaries(cycle, current_price)
                        upper= cycle.zone_data.get('upper_boundary', 0.0)
                        lower= cycle.zone_data.get('lower_boundary', 0.0)
                        logger.info(f"✅ Initialized zone boundaries for cycle {cycle.cycle_id}")
                    
                    # Check if trailing stop-loss needs initialization
                    if not hasattr(cycle, 'trailing_stop_loss') or cycle.trailing_stop_loss is None:
                        cycle.trailing_stop_loss = 0.0
                    if not hasattr(cycle, 'highest_buy_price') or cycle.highest_buy_price is None:
                        cycle.highest_buy_price = 0.0
                    if not hasattr(cycle, 'lowest_sell_price') or cycle.lowest_sell_price is None:
                        cycle.lowest_sell_price = 999999.0
                    
                    # Update trailing stop-loss if needed
                    if cycle.trailing_stop_loss == 0.0:
                        self._update_trailing_stop_loss(cycle, current_price)
                        logger.info(f"✅ Initialized trailing stop-loss for cycle {cycle.cycle_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Error initializing zone boundaries for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {str(e)}")
                    continue
            
            logger.info(f"✅ Zone boundaries initialized for {len(active_cycles)} active cycles")
            
        except Exception as e:
            logger.error(f"❌ Error initializing zone boundaries for existing cycles: {str(e)}")
            logger.error(traceback.format_exc())

    def _fix_missing_grid_levels_for_existing_cycles(self):
        """Fix missing grid_level fields for all existing cycles"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            for cycle in active_cycles:
                try:
                    fixed_count = self._fix_missing_grid_levels_in_cycle(cycle)
                    if fixed_count > 0:
                        logger.info(f"✅ Fixed grid_level for {fixed_count} orders in cycle {cycle.cycle_id}")
                except Exception as e:
                    logger.error(f"❌ Error fixing grid_level for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {str(e)}")
                    continue
            
            logger.info(f"✅ Grid level fixes completed for {len(active_cycles)} active cycles")
            
        except Exception as e:
            logger.error(f"❌ Error fixing grid_level for existing cycles: {str(e)}")
            logger.error(traceback.format_exc())

    def _force_refresh_grid_levels_for_all_cycles(self):
        """Force refresh grid levels for all existing cycles by recalculating from order prices"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            total_fixed = 0
            
            for cycle in active_cycles:
                try:
                    fixed_count = self._force_refresh_grid_levels_in_cycle(cycle)
                    if fixed_count > 0:
                        logger.info(f"✅ Force refreshed grid_level for {fixed_count} orders in cycle {cycle.cycle_id}")
                        total_fixed += fixed_count
                except Exception as e:
                    logger.error(f"❌ Error force refreshing grid_level for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {str(e)}")
                    continue
            
            logger.info(f"✅ Force refresh completed: {total_fixed} orders fixed across {len(active_cycles)} active cycles")
            
        except Exception as e:
            logger.error(f"❌ Error force refreshing grid_level for existing cycles: {str(e)}")
            logger.error(traceback.format_exc())

    def _force_refresh_grid_levels_in_cycle(self, cycle):
        """Force refresh grid levels for all orders in a cycle by recalculating from order prices"""
        try:
            fixed_count = 0
            pip_value = self._get_pip_value()
            entry_price = getattr(cycle, 'entry_price', 0.0)
            grid_interval_pips = getattr(cycle, 'grid_interval_pips', self.grid_interval_pips)
            
            if not entry_price or not grid_interval_pips:
                logger.warning(f"⚠️ Cannot refresh grid levels for cycle {cycle.cycle_id}: missing entry_price or grid_interval_pips")
                return 0
            
            for order in getattr(cycle, 'orders', []):
                if order.get('status') == 'active':
                    try:
                        # Recalculate grid level using correct MoveGuard logic
                        price = order.get('price', 0.0)
                        if price > 0:
                            entry_interval_pips = getattr(cycle, 'entry_interval_pips', self.entry_interval_pips)
                            direction = getattr(cycle, 'direction', 'BUY')
                            
                            # Get zone boundaries from cycle
                            zone_data = getattr(cycle, 'zone_data', {})
                            upper_boundary = zone_data.get('upper_boundary', entry_price)
                            lower_boundary = zone_data.get('lower_boundary', entry_price)
                            
                            # Calculate grid level based on direction and zone boundaries
                            if direction == 'BUY':
                                # For BUY: Level 1 starts below lower_boundary - initial_offset
                                grid_start_price = lower_boundary - (entry_interval_pips * pip_value)
                                
                                if float(price) >= lower_boundary:
                                    # Price is within or above zone - Level 0 (entry order)
                                    new_grid_level = 0
                                elif float(price) >= grid_start_price:
                                    # Price is between lower_boundary and grid_start_price - Level 0
                                    new_grid_level = 0
                                else:
                                    # Price is below grid_start_price - calculate grid level
                                    price_diff = grid_start_price - float(price)
                                    pips_diff = price_diff / pip_value
                                    new_grid_level = int(pips_diff / float(grid_interval_pips)) + 1
                                    new_grid_level = max(1, new_grid_level)
                            else:  # SELL
                                # For SELL: Level 1 starts above upper_boundary + initial_offset
                                grid_start_price = upper_boundary + (entry_interval_pips * pip_value)
                                
                                if float(price) <= upper_boundary:
                                    # Price is within or below zone - Level 0 (entry order)
                                    new_grid_level = 0
                                elif float(price) <= grid_start_price:
                                    # Price is between upper_boundary and grid_start_price - Level 0
                                    new_grid_level = 0
                                else:
                                    # Price is above grid_start_price - calculate grid level
                                    price_diff = float(price) - grid_start_price
                                    pips_diff = price_diff / pip_value
                                    new_grid_level = int(pips_diff / float(grid_interval_pips)) + 1
                                    new_grid_level = max(1, new_grid_level)
                            
                            # Update grid level if it changed
                            old_grid_level = order.get('grid_level')
                            if old_grid_level != new_grid_level:
                                order['grid_level'] = new_grid_level
                                
                                # Update order type and flags (preserve existing order_type from MT5 comment if available)
                                current_order_type = order.get('order_type', '')
                                if new_grid_level == 0:
                                    order['is_grid'] = False
                                    order['is_initial'] = True
                                                                    # Only set order_type if not already set from MT5 comment
                                if not current_order_type or current_order_type == 'unknown':
                                    order['order_type'] = 'grid_0'
                                else:
                                    order['is_grid'] = True
                                    order['is_initial'] = False
                                    # Only set order_type if not already set from MT5 comment
                                    if not current_order_type or current_order_type == 'unknown':
                                        if new_grid_level == 1:
                                            order['order_type'] = 'grid_entry'
                                        else:
                                            order['order_type'] = f'grid_level_{new_grid_level}'
                                
                                fixed_count += 1
                                logger.debug(f"📊 Force refreshed order {order.get('order_id')}: grid_level {old_grid_level} → {new_grid_level}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to refresh grid level for order {order.get('order_id')}: {e}")
                        continue
            
            return fixed_count
            
        except Exception as e:
            logger.error(f"❌ Error force refreshing grid levels in cycle: {str(e)}")
            return 0

    def _safe_float_value(self, value):
        """Safely convert value to float for MoveGuard"""
        try:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                # Handle infinity values - convert to 0.0 for database storage
                if value == float('inf') or value == float('-inf'):
                    return 0.0
                return float(value)
            if isinstance(value, str):
                # Handle string representations of infinity
                if value.lower() in ['inf', 'infinity', '-inf', '-infinity']:
                    return 0.0
                return float(value) if value.strip() else 0.0
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    # ==================== EVENT HANDLING ====================

    async def handle_event(self, event):
        """Handle events for MoveGuard strategy"""
        try:
         
            message, content = self._extract_event_data(event)
            logger.info(f"📨 MoveGuard received event: {message}")
            
            return await self._route_event_to_handler(message, content)
            
        except Exception as e:
            logger.error(f"❌ Error handling MoveGuard event: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def _is_event_valid(self, event) -> bool:
        """Validate event for MoveGuard"""
        try:
            # Handle both dictionary and PocketBase Record objects
            if hasattr(event, 'get'):
                # It's a dictionary-like object
                return event and isinstance(event, dict) and 'message' in event
            elif hasattr(event, 'content'):
                # It's a PocketBase Record object
                content = event.content if hasattr(event.content, 'get') else {}
                return isinstance(content, dict) and 'message' in content
            else:
                # Unknown object type
                logger.warning(f"Unknown event object type for validation: {type(event)}")
                return False
        except Exception as e:
            logger.error(f"Error validating event: {e}")
            return False

    def _extract_event_data(self, event):
        """Extract message and content from event"""
        try:
            # Handle both dictionary and PocketBase Record objects
            if hasattr(event, 'get'):
                # It's a dictionary-like object
                message = event.get('message', '')
                content = event.get('content', {})
            elif hasattr(event, 'content'):
                # It's a PocketBase Record object
                content = event.content if hasattr(event.content, 'get') else {}
                message = content.get('message', '') if isinstance(content, dict) else ''
            else:
                # Fallback for unknown object types
                logger.warning(f"Unknown event object type: {type(event)}")
                message = ''
                content = {}
            
            return message, content
            
        except Exception as e:
            logger.error(f"Error extracting event data: {e}")
            return '', {}

    async def _route_event_to_handler(self, message: str, content: dict) -> bool:
        """Route event to appropriate handler for MoveGuard"""
        try:
            if message == "open_order":
                return await self._handle_open_order_event(content)
            elif message == "close_cycle":
                return await self._handle_close_cycle_event(content)
            elif message == "close_order":
                return await self._handle_close_order_event(content)
            else:
                logger.warning(f"⚠️ Unknown event type for MoveGuard: {message}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error routing MoveGuard event: {str(e)}")
            return False

    # ==================== ORDER MANAGEMENT ====================

    async def _handle_open_order_event(self, content: dict) -> bool:
        """Handle open order event for MoveGuard"""
        try:
            logger.info("📈 MoveGuard handling open order event")
            
            # Extract order parameters
            order_params = self._extract_order_parameters(content)
            
            # Get current market prices
            current_prices = self._get_current_market_prices()
            if not current_prices:
                logger.error("❌ Failed to get market prices for MoveGuard order")
                return False
            
            # Place order based on type
            return await self._place_order_by_type(order_params, current_prices)
            
        except Exception as e:
            logger.error(f"❌ Error handling MoveGuard open order event: {str(e)}")
            return False

    def _extract_order_parameters(self, content: dict) -> dict:
        """Extract order parameters for MoveGuard with robust direction mapping.
        Accepts numeric type where 0 = BUY and 1 = SELL.
        """
        # Default values
        direction = str(content.get('direction', '')).upper() if content.get('direction') is not None else ''
        lot_size = float(content.get('lot_size', self.lot_size))
        price = float(content.get('price', 0.0))
        stop_loss = float(content.get('stop_loss', 0.0))
        take_profit = float(content.get('take_profit', 0.0))
        username = content.get('username', 'system')
        user_id = content.get('user_id', '')
        sent_by_admin = content.get('sent_by_admin', False)

        # Prefer numeric type mapping when provided
        raw_type = content.get('type', content.get('order_type'))
        mapped_direction = ''
        if raw_type is not None:
            try:
                # Allow string digits
                if isinstance(raw_type, str) and raw_type.strip().isdigit():
                    raw_type_val = int(raw_type.strip())
                elif isinstance(raw_type, (int, float)):
                    raw_type_val = int(raw_type)
                else:
                    raw_type_val = None
                if raw_type_val is not None:
                    if raw_type_val == 0:
                        mapped_direction = 'BUY'
                    elif raw_type_val == 1:
                        mapped_direction = 'SELL'
                # If not numeric, try textual mapping
                if not mapped_direction and isinstance(raw_type, str):
                    text = raw_type.strip().upper()
                    if text in ('BUY', 'B'):
                        mapped_direction = 'BUY'
                    elif text in ('SELL', 'S'):
                        mapped_direction = 'SELL'
            except Exception:
                mapped_direction = ''

        # Final direction resolution: numeric mapping wins, else provided direction text, else BUY
        final_direction = mapped_direction or (direction if direction in ('BUY', 'SELL') else 'BUY')

        return {
            'direction': final_direction,
            'lot_size': lot_size,
            'price': price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'username': username,
            'user_id': user_id,
            'sent_by_admin': sent_by_admin
        }

    def _get_current_market_prices(self) -> Optional[dict]:
        """Get current market prices for MoveGuard"""
        try:
            bid = self.meta_trader.get_bid(self.symbol)
            ask = self.meta_trader.get_ask(self.symbol)
            if bid and ask:
                return {
                    'bid': bid,
                    'ask': ask,
                    'last': (bid + ask) / 2
                }
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get market prices: {str(e)}")
            return None

    async def _place_order_by_type(self, order_params: dict, current_prices: dict) -> bool:
        """Place order based on type for MoveGuard"""
        try:
            direction = order_params['direction'].upper()
            
            if direction == 'BUY':
                return await self._place_buy_order(order_params, current_prices['ask'])
            elif direction == 'SELL':
                return await self._place_sell_order(order_params, current_prices['bid'])
            elif direction == 'DUAL':
                return await self._place_dual_orders(order_params, current_prices)
            else:
                logger.error(f"❌ Unknown order direction for MoveGuard: {direction}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard order: {str(e)}")
            return False

    async def _place_buy_order(self, order_params: dict, current_ask: float, comment: str = "initial_BUY") -> bool:
        """Place buy order for MoveGuard using unified MT5 order placement"""
        try:
            logger.info(f"📈 MoveGuard placing BUY order at {current_ask}")
            
            # Get initial stop loss configuration for interval cycles
            initial_stop_loss_pips = getattr(self, 'initial_stop_loss_pips', 100.0)
            
            # Use unified MT5 order placement
            success, order_data = MT5OrderUtils.place_buy_order(
                meta_trader=self.meta_trader,
                symbol=self.symbol,
                lot_size=self.lot_size,  # This will use bot config for new cycles
                magic_number=self.bot.magic_number,
                stop_loss_pips=initial_stop_loss_pips,  # ✅ Use initial SL config
                take_profit_pips=0,
                slippage=50, 
                comment=comment
            )
            
            if not success or not order_data:
                logger.error("❌ Failed to place MoveGuard BUY order via MT5")
                return False
            
            # Create cycle with the order data
            cycle_success = self._create_manual_cycle(
                order_data, 'BUY', 
                order_params['username'], 
                order_params['sent_by_admin'], 
                order_params['user_id']
            )
            
            if cycle_success:
                logger.info("✅ MoveGuard BUY order placed and cycle created successfully")
                return True
            else:
                logger.error("❌ Failed to create MoveGuard BUY cycle")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard BUY order: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def _place_sell_order(self, order_params: dict, current_bid: float, comment: str = "initial_SELL") -> bool:
        """Place sell order for MoveGuard using unified MT5 order placement"""
        try:
            logger.info(f"📉 MoveGuard placing SELL order at {current_bid}")
            
            # Get initial stop loss configuration for interval cycles
            initial_stop_loss_pips = getattr(self, 'initial_stop_loss_pips', 100.0)
            
            # Use unified MT5 order placement
            success, order_data = MT5OrderUtils.place_sell_order(
                meta_trader=self.meta_trader,
                symbol=self.symbol,
                lot_size=self.lot_size,
                magic_number=self.bot.magic_number,
                stop_loss_pips=initial_stop_loss_pips,  # ✅ Use initial SL config
                take_profit_pips=0,
                slippage=50,
                comment=comment
            )
            
            if not success or not order_data:
                logger.error("❌ Failed to place MoveGuard SELL order via MT5")
                return False
            
            # Create cycle with the order data
            cycle_success = self._create_manual_cycle(
                order_data, 'SELL', 
                order_params['username'], 
                order_params['sent_by_admin'], 
                order_params['user_id']
            )
            
            if cycle_success:
                logger.info("✅ MoveGuard SELL order placed and cycle created successfully")
                return True
            else:
                logger.error("❌ Failed to create MoveGuard SELL cycle")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard SELL order: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def _place_dual_orders(self, order_params: dict, current_prices: dict) -> bool:
        """Place dual orders for MoveGuard"""
        try:
            logger.info("🔄 MoveGuard placing DUAL orders")
            
            # Place both BUY and SELL orders
            buy_success = await self._place_buy_order(order_params, current_prices['ask'])
            sell_success = await self._place_sell_order(order_params, current_prices['bid'])
            
            return buy_success and sell_success
            
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard DUAL orders: {str(e)}")
            return False

    def _create_order_data(self, direction: str, price: float, current_price: float) -> dict:
        """Create order data for MoveGuard"""
        return {
            'direction': direction,
            'price': price,
            'current_price': current_price,
            'lot_size': self.lot_size,
            'stop_loss_pips': self.initial_stop_loss_pips,
            'take_profit_pips': self.cycle_take_profit_pips,
            'strategy': 'MoveGuard'
        }

    # ==================== CYCLE MANAGEMENT ====================

    def _create_manual_cycle(self, order_data: dict, direction: str, 
                            username: str, sent_by_admin: bool, user_id: str) -> bool:
        """Create manual cycle for MoveGuard"""
        try:
            logger.info(f"🔄 MoveGuard creating manual cycle for {direction}")
            
            # Build cycle data
            cycle_data = self._build_cycle_data(order_data, username, user_id, direction, sent_by_admin)
            
            if cycle_data is None:
                logger.error("❌ Failed to build cycle data for MoveGuard")
                return False
            
            # Create cycle object for MoveGuard
            cycle = MoveGuardCycle(cycle_data, self.meta_trader, self.bot)
            
            # MANUAL CYCLE DUPLICATE CHECK: Check for existing cycles at same price and direction
            cycle_entry_price = getattr(cycle, 'entry_price', None)
            if cycle_entry_price is not None:
                active_cycles = self.multi_cycle_manager.get_all_active_cycles()
                for existing_cycle in active_cycles:
                    existing_entry_price = getattr(existing_cycle, 'entry_price', None)
                    existing_direction = getattr(existing_cycle, 'direction', None)
                    
                    if (existing_entry_price is not None and 
                        existing_direction == direction and
                        abs(existing_entry_price - cycle_entry_price) < 0.00001):  # Exact match
                        
                        logger.warning(f"🚫 MANUAL CYCLE DUPLICATE PREVENTION: Cycle at price {cycle_entry_price} direction {direction} "
                                      f"already exists as cycle {existing_cycle.cycle_id} at price {existing_entry_price}")
                        return False
            
            # Add to multi-cycle manager (which also has duplicate checking)
            if not self.multi_cycle_manager.add_cycle(cycle):
                logger.warning(f"🚫 Failed to add cycle {cycle.cycle_id} to multi-cycle manager (likely duplicate)")
                return False
            
            # Create cycle in database first
            try:
                if hasattr(cycle, '_create_cycle_in_database'):
                    cycle._create_cycle_in_database()
                    logger.info(f"✅ MoveGuard cycle {cycle.cycle_id} created in database")
                else:
                    logger.warning("⚠️ Cycle object doesn't have _create_cycle_in_database method")
            except Exception as e:
                logger.error(f"❌ Error creating cycle in database: {str(e)}")
                # Continue anyway - the cycle is still created locally
            
            logger.info(f"✅ MoveGuard cycle {cycle.cycle_id} created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating MoveGuard cycle: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def _build_cycle_data(self, order_data, username, user_id, direction, sent_by_admin):
        """Build cycle data for MoveGuard"""
        try:
            # Generate unique cycle ID
            cycle_id = f"MG_{int(time.time())}_{direction}_{username}"
            
            # Create cycle-specific configuration snapshot from current bot config
            cycle_config = self._create_cycle_config_snapshot()
            
            # Ensure we have all required fields
            cycle_data = {
                'cycle_id': cycle_id,
                'id': cycle_id,  # Add 'id' field for database compatibility
                'symbol': self.symbol,
                'direction': direction,
                'entry_price': float(order_data.get('price', 0.0)),
                'lot_size': float(order_data.get('volume', self.lot_size)),
                'status': 'active',
                'created_at': datetime.datetime.now().isoformat(),
                'updated_at': datetime.datetime.now().isoformat(),
                'total_volume': float(order_data.get('volume', self.lot_size)),
                'total_profit': 0.0,
                'total_profit_pips': 0.0,
                'username': username,
                'user_id': user_id,
                'sent_by_admin': sent_by_admin,
                'strategy_name': 'MoveGuard',
                'cycle_type': 'MoveGuard',
                'orders': [MT5OrderUtils._convert_to_moveguard_format(order_data, direction)] if order_data else [],
                'active_orders': [MT5OrderUtils._convert_to_moveguard_format(order_data, direction)] if order_data else [],
                'completed_orders': [],
                'is_closed': False,
                'closing_method': None,
                'closed_at': None,
                'recovery_data': {
                    'recovery_orders': [],
                    'recovery_activated': False,
                    'recovery_direction': None
                },
                'grid_data': {
                    'current_level': 0,
                    'grid_direction': direction,
                    'last_grid_price': float(order_data.get('price', 0.0)),
                    'grid_orders': []
                },
                'zone_data': {
                    'base_price': float(order_data.get('price', 0.0)),
                    'upper_boundary': float(order_data.get('price', 0.0)) + (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value()),
                    'lower_boundary': float(order_data.get('price', 0.0)) - (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value()),
                    'movement_mode':  self.zone_movement_mode,
                    'last_movement': None
                },
                # Cycle-specific configuration snapshot
                'cycle_config': cycle_config,
                # MoveGuard-specific configuration (for backward compatibility)
                'grid_interval_pips': float(getattr(self, 'grid_interval_pips', 50.0)),
                'entry_interval_pips': float(getattr(self, 'entry_interval_pips', 10.0)),
                'initial_stop_loss_pips': float(getattr(self, 'initial_stop_loss_pips', 300.0)),
                'cycle_stop_loss_pips': float(getattr(self, 'cycle_stop_loss_pips', 200.0)),
                'recovery_stop_loss_pips': float(getattr(self, 'recovery_stop_loss_pips', 150.0)),
                'cycle_take_profit_pips': float(getattr(self, 'cycle_take_profit_pips', 100.0)),
                'max_trades_per_cycle': int(getattr(self, 'max_trades_per_cycle', 10)),
                'zone_movement_mode': self.zone_movement_mode,
                'recovery_enabled': bool(getattr(self, 'recovery_enabled', True)),
                # Recovery mode fields
                'in_recovery_mode': False,
                'recovery_activated': False,
                'recovery_direction': None,
                'initial_direction': direction,
                'recovery_zone_base_price': 0.0,
                'initial_stop_loss_price': 0.0,
                'initial_order_open_price': float(order_data.get('price', 0.0)),
                'initial_order_stop_loss': 0.0,
                'upper_bound': float(order_data.get('price', 0.0)) + (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value()),
                'lower_bound': float(order_data.get('price', 0.0)) - (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value())
            }
            
            logger.info(f"✅ MoveGuard cycle data built successfully: {cycle_id}")
            return cycle_data
            
        except Exception as e:
            logger.error(f"❌ Error building MoveGuard cycle data: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _create_cycle_config_snapshot(self):
        """Create a snapshot of current strategy configuration for cycle-specific storage"""
        try:
            # Use current strategy configuration values instead of potentially stale self.config
            # This ensures each cycle gets the configuration that was active when it was created
            
            # Create comprehensive configuration snapshot from current strategy state
            cycle_config = {
                # Core sizing - use current strategy values
                'lot_size': float(getattr(self, 'lot_size', 0.01)),
                
                # Entry intervals - use current strategy values
                'entry_interval_pips': float(getattr(self, 'entry_interval_pips', 50.0)),
                'subsequent_entry_interval_pips': float(getattr(self, 'subsequent_entry_interval_pips', 50.0)),
                'grid_interval_pips': float(getattr(self, 'grid_interval_pips', 50.0)),
                
                # Stop losses and take profit - use current strategy values
                'initial_stop_loss_pips': float(getattr(self, 'initial_stop_loss_pips', 100.0)),
                'cycle_stop_loss_pips': float(getattr(self, 'cycle_stop_loss_pips', 100.0)),
                'recovery_stop_loss_pips': float(getattr(self, 'recovery_stop_loss_pips', 200.0)),
                'cycle_take_profit_pips': float(getattr(self, 'cycle_take_profit_pips', 100.0)),
                
                # Recovery spacing - use current strategy values
                'recovery_interval_pips': float(getattr(self, 'recovery_interval_pips', 50.0)),
                'recovery_spacing_pips': float(getattr(self, 'recovery_spacing_pips', 50.0)),
                
                # Zones - use current strategy values
                'zone_movement_mode': getattr(self, 'zone_movement_mode', "Move Both Sides"),
                'zone_threshold_pips': float(getattr(self, 'zone_threshold_pips', 300.0)),
                'zone_move_step_pips': float(getattr(self, 'zone_move_step_pips', 300.0)),
                
                # Multi-cycle limits - use current strategy values
                'max_active_cycles': int(getattr(self, 'max_active_cycles', 3)),
                'max_trades_per_cycle': int(getattr(self, 'max_trades_per_cycle', 50)),
                'max_active_trades_per_cycle': int(getattr(self, 'max_active_trades_per_cycle', 20)),
                
                # Recovery settings - use current strategy values
                'recovery_enabled': bool(getattr(self, 'recovery_enabled', True)),
                
                # Order intervals - use current strategy values
                'order_interval_pips': float(getattr(self, 'order_interval_pips', 50.0)),
                'reversal_threshold_pips': float(getattr(self, 'reversal_threshold_pips', 300.0)),
                
                # Cycle interval configuration - use current strategy values
                'cycle_interval': float(getattr(self, 'cycle_interval', 100.0)),
                'auto_place_cycles': bool(getattr(self, 'auto_place_cycles', True)),
                
                # Symbol - use current strategy value
                'symbol': getattr(self, 'symbol', 'EURUSD'),
                
                # Timestamp for tracking when config was saved
                'config_saved_at': datetime.datetime.now().isoformat(),
                'config_version': '1.0'
            }
            
            logger.info(f"✅ Cycle configuration snapshot created with {len(cycle_config)} parameters from current strategy state")
            logger.debug(f"📋 Cycle config snapshot: lot_size={cycle_config['lot_size']}, grid_interval_pips={cycle_config['grid_interval_pips']}, zone_threshold_pips={cycle_config['zone_threshold_pips']}")
            return cycle_config
            
        except Exception as e:
            logger.error(f"❌ Error creating cycle configuration snapshot: {str(e)}")
            logger.error(traceback.format_exc())
            return {}

    def get_cycle_config_value(self, cycle, config_key, default_value=None):
        """Get configuration value from cycle-specific config, fallback to current strategy config"""
        try:
            # First try to get from cycle-specific configuration
            if hasattr(cycle, 'cycle_config') and cycle.cycle_config:
                cycle_config = cycle.cycle_config
                if isinstance(cycle_config, str):
                    try:
                        cycle_config = json.loads(cycle_config)
                    except json.JSONDecodeError:
                        cycle_config = {}
                
                if config_key in cycle_config:
                    value = cycle_config[config_key]
                    logger.debug(f"📋 Using cycle-specific config for {config_key}: {value}")
                    return value
            
            # Fallback to current strategy configuration values instead of potentially stale self.config
            # Map config keys to strategy attributes
            strategy_attr_map = {
                'lot_size': 'lot_size',
                'entry_interval_pips': 'entry_interval_pips',
                'subsequent_entry_interval_pips': 'subsequent_entry_interval_pips',
                'grid_interval_pips': 'grid_interval_pips',
                'initial_stop_loss_pips': 'initial_stop_loss_pips',
                'cycle_stop_loss_pips': 'cycle_stop_loss_pips',
                'recovery_stop_loss_pips': 'recovery_stop_loss_pips',
                'cycle_take_profit_pips': 'cycle_take_profit_pips',
                'recovery_interval_pips': 'recovery_interval_pips',
                'recovery_spacing_pips': 'recovery_spacing_pips',
                'zone_movement_mode': 'zone_movement_mode',
                'zone_threshold_pips': 'zone_threshold_pips',
                'zone_move_step_pips': 'zone_move_step_pips',
                'max_active_cycles': 'max_active_cycles',
                'max_trades_per_cycle': 'max_trades_per_cycle',
                'max_active_trades_per_cycle': 'max_active_trades_per_cycle',
                'recovery_enabled': 'recovery_enabled',
                'order_interval_pips': 'order_interval_pips',
                'reversal_threshold_pips': 'reversal_threshold_pips',
                'cycle_interval': 'cycle_interval',
                'auto_place_cycles': 'auto_place_cycles',
                'symbol': 'symbol'
            }
            
            # Try to get from current strategy state
            if config_key in strategy_attr_map:
                strategy_attr = strategy_attr_map[config_key]
                if hasattr(self, strategy_attr):
                    value = getattr(self, strategy_attr)
                    logger.debug(f"📋 Using current strategy config for {config_key}: {value}")
                    return value
            
            # Final fallback to default value
            logger.debug(f"📋 Using default value for {config_key}: {default_value}")
            return default_value
            
        except Exception as e:
            logger.error(f"❌ Error getting cycle config value for {config_key}: {str(e)}")
            return default_value

    def get_cycle_zone_threshold_pips(self, cycle):
        """Get zone_threshold_pips from cycle-specific config"""
        return self.get_cycle_config_value(cycle, 'zone_threshold_pips', 50.0)

    def get_cycle_entry_interval_pips(self, cycle):
        """Get entry_interval_pips from cycle-specific config"""
        return self.get_cycle_config_value(cycle, 'entry_interval_pips', 50.0)

    def get_cycle_subsequent_entry_interval_pips(self, cycle):
        """Get subsequent_entry_interval_pips from cycle-specific config"""
        return self.get_cycle_config_value(cycle, 'subsequent_entry_interval_pips', 50.0)

    def update_configs(self, config):
        """
        Update the MoveGuard strategy configuration with new settings.
        This ensures that new cycles will use the updated configuration.
        
        Parameters:
        config (dict): The new configuration settings for the strategy.
        """
        try:
            logger.info("🔄 Updating MoveGuard strategy configuration...")
            
            # Update the config reference
            self.config = config
            
            # Re-initialize strategy configuration with new values
            self._initialize_strategy_configuration(config)
            
            logger.info("✅ MoveGuard strategy configuration updated successfully")
            logger.debug(f"📋 Updated config: lot_size={self.lot_size}, grid_interval_pips={self.grid_interval_pips}, zone_threshold_pips={self.zone_threshold_pips}")
            
        except Exception as e:
            logger.error(f"❌ Error updating MoveGuard strategy configuration: {str(e)}")
            logger.error(traceback.format_exc())

    # ==================== STRATEGY EXECUTION ====================

    def start_strategy(self):
        """Start the MoveGuard strategy"""
        try:
            logger.info("🚀 Starting MoveGuard Strategy...")
            
            if not self.is_initialized:
                self.initialize()
            
            self.is_running = True
            
            # Start monitoring in background thread
            def monitoring_wrapper():
                asyncio.run(self._monitoring_loop())
            
            self.monitoring_thread = threading.Thread(target=monitoring_wrapper, daemon=True)
            self.monitoring_thread.start()
            
            logger.info("✅ MoveGuard Strategy started successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to start MoveGuard Strategy: {str(e)}")

    def stop_strategy(self):
        """Stop the MoveGuard strategy"""
        try:
            logger.info("🛑 Stopping MoveGuard Strategy...")
            
            self.is_running = False
            
            if hasattr(self, 'monitoring_thread') and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=5)
            
            logger.info("✅ MoveGuard Strategy stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error stopping MoveGuard Strategy: {str(e)}")

    async def _monitoring_loop(self):
        """Main monitoring loop for MoveGuard"""
        try:
            logger.info("🔄 MoveGuard monitoring loop started")
            
            order_tracking_counter = 0
            
            while self.is_running:
                try:
                    # Get market data
                    market_data = self._get_market_data()
                    if not market_data:
                        await asyncio.sleep(1)
                        continue
                    
                    # Process strategy logic
                    await self._process_strategy_logic(market_data)
                    
                    # Update active cycles
                    self._update_active_cycles_sync()
                    
                    # Track order status every 5 seconds
                    order_tracking_counter += 1
                    if order_tracking_counter >= 5:
                        self._track_and_update_order_status()
                        order_tracking_counter = 0
                    
                    # Sleep for monitoring interval
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Error in MoveGuard monitoring loop: {str(e)}")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error(f"❌ Fatal error in MoveGuard monitoring loop: {str(e)}")

    def _update_active_cycles_sync(self):
        """Update active cycles for MoveGuard"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            for cycle in active_cycles:
                try:
                    # Update cycle statistics
                    current_price = self._get_current_price()
                    if current_price:
                        cycle.total_profit_pips = self._calculate_cycle_total_profit_pips(cycle, current_price)
                    
                    # Update database - call synchronously since the method is not async
                    try:
                        self._update_cycle_in_database(cycle)
                    except Exception as e:
                        logger.error(f"❌ Error updating cycle in database: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"❌ Error updating cycle {cycle.cycle_id}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error updating active cycles: {str(e)}")

    async def _process_strategy_logic(self, market_data: dict):
        """Process MoveGuard strategy logic"""
        try:
            current_price = market_data.get('price', 0.0)
            if not current_price:
                return
            
            # Check if market is open (skip processing if market is closed)
            if not self._is_market_open():
                logger.debug("🕐 Market is closed, skipping strategy processing")
                return
            
            # Check if price has moved significantly (skip processing if no significant movement)
            if not self._has_price_moved(current_price):
                logger.debug(f"📊 Price hasn't moved significantly (threshold: {self.price_movement_threshold}), skipping strategy processing")
                return
            
            # Get active cycles
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            # Filter cycles that need processing (smart filtering)
            cycles_to_process = []
            for cycle in active_cycles:
                if self._should_process_cycle(cycle):
                    cycles_to_process.append(cycle)
            
            if not cycles_to_process:
                logger.debug("📊 No cycles need processing at this time")
                # Still check for interval-based cycle creation even if no cycles to process
                await self._check_cycle_intervals(current_price)
                return
            
            logger.debug(f"🔄 Processing {len(cycles_to_process)} out of {len(active_cycles)} active cycles")
            
            # Update filtered cycles with current profit data from MetaTrader
            self._update_cycles_profit_from_mt5(cycles_to_process)
            
            # Process batch updates if needed
            self._process_batch_updates()
            
            # Update database with latest profit data (throttled)
            for cycle in cycles_to_process:
                try:
                    self._update_cycle_in_database(cycle)
                except Exception as e:
                    logger.error(f"❌ Error updating cycle {cycle.cycle_id} in database after profit update: {str(e)}")
            
            # Log total active profit for monitoring
            total_profit = self.get_total_active_profit_from_mt5()
            if total_profit != 0:
                logger.info(f"💰 Total active profit: ${total_profit:.2f}")
            
            # Fix any incorrectly closed orders and order types
            for cycle in active_cycles:
                self._fix_incorrectly_closed_orders(cycle)
                self._fix_order_types_in_cycle(cycle)
            
            # Process grid logic
            self._process_grid_logic(current_price, market_data, active_cycles)
            
            # Process zone logic
            # self._process_zone_logic(current_price, market_data, active_cycles)
            
            # Process recovery logic
            # self._process_recovery_logic(current_price, market_data)
            
            # Check take profit conditions
            self._check_take_profit_conditions(current_price, active_cycles)
            
            # Check for interval-based cycle creation
            await self._check_cycle_intervals(current_price)
            
            # Clean up active cycle levels for closed cycles
            self._cleanup_cycle_levels()
            
        except Exception as e:
            logger.error(f"❌ Error processing MoveGuard strategy logic: {str(e)}")

    def _process_grid_logic(self, current_price: float, market_data: dict, active_cycles: List):
        """Process grid logic: boundary-based activation and closure"""
        try:
            for cycle in active_cycles:
                if cycle.status != 'active':
                    continue

                # Ensure order types are correctly set from MT5 comments before processing
                self._ensure_order_types_from_mt5_comments(cycle)

                # Initialize boundary tracking
                if not hasattr(cycle, 'was_above_upper'):
                    cycle.was_above_upper = False
                if not hasattr(cycle, 'was_below_lower'):
                    cycle.was_below_lower = False
                if not hasattr(cycle, 'highest_buy_price'):
                    cycle.highest_buy_price = 0.0
                if not hasattr(cycle, 'lowest_sell_price'):
                    cycle.lowest_sell_price = float('inf')

                # Calculate proper boundaries according to MoveGuard rules
                # upper, lower = self._calculate_proper_boundaries(cycle, current_price)
                upper= cycle.zone_data.get('upper_boundary', 0.0)
                lower= cycle.zone_data.get('lower_boundary', 0.0)
                if upper == 0.0 or lower == 0.0:
                    upper, lower = self._calculate_proper_boundaries(cycle, current_price)
                pip_value = self._get_pip_value()
                entry_interval_pips = self.get_cycle_entry_interval_pips(cycle)
                initial_offset = entry_interval_pips * pip_value

                active_order_count = len([o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active'])
                
                # Get grid orders safely using helper method
                grid_orders = self._get_grid_orders_safely(cycle)
                active_grid_order_count = len([o for o in grid_orders if o.get('status') == 'active'])
                
                # Check trailing stop-loss first (for both BUY and SELL cycles)
                if active_order_count > 0 and active_grid_order_count > 0:
                    # Log trailing stop-loss status for debugging
                    self._log_trailing_stop_loss_status(cycle, current_price)
                    
                    if self._check_trailing_stop_loss(cycle, current_price):
                        self._handle_trailing_stop_loss_trigger(cycle, current_price)
                        continue
             

                # Initial order placement: only when price crosses boundaries by entry_interval_pips
                if active_order_count == 0:
                    if current_price >= (upper + initial_offset):
                        cycle.direction = 'BUY'
                        cycle.was_above_upper = True
                        # Calculate grid start price for BUY orders
                        grid_start_price = upper + (entry_interval_pips * pip_value)
                        logger.info(f"🎯 MoveGuard placing first BUY order - price {current_price} >= upper+offset {upper + initial_offset}, placing at grid_start_price {grid_start_price}")
                        self._place_initial_order(cycle, 'BUY', grid_start_price)
                        # Use cycle-specific zone_threshold_pips from cycle_config
                        cycle_zone_threshold_pips = cycle.cycle_config.get('zone_threshold_pips', 50.0) if hasattr(cycle, 'cycle_config') and cycle.cycle_config else 50.0
                        cycle.lower_bound = upper - (cycle_zone_threshold_pips * pip_value)
                        lower = cycle.lower_bound
                        #update zone data
                        cycle.zone_data['upper_boundary'] = upper
                        cycle.zone_data['lower_boundary'] = lower
                        continue
                    elif current_price <= (lower - initial_offset):
                        cycle.direction = 'SELL'
                        cycle.was_below_lower = True
                        # Calculate grid start price for SELL orders
                        grid_start_price = lower - (entry_interval_pips * pip_value)
                        logger.info(f"🎯 MoveGuard placing first SELL order - price {current_price} <= lower-offset {lower - initial_offset}, placing at grid_start_price {grid_start_price}")
                        self._place_initial_order(cycle, 'SELL', grid_start_price)
                        # Use cycle-specific zone_threshold_pips from cycle_config
                        cycle_zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
                        cycle.upper_bound = lower + (cycle_zone_threshold_pips * pip_value)
                        upper = cycle.upper_bound
                        #update zone data   
                        cycle.zone_data['upper_boundary'] = upper
                        cycle.zone_data['lower_boundary'] = lower
                        continue

                # Subsequent grid orders: price-based grid placement
                if active_order_count > 0:
                    # Calculate grid level and check if price has moved enough to place new order
                    grid_level = self._calculate_grid_level(cycle, current_price)
                    
                    # Get grid parameters
                    pip_value = self._get_pip_value()
                    grid_interval_pips = self.get_cycle_config_value(cycle, 'grid_interval_pips', self.grid_interval_pips)
                    entry_interval_pips = self.get_cycle_entry_interval_pips(cycle)
                    
                    # Calculate grid start price and target price for this level
                    if cycle.direction == 'BUY':
                        # For BUY: grid starts above upper boundary
                        grid_start_price = upper + (entry_interval_pips * pip_value)
                        target_price = grid_start_price + (grid_interval_pips * (grid_level) * pip_value)
                        
                        # Place order if price has reached or exceeded the target
                        if current_price >= target_price:
                            logger.info(f"📈 BUY Grid Level {grid_level}: Price {current_price:.5f} >= Target {target_price:.5f} (Grid Start: {grid_start_price:.5f}, Interval: {grid_interval_pips} pips)")
                            self._place_grid_buy_order(cycle, current_price, grid_level)
                            cycle.highest_buy_price = max(cycle.highest_buy_price, current_price)
                            # Update trailing stop-loss after placing new buy order
                            cycle_zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
                            cycle.trailing_stop_loss = cycle.highest_buy_price - (cycle_zone_threshold_pips * pip_value)
                            cycle.trailing_stop_loss = max(cycle.trailing_stop_loss, upper)
                            continue
                            
                    elif cycle.direction == 'SELL':
                        # For SELL: grid starts below lower boundary
                        grid_start_price = lower - (entry_interval_pips * pip_value)
                        target_price = grid_start_price - (grid_interval_pips * (grid_level) * pip_value)
                        
                        # Place order if price has reached or fallen below the target
                        if current_price <= target_price:
                            logger.info(f"📉 SELL Grid Level {grid_level}: Price {current_price:.5f} <= Target {target_price:.5f} (Grid Start: {grid_start_price:.5f}, Interval: {grid_interval_pips} pips)")
                            self._place_grid_sell_order(cycle, current_price, grid_level)
                            cycle.lowest_sell_price = min(cycle.lowest_sell_price, current_price)
                            # Update trailing stop-loss after placing new sell order
                            cycle_zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
                            cycle.trailing_stop_loss = cycle.lowest_sell_price + (cycle_zone_threshold_pips * pip_value)
                            cycle.trailing_stop_loss = min(cycle.trailing_stop_loss, lower)
                            continue
                    
                # Enforce initial order SL logic without closing cycle
                self._check_and_close_initial_order(cycle, current_price)

        except Exception as e:
            logger.error(f"❌ Error processing grid logic: {str(e)}")
            logger.error(traceback.format_exc())

    def _place_initial_order(self, cycle, direction: str, order_price: float) -> bool:
        """Place the first order (grid_0) at the calculated grid start price with initial SL only."""
        try:
            pip_value = self._get_pip_value()
            sl_price = 0.0
            tp_price = 0.0
            # Get cycle-specific configuration values
            lot_size = self.get_cycle_config_value(cycle, 'lot_size', self.lot_size)
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            max_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_trades_per_cycle', self.max_trades_per_cycle)
            max_active_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_active_trades_per_cycle', self.max_active_trades_per_cycle)
            
            # Check total trades limit (active + closed orders)
            total_orders = len(cycle.orders) if hasattr(cycle, 'orders') else 0
            if total_orders >= max_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max total trades ({max_trades_per_cycle}) - cannot place initial order")
                return False
            
            # Check active trades limit (active orders only)
            active_orders = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
            if len(active_orders) >= max_active_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max active trades ({max_active_trades_per_cycle}) - cannot place initial order")
                return False
            
            if direction == 'BUY':
                if initial_stop_loss_pips > 0:
                    sl_price = round(order_price - (initial_stop_loss_pips * pip_value), 2)
                result = self.meta_trader.place_buy_order(
                    symbol=self.symbol,
                    volume=lot_size,
                    price=order_price,
                    stop_loss=sl_price,
                    take_profit=0.0,
                    comment="MoveGuard_Grid_0"
                )
                order_direction = 'BUY'
            else:
                if initial_stop_loss_pips > 0:
                    sl_price = round(order_price + (initial_stop_loss_pips * pip_value), 2)
                result = self.meta_trader.place_sell_order(
                    symbol=self.symbol,
                    volume=lot_size,
                    price=order_price,
                    stop_loss=sl_price,
                    take_profit=0.0,
                    comment="MoveGuard_Grid_0"
                )
                order_direction = 'SELL'

            if result and isinstance(result, dict) and 'order' in result:
                # Update cycle direction to match the order being placed
                cycle.direction = order_direction
                logger.info(f"🔄 Updated cycle {cycle.cycle_id} direction to {order_direction}")
                
                order_info = {
                    'order_id': result['order'].get('ticket'),
                    'ticket': result['order'].get('ticket'),
                    'direction': order_direction,
                    'price': order_price,
                    'lot_size': lot_size,
                    'is_initial': True,
                    'order_type': 'grid_0',
                    'status': 'active',
                    'placed_at': datetime.datetime.now().isoformat(),
                    'profit': 0.0,
                    'profit_pips': 0.0,
                    'last_profit_update': datetime.datetime.now().isoformat(),
                    'grid_level': 0,
                    'is_grid': True
                }
                if hasattr(cycle, 'orders'):
                    cycle.orders.append(order_info)
                else:
                    cycle.orders = [order_info]
                # Track active orders list
                if hasattr(cycle, 'active_orders'):
                    cycle.active_orders.append(order_info)
                else:
                    cycle.active_orders = [order_info]
                # Ensure grid data exists (grid_0 order is part of the grid)
                if not hasattr(cycle, 'grid_data') or not isinstance(cycle.grid_data, dict):
                    cycle.grid_data = {
                        'current_level': 0,
                        'grid_direction': direction,
                        'last_grid_price': order_price,
                        'grid_orders': []
                    }
                # Add grid_0 order to grid_orders list since it's part of the grid system
                cycle.grid_data['grid_orders'].append(order_info)
                
                # Initialize trailing stop-loss for both BUY and SELL orders
                self._update_trailing_stop_loss(cycle, order_price)
                
                return True
            else:
                logger.error("❌ Failed to place MoveGuard initial order")
                return False
        except Exception as e:
            logger.error(f"❌ Error placing initial order: {e}")
            return False


    def _check_and_close_initial_order(self, cycle, current_price: float):
        """Close the cycle entry order if price hits its implicit SL threshold; keep cycle open."""
        try:
            # Get cycle-specific configuration values
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            if initial_stop_loss_pips <= 0:
                return
            pip_value = self._get_pip_value()
            # Find active cycle entry order (marked as is_initial=True and is_grid=False)
            initial = None
            for o in getattr(cycle, 'orders', []):
                if o.get('status') == 'active' and o.get('is_initial', False) and not o.get('is_grid', False):
                    initial = o
                    break
            if not initial:
                return
            entry = initial.get('price', 0.0)
            direction = initial.get('direction', 'BUY')
            threshold_pips = initial_stop_loss_pips
            hit = False
            if direction == 'BUY':
                sl_price = entry - (threshold_pips * pip_value)
                if current_price <= sl_price:
                    hit = True
            else:  # SELL
                sl_price = entry + (threshold_pips * pip_value)
                if current_price >= sl_price:
                    hit = True
            if hit:

                if self._close_order(initial):
                    initial['status'] = 'closed'
                    initial['closed_at'] = datetime.datetime.now().isoformat()
                    logger.info(f"Closed cycle entry order at SL threshold for cycle {cycle.cycle_id}")
        except Exception as e:
            logger.error(f"Error in _check_and_close_initial_order: {e}")

    def _process_zone_logic(self, current_price: float, market_data: dict, active_cycles: List):
        """Process zone logic for MoveGuard"""
        try:
            for cycle in active_cycles:
                if cycle.status != 'active':
                    continue
                
                # Check zone movement conditions
                zone_movement = self._check_zone_movement(cycle, current_price)
                
                if zone_movement['should_move']:
                    self._move_zone(cycle, zone_movement['direction'], current_price)
                    
        except Exception as e:
            logger.error(f"❌ Error processing zone logic: {str(e)}")

    def _process_recovery_logic(self, current_price: float, market_data: dict):
        """Process recovery logic for MoveGuard"""
        try:
            if not self.recovery_enabled:
                return
            
            # Check recovery conditions for all cycles
            for cycle_id, recovery_data in self.recovery_cycles.items():
                self._check_recovery_conditions(cycle_id, recovery_data, current_price)
                
        except Exception as e:
            logger.error(f"❌ Error processing recovery logic: {str(e)}")

    # ==================== UTILITY METHODS ====================

    def _get_market_data(self) -> Optional[dict]:
        """Get market data for MoveGuard"""
        try:
            bid = self.meta_trader.get_bid(self.symbol)
            ask = self.meta_trader.get_ask(self.symbol)
            if bid and ask:
                price = (bid + ask) / 2
                return {
                    'price': price,
                    'bid': bid,
                    'ask': ask,
                    'last': price,
                    'time': datetime.datetime.now()
                }
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get market data: {str(e)}")
            return None

    def _get_current_price(self) -> Optional[float]:
        """Get current price for MoveGuard"""
        try:
            bid = self.meta_trader.get_bid(self.symbol)
            ask = self.meta_trader.get_ask(self.symbol)
            if bid and ask:
                return (bid + ask) / 2
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get current price: {str(e)}")
            return None

    def _is_market_open(self) -> bool:
        """Check if market is currently open"""
        try:
            if not self.market_hours_enabled:
                return True  # If market hours checking is disabled, always return True
            
            # Get current time
            current_time = datetime.datetime.now()
            current_hour = current_time.hour
            current_minute = current_time.minute
            current_weekday = current_time.weekday()  # 0=Monday, 6=Sunday
            
            # Forex market is typically closed on weekends (Saturday=5, Sunday=6)
            if current_weekday >= 5:  # Saturday or Sunday
                return False
            
            # Forex market is typically closed from Friday 22:00 to Sunday 22:00 (GMT)
            # This is a simplified check - you might want to make this more sophisticated
            if current_weekday == 4 and current_hour >= 22:  # Friday after 22:00
                return False
            
            # Market is generally open Monday-Friday
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking market hours: {str(e)}")
            return True  # Default to open if there's an error

    def _has_price_moved(self, current_price: float) -> bool:
        """Check if price has moved significantly enough to trigger updates"""
        try:
            if self.last_price is None:
                self.last_price = current_price
                return True  # First price update, always process
            
            price_diff = abs(current_price - self.last_price)
            if price_diff >= self.price_movement_threshold:
                self.last_price = current_price
                self.last_price_update_time = datetime.datetime.now().timestamp()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking price movement: {str(e)}")
            return True  # Default to process if there's an error

    def _get_cached_data(self, key: str, default=None):
        """Get data from cache with TTL check"""
        try:
            if key in self.cache:
                data, timestamp = self.cache[key]
                if datetime.datetime.now().timestamp() - timestamp < self.cache_ttl:
                    return data
                else:
                    # Cache expired, remove it
                    del self.cache[key]
            return default
        except Exception as e:
            logger.error(f"❌ Error getting cached data: {str(e)}")
            return default

    def _set_cached_data(self, key: str, data):
        """Set data in cache with timestamp"""
        try:
            self.cache[key] = (data, datetime.datetime.now().timestamp())
        except Exception as e:
            logger.error(f"❌ Error setting cached data: {str(e)}")

    def _should_process_cycle(self, cycle) -> bool:
        """Check if cycle should be processed based on throttling"""
        try:
            if not self.optimization_enabled:
                return True  # Skip throttling if optimization is disabled
            
            cycle_id = getattr(cycle, 'cycle_id', 'unknown')
            current_time = datetime.datetime.now().timestamp()
            last_process_time = self.processing_throttle.get(cycle_id, 0)
            
            if current_time - last_process_time >= self.cycle_process_interval:
                self.processing_throttle[cycle_id] = current_time
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking cycle processing: {str(e)}")
            return True  # Default to process if there's an error

    def _get_pip_value(self) -> float:
        """Get pip value for MoveGuard"""
        try:
            # Get symbol point value from MetaTrader
            symbol_info = self.meta_trader.get_symbol_info(self.symbol)
            if symbol_info and hasattr(symbol_info, 'point'):
                return float(symbol_info.point)*10
           
        except Exception as e:
            logger.error(f"❌ Failed to get pip value: {str(e)}")
            return 0.0001

    def set_entry_price(self, price: float):
        """Set entry price for MoveGuard"""
        self.last_grid_price = price
        logger.info(f"📊 MoveGuard entry price set to {price}")

    # ==================== BATCH UPDATE SYSTEM ====================
    
    def _add_to_batch_queue(self, cycle, use_snapshot: bool = False, snapshot: dict = None):
        """Add cycle to batch update queue"""
        try:
            cycle_id = getattr(cycle, 'cycle_id', 'unknown')
            # Check if cycle is already in queue
            for item in self.batch_update_queue:
                if item.get('cycle_id') == cycle_id:
                    # Update existing entry
                    item['cycle'] = cycle
                    item['use_snapshot'] = use_snapshot
                    item['snapshot'] = snapshot
                    item['timestamp'] = datetime.datetime.now().timestamp()
                    return
            
            # Add new entry to queue
            self.batch_update_queue.append({
                'cycle_id': cycle_id,
                'cycle': cycle,
                'use_snapshot': use_snapshot,
                'snapshot': snapshot,
                'timestamp': datetime.datetime.now().timestamp()
            })
            
        except Exception as e:
            logger.error(f"❌ Error adding cycle to batch queue: {str(e)}")

    def _process_batch_updates(self, force: bool = False):
        """Process all queued batch updates"""
        try:
            if not self.batch_update_queue:
                return
            
            current_time = datetime.datetime.now().timestamp()
            
            # Check if it's time to process batch updates (unless forced)
            if not force and current_time - self.last_batch_update_time < self.batch_update_interval:
                return
            
            logger.info(f"🔄 Processing {len(self.batch_update_queue)} batch database updates")
            
            # Process all queued updates
            successful_updates = 0
            failed_updates = 0
            
            for item in self.batch_update_queue:
                try:
                    cycle = item['cycle']
                    use_snapshot = item['use_snapshot']
                    snapshot = item['snapshot']
                    
                    # Update cycle statistics before database update
                    self._update_cycle_statistics_with_profit(cycle)
                    
                    cycle_data = self._prepare_cycle_data_for_database(cycle, use_snapshot, snapshot)
                    
                    if self._validate_cycle_data_before_update(cycle_data):
                        success = self.client.update_MG_cycle_by_id(cycle.cycle_id, cycle_data)
                        if success:
                            successful_updates += 1
                            cycle._last_db_update_time = current_time
                        else:
                            failed_updates += 1
                    else:
                        failed_updates += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error processing batch update for cycle {item.get('cycle_id', 'unknown')}: {str(e)}")
                    failed_updates += 1
            
            logger.info(f"✅ Batch update completed: {successful_updates} successful, {failed_updates} failed")
            
            # Clear the queue
            self.batch_update_queue.clear()
            self.last_batch_update_time = current_time
            
        except Exception as e:
            logger.error(f"❌ Error processing batch updates: {str(e)}")

    # ==================== DATABASE OPERATIONS ====================

    def _update_cycle_in_database(self, cycle, use_snapshot: bool = False, snapshot: dict = None, force_update: bool = False):
        """Update cycle in database for MoveGuard with throttling and batching"""
        try:
            # Throttle database updates to reduce load (unless forced or cycle is closing)
            cycle_is_closing = getattr(cycle, 'is_closed', False) or getattr(cycle, 'status', '') == 'closed'
            
            if not force_update and not cycle_is_closing and self.optimization_enabled:
                current_time = datetime.datetime.now().timestamp()
                last_update = getattr(cycle, '_last_db_update_time', 0)
                
                if current_time - last_update < self.database_update_interval:
                    # Add to batch queue instead of skipping
                    self._add_to_batch_queue(cycle, use_snapshot, snapshot)
                    logger.debug(f"⏱️ Added cycle {cycle.cycle_id} to batch queue (last update: {current_time - last_update:.1f}s ago)")
                    return True  # Skip immediate update but queue for batch
            
            # Update cycle statistics before database update
            self._update_cycle_statistics_with_profit(cycle)
            
            cycle_data = self._prepare_cycle_data_for_database(cycle, use_snapshot, snapshot)
            
            if not self._validate_cycle_data_before_update(cycle_data):
                logger.error(f"❌ Invalid cycle data for MoveGuard cycle {cycle.cycle_id}")
                return False
            
            # First, try to update the cycle
            try:
                success = self.client.update_MG_cycle_by_id(cycle.cycle_id, cycle_data)
                
                if success:
                    logger.debug(f"✅ MoveGuard cycle {cycle.cycle_id} updated in database")
                    # Update the last database update timestamp
                    cycle._last_db_update_time = datetime.datetime.now().timestamp()
                    return True
                else:
                    logger.warning(f"⚠️ Failed to update MoveGuard cycle {cycle.cycle_id} - cycle might not exist")
                    
            except Exception as update_error:
                logger.warning(f"⚠️ Update failed for cycle {cycle.cycle_id}: {str(update_error)}")
            
            # If update failed, try to create the cycle
            try:
                logger.info(f"🔄 Attempting to create MoveGuard cycle {cycle.cycle_id} in database")
                
                # Prepare creation data
                creation_data = cycle_data.copy()
                creation_data['cycle_id'] = cycle.cycle_id
                creation_data['bot'] = str(self.bot.id) if hasattr(self.bot, 'id') else None
                creation_data['account'] = str(getattr(self.bot.account, 'id', None)) if hasattr(self.bot, 'account') else None
                
                # Try to create the cycle
                logger.info(f"🔄 Creating MoveGuard cycle {cycle.cycle_id} in database with data: {creation_data}")
                result = self.client.create_MG_cycle(creation_data)
                
                if result and hasattr(result, 'id'):
                    logger.info(f"✅ MoveGuard cycle {cycle.cycle_id} created in database with ID: {result.id}")
                    return True
                else:
                    logger.error(f"❌ Failed to create MoveGuard cycle {cycle.cycle_id} in database - No result returned")
                    logger.error(f"Creation data: {creation_data}")
                    return False
                    
            except Exception as create_error:
                logger.error(f"❌ Error creating MoveGuard cycle in database: {str(create_error)}")
                logger.error(f"Creation data that failed: {creation_data}")
                logger.error(f"Error details: {traceback.format_exc()}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating MoveGuard cycle in database: {str(e)}")
            return False

    def _prepare_cycle_data_for_database(self, cycle, use_snapshot: bool = False, snapshot: dict = None):
        """Prepare cycle data for database update for MoveGuard"""
        try:
            def get_value(field_name, default=None):
                if use_snapshot and snapshot:
                    return snapshot.get(field_name, default)
                else:
                    return getattr(cycle, field_name, default)
            
            # Get grid_data safely - it might not exist on the cycle object
            grid_data = {}
            if hasattr(cycle, 'grid_data'):
                grid_data = get_value('grid_data', {})
            else:
                # Create default grid_data structure if it doesn't exist
                grid_data = {
                    'current_level': 0,
                    'grid_direction': get_value('direction', 'BUY'),
                    'last_grid_price': get_value('entry_price', 0.0),
                    'grid_orders': []
                }

            # Get zone_data safely and compute bounds
            zone_data_val = {}
            if hasattr(cycle, 'zone_data'):
                zone_data_val = get_value('zone_data', {})
            if not zone_data_val:
                pip_value = self._get_pip_value()
                base = self._safe_float_value(get_value('entry_price'))
                zone_data_val = {
                    'base_price': base,
                    'upper_boundary': base + (self.get_cycle_zone_threshold_pips(cycle) * pip_value),
                    'lower_boundary': base - (self.get_cycle_zone_threshold_pips(cycle) * pip_value),
                    'movement_mode': getattr(self, 'zone_movement_mode', 'Move Both Sides'),
                    'last_movement': None
                }
            upper_bound_val = self._safe_float_value(zone_data_val.get('upper_boundary', 0.0))
            lower_bound_val = self._safe_float_value(zone_data_val.get('lower_boundary', 0.0))
            
            # Ensure we have the latest profit and volume calculations
            # Force update cycle statistics to get accurate profit and volume data
            self._update_cycle_statistics_with_profit(cycle)

            # Get cycle_config safely - it might not exist on the cycle object
            cycle_config = get_value('cycle_config', {})
            if not cycle_config:
                # If cycle_config doesn't exist, create a snapshot from current bot config
                cycle_config = self._create_cycle_config_snapshot()
                logger.info(f"🔄 Created cycle_config snapshot for cycle {cycle.cycle_id} during database update")

            cycle_data = {
                'id': cycle.cycle_id,
                'symbol': cycle.symbol,
                'direction': cycle.direction,
                'entry_price': self._safe_float_value(cycle.entry_price),
                'lot_size': self._safe_float_value(cycle.lot_size),
                'status': cycle.status,
                'total_volume': self._safe_float_value(cycle.total_volume),
                'total_profit': self._safe_float_value(cycle.total_profit),
                'total_profit_pips': self._safe_float_value(getattr(cycle, 'total_profit_pips', 0.0)),
                'total_profit_dollars': self._safe_float_value(getattr(cycle, 'total_profit_dollars', 0.0)),
                'cycle_type': 'MoveGuard',
                'orders': self._serialize_data(cycle.orders),
                'orders_config': self._serialize_data(getattr(cycle, 'orders_config', {})),
                'account': str(getattr(self.bot.account, 'id', None)) if hasattr(self.bot, 'account') else None,
                'bot': str(self.bot.id) if hasattr(self.bot, 'id') else None,
                'magic_number': self._safe_float_value(getattr(cycle, 'magic_number', 0.0)),
                'stop_loss': self._safe_float_value(getattr(cycle, 'stop_loss', 0.0)),
                'take_profit': self._safe_float_value(getattr(cycle, 'take_profit', 0.0)),
                'current_direction': cycle.direction,
                'cycle_id': cycle.cycle_id,
                'grid_data': self._serialize_data(grid_data),
                'zone_data': self._serialize_data(zone_data_val),
                'recovery_data': self._serialize_data(getattr(cycle, 'recovery_data', {})),
                'zone_movement_history': self._serialize_data(getattr(cycle, 'zone_movement_history', [])),
                'close_reason': getattr(cycle, 'close_reason', ''),
                'close_time': getattr(cycle, 'close_time', None),  # Use close_time field that exists in collection
                'total_orders': self._safe_float_value(getattr(cycle, 'total_orders', 0.0)),
                'profitable_orders': self._safe_float_value(getattr(cycle, 'profitable_orders', 0.0)),
                'loss_orders': self._safe_float_value(getattr(cycle, 'loss_orders', 0.0)),
                'duration_minutes': self._safe_float_value(getattr(cycle, 'duration_minutes', 0.0)),
                'upper_bound': upper_bound_val,
                'lower_bound': lower_bound_val,
                'is_closed': getattr(cycle, 'is_closed', False),
                'closing_method': getattr(cycle, 'closing_method', None),
                # Add trailing stop-loss and price tracking fields
                'trailing_stop_loss': self._safe_float_value(getattr(cycle, 'trailing_stop_loss', 0.0)),
                'highest_buy_price': self._safe_float_value(getattr(cycle, 'highest_buy_price', 0.0)),
                'lowest_sell_price': self._safe_float_value(getattr(cycle, 'lowest_sell_price', 999999.0)),
                # CRITICAL: Include cycle_config for cycle-specific configuration storage
                'cycle_config': self._serialize_data(cycle_config)
            }
            
            return cycle_data
            
        except Exception as e:
            logger.error(f"❌ Error preparing MoveGuard cycle data: {str(e)}")
            return {}

    def _validate_cycle_data_before_update(self, cycle_data: dict) -> bool:
        """Validate cycle data before database update for MoveGuard"""
        try:
            required_fields = ['id', 'symbol', 'direction', 'entry_price', 'lot_size', 'status']
            
            for field in required_fields:
                if field not in cycle_data or cycle_data[field] is None:
                    logger.error(f"❌ Missing required field for MoveGuard cycle: {field}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validating MoveGuard cycle data: {str(e)}")
            return False

    def _serialize_data(self, data):
        """Serialize data for MoveGuard database storage"""
        try:
            if isinstance(data, (dict, list)):
                return json.dumps(data)
            return str(data)
        except Exception as e:
            logger.error(f"❌ Error serializing data for MoveGuard: {str(e)}")
            return "{}"

    # ==================== STRATEGY STATISTICS ====================

    def get_strategy_statistics(self) -> dict:
        """Get MoveGuard strategy statistics"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            stats = {
                'strategy_name': 'MoveGuard',
                'active_cycles': len(active_cycles),
                'total_cycles': len(self.multi_cycle_manager.get_all_active_cycles()),
                'total_profit': sum(cycle.total_profit for cycle in active_cycles),
                'total_profit_pips': sum(cycle.total_profit_pips for cycle in active_cycles),
                'total_profit_dollars': self.get_total_active_profit_from_mt5(),
                'total_volume': sum(cycle.total_volume for cycle in active_cycles),
                'recovery_cycles': len(self.recovery_cycles),
                'active_zones': len(self.active_zones),
                'grid_levels': self.current_grid_level,
                'is_running': self.is_running,
                'is_initialized': self.is_initialized
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting MoveGuard statistics: {str(e)}")
            return {}

    def reset_strategy(self):
        """Reset MoveGuard strategy"""
        try:
            logger.info("🔄 Resetting MoveGuard Strategy...")
            
            # Stop strategy
            self.stop_strategy()
            
            # Clear all cycles
            self.multi_cycle_manager.clear_all_cycles()
            
            # Reset state
            self.is_running = False
            self.is_initialized = False
            self.current_grid_level = 0
            self.grid_direction = None
            self.last_grid_price = 0.0
            self.active_zones = {}
            self.zone_movement_history = []
            self.recovery_cycles = {}
            self.recovery_direction_locks = {}
            
            # Reset loss tracker
            self.loss_tracker = self._initialize_loss_tracker()
            
            logger.info("✅ MoveGuard Strategy reset successfully")
            
        except Exception as e:
            logger.error(f"❌ Error resetting MoveGuard Strategy: {str(e)}")

    async def cleanup(self):
        """Cleanup MoveGuard strategy"""
        try:
            logger.info("🧹 Cleaning up MoveGuard Strategy...")
            
            # Stop strategy
            self.stop_strategy()
            
            # Update all cycles in database
            all_cycles = self.multi_cycle_manager.get_all_active_cycles()
            for cycle in all_cycles:
                try:
                    self._update_cycle_in_database(cycle)
                except Exception as e:
                    logger.error(f"❌ Error updating cycle {cycle.cycle_id} in database: {str(e)}")
            
            logger.info("✅ MoveGuard Strategy cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Error cleaning up MoveGuard Strategy: {str(e)}")

    # ==================== THREADING SUPPORT ====================

    async def run_in_thread(self):
        """Run MoveGuard strategy in thread"""
        try:
            def run_coroutine_in_thread(coro):
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
            
            # Start strategy
            self.start_strategy()
            
            # # Run monitoring loop
            # await self._monitoring_loop()
            
        except Exception as e:
            logger.error(f"❌ Error running MoveGuard in thread: {str(e)}")

    async def run(self):
        """Run MoveGuard strategy"""
        try:
            logger.info("🚀 Running MoveGuard Strategy...")
            
            # Initialize strategy
            self.initialize()
            
            # Start strategy
            self.start_strategy()
            
            # Keep running until stopped
            while self.is_running:
                await asyncio.sleep(1)
            
            logger.info("✅ MoveGuard Strategy run completed")
            
        except Exception as e:
            logger.error(f"❌ Error running MoveGuard Strategy: {str(e)}")

    # ==================== PLACEHOLDER METHODS FOR COMPLETE IMPLEMENTATION ====================

    def _calculate_grid_level(self, cycle, current_price: float) -> int:
        """Calculate grid level for MoveGuard based on price movement and existing orders"""
        try:
            # Get zone boundaries and grid parameters
            zone_data = cycle.zone_data
            upper_boundary = zone_data.get('upper_boundary', 0.0)
            lower_boundary = zone_data.get('lower_boundary', 0.0)
            
            pip_value = self._get_pip_value()
            grid_interval_pips = getattr(cycle, 'grid_interval_pips', self.grid_interval_pips)
            entry_interval_pips = getattr(cycle, 'entry_interval_pips', self.entry_interval_pips)
            
            # Get active orders for this cycle
            active_orders = [o for o in cycle.orders if o.get('status') == 'active']
            active_grid_orders = [o for o in active_orders if o.get('is_grid', False)]
            
            if not active_grid_orders:
                logger.debug(f"📊 No active grid orders found for cycle {cycle.cycle_id}, starting at level 1")
                return 1
            
            # Find the highest grid level among active grid orders
            max_grid_level = -1
            for order in active_grid_orders:
                grid_level = order.get('grid_level', 0)
                if grid_level > max_grid_level:
                    max_grid_level = grid_level
            
            next_level = max_grid_level + 1
            logger.debug(f"📊 Grid level calculation for cycle {cycle.cycle_id}: max_level={max_grid_level}, next_level={next_level}")
            return next_level
            
        except Exception as e:
            logger.error(f"❌ Error calculating grid level for MoveGuard: {str(e)}")
            return 1

    def _reset_grid_levels_on_trailing_sl(self, cycle):
        """Reset grid levels to start from 1 when trailing SL is hit"""
        try:
            logger.info(f"🔄 Resetting grid levels for cycle {cycle.cycle_id} due to trailing SL hit")
            
            # Get all active orders for this cycle
            active_orders = [o for o in cycle.orders if o.get('status') == 'active']
            
            # Reset grid levels starting from 0
            new_level = 0
            for order in active_orders:
                if order.get('is_grid', False):  # Reset all grid orders including grid_0
                    old_level = order.get('grid_level', 0)
                    order['grid_level'] = new_level
                    order['order_type'] = f'grid_{new_level}'
                    logger.debug(f"📊 Reset order {order.get('order_id')} from level {old_level} to {new_level}")
                    new_level += 1
            
            logger.info(f"✅ Grid levels reset for cycle {cycle.cycle_id}: {len(active_orders)} orders updated")
            
        except Exception as e:
            logger.error(f"❌ Error resetting grid levels for cycle {cycle.cycle_id}: {str(e)}")

    def _place_grid_order(self, cycle, current_price: float, grid_level: int):
        """Place grid order for MoveGuard"""
        try:
            logger.info(f"📈 MoveGuard placing grid order: level={grid_level}, price={current_price}")
            
            # Get cycle-specific configuration values
            max_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_trades_per_cycle', self.max_trades_per_cycle)
            grid_interval_pips = self.get_cycle_config_value(cycle, 'grid_interval_pips', self.grid_interval_pips)
            entry_interval_pips = self.get_cycle_config_value(cycle, 'entry_interval_pips', self.entry_interval_pips)
            
            # Check if we've reached max trades per cycle
            if len(cycle.orders) >= max_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max trades ({max_trades_per_cycle})")
                return False
            
            # Determine order direction based on cycle direction
            order_direction = cycle.direction
            
            # Calculate order price based on grid level and boundaries
            pip_value = self._get_pip_value()
            
            # Get zone boundaries
            zone_data = cycle.zone_data
            upper_boundary = zone_data.get('upper_boundary', 0.0)
            lower_boundary = zone_data.get('lower_boundary', 0.0)
            
            if order_direction == 'BUY':
                # For BUY cycles: calculate from upper boundary
                # Grid level 0 starts at upper_boundary + entry_interval_pips
                grid_start_price = upper_boundary + (entry_interval_pips * pip_value)
                grid_pips = grid_level * grid_interval_pips
                order_price = grid_start_price + (grid_pips * pip_value)
                
                # Only place if current price is near the grid level (within tolerance)
                price_tolerance = entry_interval_pips * pip_value
                if abs(current_price - order_price) <= price_tolerance:
                    logger.info(f"📈 Placing BUY grid order: level={grid_level}, target_price={order_price}, current_price={current_price}")
                    return self._place_grid_buy_order(cycle, order_price, grid_level)
                else:
                    logger.debug(f"📊 BUY grid level {grid_level} not ready: target={order_price}, current={current_price}, diff={abs(current_price - order_price):.5f}")
            else:  # SELL
                # For SELL cycles: calculate from lower boundary
                # Grid level 0 starts at lower_boundary - entry_interval_pips
                grid_start_price = lower_boundary - (entry_interval_pips * pip_value)
                grid_pips = grid_level * grid_interval_pips
                order_price = grid_start_price - (grid_pips * pip_value)
                
                # Only place if current price is near the grid level (within tolerance)
                price_tolerance = entry_interval_pips * pip_value
                if abs(current_price - order_price) <= price_tolerance:
                    logger.info(f"📉 Placing SELL grid order: level={grid_level}, target_price={order_price}, current_price={current_price}")
                    return self._place_grid_sell_order(cycle, order_price, grid_level)
                else:
                    logger.debug(f"📊 SELL grid level {grid_level} not ready: target={order_price}, current={current_price}, diff={abs(current_price - order_price):.5f}")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error placing grid order for MoveGuard: {str(e)}")
            return False

    def _place_grid_buy_order(self, cycle, order_price: float, grid_level: int) -> bool:
        """Place grid BUY order for MoveGuard"""
        try:
            logger.info(f"📈 MoveGuard placing grid BUY order at {order_price}")
            
            # Get cycle-specific configuration values
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            lot_size = self.get_cycle_config_value(cycle, 'lot_size', self.lot_size)
            max_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_trades_per_cycle', self.max_trades_per_cycle)
            max_active_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_active_trades_per_cycle', self.max_active_trades_per_cycle)
            
            # Check total trades limit (active + closed orders)
            total_orders = len(cycle.orders) if hasattr(cycle, 'orders') else 0
            if total_orders >= max_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max total trades ({max_trades_per_cycle}) - cannot place BUY grid order")
                return False
            
            # Check active trades limit (active orders only)
            active_orders = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
            if len(active_orders) >= max_active_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max active trades ({max_active_trades_per_cycle}) - cannot place BUY grid order")
                return False
            
            # Calculate stop loss and take profit
            pip_value = self._get_pip_value()
            
            # Determine if this is the first grid order (apply SL only for the first grid)
            is_first_grid = True
            if hasattr(cycle, 'grid_data') and isinstance(cycle.grid_data, dict):
                grid_orders_list = cycle.grid_data.get('grid_orders', []) if isinstance(cycle.grid_data.get('grid_orders'), list) else []
                if grid_orders_list:
                    is_first_grid = False
            first_grid_sl = 0
            if is_first_grid and initial_stop_loss_pips > 0:
                first_grid_sl = order_price - (initial_stop_loss_pips * pip_value)
                # Validate stop loss is reasonable (at least 1 pip away from order price)
                min_sl_distance = pip_value * 1.0  # 1 pip minimum
                if order_price - first_grid_sl < min_sl_distance:
                    first_grid_sl = order_price - min_sl_distance
                    logger.warning(f"⚠️ Adjusted BUY stop loss to minimum distance: {first_grid_sl:.5f}")

            # Validate order parameters before placement
            if lot_size <= 0:
                logger.error(f"❌ Invalid lot size for BUY order: {lot_size}")
                return False
            
            if order_price <= 0:
                logger.error(f"❌ Invalid order price for BUY order: {order_price}")
                return False
            
            logger.debug(f"📋 Placing BUY order: symbol={self.symbol}, volume={lot_size}, price={order_price:.5f}, sl={first_grid_sl:.5f}, grid_level={grid_level}")
            
            # Place order through MetaTrader using the correct method
            order_result = self.meta_trader.place_buy_order(
                symbol=self.symbol,
                volume=lot_size,
                price=order_price,
                stop_loss=first_grid_sl,
                take_profit=0,
                comment=f"MoveGuard_Grid_{grid_level}"
            )
            
            if order_result and isinstance(order_result, dict) and 'order' in order_result:
                # Update cycle direction to BUY when placing BUY orders
                cycle.direction = 'BUY'
                logger.info(f"📈 Updated cycle {cycle.cycle_id} direction to BUY")
                
                # Add order to cycle
                order_info = {
                    'order_id': order_result['order'].get('ticket'),
                    'ticket': order_result['order'].get('ticket'),
                    'direction': 'BUY',
                    'price': order_price,
                    'lot_size': lot_size,
                    'grid_level': grid_level,
                    'is_grid': True,
                    'order_type': f'grid_{grid_level}',
                    'status': 'active',
                    'placed_at': datetime.datetime.now().isoformat()
                }
                
                # Add order to cycle
                if hasattr(cycle, 'orders'):
                    cycle.orders.append(order_info)
                else:
                    cycle.orders = [order_info]
                
                # Track active orders list
                if hasattr(cycle, 'active_orders'):
                    cycle.active_orders.append(order_info)
                else:
                    cycle.active_orders = [order_info]
                
                # Update grid data
                if hasattr(cycle, 'grid_data'):
                    if isinstance(cycle.grid_data, dict):
                        cycle.grid_data['current_level'] = grid_level
                        cycle.grid_data['grid_orders'].append(order_info)
                    else:
                        # Initialize grid_data if it's not a dict
                        cycle.grid_data = {
                            'current_level': grid_level,
                            'grid_direction': cycle.direction,
                            'last_grid_price': order_price,
                            'grid_orders': [order_info]
                        }
                else:
                    cycle.grid_data = {
                        'current_level': grid_level,
                        'grid_direction': cycle.direction,
                        'last_grid_price': order_price,
                        'grid_orders': [order_info]
                    }
                
                logger.info(f"✅ MoveGuard grid BUY order placed successfully: {order_info['order_id']}")
                return True
            else:
                logger.error(f"❌ Failed to place MoveGuard grid BUY order")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard grid BUY order: {str(e)}")
            return False

    def _place_grid_sell_order(self, cycle, order_price: float, grid_level: int) -> bool:
        """Place grid SELL order for MoveGuard"""
        try:
            logger.info(f"📉 MoveGuard placing grid SELL order at {order_price}")
            
            # Get cycle-specific configuration values
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            lot_size = self.get_cycle_config_value(cycle, 'lot_size', self.lot_size)
            max_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_trades_per_cycle', self.max_trades_per_cycle)
            max_active_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_active_trades_per_cycle', self.max_active_trades_per_cycle)
            
            # Check total trades limit (active + closed orders)
            total_orders = len(cycle.orders) if hasattr(cycle, 'orders') else 0
            if total_orders >= max_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max total trades ({max_trades_per_cycle}) - cannot place SELL grid order")
                return False
            
            # Check active trades limit (active orders only)
            active_orders = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
            if len(active_orders) >= max_active_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max active trades ({max_active_trades_per_cycle}) - cannot place SELL grid order")
                return False
            
            # Calculate stop loss and take profit
            pip_value = self._get_pip_value()

            # Determine if this is the first grid order (apply SL only for the first grid)
            is_first_grid = True
            if hasattr(cycle, 'grid_data') and isinstance(cycle.grid_data, dict):
                grid_orders_list = cycle.grid_data.get('grid_orders', []) if isinstance(cycle.grid_data.get('grid_orders'), list) else []
                if grid_orders_list:
                    is_first_grid = False
            first_grid_sl = 0
            if is_first_grid and initial_stop_loss_pips > 0:
                first_grid_sl = order_price + (initial_stop_loss_pips * pip_value)
                # Validate stop loss is reasonable (at least 1 pip away from order price)
                min_sl_distance = pip_value * 1.0  # 1 pip minimum
                if first_grid_sl - order_price < min_sl_distance:
                    first_grid_sl = order_price + min_sl_distance
                    logger.warning(f"⚠️ Adjusted SELL stop loss to minimum distance: {first_grid_sl:.5f}")

            # Validate order parameters before placement
            if lot_size <= 0:
                logger.error(f"❌ Invalid lot size for SELL order: {lot_size}")
                return False
            
            if order_price <= 0:
                logger.error(f"❌ Invalid order price for SELL order: {order_price}")
                return False
            
            logger.debug(f"📋 Placing SELL order: symbol={self.symbol}, volume={lot_size}, price={order_price:.5f}, sl={first_grid_sl:.5f}, grid_level={grid_level}")
            
            # Place order through MetaTrader using the correct method
            order_result = self.meta_trader.place_sell_order(
                symbol=self.symbol,
                volume=lot_size,
                price=order_price,
                stop_loss=first_grid_sl,
                take_profit=0,
                comment=f"MoveGuard_Grid_{grid_level}"
            )
            
            if order_result and isinstance(order_result, dict) and 'order' in order_result:
                # Update cycle direction to SELL when placing SELL orders
                cycle.direction = 'SELL'
                logger.info(f"📉 Updated cycle {cycle.cycle_id} direction to SELL")
                
                # Add order to cycle
                order_info = {
                    'order_id': order_result['order'].get('ticket'),
                    'ticket': order_result['order'].get('ticket'),
                    'direction': 'SELL',
                    'price': order_price,
                    'lot_size': lot_size,
                    'grid_level': grid_level,
                    'is_grid': True,
                    'order_type': f'grid_{grid_level}',
                    'status': 'active',
                    'placed_at': datetime.datetime.now().isoformat()
                }
                
                # Add order to cycle
                if hasattr(cycle, 'orders'):
                    cycle.orders.append(order_info)
                else:
                    cycle.orders = [order_info]
                
                # Track active orders list
                if hasattr(cycle, 'active_orders'):
                    cycle.active_orders.append(order_info)
                else:
                    cycle.active_orders = [order_info]
                
                # Update grid data
                if hasattr(cycle, 'grid_data'):
                    if isinstance(cycle.grid_data, dict):
                        cycle.grid_data['current_level'] = grid_level
                        cycle.grid_data['grid_orders'].append(order_info)
                    else:
                        # Initialize grid_data if it's not a dict
                        cycle.grid_data = {
                            'current_level': grid_level,
                            'grid_direction': cycle.direction,
                            'last_grid_price': order_price,
                            'grid_orders': [order_info]
                        }
                else:
                    cycle.grid_data = {
                        'current_level': grid_level,
                        'grid_direction': cycle.direction,
                        'last_grid_price': order_price,
                        'grid_orders': [order_info]
                    }
                
                logger.info(f"✅ MoveGuard grid SELL order placed successfully: {order_info['order_id']}")
                return True
            else:
                logger.error(f"❌ Failed to place MoveGuard grid SELL order")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard grid SELL order: {str(e)}")
            return False

    def _check_zone_movement(self, cycle, current_price: float) -> dict:
        """Check zone movement for MoveGuard based on zone movement mode"""
        try:
            # Get zone data from cycle
            if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                cycle.zone_data = {
                    'base_price': cycle.entry_price,
                    'upper_boundary': cycle.entry_price + (self.get_cycle_zone_threshold_pips(cycle) * self._get_pip_value()),
                    'lower_boundary': cycle.entry_price - (self.get_cycle_zone_threshold_pips(cycle) * self._get_pip_value()),
                    'movement_mode': self.zone_movement_mode,
                    'last_movement': None
                }
            
            zone_data = cycle.zone_data
            base_price = zone_data['base_price']
            upper_boundary = zone_data['upper_boundary']
            lower_boundary = zone_data['lower_boundary']
            movement_mode = zone_data['movement_mode']
            
            # Check if price has breached zone boundaries
            should_move = False
            direction = None
            
            if current_price > upper_boundary:
                # Price above upper boundary
                if movement_mode in ['Move Up Only', 'Move Both Sides']:
                    should_move = True
                    direction = 'UP'
                    logger.info(f"📈 MoveGuard zone breach UP detected at {current_price}")
            elif current_price < lower_boundary:
                # Price below lower boundary
                if movement_mode in ['Move Down Only', 'Move Both Sides']:
                    should_move = True
                    direction = 'DOWN'
                    logger.info(f"📉 MoveGuard zone breach DOWN detected at {current_price}")
            
            return {
                'should_move': should_move,
                'direction': direction,
                'current_price': current_price,
                'base_price': base_price,
                'upper_boundary': upper_boundary,
                'lower_boundary': lower_boundary
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking zone movement for MoveGuard: {str(e)}")
            return {'should_move': False, 'direction': None}

    def _move_zone(self, cycle, direction: str, current_price: float):
        """Move zone for MoveGuard"""
        try:
            logger.info(f"🔄 MoveGuard moving zone {direction} to {current_price}")
            
            # Update zone data
            if not hasattr(cycle, 'zone_data'):
                cycle.zone_data = {}
            
            # Calculate new zone boundaries
            pip_value = self._get_pip_value()
            zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
            
            if direction == 'UP':
                # Move zone up - new base price is current price
                new_base_price = current_price
                new_upper_boundary = new_base_price + (zone_threshold_pips * pip_value)
                new_lower_boundary = new_base_price - (zone_threshold_pips * pip_value)
            else:  # DOWN
                # Move zone down - new base price is current price
                new_base_price = current_price
                new_upper_boundary = new_base_price + (zone_threshold_pips * pip_value)
                new_lower_boundary = new_base_price - (zone_threshold_pips * pip_value)
            
            # Update zone data
            cycle.zone_data.update({
                'base_price': new_base_price,
                'upper_boundary': new_upper_boundary,
                'lower_boundary': new_lower_boundary,
                'last_movement': {
                    'direction': direction,
                    'old_base': cycle.zone_data.get('base_price'),
                    'new_base': new_base_price,
                    'timestamp': datetime.datetime.now().isoformat()
                }
            })
            
            # Record zone movement history
            if not hasattr(cycle, 'zone_movement_history'):
                cycle.zone_movement_history = []
            
            cycle.zone_movement_history.append({
                'direction': direction,
                'old_base': cycle.zone_data.get('base_price'),
                'new_base': new_base_price,
                'timestamp': datetime.datetime.now().isoformat()
            })
            
            logger.info(f"✅ MoveGuard zone moved {direction}: base_price={new_base_price:.5f}, upper={new_upper_boundary:.5f}, lower={new_lower_boundary:.5f}")
            
            # Update cycle entry price to reflect new zone
            cycle.entry_price = new_base_price
            
        except Exception as e:
            logger.error(f"❌ Error moving zone for MoveGuard: {str(e)}")

    def _check_recovery_conditions(self, cycle_id: str, recovery_data: dict, current_price: float):
        """Check recovery conditions for MoveGuard"""
        try:
            if not self.recovery_enabled:
                return
            
            # Get cycle from multi-cycle manager
            cycle = self.multi_cycle_manager.get_cycle(cycle_id)
            if not cycle:
                logger.warning(f"⚠️ Cycle {cycle_id} not found for recovery check")
                return
            
            # Check if cycle is in recovery mode
            if not hasattr(cycle, 'recovery_data') or not cycle.recovery_data:
                cycle.recovery_data = {
                    'is_active': False,
                    'trigger_price': 0.0,
                    'recovery_orders': [],
                    'direction_lock': None,
                    'started_at': None
                }
            
            recovery_info = cycle.recovery_data
            
            # Check if recovery should be triggered
            if not recovery_info['is_active']:
                self._check_recovery_trigger(cycle, current_price)
            else:
                # Recovery is active, check for completion or additional orders
                self._process_active_recovery(cycle, current_price)
                
        except Exception as e:
            logger.error(f"❌ Error checking recovery conditions for MoveGuard: {str(e)}")

    def _check_recovery_trigger(self, cycle, current_price: float):
        """Check if recovery should be triggered for MoveGuard"""
        try:
            # Calculate total loss for the cycle
            total_loss = self._calculate_cycle_total_loss(cycle)
            
            # Check if loss exceeds recovery threshold
            recovery_stop_loss_pips = self.get_cycle_config_value(cycle, 'recovery_stop_loss_pips', self.recovery_stop_loss_pips)
            recovery_threshold = recovery_stop_loss_pips * self._get_pip_value()
            
            if total_loss > recovery_threshold:
                logger.info(f"🚨 MoveGuard recovery triggered for cycle {cycle.cycle_id}: loss={total_loss:.5f}")
                
                # Initialize recovery mode
                cycle.recovery_data.update({
                    'is_active': True,
                    'trigger_price': current_price,
                    'recovery_orders': [],
                    'direction_lock': cycle.direction,  # Lock to same direction
                    'started_at': datetime.datetime.now().isoformat()
                })
                
                # Place first recovery order
                self._place_recovery_order(cycle, current_price)
                
        except Exception as e:
            logger.error(f"❌ Error checking recovery trigger for MoveGuard: {str(e)}")

    def _process_active_recovery(self, cycle, current_price: float):
        """Process active recovery for MoveGuard"""
        try:
            recovery_info = cycle.recovery_data
            
            # Check if recovery should continue
            total_loss = self._calculate_cycle_total_loss(cycle)
            recovery_stop_loss_pips = self.get_cycle_config_value(cycle, 'recovery_stop_loss_pips', self.recovery_stop_loss_pips)
            recovery_threshold = recovery_stop_loss_pips * self._get_pip_value()
            
            if total_loss <= recovery_threshold:
                # Recovery successful, exit recovery mode
                logger.info(f"✅ MoveGuard recovery completed for cycle {cycle.cycle_id}")
                recovery_info['is_active'] = False
                return
            
            # Check if we should place additional recovery orders
            last_recovery_order = recovery_info['recovery_orders'][-1] if recovery_info['recovery_orders'] else None
            
            if last_recovery_order:
                # Calculate if price has moved enough for new recovery order
                pip_value = self._get_pip_value()
                price_diff = abs(current_price - last_recovery_order['price'])
                pips_diff = price_diff / pip_value
                
                recovery_interval_pips = self.get_cycle_config_value(cycle, 'recovery_interval_pips', self.recovery_interval_pips)
                if pips_diff >= recovery_interval_pips:
                    self._place_recovery_order(cycle, current_price)
                    
        except Exception as e:
            logger.error(f"❌ Error processing active recovery for MoveGuard: {str(e)}")

    def _place_recovery_order(self, cycle, current_price: float):
        """Place recovery order for MoveGuard"""
        try:
            logger.info(f"🔄 MoveGuard placing recovery order at {current_price}")
            
            # Determine order direction (same as cycle direction)
            order_direction = cycle.direction
            
            # Calculate stop loss and take profit
            pip_value = self._get_pip_value()
            
            # Get cycle-specific configuration values
            lot_size = self.get_cycle_config_value(cycle, 'lot_size', self.lot_size)
            recovery_stop_loss_pips = self.get_cycle_config_value(cycle, 'recovery_stop_loss_pips', self.recovery_stop_loss_pips)
            cycle_take_profit_pips = self.get_cycle_config_value(cycle, 'cycle_take_profit_pips', self.cycle_take_profit_pips)
            
            # Place order through MetaTrader using the correct methods
            if order_direction == 'BUY':
                # stop_loss = current_price - (recovery_stop_loss_pips * pip_value)
                # take_profit = current_price + (cycle_take_profit_pips * pip_value)
                
                order_result = self.meta_trader.place_buy_order(
                    symbol=self.symbol,
                    volume=lot_size,
                    price=current_price,
                    stop_loss=0,
                    take_profit=0,
                    comment="MoveGuard_Recovery"
                )
            else:  # SELL
                # stop_loss = current_price + (recovery_stop_loss_pips * pip_value)
                # take_profit = current_price - (cycle_take_profit_pips * pip_value)
                
                order_result = self.meta_trader.place_sell_order(
                    symbol=self.symbol,
                    volume=lot_size,
                    price=current_price,
                    stop_loss=0,
                    take_profit=0,
                    comment="MoveGuard_Recovery"
                )
            
            if order_result and isinstance(order_result, dict) and 'order' in order_result:
                # Ensure cycle direction matches recovery order direction
                cycle.direction = order_direction
                logger.info(f"🔄 Confirmed cycle {cycle.cycle_id} direction as {order_direction} for recovery order")
                
                # Add recovery order to cycle
                recovery_order = {
                    'order_id': order_result['order'].get('ticket'),
                    'direction': order_direction,
                    'price': current_price,
                    'lot_size': lot_size,
                    'type': 'recovery',
                    'status': 'active',
                    'placed_at': datetime.datetime.now().isoformat(),
                    'grid_level': -2  # -2 indicates recovery order (not a grid order)
                }
                
                # Add order to cycle
                if hasattr(cycle, 'orders'):
                    cycle.orders.append(recovery_order)
                else:
                    cycle.orders = [recovery_order]
                
                # Track active orders list
                if hasattr(cycle, 'active_orders'):
                    cycle.active_orders.append(recovery_order)
                else:
                    cycle.active_orders = [recovery_order]
                
                # Update recovery data
                if not hasattr(cycle, 'recovery_data'):
                    cycle.recovery_data = {'recovery_orders': []}
                cycle.recovery_data['recovery_orders'].append(recovery_order)
                
                logger.info(f"✅ MoveGuard recovery order placed successfully: {recovery_order['order_id']}")
                return True
            else:
                logger.error(f"❌ Failed to place MoveGuard recovery order")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing recovery order for MoveGuard: {str(e)}")
            return False

    def _calculate_cycle_total_loss(self, cycle) -> float:
        """Calculate total loss for a cycle in MoveGuard"""
        try:
            total_loss = 0.0
            current_price = self._get_current_price()
            
            if not current_price:
                return 0.0
            
            for order in cycle.orders:
                if order.get('status') == 'active':
                    # Calculate unrealized loss for active orders
                    order_price = order.get('price', 0.0)
                    if order.get('direction') == 'BUY':
                        loss = order_price - current_price
                    else:  # SELL
                        loss = current_price - order_price
                    
                    total_loss += loss * order.get('lot_size', 0.0)
            
            return total_loss
            
        except Exception as e:
            logger.error(f"❌ Error calculating cycle total loss for MoveGuard: {str(e)}")
            return 0.0

    def _check_take_profit_conditions(self, current_price: float, active_cycles: List):
        """Check take profit conditions for MoveGuard"""
        try:
            for cycle in active_cycles:
                if cycle.status != 'active':
                    continue

                # Bound-based closing for BUY cycles per new rules
                if hasattr(cycle, 'zone_data') and cycle.direction == 'BUY':
                    # Calculate proper boundaries
                    # upper, lower = self._calculate_proper_boundaries(cycle, current_price)
                    upper= cycle.zone_data.get('upper_boundary', 0.0)
                    lower= cycle.zone_data.get('lower_boundary', 0.0)
                    if getattr(cycle, 'was_above_upper', False) and current_price <= upper:
                        logger.info(f"🎯 Upper bound hit after breach, closing all BUY orders for cycle {cycle.cycle_id}")
                        asyncio.create_task(self._close_all_cycle_orders(cycle))
                        # Move zone: new top = highest_buy_price, bottom = top - zone_size_pips
                        pip_value = self._get_pip_value()
                        new_top = max(getattr(cycle, 'highest_buy_price', 0.0), upper)
                        new_bottom = new_top - (self.get_cycle_zone_threshold_pips(cycle) * pip_value)
                        cycle.zone_data.update({
                            'base_price': new_top,
                            'upper_boundary': new_top,
                            'lower_boundary': new_bottom,
                            'last_movement': {
                                'direction': 'DOWN',
                                'old_base': cycle.zone_data.get('base_price'),
                                'new_base': new_top,
                                'timestamp': datetime.datetime.now().isoformat()
                            }
                        })
                        cycle.entry_price = new_top
                        cycle.was_above_upper = False
                        continue

                # Fallback TP logic (retain existing behavior for SELL or legacy)
                # Update all active orders with current profit from MetaTrader
                self._update_cycle_orders_profit_from_mt5(cycle)
                
                total_profit_dollars = self._calculate_cycle_total_profit_dollars(cycle, current_price)
                # Use cycle-specific take profit configuration
                take_profit_dollars = self.get_cycle_config_value(cycle, 'cycle_take_profit_pips', self.cycle_take_profit_pips)
                
                if total_profit_dollars >= take_profit_dollars:
                    logger.info(f"🎯 MoveGuard take profit reached for cycle {cycle.cycle_id}: ${total_profit_dollars:.2f} (target: ${take_profit_dollars:.2f})")
                    self._close_cycle_on_take_profit(cycle)
        except Exception as e:
            logger.error(f"❌ Error checking take profit conditions for MoveGuard: {str(e)}")

    def _close_cycle_on_take_profit(self, cycle):
        """Close cycle when take profit is reached for MoveGuard"""
        try:
            logger.info(f"🎯 MoveGuard closing cycle {cycle.cycle_id} on take profit")
            
            # Close all active orders in the cycle and update local lists
            for order in list(cycle.orders):
                if order.get('status') == 'active':
                    if self._close_order(order):
                        # Move from active_orders to completed_orders if those lists exist
                        oid = order.get('order_id') or order.get('ticket')
                        if hasattr(cycle, 'active_orders') and isinstance(cycle.active_orders, list):
                            cycle.active_orders = [o for o in cycle.active_orders if (o.get('order_id') or o.get('ticket')) != oid]
                        if hasattr(cycle, 'completed_orders') and isinstance(cycle.completed_orders, list):
                            cycle.completed_orders.append(order)
            
            # Update cycle status and closure tracking
            cycle.status = 'closed'
            cycle.is_closed = True
            cycle.closing_method = "take_profit"
            cycle.close_time = datetime.datetime.now().isoformat()  # Use close_time for database
            cycle.close_reason = "Take profit target reached"
            cycle.total_profit_pips = self._calculate_cycle_total_profit_pips(cycle, self._get_current_price())
            cycle.total_profit_dollars = self._calculate_cycle_total_profit_dollars(cycle, self._get_current_price())
            
            # Update database - force immediate update when closing
            self._update_cycle_in_database(cycle, force_update=True)
            
            # Remove cycle from manager locally
            try:
                self.multi_cycle_manager.remove_cycle(cycle.cycle_id)
            except Exception as rm_err:
                logger.warning(f"Could not remove cycle {cycle.cycle_id} from manager: {rm_err}")
            
            # Remove level from active cycle levels tracking
            self._remove_cycle_level(cycle.entry_price)
            
            logger.info(f"✅ MoveGuard cycle {cycle.cycle_id} closed on take profit: ${cycle.total_profit_dollars:.2f} ({cycle.total_profit_pips:.2f} pips)")
            
        except Exception as e:
            logger.error(f"❌ Error closing cycle on take profit for MoveGuard: {str(e)}")

    def _close_order(self, order):
        """Close individual order for MoveGuard"""
        try:
            # Normalize to unified 'order_id' but accept legacy 'ticket'
            order_id = order.get('order_id') or order.get('ticket')
            if not order_id:
                logger.warning(f"⚠️ No order ID/ticket found for order in MoveGuard")
                return False
            # Check if order is already closed
            if order.get('status') == 'closed':
                logger.info(f"✅ MoveGuard order {order_id} already closed")
                return True

            # Try to close active position first
            positions = None
            try:
                positions = self.meta_trader.get_position_by_ticket(int(order_id))
            except Exception:
                positions = None
                
            if positions and len(positions) > 0:
                # Close active position
                pos = positions[0]
                result = self.meta_trader.close_position(pos)
                if result is not None:
                    # Preserve existing profit data, only update status
                    existing_profit = order.get('profit', 0.0)
                    existing_profit_pips = order.get('profit_pips', 0.0)
                    order['status'] = 'closed'
                    order['closed_at'] = datetime.datetime.now().isoformat()
                    # Keep existing profit data, don't recalculate
                    order['profit'] = existing_profit
                    order['profit_pips'] = existing_profit_pips
                    # Ensure both keys are kept in sync for downstream persistence
                    order['order_id'] = int(order_id)
                    order['ticket'] = int(order_id)
                    logger.info(f"✅ MoveGuard active position {order_id} closed with preserved profit: {existing_profit:.2f} ({existing_profit_pips:.2f} pips)")
                    return True
                else:
                    logger.error(f"❌ Failed to close MoveGuard active position {order_id}")
                    return False
            else:
                # Try to delete pending order
                try:
                    result = self.meta_trader.delete_order(int(order_id))
                    if result is not None:
                        order['status'] = 'closed'
                        order['closed_at'] = datetime.datetime.now().isoformat()
                        order['profit'] = 0.0
                        order['profit_pips'] = 0.0
                        # Ensure both keys are kept in sync for downstream persistence
                        order['order_id'] = int(order_id)
                        order['ticket'] = int(order_id)
                        logger.info(f"✅ MoveGuard pending order {order_id} deleted successfully")
                        return True
                    else:
                        logger.warning(f"⚠️ MoveGuard order {order_id} not found in MetaTrader (may already be closed)")
                        # Mark as closed anyway since it's not in MT5
                        order['status'] = 'closed'
                        order['closed_at'] = datetime.datetime.now().isoformat()
                        order['profit'] = 0.0
                        order['profit_pips'] = 0.0
                        return True
                except Exception as e:
                    logger.warning(f"⚠️ Error deleting pending order {order_id}: {e}")
                    # Mark as closed anyway since we can't find it in MT5
                    order['status'] = 'closed'
                    order['closed_at'] = datetime.datetime.now().isoformat()
                    order['profit'] = 0.0
                    order['profit_pips'] = 0.0
                    return True
        except Exception as e:
            logger.error(f"❌ Error closing order for MoveGuard: {str(e)}")
            return False

    def _calculate_cycle_total_profit_pips(self, cycle, current_price: float) -> float:
        """Calculate cycle total profit pips for MoveGuard"""
        try:
            total_profit_pips = 0.0
            pip_value = self._get_pip_value()
            
            for order in cycle.orders:
                if order.get('status') == 'active':
                    order_price = order.get('price', 0.0)
                    order_direction = order.get('direction', 'BUY')
                    
                    if order_direction == 'BUY':
                        # For BUY orders, profit when price goes up
                        profit_pips = (current_price - order_price) / pip_value
                    else:  # SELL
                        # For SELL orders, profit when price goes down
                        profit_pips = (order_price - current_price) / pip_value
                    
                    # Weight by lot size
                    weighted_profit = profit_pips * order.get('lot_size', 0.0)
                    total_profit_pips += weighted_profit
            
            return total_profit_pips
            
        except Exception as e:
            logger.error(f"❌ Error calculating cycle total profit pips for MoveGuard: {str(e)}")
            return 0.0

    def _calculate_cycle_total_profit_dollars(self, cycle, current_price: float) -> float:
        """Get cycle total profit in dollars directly from MetaTrader for MoveGuard"""
        try:
            total_profit_dollars = 0.0
            
            for order in cycle.orders:
                if order.get('status') == 'active':
                    # Get profit directly from MetaTrader for this active order
                    order_profit = self._calculate_order_profit(order)
                    total_profit_dollars += order_profit['profit']
                    
                    # Update the order with the latest profit data from MetaTrader
                    order['profit'] = order_profit['profit']
                    order['profit_pips'] = order_profit['profit_pips']
                elif order.get('status') == 'closed':
                    # Add realized profit from closed orders
                    total_profit_dollars += order.get('profit', 0.0)
            
            return total_profit_dollars
            
        except Exception as e:
            logger.error(f"❌ Error getting cycle total profit dollars from MetaTrader for MoveGuard: {str(e)}")
            return 0.0

    async def _handle_close_cycle_event(self, content: dict) -> bool:
        """Handle close cycle event for MoveGuard"""
        try:
            logger.info("🔄 MoveGuard handling close cycle event")
             
            # Extract one or many cycle IDs from event content
            cycle_ids = self._extract_cycle_ids_from_event(content)
            
            # If "all" or nothing resolvable, close all active cycles
            if not cycle_ids or any(str(cid).lower() == 'all' for cid in cycle_ids):
                successes = 0
                active_cycles = self.multi_cycle_manager.get_all_active_cycles()
                logger.info(f"🔄 Closing all {len(active_cycles)} active cycles")
                
                for c in active_cycles:
                    ok = await self._close_all_cycle_orders(c)
                    if ok:
                        c.status = 'closed'
                        c.is_closed = True
                        c.closing_method = "event"
                        c.close_time = datetime.datetime.now().isoformat()  # Use close_time for database
                        c.close_reason = "Manual close request"
                        c.updated_at = datetime.datetime.now().isoformat()
                        try:
                            # Force immediate database update when closing cycles
                            self._update_cycle_in_database(c, force_update=True)
                        except Exception as e:
                            logger.error(f"❌ Error updating cycle {getattr(c,'cycle_id','unknown')} in database: {e}")
                        successes += 1
                        logger.info(f"✅ Successfully closed cycle {getattr(c,'cycle_id','unknown')}")
                    else:
                        logger.error(f"❌ Failed to close cycle {getattr(c,'cycle_id','unknown')}")
                
                # Remove all cycles from active cycles list
                self.multi_cycle_manager.clear_all_cycles()
                
                # Clear active cycle levels to ensure clean state
                self.active_cycle_levels.clear()
                logger.info("🧹 Cleared active cycle levels for fresh start")
                
                # Keep last_cycle_price to maintain price level reference for auto cycle placement
                logger.info("🔄 Keeping last_cycle_price for immediate auto cycle placement after close all")
                
                # Force process any remaining batch updates immediately
                self._process_batch_updates(force=True)
                
                logger.info(f"✅ Closed {successes}/{len(active_cycles)} cycles and removed from active list (close_all request)")
                return successes > 0

            # Otherwise close targeted cycles
            any_success = False
            for cid in cycle_ids:
                # Normalize dict payloads
                if isinstance(cid, dict):
                    cid = cid.get('id') or cid.get('cycle_id')
                if not cid:
                    continue
                # Get by key
                cycle = self.multi_cycle_manager.get_cycle(cid)
                # Fallback search in list by id or cycle_id
                if not cycle:
                    for c in self.multi_cycle_manager.get_all_active_cycles():
                        if getattr(c, 'cycle_id', None) == cid or getattr(c, 'id', None) == cid:
                            cycle = c
                            break
                if not cycle:
                    logger.warning(f"⚠️ Target cycle {cid} not found; skipping")
                    continue

                ok = await self._close_all_cycle_orders(cycle)
                if ok:
                    cycle.status = 'closed'
                    cycle.is_closed = True
                    cycle.closing_method = "event"
                    cycle.close_time = datetime.datetime.now().isoformat()  # Use close_time for database
                    cycle.close_reason = "Manual close request"
                    cycle.updated_at = datetime.datetime.now().isoformat()
                    try:
                        # Force immediate database update when closing cycles
                        self._update_cycle_in_database(cycle, force_update=True)
                    except Exception as e:
                        logger.error(f"❌ Error updating cycle {getattr(cycle,'cycle_id','unknown')} in database: {e}")
                    
                    # Remove cycle from active cycles list
                    self.multi_cycle_manager.remove_cycle(cycle.cycle_id)
                    
                    # Remove level from active cycle levels tracking
                    self._remove_cycle_level(cycle.entry_price)
                    
                    logger.info(f"✅ MoveGuard cycle {cid} closed successfully and removed from active list")
                    any_success = True
                else:
                    logger.error(f"❌ Failed to close MoveGuard cycle {cid}")

            return any_success
             
        except Exception as e:
            logger.error(f"❌ Error handling close cycle event for MoveGuard: {str(e)}")
            return False

    def _extract_cycle_ids_from_event(self, content: dict) -> list:
        """Extract one or more cycle IDs from various event payload shapes.
        Supports keys: id, cycle_id, ids, cycles, cycle; values can be str, dict, or list.
        """
        try:
            if not isinstance(content, dict):
                return []
            # Direct single keys
            for k in ('id', 'cycle_id'):
                if k in content and content[k]:
                    return [content[k]] if not isinstance(content[k], list) else content[k]
            # Common arrays
            for k in ('ids', 'cycles'):
                if k in content and isinstance(content[k], list) and content[k]:
                    return content[k]
            # Nested object
            if 'cycle' in content and isinstance(content['cycle'], dict):
                cyc = content['cycle']
                return [cyc.get('id') or cyc.get('cycle_id')] if (cyc.get('id') or cyc.get('cycle_id')) else []
            # Fallback none
            return []
        except Exception:
            return []

    async def _handle_close_order_event(self, content: dict) -> bool:
        """Handle close order event for MoveGuard"""
        try:
            logger.info("🔄 MoveGuard handling close order event")
            
            # Extract order ID from content
            order_id = content.get('order_id')
            if not order_id:
                logger.error("❌ No order_id provided in close order event for MoveGuard")
                return False
            
            # Find the order in all cycles
            order_found = False
            for cycle in self.multi_cycle_manager.get_all_active_cycles():
                for order in cycle.orders:
                    if order.get('order_id') == order_id:
                        # Close the specific order
                        success = self._close_order(order)
                        if success:
                            # Update database
                            try:
                                self._update_cycle_in_database(cycle)
                            except Exception as e:
                                logger.error(f"❌ Error updating cycle {cycle.cycle_id} in database: {str(e)}")
                            logger.info(f"✅ MoveGuard order {order_id} closed successfully")
                            order_found = True
                        break
                if order_found:
                    break
            
            if not order_found:
                logger.warning(f"⚠️ Order {order_id} not found in any MoveGuard cycle")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling close order event for MoveGuard: {str(e)}")
            return False

    async def _close_all_cycle_orders(self, cycle) -> bool:
        """Close all orders in a cycle for MoveGuard"""
        try:
            logger.info(f"🔄 MoveGuard closing all orders for cycle {cycle.cycle_id}")
            
            success_count = 0
            total_orders = len(cycle.orders)
            
            # Close ALL orders in the cycle, regardless of status
            # This ensures initial orders and any other orders are closed
            # Check multiple possible order storage locations
            all_orders = []
            
            # Main orders list
            if hasattr(cycle, 'orders') and cycle.orders:
                all_orders.extend(cycle.orders)
            
            # Active orders list
            if hasattr(cycle, 'active_orders') and cycle.active_orders:
                all_orders.extend(cycle.active_orders)
            
            # Remove duplicates based on order_id/ticket
            unique_orders = []
            seen_ids = set()
            for order in all_orders:
                order_id = order.get('order_id') or order.get('ticket')
                if order_id and order_id not in seen_ids:
                    unique_orders.append(order)
                    seen_ids.add(order_id)
            
            all_orders = unique_orders
            
            if not all_orders:
                logger.info(f"✅ No orders found for cycle {cycle.cycle_id}")
                return True

            logger.info(f"🔄 Found {len(all_orders)} unique orders for cycle {cycle.cycle_id}")
            for i, order in enumerate(all_orders):
                order_id = order.get('order_id') or order.get('ticket')
                order_status = order.get('status', 'unknown')
                order_type = order.get('order_type', 'unknown')
                logger.debug(f"  Order {i+1}: ID={order_id}, Status={order_status}, Type={order_type}")

            logger.info(f"🔄 Attempting to close {len(all_orders)} orders for cycle {cycle.cycle_id}")
            
            for order in all_orders:
                order_id = order.get('order_id') or order.get('ticket')
                order_status = order.get('status', 'unknown')
                
                logger.info(f"🔄 Closing order {order_id} (status: {order_status}) for cycle {cycle.cycle_id}")
                
                # Only close if order is not already closed
                if order.get('status') != 'closed':
                    success = self._close_order(order)
                    if success:
                        success_count += 1
                        logger.info(f"✅ Successfully closed order {order_id} for cycle {cycle.cycle_id}")
                    else:
                        logger.warning(f"⚠️ Failed to close order {order_id} for cycle {cycle.cycle_id}")
                else:
                    logger.info(f"ℹ️ Order {order_id} already closed for cycle {cycle.cycle_id}")
                    success_count += 1  # Count as success since it's already closed

            logger.info(f"✅ MoveGuard closed {success_count}/{len(all_orders)} orders for cycle {cycle.cycle_id}")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error closing all cycle orders for MoveGuard: {str(e)}")
            return False

    # ==================== ORDER STATUS TRACKING ====================

    def _track_and_update_order_status(self):
        """Track and update order status for all active cycles with profit calculations"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            for cycle in active_cycles:
                if cycle.status != 'active':
                    continue
                    
                orders_updated = False
                
                # Check each active order in the cycle
                for order in cycle.orders:
                    if order.get('status') != 'active':
                        continue
                        
                    order_id = order.get('order_id') or order.get('ticket')
                    if not order_id:
                        continue
                    
                    # Check if order still exists in MT5
                    if not self._order_exists_in_mt5(order_id):
                        # Order no longer exists, calculate profit and mark as closed
                        order_profit = self._calculate_order_profit(order)
                        order['status'] = 'closed'
                        order['closed_at'] = datetime.datetime.now().isoformat()
                        order['profit'] = order_profit['profit']
                        order['profit_pips'] = order_profit['profit_pips']
                        orders_updated = True
                        logger.info(f"✅ Order {order_id} marked as closed with profit: {order_profit['profit']:.2f} ({order_profit['profit_pips']:.2f} pips)")
                
                # If orders were updated, recalculate cycle statistics
                if orders_updated:
                    self._update_cycle_statistics_with_profit(cycle)
                    self._update_cycle_in_database(cycle)
                    
        except Exception as e:
            logger.error(f"❌ Error tracking order status: {str(e)}")

    def _order_exists_in_mt5(self, order_id: int) -> bool:
        """Check if order/position still exists in MT5 (both pending orders and active positions)"""
        try:
            # Check for active positions
            positions = self.meta_trader.get_position_by_ticket(int(order_id))
            if positions and len(positions) > 0:
                return True
                
           
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking order existence in MT5: {str(e)}")
            return False

    def _update_cycle_statistics(self, cycle):
        """Update cycle statistics after order status changes"""
        try:
            current_price = self._get_current_price()
            if not current_price:
                return
                
            # Recalculate total profit
            cycle.total_profit_pips = self._calculate_cycle_total_profit_pips(cycle, current_price)
            
            # Update active/completed order counts
            active_orders = [o for o in cycle.orders if o.get('status') == 'active']
            completed_orders = [o for o in cycle.orders if o.get('status') == 'closed']
            
            if hasattr(cycle, 'active_orders'):
                cycle.active_orders = active_orders
            if hasattr(cycle, 'completed_orders'):
                cycle.completed_orders = completed_orders
                
            # Update total volume
            cycle.total_volume = sum(o.get('lot_size', 0) for o in cycle.orders if o.get('status') == 'active')
            
            logger.debug(f"✅ Updated statistics for cycle {cycle.cycle_id}")
            
        except Exception as e:
            logger.error(f"❌ Error updating cycle statistics: {str(e)}")

    def _update_cycle_statistics_with_profit(self, cycle):
        """Update cycle statistics with comprehensive profit calculations"""
        try:
            current_price = self._get_current_price()
            if not current_price:
                return
                
            # Calculate realized profit from closed orders
            realized_profit = 0.0
            realized_profit_pips = 0.0
            
            for order in cycle.orders:
                if order.get('status') == 'closed':
                    # Use stored profit for closed orders, don't recalculate
                    realized_profit += order.get('profit', 0.0)
                    realized_profit_pips += order.get('profit_pips', 0.0)
            
            # Calculate unrealized profit from active orders
            unrealized_profit_pips = self._calculate_cycle_total_profit_pips(cycle, current_price)
            
            # Update cycle statistics
            cycle.total_profit = realized_profit
            cycle.total_profit_pips = realized_profit_pips + unrealized_profit_pips
            
            # Update active/completed order counts
            active_orders = [o for o in cycle.orders if o.get('status') == 'active']
            completed_orders = [o for o in cycle.orders if o.get('status') == 'closed']
            
            if hasattr(cycle, 'active_orders'):
                cycle.active_orders = active_orders
            if hasattr(cycle, 'completed_orders'):
                cycle.completed_orders = completed_orders
                
            # Update total volume (all orders - both active and completed)
            cycle.total_volume = sum(o.get('lot_size', 0) for o in cycle.orders)
            
            # Calculate order statistics for database fields
            cycle.total_orders = len(cycle.orders)
            
            # Count profitable and loss-making orders
            profitable_orders = 0
            loss_orders = 0
            
            for order in completed_orders:
                profit = order.get('profit', 0.0)
                if profit > 0:
                    profitable_orders += 1
                elif profit < 0:
                    loss_orders += 1
            
            cycle.profitable_orders = profitable_orders
            cycle.loss_orders = loss_orders
            
            # Calculate duration in minutes if cycle has creation time
            if hasattr(cycle, 'created_at') and cycle.created_at:
                try:
                    created_time = datetime.datetime.fromisoformat(cycle.created_at.replace('Z', '+00:00'))
                    current_time = datetime.datetime.now(datetime.timezone.utc)
                    duration = (current_time - created_time).total_seconds() / 60
                    cycle.duration_minutes = duration
                except:
                    cycle.duration_minutes = 0.0
            else:
                cycle.duration_minutes = 0.0
            
            # Calculate total profit in dollars
            total_profit_dollars = self._calculate_cycle_total_profit_dollars(cycle, self._get_current_price())
            cycle.total_profit_dollars = total_profit_dollars
            logger.info(f"✅ Updated cycle {cycle.cycle_id} statistics: realized_profit=${realized_profit:.2f}, total_profit=${total_profit_dollars:.2f} ({cycle.total_profit_pips:.2f} pips), total_volume={cycle.total_volume}, total_orders={cycle.total_orders}, profitable_orders={profitable_orders}, loss_orders={loss_orders}")
            
        except Exception as e:
            logger.error(f"❌ Error updating cycle statistics with profit: {str(e)}")

    def _calculate_order_profit(self, order):
        """Get profit for a specific order directly from MetaTrader"""
        try:
            order_id = order.get('order_id') or order.get('ticket')
            if not order_id:
                logger.warning(f"⚠️ No order ID/ticket found for order in profit calculation")
                return {'profit': 0.0, 'profit_pips': 0.0}
            
            # Get position data directly from MetaTrader
            positions = self.meta_trader.get_position_by_ticket(int(order_id))
            
            if positions and len(positions) > 0:
                position = positions[0]
                # Get actual profit from MetaTrader position
                profit = getattr(position, 'profit', 0.0)
                
                # Calculate profit in pips for reference
                order_price = order.get('price', 0.0)
                current_price = self._get_current_price()
                pip_value = self._get_pip_value()
                
                if order_price and current_price and pip_value:
                    order_direction = order.get('direction', 'BUY')
                    if order_direction == 'BUY':
                        profit_pips = (current_price - order_price) / pip_value
                    else:  # SELL
                        profit_pips = (order_price - current_price) / pip_value
                else:
                    profit_pips = 0.0
                
                # Log detailed profit information for debugging
                logger.debug(f"💰 Order {order_id} profit from MT5: ${profit:.2f}, calculated pips: {profit_pips:.2f}")
                
                return {
                    'profit': profit,
                    'profit_pips': profit_pips,
                    'close_price': current_price
                }
            else:
                # Position not found, return 0 profit
                logger.debug(f"⚠️ Order {order_id} not found in MetaTrader positions - may be pending or closed")
                return {'profit': 0.0, 'profit_pips': 0.0}
            
        except Exception as e:
            logger.error(f"❌ Error getting order profit from MetaTrader for order {order_id}: {str(e)}")
            return {'profit': 0.0, 'profit_pips': 0.0}

    def _get_order_close_price(self, order_id):
        """Get the actual close price for an order from MT5"""
        try:
            # This would ideally get the actual close price from MT5 history
            # For now, we'll use current price as fallback
            # In a full implementation, you'd query MT5 history for the actual close price
            
            # Placeholder for MT5 history query
            # close_price = self.meta_trader.get_order_close_price(order_id)
            # return close_price
            
            return None  # Will fallback to current price
            
        except Exception as e:
            logger.error(f"❌ Error getting order close price: {str(e)}")
            return None

    def _update_cycle_orders_profit_from_mt5(self, cycle):
        """Update all active orders in cycle with current profit data from MetaTrader"""
        try:
            updated_count = 0
            total_active_orders = 0
            
            for order in cycle.orders:
                if order.get('status') == 'active':
                    total_active_orders += 1
                    order_id = order.get('order_id') or order.get('ticket')
                    
                    # First verify order status with MetaTrader
                    self._verify_order_status_with_mt5(order)
                    
                    # Only update profit if order is still active after verification
                    if order.get('status') == 'active':
                        # Get current profit from MetaTrader
                        order_profit = self._calculate_order_profit(order)
                        
                        # Update order with latest profit data
                        old_profit = order.get('profit', 0.0)
                        old_profit_pips = order.get('profit_pips', 0.0)
                        
                        order['profit'] = order_profit['profit']
                        order['profit_pips'] = order_profit['profit_pips']
                        order['last_profit_update'] = datetime.datetime.now().isoformat()
                        
                        # Log significant profit changes
                        if abs(order_profit['profit'] - old_profit) > 0.01:  # More than 1 cent change
                            logger.info(f"💰 Order {order_id} profit updated: ${old_profit:.2f} → ${order_profit['profit']:.2f} ({order_profit['profit_pips']:.2f} pips)")
                        
                        updated_count += 1
            
            if updated_count > 0:
                logger.debug(f"✅ Updated profit data for {updated_count}/{total_active_orders} active orders in cycle {cycle.cycle_id}")
            
        except Exception as e:
            logger.error(f"❌ Error updating cycle orders profit from MetaTrader: {str(e)}")

    def _get_grid_orders_safely(self, cycle):
        """Safely get grid_orders from cycle.grid_data, handling different data types"""
        try:
            grid_data = getattr(cycle, 'grid_data', {})
            
            # Handle string (JSON) format
            if isinstance(grid_data, str):
                try:
                    grid_data = json.loads(grid_data)
                except (json.JSONDecodeError, AttributeError):
                    return []
            
            # Handle dict format
            if isinstance(grid_data, dict):
                grid_orders = grid_data.get('grid_orders', [])
                if isinstance(grid_orders, list):
                    return grid_orders
                else:
                    return []
            
            # Handle list format (direct grid_orders)
            if isinstance(grid_data, list):
                return grid_data
            
            return []
            
        except Exception as e:
            logger.error(f"❌ Error getting grid_orders safely: {str(e)}")
            return []

    def _update_all_cycles_profit_from_mt5(self):
        """Update all active cycles with current profit data from MetaTrader"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            updated_cycles = 0
            
            for cycle in active_cycles:
                try:
                    self._update_cycle_orders_profit_from_mt5(cycle)
                    updated_cycles += 1
                except Exception as cycle_error:
                    logger.error(f"❌ Error updating profit for cycle {cycle.cycle_id}: {str(cycle_error)}")
                    continue
            
            if updated_cycles > 0:
                logger.debug(f"✅ Updated profit data for {updated_cycles}/{len(active_cycles)} active cycles")
            
        except Exception as e:
            logger.error(f"❌ Error updating all cycles profit from MetaTrader: {str(e)}")

    def _update_cycles_profit_from_mt5(self, cycles):
        """Update specific cycles with current profit data from MetaTrader (optimized)"""
        try:
            if not cycles:
                return
            
            updated_cycles = 0
            
            for cycle in cycles:
                try:
                    self._update_cycle_orders_profit_from_mt5(cycle)
                    updated_cycles += 1
                except Exception as cycle_error:
                    logger.error(f"❌ Error updating profit for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {str(cycle_error)}")
                    continue
            
            if updated_cycles > 0:
                logger.debug(f"✅ Updated profit data for {updated_cycles}/{len(cycles)} filtered cycles")
                    
        except Exception as e:
            logger.error(f"❌ Error updating cycles profit: {str(e)}")

    def get_total_active_profit_from_mt5(self) -> float:
        """Get total profit for all active cycles combined from MetaTrader"""
        try:
            total_profit = 0.0
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            for cycle in active_cycles:
                cycle_profit = self._calculate_cycle_total_profit_dollars(cycle, self._get_current_price())
                total_profit += cycle_profit
            
            return total_profit
            
        except Exception as e:
            logger.error(f"❌ Error getting total active profit from MetaTrader: {str(e)}")
            return 0.0

    def _verify_order_status_with_mt5(self, order):
        """Verify order status against MetaTrader and fix inconsistencies"""
        try:
            order_id = order.get('order_id') or order.get('ticket')
            if not order_id:
                return False
            
            # Check if order exists in MetaTrader
            positions = self.meta_trader.get_position_by_ticket(int(order_id))
            
            if positions and len(positions) > 0:
                # Order exists in MetaTrader but marked as closed locally
                if order.get('status') == 'closed':
                    logger.warning(f"⚠️ Order {order_id} exists in MetaTrader but marked as closed locally - fixing status")
                    order['status'] = 'active'
                    if 'closed_at' in order:
                        del order['closed_at']
                
                # Also update order_type from MetaTrader comment
                self._update_order_type_from_mt5_comment(order)
                
                return True
            else:
                # Order doesn't exist in MetaTrader but marked as active locally
                if order.get('status') == 'active':
                    logger.warning(f"⚠️ Order {order_id} marked as active locally but not found in MetaTrader - may need verification")
                    # Don't automatically mark as closed, just log the warning
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error verifying order status with MetaTrader: {str(e)}")
            return False

    def _fix_incorrectly_closed_orders(self, cycle):
        """Check and fix any orders that are incorrectly marked as closed but still exist in MetaTrader"""
        try:
            fixed_count = 0
            for order in cycle.orders:
                if order.get('status') == 'closed':
                    # Check if this order actually exists in MetaTrader
                    if self._verify_order_status_with_mt5(order):
                        fixed_count += 1
                        logger.info(f"✅ Fixed incorrectly closed order {order.get('order_id')} in cycle {cycle.cycle_id}")
            
            if fixed_count > 0:
                logger.info(f"✅ Fixed {fixed_count} incorrectly closed orders in cycle {cycle.cycle_id}")
            
            return fixed_count
            
        except Exception as e:
            logger.error(f"❌ Error fixing incorrectly closed orders: {str(e)}")
            return 0

    def _update_order_type_from_mt5_comment(self, order):
        """Update order_type based on MetaTrader comment to ensure consistency"""
        try:
            order_id = order.get('order_id') or order.get('ticket')
            if not order_id:
                return False
            
            # Get position data from MetaTrader to check comment
            positions = self.meta_trader.get_position_by_ticket(int(order_id))
            
            if positions and len(positions) > 0:
                position = positions[0]
                comment = getattr(position, 'comment', '')
                
                logger.debug(f"📊 Checking MT5 comment for order {order_id}: '{comment}'")
                
                # Update order_type based on comment
                if 'MoveGuard_Grid_0' in comment:
                    old_type = order.get('order_type', 'unknown')
                    order['order_type'] = 'grid_0'
                    order['is_initial'] = True
                    order['is_grid'] = True
                    order['grid_level'] = 0
                    logger.debug(f"📊 Updated order {order_id} type: {old_type} → grid_0 (from MT5 comment)")
                    return True
                elif 'MoveGuard_Grid_' in comment:
                    # Extract grid level from comment
                    try:
                        grid_level = int(comment.split('MoveGuard_Grid_')[1])
                        old_type = order.get('order_type', 'unknown')
                        order['order_type'] = f'grid_{grid_level}'
                        order['grid_level'] = grid_level
                        order['is_grid'] = True
                        order['is_initial'] = False
                        logger.debug(f"📊 Updated order {order_id} type: {old_type} → grid_{grid_level} (from MT5 comment)")
                        return True
                    except (IndexError, ValueError):
                        # Fallback to generic grid
                        old_type = order.get('order_type', 'unknown')
                        order['order_type'] = 'grid'
                        order['is_grid'] = True
                        order['is_initial'] = False
                        logger.debug(f"📊 Updated order {order_id} type: {old_type} → grid (fallback from MT5 comment)")
                        return True
                else:
                    logger.debug(f"📊 No MoveGuard comment found for order {order_id}: '{comment}'")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error updating order_type from MT5 comment: {str(e)}")
            return False

    def _fix_order_types_in_cycle(self, cycle):
        """Fix order types for all orders in a cycle based on MetaTrader comments"""
        try:
            fixed_count = 0
            for order in cycle.orders:
                if order.get('status') == 'active':
                    if self._update_order_type_from_mt5_comment(order):
                        fixed_count += 1
                        logger.info(f"✅ Fixed order type for order {order.get('order_id')} in cycle {cycle.cycle_id}: {order.get('order_type')}")
            
            if fixed_count > 0:
                logger.info(f"✅ Fixed order types for {fixed_count} orders in cycle {cycle.cycle_id}")
            
            return fixed_count
            
        except Exception as e:
            logger.error(f"❌ Error fixing order types in cycle: {str(e)}")
            return 0

    def _ensure_order_types_from_mt5_comments(self, cycle):
        """Ensure all order types are correctly set from MT5 comments before any processing"""
        try:
            updated_count = 0
            for order in cycle.orders:
                if order.get('status') == 'active':
                    # Always try to update from MT5 comment first
                    if self._update_order_type_from_mt5_comment(order):
                        updated_count += 1
            
            if updated_count > 0:
                logger.info(f"📊 Updated {updated_count} order types from MT5 comments for cycle {cycle.cycle_id}")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ Error ensuring order types from MT5 comments: {str(e)}")
            return 0

    def _fix_missing_grid_levels_in_cycle(self, cycle):
        """Fix missing grid_level fields for grid orders in a cycle"""
        try:
            fixed_count = 0
            for order in cycle.orders:
                if order.get('status') == 'active' and order.get('is_grid') and order.get('grid_level') is None:
                    if self._update_order_type_from_mt5_comment(order):
                        fixed_count += 1
                        logger.info(f"✅ Fixed grid_level for order {order.get('order_id')} in cycle {cycle.cycle_id}: level={order.get('grid_level')}")
            
            if fixed_count > 0:
                logger.info(f"✅ Fixed grid_level for {fixed_count} orders in cycle {cycle.cycle_id}")
            
            return fixed_count
            
        except Exception as e:
            logger.error(f"❌ Error fixing grid_level in cycle: {str(e)}")
            return 0

    def _calculate_proper_boundaries(self, cycle, current_price: float):
        """Calculate proper upper and lower boundaries according to MoveGuard rules"""
        try:
            pip_value = self._get_pip_value()
            zone_threshold = self.get_cycle_zone_threshold_pips(cycle) * pip_value
            
            # Get active orders to determine cycle state
            active_orders = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
            grid_orders = self._get_grid_orders_safely(cycle)
            active_grid_orders = [o for o in grid_orders if o.get('status') == 'active']
            
            # Check if we have any grid orders
            has_grid_orders = len(grid_orders) > 0
            
            if not has_grid_orders:
                # No grid orders yet - use initial order entry price
                if active_orders:
                    initial_order = None
                    for order in active_orders:
                        if order.get('is_initial') or 'grid_0' in order.get('order_type', '').lower() or 'initial' in order.get('order_type', '').lower():
                            initial_order = order
                            break
                    
                    if initial_order:
                        entry_price = initial_order.get('price', cycle.entry_price)
                        
                        if cycle.direction == 'BUY':
                            # For BUY cycles: upper = entry + zone_threshold, lower = entry - zone_threshold
                            upper = entry_price + zone_threshold
                            lower = entry_price - zone_threshold
                        else:  # SELL
                            # For SELL cycles: upper = entry + zone_threshold, lower = entry - zone_threshold
                            upper = entry_price + zone_threshold
                            lower = entry_price - zone_threshold
                    else:
                        # Fallback to cycle entry price
                        upper = cycle.entry_price + zone_threshold
                        lower = cycle.entry_price - zone_threshold
                else:
                    # No orders yet - use cycle entry price
                    upper = cycle.entry_price + zone_threshold
                    lower = cycle.entry_price - zone_threshold
            else:
                # We have grid orders - adjust boundaries based on direction
                if cycle.direction == 'BUY':
                    # For BUY cycles with grid orders: upper stays same, lower = upper - zone_threshold
                    trailing_sl = cycle.trailing_stop_loss
                    upper = trailing_sl + zone_threshold
                    lower = trailing_sl 
                else:  # SELL
                    # For SELL cycles with grid orders: lower stays same, upper = lower + zone_threshold
                    trailing_sl = cycle.trailing_stop_loss
                    lower = trailing_sl - zone_threshold
                    upper = trailing_sl 
            
            # Update zone data
            if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                cycle.zone_data = {}
            
            cycle.zone_data['upper_boundary'] = upper
            cycle.zone_data['lower_boundary'] = lower
            cycle.zone_data['base_price'] = (upper + lower) / 2  # Center point
            
            logger.debug(f"✅ Calculated boundaries for cycle {cycle.cycle_id}: upper={upper:.5f}, lower={lower:.5f}, has_grid_orders={has_grid_orders}")
            
            return upper, lower
            
        except Exception as e:
            logger.error(f"❌ Error calculating proper boundaries: {str(e)}")
            # Fallback to original calculation
            pip_value = self._get_pip_value()
            zone_threshold = self.get_cycle_zone_threshold_pips(cycle) * pip_value
            upper = cycle.entry_price + zone_threshold
            lower = cycle.entry_price - zone_threshold
            return upper, lower

    def _update_trailing_stop_loss(self, cycle, current_price: float):
        """Update trailing stop-loss based on highest/lowest order price with zone boundary constraints"""
        try:
            pip_value = self._get_pip_value()
            zone_threshold = self.get_cycle_zone_threshold_pips(cycle) * pip_value
            
            # Get current zone boundaries
            upper = cycle.zone_data.get('upper_boundary', 0.0) if hasattr(cycle, 'zone_data') else 0.0
            lower = cycle.zone_data.get('lower_boundary', 0.0) if hasattr(cycle, 'zone_data') else 0.0
            
            if cycle.direction == 'BUY':
                # For BUY cycles: trailing SL below highest buy price
                active_buy_orders = [o for o in getattr(cycle, 'orders', []) 
                                   if o.get('status') == 'active' and o.get('direction') == 'BUY']
                
                if not active_buy_orders:
                    return
                
                # Find the highest buy price
                highest_buy_price = max([o.get('price', 0.0) for o in active_buy_orders])
                
                # Calculate new trailing stop-loss (below highest buy)
                calculated_trailing_sl = highest_buy_price - zone_threshold
                
                # Apply zone boundary constraint: SL should not be below zone top
                # Special handling for "NO_MOVE" mode with BUY cycles
                if self.zone_movement_mode == 'NO_MOVE' and cycle.direction == 'BUY':
                    # In NO_MOVE mode, keep trailing SL fixed at top boundary
                    new_trailing_sl = upper
                    logger.info(f"🎯 NO_MOVE mode: Trailing SL fixed at zone top for BUY cycle {cycle.cycle_id}: {new_trailing_sl:.5f}")
                # Special handling for "Move Down Only" mode with BUY cycles
                elif self.zone_movement_mode == 'Move Down Only' and cycle.direction == 'BUY':
                    # In Move Down Only mode, keep trailing SL at top boundary to prevent infinite loop
                    new_trailing_sl = upper
                    logger.info(f"🎯 Move Down Only mode: Trailing SL fixed at zone top for BUY cycle {cycle.cycle_id}: {new_trailing_sl:.5f}")
                elif calculated_trailing_sl < upper:
                    new_trailing_sl = upper
                    logger.info(f"🎯 Trailing SL constrained to zone top for BUY cycle {cycle.cycle_id}: calculated={calculated_trailing_sl:.5f}, constrained={new_trailing_sl:.5f}")
                else:
                    new_trailing_sl = calculated_trailing_sl
                
                # Update cycle's trailing SL
                if not hasattr(cycle, 'trailing_stop_loss') or cycle.trailing_stop_loss is None:
                    cycle.trailing_stop_loss = new_trailing_sl
                    logger.info(f"🎯 Initial trailing SL set for BUY cycle {cycle.cycle_id}: {new_trailing_sl:.5f}")
                    # Update database with new trailing SL
                    # self._update_cycle_in_database(cycle)
                elif cycle.trailing_stop_loss is not None and new_trailing_sl > cycle.trailing_stop_loss:
                    # Only move SL up, never down
                    old_sl = cycle.trailing_stop_loss
                    cycle.trailing_stop_loss = new_trailing_sl
                    logger.info(f"🎯 Trailing SL moved up for BUY cycle {cycle.cycle_id}: {old_sl:.5f} → {new_trailing_sl:.5f}")
                    # Update database with new trailing SL
                    # self._update_cycle_in_database(cycle)
                
                # Update highest buy price
                old_highest = cycle.highest_buy_price if hasattr(cycle, 'highest_buy_price') and cycle.highest_buy_price is not None else 0.0
                if not hasattr(cycle, 'highest_buy_price') or cycle.highest_buy_price is None:
                    cycle.highest_buy_price = highest_buy_price
                else:
                    cycle.highest_buy_price = max(cycle.highest_buy_price, highest_buy_price)
                
                if cycle.highest_buy_price > old_highest:
                    logger.debug(f"🎯 Highest buy price updated for cycle {cycle.cycle_id}: {old_highest:.5f} → {cycle.highest_buy_price:.5f}")
                    # Update database with new highest buy price
                    # self._update_cycle_in_database(cycle)
                
            elif cycle.direction == 'SELL':
                # For SELL cycles: trailing SL above lowest sell price
                active_sell_orders = [o for o in getattr(cycle, 'orders', []) 
                                    if o.get('status') == 'active' and o.get('direction') == 'SELL']
                
                if not active_sell_orders:
                    return
                
                # Find the lowest sell price
                lowest_sell_price = min([o.get('price', 999999.0) for o in active_sell_orders])
                
                # Skip if we got the default value (no valid sell orders)
                if lowest_sell_price >= 999999.0:
                    return
                
                # Calculate new trailing stop-loss (above lowest sell)
                calculated_trailing_sl = lowest_sell_price + zone_threshold
                
                # Apply zone boundary constraint: SL should not be above zone bottom
                # Special handling for "NO_MOVE" mode with SELL cycles
                if self.zone_movement_mode == 'NO_MOVE' and cycle.direction == 'SELL':
                    # In NO_MOVE mode, keep trailing SL fixed at bottom boundary
                    new_trailing_sl = lower
                    logger.info(f"🎯 NO_MOVE mode: Trailing SL fixed at zone bottom for SELL cycle {cycle.cycle_id}: {new_trailing_sl:.5f}")
                # Special handling for "Move Up Only" mode with SELL cycles
                elif self.zone_movement_mode == 'Move Up Only' and cycle.direction == 'SELL':
                    # In Move Up Only mode, keep trailing SL at bottom boundary to prevent infinite loop
                    new_trailing_sl = lower
                    logger.info(f"🎯 Move Up Only mode: Trailing SL fixed at zone bottom for SELL cycle {cycle.cycle_id}: {new_trailing_sl:.5f}")
                    logger.info(f"🔍 DEBUG: lowest_sell_price={lowest_sell_price:.5f}, zone_threshold={zone_threshold:.5f}, calculated_trailing_sl={calculated_trailing_sl:.5f}, lower_boundary={lower:.5f}")
                elif calculated_trailing_sl > lower:
                    new_trailing_sl = lower
                    logger.info(f"🎯 Trailing SL constrained to zone bottom for SELL cycle {cycle.cycle_id}: calculated={calculated_trailing_sl:.5f}, constrained={new_trailing_sl:.5f}")
                else:
                    new_trailing_sl = calculated_trailing_sl
                
                # Update cycle's trailing SL
                if not hasattr(cycle, 'trailing_stop_loss') or cycle.trailing_stop_loss is None:
                    cycle.trailing_stop_loss = new_trailing_sl
                    logger.info(f"🎯 Initial trailing SL set for SELL cycle {cycle.cycle_id}: {new_trailing_sl:.5f}")
                    # Update database with new trailing SL
                    # self._update_cycle_in_database(cycle)
                elif cycle.trailing_stop_loss is not None and new_trailing_sl < cycle.trailing_stop_loss:
                    # Only move SL down, never up
                    old_sl = cycle.trailing_stop_loss
                    cycle.trailing_stop_loss = new_trailing_sl
                    logger.info(f"🎯 Trailing SL moved down for SELL cycle {cycle.cycle_id}: {old_sl:.5f} → {new_trailing_sl:.5f}")
                    # Update database with new trailing SL
                    # self._update_cycle_in_database(cycle)
                
                # Update lowest sell price
                old_lowest = cycle.lowest_sell_price if hasattr(cycle, 'lowest_sell_price') and cycle.lowest_sell_price is not None else 999999.0
                if not hasattr(cycle, 'lowest_sell_price') or cycle.lowest_sell_price is None:
                    cycle.lowest_sell_price = lowest_sell_price
                else:
                    cycle.lowest_sell_price = min(cycle.lowest_sell_price, lowest_sell_price)
                
                if cycle.lowest_sell_price < old_lowest:
                    logger.debug(f"🎯 Lowest sell price updated for cycle {cycle.cycle_id}: {old_lowest:.5f} → {cycle.lowest_sell_price:.5f}")
                    # Update database with new lowest sell price
                    # self._update_cycle_in_database(cycle)
            
        except Exception as e:
            logger.error(f"❌ Error updating trailing stop-loss: {str(e)}")

    def _check_trailing_stop_loss(self, cycle, current_price: float) -> bool:
        """Check if trailing stop-loss has been hit"""
        try:
            if not hasattr(cycle, 'trailing_stop_loss') or cycle.trailing_stop_loss is None:
                return False
            
            if cycle.direction == 'BUY':
                if current_price <= cycle.trailing_stop_loss:
                    logger.info(f"🎯 Trailing SL hit for BUY cycle {cycle.cycle_id}: price {current_price:.5f} <= SL {cycle.trailing_stop_loss:.5f}")
                    return True
            elif cycle.direction == 'SELL':
                if current_price >= cycle.trailing_stop_loss:
                    logger.info(f"🎯 Trailing SL hit for SELL cycle {cycle.cycle_id}: price {current_price:.5f} >= SL {cycle.trailing_stop_loss:.5f}")
                    logger.info(f"🔍 DEBUG TSL: zone_movement_mode={self.zone_movement_mode}, lower_boundary={cycle.zone_data.get('lower_boundary', 0.0):.5f}, upper_boundary={cycle.zone_data.get('upper_boundary', 0.0):.5f}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking trailing stop-loss: {str(e)}")
            return False

    def _handle_trailing_stop_loss_trigger(self, cycle, current_price: float):
        """Handle when trailing stop-loss is triggered"""
        try:
            if cycle.direction == 'BUY':
                logger.info(f"🎯 Trailing SL triggered for BUY cycle {cycle.cycle_id} - closing all BUY orders")
                
               
                # Move zone: new top = highest_buy_price, new bottom = trailing_sl_price
                pip_value = self._get_pip_value()
                zone_threshold = self.get_cycle_zone_threshold_pips(cycle) * pip_value

                highest_buy_price = max([o.get('price', 0.0) for o in getattr(cycle, 'orders', []) 
                                if o.get('status') == 'active' and o.get('direction') == 'BUY'])
                
                # Initialize zone movement variables
                new_top = cycle.zone_data.get('upper_boundary', 0.0)
                new_bottom = cycle.zone_data.get('lower_boundary', 0.0)
                
                if self.zone_movement_mode == 'Move Both Sides' or self.zone_movement_mode == 'Move Up Only':
                    if highest_buy_price is not None:
                        new_bottom = highest_buy_price - zone_threshold
                        new_top = highest_buy_price
                    else:
                        new_bottom = cycle.zone_data.get('lower_boundary', 0.0)
                        new_top = cycle.zone_data.get('upper_boundary', 0.0)
                elif self.zone_movement_mode == 'Move Down Only':
                    # In Move Down Only mode with BUY cycles, don't move zone up
                    # Keep zone boundaries unchanged to prevent infinite loop
                    new_top = cycle.zone_data.get('upper_boundary', 0.0)
                    new_bottom = cycle.zone_data.get('lower_boundary', 0.0)
                    logger.info(f"🎯 Move Down Only mode: Zone boundaries unchanged for BUY cycle {cycle.cycle_id}")
                
                # Update zone data
                if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                    cycle.zone_data = {}
                
                old_base = cycle.zone_data.get('base_price', (new_top + new_bottom) / 2)
                cycle.zone_data.update({
                    'base_price': (new_top + new_bottom) / 2,
                    'upper_boundary': new_top,
                    'lower_boundary': new_bottom,
                    'last_movement': {
                        'direction': 'TRAILING_SL_BUY',
                        'old_base': old_base,
                        'new_base': (new_top + new_bottom) / 2,
                        'highest_buy': new_top,
                        'trailing_sl': new_bottom,
                        'timestamp': datetime.datetime.now().isoformat()
                    }
                })
                
                 # Close all active BUY orders
                asyncio.create_task(self._close_all_cycle_orders(cycle))
                
                # Reset trailing SL for next cycle
                cycle.trailing_stop_loss = None
                cycle.highest_buy_price = 0.0
                logger.info(f"✅ Zone moved after BUY trailing SL: new_top={new_top:.5f}, new_bottom={new_bottom:.5f}")
            elif cycle.direction == 'SELL':
                logger.info(f"🎯 Trailing SL triggered for SELL cycle {cycle.cycle_id} - closing all SELL orders")
                # Move zone: new top = trailing_sl_price, new bottom = lowest_sell_price
                pip_value = self._get_pip_value()
                zone_threshold = self.get_cycle_zone_threshold_pips(cycle) * pip_value
               
                lowest_sell_price = min([o.get('price', 999999.0) for o in getattr(cycle, 'orders', []) 
                                if o.get('status') == 'active' and o.get('direction') == 'SELL'])
                
                # Initialize zone movement variables
                new_top = cycle.zone_data.get('upper_boundary', 0.0)
                new_bottom = cycle.zone_data.get('lower_boundary', 0.0)
                
                if self.zone_movement_mode=='Move Both Sides' or self.zone_movement_mode=='Move Down Only':
                    if lowest_sell_price is not None:
                        new_top = lowest_sell_price + zone_threshold
                        new_bottom = lowest_sell_price
                    else:
                        new_top = cycle.zone_data.get('upper_boundary', 0.0)
                        new_bottom = cycle.zone_data.get('lower_boundary', 0.0)
                elif self.zone_movement_mode == 'Move Up Only':
                    # In Move Up Only mode with SELL cycles, don't move zone down
                    # Keep zone boundaries unchanged to prevent infinite loop
                    new_top = cycle.zone_data.get('upper_boundary', 0.0)
                    new_bottom = cycle.zone_data.get('lower_boundary', 0.0)
                    logger.info(f"🎯 Move Up Only mode: Zone boundaries unchanged for SELL cycle {cycle.cycle_id}")
                
                # Update zone data
                if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                    cycle.zone_data = {}
                
                old_base = cycle.zone_data.get('base_price', (new_top + new_bottom) / 2)
                cycle.zone_data.update({
                    'base_price': (new_top + new_bottom) / 2,
                    'upper_boundary': new_top,
                    'lower_boundary': new_bottom,
                    'last_movement': {
                        'direction': 'TRAILING_SL_SELL',
                        'old_base': old_base,
                        'new_base': (new_top + new_bottom) / 2,
                        'lowest_sell': new_bottom,
                        'trailing_sl': new_top,
                        'timestamp': datetime.datetime.now().isoformat()
                    }
                })
                
               # Close all active SELL orders
                asyncio.create_task(self._close_all_cycle_orders(cycle))
                
                # Reset trailing SL for next cycle
                cycle.trailing_stop_loss = None
                cycle.lowest_sell_price = 0.0
            
                logger.info(f"✅ Zone moved after SELL trailing SL: new_top={new_top:.5f}, new_bottom={new_bottom:.5f}")
            
        except Exception as e:
            logger.error(f"❌ Error handling trailing stop-loss trigger: {str(e)}")

    def _log_trailing_stop_loss_status(self, cycle, current_price: float):
        """Log current trailing stop-loss status for debugging"""
        try:
            if not hasattr(cycle, 'trailing_stop_loss') or cycle.trailing_stop_loss is None:
                return
            
            pip_value = self._get_pip_value()
            zone_threshold = self.get_cycle_zone_threshold_pips(cycle) * pip_value
            
            if cycle.direction == 'BUY':
                # Get active buy orders
                active_buy_orders = [o for o in getattr(cycle, 'orders', []) 
                                   if o.get('status') == 'active' and o.get('direction') == 'BUY']
                
                if active_buy_orders:
                    highest_buy_price = max([o.get('price', 0.0) for o in active_buy_orders])
                    distance_to_sl = highest_buy_price - cycle.trailing_stop_loss
                    distance_in_pips = distance_to_sl / pip_value
                    
                    logger.debug(f"🎯 Trailing SL Status - BUY Cycle {cycle.cycle_id}: "
                               f"Current Price: {current_price:.5f}, "
                               f"Highest Buy: {highest_buy_price:.5f}, "
                               f"Trailing SL: {cycle.trailing_stop_loss:.5f}, "
                               f"Distance: {distance_in_pips:.1f} pips")
                               
            elif cycle.direction == 'SELL':
                # Get active sell orders
                active_sell_orders = [o for o in getattr(cycle, 'orders', []) 
                                    if o.get('status') == 'active' and o.get('direction') == 'SELL']
                
                if active_sell_orders:
                    lowest_sell_price = min([o.get('price', 999999.0) for o in active_sell_orders])
                    # Skip if we got the default value (no valid sell orders)
                    if lowest_sell_price < 999999.0:
                        distance_to_sl = cycle.trailing_stop_loss - lowest_sell_price
                        distance_in_pips = distance_to_sl / pip_value
                        
                        logger.debug(f"🎯 Trailing SL Status - SELL Cycle {cycle.cycle_id}: "
                                   f"Current Price: {current_price:.5f}, "
                                   f"Lowest Sell: {lowest_sell_price:.5f}, "
                                   f"Trailing SL: {cycle.trailing_stop_loss:.5f}, "
                                   f"Distance: {distance_in_pips:.1f} pips")
                
        except Exception as e:
            logger.error(f"❌ Error logging trailing stop-loss status: {str(e)}")

    def _calculate_price_level(self):
        """Calculate the price level based on cycle_interval_pips"""
        try:
            next_up_level = self.last_cycle_price + (self.cycle_interval * self._get_pip_value())
            next_down_level = self.last_cycle_price - (self.cycle_interval * self._get_pip_value())
            return next_up_level, next_down_level
        except Exception as e:
            logger.error(f"❌ Error calculating price level: {str(e)}")
            return 0.0, 0.0

    def _get_cycles_at_level(self, price_level, direction=None):
        """Get all cycles at a specific price level, optionally filtered by direction"""
        try:
            cycles_at_level = []
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            # Use a more appropriate tolerance - 1 pip instead of 10% of pip value
            pip_value = self._get_pip_value()
            tolerance = pip_value * 1.0  # 1 pip tolerance for better cycle detection
            
            for cycle in active_cycles:
                # Check if cycle is at the same price level with appropriate tolerance
                if abs(cycle.entry_price - price_level) <= tolerance:
                    # Filter by direction if specified
                    if direction is None or cycle.direction == direction:
                        cycles_at_level.append(cycle)
                        logger.debug(f"Found cycle {cycle.cycle_id} at level {price_level} (entry_price: {cycle.entry_price}, direction: {cycle.direction}, tolerance: {tolerance})")
            
            return cycles_at_level
        except Exception as e:
            logger.error(f"❌ Error getting cycles at level: {str(e)}")
            return []

    def _has_cycle_at_level(self, price_level, direction=None):
        """Check if there's already a cycle at the specified price level with the same direction"""
        try:
            cycles_at_level = self._get_cycles_at_level(price_level, direction)
            return len(cycles_at_level) > 0
        except Exception as e:
            logger.error(f"❌ Error checking for cycles at level: {str(e)}")
            return False

    def _get_cycle_level_key(self, price_level):
        """Get a standardized level key for cycle tracking"""
        try:
            # Round to 4 decimal places for better precision while handling floating point differences
            # This ensures that small floating point differences don't create separate levels
            return round(price_level, 4)
        except Exception as e:
            logger.error(f"❌ Error creating level key: {str(e)}")
            return price_level

    def _add_cycle_level(self, price_level):
        """Add a price level to the active cycle levels tracking"""
        try:
            level_key = self._get_cycle_level_key(price_level)
            self.active_cycle_levels.add(level_key)
            logger.debug(f"✅ Added level {level_key} to active cycle levels tracking")
        except Exception as e:
            logger.error(f"❌ Error adding cycle level: {str(e)}")

    def _remove_cycle_level(self, price_level):
        """Remove a price level from the active cycle levels tracking"""
        try:
            level_key = self._get_cycle_level_key(price_level)
            if level_key in self.active_cycle_levels:
                self.active_cycle_levels.remove(level_key)
                logger.debug(f"🗑️ Removed level {level_key} from active cycle levels tracking")
        except Exception as e:
            logger.error(f"❌ Error removing cycle level: {str(e)}")

    def _cleanup_cycle_levels(self):
        """Clean up active cycle levels for closed cycles"""
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            active_prices = set()
            
            # Collect all active cycle entry prices
            for cycle in active_cycles:
                if hasattr(cycle, 'entry_price') and cycle.entry_price:
                    level_key = self._get_cycle_level_key(cycle.entry_price)
                    active_prices.add(level_key)
            
            # Remove levels that no longer have active cycles
            levels_to_remove = self.active_cycle_levels - active_prices
            for level in levels_to_remove:
                self.active_cycle_levels.remove(level)
                logger.debug(f"🧹 Cleaned up inactive level {level} from tracking")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up cycle levels: {str(e)}")

    def _is_level_active(self, price_level):
        """Check if a price level is already active (has a cycle)"""
        try:
            level_key = self._get_cycle_level_key(price_level)
            return level_key in self.active_cycle_levels
        except Exception as e:
            logger.error(f"❌ Error checking if level is active: {str(e)}")
            return False

    async def _check_cycle_intervals(self, current_price):
        """Check and create cycles at defined intervals"""
        try:
            if not current_price:
                return
            if not hasattr(self, 'last_cycle_price') or self.last_cycle_price is None:
                # Try to get last cycle price from database, but if none exists, use current price
                self.last_cycle_price = self._get_last_cycle_price()
                if self.last_cycle_price is None:
                    # No previous cycles exist, use current price as starting point
                    self.last_cycle_price = current_price
                    logger.info(f"🔄 No previous cycles found, using current price {current_price:.5f} as starting point for auto cycle placement")
                    # Don't return here - continue to process cycle creation on next price movement
                    return
                # Continue processing with the retrieved last_cycle_price
            # Calculate the current price level
            next_up_level, next_down_level = self._calculate_price_level()
            current_level = next_up_level if current_price > self.last_cycle_price else next_down_level
            direction = "BUY" if current_price > self.last_cycle_price else "SELL"
            
            # Debug logging for cycle creation
            logger.debug(f"🔍 Cycle interval check: current_price={current_price:.5f}, last_cycle_price={self.last_cycle_price:.5f}, "
                        f"direction={direction}, current_level={current_level:.5f}, next_up={next_up_level:.5f}, next_down={next_down_level:.5f}")
            
            
            
            # Check if we can create more cycles (respect max_active_cycles limit)
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            max_active_cycles = self.get_cycle_config_value(None, 'max_active_cycles', self.max_active_cycles)
            if len(active_cycles) >= max_active_cycles:
                logger.info(f"🎯 Max active cycles ({max_active_cycles}) reached, skipping interval cycle creation. Current active cycles: {len(active_cycles)}")
                if direction == "BUY" and current_level > self.meta_trader.get_ask(self.symbol):
                    return
                if direction == "SELL" and current_level < self.meta_trader.get_bid(self.symbol):
                    return
                # Update last cycle price
                self.last_cycle_price = current_level

                return
            
            if not self.auto_place_cycles:
                logger.debug("Auto place cycles is disabled, skipping interval cycle creation")
                # Check if we should create a cycle at this level
                if direction == "BUY" and current_level > self.meta_trader.get_ask(self.symbol):
                    return 
                if direction == "SELL" and current_level < self.meta_trader.get_bid(self.symbol):
                    return 
                # Update last cycle price
                self.last_cycle_price = current_price
                return
            
            # ATOMIC CHECK: Double-check for existing cycles with exact price matching
            has_existing_cycle_same_direction = self._has_cycle_at_level(current_level, direction)
            
            # Additional atomic check: verify no cycles exist at exact same price and direction
            exact_duplicate_exists = False
            for cycle in active_cycles:
                if (hasattr(cycle, 'entry_price') and hasattr(cycle, 'direction') and
                    cycle.direction == direction and 
                    abs(cycle.entry_price - current_level) < 0.00001):  # Exact match
                    exact_duplicate_exists = True
                    logger.warning(f"🚫 ATOMIC CHECK: Exact duplicate cycle found at {current_level:.5f} direction {direction}")
                    break
            
            # Enhanced logging for debugging cycle creation decisions
            logger.debug(f"🔍 Cycle creation check: level={current_level:.5f}, direction={direction}, "
                        f"has_existing_cycle_same_direction={has_existing_cycle_same_direction}, "
                        f"exact_duplicate_exists={exact_duplicate_exists}, "
                        f"last_cycle_price={self.last_cycle_price:.5f}")
            
            if not has_existing_cycle_same_direction and not exact_duplicate_exists:
                # Additional validation: ensure we're not creating cycles too close to existing ones of the same direction
                min_distance = self.cycle_interval * self._get_pip_value() * 0.8  # 80% of cycle interval
                too_close = False
                
                for cycle in active_cycles:
                    # Only check distance for cycles of the same direction
                    if cycle.direction == direction:
                        distance = abs(cycle.entry_price - current_level)
                        if distance < min_distance:
                            too_close = True
                            logger.debug(f"🚫 Skipping cycle creation at {current_level:.5f} - too close to existing {direction} cycle at {cycle.entry_price:.5f} (distance: {distance:.5f})")
                            break
                
                if not too_close:
                    logger.info(f"🔄 No existing cycle found at level {current_level:.5f} for {direction} direction - creating new cycle")
                    # Create new cycle with initial order based on price movement direction
                    success = await self._create_interval_cycle_sync(direction, current_level)
                    if success:
                        # Add level to active tracking
                        self._add_cycle_level(current_level)
                        # Update last_cycle_price to prevent immediate re-creation
                        self.last_cycle_price = current_level
                        logger.info(f"✅ Successfully created {direction} cycle at level {current_level:.5f}")
                   
                else:
                    # Update last_cycle_price to prevent getting stuck
                    self.last_cycle_price = current_level
            else:
                logger.debug(f"🔄 Cycle already exists at level {current_level:.5f} for {direction} direction - skipping creation")
                # Update last_cycle_price to prevent getting stuck
                self.last_cycle_price = current_level
                
        except Exception as e:
            logger.error(f"❌ Error checking cycle intervals: {str(e)}")
            logger.error(traceback.format_exc())

    async def _create_interval_cycle_sync(self, direction: str, price: float) -> bool:
        """Create a new cycle with initial order based on price movement"""
        try:
            # Check if we should create a cycle at this level
            if direction == "BUY" and price > self.meta_trader.get_ask(self.symbol):
                logger.debug(f"🔄 Skipping BUY cycle creation at {price} - price too high")
                return False  # Don't create BUY cycles below current price
            if direction == "SELL" and price < self.meta_trader.get_bid(self.symbol):
                logger.debug(f"🔄 Skipping SELL cycle creation at {price} - price too low")
                return False  # Don't create SELL cycles above current price
            
            # Double-check if we can create more cycles (safety check)
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            max_active_cycles = self.get_cycle_config_value(None, 'max_active_cycles', self.max_active_cycles)
            if len(active_cycles) >= max_active_cycles:
                logger.warning(f"Cannot create new cycle: max cycles ({max_active_cycles}) reached")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error creating interval cycle: {str(e)}")
            return False

        # Create order parameters for the interval cycle
        order_params = {
            'username': 'system',
            'sent_by_admin': True,
            'user_id': f"interval_cycle_at_{price}",
            'price_level': price
        }

        # Place the order using MoveGuard's order placement functions
        try:
            logger.info(f"🔄 Placing {direction} order for interval cycle at price {price}")
            
            if direction == "BUY":
                current_ask = self.meta_trader.get_ask(self.symbol)
                success = await self._place_buy_order(order_params, current_ask, "cycle_entry")
            else:  # SELL
                current_bid = self.meta_trader.get_bid(self.symbol)
                success = await self._place_sell_order(order_params, current_bid, "cycle_entry")
                
            if success:
                # Update last cycle price
                self.last_cycle_price = price
                logger.info(f"✅ Interval cycle created successfully for {direction} at {price}")
                return True
            else:
                logger.error(f"❌ Failed to create interval cycle for {direction} at {price}")
                return False
                
        except Exception as order_error:
            logger.error(f"❌ Exception during {direction} order placement for interval cycle: {order_error}")
            return False

    def _get_last_cycle_price(self):
        """Get the last cycle price from the database and set it as the last cycle price"""
        try:
            last_cycle_price = 0
            last_cycle_price_timestamp = 0
            
            # Go through the cycles and get the last cycle price based on the initial order open datetime
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            for cycle in active_cycles:
                if hasattr(cycle, 'initial_order_open_datetime') and cycle.initial_order_open_datetime:
                    # Convert datetime string to timestamp for comparison
                    try:
                        cycle_timestamp = datetime.datetime.fromisoformat(cycle.initial_order_open_datetime.replace('Z', '+00:00')).timestamp()
                        if cycle_timestamp > last_cycle_price_timestamp:
                            last_cycle_price_timestamp = cycle_timestamp
                            last_cycle_price = cycle.entry_price
                    except Exception as e:
                        logger.warning(f"Error parsing cycle datetime: {e}")
                        continue
            
            # If no cycles found, use current price
            if last_cycle_price == 0:
                current_price = self._get_current_price()
                if current_price:
                    last_cycle_price = current_price
                    logger.info(f"No existing cycles found, using current price as last cycle price: {last_cycle_price}")
                else:
                    logger.warning("No current price available, using 0 as last cycle price")
            
            return last_cycle_price
            
        except Exception as e:
            logger.error(f"❌ Error getting last cycle price: {str(e)}")
            return 0.0

    def _update_magic_number_if_needed(self, cfg):
        """Update magic number in PocketBase if it has changed"""
        try:
            if 'magic_number' in cfg and cfg['magic_number'] != self.bot.magic_number:
                # Update magic number in PocketBase
                if hasattr(self.client, 'update_bot_magic_number'):
                    result = self.client.update_bot_magic_number(self.bot.id, cfg['magic_number'])
                    if result:
                        self.bot.magic_number = cfg['magic_number']
                        logger.info(f"✅ Magic number updated to {cfg['magic_number']} in PocketBase")
                        self.meta_trader.magic_number = cfg['magic_number']
                        logger.info(f"✅ Magic number set on MetaTrader instance")
                    else:
                        logger.error(f"❌ Failed to update magic number in PocketBase")
                else:
                    logger.warning(f"⚠️ Client does not support update_bot_magic_number method")
        except Exception as e:
            logger.error(f"❌ Error updating magic number: {str(e)}")

    def _update_strategy_symbol(self, new_symbol: str) -> bool:
        """Update the strategy symbol and re-initialize dependent components"""
        try:
            # Validate new symbol
            if not self._validate_symbol(new_symbol):
                return False
            
            old_symbol = self.symbol
            self.symbol = new_symbol
            
            # Re-initialize symbol-dependent components
            self._reinitialize_symbol_dependent_components()
            
            # Update MetaTrader symbol info
            self._update_metatrader_symbol_info()
            
            logger.info(f"🔄 MoveGuard symbol updated: {old_symbol} → {new_symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating symbol: {str(e)}")
            return False

    def _validate_symbol(self, symbol: str) -> bool:
        """Validate that a symbol is accessible and valid in MetaTrader"""
        try:
            # Check if symbol exists in MetaTrader
            symbol_info = self.meta_trader.get_symbol_info(symbol)
            if not symbol_info:
                logger.error(f"❌ Symbol '{symbol}' not found in MetaTrader")
                return False
            
            # Check if symbol has valid point value (pip value)
            if not hasattr(symbol_info, 'point') or symbol_info.point <= 0:
                logger.error(f"❌ Symbol '{symbol}' has invalid point value")
                return False
            
            # Check if symbol is accessible for trading
            try:
                bid = self.meta_trader.get_bid(symbol)
                ask = self.meta_trader.get_ask(symbol)
                if bid is None or ask is None or bid <= 0 or ask <= 0:
                    logger.error(f"❌ Symbol '{symbol}' has invalid bid/ask prices")
                    return False
            except Exception as e:
                logger.error(f"❌ Cannot get bid/ask for symbol '{symbol}': {str(e)}")
                return False
            
            logger.info(f"✅ Symbol '{symbol}' validation successful")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validating symbol '{symbol}': {str(e)}")
            return False

    def _reinitialize_symbol_dependent_components(self):
        """Re-initialize components that depend on the symbol"""
        try:
            logger.info(f"🔄 Re-initializing symbol-dependent components for symbol: {self.symbol}")
            
            # Re-initialize enhanced zone detection
            self.enhanced_zone_detection = EnhancedZoneDetection(
                self.symbol, self.reversal_threshold_pips, self.order_interval_pips
            )
            logger.info("✅ EnhancedZoneDetection re-initialized")
            
            # Re-initialize enhanced order manager
            self.enhanced_order_manager = EnhancedOrderManager(
                self.meta_trader, self.symbol, self.bot.magic_number
            )
            logger.info("✅ EnhancedOrderManager re-initialized")
            
            # Re-initialize direction controller
            self.direction_controller = DirectionController(self.symbol)
            logger.info("✅ DirectionController re-initialized")
            
            # Reset any symbol-specific state
            self._reset_symbol_specific_state()
            
            logger.info(f"✅ All symbol-dependent components re-initialized for {self.symbol}")
            
        except Exception as e:
            logger.error(f"❌ Error re-initializing symbol-dependent components: {str(e)}")
            raise

    def _reset_symbol_specific_state(self):
        """Reset any symbol-specific internal state"""
        try:
            # Reset market data tracking
            self.current_market_price = None
            self.last_candle_time = None
            
            # Reset zone state
            self.initial_threshold_breached = False
            self.zone_activated = False
            
            # Reset grid state tracking
            self.current_grid_level = 0
            self.grid_direction = None
            self.last_grid_price = 0.0
            
            # Reset zone state tracking
            self.active_zones = {}
            self.zone_movement_history = []
            
            # Note: We don't reset active cycles as they might be valid for the new symbol
            # The user should handle cycle management when changing symbols
            
            logger.info(f"✅ Symbol-specific state reset for {self.symbol}")
            
        except Exception as e:
            logger.error(f"❌ Error resetting symbol-specific state: {str(e)}")

    def _update_metatrader_symbol_info(self):
        """Update MetaTrader symbol information for the new symbol"""
        try:
            # Verify symbol is accessible in MetaTrader
            symbol_info = self.meta_trader.get_symbol_info(self.symbol)
            if not symbol_info:
                logger.error(f"❌ Cannot get symbol info for {self.symbol} from MetaTrader")
                return False
            
            # Test bid/ask retrieval
            bid = self.meta_trader.get_bid(self.symbol)
            ask = self.meta_trader.get_ask(self.symbol)
            
            if bid and ask:
                logger.info(f"✅ MetaTrader symbol info updated for {self.symbol}: bid={bid}, ask={ask}")
                return True
            else:
                logger.error(f"❌ Cannot get bid/ask for {self.symbol} from MetaTrader")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating MetaTrader symbol info: {str(e)}")
            return False
