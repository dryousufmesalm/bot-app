"""
Multi-Cycle Manager for Advanced Cycles Trader
Implements dictionary-based multi-cycle management with zone indexing
"""

import threading
import time
import datetime
from typing import Dict, List, Optional, Set
from Views.globals.app_logger import app_logger as logger


class MultiCycleManager:
    """
    Dictionary-based multi-cycle manager with zone indexing for optimal performance.
    Maintains multiple active cycles simultaneously without interference.
    """
    
    def __init__(self, meta_trader, bot, config, api_client):
        """
        Initialize multi-cycle manager
        
        Args:
            meta_trader: MetaTrader 5 connection
            bot: Bot instance
            config: Strategy configuration
            api_client: PocketBase API client
        """
        self.meta_trader = meta_trader
        self.bot = bot
        self.config = config
        self.api_client = api_client
        
        # Core cycle storage - Dictionary-based for O(1) lookups
        self.active_cycles: Dict[str, object] = {}  # cycle_id -> AdvancedCycle
        self.zone_cycles: Dict[str, List[str]] = {}  # zone_key -> [cycle_ids]
        self.direction_cycles: Dict[str, List[str]] = {}  # direction -> [cycle_ids]
        
        # Thread safety
        self.cycle_creation_lock = threading.Lock()
        self.cycle_modification_lock = threading.Lock()
        
        # Configuration settings
        self.max_active_cycles = int(config.get("max_concurrent_cycles", 3))
        self.cleanup_interval = int(config.get("cleanup_interval", 300))  # 5 minutes
        self.last_cleanup_time = time.time()
        
        # CRITICAL FIX: Initialize configuration values before using them
        self.order_interval_pips = float(config.get("order_interval_pips", 50.0))
        self.reversal_threshold_pips = float(config.get("reversal_threshold_pips", 300.0))
        
        # Cycle creation tracking
        self.cycle_creation_times: Dict[str, float] = {}
        self.last_cycle_creation_time = 0
        self.min_cycle_creation_interval = 60  # Minimum 60 seconds between cycles
        
        # Initialize enhanced zone detection engine
        from Strategy.components.enhanced_zone_detection import EnhancedZoneDetection
        self.enhanced_zone_engine = EnhancedZoneDetection(
            symbol=getattr(bot, 'symbol_name', 'EURUSD'),
            reversal_threshold_pips=self.reversal_threshold_pips,
            order_interval_pips=self.order_interval_pips
        )
        
        logger.info(f"MultiCycleManager initialized: max_cycles={self.max_active_cycles}, "
                   f"reversal_threshold={self.reversal_threshold_pips}pips, "
                   f"order_interval={self.order_interval_pips}pips")
    
    def add_cycle(self, cycle) -> bool:
        """
        Add cycle with zone/direction indexing
        
        Args:
            cycle: AdvancedCycle instance
            
        Returns:
            bool: True if cycle added successfully
        """
        try:
            with self.cycle_creation_lock:
                # Get cycle_id from the cycle
                if not hasattr(cycle, 'cycle_id') or not cycle.cycle_id:
                    logger.error("Cannot add cycle without cycle_id")
                    return False
                
                cycle_id = cycle.cycle_id
                
                # Check if cycle already exists
                if cycle_id in self.active_cycles:
                    logger.warning(f"Cycle {cycle_id} already exists in manager")
                    return False
                
                # Check maximum cycles limit
                if len(self.active_cycles) >= self.max_active_cycles:
                    logger.warning(f"Maximum cycles limit ({self.max_active_cycles}) reached")
                    self._cleanup_oldest_closed_cycle()
                
                # Add to main storage
                self.active_cycles[cycle_id] = cycle
                
                # CRITICAL FIX: Get cycle direction properly
                # First try current_direction, then direction, then default to UNKNOWN
                direction = getattr(cycle, 'current_direction', None)
                if not direction or direction not in ["BUY", "SELL"]:
                    direction = getattr(cycle, 'direction', None)
                if not direction or direction not in ["BUY", "SELL"]:
                    logger.warning(f"No valid direction found for cycle {cycle_id}, defaulting to BUY")
                    direction = "BUY"  # Default to BUY instead of UNKNOWN
                
                # Add to zone indexing
                zone_key = self._generate_zone_key(cycle)
                if zone_key not in self.zone_cycles:
                    self.zone_cycles[zone_key] = []
                self.zone_cycles[zone_key].append(cycle_id)
                
                # Add to direction indexing
                if direction not in self.direction_cycles:
                    self.direction_cycles[direction] = []
                self.direction_cycles[direction].append(cycle_id)
                
                # Track creation time
                self.cycle_creation_times[cycle_id] = time.time()
                
                # CRITICAL FIX: Create reversal monitor with validated direction
                if hasattr(self.enhanced_zone_engine, 'create_reversal_monitor'):
                    monitor_id = self.enhanced_zone_engine.create_reversal_monitor(cycle_id, direction)
                    if monitor_id:
                        logger.info(f"✅ Created reversal monitor for cycle {cycle_id} with direction {direction}")
                    else:
                        logger.warning(f"Failed to create reversal monitor for cycle {cycle_id}")
                
                logger.info(f"✅ Cycle {cycle_id} added to manager (Total: {len(self.active_cycles)})")
                return True
                
        except Exception as e:
            logger.error(f"Error adding cycle {getattr(cycle, 'cycle_id', 'unknown')}: {e}")
            return False
    
    def remove_cycle(self, cycle_id: str) -> bool:
        """
        Remove cycle from all indexes
        
        Args:
            cycle_id: ID of cycle to remove
            
        Returns:
            bool: True if cycle removed successfully
        """
        try:
            with self.cycle_modification_lock:
                # Check if cycle exists
                if cycle_id not in self.active_cycles:
                    logger.warning(f"Cycle {cycle_id} not found in manager")
                    return False
                
                cycle = self.active_cycles[cycle_id]
                
                # Remove from main storage
                del self.active_cycles[cycle_id]
                
                # Remove from zone indexing
                zone_key = self._generate_zone_key(cycle)
                if zone_key in self.zone_cycles:
                    if cycle_id in self.zone_cycles[zone_key]:
                        self.zone_cycles[zone_key].remove(cycle_id)
                    if not self.zone_cycles[zone_key]:  # Remove empty zone
                        del self.zone_cycles[zone_key]
                
                # Remove from direction indexing
                direction = getattr(cycle, 'direction', 'UNKNOWN')
                if direction in self.direction_cycles:
                    if cycle_id in self.direction_cycles[direction]:
                        self.direction_cycles[direction].remove(cycle_id)
                    if not self.direction_cycles[direction]:  # Remove empty direction
                        del self.direction_cycles[direction]
                
                # Remove creation time tracking
                if cycle_id in self.cycle_creation_times:
                    del self.cycle_creation_times[cycle_id]
                
                logger.info(f"✅ Cycle {cycle_id} removed from manager (Remaining: {len(self.active_cycles)})")
                return True
                
        except Exception as e:
            logger.error(f"Error removing cycle {cycle_id}: {e}")
            return False
    
    def get_cycle(self, cycle_id: str) -> Optional[object]:
        """
        Get cycle by ID
        
        Args:
            cycle_id: ID of cycle to retrieve
            
        Returns:
            AdvancedCycle instance or None
        """
        return self.active_cycles.get(cycle_id)
    
    def get_cycles_by_zone(self, zone_key: str) -> List[object]:
        """
        Fast zone-based cycle retrieval
        
        Args:
            zone_key: Zone identifier
            
        Returns:
            List of AdvancedCycle instances in the zone
        """
        cycle_ids = self.zone_cycles.get(zone_key, [])
        return [self.active_cycles[cycle_id] for cycle_id in cycle_ids 
                if cycle_id in self.active_cycles]
    
    def get_cycles_by_direction(self, direction: str) -> List[object]:
        """
        Get cycles by trading direction
        
        Args:
            direction: Trading direction (BUY/SELL)
            
        Returns:
            List of AdvancedCycle instances with the direction
        """
        cycle_ids = self.direction_cycles.get(direction, [])
        return [self.active_cycles[cycle_id] for cycle_id in cycle_ids 
                if cycle_id in self.active_cycles]
    
    def get_all_active_cycles(self) -> List[object]:
        """
        Get all active cycles
        
        Returns:
            List of all AdvancedCycle instances
        """
        return list(self.active_cycles.values())
    
    def get_open_cycles(self) -> List[object]:
        """
        Get only open (non-closed) cycles
        
        Returns:
            List of open AdvancedCycle instances
        """
        return [cycle for cycle in self.active_cycles.values() 
                if not getattr(cycle, 'is_closed', False)]
    
    def should_create_new_cycle(self, current_time: float = None) -> bool:
        """
        Determine if a new cycle should be created based on multi-cycle logic
        
        Args:
            current_time: Current timestamp (optional)
            
        Returns:
            bool: True if new cycle should be created
        """
        if current_time is None:
            current_time = time.time()
        
        try:
            # Check minimum interval between cycle creation
            if (current_time - self.last_cycle_creation_time) < self.min_cycle_creation_interval:
                logger.debug(f"Cycle creation too frequent, waiting {self.min_cycle_creation_interval}s interval")
                return False
            
            # Check maximum cycles limit
            if len(self.active_cycles) >= self.max_active_cycles:
                logger.debug(f"Maximum cycles limit ({self.max_active_cycles}) reached")
                return False
            
            # Always allow new cycle creation in multi-cycle mode
            # Each candle can create a new cycle as long as limits are respected
            return True
            
        except Exception as e:
            logger.error(f"Error checking if new cycle should be created: {e}")
            return False
    
    def create_new_cycle(self, direction: str, entry_price: float, 
                        zone_info: Dict = None, symbol: str = None) -> Optional[str]:
        """
        Create new cycle WITHOUT closing existing ones
        
        Args:
            direction: Trading direction (BUY/SELL)
            entry_price: Entry price for the cycle
            zone_info: Zone information dictionary
            symbol: Trading symbol
            
        Returns:
            str: Cycle ID if created successfully, None otherwise
        """
        try:
            current_time = time.time()
            
            # Check if new cycle should be created
            if not self.should_create_new_cycle(current_time):
                return None
            
            # Import here to avoid circular imports
            from cycles.ACT_cycle_Organized import AdvancedCycle
            
            # Use provided symbol or default
            if symbol is None:
                symbol = getattr(self, 'symbol', 'EURUSD')
            
            # Calculate basic parameters
            pip_value = self._get_pip_value(symbol)
            
            # Set stop loss and take profit to 0
            if direction == "BUY":
                stop_loss = 0  # No stop loss (0 pips)
                take_profit = 0  # No take profit (0 pips)
            else:  # SELL
                take_profit = 0  # No take profit (0 pips)
                stop_loss = 0  # No stop loss (0 pips)
            
            # Calculate bounds - use zone threshold for bounds instead of fixed 300 pips
            if direction == "BUY":
                lower_bound = entry_price - (self.reversal_threshold_pips / pip_value)
                upper_bound = entry_price + (self.reversal_threshold_pips / pip_value)
            else:  # SELL
                lower_bound = entry_price - (self.reversal_threshold_pips / pip_value)
                upper_bound = entry_price + (self.reversal_threshold_pips / pip_value)
            
            # Prepare cycle data
            cycle_data = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "status": "active",
                "bot_id": self.bot.id,
                "magic_number": self.bot.magic_number,
                "zone_base_price": zone_info.get('base_price') if zone_info else entry_price,
                "initial_threshold_price": entry_price,
                "current_direction": direction,
                "direction_switched": False,
                "done_price_levels": [],
                "next_order_index": 1,
                # Required CT_cycles fields
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "is_pending": False,
                "is_closed": False,
                "lot_idx": 0,
                "total_volume": 0.0,
                "total_profit": 0.0,
                "zone_index": len(self.active_cycles),  # Use cycle count as zone index
                "bot": str(self.bot.id),
                "account": str(getattr(self.bot, 'account', 'Default')),
                "threshold_lower": stop_loss,
                "threshold_upper": take_profit,
                "base_threshold_lower": stop_loss,
                "base_threshold_upper": take_profit,
                # Multi-cycle specific fields
                "strategy_type": "ACT",
                "reversal_threshold_pips": self.reversal_threshold_pips,
                "reversal_trigger_price": None,  # Will be calculated later
                "parent_cycle_id": None,
                "cycle_generation": len(self.active_cycles) + 1,
                "multi_cycle_batch": f"ACT_{int(current_time)}",
                "reversal_threshold_pips": self.reversal_threshold_pips,
            }
            
            # Ensure bot has API client access
            if not hasattr(self.bot, 'api_client'):
                self.bot.api_client = self.api_client
            
            # Create AdvancedCycle object
            cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
            
            # Create cycle in database first to get the cycle_id
            if not cycle._create_cycle_in_database():
                logger.error("Failed to create cycle in database")
                return None
            
            # Add to manager
            if self.add_cycle(cycle):
                self.last_cycle_creation_time = current_time
                logger.info(f"✅ New cycle created: {cycle.cycle_id} ({direction} at {entry_price})")
                return cycle.cycle_id
            else:
                logger.error(f"Failed to add cycle {cycle.cycle_id} to manager")
                return None
                
        except Exception as e:
            logger.error(f"Error creating new cycle: {e}")
            return None
    
    def manage_all_cycles(self, current_price: float, candle_data: Dict, active_cycles=None) -> Dict:
        """
        Manage all active cycles simultaneously
        
        Args:
            current_price: Current market price
            candle_data: Current candle information
            active_cycles: Optional list of cycles from AdvancedCyclesTrader
            
        Returns:
            Dict: Management results and statistics
        """
        try:
            results = {
                "cycles_processed": 0,
                "orders_placed": 0,
                "cycles_closed": 0,
                "errors": []
            }
            
            # CRITICAL FIX: If active_cycles is provided, sync them to our dictionary
            if active_cycles:
                # Make sure all cycles from the list are in our dictionary
                for cycle in active_cycles:
                    if hasattr(cycle, 'cycle_id') and cycle.cycle_id not in self.active_cycles:
                        self.add_cycle(cycle)
            
            # Process each active cycle in our dictionary
            for cycle_id, cycle in list(self.active_cycles.items()):
                try:
                    # Skip closed cycles
                    if getattr(cycle, 'is_closed', False):
                        continue
                    
                    # Place orders for this cycle if needed
                    order_placed = self._place_cycle_orders(cycle, current_price)
                    if order_placed:
                        results["orders_placed"] += 1
                    
                    # Check for zone breaches and reversals
                    self._check_cycle_zone_logic(cycle, current_price)
                    
                    results["cycles_processed"] += 1
                    
                except Exception as e:
                    error_msg = f"Error processing cycle {cycle_id}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Periodic cleanup
            if time.time() - self.last_cleanup_time > self.cleanup_interval:
                self.cleanup_closed_cycles()
                self.last_cleanup_time = time.time()
            
            return results
            
        except Exception as e:
            logger.error(f"Error managing all cycles: {e}")
            return {"error": str(e)}
    
    def _place_cycle_orders(self, cycle, current_price):
        """Place orders for a specific cycle based on its strategy"""
        try:
            # Skip if cycle is closed
            if getattr(cycle, 'is_closed', False):
                return False
                
            # Check if cycle is ready for order placement
            current_time = datetime.datetime.utcnow()
            
            # CRITICAL FIX: Verify this cycle is valid for order placement
            # Check that the cycle has necessary attributes and methods
            if not hasattr(cycle, 'should_place_next_order') or not callable(getattr(cycle, 'should_place_next_order', None)):
                logger.warning(f"Cycle {getattr(cycle, 'cycle_id', 'unknown')} missing required methods for order placement")
                return False
                
            # Check if we should place the next order for this cycle
            if not cycle.should_place_next_order(current_price, current_time):
                return False
                
            # Get order direction based on cycle's current direction
            direction = getattr(cycle, 'current_direction', 'BUY')
            
            # Get lot size from cycle or use default
            lot_size = getattr(cycle, 'lot_size', 0.01)
            
            # Get next order price
            next_price = cycle.get_next_order_price(current_price)
            
            # Determine order type and position
            order_count = len(getattr(cycle, 'active_orders', []))
            order_type = "ini" if order_count == 0 else "rec"  # initial or recovery
            order_position = order_count + 1  # 1-based position
            
            # Create short comment: type + position (e.g., "ini1", "rec2", "rec3")
            comment = f"{order_type}{order_position}"
            
            # Place order based on direction
            if direction == "BUY":
                # Place buy order
                result = self.meta_trader.place_buy_order(
                    symbol=cycle.symbol,
                    volume=lot_size,
                    price=next_price,
                    stop_loss=0.0,  # No SL/TP at order level, managed at cycle level
                    take_profit=0.0,
                    comment=comment
                )
            else:
                # Place sell order
                result = self.meta_trader.place_sell_order(
                    symbol=cycle.symbol,
                    volume=lot_size,
                    price=next_price,
                    stop_loss=0.0,  # No SL/TP at order level, managed at cycle level
                    take_profit=0.0,
                    comment=comment
                )
                
            # Process order result
            if result :
                # Add order to cycle
                order_data = {
                    'ticket': result['order']['ticket'],
                    'volume': result['order']['volume'],
                    'price_open': result['order']['price_open'],
                    'type': 0 if direction == "BUY" else 1,  # 0=BUY, 1=SELL
                    'comment': comment  # Use the same short comment format
                }
                
                # Add order to cycle
                cycle.add_order(order_data)
                
                # Update cycle in database
                if hasattr(cycle, '_update_cycle_in_database') and callable(cycle._update_cycle_in_database):
                    cycle._update_cycle_in_database()
                
                logger.info(f"✅ Placed {direction} order for cycle {cycle.cycle_id}: Ticket {result['order']['ticket']}, Price {next_price}")
                return True
            else:
                logger.error(f"❌ Failed to place {direction} order for cycle {cycle.cycle_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error placing order for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {e}")
            return False
    
    def _check_cycle_zone_logic(self, cycle, current_price: float):
        """
        Check zone logic for individual cycle
        
        Args:
            cycle: AdvancedCycle instance
            current_price: Current market price
        """
        try:
            # Get cycle ID and direction
            cycle_id = getattr(cycle, 'cycle_id', None)
            if not cycle_id:
                logger.warning("Cannot check zone logic for cycle without cycle_id")
                return
            
            # CRITICAL FIX: Get cycle direction properly
            direction = getattr(cycle, 'current_direction', None)
            if not direction or direction not in ["BUY", "SELL"]:
                direction = getattr(cycle, 'direction', None)
            if not direction or direction not in ["BUY", "SELL"]:
                logger.warning(f"No valid direction found for cycle {cycle_id}, defaulting to BUY")
                direction = "BUY"  # Default to BUY instead of UNKNOWN
            
            # Update reversal monitor with current price
            reversal_status = self.enhanced_zone_engine.update_reversal_monitor(cycle_id, current_price)
            
            # Check if reversal was triggered
            if reversal_status.get('reversal_triggered', False):
                # Set flags on the cycle to indicate a zone breach
                if hasattr(cycle, 'zone_breach_detected'):
                    cycle.zone_breach_detected = True
                    cycle.zone_breach_price = current_price
                    cycle.zone_breach_time = time.time()
                    logger.info(f"Zone breach detected for cycle {cycle_id} at price {current_price} (Direction: {direction})")
            
        except Exception as e:
            logger.error(f"Error checking zone logic for cycle {getattr(cycle, 'cycle_id', 'unknown')}: {e}")
    
    def _should_create_reversal_cycle(self, cycle, current_price: float) -> bool:
        """
        Determine if a reversal cycle should be created
        
        Args:
            cycle: AdvancedCycle instance
            current_price: Current market price
            
        Returns:
            bool: True if reversal cycle should be created
        """
        # We're no longer creating reversal cycles, but keeping this method for compatibility
        return False
    
    def cleanup_closed_cycles(self) -> int:
        """
        Memory management for closed cycles
        
        Returns:
            int: Number of cycles cleaned up
        """
        try:
            cleaned_count = 0
            cycles_to_remove = []
            
            for cycle_id, cycle in self.active_cycles.items():
                if getattr(cycle, 'is_closed', False):
                    # Keep closed cycles for a grace period before cleanup
                    cycle_creation_time = self.cycle_creation_times.get(cycle_id, 0)
                    if time.time() - cycle_creation_time > 3600:  # 1 hour grace period
                        cycles_to_remove.append(cycle_id)
            
            # Remove old closed cycles
            for cycle_id in cycles_to_remove:
                if self.remove_cycle(cycle_id):
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned up {cleaned_count} old closed cycles")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during cycle cleanup: {e}")
            return 0
    
    def _cleanup_oldest_closed_cycle(self):
        """Remove the oldest closed cycle to make room for new ones"""
        try:
            closed_cycles = [(cycle_id, cycle) for cycle_id, cycle in self.active_cycles.items() 
                           if getattr(cycle, 'is_closed', False)]
            
            if closed_cycles:
                # Find oldest closed cycle
                oldest_cycle_id = min(closed_cycles, 
                                    key=lambda x: self.cycle_creation_times.get(x[0], 0))[0]
                self.remove_cycle(oldest_cycle_id)
                logger.info(f"🧹 Removed oldest closed cycle {oldest_cycle_id} to make room")
            
        except Exception as e:
            logger.error(f"Error cleaning up oldest cycle: {e}")
    
    def _generate_zone_key(self, cycle) -> str:
        """
        Generate zone key for indexing
        
        Args:
            cycle: AdvancedCycle instance
            
        Returns:
            str: Zone key for indexing
        """
        try:
            entry_price = getattr(cycle, 'entry_price', 0)
            direction = getattr(cycle, 'direction', 'UNKNOWN')
            # Round to nearest 50 pips for zone grouping
            zone_price = round(entry_price * 10000 / 50) * 50
            return f"{direction}_{zone_price}"
        except Exception as e:
            logger.error(f"Error generating zone key: {e}")
            return f"UNKNOWN_{int(time.time())}"
    
    def _get_pip_value(self, symbol: str = None) -> float:
        """Get pip value for the current symbol"""
        try:
            if symbol is None:
                symbol = getattr(self, 'symbol', 'EURUSD')
            
            # Try to get the symbol's point value from MetaTrader if available
            if hasattr(self, 'meta_trader') and hasattr(self.meta_trader, 'get_symbol_info'):
                symbol_info = self.meta_trader.get_symbol_info(symbol)
                if symbol_info and 'point' in symbol_info and symbol_info['point'] > 0:
                    pip_value = symbol_info['point']*10
                    return pip_value
            
            pip_value = 0.01
            return pip_value
        except Exception as e:
            logger.error(f"Error getting symbol point: {e}")
            return 0.01  # Default
    
    def get_manager_statistics(self) -> Dict:
        """
        Get comprehensive manager statistics
        
        Returns:
            Dict: Manager statistics and status
        """
        try:
            open_cycles = [cycle for cycle in self.active_cycles.values() 
                          if not getattr(cycle, 'is_closed', False)]
            
            stats = {
                "total_cycles": len(self.active_cycles),
                "open_cycles": len(open_cycles),
                "closed_cycles": len(self.active_cycles) - len(open_cycles),
                "zones_active": len(self.zone_cycles),
                "directions": {
                    direction: len(cycle_ids) 
                    for direction, cycle_ids in self.direction_cycles.items()
                },
                "max_cycles_limit": self.max_active_cycles,
                "oldest_cycle_age": 0,
                "newest_cycle_age": 0,
                "memory_usage": {
                    "active_cycles": len(self.active_cycles),
                    "zone_indexes": len(self.zone_cycles),
                    "direction_indexes": len(self.direction_cycles),
                    "creation_times": len(self.cycle_creation_times)
                }
            }
            
            # Calculate cycle ages
            if self.cycle_creation_times:
                current_time = time.time()
                creation_times = list(self.cycle_creation_times.values())
                stats["oldest_cycle_age"] = current_time - min(creation_times)
                stats["newest_cycle_age"] = current_time - max(creation_times)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting manager statistics: {e}")
            return {"error": str(e)}
    
    def close_cycle_enhanced(self, cycle_id: str, closing_method: str = "manual", username: str = "system"):
        """
        Enhanced cycle closing with comprehensive status updates
        
        Args:
            cycle_id: ID of cycle to close
            closing_method: Method used for closing
            username: User initiating the close
            
        Returns:
            bool: True if cycle closed successfully
        """
        try:
            # Find the cycle
            cycle = self.get_cycle(cycle_id)
            if not cycle:
                logger.error(f"Cycle {cycle_id} not found in manager")
                return False
            
            # Update cycle status to inactive
            cycle.is_active = False
            cycle.is_closed = True
            cycle.status = "inactive"
            
            # Set closing method details
            import datetime
            closing_timestamp = datetime.datetime.utcnow()
            
            cycle.closing_method = {
                "type": closing_method,
                "user": username,
                "timestamp": closing_timestamp.isoformat(),
                "details": f"Cycle closed via {closing_method}",
                "final_profit": getattr(cycle, 'total_profit', 0.0) or 0.0,
                "total_orders": len(getattr(cycle, 'completed_orders', [])),
                "duration_minutes": self._calculate_cycle_duration_local(cycle)
            }
            
            # Update orders status to inactive
            if hasattr(cycle, 'active_orders'):
                for order in cycle.active_orders:
                    order.update({
                        "status": "inactive",
                        "is_active": False,
                        "is_closed": True,
                        "close_time": closing_timestamp.isoformat(),
                        "close_reason": closing_method,
                        "closed_by": username
                    })
                
                # Move orders to completed
                if not hasattr(cycle, 'completed_orders'):
                    cycle.completed_orders = []
                cycle.completed_orders.extend(cycle.active_orders)
                cycle.active_orders.clear()
            
            # Remove from manager
            if self.remove_cycle(cycle_id):
                logger.info(f"✅ Cycle {cycle_id} enhanced closing completed: active → inactive")
                return True
            else:
                logger.error(f"❌ Failed to remove cycle {cycle_id} from manager")
                return False
                
        except Exception as e:
            logger.error(f"Error in enhanced cycle closing: {e}")
            return False
    
    def _calculate_cycle_duration_local(self, cycle):
        """Calculate cycle duration in minutes (local version for manager)"""
        try:
            if hasattr(cycle, 'start_time') and hasattr(cycle, 'close_time'):
                if cycle.start_time and cycle.close_time:
                    duration = cycle.close_time - cycle.start_time
                    return duration.total_seconds() / 60
            return 0
        except Exception as e:
            logger.error(f"Error calculating cycle duration: {e}")
            return 0 