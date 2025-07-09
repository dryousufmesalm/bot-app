import asyncio
import logging
from Orders.order import order
import time
import threading
from DB.db_engine import engine
from DB.ah_strategy.repositories.ah_repo import AHRepo
from DB.ct_strategy.repositories.ct_repo import CTRepo

from Views.globals.app_logger import app_logger as logger


class orders_manager:
    def __init__(self, mt5):
        self.mt5 = mt5
        self.ah_repo = AHRepo(engine=engine)
        self.ct_repo = CTRepo(engine=engine)
        self.suspious_ah_orders = []
        self.suspious_ct_orders = []
        self.all_mt5_orders = []
        self.all_ah_orders = []
        self.all_ct_orders = []
        self.false_closed_orders = []
        self.logger = logger
        # Add synchronization locks for MT5 operations
        self.mt5_lock = threading.Lock()
        # Add a delay between MT5 and database operations to prevent race conditions
        self.sync_delay = 0.5  # 500ms delay

    async def get_all_mt5_orders(self):
        try:
            # Use the lock when accessing MT5 API
            with self.mt5_lock:
                positions = self.mt5.get_all_positions()
                self.all_mt5_orders = []
                for position in positions:
                    self.all_mt5_orders.append(position.ticket)
                return self.all_mt5_orders
        except Exception as e:
            self.logger.error(f"Error in get_all_mt5_orders: {e}")

    async def update_ah_orders_in_db(self):
        try:
            # Create a fixed list of tasks before starting execution
            tasks = []
            # First handle active MT5 orders
            for pos in self.all_mt5_orders:
                tasks.append(self.update_single_ah_order(pos))

            # Process all active orders first
            if tasks:
                await asyncio.gather(*tasks)

            # Wait for a short delay to ensure MT5 status is fully propagated
            await asyncio.sleep(self.sync_delay)

            # Then handle suspicious orders that might be closed
            suspicious_tasks = []
            for db_order in self.suspious_ah_orders:
                suspicious_tasks.append(
                    self.update_single_suspicious_ah_order(db_order))

            if suspicious_tasks:
                await asyncio.gather(*suspicious_tasks)

        except Exception as e:
            self.logger.error(f"Error in update_ah_orders_in_db: {e}")

    async def update_single_ah_order(self, pos):
        try:
            # Get order data from database
            db_order = self.ah_repo.get_order_by_ticket(pos)
            if db_order:
                # Create a local lock scope for this specific order
                with self.mt5_lock:
                    order_obj = order(db_order, db_order.is_pending,
                                      self.mt5, self.ah_repo, "db", db_order.cycle_id)
                    # Only update order status, then wait before checking for cycles
                    updated = order_obj.update_from_mt5()

                # If order status was updated successfully, we can update the database
                if updated:
                    order_obj.update_order()

                # Check for false closed cycles with a small delay
                await asyncio.sleep(self.sync_delay / 2)
                order_obj.check_false_closed_cycles()
        except Exception as e:
            self.logger.error(f"Error in update_single_ah_order: {e}")

    async def update_single_suspicious_ah_order(self, db_order):
        try:
            # Use the lock when checking closed status in MT5
            is_closed = self.mt5.check_order_is_closed(db_order.ticket)

            # Only perform the update if definitely closed in MT5
            if is_closed:
                # Log this discrepancy for analysis
                self.logger.info(
                    f"Order {db_order.ticket} confirmed closed in MT5 but still open in DB")

                order_obj = order(db_order, db_order.is_pending,
                                  self.mt5, self.ah_repo, "db", db_order.cycle_id)
                order_obj.is_closed = is_closed

                # Additional verification with retry
                # Double-check once more before committing the change
                if self.mt5.check_order_is_closed(db_order.ticket):
                    order_obj.update_order()
                    # After updating, verify cycle status
                    await asyncio.sleep(self.sync_delay / 2)
                    order_obj.check_false_closed_cycles()
        except Exception as e:
            self.logger.error(
                f"Error in update_single_suspicious_ah_order: {e}")

    async def get_all_ah_orders_in_db(self):
        try:
            orders = self.ah_repo.get_open_orders_only()
            self.all_ah_orders = [
                entry for entry in orders if entry.account == self.mt5.account_id]
            return self.all_ah_orders
        except Exception as e:
            self.logger.error(f"Error in get_all_ah_orders_in_db: {e}")

    async def get_suspicious_ah_orders_in_db(self):
        try:
            self.suspious_ah_orders = [
                order for order in self.all_ah_orders if order.ticket not in self.all_mt5_orders]
            return self.suspious_ah_orders
        except Exception as e:
            self.logger.error(f"Error in get_suspicious_ah_orders_in_db: {e}")

    async def get_false_closed_orders(self):
        try:
            if len(self.all_ah_orders) != len(self.all_mt5_orders):
                self.false_closed_orders = [
                    order for order in self.all_ah_orders if order.ticket not in self.all_mt5_orders]
        except Exception as e:
            self.logger.error(f"Error in get_false_closed_orders: {e}")

    async def update_ct_orders_in_db(self):
        try:
            # Create a fixed list of tasks before starting execution
            tasks = []
            # First handle active MT5 orders
            for pos in self.all_mt5_orders:
                tasks.append(self.update_single_ct_order(pos))

            # Process all active orders first
            if tasks:
                await asyncio.gather(*tasks)

            # Wait for a short delay to ensure MT5 status is fully propagated
            await asyncio.sleep(self.sync_delay)

            # Then handle suspicious orders that might be closed
            suspicious_tasks = []
            for db_order in self.suspious_ct_orders:
                suspicious_tasks.append(
                    self.update_single_suspicious_ct_order(db_order))

            if suspicious_tasks:
                await asyncio.gather(*suspicious_tasks)
        except Exception as e:
            self.logger.error(f"Error in update_ct_orders_in_db: {e}")

    async def update_single_ct_order(self, pos):
        try:
            # Get order data from database
            db_order = self.ct_repo.get_order_by_ticket(pos)
            if db_order:
                # Create a local lock scope for this specific order
                with self.mt5_lock:
                    order_obj = order(db_order, db_order.is_pending,
                                      self.mt5, self.ct_repo, "db", db_order.cycle_id)
                    # Only update order status, then wait before checking for cycles
                    updated = order_obj.update_from_mt5()

                # If order status was updated successfully, we can update the database
                if updated:
                    order_obj.update_order()

                # Check for false closed cycles with a small delay
                await asyncio.sleep(self.sync_delay / 2)
                order_obj.check_false_closed_cycles()
        except Exception as e:
            self.logger.error(f"Error in update_single_ct_order: {e}")

    async def update_single_suspicious_ct_order(self, db_order):
        try:
            # Use the lock when checking closed status in MT5
            is_closed = self.mt5.check_order_is_closed(db_order.ticket)

            # Only perform the update if definitely closed in MT5
            if is_closed:
                # Log this discrepancy for analysis
                self.logger.info(
                    f"Order {db_order.ticket} confirmed closed in MT5 but still open in DB")

                order_obj = order(db_order, db_order.is_pending,
                                  self.mt5, self.ct_repo, "db", db_order.cycle_id)
                order_obj.is_closed = is_closed

                # Additional verification with retry
                # Double-check once more before committing the change
                if self.mt5.check_order_is_closed(db_order.ticket):
                    order_obj.update_order()
                    # After updating, verify cycle status
                    await asyncio.sleep(self.sync_delay / 2)
                    order_obj.check_false_closed_cycles()
        except Exception as e:
            self.logger.error(
                f"Error in update_single_suspicious_ct_order: {e}")

    async def get_all_ct_orders_in_db(self):
        try:
            orders = self.ct_repo.get_open_orders_only()
            self.all_ct_orders = [
                entry for entry in orders if entry.account == self.mt5.account_id]
            return self.all_ct_orders
        except Exception as e:
            self.logger.error(f"Error in get_all_ct_orders_in_db: {e}")

    async def get_suspicious_ct_orders_in_db(self):
        try:
            self.suspious_ct_orders = [
                order for order in self.all_ct_orders if order.ticket not in self.all_mt5_orders]
            return self.suspious_ct_orders
        except Exception as e:
            self.logger.error(f"Error in get_suspicious_ct_orders_in_db: {e}")

    async def run_orders_manager(self):
        while True:
            try:
                # Add more detailed logging to help diagnose issues
                self.logger.debug("Starting order sync cycle")

                # Get orders from MT5 first
                await self.get_all_mt5_orders()
                self.logger.debug(
                    f"Found {len(self.all_mt5_orders)} orders in MT5")

                # Brief delay to ensure MT5 data is stable
                await asyncio.sleep(self.sync_delay / 2)

                # Get orders from database
                await self.get_all_ah_orders_in_db()
                await self.get_suspicious_ah_orders_in_db()
                self.logger.debug(
                    f"Found {len(self.all_ah_orders)} AH orders in DB, {len(self.suspious_ah_orders)} suspicious")

                # Get CT orders
                await self.get_all_ct_orders_in_db()
                await self.get_suspicious_ct_orders_in_db()
                self.logger.debug(
                    f"Found {len(self.all_ct_orders)} CT orders in DB, {len(self.suspious_ct_orders)} suspicious")

                # Update orders with a delay between strategies
                await self.update_ah_orders_in_db()
                await asyncio.sleep(self.sync_delay)
                await self.update_ct_orders_in_db()

                # Longer delay between full sync cycles to prevent overloading
                await asyncio.sleep(1)

                self.logger.debug("Completed order sync cycle")
            except Exception as e:
                self.logger.error(f"Error in run_orders_manager: {e}")
                # Add a longer delay after error to prevent rapid retry loops
                await asyncio.sleep(5)

    async def run_in_thread(self):
        try:
            await self.run_orders_manager()
        except Exception as e:
            logger.error(f"Error starting orders_manager: {e}")
