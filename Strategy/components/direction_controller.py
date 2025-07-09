import datetime
from typing import Dict, List, Optional, Tuple
from Views.globals.app_logger import app_logger as logger


class DirectionController:
    """Direction controller for Advanced Cycles Trader strategy"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.current_direction = None  # Current trading direction
        self.direction_history = []  # Track direction changes
        self.last_direction_change = None  # When direction was last changed
        self.zone_based_direction = None  # Direction determined by zone analysis
        self.candle_based_direction = None  # Direction determined by candle analysis
        self.direction_locked = False  # Lock direction during active trading
        self.direction_switch_count = 0  # Count of direction switches
        
        # Direction determination settings
        self.min_switch_interval = 300  # Minimum 5 minutes between switches
        self.confirmation_candles = 1  # Number of candles to confirm direction
        self.direction_confidence = 0.5  # Confidence level (0-1) - start with moderate confidence
        
        logger.info(f"DirectionController initialized for {symbol}")

    def determine_direction_from_zone_breach(self, zone_price: float, candle_close: float, 
                                           candle_open: float = None) -> str:
        """Determine trading direction based on zone breach and candle close"""
        try:
            # Basic direction determination based on candle close relative to zone
            if candle_close > zone_price:
                self.zone_based_direction = "BUY"
                direction_reason = f"candle closed above zone ({candle_close} > {zone_price})"
            else:
                self.zone_based_direction = "SELL"
                direction_reason = f"candle closed below zone ({candle_close} < {zone_price})"
            
            # Enhanced analysis if we have candle open price
            if candle_open:
                candle_body = abs(candle_close - candle_open)
                candle_direction = "bullish" if candle_close > candle_open else "bearish"
                
                # Adjust confidence based on candle strength
                if candle_body > 0.001:  # Significant candle body
                    self.direction_confidence = min(0.9, self.direction_confidence + 0.3)
                else:
                    self.direction_confidence = max(0.1, self.direction_confidence - 0.1)
                
                logger.info(f"Direction from zone: {self.zone_based_direction} "
                           f"({direction_reason}, candle: {candle_direction}, "
                           f"confidence: {self.direction_confidence:.2f})")
            else:
                self.direction_confidence = 0.7  # Default confidence
                logger.info(f"Direction from zone: {self.zone_based_direction} ({direction_reason})")
            
            return self.zone_based_direction
            
        except Exception as e:
            logger.error(f"Error determining direction from zone breach: {e}")
            return "HOLD"

    def analyze_candle_pattern(self, candle_data: Dict) -> str:
        """Analyze candle pattern to determine direction"""
        try:
            open_price = candle_data.get("open", 0)
            close_price = candle_data.get("close", 0)
            high_price = candle_data.get("high", 0)
            low_price = candle_data.get("low", 0)
            
            if not all([open_price, close_price, high_price, low_price]):
                logger.warning("Incomplete candle data for pattern analysis")
                return "HOLD"
            
            # Calculate candle characteristics
            body_size = abs(close_price - open_price)
            upper_shadow = high_price - max(open_price, close_price)
            lower_shadow = min(open_price, close_price) - low_price
            candle_range = high_price - low_price
            
            # Determine candle direction
            if close_price > open_price:
                candle_type = "bullish"
                suggested_direction = "BUY"
            elif close_price < open_price:
                candle_type = "bearish"
                suggested_direction = "SELL"
            else:
                candle_type = "doji"
                suggested_direction = "HOLD"
            
            # Analyze candle strength
            if candle_range > 0:
                body_ratio = body_size / candle_range
                upper_shadow_ratio = upper_shadow / candle_range
                lower_shadow_ratio = lower_shadow / candle_range
                
                # Strong candle pattern (large body, small shadows)
                if body_ratio > 0.7:
                    self.direction_confidence = 0.9
                    pattern_strength = "strong"
                # Moderate candle pattern
                elif body_ratio > 0.4:
                    self.direction_confidence = 0.6
                    pattern_strength = "moderate"
                # Weak candle pattern (small body, large shadows)
                else:
                    self.direction_confidence = 0.3
                    pattern_strength = "weak"
                    if body_ratio < 0.1:  # Doji-like
                        suggested_direction = "HOLD"
            else:
                self.direction_confidence = 0.1
                pattern_strength = "unclear"
                suggested_direction = "HOLD"
            
            self.candle_based_direction = suggested_direction
            
            logger.info(f"Candle analysis: {candle_type} {pattern_strength} -> {suggested_direction} "
                       f"(confidence: {self.direction_confidence:.2f})")
            
            return suggested_direction
            
        except Exception as e:
            logger.error(f"Error analyzing candle pattern: {e}")
            return "HOLD"

    def should_switch_direction(self, new_direction: str, current_price: float, 
                              stop_loss_hit: bool = False) -> bool:
        """Determine if direction should be switched"""
        try:
            # Always switch if stop loss was hit
            if stop_loss_hit:
                logger.info("Direction switch triggered by stop loss hit")
                return True
            
            # Don't switch if direction is locked
            if self.direction_locked:
                logger.info("Direction switch blocked - direction is locked")
                return False
            
            # Don't switch to the same direction
            if new_direction == self.current_direction:
                return False
            
            # Don't switch if invalid direction
            if new_direction not in ["BUY", "SELL"]:
                logger.warning(f"Invalid direction for switch: {new_direction}")
                return False
            
            # Check minimum time interval between switches
            if self.last_direction_change:
                time_since_last_switch = (datetime.datetime.utcnow() - self.last_direction_change).total_seconds()
                if time_since_last_switch < self.min_switch_interval:
                    logger.info(f"Direction switch blocked - too soon ({time_since_last_switch}s < {self.min_switch_interval}s)")
                    return False
            
            # Check direction confidence (lowered for testing)
            if self.direction_confidence < 0.1:
                logger.info(f"Direction switch blocked - low confidence ({self.direction_confidence:.2f})")
                return False
            
            # Additional validation based on zone and candle agreement
            if self.zone_based_direction and self.candle_based_direction:
                if self.zone_based_direction != self.candle_based_direction:
                    logger.warning("Zone and candle directions disagree - requiring higher confidence")
                    if self.direction_confidence < 0.8:
                        return False
            
            logger.info(f"Direction switch approved: {self.current_direction} -> {new_direction}")
            return True
            
        except Exception as e:
            logger.error(f"Error checking if direction should switch: {e}")
            return False

    def execute_direction_switch(self, new_direction: str, reason: str = "zone_breach") -> bool:
        """Execute a direction switch"""
        try:
            if not self.should_switch_direction(new_direction, 0, reason == "stop_loss_hit"):
                return False
            
            # Record the direction change
            old_direction = self.current_direction
            self.current_direction = new_direction
            self.last_direction_change = datetime.datetime.utcnow()
            self.direction_switch_count += 1
            
            # Add to history
            self.direction_history.append({
                "old_direction": old_direction,
                "new_direction": new_direction,
                "timestamp": self.last_direction_change,
                "reason": reason,
                "confidence": self.direction_confidence
            })
            
            # Reset confidence after switch
            self.direction_confidence = 0.7
            
            logger.info(f"Direction switched: {old_direction} -> {new_direction} "
                       f"(reason: {reason}, count: {self.direction_switch_count})")
            
            return True
            
        except Exception as e:
            logger.error(f"Error executing direction switch: {e}")
            return False

    def lock_direction(self, lock: bool = True) -> bool:
        """Lock or unlock the current direction"""
        try:
            self.direction_locked = lock
            status = "locked" if lock else "unlocked"
            logger.info(f"Direction {status}: {self.current_direction}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting direction lock: {e}")
            return False

    def get_direction_confidence(self) -> float:
        """Get current direction confidence level"""
        return self.direction_confidence

    def get_current_direction(self) -> Optional[str]:
        """Get the current trading direction"""
        return self.current_direction

    def validate_direction_consistency(self) -> Dict:
        """Validate consistency between zone and candle directions"""
        try:
            consistency_check = {
                "zone_direction": self.zone_based_direction,
                "candle_direction": self.candle_based_direction,
                "current_direction": self.current_direction,
                "consistent": True,
                "confidence": self.direction_confidence
            }
            
            # Check if all directions agree
            directions = [d for d in [self.zone_based_direction, self.candle_based_direction, self.current_direction] if d]
            
            if len(set(directions)) > 1:
                consistency_check["consistent"] = False
                consistency_check["conflict"] = f"Directions disagree: {directions}"
                logger.warning(f"Direction inconsistency detected: {directions}")
            else:
                logger.info("Direction consistency validated")
            
            return consistency_check
            
        except Exception as e:
            logger.error(f"Error validating direction consistency: {e}")
            return {"consistent": False, "error": str(e)}

    def get_direction_statistics(self) -> Dict:
        """Get comprehensive direction statistics"""
        try:
            recent_switches = len([h for h in self.direction_history 
                                 if (datetime.datetime.utcnow() - h["timestamp"]).total_seconds() < 3600])
            
            return {
                "current_direction": self.current_direction,
                "direction_locked": self.direction_locked,
                "total_switches": self.direction_switch_count,
                "recent_switches_1h": recent_switches,
                "last_switch_time": self.last_direction_change,
                "direction_confidence": self.direction_confidence,
                "zone_based_direction": self.zone_based_direction,
                "candle_based_direction": self.candle_based_direction,
                "switch_history_count": len(self.direction_history)
            }
            
        except Exception as e:
            logger.error(f"Error getting direction statistics: {e}")
            return {}

    def reset_direction_state(self) -> bool:
        """Reset direction state (use with caution)"""
        try:
            self.current_direction = None
            self.zone_based_direction = None
            self.candle_based_direction = None
            self.direction_locked = False
            self.direction_confidence = 0.0
            self.last_direction_change = None
            # Keep history for analysis but reset counters
            self.direction_switch_count = 0
            
            logger.info("Direction state reset")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting direction state: {e}")
            return False

    def get_direction_recommendation(self, zone_price: float, candle_data: Dict, 
                                   current_price: float) -> Dict:
        """Get comprehensive direction recommendation"""
        try:
            # Analyze zone breach
            zone_direction = self.determine_direction_from_zone_breach(
                zone_price, candle_data.get("close", current_price), candle_data.get("open")
            )
            
            # Analyze candle pattern
            candle_direction = self.analyze_candle_pattern(candle_data)
            
            # Validate consistency
            consistency = self.validate_direction_consistency()
            
            # Determine final recommendation
            if zone_direction == candle_direction and zone_direction != "HOLD":
                recommended_direction = zone_direction
                recommendation_strength = "strong"
                confidence = min(0.95, self.direction_confidence + 0.2)
            elif zone_direction != "HOLD" and candle_direction == "HOLD":
                recommended_direction = zone_direction
                recommendation_strength = "moderate"
                confidence = self.direction_confidence
            elif candle_direction != "HOLD" and zone_direction == "HOLD":
                recommended_direction = candle_direction
                recommendation_strength = "moderate"
                confidence = self.direction_confidence
            else:
                recommended_direction = "HOLD"
                recommendation_strength = "weak"
                confidence = 0.3
            
            return {
                "recommended_direction": recommended_direction,
                "strength": recommendation_strength,
                "confidence": confidence,
                "zone_direction": zone_direction,
                "candle_direction": candle_direction,
                "consistency": consistency,
                "should_switch": self.should_switch_direction(recommended_direction, current_price)
            }
            
        except Exception as e:
            logger.error(f"Error getting direction recommendation: {e}")
            return {"recommended_direction": "HOLD", "error": str(e)}

    def update_direction_from_market_data(self, market_data: Dict) -> bool:
        """Update direction based on latest market data"""
        try:
            if not market_data:
                return False
            
            # Extract relevant data
            current_price = market_data.get("current_price", 0)
            zone_price = market_data.get("zone_price")
            candle_data = market_data.get("candle", {})
            
            if not zone_price or not candle_data:
                logger.warning("Insufficient market data for direction update")
                return False
            
            # Get direction recommendation
            recommendation = self.get_direction_recommendation(zone_price, candle_data, current_price)
            
            # Execute switch if recommended
            if recommendation["should_switch"] and recommendation["recommended_direction"] != "HOLD":
                return self.execute_direction_switch(
                    recommendation["recommended_direction"], 
                    "market_analysis"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating direction from market data: {e}")
            return False