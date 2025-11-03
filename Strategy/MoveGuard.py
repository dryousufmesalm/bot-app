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
        
        # SL enforcement control
        self.disable_interval_sl_enforcement = bool(cfg.get("disable_interval_sl_enforcement", False))
        
        # Error suppression for tuple conversion issues
        self.suppress_tuple_conversion_errors = bool(cfg.get("suppress_tuple_conversion_errors", True))

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
            
            # CRITICAL: Restore pending orders for all existing cycles
            self._restore_pending_orders_for_all_cycles()
            
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
                                
                                # CRITICAL: Initialize pending orders from PocketBase data
                                if not hasattr(cycle, 'pending_orders'):
                                    cycle.pending_orders = []
                                    cycle.pending_order_levels = set()
                                
                                # Restore pending orders from cycle data
                                pending_orders = local_cycle_data.get('pending_orders', [])
                                pending_levels = local_cycle_data.get('pending_order_levels', set())
                                if pending_orders:
                                    cycle.pending_orders = pending_orders
                                    cycle.pending_order_levels = pending_levels
                                    logger.info(f"✅ Restored {len(pending_orders)} pending orders for cycle {cycle.cycle_id}")
                                
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
            
            # Handle pending orders data
            pending_orders_data = getattr(pb_cycle, 'pending_orders', '[]')
            if isinstance(pending_orders_data, str):
                try:
                    cycle_data['pending_orders'] = json.loads(pending_orders_data)
                except (json.JSONDecodeError, ValueError):
                    cycle_data['pending_orders'] = []
            else:
                cycle_data['pending_orders'] = pending_orders_data or []
            
            # Handle pending order levels data
            pending_levels_data = getattr(pb_cycle, 'pending_order_levels', '[]')
            if isinstance(pending_levels_data, str):
                try:
                    cycle_data['pending_order_levels'] = set(json.loads(pending_levels_data))
                except (json.JSONDecodeError, ValueError):
                    cycle_data['pending_order_levels'] = set()
            else:
                cycle_data['pending_order_levels'] = set(pending_levels_data or [])
            
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
            
            # CRITICAL FIX: Immediately update profit for the initial order after creation
            # This ensures the first order has correct profit data before it might be closed
            try:
                logger.info(f"🔄 Updating profit for initial order in cycle {cycle.cycle_id}")
                self._update_cycle_orders_profit_from_mt5(cycle)
                
                # Also update cycle statistics with the fresh profit data
                self._update_cycle_statistics_with_profit(cycle)
                
                # Update the cycle in database with the correct profit data
                self._update_cycle_in_database(cycle, force_update=True)
                
                logger.info(f"✅ Initial order profit updated for cycle {cycle.cycle_id}")
                
            except Exception as profit_error:
                logger.warning(f"⚠️ Failed to update initial order profit for cycle {cycle.cycle_id}: {str(profit_error)}")
                # Continue anyway - the cycle is still created successfully
            
            logger.info(f"✅ MoveGuard cycle {cycle.cycle_id} created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating MoveGuard cycle: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def  _build_cycle_data(self, order_data, username, user_id, direction, sent_by_admin):
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
                    'upper_boundary': float(order_data.get('price', 0.0)) + (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value() ),
                    'lower_boundary': float(order_data.get('price', 0.0)) - (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value() ),
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
                'upper_bound': float(order_data.get('price', 0.0)) + (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value() / 2),
                'lower_bound': float(order_data.get('price', 0.0)) - (cycle_config.get('zone_threshold_pips', 50.0) * self._get_pip_value() / 2)
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
            
            # CRITICAL: Monitor all active orders status across all cycles
            # This ensures we catch any orders that were closed in MT5
            for cycle in active_cycles:
                if cycle.status == 'active':
                    self._monitor_active_orders_status(cycle)
            
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
            
            # CRITICAL: Check for closed orders and clean up pending orders
            # for cycle in active_cycles:
                # self._check_and_cleanup_closed_orders(cycle)
            
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
                total_order_count = len([o for o in getattr(cycle, 'orders', [])])
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
             
                    # Monitor pending orders for triggers
                self._monitor_pending_orders(cycle, current_price)
                
                # Monitor active orders status - check if they were closed in MT5
                self._monitor_active_orders_status(cycle)
                
                # Initial order placement: only when price crosses boundaries by entry_interval_pips
                if active_order_count == 0:
                    # Update bounds based on movement mode when all orders are closed
                    # Use trailing_stop_loss if available, otherwise use current_price or cycle entry_price
                    
                    if cycle.trailing_stop_loss is not None and cycle.trailing_stop_loss > 0:
                        self._update_bounds_after_all_orders_closed(cycle, cycle.trailing_stop_loss, cycle.direction, current_price)
                       
                    # check if there is no active pending orders
                    if len(cycle.pending_orders) == 0:
                        # Enhanced direction determination based on movement mode
                        # new_direction = self._determine_new_direction_after_all_orders_closed(cycle, current_price)
                        
                        # if new_direction:
                        #     # Update bounds based on movement mode
                            
                        #     # Set cycle direction and place initial order
                        #     # cycle.direction = new_direction
                        #     # if new_direction == 'BUY':
                        #     #     cycle.was_above_upper = True
                        #     #     self._place_initial_order(cycle, 'BUY', current_price)
                        #     # else:  # SELL
                        #     #     cycle.was_below_lower = True
                        #     #     self._place_initial_order(cycle, 'SELL', current_price)
                        #       # Maintain pending orders ahead of current position
                        self._maintain_pending_grid_orders(cycle, current_price, 5)
                        # else:
                            # logger.info(f"🔄 MoveGuard: Price {current_price:.5f} is within the zone boundaries, skipping initial order placement")
                            # continue
                    if len(cycle.pending_orders) > 0:
                        # Validate pending orders grid levels - cancel if invalid
                        if not self._validate_pending_orders_grid_levels(cycle):
                            logger.warning(f"🚨 Invalid pending orders grid levels detected - cancelling all pending orders")
                            self._cancel_cycle_pending_orders(cycle)
                            continue
                        
                        # Enhanced direction determination for pending orders scenario
                        new_direction = self._determine_new_direction_after_all_orders_closed(cycle, current_price)
                        # if len(cycle.pending_orders) <5:
                        #     self._cancel_cycle_pending_orders(cycle)
                        if new_direction:
                            # Set cycle direction
                            cycle.direction = new_direction
                    
                            if new_direction == 'BUY':
                                cycle.was_above_upper = True
                                # Cancel SELL pending orders if any
                                active_sell_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'SELL']
                                active_buy_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'BUY']
                                if len(active_buy_pending_orders) > 0 and cycle.trailing_stop_loss is not None and current_price < cycle.trailing_stop_loss and cycle.trailing_stop_loss > 0: 
                                    self._cancel_buy_pending_orders(cycle)
                                if len(active_sell_pending_orders) > 0:
                                    self._cancel_sell_pending_orders(cycle)
                            else:  # SELL
                                cycle.was_below_lower = True
                                # Cancel BUY pending orders if any
                                active_buy_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'BUY']
                                active_sell_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'SELL']
                                if len(active_buy_pending_orders) > 0:
                                    self._cancel_buy_pending_orders(cycle)
                                if len(active_sell_pending_orders) > 0 and cycle.trailing_stop_loss is not None and current_price > cycle.trailing_stop_loss and cycle.trailing_stop_loss > 0:
                                    self._cancel_sell_pending_orders(cycle)
                        else:
                            logger.info(f"🔄 MoveGuard: Price {current_price:.5f} is within the zone boundaries, skipping initial order placement")
                            continue

                    # Initialize pending order tracking for new cycles
                    if not hasattr(cycle, 'pending_orders'):
                        cycle.pending_orders = []
                        cycle.pending_order_levels = set()
                        logger.info(f"🔄 MoveGuard: Initialized pending order tracking for cycle {cycle.cycle_id}")
                
                    # Use cycle-specific zone_threshold_pips from cycle_config
                    if total_order_count == 0:
                        cycle_zone_threshold_pips = cycle.cycle_config.get('zone_threshold_pips', 50.0) if hasattr(cycle, 'cycle_config') and cycle.cycle_config else 50.0
                        cycle.lower_bound = upper - (cycle_zone_threshold_pips * pip_value)
                        cycle.highest_buy_price = current_price
                        lower = cycle.lower_bound
                        #update zone data
                        cycle.zone_data['upper_boundary'] = upper
                        cycle.zone_data['lower_boundary'] = lower
                    continue
               
                # Pending order monitoring and maintenance
                if active_order_count > 0:
                    # Reset grid restart completion flag when orders become active again
                    if hasattr(cycle, 'grid_restart_completed') and cycle.grid_restart_completed:
                        cycle.grid_restart_completed = False
                        logger.info(f"🔄 MoveGuard GRID RESTART: Reset restart completion flag - orders are active again in cycle {cycle.cycle_id}")
                    
                    if len(cycle.pending_orders) > 0:
                        # Validate pending orders grid levels - cancel if invalid
                        if not self._validate_pending_orders_grid_levels(cycle):
                            logger.warning(f"🚨 Invalid pending orders grid levels detected - cancelling all pending orders")
                            self._cancel_cycle_pending_orders(cycle)
                            continue
                        
                        # Enhanced direction determination for pending orders scenario
                        new_direction = self._determine_new_direction_after_all_orders_closed(cycle, current_price)
                        # if len(cycle.pending_orders) <5:
                        #     self._cancel_cycle_pending_orders(cycle)
                        if new_direction:
                            # Set cycle direction
                            cycle.direction = new_direction
                    
                            if new_direction == 'BUY':
                                cycle.was_above_upper = True
                                # Cancel SELL pending orders if any
                                active_sell_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'SELL']
                                active_buy_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'BUY']
                  
                                if len(active_sell_pending_orders) > 0:
                                    self._cancel_sell_pending_orders(cycle)
                            else:  # SELL
                                cycle.was_below_lower = True
                                # Cancel BUY pending orders if any
                                active_buy_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'BUY']
                                active_sell_pending_orders = [o for o in cycle.pending_orders if o.get('direction') == 'SELL']
                                if len(active_buy_pending_orders) > 0:
                                    self._cancel_buy_pending_orders(cycle)
                          
                    # Maintain pending orders ahead of current position
                    self._maintain_pending_grid_orders(cycle, current_price, 5)
                    
                    # Update trailing stop loss for ALL active positions
                    if hasattr(cycle, 'trailing_stop_loss') and cycle.trailing_stop_loss is not None and cycle.trailing_stop_loss > 0:
                        # Update SL for all active positions, not pending orders
                        active_positions = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
                        if len(active_positions) > 0:
                            logger.info(f"🔄 Updating trailing SL for {len(active_positions)} active position(s) to {cycle.trailing_stop_loss:.5f}")
                            success = self._update_all_orders_trailing_sl(cycle, cycle.trailing_stop_loss)
                            
                    continue
                    
                # Enforce initial order SL logic without closing cycle
                self._check_and_close_initial_order(cycle, current_price)
                
                # Check and enforce SL for interval cycle orders
                # self._check_and_enforce_interval_order_sl(cycle, current_price)

        except Exception as e:
            logger.error(f"❌ Error processing grid logic: {str(e)}")
            logger.error(traceback.format_exc())

    def _place_initial_order(self, cycle, direction: str, order_price: float) -> bool:
        """Place the first order (grid_0) as a pending order at the calculated grid start price."""
        try:
            pip_value = self._get_pip_value()
            sl_price = 0.0
            
            # Get cycle-specific configuration values
            lot_size = self.get_cycle_config_value(cycle, 'lot_size', self.lot_size)
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            max_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_trades_per_cycle', self.max_trades_per_cycle)
            max_active_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_active_trades_per_cycle', self.max_active_trades_per_cycle)
            order_interval_pips = self.get_cycle_config_value(cycle, 'order_interval_pips', self.order_interval_pips)
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
            
            # Calculate SL for pending order (ensure it's a proper price, not pips)
            if initial_stop_loss_pips > 0:
                if direction == 'BUY':
                    sl_price = round(order_price - (initial_stop_loss_pips * pip_value), 2)
                else:
                    sl_price = round(order_price + (initial_stop_loss_pips * pip_value), 2)
                
                # Validate SL is a reasonable price for the symbol
                if sl_price <= 0 or sl_price < order_price * 0.1:  # SL too low or negative
                    logger.warning(f"Calculated SL {sl_price} is invalid for {direction} order at {order_price}, setting to 0")
                    sl_price = 0
                
                # CRITICAL: Validate SL distance from order price to prevent MT5 errors
                if sl_price > 0:
                    min_sl_distance = pip_value * 10.0  # Minimum 10 pips distance
                    
                    if direction == 'BUY':
                        # For BUY orders, SL must be below order price
                        if sl_price >= order_price:
                            sl_price = order_price - min_sl_distance
                            logger.warning(f"⚠️ BUY initial order SL too close to price, adjusted to {sl_price:.5f}")
                        elif (order_price - sl_price) < min_sl_distance:
                            sl_price = order_price - min_sl_distance
                            logger.warning(f"⚠️ BUY initial order SL too close to price, adjusted to {sl_price:.5f}")
                    else:  # SELL
                        # For SELL orders, SL must be above order price
                        if sl_price <= order_price:
                            sl_price = order_price + min_sl_distance
                            logger.warning(f"⚠️ SELL initial order SL too close to price, adjusted to {sl_price:.5f}")
                        elif (sl_price - order_price) < min_sl_distance:
                            sl_price = order_price + min_sl_distance
                            logger.warning(f"⚠️ SELL initial order SL too close to price, adjusted to {sl_price:.5f}")
                    
                    logger.info(f"📊 {direction} initial order SL validation: order_price={order_price:.5f}, sl={sl_price:.5f}, distance={abs(order_price - sl_price):.5f}")
            
            # Place pending order instead of market order
            if direction == 'BUY':
                # For BUY_STOP orders, target price must be above current price
                # Add a small offset (10 pips) above current price for BUY_STOP
                buy_stop_offset = order_interval_pips * pip_value
                target_buy_price = order_price + buy_stop_offset
                
                logger.info(f"🎯 BUY_STOP placement: current_price={order_price:.5f}, target_price={target_buy_price:.5f} (10 pips above)")
                
                result = self.meta_trader.place_pending_buy_order(
                    symbol=self.symbol,
                    target_price=target_buy_price,
                    current_price=order_price,  # Current market price
                    volume=lot_size,
                    sl=sl_price,
                    tp=0.0,
                    comment=f"Grid_0_BUY",
                    force_buy_stop=True  # Always use BUY_STOP
                )
                order_direction = 'BUY'
            else:
                # For SELL_STOP orders, target price must be below current price
                # Add a small offset (10 pips) below current price for SELL_STOP
                sell_stop_offset = order_interval_pips * pip_value
                target_sell_price = order_price - sell_stop_offset
                
                logger.info(f"🎯 SELL_STOP placement: current_price={order_price:.5f}, target_price={target_sell_price:.5f} (10 pips below)")
                
                result = self.meta_trader.place_pending_sell_order(
                    symbol=self.symbol,
                    target_price=target_sell_price,
                    current_price=order_price,  # Current market price
                    volume=lot_size,
                    sl=sl_price,
                    tp=0.0,
                    comment=f"Grid_0_SELL",
                    force_sell_stop=True  # Always use SELL_STOP
                )
                order_direction = 'SELL'

            if result:
                # Extract order ID from result - handle different result formats
                order_id = None
                
                # Handle tuple format (TradeOrder objects wrapped in tuple)
                if isinstance(result, tuple) and len(result) > 0:
                    trade_order = result[0]
                    order_id = getattr(trade_order, 'ticket', None)
                elif isinstance(result, dict):
                    # Dictionary format
                    order_id = result.get('order')
                    if not order_id:
                        order_id = result.get('ticket')
                else:
                    # Object format - try different attributes
                    order_id = getattr(result, 'order', None)
                    if not order_id:
                        order_id = getattr(result, 'ticket', None)
                    if not order_id and hasattr(result, '_asdict'):
                        # NamedTuple format
                        result_dict = result._asdict()
                        order_id = result_dict.get('order') or result_dict.get('ticket')
                
                if order_id:
                    # Update cycle direction to match the order being placed
                    cycle.direction = order_direction
                    logger.info(f"🔄 Updated cycle {cycle.cycle_id} direction to {order_direction}")
                    
                    order_info = {
                        'order_id': order_id,
                        'ticket': order_id,
                        'direction': order_direction,
                        'price': order_price,  # Pending order price
                        'lot_size': lot_size,
                        'is_initial': True,
                        'order_type': 'grid_0',
                        'status': 'pending',  # Initial order is now pending
                        'placed_at': datetime.datetime.now().isoformat(),
                        'profit': 0.0,
                        'profit_pips': 0.0,
                        'last_profit_update': datetime.datetime.now().isoformat(),
                        'grid_level': 0,
                        'is_grid': True,
                        'sl': sl_price,
                        'is_active': False
                    
                    }
                    
                    # Add to pending orders tracking
                    if not hasattr(cycle, 'pending_orders'):
                        cycle.pending_orders = []
                        cycle.pending_order_levels = set()
                    
                    cycle.pending_orders.append(order_info)
                    cycle.pending_order_levels.add(0)
                    
                    if hasattr(cycle, 'orders'):
                        cycle.orders.append(order_info)
                    else:
                        cycle.orders = [order_info]
                    
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
                    
                    logger.info(f"✅ MoveGuard initial {direction} order placed as pending: ID {order_id}, Price {order_price:.5f}")
                    
                    # IMMEDIATELY place 5 pending orders to maintain grid ahead
                    logger.info(f"🚀 AUTOMATIC GRID SETUP: Placing 5 pending orders after initial order placement")
                    grid_success = self._maintain_pending_grid_orders(cycle, order_price, 5)
                    
                    if grid_success:
                        logger.info(f"✅ SUCCESS: 5 pending orders placed automatically after initial order")
                    else:
                        logger.warning(f"⚠️ WARNING: Failed to place pending orders after initial order")
                    
                    return True
                else:
                    logger.error("❌ Failed to extract order ID from pending order result")
                    return False
            else:
                logger.error("❌ Failed to place MoveGuard initial pending order")
                return False
        except Exception as e:
            logger.error(f"❌ Error placing initial pending order: {e}")
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
            # if hit:

            #     if self._close_order(initial):
            #         initial['status'] = 'closed'
            #         initial['closed_at'] = datetime.datetime.now().isoformat()
            #         logger.info(f"Closed cycle entry order at SL threshold for cycle {cycle.cycle_id}")
        except Exception as e:
            logger.error(f"Error in _check_and_close_initial_order: {e}")

    def _calculate_expected_sl_price(self, cycle, order, direction: str, entry_price: float) -> float:
        """Calculate expected SL price using same logic as trailing SL calculation
        
        This ensures expected SL matches the actual trailing SL behavior, considering:
        - Movement mode (Move Both Sides, Move Up Only, Move Down Only, No Move)
        - Zone boundaries (upper_boundary, lower_boundary)
        - Highest/lowest prices (highest_buy_price, lowest_sell_price)
        - Zone threshold pips instead of initial_stop_loss_pips
        
        Args:
            cycle: The cycle object
            order: The order object
            direction: 'BUY' or 'SELL'
            entry_price: The order entry price
            
        Returns:
            float: The expected SL price
        """
        try:
            pip_value = self._get_pip_value()
            zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
            
            if direction == 'BUY':
                # Use same logic as BUY trailing SL calculation
                upper_boundary = cycle.zone_data.get('upper_boundary', 0.0)
                
                if hasattr(cycle, 'highest_buy_price') and cycle.highest_buy_price > 0:
                    expected_sl = cycle.highest_buy_price - (zone_threshold_pips * pip_value)
                else:
                    # First order - use order price as reference
                    expected_sl = entry_price - (zone_threshold_pips * pip_value)
                
                # Cap at upper boundary if zone movement mode requires it
                if cycle.zone_movement_mode == 'Move Both Sides' or cycle.zone_movement_mode == 'Move Up Only':
                    expected_sl = max(expected_sl, upper_boundary)
                    
            else:  # SELL
                # Use same logic as SELL trailing SL calculation
                lower_boundary = cycle.zone_data.get('lower_boundary', 0.0)
                
                if hasattr(cycle, 'lowest_sell_price') and cycle.lowest_sell_price < 999999.0:
                    expected_sl = cycle.lowest_sell_price + (zone_threshold_pips * pip_value)
                else:
                    # First order - use order price as reference
                    expected_sl = entry_price + (zone_threshold_pips * pip_value)
                
                # Cap at lower boundary if zone movement mode requires it
                if cycle.zone_movement_mode == 'Move Both Sides' or cycle.zone_movement_mode == 'Move Down Only':
                    expected_sl = min(expected_sl, lower_boundary)
            
            # Validate stop loss is reasonable (at least 1 pip away from entry price)
            min_sl_distance = pip_value * 1.0  # 1 pip minimum
            if direction == 'BUY':
                if entry_price - expected_sl < min_sl_distance:
                    expected_sl = entry_price - min_sl_distance
            else:  # SELL
                if expected_sl - entry_price < min_sl_distance:
                    expected_sl = entry_price + min_sl_distance
            
            logger.debug(f"📊 Calculated expected SL for {direction} order: {expected_sl:.5f} (movement_mode={cycle.zone_movement_mode})")
            return expected_sl
            
        except Exception as e:
            logger.error(f"❌ Error calculating expected SL price: {e}")
            # Fallback to simple calculation
            pip_value = self._get_pip_value()
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', 300.0)
            
            if direction == 'BUY':
                return entry_price - (initial_stop_loss_pips * pip_value)
            else:
                return entry_price + (initial_stop_loss_pips * pip_value)

    def _check_and_enforce_interval_order_sl(self, cycle, current_price: float):
        """Check and enforce SL for interval cycle orders that don't have SL or didn't close by SL."""
        try:
            # TEMPORARY SAFETY: Add configuration to disable this function if needed
            if hasattr(self, 'disable_interval_sl_enforcement') and self.disable_interval_sl_enforcement:
                return
                
            # Get cycle-specific configuration values
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            if initial_stop_loss_pips <= 0:
                return
            
            pip_value = self._get_pip_value()
            
            # Find active interval cycle orders (grid_level 0, is_initial=True, is_grid=True)
            interval_orders = []
            logger.debug(f"🔍 Starting order collection for cycle {cycle.cycle_id}")
            
            for i, o in enumerate(getattr(cycle, 'orders', [])):
                logger.debug(f"🔍 Order {i}: type={type(o)}, content={o}")
                
                # Handle both dict and tuple formats
                if isinstance(o, dict):
                    logger.debug(f"🔍 Processing dict order {i}")
                    if (o.get('status') == 'active' and 
                        o.get('is_initial', False) and 
                        o.get('is_grid', True) and 
                        o.get('grid_level', 0) == 0):
                        logger.debug(f"✅ Adding dict order {i} to interval_orders")
                        interval_orders.append(o)
                elif isinstance(o, (tuple, list)) and len(o) >= 4:
                    logger.debug(f"🔍 Processing tuple order {i} with length {len(o)}")
                    # Handle tuple format - assume structure: (order_id, status, grid_level, is_initial, ...)
                    if (len(o) >= 5 and 
                        o[1] == 'active' and  # status
                        o[3] == True and      # is_initial
                        o[2] == 0):           # grid_level
                        # Convert tuple to dict format for processing
                        order_dict = {
                            'order_id': o[0],
                            'ticket': o[0],
                            'status': o[1],
                            'grid_level': o[2],
                            'is_initial': o[3],
                            'is_grid': o[4] if len(o) > 4 else True,
                            'direction': o[5] if len(o) > 5 else 'BUY',
                            'price': o[6] if len(o) > 6 else 0.0
                        }
                        logger.debug(f"✅ Adding converted tuple order {i} to interval_orders: {order_dict}")
                        interval_orders.append(order_dict)
                else:
                    logger.debug(f"⚠️ Skipping order {i} - type: {type(o)}, length: {len(o) if hasattr(o, '__len__') else 'N/A'}")
            
            # Ensure all orders are dictionaries - with enhanced validation
            processed_orders = []
            for order in interval_orders:
                if isinstance(order, dict):
                    processed_orders.append(order)
                elif isinstance(order, (tuple, list)) and len(order) >= 4:
                    # Convert remaining tuples to dictionaries
                    try:
                        order_dict = {
                            'order_id': order[0] if len(order) > 0 else None,
                            'ticket': order[0] if len(order) > 0 else None,
                            'status': order[1] if len(order) > 1 else 'active',
                            'grid_level': order[2] if len(order) > 2 else 0,
                            'is_initial': order[3] if len(order) > 3 else True,
                            'is_grid': order[4] if len(order) > 4 else True,
                            'direction': order[5] if len(order) > 5 else 'BUY',
                            'price': order[6] if len(order) > 6 else 0.0
                        }
                        processed_orders.append(order_dict)
                        logger.debug(f"✅ Converted tuple to dict: {order_dict}")
                    except Exception as convert_error:
                        if not self.suppress_tuple_conversion_errors:
                            logger.warning(f"⚠️ Failed to convert tuple order: {convert_error} - {order}")
                        else:
                            logger.debug(f"🔍 Suppressed tuple conversion error: {convert_error}")
                else:
                    logger.warning(f"⚠️ Skipping non-dict order: {type(order)} - {order}")
            interval_orders = processed_orders
            
            if not interval_orders:
                return
            
            logger.debug(f"🔍 Checking {len(interval_orders)} interval orders for SL enforcement in cycle {cycle.cycle_id}")
            
            for order in interval_orders:
                try:
                    # COMPREHENSIVE DEBUG: Log order type and structure
                    logger.debug(f"🔍 Processing order type: {type(order)}")
                    if isinstance(order, tuple):
                        logger.debug(f"🔍 Tuple structure: length={len(order)}, content={order}")
                        # Convert tuple to dict if it somehow got through
                        try:
                            order = {
                                'order_id': order[0] if len(order) > 0 else None,
                                'ticket': order[0] if len(order) > 0 else None,
                                'status': order[1] if len(order) > 1 else 'active',
                                'grid_level': order[2] if len(order) > 2 else 0,
                                'is_initial': order[3] if len(order) > 3 else True,
                                'is_grid': order[4] if len(order) > 4 else True,
                                'direction': order[5] if len(order) > 5 else 'BUY',
                                'price': order[6] if len(order) > 6 else 0.0
                            }
                            logger.debug(f"✅ Converted tuple to dict in processing: {order}")
                        except Exception as convert_error:
                            if not self.suppress_tuple_conversion_errors:
                                logger.warning(f"⚠️ Failed to convert tuple in processing: {convert_error} - skipping")
                            else:
                                logger.debug(f"🔍 Suppressed tuple conversion error in processing: {convert_error}")
                            continue
                    elif isinstance(order, dict):
                        logger.debug(f"🔍 Dict keys: {list(order.keys())}")
                    else:
                        logger.debug(f"🔍 Unknown type: {type(order)} - {order}")
                        logger.warning(f"⚠️ Skipping unknown order type: {type(order)}")
                        continue
                    
                    # Final type checking for safety
                    if not isinstance(order, dict):
                        logger.warning(f"⚠️ Skipping non-dict order in processing: {type(order)}")
                        continue
                    
                    # SAFE ATTRIBUTE ACCESS: Use try-catch for each .get() call
                    try:
                        order_id = order.get('order_id') or order.get('ticket')
                    except Exception as get_error:
                        logger.error(f"❌ Error getting order_id: {get_error} - Order type: {type(order)}")
                        continue
                    
                    try:
                        entry_price = order.get('price', 0.0)
                    except Exception as get_error:
                        logger.error(f"❌ Error getting price: {get_error} - Order type: {type(order)}")
                        continue
                    
                    try:
                        direction = order.get('direction', 'BUY')
                    except Exception as get_error:
                        logger.error(f"❌ Error getting direction: {get_error} - Order type: {type(order)}")
                        continue
                    
                    if not order_id or entry_price <= 0:
                        logger.debug(f"⚠️ Skipping order with invalid data: ID={order_id}, Price={entry_price}")
                        continue
                    
                    # Check if order has SL in MT5 - with enhanced validation
                    position = self.meta_trader.get_position_by_ticket(int(order_id))
                    has_sl_in_mt5 = False
                    current_sl = 0.0
                    
                    # ENHANCED VALIDATION: Check if position exists before processing
                    if not position or len(position) == 0:
                        logger.debug(f"🔍 Position {order_id} not found in MT5 - marking order as closed")
                        # Mark order as closed in internal data to prevent future attempts
                        order['status'] = 'closed'
                        order['closed_reason'] = 'position_not_found'
                        continue
                    
                    # Position exists - check SL status
                    if position and len(position) > 0:
                        # Get the first position object and access its attributes safely
                        position_obj = position[0]
                        current_sl = getattr(position_obj, 'sl', 0.0)
                        has_sl_in_mt5 = current_sl != 0.0
                    
                    # Calculate expected SL price using same logic as trailing SL (considering movement mode)
                    expected_sl_price = self._calculate_expected_sl_price(cycle, order, direction, entry_price)
                    
                    if direction == 'BUY':
                        sl_hit = current_price <= expected_sl_price
                    else:  # SELL
                        sl_hit = current_price >= expected_sl_price
                    
                    # Case 1: Order has no SL in MT5 - add SL
                    if not has_sl_in_mt5:
                        logger.warning(f"🚨 Interval order {order_id} has no SL in MT5 - adding SL at {expected_sl_price:.5f}")
                        try:
                            result = self.meta_trader.modify_position_sl_tp(int(order_id), sl=expected_sl_price, tp=0.0)
                            if result:
                                logger.info(f"✅ Added SL to interval order {order_id} at {expected_sl_price:.5f}")
                            else:
                                logger.debug(f"🔍 Position {order_id} may have been closed - skipping SL modification")
                                order['status'] = 'closed'
                                order['closed_reason'] = 'position_closed_during_sl_update'
                        except Exception as e:
                            logger.debug(f"🔍 Failed to add SL to interval order {order_id} (position may be closed): {e}")
                            # Mark as closed to prevent future attempts
                            order['status'] = 'closed'
                            order['closed_reason'] = 'sl_modification_failed'
                    
                    # Case 2: Order has SL but price hit SL threshold - let broker handle it
                    elif has_sl_in_mt5 and sl_hit:
                        logger.info(f"📊 Interval order {order_id} hit SL threshold - broker will close it")
                        logger.info(f"   Entry: {entry_price:.5f}, Current: {current_price:.5f}, Expected SL: {expected_sl_price:.5f}")
                        # Let the broker close the order when SL is hit - don't close it manually
                        # The broker's platform will handle the closure at the stop loss price
                    
                    # Case 3: Order has SL but it's different from expected - update SL
                    elif has_sl_in_mt5 and abs(current_sl - expected_sl_price) > 0.00001:
                        logger.warning(f"🚨 Interval order {order_id} has incorrect SL - updating from {current_sl:.5f} to {expected_sl_price:.5f}")
                        try:
                            result = self.meta_trader.modify_position_sl_tp(int(order_id), sl=expected_sl_price, tp=0.0)
                            if result:
                                logger.info(f"✅ Updated SL for interval order {order_id} to {expected_sl_price:.5f}")
                            else:
                                logger.debug(f"🔍 Position {order_id} may have been closed - skipping SL update")
                                order['status'] = 'closed'
                                order['closed_reason'] = 'position_closed_during_sl_update'
                        except Exception as e:
                            logger.debug(f"🔍 Failed to update SL for interval order {order_id} (position may be closed): {e}")
                            # Mark as closed to prevent future attempts
                            order['status'] = 'closed'
                            order['closed_reason'] = 'sl_update_failed'
                    
                    # Log status for debugging
                    else:
                        logger.debug(f"✅ Interval order {order_id} SL status OK: SL={current_sl:.5f}, Expected={expected_sl_price:.5f}")
                        
                except Exception as order_error:
                    logger.error(f"❌ Error processing interval order: {order_error}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error in _check_and_enforce_interval_order_sl: {e}")

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

    def _update_all_orders_trailing_sl(self, cycle, new_trailing_sl: float) -> bool:
        """Update stop loss for all active orders in the cycle to the new trailing SL value
        
        This is the BETTER approach - modify actual MT5 orders instead of tracking in memory.
        MT5 will automatically close orders when price hits their SL, even if bot crashes.
        
        Args:
            cycle: The cycle object
            new_trailing_sl: The new trailing stop-loss price
            
        Returns:
            bool: True if at least one order was successfully updated
        """
        try:
            if not hasattr(cycle, 'orders') or not cycle.orders:
                logger.debug(f"No orders found for cycle {cycle.cycle_id}")
                return False
            if new_trailing_sl <= 0:
                return False
            # Only update active positions, skip pending orders
            active_orders = [o for o in cycle.orders if o.get('status') == 'active']
            pending_orders = [o for o in cycle.orders if o.get('status') == 'pending']
            
            if not active_orders:
                logger.debug(f"No active orders to update SL for cycle {cycle.cycle_id} (pending orders: {len(pending_orders)})")
                return False
            
            logger.debug(f"Updating SL for {len(active_orders)} active orders, skipping {len(pending_orders)} pending orders")
            
            updated_count = 0
            failed_count = 0
            closed_orders = 0
            
            for order in active_orders:
                order_id = order.get('ticket') or order.get('order_id')
                if not order_id:
                    logger.warning(f"⚠️ Order missing ticket/order_id: {order}")
                    continue
                
                try:
                    # Check if position still exists in MT5
                    position = self.meta_trader.get_position_by_ticket(int(order_id))
                    if not position or len(position) == 0:
                        logger.debug(f"🔍 Position {order_id} not found in MT5 - order was closed, updating status")
                        order['status'] = 'closed'
                        order['closed_reason'] = 'position_not_found'
                        order['closed_at'] = datetime.datetime.now().isoformat()
                        closed_orders += 1
                        continue
                    
                    # Modify the position's stop loss in MT5
                    logger.debug(f"🔧 Attempting to modify SL for order {order_id} from {order.get('stop_loss', 'unknown')} to {new_trailing_sl:.5f}")
                    result = self.meta_trader.modify_position_sl_tp(
                        ticket=int(order_id),
                        sl=new_trailing_sl,
                        tp=0.0
                    )
                    
                    if result:
                        updated_count += 1
                        logger.info(f"✅ Successfully updated SL for order {order_id} to {new_trailing_sl:.5f}")
                        # Update order record with new SL
                        order['stop_loss'] = new_trailing_sl
                    else:
                        failed_count += 1
                        logger.warning(f"⚠️ Failed to update SL for order {order_id} - modify_position_sl_tp returned False")
                        # Try to get more details about why it failed
                        try:
                            position_info = self.meta_trader.get_position_by_ticket(int(order_id))
                            if position_info:
                                logger.warning(f"🔍 Position {order_id} exists but SL modification failed. Current SL: {getattr(position_info, 'sl', 'unknown')}")
                        except Exception as e:
                            logger.warning(f"🔍 Could not get position info for {order_id}: {e}")
                        
                except Exception as e:
                    failed_count += 1
                    logger.debug(f"⚠️ Error updating SL for order {order_id}: {e}")
                    continue
            
            # If we found closed orders, update the cycle data and sync to database
            if closed_orders > 0:
                logger.info(f"🔄 Found {closed_orders} closed orders in cycle {cycle.cycle_id} - updating cycle data")
                # Force update cycle in database to reflect closed orders
                self._update_cycle_in_database(cycle, force_update=True)
            
            if updated_count > 0:
                logger.info(f"✅ Updated trailing SL to {new_trailing_sl:.5f} for {updated_count}/{len(active_orders)} orders in cycle {cycle.cycle_id}")
                # Log each order's new SL for debugging
                for order in active_orders:
                    order_id = order.get('ticket') or order.get('order_id')
                    logger.info(f"📊 Order {order_id} (Grid {order.get('grid_level', '?')}) SL updated to {new_trailing_sl:.5f}")
                return True
            else:
                logger.warning(f"⚠️ Failed to update trailing SL for any orders in cycle {cycle.cycle_id} ({failed_count} failures, {closed_orders} closed)")
                # Log details about why it failed
                logger.warning(f"🔍 Active orders in cycle: {[o.get('ticket') for o in active_orders]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating trailing SL for cycle orders: {e}")
            return False

    def _force_update_all_orders_sl(self, cycle, new_trailing_sl: float) -> bool:
        """Force update ALL orders' SL by getting them directly from MT5"""
        try:
            logger.info(f"🚀 FORCE updating all orders' SL to {new_trailing_sl:.5f} for cycle {cycle.cycle_id}")
            
            # Get all positions from MT5 directly
            all_positions = self.meta_trader.get_all_positions()
            if not all_positions:
                logger.warning("⚠️ No positions found in MT5")
                return False
            
            updated_count = 0
            
            # Find positions that belong to this cycle
            for position in all_positions:
                if hasattr(position, 'comment') and 'MoveGuard' in str(position.comment):
                    # This is a MoveGuard position
                    try:
                        result = self.meta_trader.modify_position_sl_tp(
                            ticket=int(position.ticket),
                            sl=new_trailing_sl,
                            tp=0.0
                        )
                        if result:
                            updated_count += 1
                            logger.info(f"✅ FORCE updated SL for position {position.ticket} to {new_trailing_sl:.5f}")
                        else:
                            logger.warning(f"⚠️ FORCE update failed for position {position.ticket}")
                    except Exception as e:
                        logger.error(f"❌ FORCE update error for position {position.ticket}: {e}")
            
            logger.info(f"🚀 FORCE update complete: {updated_count} positions updated")
            return updated_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error in force update: {e}")
            return False

    def _get_pip_value(self) -> float:
        """Get pip value for MoveGuard with enhanced validation"""
        try:
            # Get symbol point value from MetaTrader
            symbol_info = self.meta_trader.get_symbol_info(self.symbol)
            if symbol_info and hasattr(symbol_info, 'point'):
                pip_value = float(symbol_info.point) * 10
                if pip_value > 0:
                    logger.debug(f"✅ Got pip value from MT5: {pip_value}")
                    return pip_value
                else:
                    logger.warning(f"⚠️ Invalid pip value from MT5: {pip_value}")
            
            # Fallback based on symbol type
            if 'BTC' in self.symbol.upper():
                logger.info(f"🔄 Using BTC fallback pip value: 0.1")
                return 0.1
            elif 'USD' in self.symbol.upper() or 'EUR' in self.symbol.upper():
                logger.info(f"🔄 Using Forex fallback pip value: 0.0001")
                return 0.0001
            else:
                logger.info(f"🔄 Using default fallback pip value: 0.0001")
                return 0.0001
           
        except Exception as e:
            logger.error(f"❌ Failed to get pip value: {str(e)}")
            # Enhanced fallback based on symbol
            if 'BTC' in self.symbol.upper():
                return 0.1
            else:
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
                # Get pip value with validation
                pip_value = self._get_pip_value()
                if pip_value <= 0:
                    logger.warning(f"⚠️ Invalid pip value: {pip_value}, using fallback 0.0001")
                    pip_value = 0.0001
                
                # Get entry price with validation
                base = self._safe_float_value(get_value('entry_price'))
                if base <= 0:
                    logger.warning(f"⚠️ Invalid entry price: {base}, using current price fallback")
                    try:
                        current_price = self._get_current_price()
                        base = current_price if current_price > 0 else 1.0
                        logger.info(f"🔄 Using current price as base: {base}")
                    except Exception as e:
                        logger.error(f"❌ Failed to get current price: {e}, using fallback 1.0")
                        base = 1.0
                
                # Get zone threshold with validation
                zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
                if zone_threshold_pips <= 0:
                    logger.warning(f"⚠️ Invalid zone threshold: {zone_threshold_pips}, using fallback 50.0")
                    zone_threshold_pips = 50.0
                
                # Calculate boundaries with validation
                zone_threshold = zone_threshold_pips * pip_value 
                upper_boundary = base + zone_threshold
                lower_boundary = base - zone_threshold
                
                # Validate calculated boundaries
                if upper_boundary <= lower_boundary:
                    logger.error(f"❌ Invalid boundaries: upper={upper_boundary}, lower={lower_boundary}")
                    # Use fallback boundaries
                    upper_boundary = base + (50.0 * 0.0001)
                    lower_boundary = base - (50.0 * 0.0001)
                
                zone_data_val = {
                    'base_price': base,
                    'upper_boundary': upper_boundary,
                    'lower_boundary': lower_boundary,
                    'movement_mode': getattr(self, 'zone_movement_mode', 'Move Both Sides'),
                    'last_movement': None
                }
                
                # Validate distance between boundaries
                distance = upper_boundary - lower_boundary
                expected_distance = zone_threshold_pips * pip_value
                logger.info(f"✅ Calculated zone boundaries: base={base:.5f}, upper={upper_boundary:.5f}, lower={lower_boundary:.5f}")
                logger.info(f"📏 Zone distance: {distance:.5f} (expected: {expected_distance:.5f}, zone_threshold: {zone_threshold_pips} pips)")
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
                'magic_number': int(getattr(cycle, 'magic_number', 0)),
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
                'cycle_config': self._serialize_data(cycle_config),
                # Add pending orders tracking for PocketBase persistence
                'pending_orders': self._serialize_data(getattr(cycle, 'pending_orders', [])),
                'pending_order_levels': self._serialize_data(list(getattr(cycle, 'pending_order_levels', set())))
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
            
            # CRITICAL FIX: ALL grid orders should have SL set to current trailing SL
            # This ensures MT5 protects them even if bot crashes
            order_sl = 0
            
            # Get current trailing SL if it exists
            if hasattr(cycle, 'trailing_stop_loss') and cycle.trailing_stop_loss is not None and cycle.trailing_stop_loss > 0:
                # Use existing trailing SL
                order_sl = cycle.trailing_stop_loss
                logger.debug(f"📊 Using existing trailing SL for BUY grid order: {order_sl:.5f}")
            else:
                # Calculate SL based on initial_stop_loss_pips from configuration
                upper_boundary = cycle.zone_data.get('upper_boundary', 0.0)
                
                if hasattr(cycle, 'highest_buy_price') and cycle.highest_buy_price > 0:
                    order_sl = cycle.highest_buy_price - (initial_stop_loss_pips * pip_value)
                else:
                    # First order - use order price as reference with initial_stop_loss_pips
                    order_sl = order_price - (initial_stop_loss_pips * pip_value)
                
                # Cap at upper boundary if zone movement mode requires it
                if cycle.zone_movement_mode == 'Move Both Sides' or cycle.zone_movement_mode == 'Move Up Only':
                    order_sl = max(order_sl, upper_boundary)
                
                logger.debug(f"📊 Calculated initial SL for BUY grid order using initial_stop_loss_pips ({initial_stop_loss_pips}): {order_sl:.5f}")
            
            # Validate stop loss is reasonable (at least 1 pip away from order price)
            min_sl_distance = pip_value * 1.0  # 1 pip minimum
            if order_price - order_sl < min_sl_distance:
                order_sl = order_price - min_sl_distance
                logger.warning(f"⚠️ Adjusted BUY stop loss to minimum distance: {order_sl:.5f}")

            # Validate order parameters before placement
            if lot_size <= 0:
                logger.error(f"❌ Invalid lot size for BUY order: {lot_size}")
                return False
            
            if order_price <= 0:
                logger.error(f"❌ Invalid order price for BUY order: {order_price}")
                return False
            
            logger.debug(f"📋 Placing BUY order: symbol={self.symbol}, volume={lot_size}, price={order_price:.5f}, sl={order_sl:.5f}, grid_level={grid_level}")
            
            # Place order through MetaTrader using the correct method
            order_result = self.meta_trader.place_buy_order(
                symbol=self.symbol,
                volume=lot_size,
                price=order_price,
                stop_loss=order_sl,
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
                    'price': order_result['order'].get('price_open', order_price),  # Use actual open price from MT5 result
                    'lot_size': lot_size,
                    'grid_level': grid_level,
                    'is_grid': True,
                    'order_type': f'grid_{grid_level}',
                    'status': 'active',
                    'placed_at': datetime.datetime.now().isoformat(),
                    'profit': 0.0,
                    'profit_pips': 0.0,
                    'last_profit_update': datetime.datetime.now().isoformat()
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
                
                # CRITICAL FIX: Immediately update profit for the grid order after creation
                try:
                    logger.info(f"🔄 Updating profit for grid BUY order {order_info['order_id']} in cycle {cycle.cycle_id}")
                    
                    # Get current profit from MetaTrader
                    order_profit = self._calculate_order_profit(order_info)
                    
                    # Update order with fresh profit data
                    order_info['profit'] = order_profit['profit']
                    order_info['profit_pips'] = order_profit['profit_pips']
                    order_info['last_profit_update'] = datetime.datetime.now().isoformat()
                    
                    logger.info(f"✅ Grid BUY order {order_info['order_id']} profit updated: ${order_profit['profit']:.2f} ({order_profit['profit_pips']:.2f} pips)")
                    
                except Exception as profit_error:
                    logger.warning(f"⚠️ Failed to update grid BUY order profit for {order_info['order_id']}: {str(profit_error)}")
                    # Continue anyway - the order is still created successfully
                
                logger.info(f"✅ MoveGuard grid BUY order placed successfully: {order_info['order_id']}")
                
                # NOTE: Stop loss sync removed - first order should keep its SL until second order gets activated
                # The sync will happen when the second order actually gets executed, not when it's placed
                
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

            # CRITICAL FIX: ALL grid orders should have SL set to current trailing SL
            # This ensures MT5 protects them even if bot crashes
            order_sl = 0
            
            # Get current trailing SL if it exists
            if hasattr(cycle, 'trailing_stop_loss') and cycle.trailing_stop_loss is not None and cycle.trailing_stop_loss > 0:
                # Use existing trailing SL
                order_sl = cycle.trailing_stop_loss
                logger.debug(f"📊 Using existing trailing SL for SELL grid order: {order_sl:.5f}")
            else:
                # Calculate SL based on initial_stop_loss_pips from configuration
                lower_boundary = cycle.zone_data.get('lower_boundary', 0.0)
                
                if hasattr(cycle, 'lowest_sell_price') and cycle.lowest_sell_price < 999999.0:
                    order_sl = cycle.lowest_sell_price + (initial_stop_loss_pips * pip_value)
                else:
                    # First order - use order price as reference with initial_stop_loss_pips
                    order_sl = order_price + (initial_stop_loss_pips * pip_value)
                
                # Cap at lower boundary if zone movement mode requires it
                if cycle.zone_movement_mode == 'Move Both Sides' or cycle.zone_movement_mode == 'Move Down Only':
                    order_sl = min(order_sl, lower_boundary)
                
                logger.debug(f"📊 Calculated initial SL for SELL grid order using initial_stop_loss_pips ({initial_stop_loss_pips}): {order_sl:.5f}")
            
            # Validate stop loss is reasonable (at least 1 pip away from order price)
            min_sl_distance = pip_value * 1.0  # 1 pip minimum
            if order_sl - order_price < min_sl_distance:
                order_sl = order_price + min_sl_distance
                logger.warning(f"⚠️ Adjusted SELL stop loss to minimum distance: {order_sl:.5f}")

            # Validate order parameters before placement
            if lot_size <= 0:
                logger.error(f"❌ Invalid lot size for SELL order: {lot_size}")
                return False
            
            if order_price <= 0:
                logger.error(f"❌ Invalid order price for SELL order: {order_price}")
                return False
            
            logger.debug(f"📋 Placing SELL order: symbol={self.symbol}, volume={lot_size}, price={order_price:.5f}, sl={order_sl:.5f}, grid_level={grid_level}")
            
            # Place order through MetaTrader using the correct method
            order_result = self.meta_trader.place_sell_order(
                symbol=self.symbol,
                volume=lot_size,
                price=order_price,
                stop_loss=order_sl,
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
                    'price': order_result['order'].get('price_open', order_price),  # Use actual open price from MT5 result
                    'lot_size': lot_size,
                    'grid_level': grid_level,
                    'is_grid': True,
                    'order_type': f'grid_{grid_level}',
                    'status': 'active',
                    'placed_at': datetime.datetime.now().isoformat(),
                    'profit': 0.0,
                    'profit_pips': 0.0,
                    'last_profit_update': datetime.datetime.now().isoformat()
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
                
                # CRITICAL FIX: Immediately update profit for the grid order after creation
                try:
                    logger.info(f"🔄 Updating profit for grid SELL order {order_info['order_id']} in cycle {cycle.cycle_id}")
                    
                    # Get current profit from MetaTrader
                    order_profit = self._calculate_order_profit(order_info)
                    
                    # Update order with fresh profit data
                    order_info['profit'] = order_profit['profit']
                    order_info['profit_pips'] = order_profit['profit_pips']
                    order_info['last_profit_update'] = datetime.datetime.now().isoformat()
                    
                    logger.info(f"✅ Grid SELL order {order_info['order_id']} profit updated: ${order_profit['profit']:.2f} ({order_profit['profit_pips']:.2f} pips)")
                    
                except Exception as profit_error:
                    logger.warning(f"⚠️ Failed to update grid SELL order profit for {order_info['order_id']}: {str(profit_error)}")
                    # Continue anyway - the order is still created successfully
                
                logger.info(f"✅ MoveGuard grid SELL order placed successfully: {order_info['order_id']}")
                
                # NOTE: Stop loss sync removed - first order should keep its SL until second order gets activated
                # The sync will happen when the second order actually gets executed, not when it's placed
                
                return True
            else:
                logger.error(f"❌ Failed to place MoveGuard grid SELL order")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing MoveGuard grid SELL order: {str(e)}")
            return False

    def _level_already_exists(self, cycle, target_level: int) -> bool:
        """Check if a grid level already exists in pending or active orders"""
        # Check pending orders
        if target_level in cycle.pending_order_levels:
            return True
        
        # Check active orders
        for order in cycle.orders:
            if order.get('status') == 'active' and order.get('grid_level') == target_level:
                return True
        
        return False

    def _calculate_pending_orders_needed(self, cycle) -> int:
        """Calculate how many pending orders are needed to maintain 5 pending orders"""
        current_pending_count = len(cycle.pending_orders)
        target_pending_count = 5
        return max(0, target_pending_count - current_pending_count)

    def _get_next_grid_level(self, cycle) -> int:
        """Get the next grid level to place - continues from highest active order level only (pending orders are excluded)
        
        If active orders are 1, 2, 3, next level should be 4.
        If no active orders, starts from 1.
        """
        # Find highest active order level (NOT pending orders)
        max_active_level = 0
        active_levels = []
        
        # Only check active orders (pending orders are ignored as they'll be replaced)
        for order in cycle.orders:
            if order.get('status') == 'active':
                grid_level = order.get('grid_level', 0)
                if grid_level > 0:  # Only count valid grid levels (> 0)
                    max_active_level = max(max_active_level, grid_level)
                    active_levels.append(grid_level)
        
        # Return next level after highest active order, ensuring we start from grid level 1
        next_level = max_active_level + 1
        result = max(next_level, 1)
        
        logger.debug(f"🔍 _get_next_grid_level: active_levels={sorted(active_levels)}, max_active={max_active_level}, next_level={result}")
        return result
    
    def _check_grid_level_gaps(self, cycle) -> bool:
        """Check if there are gaps in active grid order levels
        
        Returns True if gaps are detected (e.g., levels 1, 3, 5 instead of 1, 2, 3)
        Returns False if levels are sequential (1, 2, 3) or no active orders
        """
        try:
            # Get all active order grid levels
            active_levels = []
            for order in cycle.orders:
                if order.get('status') == 'active':
                    grid_level = order.get('grid_level', 0)
                    if grid_level > 0:  # Only count valid grid levels
                        active_levels.append(grid_level)
            
            # If no active orders or only 1, no gaps possible
            if len(active_levels) <= 1:
                return False
            
            # Sort levels
            active_levels.sort()
            
            # Check for gaps: levels should be consecutive (1, 2, 3...)
            for i in range(len(active_levels) - 1):
                if active_levels[i + 1] != active_levels[i] + 1:
                    logger.warning(f"⚠️ Gap detected in grid levels: {active_levels} - missing levels between {active_levels[i]} and {active_levels[i + 1]}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking grid level gaps: {str(e)}")
            return False

    def _validate_pending_orders_grid_levels(self, cycle) -> bool:
        """Validate that pending orders start from grid levels 1 to 5 when no active orders exist"""
        try:
            # Check if there are no active orders
            active_orders = [o for o in cycle.orders if o.get('status') == 'active']
            if len(active_orders) > 0:
                # If there are active orders, validation passes
                return True
            
            # If no active orders, check pending orders grid levels
            if len(cycle.pending_orders) == 0:
                # No pending orders, validation passes
                return True
            
            # Get all pending order grid levels
            pending_levels = []
            for order in cycle.pending_orders:
                grid_level = order.get('grid_level', 0)
                pending_levels.append(grid_level)
            
            # Sort the levels
            pending_levels.sort()
            
            # Check if pending orders start from 1 to 5 (or less if fewer than 5 orders)
            expected_levels = list(range(1, min(6, len(pending_levels) + 1)))
            
            # If pending levels don't match expected levels 1, 2, 3, 4, 5, validation fails
            if pending_levels != expected_levels:
                logger.warning(f"⚠️ Pending orders grid levels validation failed:")
                logger.warning(f"   - Expected levels: {expected_levels}")
                logger.warning(f"   - Actual levels: {pending_levels}")
                logger.warning(f"   - No active orders found, cancelling all pending orders")
                return False
            
            logger.debug(f"✅ Pending orders grid levels validation passed: {pending_levels}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validating pending orders grid levels: {str(e)}")
            return False

    def _maintain_pending_grid_orders(self, cycle, current_price: float, num_levels: int = 5) -> bool:
        """Maintain exactly 5 pending orders ahead of current position - check for existing levels"""
        try:
            if not hasattr(cycle, 'pending_orders'):
                cycle.pending_orders = []
                cycle.pending_order_levels = set()
            
            # Sync pending orders from PocketBase to ensure we have latest data
            self._sync_pending_orders_from_pocketbase(cycle)
            
            # CRITICAL: Check for gaps in active grid levels - if gaps exist, cancel all pending and replace
            if self._check_grid_level_gaps(cycle):
                logger.warning(f"🚨 Gap detected in active grid levels - cancelling all pending orders and will replace")
                self._cancel_cycle_pending_orders(cycle)
                # Continue to place new pending orders below
            
            # CRITICAL: Cancel pending orders that don't match cycle direction
            if hasattr(cycle, 'direction') and cycle.direction in ['BUY', 'SELL']:
                mismatched_pending = [o for o in cycle.pending_orders if o.get('direction') != cycle.direction]
                if len(mismatched_pending) > 0:
                    logger.warning(f"🚨 Found {len(mismatched_pending)} pending orders with wrong direction (cycle: {cycle.direction}) - cancelling them")
                    if cycle.direction == 'BUY':
                        self._cancel_sell_pending_orders(cycle)
                    else:
                        self._cancel_buy_pending_orders(cycle)
            
            # Validate pending orders grid levels before proceeding
            if not self._validate_pending_orders_grid_levels(cycle):
                logger.warning(f"🚨 Invalid pending orders grid levels detected in grid maintenance - cancelling all pending orders")
                self._cancel_cycle_pending_orders(cycle)
                # Continue to place new pending orders below
            
            # Calculate how many pending orders we need to maintain exactly 5
            pending_orders_needed = self._calculate_pending_orders_needed(cycle)
            
            if pending_orders_needed <= 0:
                logger.debug(f"📊 Grid maintenance: Already have sufficient pending orders ({len(cycle.pending_orders)}/5)")
                return True
            logger.info(f"📋 AUTOMATIC GRID MAINTENANCE: Need to place {pending_orders_needed} more pending orders to maintain 5 pending orders (current: {len(cycle.pending_orders)})")
            # Get grid parameters
            pip_value = self._get_pip_value()
            grid_interval_pips = self.get_cycle_config_value(cycle, 'grid_interval_pips', self.grid_interval_pips)
            entry_interval_pips = self.get_cycle_entry_interval_pips(cycle)
            
            # CRITICAL: Ensure cycle has a valid direction before placing orders
            if not hasattr(cycle, 'direction') or cycle.direction not in ['BUY', 'SELL']:
                logger.error(f"❌ Cycle {cycle.cycle_id} has invalid direction: {getattr(cycle, 'direction', None)} - cannot place pending orders")
                return False
            # Calculate grid start price
            upper = cycle.zone_data.get('upper_boundary', 0.0)
            lower = cycle.zone_data.get('lower_boundary', 0.0)
            
            # CRITICAL: Fix direction BEFORE placing orders to ensure all orders use same direction
            # Cancel pending orders with wrong direction before placing new ones
            if len(cycle.pending_orders) > 0:
                # Validate pending orders grid levels - cancel if invalid
                if not self._validate_pending_orders_grid_levels(cycle):
                    logger.warning(f"🚨 Invalid pending orders grid levels detected - cancelling all pending orders")
                    self._cancel_cycle_pending_orders(cycle)
                else:
                    # Check if pending orders match current cycle direction
                    mismatched_pending = [o for o in cycle.pending_orders if o.get('direction') != cycle.direction]
                    if len(mismatched_pending) > 0:
                        logger.warning(f"🚨 Found {len(mismatched_pending)} pending orders with wrong direction (cycle: {cycle.direction}) - cancelling them")
                        if cycle.direction == 'BUY':
                            self._cancel_sell_pending_orders(cycle)
                        else:
                            self._cancel_buy_pending_orders(cycle)
            
            # CRITICAL: Use current cycle direction for ALL pending orders (don't change it mid-placement)
            # Store direction to ensure consistency throughout this function
            order_direction = cycle.direction
            
            logger.info(f"📋 Placing {pending_orders_needed} pending {order_direction} orders - cycle direction: {order_direction}")
            
            if order_direction == 'BUY':
                # Check if this is a grid restart scenario
                grid_restart_completed = getattr(cycle, 'grid_restart_completed', False)
                is_grid_restart = (hasattr(cycle, 'grid_restart_start_price') and 
                                 cycle.zone_movement_mode in ['No Move', 'Move Down Only'] and
                                 not grid_restart_completed)
                
                if is_grid_restart:
                    grid_start_price = getattr(cycle, 'grid_restart_start_price', current_price)
                else:
                    grid_start_price = upper + (entry_interval_pips * pip_value)
                
                # Place pending orders one by one, checking for existing levels
                # Get starting level from highest active order
                start_level = self._get_next_grid_level(cycle)
                
                for order_index in range(pending_orders_needed):
                    # Calculate next level: start from highest active + order_index
                    target_level = start_level + order_index
                    
                    # Check if this level already exists (in active or pending)
                    if self._level_already_exists(cycle, target_level):
                        logger.debug(f"📊 Level {target_level} already exists, skipping")
                        # If level exists, try next level
                        target_level = start_level + order_index + 1
                        # Check again
                        if self._level_already_exists(cycle, target_level):
                            logger.warning(f"⚠️ Level {target_level} also exists, continuing to next")
                            continue
                    
                    logger.info(f"📋 Placing {order_direction} pending order #{order_index + 1}/{pending_orders_needed} at grid level {target_level} (start_level={start_level})")
                    
                    # Note: Level will be added to pending_order_levels inside _place_pending_grid_order
                    
                    # Calculate target price for this level
                    # For BUY orders: grid level 1 should be at grid_start_price, level 2 should be grid_start_price + grid_interval_pips
                    target_price = grid_start_price + (grid_interval_pips * (target_level - 1) * pip_value)
                    
                    # Debug logging to identify price calculation issues
                    logger.info(f"🔍 BUY Grid Level {target_level} Price Calculation:")
                    logger.info(f"   - grid_start_price: {grid_start_price:.5f}")
                    logger.info(f"   - grid_interval_pips: {grid_interval_pips}")
                    logger.info(f"   - pip_value: {pip_value:.5f}")
                    logger.info(f"   - target_level: {target_level}")
                    logger.info(f"   - calculated target_price: {target_price:.5f}")
                    
                    # Enhanced retry logic for BUY orders
                    success = False
                    retry_count = 0
                    max_retries = 3

                    while not success and retry_count < max_retries:
                        retry_count += 1
                        
                        # Only place if target price is above current price (for BUY orders)
                        if target_price > current_price:
                            logger.info(f"🔄 Attempting to place BUY level {target_level} at price {target_price:.5f} (attempt {retry_count}/{max_retries})")
                            success = self._place_pending_grid_order(cycle, target_level, target_price, order_direction, current_price)
                            
                            if not success and retry_count < max_retries:
                                # Get fresh ask price for retry
                                ask = self.meta_trader.get_ask(self.symbol)
                                target_price = ask + (grid_interval_pips * (target_level - 1) * pip_value)
                                grid_start_price = ask
                                logger.warning(f"⚠️ BUY level {target_level} failed, retrying with ask price {ask:.5f}, new target {target_price:.5f}")
                                success = self._place_pending_grid_order(cycle, target_level, target_price, order_direction, ask)
                        else:
                            # Target price is not above current price, use ask price
                            ask = self.meta_trader.get_ask(self.symbol)
                            target_price = ask + (grid_interval_pips * (target_level - 1) * pip_value)
                            grid_start_price = ask 
                            logger.info(f"🔄 BUY level {target_level} price too low, using ask price {ask:.5f}, target {target_price:.5f} (attempt {retry_count}/{max_retries})")
                            success = self._place_pending_grid_order(cycle, target_level, target_price, order_direction, ask)
                    
                    if not success:
                        logger.error(f"❌ Failed to place {order_direction} level {target_level} after {max_retries} attempts - stopping grid placement")
                        # Note: Level removal handled in _place_pending_grid_order on failure
                        # cancel all pending orders
                        # self._cancel_cycle_pending_orders(cycle)
                    else:
                        logger.info(f"✅ Successfully placed {order_direction} level {target_level} at price {target_price:.5f}")
            elif order_direction == 'SELL':
                # Check if this is a grid restart scenario
                grid_restart_completed = getattr(cycle, 'grid_restart_completed', False)
                is_grid_restart = (hasattr(cycle, 'grid_restart_start_price') and 
                                 cycle.zone_movement_mode in ['No Move', 'Move Down Only'] and
                                 not grid_restart_completed)
                
                if is_grid_restart:
                    grid_start_price = getattr(cycle, 'grid_restart_start_price', current_price)
                else:
                    grid_start_price = lower - (entry_interval_pips * pip_value)
                
                # Place pending orders one by one, checking for existing levels
                # Get starting level from highest active order
                start_level = self._get_next_grid_level(cycle)
                
                for order_index in range(pending_orders_needed):
                    # Calculate next level: start from highest active + order_index
                    target_level = start_level + order_index
                    
                    # Check if this level already exists (in active or pending)
                    if self._level_already_exists(cycle, target_level):
                        logger.debug(f"📊 Level {target_level} already exists, skipping")
                        # If level exists, try next level
                        target_level = start_level + order_index + 1
                        # Check again
                        if self._level_already_exists(cycle, target_level):
                            logger.warning(f"⚠️ Level {target_level} also exists, continuing to next")
                            continue
                    
                    logger.info(f"📋 Placing {order_direction} pending order #{order_index + 1}/{pending_orders_needed} at grid level {target_level}")
                    
                    # Note: Level will be added to pending_order_levels inside _place_pending_grid_order
                    
                    # Calculate target price for this level
                    # For SELL orders: grid level 1 should be at grid_start_price, level 2 should be grid_start_price - grid_interval_pips
                    target_price = grid_start_price - (grid_interval_pips * (target_level - 1) * pip_value)
                    
                    # Debug logging to identify price calculation issues
                    logger.info(f"🔍 SELL Grid Level {target_level} Price Calculation:")
                    logger.info(f"   - grid_start_price: {grid_start_price:.5f}")
                    logger.info(f"   - grid_interval_pips: {grid_interval_pips}")
                    logger.info(f"   - pip_value: {pip_value:.5f}")
                    logger.info(f"   - target_level: {target_level}")
                    logger.info(f"   - calculated target_price: {target_price:.5f}")
                    
                    # Enhanced retry logic for SELL orders
                    success = False
                    retry_count = 0
                    max_retries = 3
                    
                    while not success and retry_count < max_retries:
                        retry_count += 1
                        
                        # Only place if target price is below current price (for SELL orders)
                        if target_price < current_price:
                            logger.info(f"🔄 Attempting to place SELL level {target_level} at price {target_price:.5f} (attempt {retry_count}/{max_retries})")
                            success = self._place_pending_grid_order(cycle, target_level, target_price, order_direction, current_price)
                            
                            if not success and retry_count < max_retries:
                                # Get fresh bid price for retry
                                bid = self.meta_trader.get_bid(self.symbol)
                                target_price = bid - (grid_interval_pips * (target_level - 1) * pip_value)
                                grid_start_price = bid 
                                logger.warning(f"⚠️ SELL level {target_level} failed, retrying with bid price {bid:.5f}, new target {target_price:.5f}")
                                success = self._place_pending_grid_order(cycle, target_level, target_price, order_direction, bid)

                        else:
                            # Target price is not below current price, use bid price
                            bid = self.meta_trader.get_bid(self.symbol)
                            target_price = bid - (grid_interval_pips * (target_level - 1) * pip_value)
                            grid_start_price = bid 
                            logger.info(f"🔄 SELL level {target_level} price too high, using bid price {bid:.5f}, target {target_price:.5f} (attempt {retry_count}/{max_retries})")
                            success = self._place_pending_grid_order(cycle, target_level, target_price, order_direction, bid)
                    
                    if not success:
                        logger.error(f"❌ Failed to place {order_direction} level {target_level} after {max_retries} attempts - stopping grid placement")
                        # Note: Level removal handled in _place_pending_grid_order on failure
                        # cancel all pending orders
                        # self._cancel_cycle_pending_orders(cycle)
                    else:
                        logger.info(f"✅ Successfully placed {order_direction} level {target_level} at price {target_price:.5f}")
                    
            return True
            
        except Exception as e:
            logger.error(f"❌ Error maintaining pending grid orders: {str(e)}")
            return False

    def _place_pending_grid_order(self, cycle, grid_level: int, target_price: float, direction: str, current_price: float) -> bool:
        """Place a pending grid order at specified level and price"""
        try:
            logger.info(f"📋 MoveGuard placing pending {direction} order at level {grid_level}, price {target_price:.5f}")
            
            # CRITICAL: Ensure order direction matches cycle direction
            if not hasattr(cycle, 'direction') or cycle.direction != direction:
                logger.error(f"❌ Order direction {direction} does not match cycle direction {getattr(cycle, 'direction', None)} - cancelling order placement")
                return False
            
            # CRITICAL: Check if this level already exists BEFORE placing order to prevent duplicates
            if self._level_already_exists(cycle, grid_level):
                logger.warning(f"⚠️ Grid level {grid_level} already exists - skipping duplicate order placement")
                return False
            
            # CRITICAL: Add level to pending_order_levels BEFORE placing to prevent race conditions
            if not hasattr(cycle, 'pending_order_levels'):
                cycle.pending_order_levels = set()
            cycle.pending_order_levels.add(grid_level)
            
            # Get cycle-specific configuration values
            initial_stop_loss_pips = self.get_cycle_config_value(cycle, 'initial_stop_loss_pips', self.initial_stop_loss_pips)
            lot_size = self.get_cycle_config_value(cycle, 'lot_size', self.lot_size)
            max_trades_per_cycle = self.get_cycle_config_value(cycle, 'max_trades_per_cycle', self.max_trades_per_cycle)
            
            # Check total trades limit
            total_orders = len(cycle.orders) if hasattr(cycle, 'orders') else 0
            if total_orders >= max_trades_per_cycle:
                logger.info(f"⚠️ Cycle {cycle.cycle_id} has reached max total trades ({max_trades_per_cycle}) - cannot place pending order")
                return False
            
            # Calculate SL for pending order (use current trailing SL or calculate using initial_stop_loss_pips)
            pip_value = self._get_pip_value()
            order_sl = 0
            
            if hasattr(cycle, 'trailing_stop_loss') and cycle.trailing_stop_loss is not None and cycle.trailing_stop_loss > 0:
                # Use existing trailing SL if it's a valid price (not pips)
                if cycle.trailing_stop_loss > 1000:  # Valid price range for BTCUSDm
                    order_sl = cycle.trailing_stop_loss
                    logger.debug(f"📊 Using existing trailing SL for pending {direction} grid order: {order_sl:.5f}")
                else:
                    logger.warning(f"Trailing SL {cycle.trailing_stop_loss} appears to be in pips, calculating proper price using initial_stop_loss_pips")
                    if direction == 'BUY':
                        order_sl = target_price - (initial_stop_loss_pips * pip_value)
                    else:  # SELL
                        order_sl = target_price + (initial_stop_loss_pips * pip_value)
            else:
                # Calculate initial SL using initial_stop_loss_pips
                if direction == 'BUY':
                    order_sl = target_price - (initial_stop_loss_pips * pip_value)
                else:  # SELL
                    order_sl = target_price + (initial_stop_loss_pips * pip_value)
                logger.debug(f"📊 Calculated initial SL for pending {direction} grid order using initial_stop_loss_pips ({initial_stop_loss_pips}): {order_sl:.5f}")
            
            # CRITICAL: Validate SL distance from order price to prevent MT5 errors
            if order_sl > 0:
                min_sl_distance = pip_value * 10.0  # Minimum 10 pips distance
                
                if direction == 'BUY':
                    # For BUY orders, SL must be below order price
                    if order_sl >= target_price:
                        # SL too close or above order price - set to minimum distance below
                        order_sl = target_price - min_sl_distance
                        logger.warning(f"⚠️ BUY order SL too close to price, adjusted to {order_sl:.5f}")
                    elif (target_price - order_sl) < min_sl_distance:
                        # SL too close to order price - adjust to minimum distance
                        order_sl = target_price - min_sl_distance
                        logger.warning(f"⚠️ BUY order SL too close to price, adjusted to {order_sl:.5f}")
                else:  # SELL
                    # For SELL orders, SL must be above order price
                    if order_sl <= target_price:
                        # SL too close or below order price - set to minimum distance above
                        order_sl = target_price + min_sl_distance
                        logger.warning(f"⚠️ SELL order SL too close to price, adjusted to {order_sl:.5f}")
                    elif (order_sl - target_price) < min_sl_distance:
                        # SL too close to order price - adjust to minimum distance
                        order_sl = target_price + min_sl_distance
                        logger.warning(f"⚠️ SELL order SL too close to price, adjusted to {order_sl:.5f}")
                
                logger.info(f"📊 {direction} order SL validation: order_price={target_price:.5f}, sl={order_sl:.5f}, distance={abs(target_price - order_sl):.5f}")
            
            # Enhanced logging for debugging order placement
            logger.info(f"📊 Order placement details: direction={direction}, target_price={target_price:.5f}, current_price={current_price:.5f}, sl={order_sl:.5f}, lot_size={lot_size}")
            
            # Place pending order via MT5
            if direction == 'BUY':
                result = self.meta_trader.place_pending_buy_order(
                    symbol=self.symbol,
                    target_price=target_price,
                    current_price=current_price,
                    volume=lot_size,
                    sl=order_sl,
                    tp=0,
                    comment=f"Grid_{grid_level}_BUY",
                    force_buy_stop=True  # Always use BUY_STOP
                )
            else:  # SELL
                result = self.meta_trader.place_pending_sell_order(
                    symbol=self.symbol,
                    target_price=target_price,
                    current_price=current_price,
                    volume=lot_size,
                    sl=order_sl,
                    tp=0,
                    comment=f"Grid_{grid_level}_SELL",
                    force_sell_stop=True  # Always use SELL_STOP
                )
            
            # Enhanced result logging
            if result:
                logger.info(f"✅ MT5 order placement successful for {direction} level {grid_level}: {result}")
            else:
                logger.error(f"❌ MT5 order placement failed for {direction} level {grid_level} - result: {result}")
            
            if result:
                # Extract order ID from result - handle different result formats
                order_id = None
                
                # Handle tuple format (TradeOrder objects wrapped in tuple)
                if isinstance(result, tuple) and len(result) > 0:
                    trade_order = result[0]
                    order_id = getattr(trade_order, 'ticket', None)
                elif isinstance(result, dict):
                    # Dictionary format
                    order_id = result.get('order')
                    if not order_id:
                        order_id = result.get('ticket')
                else:
                    # Object format - try different attributes
                    order_id = getattr(result, 'order', None)
                    if not order_id:
                        order_id = getattr(result, 'ticket', None)
                    if not order_id and hasattr(result, '_asdict'):
                        # NamedTuple format
                        result_dict = result._asdict()
                        order_id = result_dict.get('order') or result_dict.get('ticket')
                
                if order_id:
                    # Store pending order info
                    pending_order = {
                        'order_id': order_id,
                        'is_active': False,
                        'is_initial': False,
                        'is_grid': True,
                        'order_type': f'grid_{grid_level}',
                        'profit': 0.0,
                        'profit_pips': 0.0,
                        'last_profit_update': datetime.datetime.now().isoformat(),
                        'placed_at': datetime.datetime.now().isoformat(),
                        'ticket': order_id,
                        'grid_level': grid_level,
                        'target_price': target_price,
                        'direction': direction,
                        'sl': order_sl,
                        'tp': 0,
                        'price': target_price,
                        'lot_size': lot_size,
                        'comment': f"Grid_{grid_level}_{direction}",
                        'status': 'pending',
                     
                    }
                    
                    cycle.pending_orders.append(pending_order)
                    # Note: grid_level already added to pending_order_levels at the start of this function
                    
                    # CRITICAL FIX: Add to main cycle orders list as well
                    if hasattr(cycle, 'orders'):
                        cycle.orders.append(pending_order)
                    else:
                        cycle.orders = [pending_order]
                    
                    # Sync pending orders to PocketBase
                    self._sync_pending_orders_to_pocketbase(cycle)
                    
                    if direction == 'BUY':
                        logger.info(f"✅ MoveGuard pending {direction} order placed: Level {grid_level}, ID {order_id}, Price {target_price:.5f} (BUY_STOP forced)")
                    else:
                        logger.info(f"✅ MoveGuard pending {direction} order placed: Level {grid_level}, ID {order_id}, Price {target_price:.5f} (SELL_STOP forced)")
                    return True
                else:
                    logger.error(f"❌ Failed to extract order ID from pending order result: {result}")
                    # Remove level from pending_order_levels since order placement failed
                    if hasattr(cycle, 'pending_order_levels'):
                        cycle.pending_order_levels.discard(grid_level)
                    return False
            else:
                logger.error(f"❌ Failed to place pending {direction} order at level {grid_level}")
                # Remove level from pending_order_levels since order placement failed
                if hasattr(cycle, 'pending_order_levels'):
                    cycle.pending_order_levels.discard(grid_level)
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing pending grid order: {str(e)}")
            # Remove level from pending_order_levels if there was an exception
            if hasattr(cycle, 'pending_order_levels'):
                cycle.pending_order_levels.discard(grid_level)
            return False

    def _cancel_sell_pending_orders(self, cycle) -> bool:
        """Cancel all SELL pending orders for a cycle"""
        try:
            if not hasattr(cycle, 'pending_orders') or not cycle.pending_orders:
                logger.info(f"No pending orders to cancel for cycle {cycle.cycle_id}")
                return True
            
            # Filter for SELL orders only
            sell_pending_orders = [order for order in cycle.pending_orders if order.get('direction') == 'SELL']
            
            if not sell_pending_orders:
                logger.info(f"No SELL pending orders to cancel for cycle {cycle.cycle_id}")
                return True
            
            cancelled_count = 0
            for pending_order in sell_pending_orders[:]:  # Copy list to avoid modification during iteration
                order_id = pending_order.get('order_id')
                grid_level = pending_order.get('grid_level')
                direction = pending_order.get('direction')
                
                if order_id and direction == 'SELL':
                    result = self.meta_trader.cancel_pending_order(order_id, self.symbol)
                    if result:
                        cancelled_count += 1
                        
                        # Update status in main orders list from 'pending' to 'cancelled'
                        for order in cycle.orders:
                            if order.get('order_id') == order_id:
                                order['status'] = 'cancelled'
                                order['cancelled_at'] = datetime.datetime.now().isoformat()
                                logger.info(f"🔄 Updated SELL order {order_id} status from 'pending' to 'cancelled' in cycle orders")
                                break
                        
                        # Remove from pending orders list
                        cycle.pending_orders.remove(pending_order)
                        cycle.pending_order_levels.discard(grid_level)
                        
                        # Remove from main orders list if it exists there
                        try:
                            cycle.orders.remove(pending_order)
                        except ValueError:
                            # Order not in main orders list - that's fine
                            pass
                        
                        logger.info(f"✅ Cancelled SELL pending order {order_id} (level {grid_level})")
                    else:
                        # Pending order cancellation failed - check if it was activated as market order
                        logger.warning(f"⚠️ Failed to cancel SELL pending order {order_id} - checking if it was activated as market order")
                        
                        # Search for the order as a market position
                        position = self.meta_trader.get_position_by_ticket(int(order_id))
                        if position and len(position) > 0:
                            logger.info(f"🔍 Found SELL pending order {order_id} as activated market position - will close it")
                            
                            # Update the pending order to active status in cycle.orders
                            for order in cycle.orders:
                                if order.get('order_id') == order_id:
                                    order['status'] = 'active'
                                    order['activated_at'] = datetime.datetime.now().isoformat()
                                    logger.info(f"🔄 Updated SELL order {order_id} status from 'pending' to 'active' (activated)")
                                    break
                            
                            # Remove from pending orders list since it's now active
                            cycle.pending_orders.remove(pending_order)
                            cycle.pending_order_levels.discard(grid_level)
                            
                            # Remove from main orders list if it exists there (since it's now in active_orders)
                            try:
                                cycle.orders.remove(pending_order)
                            except ValueError:
                                # Order not in main orders list - that's fine
                                pass
                            
                            # Add to active orders if the list exists
                            if hasattr(cycle, 'active_orders') and isinstance(cycle.active_orders, list):
                                cycle.active_orders.append(pending_order)
                            
                            cancelled_count += 1  # Count as handled
                            logger.info(f"✅ Handled activated SELL pending order {order_id} (level {grid_level}) - now active")
                        else:
                            logger.error(f"❌ Failed to cancel SELL pending order {order_id} and order not found as market position")
            
            logger.info(f"🔄 MoveGuard cancelled {cancelled_count}/{len(sell_pending_orders)} SELL pending orders for cycle {cycle.cycle_id}")
            
            # Sync changes to PocketBase
            self._sync_pending_orders_to_pocketbase(cycle)
            
            return cancelled_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error cancelling SELL pending orders for cycle {cycle.cycle_id}: {str(e)}")
            return False

    def _cancel_buy_pending_orders(self, cycle) -> bool:
        """Cancel all BUY pending orders for a cycle"""
        try:
            if not hasattr(cycle, 'pending_orders') or not cycle.pending_orders:
                logger.info(f"No pending orders to cancel for cycle {cycle.cycle_id}")
                return True
            
            # Filter for BUY orders only
            buy_pending_orders = [order for order in cycle.pending_orders if order.get('direction') == 'BUY']
            
            if not buy_pending_orders:
                logger.info(f"No BUY pending orders to cancel for cycle {cycle.cycle_id}")
                return True
            
            cancelled_count = 0
            for pending_order in buy_pending_orders[:]:  # Copy list to avoid modification during iteration
                order_id = pending_order.get('order_id')
                grid_level = pending_order.get('grid_level')
                direction = pending_order.get('direction')
                
                if order_id and direction == 'BUY':
                    result = self.meta_trader.cancel_pending_order(order_id, self.symbol)
                    if result:
                        cancelled_count += 1
                        
                        # Update status in main orders list from 'pending' to 'cancelled'
                        for order in cycle.orders:
                            if order.get('order_id') == order_id:
                                order['status'] = 'cancelled'
                                order['cancelled_at'] = datetime.datetime.now().isoformat()
                                logger.info(f"🔄 Updated BUY order {order_id} status from 'pending' to 'cancelled' in cycle orders")
                                break
                        
                        # Remove from pending orders list
                        cycle.pending_orders.remove(pending_order)
                        cycle.pending_order_levels.discard(grid_level)
                        
                        # Remove from main orders list if it exists there
                        try:
                            cycle.orders.remove(pending_order)
                        except ValueError:
                            # Order not in main orders list - that's fine
                            pass
                        
                        logger.info(f"✅ Cancelled BUY pending order {order_id} (level {grid_level})")
                    else:
                        # Pending order cancellation failed - check if it was activated as market order
                        logger.warning(f"⚠️ Failed to cancel BUY pending order {order_id} - checking if it was activated as market order")
                        
                        # Search for the order as a market position
                        position = self.meta_trader.get_position_by_ticket(int(order_id))
                        if position and len(position) > 0:
                            logger.info(f"🔍 Found BUY pending order {order_id} as activated market position - will close it")
                            
                            # Update the pending order to active status in cycle.orders
                            for order in cycle.orders:
                                if order.get('order_id') == order_id:
                                    order['status'] = 'active'
                                    order['activated_at'] = datetime.datetime.now().isoformat()
                                    logger.info(f"🔄 Updated BUY order {order_id} status from 'pending' to 'active' (activated)")
                                    break
                            
                            # Remove from pending orders list since it's now active
                            cycle.pending_orders.remove(pending_order)
                            cycle.pending_order_levels.discard(grid_level)
                            
                            # Remove from main orders list if it exists there (since it's now in active_orders)
                            try:
                                cycle.orders.remove(pending_order)
                            except ValueError:
                                # Order not in main orders list - that's fine
                                pass
                            
                            # Add to active orders if the list exists
                            if hasattr(cycle, 'active_orders') and isinstance(cycle.active_orders, list):
                                cycle.active_orders.append(pending_order)
                            
                            cancelled_count += 1  # Count as handled
                            logger.info(f"✅ Handled activated BUY pending order {order_id} (level {grid_level}) - now active")
                        else:
                            logger.error(f"❌ Failed to cancel BUY pending order {order_id} and order not found as market position")
            
            logger.info(f"🔄 MoveGuard cancelled {cancelled_count}/{len(buy_pending_orders)} BUY pending orders for cycle {cycle.cycle_id}")
            
            # Sync changes to PocketBase
            self._sync_pending_orders_to_pocketbase(cycle)
            
            return cancelled_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error cancelling BUY pending orders for cycle {cycle.cycle_id}: {str(e)}")
            return False

    def _cancel_cycle_pending_orders(self, cycle) -> bool:
        """Cancel all pending orders for a cycle"""
        try:
            if not hasattr(cycle, 'pending_orders') or not cycle.pending_orders:
                logger.info(f"No pending orders to cancel for cycle {cycle.cycle_id}")
                return True
            
            cancelled_count = 0
            for pending_order in cycle.pending_orders[:]:  # Copy list to avoid modification during iteration
                order_id = pending_order.get('order_id')
                grid_level = pending_order.get('grid_level')
                
                if order_id:
                    result = self.meta_trader.cancel_pending_order(order_id, self.symbol)
                    if result:
                        cancelled_count += 1
                        
                        # Update status in main orders list from 'pending' to 'cancelled'
                        for order in cycle.orders:
                            if order.get('order_id') == order_id:
                                order['status'] = 'cancelled'
                                order['cancelled_at'] = datetime.datetime.now().isoformat()
                                logger.info(f"🔄 Updated order {order_id} status from 'pending' to 'cancelled' in cycle orders")
                                break
                        
                        # Remove from pending orders list
                        cycle.pending_orders.remove(pending_order)
                        cycle.pending_order_levels.discard(grid_level)
                        
                        # Remove from main orders list if it exists there
                        try:
                            cycle.orders.remove(pending_order)
                        except ValueError:
                            # Order not in main orders list - that's fine
                            pass
                        
                        logger.info(f"✅ Cancelled pending order {order_id} (level {grid_level})")
                    else:
                        # Pending order cancellation failed - check if it was activated as market order
                        logger.warning(f"⚠️ Failed to cancel pending order {order_id} - checking if it was activated as market order")
                        
                        # Search for the order as a market position
                        position = self.meta_trader.get_position_by_ticket(int(order_id))
                        if position and len(position) > 0:
                            logger.info(f"🔍 Found pending order {order_id} as activated market position - will close it")
                            
                            # Update the pending order to active status in cycle.orders
                            for order in cycle.orders:
                                if order.get('order_id') == order_id:
                                    order['status'] = 'active'
                                    order['activated_at'] = datetime.datetime.now().isoformat()
                                    logger.info(f"🔄 Updated order {order_id} status from 'pending' to 'active' (activated)")
                                    break
                            
                            # Remove from pending orders list since it's now active
                            cycle.pending_orders.remove(pending_order)
                            cycle.pending_order_levels.discard(grid_level)
                            
                            # Remove from main orders list if it exists there (since it's now in active_orders)
                            try:
                                cycle.orders.remove(pending_order)
                            except ValueError:
                                # Order not in main orders list - that's fine
                                pass
                            
                            # Add to active orders if the list exists
                            if hasattr(cycle, 'active_orders') and isinstance(cycle.active_orders, list):
                                cycle.active_orders.append(pending_order)
                            
                            cancelled_count += 1  # Count as handled
                            logger.info(f"✅ Handled activated pending order {order_id} (level {grid_level}) - now active")
                        else:
                            logger.warning(f"⚠️ Failed to cancel pending order {order_id} and order not found as market position - likely already cancelled or executed")
                            # Mark as cancelled in cycle data even if we can't cancel it in MT5
                            for order in cycle.orders:
                                if order.get('order_id') == order_id:
                                    order['status'] = 'cancelled'
                                    order['cancelled_at'] = datetime.datetime.now().isoformat()
                                    order['cancelled_reason'] = 'not_found_in_mt5'
                                    logger.info(f"🔄 Updated order {order_id} status to 'cancelled' in cycle data")
                                    break
                            
                            # Remove from pending orders list
                            cycle.pending_orders.remove(pending_order)
                            cycle.pending_order_levels.discard(grid_level)
                            
                            # Remove from main orders list if it exists there
                            try:
                                cycle.orders.remove(pending_order)
                            except ValueError:
                                # Order not in main orders list - that's fine
                                pass
                            
                            cancelled_count += 1  # Count as handled
                            logger.info(f"✅ Cleaned up pending order {order_id} (level {grid_level}) from cycle data")
            
            logger.info(f"🔄 MoveGuard cancelled {cancelled_count}/{len(cycle.pending_orders)} pending orders for cycle {cycle.cycle_id}")
            
            # Clear tracking if all orders cancelled
            if cancelled_count == len(cycle.pending_orders):
                cycle.pending_orders = []
                cycle.pending_order_levels = set()
                
                # Sync cleared pending orders to PocketBase
                self._sync_pending_orders_to_pocketbase(cycle)
            
            # Always sync cycle data to database after pending order operations
            # This ensures the cycle data is consistent even if some operations failed
            try:
                logger.info(f"🔄 Syncing cycle {cycle.cycle_id} data to database after pending order operations")
                self._update_cycle_in_database(cycle, force_update=True)
            except Exception as sync_error:
                logger.error(f"❌ Failed to sync cycle {cycle.cycle_id} data to database: {str(sync_error)}")
            
            return cancelled_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error cancelling pending orders for cycle {cycle.cycle_id}: {str(e)}")
            return False

    def _get_pending_order_summary(self, cycle) -> dict:
        """Get a summary of the automatic pending order placement system for a cycle"""
        try:
            if not hasattr(cycle, 'pending_orders'):
                return {
                    'pending_orders_count': 0,
                    'pending_levels': [],
                    'system_status': 'Not initialized'
                }
            
            pending_orders = cycle.pending_orders
            pending_levels = list(cycle.pending_order_levels) if hasattr(cycle, 'pending_order_levels') else []
            
            # Get active orders count for context
            active_orders = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
            
            return {
                'pending_orders_count': len(pending_orders),
                'pending_levels': sorted(pending_levels),
                'active_orders_count': len(active_orders),
                'system_status': 'Active' if pending_orders else 'No pending orders',
                'next_levels_needed': 3 - len(pending_orders) if len(pending_orders) < 3 else 0,
                'cycle_direction': getattr(cycle, 'direction', 'Unknown')
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting pending order summary: {str(e)}")
            return {
                'pending_orders_count': 0,
                'pending_levels': [],
                'system_status': 'Error'
            }

    def _update_pending_order_on_trigger(self, cycle, order_id: int) -> bool:
        """Handle when a pending order becomes an active position and immediately place next pending order"""
        try:
            # Find the pending order
            pending_order = None
            for po in cycle.pending_orders:
                if po.get('order_id') == order_id:
                    pending_order = po
                    break
            
            if not pending_order:
                logger.warning(f"Pending order {order_id} not found in cycle {cycle.cycle_id}")
                return False
            
            grid_level = pending_order.get('grid_level')
            direction = pending_order.get('direction')
            target_price = pending_order.get('target_price', 0)
            
            logger.info(f"🎯 PENDING ORDER ACTIVATED: {direction} order {order_id} (level {grid_level}) at {target_price:.5f}")
            
            # Update status in main orders list from 'pending' to 'active'
            order_found_in_main = False
            for order in cycle.orders:
                if order.get('order_id') == order_id:
                    order['status'] = 'active'
                    order['triggered_at'] = datetime.datetime.now().isoformat()
                    order_found_in_main = True
                    logger.info(f"🔄 Updated order {order_id} status from 'pending' to 'active' in cycle orders")
                    break
            
            # If order not found in main orders list, add it (shouldn't happen with new implementation)
            if not order_found_in_main:
                logger.warning(f"⚠️ Order {order_id} not found in main orders list - adding it now")
                pending_order['status'] = 'active'
                pending_order['triggered_at'] = datetime.datetime.now().isoformat()
                cycle.orders.append(pending_order)
            
            # Remove from pending orders tracking (but keep in main orders list)
            cycle.pending_orders.remove(pending_order)
            cycle.pending_order_levels.discard(grid_level)
            
            # Sync updated pending orders to PocketBase
            self._sync_pending_orders_to_pocketbase(cycle)
            
            logger.info(f"✅ Pending {direction} order {order_id} (level {grid_level}) triggered and became active position")
            logger.info(f"📊 Order Movement Summary:")
            logger.info(f"   - Removed from pending_orders: {order_id}")
            logger.info(f"   - Status updated to 'active' in main orders list")
            logger.info(f"   - Pending orders count: {len(cycle.pending_orders)}")
            logger.info(f"   - Total orders count: {len(cycle.orders)}")
            
            # DISABLED: Grid level 0 SL sync - keeping original SL for initial order
            # if grid_level == 1:
            #     self._sync_grid_0_sl_on_activation(cycle, direction)
            
            # IMMEDIATELY place next pending order to maintain grid ahead
            logger.info(f"🚀 AUTOMATIC NEXT ORDER PLACEMENT: Placing next pending order after activation of level {grid_level}")
            next_order_success = self._maintain_pending_grid_orders(cycle, target_price, 5)
            
            if next_order_success:
                logger.info(f"✅ SUCCESS: Next pending order placed automatically after level {grid_level} activation")
            else:
                logger.warning(f"⚠️ WARNING: Failed to place next pending order after level {grid_level} activation")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating pending order on trigger: {str(e)}")
            return False

    def _monitor_pending_orders(self, cycle, current_price: float) -> bool:
        """Monitor pending orders and check their actual status in MT5"""
        try:
            if not hasattr(cycle, 'pending_orders') or not cycle.pending_orders:
                return True
            
            # Check each pending order by querying MT5
            for pending_order in cycle.pending_orders[:]:  # Copy list to avoid modification during iteration
                order_id = pending_order.get('order_id')
                grid_level = pending_order.get('grid_level')
                direction = pending_order.get('direction')
                target_price = pending_order.get('target_price')
                
                if not order_id:
                    continue
                
                # Check actual order status in MT5
                order_status = self._check_pending_order_status_in_mt5(order_id)
                
                if order_status == 'filled':
                    # Order has been triggered and filled
                    target_price_safe = target_price or 0.0
                    logger.info(f"✅ {direction} pending order {order_id} (level {grid_level}) filled at {target_price_safe:.5f}")
                    logger.info(f"🔄 TRIGGERING AUTOMATIC NEXT ORDER PLACEMENT for cycle {cycle.cycle_id}")
                    self._update_pending_order_on_trigger(cycle, order_id)
                    
                    # Update cycle tracking prices
                    if direction == 'BUY':
                        cycle.highest_buy_price = max(cycle.highest_buy_price, current_price)
                        # Update trailing SL
                        pip_value = self._get_pip_value()
                        cycle_zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
                        upper = cycle.zone_data.get('upper_boundary', 0.0)
                        new_trailing_sl = cycle.highest_buy_price - (cycle_zone_threshold_pips * pip_value)
                        new_trailing_sl = max(new_trailing_sl, upper)
                        cycle.trailing_stop_loss = new_trailing_sl
                        logger.info(f"📊 Updated BUY trailing SL to {new_trailing_sl:.5f} after pending order trigger")
                    else:  # SELL
                        cycle.lowest_sell_price = min(cycle.lowest_sell_price, current_price)
                        # Update trailing SL
                        pip_value = self._get_pip_value()
                        cycle_zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
                        lower = cycle.zone_data.get('lower_boundary', 0.0)
                        new_trailing_sl = cycle.lowest_sell_price + (cycle_zone_threshold_pips * pip_value)
                        new_trailing_sl = min(new_trailing_sl, lower)
                        cycle.trailing_stop_loss = new_trailing_sl
                        logger.info(f"📊 Updated SELL trailing SL to {new_trailing_sl:.5f} after pending order trigger")
                        
                elif order_status == 'cancelled':
                    # Order was cancelled (shouldn't happen normally)
                    logger.warning(f"⚠️ Pending order {order_id} was cancelled in MT5")
                    cycle.pending_orders.remove(pending_order)
                    cycle.pending_order_levels.discard(grid_level)
                    
                    # Update status in main orders list
                    for order in cycle.orders:
                        if order.get('order_id') == order_id:
                            order['status'] = 'cancelled'
                            order['cancelled_at'] = datetime.datetime.now().isoformat()
                            break
                    
                    # Sync to PocketBase
                    self._sync_pending_orders_to_pocketbase(cycle)
                    
                elif order_status == 'pending':
                    # Order is still pending - check if price has reached target for early detection
                    order_triggered_by_price = False
                    
                    if direction == 'BUY' and target_price and current_price >= target_price:
                        order_triggered_by_price = True
                        logger.info(f"🎯 BUY pending order {order_id} (level {grid_level}) price reached {current_price:.5f} >= {target_price:.5f}")
                    elif direction == 'SELL' and target_price and current_price <= target_price:
                        order_triggered_by_price = True
                        logger.info(f"🎯 SELL pending order {order_id} (level {grid_level}) price reached {current_price:.5f} <= {target_price:.5f}")
                    
                    # Note: We don't process here as MT5 might still be processing the fill
                    # The next monitoring cycle will catch it when MT5 reports 'filled'
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error monitoring pending orders: {str(e)}")
            return False

    def _check_pending_order_status_in_mt5(self, order_id: int) -> str:
        """Check the actual status of a pending order in MT5"""
        try:
            # First check if it's still a pending order
            is_pending = self.meta_trader.check_order_is_pending(order_id)
            
            if is_pending:
                # Order is still pending
                return 'pending'
            else:
                # Order is no longer pending - check if it became a position
                position_info = self.meta_trader.get_position_by_ticket(order_id)
                
                if position_info:
                    # Order has been filled and became a position
                    return 'filled'
                else:
                    # Order not found in pending orders or positions - likely cancelled
                    return 'cancelled'
                
        except Exception as e:
            logger.error(f"❌ Error checking order status for {order_id}: {str(e)}")
            return 'error'

    def _sync_pending_orders_to_pocketbase(self, cycle):
        """Sync pending orders to PocketBase database"""
        try:
            if not hasattr(cycle, 'cycle_id') or not cycle.cycle_id:
                logger.warning("Cannot sync pending orders - cycle has no cycle_id")
                return False
            
            # Update cycle in database with current pending orders
            success = self._update_cycle_in_database(cycle, force_update=True)
            if success:
                logger.debug(f"✅ Synced {len(cycle.pending_orders)} pending orders to PocketBase for cycle {cycle.cycle_id}")
            else:
                logger.warning(f"⚠️ Failed to sync pending orders to PocketBase for cycle {cycle.cycle_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error syncing pending orders to PocketBase: {str(e)}")
            return False

    def _sync_pending_orders_from_pocketbase(self, cycle):
        """Sync pending orders from PocketBase database to local cycle"""
        try:
            if not hasattr(cycle, 'cycle_id') or not cycle.cycle_id:
                return False
            
            # Get latest cycle data from PocketBase
            try:
                pb_cycle = self.client.collection('cycles').get(cycle.cycle_id)
                if pb_cycle:
                    # Extract pending orders from PocketBase
                    pending_orders_data = getattr(pb_cycle, 'pending_orders', '[]')
                    if isinstance(pending_orders_data, str):
                        try:
                            pending_orders = json.loads(pending_orders_data)
                        except (json.JSONDecodeError, ValueError):
                            pending_orders = []
                    else:
                        pending_orders = pending_orders_data or []
                    
                    # Extract pending order levels
                    pending_levels_data = getattr(pb_cycle, 'pending_order_levels', '[]')
                    if isinstance(pending_levels_data, str):
                        try:
                            pending_levels = set(json.loads(pending_levels_data))
                        except (json.JSONDecodeError, ValueError):
                            pending_levels = set()
                    else:
                        pending_levels = set(pending_levels_data or [])
                    
                    # Update local cycle with PocketBase data
                    cycle.pending_orders = pending_orders
                    cycle.pending_order_levels = pending_levels
                    
                    logger.debug(f"✅ Synced {len(pending_orders)} pending orders from PocketBase for cycle {cycle.cycle_id}")
                    return True
                    
            except Exception as pb_error:
                logger.warning(f"⚠️ Could not fetch cycle from PocketBase: {pb_error}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error syncing pending orders from PocketBase: {str(e)}")
            return False

    def _monitor_active_orders_status(self, cycle) -> bool:
        """Monitor active orders and update status to 'closed' when they're closed in MT5"""
        try:
            if not hasattr(cycle, 'orders') or not cycle.orders:
                return True
            
            # Get all active orders (status = 'active')
            active_orders = [order for order in cycle.orders if order.get('status') == 'active']
            
            if not active_orders:
                return True
            
            closed_orders_count = 0
            
            # Check each active order to see if it still exists in MT5
            for order in active_orders:
                order_id = order.get('order_id') or order.get('ticket')
                if not order_id:
                    continue
                
                try:
                    # Check if the order still exists as a position in MT5
                    position = self.meta_trader.get_position_by_ticket(int(order_id))
                    
                    if not position or len(position) == 0:
                        # Order no longer exists in MT5 - it was closed
                        order['status'] = 'closed'
                        order['closed_at'] = datetime.datetime.now().isoformat()
                        order['closed_reason'] = 'mt5_position_closed'
                        closed_orders_count += 1
                        
                        # Log the closure
                        direction = order.get('direction', 'UNKNOWN')
                        grid_level = order.get('grid_level', 'N/A')
                        logger.info(f"🔍 Order {order_id} ({direction}, level {grid_level}) was closed in MT5 - status updated to 'closed'")
                        
                        # Update profit data if available
                        try:
                            # Try to get final profit data before marking as closed
                            order_profit = self.meta_trader.get_order_profit(order_id)
                            if order_profit:
                                order['profit'] = order_profit.get('profit', 0.0)
                                order['profit_pips'] = order_profit.get('profit_pips', 0.0)
                                logger.info(f"📊 Final profit for closed order {order_id}: ${order['profit']:.2f} ({order['profit_pips']:.1f} pips)")
                        except Exception as profit_error:
                            logger.debug(f"Could not get final profit for order {order_id}: {profit_error}")
                    
                except Exception as e:
                    logger.error(f"❌ Error checking order {order_id} status in MT5: {str(e)}")
                    continue
            
            # If any orders were closed, sync to PocketBase and log status
            if closed_orders_count > 0:
                logger.info(f"📊 Cycle {cycle.cycle_id}: {closed_orders_count} orders were closed in MT5 and status updated")
                
                # Log comprehensive order lifecycle status
                self._log_order_lifecycle_status(cycle)
                
                # Sync the updated order statuses to PocketBase
                try:
                    self._update_cycle_in_database(cycle, force_update=True)
                    logger.debug(f"✅ Synced closed order statuses to PocketBase for cycle {cycle.cycle_id}")
                except Exception as sync_error:
                    logger.warning(f"⚠️ Failed to sync closed order statuses to PocketBase: {sync_error}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error monitoring active orders status for cycle {cycle.cycle_id}: {str(e)}")
            return False

    def _get_order_status_summary(self, cycle) -> dict:
        """Get comprehensive order status summary for a cycle"""
        try:
            if not hasattr(cycle, 'orders') or not cycle.orders:
                return {
                    'total_orders': 0,
                    'pending_orders': 0,
                    'active_orders': 0,
                    'closed_orders': 0,
                    'cancelled_orders': 0
                }
            
            summary = {
                'total_orders': len(cycle.orders),
                'pending_orders': 0,
                'active_orders': 0,
                'closed_orders': 0,
                'cancelled_orders': 0
            }
            
            for order in cycle.orders:
                status = order.get('status', 'unknown')
                if status == 'pending':
                    summary['pending_orders'] += 1
                elif status == 'active':
                    summary['active_orders'] += 1
                elif status == 'closed':
                    summary['closed_orders'] += 1
                elif status == 'cancelled':
                    summary['cancelled_orders'] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error getting order status summary for cycle {cycle.cycle_id}: {str(e)}")
            return {
                'total_orders': 0,
                'pending_orders': 0,
                'active_orders': 0,
                'closed_orders': 0,
                'cancelled_orders': 0
            }

    def _log_order_lifecycle_status(self, cycle):
        """Log comprehensive order lifecycle status for monitoring"""
        try:
            if not hasattr(cycle, 'cycle_id'):
                return
            
            # Get order status summary
            summary = self._get_order_status_summary(cycle)
            
            # Get pending orders count
            pending_count = len(getattr(cycle, 'pending_orders', []))
            
            # Log comprehensive status
            logger.info(f"📊 Cycle {cycle.cycle_id} Order Status Summary:")
            logger.info(f"   📋 Total Orders: {summary['total_orders']}")
            logger.info(f"   ⏳ Pending Orders: {summary['pending_orders']} (tracked: {pending_count})")
            logger.info(f"   🟢 Active Orders: {summary['active_orders']}")
            logger.info(f"   🔴 Closed Orders: {summary['closed_orders']}")
            logger.info(f"   ❌ Cancelled Orders: {summary['cancelled_orders']}")
            
            # Log any discrepancies
            if summary['pending_orders'] != pending_count:
                logger.warning(f"⚠️ Pending order count mismatch: orders list={summary['pending_orders']}, pending_orders list={pending_count}")
            
        except Exception as e:
            logger.error(f"❌ Error logging order lifecycle status for cycle {cycle.cycle_id}: {str(e)}")

    def _restore_pending_orders_for_all_cycles(self):
        """Restore pending orders for all existing cycles from PocketBase"""
        try:
            logger.info("🔄 MoveGuard: Restoring pending orders for all existing cycles...")
            
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            restored_count = 0
            
            for cycle in active_cycles:
                try:
                    # Initialize pending orders tracking if not exists
                    if not hasattr(cycle, 'pending_orders'):
                        cycle.pending_orders = []
                        cycle.pending_order_levels = set()
                    
                    # Sync pending orders from PocketBase
                    if self._sync_pending_orders_from_pocketbase(cycle):
                        restored_count += 1
                        logger.info(f"✅ Restored {len(cycle.pending_orders)} pending orders for cycle {cycle.cycle_id}")
                        
                        # If we have pending orders, verify they still exist in MT5
                        if cycle.pending_orders:
                            self._verify_pending_orders_in_mt5(cycle)
                    else:
                        logger.warning(f"⚠️ Could not restore pending orders for cycle {cycle.cycle_id}")
                        
                except Exception as e:
                    logger.error(f"❌ Error restoring pending orders for cycle {cycle.cycle_id}: {str(e)}")
                    continue
            
            logger.info(f"✅ MoveGuard: Restored pending orders for {restored_count}/{len(active_cycles)} cycles")
            
        except Exception as e:
            logger.error(f"❌ Error restoring pending orders for all cycles: {str(e)}")
            logger.error(traceback.format_exc())

    def _verify_pending_orders_in_mt5(self, cycle):
        """Verify that pending orders still exist in MT5 and clean up invalid ones"""
        try:
            if not cycle.pending_orders:
                return
            
            valid_pending_orders = []
            valid_pending_levels = set()
            
            for pending_order in cycle.pending_orders[:]:  # Copy to avoid modification during iteration
                order_id = pending_order.get('order_id')
                grid_level = pending_order.get('grid_level')
                
                if order_id:
                    # Check if order still exists in MT5
                    try:
                        order_info = self.meta_trader.get_order_by_ticket(order_id)
                        if order_info and len(order_info) > 0:
                            # Order still exists in MT5
                            valid_pending_orders.append(pending_order)
                            valid_pending_levels.add(grid_level)
                            logger.debug(f"✅ Verified pending order {order_id} (level {grid_level}) still exists in MT5")
                        else:
                            # Order no longer exists in MT5 - remove from tracking
                            logger.warning(f"⚠️ Pending order {order_id} (level {grid_level}) no longer exists in MT5 - removing from tracking")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not verify pending order {order_id}: {e} - removing from tracking")
                else:
                    logger.warning(f"⚠️ Pending order has no order_id - removing from tracking")
            
            # Update cycle with only valid pending orders
            cycle.pending_orders = valid_pending_orders
            cycle.pending_order_levels = valid_pending_levels
            
            if len(valid_pending_orders) != len(cycle.pending_orders):
                logger.info(f"🔄 Cleaned up invalid pending orders for cycle {cycle.cycle_id}: {len(valid_pending_orders)}/{len(cycle.pending_orders)} valid")
                # Sync cleaned pending orders to PocketBase
                self._sync_pending_orders_to_pocketbase(cycle)
            
        except Exception as e:
            logger.error(f"❌ Error verifying pending orders in MT5 for cycle {cycle.cycle_id}: {str(e)}")

    def _check_and_cleanup_closed_orders(self, cycle):
        """Check for closed orders and clean up pending orders when orders hit SL"""
        try:
            if not hasattr(cycle, 'orders') or not cycle.orders:
                return
            
            # Check if any orders were closed (hit SL)
            orders_closed = False
            for order in cycle.active_orders:
                if order.status == 'closed':
                    orders_closed = True
                    logger.info(f"🔍 Order {order.order_id} was closed (likely hit SL) - updated status to 'closed'")
            
            # If any orders were closed, check if we need to clean up pending orders
            if orders_closed:
                logger.info(f"🔄 Orders were closed in cycle {cycle.cycle_id} - checking if pending orders should be cleaned up")
                
                # Check if all orders are now closed
                active_orders = [o for o in cycle.orders if o.get('status') == 'active']
                if not active_orders:
                    logger.info(f"🔄 All orders closed in cycle {cycle.cycle_id} - cleaning up pending orders but keeping cycle open")
                    
                    # Cancel all pending orders first
                    self._cancel_cycle_pending_orders(cycle)
                    
                    # Keep cycle open - don't close it just because all orders are closed
                    logger.info(f"📊 Cycle {cycle.cycle_id} remains open - no active orders but cycle stays active for potential future orders")
                    
                    # Optional: You can add logic here to potentially place new orders later
                    # For now, we just keep the cycle open without automatically closing it
                else:
                    # Some orders still active - check if we should clean up some pending orders
                    logger.info(f"📊 Some orders still active in cycle {cycle.cycle_id} - keeping pending orders")
            else:
                # Some orders still active - check if we should clean up some pending orders
                logger.info(f"📊 Some orders still active in cycle {cycle.cycle_id} - keeping pending orders")
    
        except Exception as e:
            logger.error(f"❌ Error checking and cleaning up closed orders for cycle {cycle.cycle_id}: {str(e)}")

    def _determine_new_direction_after_all_orders_closed(self, cycle, current_price: float) -> str:
        """Determine new direction when all orders are closed based on movement mode and price position"""
        try:
            # Get current zone boundaries
            upper = cycle.zone_data.get('upper_boundary', 0.0)
            lower = cycle.zone_data.get('lower_boundary', 0.0)
            movement_mode = cycle.zone_data.get('movement_mode', 'Move Both Sides')
            
            # Calculate entry interval offset
            pip_value = self._get_pip_value()
            entry_interval_pips = self.get_cycle_entry_interval_pips(cycle)
            initial_offset = entry_interval_pips * pip_value
            
            logger.info(f"🎯 Direction determination: price={current_price:.5f}, upper={upper:.5f}, lower={lower:.5f}, mode={movement_mode}")
            
            # Determine direction based on movement mode and price position
            if movement_mode == 'No Move':
                # No movement - use original boundaries
                if current_price >= (upper ):
                    logger.info(f"🎯 No Move mode: Price above upper boundary, direction=BUY")
                    return 'BUY'
                elif current_price <= (lower):
                    logger.info(f"🎯 No Move mode: Price below lower boundary, direction=SELL")
                    return 'SELL'
            elif movement_mode == 'Move Up Only':
                # Only move up - prefer BUY direction
                if current_price >= (upper ):
                    logger.info(f"🎯 Move Up Only mode: Price above upper boundary, direction=BUY")
                    return 'BUY'
                # Only allow SELL if price is significantly below lower boundary
                elif current_price <= (lower ):
                    logger.info(f"🎯 Move Up Only mode: Price significantly below lower boundary, direction=SELL")
                    return 'SELL'
            elif movement_mode == 'Move Down Only':
                # Only move down - prefer SELL direction
                if current_price <= (lower ):
                    logger.info(f"🎯 Move Down Only mode: Price below lower boundary, direction=SELL")
                    return 'SELL'
                # Only allow BUY if price is significantly above upper boundary
                elif current_price >= (upper ):
                    logger.info(f"🎯 Move Down Only mode: Price significantly above upper boundary, direction=BUY")
                    return 'BUY'
            else:  # Move Both Sides
                # Standard logic for both directions
                if current_price >= (upper ):
                    logger.info(f"🎯 Move Both Sides mode: Price above upper boundary, direction=BUY")
                    return 'BUY'
                elif current_price <= (lower ):
                    logger.info(f"🎯 Move Both Sides mode: Price below lower boundary, direction=SELL")
                    return 'SELL'
            
            logger.info(f"🎯 No direction change needed: price within boundaries")
            return None  # No direction change needed
            
        except Exception as e:
            logger.error(f"❌ Error determining new direction: {str(e)}")
            return None

    def _update_bounds_after_all_orders_closed(self, cycle, base_price: float, new_direction: str, current_price: float):
        """Update zone boundaries when all orders are closed based on movement mode"""
        try:
            movement_mode = cycle.zone_data.get('movement_mode', 'Move Both Sides')
            pip_value = self._get_pip_value()
            zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
            
            logger.info(f"🔄 Updating bounds after all orders closed: mode={movement_mode}, direction={new_direction}")
            
            # Handle None base_price (when trailing_stop_loss is None)
            if base_price is None:
                base_price = current_price
                logger.warning(f"⚠️ base_price is None, using current_price={current_price:.5f} as fallback")
            
            # Initialize variables with current values as defaults
            new_base = cycle.zone_data.get('base_price', base_price)
            new_upper = cycle.zone_data.get('upper_boundary', base_price + (zone_threshold_pips * pip_value ))
            new_lower = cycle.zone_data.get('lower_boundary', base_price - (zone_threshold_pips * pip_value ))
            
            if movement_mode == 'No Move':
                # Keep original boundaries
                logger.info(f"🎯 No Move mode: Keeping original boundaries")
                return
            elif movement_mode == 'Move Up Only' and new_direction == 'BUY' and base_price > current_price:
                # Move zone up to base price
                new_base = base_price
                new_upper = new_base + (zone_threshold_pips * pip_value  )
                new_lower = new_base
                logger.info(f"🎯 Move Up Only: Moving zone up to {base_price:.5f}")
            elif movement_mode == 'Move Down Only' and new_direction == 'SELL' and base_price < current_price:
                # Move zone down to base price
                new_base = base_price
                new_upper = new_base 
                new_lower = new_base - (zone_threshold_pips * pip_value )
                logger.info(f"🎯 Move Down Only: Moving zone down to {base_price:.5f}")
            elif movement_mode == 'Move Both Sides' and new_direction == 'BUY' and base_price > current_price:
                # Move zone to base price for BUY
                new_base = base_price
                new_upper = new_base + (zone_threshold_pips * pip_value )
                new_lower = new_base 
                logger.info(f"🎯 Move Both Sides: Moving zone to {base_price:.5f} for BUY")
            elif movement_mode == 'Move Both Sides' and new_direction == 'SELL' and base_price < current_price:
                # Move zone to base price for SELL
                new_base = base_price
                new_upper = new_base 
                new_lower = new_base - (zone_threshold_pips * pip_value )
                logger.info(f"🎯 Move Both Sides: Moving zone to {base_price:.5f} for SELL")
            else:
                # No bounds update needed - use current values
                logger.info(f"🎯 No bounds update needed for mode={movement_mode}, direction={new_direction}")
                return
            if new_upper <= new_lower:
                logger.error(f"❌ Invalid boundaries: upper={new_upper}, lower={new_lower}")
                return
            # Update zone data
            old_base = cycle.zone_data.get('base_price', 0.0)
            cycle.zone_data.update({
                'base_price': new_base,
                'upper_boundary': new_upper,
                'lower_boundary': new_lower,
                'last_movement': {
                    'direction': f'BOUNDS_UPDATE_{new_direction}',
                    'old_base': old_base,
                    'new_base': new_base,
                    'timestamp': datetime.datetime.now().isoformat()
                }
            })
            
            cycle.trailing_stop_loss = 0
            
            # Validate distance between boundaries
            distance = new_upper - new_lower
            expected_distance = zone_threshold_pips * pip_value
            logger.info(f"✅ Bounds updated: base={new_base:.5f}, upper={new_upper:.5f}, lower={new_lower:.5f}")
            logger.info(f"📏 Zone distance: {distance:.5f} (expected: {expected_distance:.5f}, zone_threshold: {zone_threshold_pips} pips)")
            
        except Exception as e:
            logger.error(f"❌ Error updating bounds after all orders closed: {str(e)}")

    def _check_zone_movement(self, cycle, current_price: float) -> dict:
        """Check zone movement for MoveGuard based on zone movement mode"""
        try:
            # Get zone data from cycle
            if not hasattr(cycle, 'zone_data') or not cycle.zone_data:
                cycle.zone_data = {
                    'base_price': cycle.entry_price,
                    'upper_boundary': cycle.entry_price + (self.get_cycle_zone_threshold_pips(cycle) * self._get_pip_value()),
                    'lower_boundary': cycle.entry_price - (self.get_cycle_zone_threshold_pips(cycle) * self._get_pip_value() ),
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
                new_upper_boundary = new_base_price + (zone_threshold_pips * pip_value / 2)
                new_lower_boundary = new_base_price - (zone_threshold_pips * pip_value / 2)
            else:  # DOWN
                # Move zone down - new base price is current price
                new_base_price = current_price
                new_upper_boundary = new_base_price + (zone_threshold_pips * pip_value / 2)
                new_lower_boundary = new_base_price - (zone_threshold_pips * pip_value / 2)
            
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
            
            # Validate distance between boundaries
            distance = new_upper_boundary - new_lower_boundary
            expected_distance = zone_threshold_pips * pip_value
            logger.info(f"✅ MoveGuard zone moved {direction}: base_price={new_base_price:.5f}, upper={new_upper_boundary:.5f}, lower={new_lower_boundary:.5f}")
            logger.info(f"📏 Zone distance: {distance:.5f} (expected: {expected_distance:.5f}, zone_threshold: {zone_threshold_pips} pips)")
            
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
            
            # Cancel all pending orders before closing cycle
            self._cancel_cycle_pending_orders(cycle)
            
            # Close all active orders in the cycle and update local lists
            active_orders_closed = 0
            for order in list(cycle.orders):
                if order.get('status') == 'active':
                    order_id = order.get('order_id') or order.get('ticket')
                    is_activated_pending = order.get('activated_at') is not None
                    
                    if self._close_order(order):
                        active_orders_closed += 1
                        
                        # Log if this was an activated pending order
                        if is_activated_pending:
                            logger.info(f"✅ Closed activated pending order {order_id} (was pending, now active)")
                        else:
                            logger.info(f"✅ Closed active order {order_id}")
                        
                        # Move from active_orders to completed_orders if those lists exist
                        oid = order.get('order_id') or order.get('ticket')
                        if hasattr(cycle, 'active_orders') and isinstance(cycle.active_orders, list):
                            cycle.active_orders = [o for o in cycle.active_orders if (o.get('order_id') or o.get('ticket')) != oid]
                        if hasattr(cycle, 'completed_orders') and isinstance(cycle.completed_orders, list):
                            cycle.completed_orders.append(order)
                    else:
                        logger.warning(f"⚠️ Failed to close active order {order_id}")
            
            logger.info(f"🔄 MoveGuard closed {active_orders_closed} active orders for cycle {cycle.cycle_id}")
            
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
                # Preserve profit before closing the position
                self._preserve_order_profit_before_closure(order)
                
                # Close active position
                pos = positions[0]
                result = self.meta_trader.close_position(pos)
                if result is not None:
                    # Use preserved profit data
                    preserved_profit = order.get('profit', 0.0)
                    preserved_profit_pips = order.get('profit_pips', 0.0)
                    
                    order['status'] = 'closed'
                    order['closed_at'] = datetime.datetime.now().isoformat()
                    # Keep preserved profit data
                    order['profit'] = preserved_profit
                    order['profit_pips'] = preserved_profit_pips
                    # Ensure both keys are kept in sync for downstream persistence
                    order['order_id'] = int(order_id)
                    order['ticket'] = int(order_id)
                    logger.info(f"✅ MoveGuard active position {order_id} closed with preserved profit: ${preserved_profit:.2f} ({preserved_profit_pips:.2f} pips)")
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

                # Cancel all pending orders before closing cycle
                self._cancel_cycle_pending_orders(cycle)
                
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
            
            # Cancel all pending orders first
            self._cancel_cycle_pending_orders(cycle)
            
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
                        # Order no longer exists - preserve profit before marking as closed
                        logger.info(f"🔄 Order {order_id} no longer exists in MT5 - preserving profit before closure")
                        
                        # Try to preserve profit before closure
                        profit_preserved = self._preserve_order_profit_before_closure(order)
                        
                        # Try to get the last known profit from the order itself
                        last_profit = order.get('profit', 0.0)
                        last_profit_pips = order.get('profit_pips', 0.0)
                        
                        # SPECIAL HANDLING: For initial orders, ensure we have profit data
                        is_initial_order = order.get('is_initial', False) or order.get('order_type') == 'grid_0'
                        if is_initial_order and last_profit == 0.0:
                            logger.warning(f"⚠️ Initial order {order_id} has no profit data - attempting emergency profit calculation")
                            
                        # If no profit data exists, try to calculate from MT5 one last time
                        if last_profit == 0.0:
                            order_profit = self._calculate_order_profit(order)
                            last_profit = order_profit['profit']
                            last_profit_pips = order_profit['profit_pips']
                            
                            # Log if we still have no profit data for initial orders
                            if is_initial_order and last_profit == 0.0:
                                logger.error(f"❌ CRITICAL: Initial order {order_id} still has no profit data after emergency calculation!")
                        
                        # Mark order as closed with preserved profit
                        order['status'] = 'closed'
                        order['closed_at'] = datetime.datetime.now().isoformat()
                        order['profit'] = last_profit
                        order['profit_pips'] = last_profit_pips
                        
                        # Store close price if available
                        if 'close_price' in order:
                            order['close_price'] = order.get('close_price', 0.0)
                        
                        orders_updated = True
                        logger.info(f"✅ Order {order_id} marked as closed with preserved profit: ${last_profit:.2f} ({last_profit_pips:.2f} pips)")
                
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

    def _preserve_order_profit_before_closure(self, order):
        """Preserve the current profit of an order before it gets closed"""
        try:
            order_id = order.get('order_id') or order.get('ticket')
            if not order_id:
                logger.warning(f"⚠️ No order ID/ticket found for profit preservation")
                return False
            
            # Get current profit from MetaTrader if order is still active
            positions = self.meta_trader.get_position_by_ticket(int(order_id))
            
            if positions and len(positions) > 0:
                position = positions[0]
                current_profit = getattr(position, 'profit', 0.0)
                current_swap = getattr(position, 'swap', 0.0)
                current_commission = getattr(position, 'commission', 0.0)
                
                # Preserve the profit data in the order
                order['profit'] = current_profit
                order['swap'] = current_swap
                order['commission'] = current_commission
                order['close_price'] = getattr(position, 'price_current', 0.0)
                
                logger.info(f"💰 Preserved profit for order {order_id}: ${current_profit:.2f} (swap: ${current_swap:.2f}, commission: ${current_commission:.2f})")
                return True
            else:
                # Order not found in positions, might already be closed
                logger.debug(f"⚠️ Order {order_id} not found in positions for profit preservation")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error preserving profit for order {order_id}: {str(e)}")
            return False

    def _calculate_order_profit(self, order):
        """Get profit for a specific order directly from MetaTrader or use preserved profit"""
        try:
            order_id = order.get('order_id') or order.get('ticket')
            if not order_id:
                logger.warning(f"⚠️ No order ID/ticket found for order in profit calculation")
                return {'profit': 0.0, 'profit_pips': 0.0}
            
            # Check if order already has preserved profit (for closed orders)
            if order.get('status') == 'closed' and 'profit' in order:
                preserved_profit = order.get('profit', 0.0)
                preserved_profit_pips = order.get('profit_pips', 0.0)
                logger.info(f"💰 Using preserved profit for closed order {order_id}: ${preserved_profit:.2f} ({preserved_profit_pips:.2f} pips)")
                return {
                    'profit': preserved_profit,
                    'profit_pips': preserved_profit_pips,
                    'close_price': order.get('close_price', 0.0)
                }
            
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
                # Position not found - try to get profit from order history or preserve last known value
                logger.debug(f"⚠️ Order {order_id} not found in MetaTrader positions - trying to preserve last profit")
                
                # Try to get profit from order history or use last known value
                last_profit = order.get('profit', 0.0)
                last_profit_pips = order.get('profit_pips', 0.0)
                
                if last_profit != 0.0:
                    logger.info(f"💰 Using last known profit for order {order_id}: ${last_profit:.2f} ({last_profit_pips:.2f} pips)")
                    return {
                        'profit': last_profit,
                        'profit_pips': last_profit_pips,
                        'close_price': order.get('close_price', 0.0)
                    }
                else:
                    logger.warning(f"⚠️ No profit data available for order {order_id} - returning 0.0")
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
            # Get pip value with validation
            pip_value = self._get_pip_value()
            if pip_value <= 0:
                logger.warning(f"⚠️ Invalid pip value in boundary calculation: {pip_value}, using fallback")
                pip_value = 0.0001
            
            # Get zone threshold with validation
            zone_threshold_pips = self.get_cycle_zone_threshold_pips(cycle)
            if zone_threshold_pips <= 0:
                logger.warning(f"⚠️ Invalid zone threshold in boundary calculation: {zone_threshold_pips}, using fallback")
                zone_threshold_pips = 50.0
            
            zone_threshold = zone_threshold_pips * pip_value
            
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

    def _sync_grid_0_sl_on_activation(self, cycle, direction: str):
        """
        Sync grid level 0 order's stop loss when grid level 1 order gets activated
        This tightens the initial order's risk once the second order actually gets executed
        """
        try:
            logger.info(f"🔄 Syncing grid 0 SL on grid 1 activation for {direction} cycle {cycle.cycle_id}")
            
            # Find grid level 1 order to get its stop loss
            grid_1_orders = [o for o in getattr(cycle, 'orders', []) 
                           if o.get('status') == 'active' and 
                           o.get('grid_level', 0) == 1]
            
            if not grid_1_orders:
                logger.warning(f"⚠️ No active grid level 1 order found in cycle {cycle.cycle_id}")
                return False
            
            # Get the stop loss from grid level 1 order
            grid_1_order = grid_1_orders[0]
            grid_1_sl = grid_1_order.get('sl') or grid_1_order.get('stop_loss', 0.0)
            
            if grid_1_sl <= 0:
                logger.warning(f"⚠️ Grid level 1 order has no valid stop loss: {grid_1_sl}")
                return False
            
            # Find grid level 0 order
            grid_0_orders = [o for o in getattr(cycle, 'orders', []) 
                           if o.get('status') == 'active' and
                           o.get('grid_level', 0) == 0]
            
            if not grid_0_orders:
                logger.warning(f"⚠️ No active grid level 0 order found in cycle {cycle.cycle_id}")
                return False
            
            # Take the first grid 0 order (should only be one)
            grid_0_order = grid_0_orders[0]
            order_id = grid_0_order.get('ticket') or grid_0_order.get('order_id')
            
            if not order_id:
                logger.error(f"❌ Grid 0 order has no ticket/order_id")
                return False
            
            logger.info(f"📊 Found grid 0 order {order_id}, updating SL from current to {grid_1_sl:.5f} (grid 1 activation)")
            
            # Update stop loss in MetaTrader
            try:
                result = self.meta_trader.modify_position_sl_tp(
                    ticket=int(order_id),
                    sl=grid_1_sl,
                    tp=0.0  # Keep existing TP or 0
                )
                
                if result:
                    # Update order data in cycle
                    grid_0_order['sl'] = grid_1_sl
                    grid_0_order['stop_loss'] = grid_1_sl
                    logger.info(f"✅ Successfully updated grid 0 order {order_id} SL to {grid_1_sl:.5f} (on grid 1 activation)")
                    return True
                else:
                    logger.warning(f"⚠️ Failed to update grid 0 order {order_id} SL - MetaTrader returned False")
                    return False
                    
            except Exception as mt5_error:
                logger.error(f"❌ MetaTrader error updating grid 0 order {order_id} SL: {str(mt5_error)}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error syncing grid 0 SL on activation: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def _sync_grid_0_sl_with_grid_1(self, cycle, grid_1_sl: float, direction: str):
        """
        DEPRECATED: Sync grid level 0 order's stop loss to match grid level 1's stop loss
        This function is no longer used - stop loss sync now happens on activation, not placement
        """
        try:
            logger.info(f"🔄 Syncing grid 0 SL with grid 1 SL: {grid_1_sl:.5f} for {direction} cycle {cycle.cycle_id}")
            
            # Find grid level 0 order
            grid_0_orders = [o for o in getattr(cycle, 'orders', []) 
                           if o.get('status') == 'active' and 
                           o.get('grid_level', 0) == 0]
            
            if not grid_0_orders:
                logger.warning(f"⚠️ No active grid level 0 order found in cycle {cycle.cycle_id}")
                return False
            
            # Take the first grid 0 order (should only be one)
            grid_0_order = grid_0_orders[0]
            order_id = grid_0_order.get('ticket') or grid_0_order.get('order_id')
            
            if not order_id:
                logger.error(f"❌ Grid 0 order has no ticket/order_id")
                return False
            
            logger.info(f"📊 Found grid 0 order {order_id}, updating SL from current to {grid_1_sl:.5f}")
            
            # Update stop loss in MetaTrader
            try:
                result = self.meta_trader.modify_position_sl_tp(
                    ticket=int(order_id),
                    sl=grid_1_sl,
                    tp=0.0  # Keep existing TP or 0
                )
                
                if result:
                    # Update order data in cycle
                    grid_0_order['sl'] = grid_1_sl
                    grid_0_order['stop_loss'] = grid_1_sl
                    logger.info(f"✅ Successfully updated grid 0 order {order_id} SL to {grid_1_sl:.5f}")
                    return True
                else:
                    logger.warning(f"⚠️ Failed to update grid 0 order {order_id} SL - MetaTrader returned False")
                    return False
                    
            except Exception as mt5_error:
                logger.error(f"❌ MetaTrader error updating grid 0 order {order_id} SL: {str(mt5_error)}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error syncing grid 0 SL with grid 1: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

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
            # If only one active order exists and it's the grid 0 order, do not allow trailing SL to close it
            active_orders = [o for o in getattr(cycle, 'orders', []) if o.get('status') == 'active']
            if len(active_orders) == 1:
                only_order = active_orders[0]
                order_type = only_order.get('order_type')
                grid_level = only_order.get('grid_level')
                if order_type == 'grid_0' or grid_level == 0:
                    return False

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
            
            # Enhanced diagnostic logging for cycle creation blocking
            closed_cycles_count = sum(1 for cycle in active_cycles if getattr(cycle, 'is_closed', False))
            truly_active_count = len(active_cycles) - closed_cycles_count
            
            if len(active_cycles) >= max_active_cycles:
                logger.warning(f"🚫 CYCLE CREATION BLOCKED: Max cycles ({max_active_cycles}) reached!")
                logger.warning(f"   📊 Total cycles in manager: {len(active_cycles)}")
                logger.warning(f"   📊 Truly active cycles: {truly_active_count}")
                logger.warning(f"   📊 Closed cycles still in manager: {closed_cycles_count}")
                logger.warning(f"   🔧 Recommendation: Clean up closed cycles to allow new cycle creation")
                
                # Try to clean up closed cycles if we have any
                if closed_cycles_count > 0:
                    logger.info(f"🧹 Attempting to clean up {closed_cycles_count} closed cycles...")
                    self.multi_cycle_manager.cleanup_closed_cycles()
                    # Recheck after cleanup
                    active_cycles_after_cleanup = self.multi_cycle_manager.get_all_active_cycles()
                    logger.info(f"✅ After cleanup: {len(active_cycles_after_cleanup)} cycles remaining")
                    
                    # If we now have room, continue with cycle creation
                    if len(active_cycles_after_cleanup) < max_active_cycles:
                        logger.info(f"✅ Cleanup successful! Proceeding with cycle creation...")
                        active_cycles = active_cycles_after_cleanup
                    else:
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
            
            # Enhanced diagnostic logging for cycle creation blocking
            closed_cycles_count = sum(1 for cycle in active_cycles if getattr(cycle, 'is_closed', False))
            truly_active_count = len(active_cycles) - closed_cycles_count
            
            if len(active_cycles) >= max_active_cycles:
                logger.warning(f"🚫 CYCLE CREATION BLOCKED in _create_interval_cycle_sync: Max cycles ({max_active_cycles}) reached!")
                logger.warning(f"   📊 Total cycles in manager: {len(active_cycles)}")
                logger.warning(f"   📊 Truly active cycles: {truly_active_count}")
                logger.warning(f"   📊 Closed cycles still in manager: {closed_cycles_count}")
                
                # Try to clean up closed cycles if we have any
                if closed_cycles_count > 0:
                    logger.info(f"🧹 Attempting to clean up {closed_cycles_count} closed cycles in _create_interval_cycle_sync...")
                    self.multi_cycle_manager.cleanup_closed_cycles()
                    # Recheck after cleanup
                    active_cycles_after_cleanup = self.multi_cycle_manager.get_all_active_cycles()
                    logger.info(f"✅ After cleanup: {len(active_cycles_after_cleanup)} cycles remaining")
                    
                    # If we now have room, continue with cycle creation
                    if len(active_cycles_after_cleanup) < max_active_cycles:
                        logger.info(f"✅ Cleanup successful! Proceeding with cycle creation in _create_interval_cycle_sync...")
                        active_cycles = active_cycles_after_cleanup
                    else:
                        logger.warning(f"Cannot create new cycle: max cycles ({max_active_cycles}) reached")
                        return False
                else:
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

    def diagnose_cycle_creation_status(self):
        """Diagnostic method to check why cycle creation might be blocked"""
        try:
            logger.info("🔍 === CYCLE CREATION DIAGNOSTIC REPORT ===")
            
            # Check active cycles
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            max_active_cycles = self.get_cycle_config_value(None, 'max_active_cycles', self.max_active_cycles)
            
            closed_cycles_count = sum(1 for cycle in active_cycles if getattr(cycle, 'is_closed', False))
            truly_active_count = len(active_cycles) - closed_cycles_count
            
            logger.info(f"📊 Active Cycles Status:")
            logger.info(f"   - Total cycles in manager: {len(active_cycles)}")
            logger.info(f"   - Max allowed cycles: {max_active_cycles}")
            logger.info(f"   - Truly active cycles: {truly_active_count}")
            logger.info(f"   - Closed cycles still in manager: {closed_cycles_count}")
            logger.info(f"   - Available slots: {max_active_cycles - len(active_cycles)}")
            
            # Check auto_place_cycles setting
            auto_place = getattr(self, 'auto_place_cycles', True)
            logger.info(f"⚙️ Configuration:")
            logger.info(f"   - Auto place cycles: {auto_place}")
            logger.info(f"   - Last cycle price: {getattr(self, 'last_cycle_price', 'Not set')}")
            
            # Check for any stuck cycles
            stuck_cycles = []
            for cycle in active_cycles:
                if getattr(cycle, 'is_closed', False):
                    stuck_cycles.append(cycle.cycle_id)
            
            if stuck_cycles:
                logger.warning(f"⚠️ Found {len(stuck_cycles)} closed cycles still in manager: {stuck_cycles}")
                logger.warning(f"   🔧 Recommendation: Run cleanup_closed_cycles() to remove them")
            else:
                logger.info(f"✅ No stuck closed cycles found")
            
            # Check cycle creation capability
            if len(active_cycles) >= max_active_cycles:
                logger.warning(f"🚫 CYCLE CREATION BLOCKED: Maximum cycles reached")
                if closed_cycles_count > 0:
                    logger.warning(f"   💡 Solution: Clean up {closed_cycles_count} closed cycles to free up slots")
                else:
                    logger.warning(f"   💡 Solution: Increase max_active_cycles or wait for cycles to close naturally")
            else:
                logger.info(f"✅ Cycle creation should be working normally")
            
            logger.info("🔍 === END DIAGNOSTIC REPORT ===")
            
        except Exception as e:
            logger.error(f"❌ Error in cycle creation diagnostic: {str(e)}")

    def force_cleanup_closed_cycles(self):
        """Force cleanup of all closed cycles to free up slots for new cycle creation"""
        try:
            logger.info("🧹 Force cleaning up closed cycles...")
            
            before_count = len(self.multi_cycle_manager.get_all_active_cycles())
            cleaned_count = self.multi_cycle_manager.cleanup_closed_cycles()
            after_count = len(self.multi_cycle_manager.get_all_active_cycles())
            
            logger.info(f"✅ Cleanup completed:")
            logger.info(f"   - Cycles before cleanup: {before_count}")
            logger.info(f"   - Cycles cleaned up: {cleaned_count}")
            logger.info(f"   - Cycles after cleanup: {after_count}")
            logger.info(f"   - Available slots: {self.get_cycle_config_value(None, 'max_active_cycles', self.max_active_cycles) - after_count}")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"❌ Error in force cleanup: {str(e)}")
            return 0

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
