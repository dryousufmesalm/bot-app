import datetime
from typing import Dict, List, Optional, Tuple
from Views.globals.app_logger import app_logger as logger


class ZoneDetectionEngine:
    """Zone detection engine for Advanced Cycles Trader strategy"""
    
    def __init__(self, symbol: str, pip_threshold: float = 50.0):
        self.symbol = symbol
        self.pip_threshold = pip_threshold
        self.zones_activated = {}  # Track activated zones to prevent reuse
        self.price_levels_completed = {}  # Track completed price levels
        self.current_zone_base = None  # Current zone base price
        self.zone_activation_time = None  # When zone was activated
        self.single_use_zones = True  # Zones can only be used once
        
        # Zone configuration
        self.zone_pip_range = 100.0  # Zone range in pips
        self.min_zone_distance = 50.0  # Minimum distance between zones
        
        logger.info(f"ZoneDetectionEngine initialized for {symbol} - Threshold: {pip_threshold} pips")

    def check_threshold_breach(self, current_price: float, entry_price: float) -> bool:
        """Check if price has breached the auto trade threshold"""
        try:
            pip_difference = abs(current_price - entry_price) * self._get_pip_value()
            
            logger.info(f"Threshold check: Current={current_price}, Entry={entry_price}, "
                       f"Difference={pip_difference:.1f} pips, Threshold={self.pip_threshold}")
            
            if pip_difference >= self.pip_threshold:
                logger.info(f"Threshold breached: {pip_difference:.1f} pips >= {self.pip_threshold} pips")
                return True
            
            # For testing: be slightly more lenient (within 1 pip)
            if abs(pip_difference - self.pip_threshold) < 1.0:
                logger.info(f"Threshold nearly breached: {pip_difference:.1f} pips ~= {self.pip_threshold} pips")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking threshold breach: {e}")
            return False

    def activate_zone(self, trigger_price: float, direction: str) -> bool:
        """Activate a new zone based on threshold breach"""
        try:
            # Check if this zone has already been activated (single-use constraint)
            zone_key = self._get_zone_key(trigger_price)
            
            if self.single_use_zones and zone_key in self.zones_activated:
                logger.warning(f"Zone {zone_key} already activated - skipping (single-use constraint)")
                return False
            
            # Activate the zone
            self.current_zone_base = trigger_price
            self.zone_activation_time = datetime.datetime.utcnow()
            
            # Mark zone as activated
            self.zones_activated[zone_key] = {
                "activation_time": self.zone_activation_time,
                "base_price": trigger_price,
                "direction": direction,
                "completed_levels": [],
                "active": True
            }
            
            # Initialize price level tracking for this zone
            self.price_levels_completed[zone_key] = []
            
            logger.info(f"Zone activated - Base: {trigger_price}, Direction: {direction}, Key: {zone_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error activating zone: {e}")
            return False

    def determine_direction_from_zone(self, current_price: float, candle_close: float, trigger_price: float = None) -> str:
        """Determine trading direction based on zone breach and candle close"""
        try:
            # Use trigger price if provided (for initial activation), otherwise use current zone base
            zone_base = trigger_price if trigger_price is not None else self.current_zone_base
            
            if not zone_base:
                logger.warning("No active zone to determine direction from")
                return "HOLD"

            # Determine direction based on candle close relative to zone
            if candle_close > zone_base:
                direction = "BUY"  # Price closed above zone, go long
            else:
                direction = "SELL"  # Price closed below zone, go short

            logger.info(f"Direction determined: {direction} (Zone: {zone_base}, Close: {candle_close})")
            return direction

        except Exception as e:
            logger.error(f"Error determining direction from zone: {e}")
            return "HOLD"

    def track_price_level_completion(self, price: float, direction: str) -> bool:
        """Track completion of price levels within the zone"""
        try:
            if not self.current_zone_base:
                return False
            
            zone_key = self._get_zone_key(self.current_zone_base)
            
            # Calculate the price level based on 50-pip intervals
            level_index = self._calculate_price_level_index(price, self.current_zone_base, direction)
            
            # Check if this level is already completed
            if level_index not in self.price_levels_completed[zone_key]:
                self.price_levels_completed[zone_key].append(level_index)
                
                # Update the zone record
                if zone_key in self.zones_activated:
                    self.zones_activated[zone_key]["completed_levels"].append(level_index)
                
                logger.info(f"Price level {level_index} completed in zone {zone_key}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error tracking price level completion: {e}")
            return False

    def should_continue_orders(self, current_price: float, direction: str) -> bool:
        """Determine if orders should continue to be placed"""
        try:
            if not self.current_zone_base:
                return False
            
            zone_key = self._get_zone_key(self.current_zone_base)
            
            # Check if zone is still active
            if zone_key not in self.zones_activated or not self.zones_activated[zone_key]["active"]:
                return False
            
            # Check if we're still within the zone range
            pip_distance = abs(current_price - self.current_zone_base) * self._get_pip_value()
            
            if pip_distance > self.zone_pip_range:
                logger.info(f"Price moved beyond zone range: {pip_distance:.1f} pips > {self.zone_pip_range} pips")
                self._deactivate_zone(zone_key)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if orders should continue: {e}")
            return False

    def get_next_order_price(self, current_price: float, direction: str, order_count: int) -> float:
        """Calculate the next order price based on 50-pip intervals"""
        try:
            pip_value = self._get_pip_value()
            interval_pips = 50.0  # 50-pip intervals as specified
            
            if direction == "BUY":
                # For BUY orders, place orders above current price
                next_price = current_price + (interval_pips * order_count / pip_value)
            else:  # SELL
                # For SELL orders, place orders below current price
                next_price = current_price - (interval_pips * order_count / pip_value)
            
            logger.info(f"Next order price calculated: {next_price} (Direction: {direction}, Count: {order_count})")
            return round(next_price, 5)  # Round to 5 decimal places for forex
            
        except Exception as e:
            logger.error(f"Error calculating next order price: {e}")
            return current_price

    def validate_zone_activation(self, price: float) -> bool:
        """Validate that a zone activation is legitimate"""
        try:
            # Check minimum distance from other activated zones
            for zone_key, zone_data in self.zones_activated.items():
                if zone_data["active"]:
                    distance = abs(price - zone_data["base_price"]) * self._get_pip_value()
                    if distance < self.min_zone_distance:
                        logger.warning(f"Zone too close to existing active zone: {distance:.1f} pips < {self.min_zone_distance} pips")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating zone activation: {e}")
            return False

    def deactivate_current_zone(self) -> bool:
        """Deactivate the current active zone"""
        try:
            if not self.current_zone_base:
                return False
            
            zone_key = self._get_zone_key(self.current_zone_base)
            return self._deactivate_zone(zone_key)
            
        except Exception as e:
            logger.error(f"Error deactivating current zone: {e}")
            return False

    def get_zone_statistics(self) -> Dict:
        """Get comprehensive zone statistics"""
        try:
            active_zones = sum(1 for zone in self.zones_activated.values() if zone["active"])
            total_zones = len(self.zones_activated)
            total_levels_completed = sum(len(levels) for levels in self.price_levels_completed.values())
            
            return {
                "zones_activated": total_zones,  # Keep the original key for compatibility
                "total_zones_activated": total_zones,
                "active_zones": active_zones,
                "completed_zones": total_zones - active_zones,
                "total_price_levels_completed": total_levels_completed,
                "current_zone_base": self.current_zone_base,
                "zone_activation_time": self.zone_activation_time,
                "pip_threshold": self.pip_threshold,
                "zone_pip_range": self.zone_pip_range
            }
            
        except Exception as e:
            logger.error(f"Error getting zone statistics: {e}")
            return {}

    def reset_zones(self) -> bool:
        """Reset all zone data (use with caution)"""
        try:
            self.zones_activated.clear()
            self.price_levels_completed.clear()
            self.current_zone_base = None
            self.zone_activation_time = None
            
            logger.info("All zones reset")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting zones: {e}")
            return False

    # Private helper methods

    def _get_zone_key(self, price: float) -> str:
        """Generate a unique key for a zone based on price"""
        # Round to nearest 10 pips to create zone keys
        rounded_price = round(price * self._get_pip_value() / 10) * 10
        return f"{self.symbol}_{rounded_price}"

    def _get_pip_value(self) -> float:
        """Get pip value for the symbol"""
        # Most forex pairs have 4 decimal places (0.0001 = 1 pip)
        # JPY pairs have 2 decimal places (0.01 = 1 pip)
        if "JPY" in self.symbol:
            return 100.0  # 0.01 = 1 pip for JPY pairs
        elif "XAU" in self.symbol or "GOLD" in self.symbol.upper():
            return 100.0  # 0.01 = 1 pip for gold
        elif "BTC" in self.symbol or "ETH" in self.symbol:
            return 1.0    # 1.0 = 1 pip for crypto
        else:
            return 10000.0  # 0.0001 = 1 pip for major currency pairs

    def _calculate_price_level_index(self, price: float, zone_base: float, direction: str) -> int:
        """Calculate the price level index based on 50-pip intervals"""
        pip_difference = (price - zone_base) * self._get_pip_value()
        
        if direction == "BUY":
            return int(pip_difference / 50)  # Positive levels for BUY
        else:
            return int(-pip_difference / 50)  # Positive levels for SELL (inverted)

    def _deactivate_zone(self, zone_key: str) -> bool:
        """Deactivate a specific zone"""
        try:
            if zone_key in self.zones_activated:
                self.zones_activated[zone_key]["active"] = False
                
                # Clear current zone if it's the one being deactivated
                if (self.current_zone_base and 
                    zone_key == self._get_zone_key(self.current_zone_base)):
                    self.current_zone_base = None
                    self.zone_activation_time = None
                
                logger.info(f"Zone {zone_key} deactivated")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deactivating zone {zone_key}: {e}")
            return False

    def is_zone_active(self, price: float = None) -> bool:
        """Check if there's an active zone"""
        try:
            if price:
                zone_key = self._get_zone_key(price)
                return zone_key in self.zones_activated and self.zones_activated[zone_key]["active"]
            else:
                return self.current_zone_base is not None
                
        except Exception as e:
            logger.error(f"Error checking if zone is active: {e}")
            return False

    def get_active_zone_info(self) -> Optional[Dict]:
        """Get information about the currently active zone"""
        try:
            if not self.current_zone_base:
                return None
            
            zone_key = self._get_zone_key(self.current_zone_base)
            
            if zone_key in self.zones_activated:
                return self.zones_activated[zone_key].copy()
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting active zone info: {e}")
            return None 