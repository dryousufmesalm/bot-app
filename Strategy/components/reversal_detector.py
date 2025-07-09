"""
Reversal Detector Component
Implements price reversal detection logic for the Advanced Cycles Trader
"""

import time
import datetime
from typing import Dict, List, Optional, Tuple
from Views.globals.app_logger import app_logger as logger


class ReversalDetector:
    """
    Reversal detector for Advanced Cycles Trader strategy.
    Tracks highest/lowest prices and detects reversals based on threshold.
    """
    
    def __init__(self, symbol: str, reversal_threshold_pips: float = 300.0):
        """
        Initialize reversal detector
        
        Args:
            symbol: Trading symbol
            reversal_threshold_pips: Pip threshold for reversal detection (default: 300.0)
        """
        self.symbol = symbol
        self.reversal_threshold_pips = reversal_threshold_pips
        
        # Price tracking
        self.highest_buy_price = 0.0
        self.lowest_sell_price = float('inf')
        self.last_price = 0.0
        
        # Direction tracking
        self.current_direction = None
        self.reversal_count = 0
        self.last_reversal_time = None
        self.min_reversal_interval = 300  # Minimum 5 minutes between reversals
        
        # Reversal monitoring
        self.active_monitors: Dict[str, Dict] = {}  # cycle_id -> monitor data
        self.reversal_history: List[Dict] = []
        
        logger.info(f"ReversalDetector initialized for {symbol} with {reversal_threshold_pips} pips threshold")
    
    def create_reversal_monitor(self, cycle_id: str, direction: str) -> str:
        """
        Create a new reversal monitor for a cycle
        
        Args:
            cycle_id: ID of the cycle to monitor
            direction: Initial direction (BUY/SELL)
            
        Returns:
            str: Monitor ID or None if failed
        """
        try:
            if cycle_id in self.active_monitors:
                logger.warning(f"Reversal monitor already exists for cycle {cycle_id}")
                return cycle_id
            
            # Validate direction
            if direction not in ["BUY", "SELL"]:
                logger.error(f"Invalid direction for reversal monitor: {direction}")
                return None
            
            # Create monitor
            monitor_id = f"rev_{cycle_id}_{int(time.time())}"
            self.active_monitors[cycle_id] = {
                "monitor_id": monitor_id,
                "cycle_id": cycle_id,
                "direction": direction,
                "created_time": datetime.datetime.utcnow(),
                "highest_price": 0.0,
                "lowest_price": float('inf'),
                "last_price": 0.0,
                "reversal_triggered": False,
                "reversal_price": None,
                "reversal_time": None
            }
            
            logger.info(f"Created reversal monitor {monitor_id} for cycle {cycle_id} with direction {direction}")
            return monitor_id
            
        except Exception as e:
            logger.error(f"Error creating reversal monitor: {e}")
            return None
    
    def update_reversal_monitor(self, cycle_id: str, current_price: float) -> Dict:
        """
        Update reversal monitor with current price and check for reversals
        
        Args:
            cycle_id: ID of the cycle to update
            current_price: Current market price
            
        Returns:
            Dict: Monitor status including reversal detection
        """
        try:
            if cycle_id not in self.active_monitors:
                logger.warning(f"No reversal monitor found for cycle {cycle_id}")
                return {"error": "Monitor not found"}
            
            monitor = self.active_monitors[cycle_id]
            direction = monitor["direction"]
            
            # Update price tracking
            monitor["last_price"] = current_price
            
            # Update highest/lowest prices
            if direction == "BUY":
                if current_price > monitor["highest_price"]:
                    monitor["highest_price"] = current_price
                    logger.debug(f"Updated highest BUY price to {current_price} for cycle {cycle_id}")
            else:  # SELL
                if current_price < monitor["lowest_price"] or monitor["lowest_price"] == float('inf'):
                    monitor["lowest_price"] = current_price
                    logger.debug(f"Updated lowest SELL price to {current_price} for cycle {cycle_id}")
            
            # Check for reversal
            reversal_detected = False
            reversal_price = None
            
            if direction == "BUY" and monitor["highest_price"] > 0:
                # For BUY direction, check if price dropped below threshold
                pip_value = self._get_pip_value()
                threshold_distance = self.reversal_threshold_pips / pip_value
                reversal_price = monitor["highest_price"] - threshold_distance
                
                if current_price <= reversal_price:
                    reversal_detected = True
                    logger.info(f"🔄 BUY→SELL reversal detected for cycle {cycle_id}: "
                               f"Price {current_price} dropped {self.reversal_threshold_pips} pips "
                               f"from highest {monitor['highest_price']}")
            
            elif direction == "SELL" and monitor["lowest_price"] < float('inf'):
                # For SELL direction, check if price rose above threshold
                pip_value = self._get_pip_value()
                threshold_distance = self.reversal_threshold_pips / pip_value
                reversal_price = monitor["lowest_price"] + threshold_distance
                
                if current_price >= reversal_price:
                    reversal_detected = True
                    logger.info(f"🔄 SELL→BUY reversal detected for cycle {cycle_id}: "
                               f"Price {current_price} rose {self.reversal_threshold_pips} pips "
                               f"from lowest {monitor['lowest_price']}")
            
            # Update monitor if reversal detected
            if reversal_detected and not monitor["reversal_triggered"]:
                monitor["reversal_triggered"] = True
                monitor["reversal_price"] = reversal_price
                monitor["reversal_time"] = datetime.datetime.utcnow()
                
                # Add to history
                self.reversal_history.append({
                    "cycle_id": cycle_id,
                    "old_direction": direction,
                    "new_direction": "SELL" if direction == "BUY" else "BUY",
                    "reversal_price": reversal_price,
                    "current_price": current_price,
                    "highest_price": monitor["highest_price"],
                    "lowest_price": monitor["lowest_price"],
                    "timestamp": monitor["reversal_time"]
                })
                
                self.reversal_count += 1
                self.last_reversal_time = monitor["reversal_time"]
            
            return {
                "cycle_id": cycle_id,
                "direction": direction,
                "highest_price": monitor["highest_price"],
                "lowest_price": monitor["lowest_price"],
                "current_price": current_price,
                "reversal_triggered": monitor["reversal_triggered"],
                "reversal_price": monitor["reversal_price"],
                "new_direction": "SELL" if direction == "BUY" else "BUY" if monitor["reversal_triggered"] else None
            }
            
        except Exception as e:
            logger.error(f"Error updating reversal monitor: {e}")
            return {"error": str(e)}
    
    def get_new_direction_after_reversal(self, cycle_id: str) -> Optional[str]:
        """
        Get the new direction after a reversal
        
        Args:
            cycle_id: ID of the cycle
            
        Returns:
            str: New direction or None if no reversal
        """
        try:
            if cycle_id not in self.active_monitors:
                return None
            
            monitor = self.active_monitors[cycle_id]
            
            if monitor["reversal_triggered"]:
                current_direction = monitor["direction"]
                return "SELL" if current_direction == "BUY" else "BUY"
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting new direction after reversal: {e}")
            return None
    
    def reset_monitor_after_direction_switch(self, cycle_id: str, new_direction: str) -> bool:
        """
        Reset monitor after a direction switch
        
        Args:
            cycle_id: ID of the cycle
            new_direction: New direction after switch
            
        Returns:
            bool: True if reset successful
        """
        try:
            if cycle_id not in self.active_monitors:
                logger.warning(f"No reversal monitor found for cycle {cycle_id}")
                return False
            
            # Store the last price from the old monitor
            last_price = self.active_monitors[cycle_id]["last_price"]
            
            # Create a new monitor with the new direction
            monitor_id = f"rev_{cycle_id}_{int(time.time())}"
            self.active_monitors[cycle_id] = {
                "monitor_id": monitor_id,
                "cycle_id": cycle_id,
                "direction": new_direction,
                "created_time": datetime.datetime.utcnow(),
                "highest_price": last_price if new_direction == "BUY" else 0.0,
                "lowest_price": last_price if new_direction == "SELL" else float('inf'),
                "last_price": last_price,
                "reversal_triggered": False,
                "reversal_price": None,
                "reversal_time": None
            }
            
            logger.info(f"Reset reversal monitor for cycle {cycle_id} with new direction {new_direction}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting reversal monitor: {e}")
            return False
    
    def get_reversal_statistics(self) -> Dict:
        """
        Get reversal statistics
        
        Returns:
            Dict: Reversal statistics
        """
        try:
            active_monitors = len(self.active_monitors)
            triggered_monitors = sum(1 for m in self.active_monitors.values() if m["reversal_triggered"])
            
            return {
                "total_reversals": self.reversal_count,
                "active_monitors": active_monitors,
                "triggered_monitors": triggered_monitors,
                "last_reversal_time": self.last_reversal_time.isoformat() if self.last_reversal_time else None,
                "buy_monitors": sum(1 for m in self.active_monitors.values() if m["direction"] == "BUY"),
                "sell_monitors": sum(1 for m in self.active_monitors.values() if m["direction"] == "SELL")
            }
            
        except Exception as e:
            logger.error(f"Error getting reversal statistics: {e}")
            return {"error": str(e)}
    
    def _get_pip_value(self) -> float:
        """Get pip value for the current symbol"""
        try:
            if 'JPY' in self.symbol:
                return 100.0  # JPY pairs have 2 decimal places
            else:
                return 10000.0  # Most pairs have 4 decimal places
        except Exception as e:
            logger.error(f"Error getting pip value: {e}")
            return 10000.0  # Default 