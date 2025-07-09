from cycles.ACT_cycle_Organized import AdvancedCycle as ACT_cycle
from cycles.AH_cycle import cycle as AH_cycle
from cycles.CT_cycle import cycle as CT_cycle
from DB.db_engine import engine
from DB.ah_strategy.repositories.ah_repo import AHRepo
from DB.ct_strategy.repositories.ct_repo import CTRepo
# ACTRepo removed - using in-memory operations
import time
import asyncio
import logging
from Views.globals.app_logger import app_logger as logger

logger = logging.getLogger(__name__)

class cycles_manager:
    def __init__(self, mt5, remote_api, account):
        self.mt5 = mt5
        self.ah_repo = AHRepo(engine=engine)
        self.ct_repo = CTRepo(engine=engine)
        # ACTRepo removed - using in-memory operations
        self.remote_api = remote_api
        self.all_AH_cycles = []
        self.remote_AH_cycles = []
        self.all_CT_cycles = []
        self.remote_CT_cycles = []
        self.all_ACT_cycles = []
        self.remote_ACT_cycles = []
        self.account = account

    def get_all_AH_active_cycles(self):
        try:
            cycles = self.ah_repo.get_active_cycles(self.account.id)
            active_cycles = [
                cycle for cycle in cycles if cycle.is_closed is False]
            return active_cycles
        except Exception as e:
            logger.error(f"Error getting all AH active cycles: {e}")
            return []

    def get_all_CT_active_cycles(self):
        try:
            cycles = self.ct_repo.get_active_cycles(self.account.id)
            active_cycles = [
                cycle for cycle in cycles if cycle.is_closed is False]
            return active_cycles
        except Exception as e:
            logger.error(f"Error getting all CT active cycles: {e}")
            return []

    def get_all_ACT_active_cycles(self):
        """Get all active ACT cycles from PocketBase (since ACT cycles are stored there directly)"""
        try:
            # ACT cycles are stored directly in PocketBase, not local database
            logger.debug(f"Requesting ACT cycles for account {self.account.id}")
            cycles = self.remote_api.get_all_ACT_active_cycles_by_account(self.account.id)
            
            # Enhanced diagnostic logging
            if cycles is None:
                logger.warning("remote_api.get_all_ACT_active_cycles_by_account returned None")
                return []
            
            if len(cycles) == 0:
                logger.debug("No ACT cycles found in PocketBase for this account")
                return []
            
            logger.info(f"Found {len(cycles)} total ACT cycles in PocketBase")
            
            # Filter for active cycles with detailed logging
            active_cycles = []
            closed_cycles = 0
            
            for cycle in cycles:
                is_closed = getattr(cycle, 'is_closed', False)
                cycle_id = getattr(cycle, 'id', 'unknown')
                
                if is_closed:
                    closed_cycles += 1
                    logger.debug(f"ACT cycle {cycle_id} is closed - skipping")
                else:
                    active_cycles.append(cycle)
                    logger.debug(f"ACT cycle {cycle_id} is active - including")
            
            logger.info(f"ACT cycles summary: {len(active_cycles)} active, {closed_cycles} closed")
            
            if len(active_cycles) == 0:
                logger.info("No active ACT cycles found after filtering")
            
            return active_cycles
            
        except Exception as e:
            logger.error(f"Error getting all ACT active cycles: {e}")
            logger.error(f"Account ID: {getattr(self.account, 'id', 'unknown')}")
            logger.error(f"Remote API available: {self.remote_api is not None}")
            return []

    def get_remote_AH_active_cycles(self):
        try:
            cycles = self.remote_api.get_all_AH_active_cycles_by_account(
                self.account.id)
            if cycles is None or len(cycles) == 0:
                return []
            active_cycles = [
                cycle for cycle in cycles if cycle.is_closed is False]
            return active_cycles
        except Exception as e:
            logger.error(f"Error getting remote AH active cycles: {e}")
            return []

    def get_remote_CT_active_cycles(self):
        try:
            cycles = self.remote_api.get_all_CT_active_cycles_by_account(
                self.account.id)
            if cycles is None or len(cycles) == 0:
                return []
            active_cycles = [
                cycle for cycle in cycles if cycle.is_closed is False]
            return active_cycles
        except Exception as e:
            logger.error(f"Error getting remote CT active cycles: {e}")
            return []

    def get_remote_ACT_active_cycles(self):
        """Get remote ACT cycles - same as get_all_ACT_active_cycles since they're stored in PocketBase"""
        return self.get_all_ACT_active_cycles()

    async def run_cycles_manager(self):
        while True:
            try:
                await asyncio.gather(
                    self.sync_AH_cycles(),
                    self.sync_CT_cycles(),
                    self.sync_ACT_cycles(),
                    self.fix_incorrectly_closed_cycles()
                )
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in run_cycles_manager: {e}")

    async def sync_AH_cycles(self):
        try:
            self.all_AH_cycles = self.get_all_AH_active_cycles()  # get all orders from MT5
            # get all orders from remote
            self.remote_AH_cycles = self.get_remote_AH_active_cycles()

            if self.remote_AH_cycles is None:
                logger.error("remote_AH_cycles is None")
                return

            for remote_cycle in self.remote_AH_cycles:
                try:
                    if remote_cycle is None:
                        logger.error(
                            "Found None remote_cycle in remote_AH_cycles")
                        continue

                    cycle_id = remote_cycle.id
                    if cycle_id not in [cycle.cycle_id for cycle in self.all_AH_cycles]:
                        cycle_data = self.ah_repo.get_cycle_by_remote_id(
                            cycle_id)
                        if cycle_data is not None:
                            cycle_obj = AH_cycle(
                                cycle_data, self.mt5, self, "db")
                            self.remote_api.update_AH_cycle_by_id(
                                cycle_obj.cycle_id, cycle_obj.to_remote_dict())
                        if cycle_data is None:
                            try:
                                cycle_obj = AH_cycle(
                                    remote_cycle, self.mt5, self, "remote")
                                self.ah_repo.create_cycle(cycle_obj.to_dict())
                            except Exception as creation_error:
                                logger.error(
                                    f"Error creating AH cycle from remote data: {creation_error}")
                except Exception as cycle_error:
                    logger.error(
                        f"Error processing remote AH cycle: {cycle_error}")

            for cycle_data in self.all_AH_cycles:
                try:
                    if cycle_data is None:
                        logger.error("Found None cycle_data in all_AH_cycles")
                        continue

                    cycle_obj = AH_cycle(cycle_data, self.mt5, self, "db")
                    cycle_id = cycle_obj.cycle_id

                    if not cycle_id:
                        logger.error(
                            f"Empty cycle_id for local AH cycle {cycle_data.id}")
                        continue

                    self.remote_api.update_AH_cycle_by_id(
                        cycle_id, cycle_obj.to_remote_dict())
                except Exception as local_cycle_error:
                    logger.error(
                        f"Error processing local AH cycle: {local_cycle_error}")
        except Exception as e:
            logger.error(f"Error in sync_AH_cycles: {e}")

    async def sync_CT_cycles(self):
        try:
            self.all_CT_cycles = self.get_all_CT_active_cycles()

            self.remote_CT_cycles = self.get_remote_CT_active_cycles()

            if self.remote_CT_cycles is None:
                logger.error("remote_CT_cycles is None")
                return

            for remote_cycle in self.remote_CT_cycles:
                if remote_cycle is None:
                    logger.error("Found None remote_cycle in remote_CT_cycles")
                    continue

                try:
                    cycle_id = remote_cycle.id

                    if cycle_id not in [cycle.cycle_id for cycle in self.all_CT_cycles]:
                        cycle_data = self.ct_repo.get_cycle_by_remote_id(
                            cycle_id)

                        if cycle_data is not None:
                            cycle_obj = CT_cycle(
                                cycle_data, self.mt5, self, "db")
                            self.remote_api.update_CT_cycle_by_id(
                                cycle_obj.cycle_id, cycle_obj.to_remote_dict())
                        if cycle_data is None:
                            try:
                                cycle_obj = CT_cycle(
                                    remote_cycle, self.mt5, self, "remote")
                                self.ct_repo.create_cycle(cycle_obj.to_dict())
                            except Exception as creation_error:
                                logger.error(
                                    f"Error creating cycle from remote data: {creation_error}")
                except Exception as cycle_error:
                    logger.error(
                        f"Error processing remote cycle: {cycle_error}")

            for cycle_data in self.all_CT_cycles:
                try:
                    if cycle_data is None:
                        logger.error("Found None cycle_data in all_CT_cycles")
                        continue

                    cycle_obj = CT_cycle(cycle_data, self.mt5, self, "db")
                    cycle_id = cycle_obj.cycle_id

                    if not cycle_id:
                        logger.error(
                            f"Empty cycle_id for local cycle {cycle_data.id}")
                        continue

                    remote_dict = cycle_obj.to_remote_dict()
                    self.remote_api.update_CT_cycle_by_id(
                        cycle_id, remote_dict)
                except Exception as local_cycle_error:
                    logger.error(
                        f"Error processing local cycle: {local_cycle_error}")
        except Exception as e:
            logger.error(f"Error in sync_CT_cycles: {e}")

    async def sync_ACT_cycles(self):
        """
        Sync ACT cycles - simpler than AH/CT since ACT cycles are stored directly in PocketBase.
        This method primarily monitors and validates ACT cycle data consistency.
        """
        try:
            # Get all active ACT cycles from PocketBase
            self.all_ACT_cycles = self.get_all_ACT_active_cycles()
            self.remote_ACT_cycles = self.all_ACT_cycles  # Same source for ACT cycles

            if not self.all_ACT_cycles:
                logger.debug("No active ACT cycles found")
                return

            # For ACT cycles, we mainly validate and update their live data
            validated_count = 0
            for cycle_data in self.all_ACT_cycles:
                try:
                    if cycle_data is None:
                        logger.error("Found None cycle_data in all_ACT_cycles")
                        continue

                    # FIXED: Get the proper bot for this cycle
                    bot_for_cycle = self._get_bot_for_cycle(cycle_data)
                    if bot_for_cycle is None:
                        logger.error(f"Could not find bot for ACT cycle {getattr(cycle_data, 'id', 'unknown')} - skipping check")
                        continue

                    # Create ACT cycle object to validate and update
                    cycle_obj = ACT_cycle(cycle_data.__dict__, self.mt5, bot_for_cycle)
                    
                    # Update orders with live data from MetaTrader
                    cycle_obj.update_orders_with_live_data()
                    
                    # Update the cycle status
                    cycle_obj.update_cycle_status()
                    
                    # Update in PocketBase if there were changes
                    try:
                        update_data = {
                            'active_orders': cycle_obj.active_orders,
                            'completed_orders': cycle_obj.completed_orders,
                            'total_profit': getattr(cycle_obj, 'total_profit', 0.0),
                            'is_closed': getattr(cycle_obj, 'is_closed', False),
                            'updated': int(time.time())
                        }
                        
                        self.remote_api.update_ACT_cycle_by_id(cycle_data.id, update_data)
                        validated_count += 1
                        
                    except Exception as update_error:
                        logger.error(f"Error updating ACT cycle {cycle_data.id}: {update_error}")
                        
                except Exception as cycle_error:
                    logger.error(f"Error processing ACT cycle: {cycle_error}")

            if validated_count > 0:
                logger.debug(f"Validated and updated {validated_count} ACT cycles")
                
        except Exception as e:
            logger.error(f"Error in sync_ACT_cycles: {e}")

    def _get_bot_for_cycle(self, cycle_data):
        """Get the bot instance for a given cycle"""
        try:
            # Get bot ID from cycle data
            bot_id = getattr(cycle_data, 'bot', None)
            if not bot_id:
                logger.error(f"No bot ID found in cycle data for cycle {getattr(cycle_data, 'id', 'unknown')}")
                return None
            
            # Find the bot in the account's bots list
            if hasattr(self.account, 'bots') and self.account.bots:
                for bot in self.account.bots:
                    if str(bot.id) == str(bot_id):
                        logger.debug(f"Found bot {bot.id} for cycle {getattr(cycle_data, 'id', 'unknown')}")
                        return bot
           
            logger.error(f"Bot {bot_id} not found in account bots for cycle {getattr(cycle_data, 'id', 'unknown')}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding bot for cycle: {e}")
            return None

    async def fix_incorrectly_closed_cycles(self):
        """
        Check for cycles that are marked as closed but still have open orders in MT5.
        This fixes the issue where cycles are incorrectly marked as closed.
        """
        try:
            # Get all closed cycles from the last 24 hours
            time_24h_ago = int(time.time()) - (24 * 60 * 60)
            closed_ah_cycles = self.ah_repo.get_recently_closed_cycles(
                self.account.id, time_24h_ago)
            closed_ct_cycles = self.ct_repo.get_recently_closed_cycles(
                self.account.id, time_24h_ago)
            
            # For ACT cycles, get recently closed from PocketBase
            closed_act_cycles = []
            try:
                # Get all ACT cycles and filter for recently closed ones
                all_act_cycles = self.remote_api.get_all_ACT_active_cycles_by_account(self.account.id)
                if all_act_cycles:
                    # Filter for cycles marked as closed in the last 24 hours
                    current_time = int(time.time())
                    closed_act_cycles = [
                        cycle for cycle in all_act_cycles 
                        if getattr(cycle, 'is_closed', False) and 
                        (current_time - getattr(cycle, 'updated', current_time)) < (24 * 60 * 60)
                    ]
            except Exception as act_error:
                logger.error(f"Error getting closed ACT cycles: {act_error}")

            # Process AH cycles
            fixed_ah_count = 0
            for cycle_data in closed_ah_cycles:
                if await self.check_and_fix_closed_cycle(cycle_data, self.ah_repo, AH_cycle, "AH"):
                    fixed_ah_count += 1

            # Process CT cycles
            fixed_ct_count = 0
            for cycle_data in closed_ct_cycles:
                if await self.check_and_fix_closed_cycle(cycle_data, self.ct_repo, CT_cycle, "CT"):
                    fixed_ct_count += 1

            # Process ACT cycles
            fixed_act_count = 0
            for cycle_data in closed_act_cycles:
                if await self.check_and_fix_closed_act_cycle(cycle_data):
                    fixed_act_count += 1

            if fixed_ah_count > 0 or fixed_ct_count > 0 or fixed_act_count > 0:
                logger.info(
                    f"Fixed {fixed_ah_count} AH cycles, {fixed_ct_count} CT cycles, and {fixed_act_count} ACT cycles incorrectly marked as closed")
        except Exception as e:
            logger.error(f"Error in fix_incorrectly_closed_cycles: {e}")

    async def check_and_fix_closed_cycle(self, cycle_data, repo, cycle_class, cycle_type):
        """
        Check if a cycle still has open orders in MT5 and fix its status if needed.

        Args:
            cycle_data: The cycle data from the database
            repo: The repository for the cycle type (AH or CT)
            cycle_class: The cycle class to instantiate
            cycle_type: A string indicating the cycle type ("AH" or "CT")

        Returns:
            bool: True if the cycle was fixed, False otherwise
        """
        try:
            # Create cycle object
            cycle_obj = cycle_class(cycle_data, self.mt5, self, "db")

            # Get all order tickets from this cycle
            all_cycle_orders = cycle_obj.combine_orders()

            # Check if any orders are still open in MT5
            still_open = False
            for ticket in all_cycle_orders:
                # Check if the order is still open in MT5
                position = self.mt5.get_position_by_ticket(ticket=ticket)
                if position and len(position) > 0:
                    logger.warning(
                        f"Found open position {ticket} in MT5 for closed {cycle_type} cycle {cycle_data.id}")
                    still_open = True
                    break

                # Also check pending orders
                pending = self.mt5.get_order_by_ticket(ticket=ticket)
                if pending and len(pending) > 0:
                    logger.warning(
                        f"Found pending order {ticket} in MT5 for closed {cycle_type} cycle {cycle_data.id}")
                    still_open = True
                    break

            # If we found open orders, update the cycle status
            if still_open:
                logger.info(
                    f"Fixing {cycle_type} cycle {cycle_data.id} incorrectly marked as closed")

                # Reopen the cycle
                cycle_obj.is_closed = False
                cycle_obj.status = "open"  # Reset status to open

                # Update in database
                repo.Update_cycle(cycle_data.id, cycle_obj.to_dict())

                # Update in remote API if it has a remote ID
                if cycle_obj.cycle_id:
                    if cycle_type == "AH":
                        self.remote_api.update_AH_cycle_by_id(
                            cycle_obj.cycle_id, cycle_obj.to_remote_dict())
                    else:
                        self.remote_api.update_CT_cycle_by_id(
                            cycle_obj.cycle_id, cycle_obj.to_remote_dict())

                return True

            return False
        except Exception as e:
            logger.error(f"Error checking cycle {cycle_data.id}: {e}")
            return False

    async def check_and_fix_closed_act_cycle(self, cycle_data):
        """
        Check if an ACT cycle still has open orders in MT5 and fix its status if needed.
        
        Args:
            cycle_data: The ACT cycle data from PocketBase
            
        Returns:
            bool: True if the cycle was fixed, False otherwise
        """
        try:
            # FIXED: Get the proper bot for this cycle
            bot_for_cycle = self._get_bot_for_cycle(cycle_data)
            if bot_for_cycle is None:
                logger.error(f"Could not find bot for ACT cycle {getattr(cycle_data, 'id', 'unknown')} - skipping check")
                return False

            # Create ACT cycle object from PocketBase data
            cycle_obj = ACT_cycle(cycle_data.__dict__, self.mt5, bot_for_cycle)
            
            # Get all order tickets from this cycle
            all_cycle_orders = []
            
            # ACT cycles store orders differently - check both active and completed orders
            if hasattr(cycle_obj, 'active_orders') and cycle_obj.active_orders:
                for order in cycle_obj.active_orders:
                    if isinstance(order, dict) and 'ticket' in order:
                        all_cycle_orders.append(order['ticket'])
                    elif hasattr(order, 'ticket'):
                        all_cycle_orders.append(order.ticket)
            
            if hasattr(cycle_obj, 'completed_orders') and cycle_obj.completed_orders:
                for order in cycle_obj.completed_orders:
                    if isinstance(order, dict) and 'ticket' in order:
                        all_cycle_orders.append(order['ticket'])
                    elif hasattr(order, 'ticket'):
                        all_cycle_orders.append(order.ticket)

            # Check if any orders are still open in MT5
            still_open = False
            for ticket in all_cycle_orders:
                try:
                    ticket_int = int(ticket)
                    
                    # Check if the order is still open in MT5
                    position = self.mt5.get_position_by_ticket(ticket=ticket_int)
                    if position and len(position) > 0:
                        logger.warning(
                            f"Found open position {ticket_int} in MT5 for closed ACT cycle {cycle_data.id}")
                        still_open = True
                        break

                    # Also check pending orders
                    pending = self.mt5.get_order_by_ticket(ticket=ticket_int)
                    if pending and len(pending) > 0:
                        logger.warning(
                            f"Found pending order {ticket_int} in MT5 for closed ACT cycle {cycle_data.id}")
                        still_open = True
                        break
                except (ValueError, TypeError):
                    # Skip invalid ticket numbers
                    continue

            # If we found open orders, update the cycle status
            if still_open:
                logger.info(
                    f"Fixing ACT cycle {cycle_data.id} incorrectly marked as closed")

                # Prepare update data
                update_data = {
                    'is_closed': False,
                    'close_reason': None,
                    'status': 'active'
                }

                # Update in PocketBase
                try:
                    self.remote_api.update_ACT_cycle_by_id(cycle_data.id, update_data)
                    return True
                except Exception as update_error:
                    logger.error(f"Error updating ACT cycle {cycle_data.id}: {update_error}")
                    return False

            return False
        except Exception as e:
            logger.error(f"Error checking ACT cycle {getattr(cycle_data, 'id', 'unknown')}: {e}")
            return False

    async def run_in_thread(self):
        try:
            await self.run_cycles_manager()
        except Exception as e:
            logger.error(f"Error starting cycles_manager: {e}")
