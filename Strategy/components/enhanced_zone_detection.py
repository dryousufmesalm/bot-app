"""
Enhanced Zone Detection Engine for Advanced Cycles Trader
Implements multi-zone state machine with reversal monitoring
"""

import time
import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
from Views.globals.app_logger import app_logger as logger
import MetaTrader5 as Mt5


class ZoneState(Enum):
    """Zone state enumeration for state machine"""
    INACTIVE = "inactive"
    MONITORING = "monitoring"
    BREACHED = "breached"
    REVERSAL_PENDING = "reversal_pending"
    REVERSAL_CONFIRMED = "reversal_confirmed"


class ReversalMonitor:
    """Monitor reversal conditions for individual cycles"""
    
    def __init__(self, cycle_id: str, direction: str, threshold_pips: float):
        self.cycle_id = cycle_id
        self.direction = direction
        self.threshold_pips = threshold_pips
        self.highest_price = None
        self.lowest_price = None
        self.reversal_triggered = False
        self.creation_time = time.time()
        
    def update_price_extremes(self, price: float):
        """Update highest/lowest prices for reversal calculation"""
        if self.highest_price is None or price > self.highest_price:
            self.highest_price = price
        if self.lowest_price is None or price < self.lowest_price:
            self.lowest_price = price
    
    def check_reversal_condition(self, current_price: float, pip_value: float) -> bool:
        """Check if reversal condition is met"""
        if self.reversal_triggered:
            return False
        
        if self.direction == "BUY" and self.highest_price:
            # Check if price dropped 300 pips from highest
            reversal_distance = (self.highest_price - current_price) * pip_value
            if reversal_distance >= self.threshold_pips:
                self.reversal_triggered = True
                return True
        elif self.direction == "SELL" and self.lowest_price:
            # Check if price rose 300 pips from lowest
            reversal_distance = (current_price - self.lowest_price) * pip_value
            if reversal_distance >= self.threshold_pips:
                self.reversal_triggered = True
                return True
        
        return False


class EnhancedZoneDetection:
    """
    Multi-zone state machine with zone history for sophisticated zone detection.
    Provides best balance of accuracy and reliability for zone-based trading.
    """
    
    def __init__(self, symbol: str, reversal_threshold_pips: float = 300.0,
                 order_interval_pips: float = 50.0):
        """Initialize the EnhancedZoneDetection component.
        
        Args:
            symbol: Trading symbol
            reversal_threshold_pips: Reversal threshold in pips (default 300)
            order_interval_pips: Order interval in pips (default 50)
        """
        self.symbol = symbol
        self.reversal_threshold_pips = reversal_threshold_pips
        self.order_interval_pips = order_interval_pips
        
        # State machine components
        self.zone_states: Dict[str, ZoneState] = {}  # zone_id -> ZoneState
        self.zone_data: Dict[str, Dict] = {}  # zone_id -> zone_data
        self.price_history: List[Dict] = []  # Recent price data
        self.reversal_monitors: Dict[str, ReversalMonitor] = {}  # cycle_id -> ReversalMonitor
        
        # Zone management
        self.active_zones: Dict[str, Dict] = {}  # zone_id -> zone_info
        self.zone_creation_times: Dict[str, float] = {}
        self.max_price_history = 1000  # Keep last 1000 price points
        self.max_zones = 20  # Maximum number of active zones
        
        # Performance tracking
        self.zone_breach_count = 0
        self.reversal_count = 0
        self.false_signal_count = 0
        
        logger.info(f"EnhancedZoneDetection initialized for {symbol} with "
                    f"threshold={reversal_threshold_pips}pips, interval={order_interval_pips}pips")
    
    def detect_zone_breach(self, price: float, entry_price: float, 
                          threshold_pips: float = None) -> Dict:
        """
        State machine for zone breach detection
        
        Args:
            price: Current market price
            entry_price: Entry price for comparison
            threshold_pips: Custom threshold (optional)
            
        Returns:
            Dict: Zone breach detection results
        """
        try:
            if threshold_pips is None:
                threshold_pips = self.order_interval_pips
            
            # Add current price to history
            self._add_price_to_history(price)
            
            # Calculate price difference in pips
            pip_value = self._get_pip_value()
            price_diff_pips = abs(price - entry_price) / pip_value
            
            # Generate zone ID
            zone_id = self._generate_zone_id(entry_price, threshold_pips)
            
            # Initialize zone if not exists
            if zone_id not in self.zone_states:
                self._initialize_zone(zone_id, entry_price, threshold_pips)
            
            # Update zone state based on price movement
            current_state = self.zone_states[zone_id]
            new_state = self._calculate_zone_state(zone_id, price, entry_price, threshold_pips)
            
            # State transition
            if new_state != current_state:
                self._transition_zone_state(zone_id, current_state, new_state, price)
            
            # Check for breach
            breach_detected = price_diff_pips >= threshold_pips
            if breach_detected and current_state != ZoneState.BREACHED:
                self.zone_breach_count += 1
                logger.info(f"🚨 Zone breach detected: {price_diff_pips:.1f} pips "
                           f"(threshold: {threshold_pips} pips)")
            
            return {
                "zone_id": zone_id,
                "breach_detected": breach_detected,
                "price_diff_pips": price_diff_pips,
                "threshold_pips": threshold_pips,
                "zone_state": new_state.value,
                "previous_state": current_state.value,
                "breach_direction": "BUY" if price > entry_price else "SELL"
            }
            
        except Exception as e:
            logger.error(f"Error detecting zone breach: {e}")
            return {"error": str(e)}
    
    def calculate_reversal_point(self, cycle_orders: List, direction: str) -> Optional[float]:
        """
        Calculate 300-pip reversal from highest/lowest order
        
        Args:
            cycle_orders: List of orders in the cycle
            direction: Trading direction (BUY/SELL)
            
        Returns:
            float: Reversal trigger price or None
        """
        try:
            if not cycle_orders:
                return None
            
            pip_value = self._get_pip_value()
            reversal_pips = self.reversal_threshold_pips  # 300 pips
            
            if direction == "BUY":
                # Find highest buy order price
                order_prices = [getattr(order, 'open_price', 0) for order in cycle_orders 
                               if hasattr(order, 'open_price')]
                if not order_prices:
                    return None
                
                highest_price = max(order_prices)
                reversal_price = highest_price - (reversal_pips / pip_value)
                
                logger.debug(f"BUY reversal: highest={highest_price}, "
                           f"reversal_trigger={reversal_price}")
                
                return reversal_price
                
            else:  # SELL
                # Find lowest sell order price
                order_prices = [getattr(order, 'open_price', float('inf')) for order in cycle_orders 
                               if hasattr(order, 'open_price')]
                if not order_prices:
                    return None
                
                lowest_price = min(order_prices)
                reversal_price = lowest_price + (reversal_pips / pip_value)
                
                logger.debug(f"SELL reversal: lowest={lowest_price}, "
                           f"reversal_trigger={reversal_price}")
                
                return reversal_price
            
        except Exception as e:
            logger.error(f"Error calculating reversal point: {e}")
            return None
    
    def validate_zone_activation(self, new_zone: Dict, existing_zones: List[Dict]) -> bool:
        """
        Prevent overlapping zones
        
        Args:
            new_zone: New zone to validate
            existing_zones: List of existing zones
            
        Returns:
            bool: True if zone activation is valid
        """
        try:
            new_base_price = new_zone.get('base_price', 0)
            new_threshold = new_zone.get('threshold_pips', self.reversal_threshold_pips)
            
            pip_value = self._get_pip_value()
            new_zone_range = new_threshold / pip_value
            
            for existing_zone in existing_zones:
                existing_base = existing_zone.get('base_price', 0)
                existing_threshold = existing_zone.get('threshold_pips', self.reversal_threshold_pips)
                existing_range = existing_threshold / pip_value
                
                # Check for overlap
                distance = abs(new_base_price - existing_base)
                min_distance = (new_zone_range + existing_range) / 2
                
                if distance < min_distance:
                    logger.warning(f"Zone overlap detected: distance={distance:.5f}, "
                                 f"min_required={min_distance:.5f}")
                    return False
            
            # Check maximum zones limit
            if len(existing_zones) >= self.max_zones:
                logger.warning(f"Maximum zones limit ({self.max_zones}) reached")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating zone activation: {e}")
            return False
    
    def create_reversal_monitor(self, cycle_id: str, direction: str) -> str:
        """
        Create reversal monitor for cycle
        
        Args:
            cycle_id: Cycle identifier
            direction: Trading direction
            
        Returns:
            str: Monitor ID
        """
        try:
            monitor_id = f"{cycle_id}_reversal"
            
            if monitor_id not in self.reversal_monitors:
                monitor = ReversalMonitor(cycle_id, direction, self.reversal_threshold_pips)
                self.reversal_monitors[monitor_id] = monitor
                logger.info(f"✅ Reversal monitor created: {monitor_id} ({direction})")
            
            return monitor_id
            
        except Exception as e:
            logger.error(f"Error creating reversal monitor: {e}")
            return ""
    
    def update_reversal_monitor(self, cycle_id: str, current_price: float) -> Dict:
        """
        Update reversal monitor with current price
        
        Args:
            cycle_id: Cycle identifier
            current_price: Current market price
            
        Returns:
            Dict: Reversal status
        """
        try:
            monitor_id = f"{cycle_id}_reversal"
            
            if monitor_id not in self.reversal_monitors:
                logger.warning(f"Reversal monitor {monitor_id} not found")
                return {"error": "Monitor not found"}
            
            monitor = self.reversal_monitors[monitor_id]
            
            # Update price extremes
            monitor.update_price_extremes(current_price)
            
            # Check reversal condition
            pip_value = self._get_pip_value()
            reversal_triggered = monitor.check_reversal_condition(current_price, pip_value)
            
            if reversal_triggered:
                self.reversal_count += 1
                logger.info(f"🔄 Reversal triggered for cycle {cycle_id}")
            
            return {
                "cycle_id": cycle_id,
                "reversal_triggered": reversal_triggered,
                "highest_price": monitor.highest_price,
                "lowest_price": monitor.lowest_price,
                "direction": monitor.direction,
                "monitor_age": time.time() - monitor.creation_time
            }
            
        except Exception as e:
            logger.error(f"Error updating reversal monitor: {e}")
            return {"error": str(e)}
    
    def get_active_zones(self) -> List[Dict]:
        """
        Get all active zones
        
        Returns:
            List: Active zone information
        """
        try:
            zones = []
            current_time = time.time()
            
            for zone_id, zone_data in self.active_zones.items():
                zone_info = {
                    "zone_id": zone_id,
                    "state": self.zone_states.get(zone_id, ZoneState.INACTIVE).value,
                    "base_price": zone_data.get('base_price', 0),
                    "threshold_pips": zone_data.get('threshold_pips', self.reversal_threshold_pips),
                    "creation_time": self.zone_creation_times.get(zone_id, 0),
                    "age_seconds": current_time - self.zone_creation_times.get(zone_id, current_time),
                    "breach_count": zone_data.get('breach_count', 0)
                }
                zones.append(zone_info)
            
            return zones
            
        except Exception as e:
            logger.error(f"Error getting active zones: {e}")
            return []
    
    def cleanup_old_zones(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up old zones to prevent memory leaks
        
        Args:
            max_age_seconds: Maximum age for zones in seconds
            
        Returns:
            int: Number of zones cleaned up
        """
        try:
            current_time = time.time()
            zones_to_remove = []
            
            for zone_id, creation_time in self.zone_creation_times.items():
                if current_time - creation_time > max_age_seconds:
                    zones_to_remove.append(zone_id)
            
            # Remove old zones
            for zone_id in zones_to_remove:
                self._remove_zone(zone_id)
            
            if zones_to_remove:
                logger.info(f"🧹 Cleaned up {len(zones_to_remove)} old zones")
            
            return len(zones_to_remove)
            
        except Exception as e:
            logger.error(f"Error cleaning up zones: {e}")
            return 0
    
    def _add_price_to_history(self, price: float):
        """Add price to history with timestamp"""
        try:
            price_data = {
                "price": price,
                "timestamp": time.time(),
                "datetime": datetime.datetime.utcnow().isoformat()
            }
            
            self.price_history.append(price_data)
            
            # Maintain history size limit
            if len(self.price_history) > self.max_price_history:
                self.price_history = self.price_history[-self.max_price_history:]
            
        except Exception as e:
            logger.error(f"Error adding price to history: {e}")
    
    def _initialize_zone(self, zone_id: str, entry_price: float, threshold_pips: float):
        """Initialize a new zone"""
        try:
            self.zone_states[zone_id] = ZoneState.MONITORING
            self.zone_data[zone_id] = {
                "entry_price": entry_price,
                "threshold_pips": threshold_pips,
                "breach_count": 0,
                "creation_time": time.time()
            }
            self.active_zones[zone_id] = self.zone_data[zone_id].copy()
            self.zone_creation_times[zone_id] = time.time()
            
            logger.debug(f"Zone initialized: {zone_id} at {entry_price}")
            
        except Exception as e:
            logger.error(f"Error initializing zone {zone_id}: {e}")
    
    def _calculate_zone_state(self, zone_id: str, current_price: float, 
                             entry_price: float, threshold_pips: float) -> ZoneState:
        """Calculate new zone state based on current conditions"""
        try:
            pip_value = self._get_pip_value()
            price_diff_pips = abs(current_price - entry_price) / pip_value
            
            current_state = self.zone_states.get(zone_id, ZoneState.INACTIVE)
            
            # State machine logic
            if price_diff_pips >= threshold_pips:
                if current_state == ZoneState.MONITORING:
                    return ZoneState.BREACHED
                elif current_state == ZoneState.BREACHED:
                    # Check for reversal conditions
                    if self._check_reversal_conditions(zone_id, current_price):
                        return ZoneState.REVERSAL_PENDING
                    return ZoneState.BREACHED
                elif current_state == ZoneState.REVERSAL_PENDING:
                    if self._confirm_reversal(zone_id, current_price):
                        return ZoneState.REVERSAL_CONFIRMED
                    return ZoneState.REVERSAL_PENDING
            else:
                if current_state in [ZoneState.BREACHED, ZoneState.REVERSAL_PENDING]:
                    return ZoneState.MONITORING
            
            return current_state
            
        except Exception as e:
            logger.error(f"Error calculating zone state: {e}")
            return ZoneState.INACTIVE
    
    def _transition_zone_state(self, zone_id: str, old_state: ZoneState, 
                              new_state: ZoneState, current_price: float):
        """Handle zone state transitions"""
        try:
            self.zone_states[zone_id] = new_state
            
            # Update zone data based on transition
            if zone_id in self.zone_data:
                if new_state == ZoneState.BREACHED and old_state != ZoneState.BREACHED:
                    self.zone_data[zone_id]["breach_count"] += 1
                    self.zone_data[zone_id]["last_breach_price"] = current_price
                    self.zone_data[zone_id]["last_breach_time"] = time.time()
            
            logger.debug(f"Zone {zone_id} state: {old_state.value} → {new_state.value}")
            
        except Exception as e:
            logger.error(f"Error transitioning zone state: {e}")
    
    def _check_reversal_conditions(self, zone_id: str, current_price: float) -> bool:
        """Check if reversal conditions are met"""
        try:
            # Simplified reversal check - can be enhanced with more sophisticated logic
            zone_data = self.zone_data.get(zone_id, {})
            entry_price = zone_data.get("entry_price", 0)
            
            pip_value = self._get_pip_value()
            price_movement = abs(current_price - entry_price) / pip_value
            
            # Consider reversal if price moved significantly beyond threshold
            return price_movement > (self.reversal_threshold_pips * 1.5)
            
        except Exception as e:
            logger.error(f"Error checking reversal conditions: {e}")
            return False
    
    def _confirm_reversal(self, zone_id: str, current_price: float) -> bool:
        """Confirm reversal based on price action"""
        try:
            # Simple confirmation logic - can be enhanced
            if len(self.price_history) < 5:
                return False
            
            # Check if price is moving back towards entry
            recent_prices = [p["price"] for p in self.price_history[-5:]]
            price_trend = recent_prices[-1] - recent_prices[0]
            
            zone_data = self.zone_data.get(zone_id, {})
            entry_price = zone_data.get("entry_price", 0)
            
            # Confirm if price is moving back towards entry
            if current_price > entry_price:  # Price above entry
                return price_trend < 0  # Confirm if trending down
            else:  # Price below entry
                return price_trend > 0  # Confirm if trending up
            
        except Exception as e:
            logger.error(f"Error confirming reversal: {e}")
            return False
    
    def _remove_zone(self, zone_id: str):
        """Remove zone from all tracking structures"""
        try:
            if zone_id in self.zone_states:
                del self.zone_states[zone_id]
            if zone_id in self.zone_data:
                del self.zone_data[zone_id]
            if zone_id in self.active_zones:
                del self.active_zones[zone_id]
            if zone_id in self.zone_creation_times:
                del self.zone_creation_times[zone_id]
            
        except Exception as e:
            logger.error(f"Error removing zone {zone_id}: {e}")
    
    def _generate_zone_id(self, entry_price: float, threshold_pips: float) -> str:
        """Generate unique zone identifier"""
        try:
            # Round price to avoid floating point precision issues
            rounded_price = round(entry_price, 5)
            return f"zone_{rounded_price}_{threshold_pips}_{self.symbol}"
        except Exception as e:
            logger.error(f"Error generating zone ID: {e}")
            return f"zone_error_{int(time.time())}"
    
    def _get_pip_value(self) -> float:
        """Get pip value for the current symbol"""
        try:
            # Select the symbol to ensure it's available
            Mt5.symbol_select(self.symbol, True)
            
            # Get symbol info from MetaTrader
            symbol_info = Mt5.symbol_info(self.symbol)
            if symbol_info is None:
                logger.error(f"Cannot get symbol info for {self.symbol}")
                return self._get_fallback_pip_value()
            
            point = symbol_info.point
            pip_value = point*10
            return pip_value
            
        except Exception as e:
            logger.error(f"Error getting pip value for {self.symbol}: {e}")
            return self._get_fallback_pip_value()
    
    def _get_fallback_pip_value(self) -> float:
        """Get fallback pip value based on symbol type"""
        if "JPY" in self.symbol:
            return 0.01  # JPY pairs
        elif "XAU" in self.symbol or "GOLD" in self.symbol.upper():
            return 0.1   # Gold
        elif "BTC" in self.symbol or "ETH" in self.symbol or "USDT" in self.symbol:
            return 1.0   # Crypto
        else:
            return 0.0001  # Major currency pairs
    
    def get_detection_statistics(self) -> Dict:
        """
        Get comprehensive detection statistics
        
        Returns:
            Dict: Detection engine statistics
        """
        try:
            return {
                "symbol": self.symbol,
                "reversal_threshold_pips": self.reversal_threshold_pips,
                "order_interval_pips": self.order_interval_pips,
                "active_zones": len(self.active_zones),
                "total_zones_created": len(self.zone_creation_times),
                "zone_breach_count": self.zone_breach_count,
                "reversal_count": self.reversal_count,
                "false_signal_count": self.false_signal_count,
                "reversal_monitors": len(self.reversal_monitors),
                "price_history_length": len(self.price_history),
                "zone_states": {
                    state.value: sum(1 for s in self.zone_states.values() if s == state)
                    for state in ZoneState
                },
                "oldest_zone_age": 0,
                "newest_zone_age": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting detection statistics: {e}")
            return {"error": str(e)}
    
    def check_zone_breach(self, current_price: float, entry_price: float = None, 
                         threshold_pips: float = None) -> Dict:
        """
        Alias for detect_zone_breach method to maintain backward compatibility
        
        Args:
            current_price: Current market price
            entry_price: Entry price for comparison (optional, uses last price if not provided)
            threshold_pips: Custom threshold (optional)
            
        Returns:
            Dict: Zone breach detection results
        """
        if entry_price is None:
            # Use the last price from history if entry_price not provided
            if self.price_history:
                entry_price = self.price_history[-1]['price']
            else:
                # If no history, use current price as entry
                entry_price = current_price
        
        return self.detect_zone_breach(current_price, entry_price, threshold_pips) 