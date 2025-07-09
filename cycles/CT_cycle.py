import datetime
from Orders.order import order
import MetaTrader5 as Mt5
from DB.db_engine import engine
from DB.ct_strategy.repositories.ct_repo import CTRepo
from types import SimpleNamespace
import json
from helpers.sync import verify_order_status, sync_delay, MT5_LOCK


class cycle:
    def __init__(self, data, mt5, bot, source=None):
        if data is None:
            raise ValueError("Cannot initialize CTcycle with None data")

        # Helper function to safely get attributes
        def safe_get(obj, attr, default=None):
            if source == "db":
                value = getattr(obj, attr, default)
            elif source == "remote":
                value = getattr(obj, attr, default)
            else:
                value = obj.get(attr, default)

            # Special handling for done_price_levels to ensure it's always a list
            if attr == "done_price_levels":
                # If it's a dictionary (from PocketBase), convert to empty list
                if isinstance(value, dict):
                    return []
                # If it's a JSON string, parse it
                elif isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        return [] if isinstance(parsed, dict) else parsed
                    except:
                        return []
                # Make sure it's a list
                elif value is None:
                    return []

            return value

        self.bot_id = safe_get(data, "bot", "")
        self.initial = safe_get(data, "initial", [])
        self.hedge = safe_get(data, "hedge", [])
        self.recovery = safe_get(data, "recovery", [])
        self.pending = safe_get(data, "pending", [])
        self.closed = safe_get(data, "closed", [])
        self.threshold = safe_get(data, "threshold", [])
        self.is_closed = safe_get(data, "is_closed", False)
        self.lower_bound = safe_get(data, "lower_bound", 0)
        self.upper_bound = safe_get(data, "upper_bound", 0)
        self.lot_idx = safe_get(data, "lot_idx", 0)
        self.zone_index = safe_get(data, "zone_index", 0)
        self.status = safe_get(data, "status", "")
        self.symbol = safe_get(data, "symbol", "")
        self.total_profit = safe_get(data, "total_profit", 0)
        self.total_volume = safe_get(data, "total_volume", 0)
        self.closing_method = safe_get(data, "closing_method", {})
        self.opened_by = safe_get(data, "opened_by", {})
        self.account = safe_get(data, "account", "")

        # Handle cycle_id
        self.cycle_id = safe_get(data, "id", "")
        self.is_pending = safe_get(data, "is_pending", False)

        self.local_api = CTRepo(engine=engine)
        self.mt5 = mt5
        self.bot = bot

        self.threshold_upper = safe_get(
            data, "threshold_upper", 0) if source == "db" else safe_get(data, "threshold_top", 0)
        self.threshold_lower = safe_get(
            data, "threshold_lower", 0) if source == "db" else safe_get(data, "threshold_bottom", 0)
        self.cycle_type = safe_get(data, "cycle_type", "")

        # Safely handle orders
        if source == 'remote':
            orders_data = safe_get(data, "orders", {})
            if isinstance(orders_data, dict):
                orders_list = orders_data.get("orders", [])
                self.orders = self.get_orders_from_remote(orders_list)
            else:
                self.orders = []
        else:
            self.orders = self.combine_orders()

        # Calculate open price safely
        self.open_price = 0
        if len(self.initial) > 0:
            initial_order = self.local_api.get_order_by_ticket(self.initial[0])
            if initial_order:
                self.open_price = initial_order.open_price

        self.base_threshold_lower = safe_get(
            data, "base_threshold_lower", self.threshold_lower)
        self.base_threshold_upper = safe_get(
            data, "base_threshold_upper", self.threshold_upper)
        self.buyLots = 0
        self.sellLots = 0

        # New fields for zone forward threshold order system
        self.done_price_levels = safe_get(data, "done_price_levels", [])
        self.current_direction = safe_get(data, "current_direction", "BUY")
        self.initial_threshold_price = safe_get(
            data, "initial_threshold_price", self.open_price)
        self.direction_switched = safe_get(data, "direction_switched", False)
        self.next_order_index = safe_get(data, "next_order_index", 0)

    def combine_orders(self):
        return self.initial + self.hedge + self.pending + self.recovery + self.threshold

    def get_orders_from_remote(self, orders):
        if orders is None:
            return []

        result = []
        for order_data in orders:
            try:
                if order_data is None:
                    continue

                # Convert order data to subscriptable object
                order_obj = order(SimpleNamespace(order_data),
                                  self.is_pending, self.mt5, self.local_api, "db")
                order_obj.create_order()

                # Add the order to the appropriate list based on its kind
                order_kind = order_obj.kind
                order_ticket = order_obj.ticket
                result.append(order_ticket)

                if order_kind == "initial":
                    self.remove_initial_order(order_ticket)
                elif order_kind == "hedge":
                    self.remove_hedge_order(order_ticket)
                elif order_kind == "recovery":
                    self.remove_recovery_order(order_ticket)
                elif order_kind == "pending":
                    self.remove_pending_order(order_ticket)
                elif order_kind == "threshold":
                    self.remove_threshold_order(order_ticket)
            except Exception as e:
                print(f"Error processing order from remote: {e}")

        return result

    def to_dict(self):
        data = {

            "bot": self.bot_id,
            "account": self.account,
            "is_pending": self.is_pending,
            "is_closed": self.is_closed,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "lot_idx": self.lot_idx,
            "zone_index": self.zone_index,
            "status": self.status,
            "symbol": self.symbol,
            "total_profit": self.total_profit,
            "total_volume": self.total_volume,
            "closing_method": self.closing_method,
            "initial": self.initial,
            "hedge": self.hedge,
            "pending": self.pending,
            "closed": self.closed,
            "recovery": self.recovery,
            "threshold": self.threshold,
            "opened_by": self.opened_by,
            "id": self.cycle_id,
            "threshold_upper": round(float(self.threshold_upper), 2),
            "threshold_lower": round(float(self.threshold_lower), 2),
            "base_threshold_lower": round(float(self.base_threshold_lower), 2),
            "base_threshold_upper": round(float(self.base_threshold_upper), 2),
            "cycle_type": self.cycle_type,
            # New fields for zone forward
            "done_price_levels": self.done_price_levels,
            "current_direction": self.current_direction,
            "initial_threshold_price": self.initial_threshold_price,
            "direction_switched": self.direction_switched,
            "next_order_index": self.next_order_index

        }

        return data
    # create cycle  data to  send to remote server

    def to_remote_dict(self):
        data = {
            "bot": self.bot_id,
            "account": self.account,
            "is_pending": self.is_pending,
            "is_closed": self.is_closed,
            "lower_bound": round(self.lower_bound, 2),
            "upper_bound": round(self.upper_bound, 2),
            "lot_idx": self.lot_idx,
            "zone_index": self.zone_index,
            "status": self.status,
            "symbol": self.symbol,
            "total_profit": round(float(self.total_profit), 2),
            "total_volume": round(float(self.total_volume), 2),
            "closing_method": self.closing_method,
            "orders": {
                "orders": []},
            "opened_by": self.opened_by,
            "cycle_type": self.cycle_type,
            "threshold_top": round(float(self.threshold_upper), 2),
            "threshold_bottom": round(float(self.threshold_lower), 2),
            # New fields for zone forward
            "done_price_levels": self.done_price_levels,
            "current_direction": self.current_direction,
            "initial_threshold_price": self.initial_threshold_price,
            "direction_switched": self.direction_switched,
            "next_order_index": self.next_order_index

        }
        #  go through the orders and add them to the data
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.mt5, self.local_api, "db", self.id)
            data["orders"]["orders"].append(order_obj.to_dict())

        for order_ticket in self.closed:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.mt5, self.local_api, "db", self.id)
            data["orders"]["orders"].append(order_obj.to_dict())
        return data
    # add  initial order

    def add_initial_order(self, order_ticket):

        self.initial.append(order_ticket)
        self.status = "initial"
    # add hedge order

    def add_hedge_order(self, order_ticket):
        self.hedge.append(order_ticket)
        self.status = "hedge"
    # add recovery order

    def add_recovery_order(self, order_ticket):
        self.recovery.append(order_ticket)
        self.status = "recovery"
    # add pending order

    def add_pending_order(self, order_ticket):
        self.pending.append(order_ticket)
        self.status = "pending"
    #  add thresholds order

    def add_threshold_order(self, order_ticket):
        self.threshold.append(order_ticket)
        self.status = "threshold"
    # remove pending order from pending

    def remove_pending_order(self, order_ticket):
        if order_ticket in self.pending:
            self.pending.remove(order_ticket)

    # remove initial order from initial list
    def remove_initial_order(self, order_ticket):
        if order_ticket in self.initial:
            self.initial.remove(order_ticket)

    # remove hedge order from hedge list
    def remove_hedge_order(self, order_ticket):
        if order_ticket in self.hedge:
            self.hedge.remove(order_ticket)

    # remove recovery order from recovery list
    def remove_recovery_order(self, order_ticket):
        if order_ticket in self.recovery:
            self.recovery.remove(order_ticket)

    # remove threshold order from  list\
    def remove_threshold_order(self, order_ticket):
        if order_ticket in self.threshold:
            self.threshold.remove(order_ticket)

    # update cylce orders
    async def update_cycle(self, remote_api):
        self.total_profit = 0
        self.total_volume = 0
        self.sellLots = 0
        self.buyLots = 0

        # Process all non-closed orders first to get current profit and volume
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            if order_data and not order_data.is_closed:
                # Add to profit/volume calculations for active orders
                self.total_profit += order_data.profit+order_data.swap+order_data.commission
                self.total_volume += order_data.volume

                if order_data.type == Mt5.ORDER_TYPE_SELL:
                    self.sellLots += order_data.volume
                elif order_data.type == Mt5.ORDER_TYPE_BUY:
                    self.buyLots += order_data.volume

                # Handle pending order conversion
                if not order_data.is_pending and order_ticket in self.pending:
                    self.remove_pending_order(order_ticket)
                    self.add_initial_order(order_ticket)
                    self.is_pending = False
                    self.status = "initial"

        # Process potentially closed orders separately with careful verification
        orders_to_process = []
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            if order_data:
                # Check if order is closed in database or not found in active MT5 positions/orders
                # Instead of using self.all_mt5_orders which doesn't exist, check directly with MT5
                positions = self.mt5.get_position_by_ticket(
                    ticket=order_ticket)
                pending_orders = self.mt5.get_order_by_ticket(
                    ticket=order_ticket)
                is_active_in_mt5 = (positions is not None and len(positions) > 0) or (
                    pending_orders is not None and len(pending_orders) > 0)

                if order_data.is_closed or not is_active_in_mt5:
                    orders_to_process.append((order_ticket, order_data))

        # Process closed orders with careful verification
        for order_ticket, order_data in orders_to_process:
            # Create order object for verification
            order_obj = order(order_data, order_data.is_pending,
                              self.mt5, self.local_api, "db", self.id)

            # Verify order status with multiple checks for consistency
            is_open, is_closed, is_pending = await verify_order_status(self.mt5, order_ticket)

            # Update the state based on verification results
            if is_closed:
                # Order is truly closed
                if order_data.kind == "initial":
                    self.remove_initial_order(order_ticket)
                elif order_data.kind == "hedge":
                    self.remove_hedge_order(order_ticket)
                elif order_data.kind == "recovery":
                    self.remove_recovery_order(order_ticket)
                elif order_data.kind == "pending":
                    if order_ticket in self.pending:
                        self.remove_pending_order(order_ticket)
                    if order_ticket in self.initial:
                        self.remove_initial_order(order_ticket)
                elif order_data.kind == "threshold":
                    self.remove_threshold_order(order_ticket)

                # Add to closed list if not already there
                if order_ticket not in self.closed:
                    # Check if order was closed with a loss, if so mark the price level as "done"
                    if order_data.profit < 0:
                        direction = "BUY" if order_data.type == Mt5.ORDER_TYPE_BUY else "SELL"
                        self.mark_price_level_as_done(
                            order_data.open_price, direction)

                    self.closed.append(order_ticket)

                # Update order status in database if needed
                if not order_data.is_closed:
                    order_obj.is_closed = True
                    order_obj.update_order()

            else:
                # Order is actually open - fix the database
                if order_data.is_closed:
                    # Fix incorrect closed status
                    print(
                        f"Fixing incorrect closed status for order {order_ticket}")
                    order_obj.is_closed = False
                    order_obj.update_order()

                    # Remove from closed list if present
                    if order_ticket in self.closed:
                        self.closed.remove(order_ticket)

        # Process closed orders profit after verifying all statuses
        for order_ticket in self.closed:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            if (order_data and order_data.kind != "pending" and order_data.kind != "initial") or (self.bot.ADD_All_to_PNL == True):
                self.total_profit += order_data.profit+order_data.swap+order_data.commission

        # Handle pending state transitions
        if len(self.pending) == 0 and self.is_pending is True:
            self.is_pending = False
            self.status = "initial"

        # Handle BUY&SELL specific logic
        if len(self.pending) == 0 and len(self.initial) == 1 and self.status == "initial" and self.cycle_type == "BUY&SELL" and len(self.orders) == 1 and len(self.closed) == 0:
            # Close the pending order and open it as market order
            order_data = self.local_api.get_order_by_ticket(self.initial[0])
            order_obj = order(order_data, order_data.is_pending,
                              self.mt5, self.local_api, "db", self.id)

            # Use lock for MT5 operations
            with MT5_LOCK:
                new_order = self.mt5.sell(
                    self.symbol, order_obj.volume, self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "initial")

            if new_order:
                self.add_initial_order(new_order[0].ticket)
                new_order_obj = order(
                    new_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                new_order_obj.create_order()

        # Directly check with MT5 if any orders are still open
        any_still_open = False
        all_order_tickets = self.initial + self.hedge + \
            self.pending + self.recovery + self.threshold
        for ticket in all_order_tickets:
            positions = self.mt5.get_position_by_ticket(ticket=ticket)
            pending_orders = self.mt5.get_order_by_ticket(ticket=ticket)
            if (positions is not None and len(positions) > 0) or (pending_orders is not None and len(pending_orders) > 0):
                any_still_open = True
                break

        # Only close cycle if all orders are truly closed (verified with MT5)
        if len(self.orders) == 0 and not any_still_open:
            self.status = "closed"
            self.is_closed = True
            self.closing_method["sent_by_admin"] = False
            self.closing_method["status"] = "MetaTrader5"
            self.closing_method["username"] = "MetaTrader5"

            # Add delay before remote update to ensure consistency
            await sync_delay(0.2)
            remote_api.update_CT_cycle_by_id(
                self.cycle_id, self.to_remote_dict())
        elif any_still_open and self.is_closed:
            # If marked as closed but has open orders, fix it
            self.is_closed = False
            self.status = "open"
            print(f"Fixed cycle {self.id} incorrectly marked as closed")

        # Save cycle state
        self.local_api.Update_cycle(self.id, self.to_dict())
    # create a new cycle

    def create_cycle(self):
        self.orders = self.combine_orders()
        cycle_data = self.local_api.create_cycle(self.to_dict())
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_objec = order(order_data, order_data.is_pending,
                                self.mt5, self.local_api, "db", cycle_data.id)
            order_objec.update_order()
        return cycle_data
    # close cycle

    def close_cycle(self, sent_by_admin, user_id, username):
        # Always get the latest orders, including threshold orders
        self.orders = self.combine_orders()

        # if cycle is not closed, close it and return True
        for order_id in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_id)
            if order_data:
                orderobj = order(order_data, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                if orderobj.close_order() is False:
                    return False

        self.is_closed = True
        self.status = "closed"
        self.closing_method["sent_by_admin"] = sent_by_admin
        if user_id == 0:
            self.closing_method["status"] = "MetaTrader5"
            self.closing_method["username"] = "MetaTrader5"
        else:
            self.closing_method["user_id"] = user_id
            self.closing_method["status"] = "closed by User"
        self.closing_method["username"] = username
        self.local_api.Update_cycle(self.id, self.to_dict())

        return True

    async def manage_cycle_orders(self, threshold, threshold2):
        if self.is_pending:
            return
        if self.is_closed:
            return

        # Store initial price as threshold price if not set
        if self.initial_threshold_price == 0 and len(self.initial) > 0:
            order_data = self.local_api.get_order_by_ticket(self.initial[0])
            if order_data:
                self.initial_threshold_price = order_data.open_price
                self.update_CT_cycle()

        # Check for direction switch based on lost orders
        self.check_direction_switch()

        ask = self.mt5.get_ask(self.symbol)
        bid = self.mt5.get_bid(self.symbol)

        # Original cycle management logic for initial status
        if self.status == "initial":
            # Check if the cycle is in the initial phase
            if (self.cycle_type == "BUY"):
                if len(self.hedge) == 0:
                    if bid < self.open_price-self.bot.hedge_sl*self.mt5.get_pips(self.symbol):
                        self.hedge_buy_order()
            if (self.cycle_type == "SELL"):
                if len(self.hedge) == 0:
                    if ask > self.open_price+self.bot.hedge_sl*self.mt5.get_pips(self.symbol):
                        self.hedge_sell_order()
            if ask > self.upper_bound:
                total_sell = self.count_initial_sell_orders()
                if total_sell >= 1:
                    self.base_threshold_lower = self.open_price - \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_lower = self.base_threshold_lower
                    self.base_threshold_upper = self.upper_bound + \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_upper = self.base_threshold_upper
                    self.close_initial_buy_orders()
                    self.status = "recovery"
                    self.hedge_sell_order()
                    self.recovery_sell_order()
                    self.update_CT_cycle()
                else:
                    self.status = "recovery"
                    self.base_threshold_lower = self.open_price - \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_lower = self.base_threshold_lower
                    self.base_threshold_upper = self.upper_bound + \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_upper = self.base_threshold_upper
            elif bid < self.lower_bound:
                total_buy = self.count_initial_buy_orders()
                if total_buy >= 1:
                    self.close_initial_sell_orders()
                    self.base_threshold_lower = self.lower_bound - \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_lower = self.base_threshold_lower
                    self.base_threshold_upper = self.open_price + \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_upper = self.base_threshold_upper
                    self.status = "recovery"
                    self.hedge_buy_order()
                    self.recovery_buy_order()
                    self.update_CT_cycle()
                else:
                    self.status = "recovery"
                    self.base_threshold_lower = self.lower_bound - \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_lower = self.base_threshold_lower
                    self.base_threshold_upper = self.open_price + \
                        threshold * self.mt5.get_pips(self.symbol)
                    self.threshold_upper = self.base_threshold_upper

        elif self.status in ["recovery", "max_recovery"]:
            self.go_hedge_direction()

            # Zone forward threshold ordering logic
            if self.current_direction == "BUY":
                # When in BUY mode, check if we should place a new buy order at threshold upper
                if ask >= self.threshold_upper and len(self.hedge) > 0:
                    next_price_level = self.threshold_upper + \
                        threshold2 * self.mt5.get_pips(self.symbol)

                    # # Only place the order if this price level hasn't been marked as "done"
                    # if not self.should_skip_price_level(next_price_level, "BUY"):
                    lot_size_index = min(self.next_order_index, len(
                        self.bot.lot_sizes) - 1) if hasattr(self.bot, 'lot_sizes') else 0
                    self.threshold_buy_order(
                        next_price_level, lot_size_index)
                    self.next_order_index = min(self.next_order_index + 1, len(
                        self.bot.lot_sizes) - 1) if hasattr(self.bot, 'lot_sizes') else 0

            elif self.current_direction == "SELL":
                # When in SELL mode, check if we should place a new sell order at threshold lower
                if bid <= self.threshold_lower and len(self.hedge) > 0:
                    next_price_level = self.threshold_lower - \
                        threshold2 * self.mt5.get_pips(self.symbol)

                    # # Only place the order if this price level hasn't been marked as "done"
                    # if not self.should_skip_price_level(next_price_level, "SELL"):
                    lot_size_index = min(self.next_order_index, len(
                        self.bot.lot_sizes) - 1) if hasattr(self.bot, 'lot_sizes') else 0
                    self.threshold_sell_order(
                        next_price_level, lot_size_index)
                    self.next_order_index = min(self.next_order_index + 1, len(
                        self.bot.lot_sizes) - 1) if hasattr(self.bot, 'lot_sizes') else 0

            # Reposition thresholds based on existing orders
            self.threshold_Reposition(threshold2)

    def close_initial_buy_orders(self):
        total_initial = len(self.initial)
        if total_initial > 1:
            for i in range(total_initial):
                ticket = self.initial[i]
                order_data_db = self.local_api.get_order_by_ticket(ticket)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                if orderobj.type == Mt5.ORDER_TYPE_BUY:
                    orderobj.close_order()
                    self.initial.pop(i)
                    self.closed.append(ticket)
                    break

    def threshold_Reposition(self, threshold):
        buy_n = 0
        sell_n = 0
        for order_ticket in self.threshold:
            order_data_db = self.local_api.get_order_by_ticket(order_ticket)
            orderobj = order(order_data_db, self.is_pending,
                             self.mt5, self.local_api, "db", self.id)
            if orderobj.type == Mt5.ORDER_TYPE_SELL:
                self.threshold_lower = orderobj.open_price - threshold * \
                    self.mt5.get_pips(self.symbol)
                sell_n += 1
            if orderobj.type == Mt5.ORDER_TYPE_BUY:
                self.threshold_upper = orderobj.open_price+threshold * \
                    self.mt5.get_pips(self.symbol)
                buy_n += 1
        if sell_n == 0:

            self.threshold_lower = self.base_threshold_lower
        if buy_n == 0:
            self.threshold_upper = self.base_threshold_upper

    def close_initial_sell_orders(self):
        total_sells = len(self.initial)
        if total_sells > 1:
            for i in range(total_sells):
                ticket = self.initial[i]
                order_data_db = self.local_api.get_order_by_ticket(ticket)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                if orderobj.type == Mt5.ORDER_TYPE_SELL:
                    orderobj.close_order()
                    self.initial.pop(i)
                    self.closed.append(ticket)
                    break

    def count_initial_sell_orders(self):
        total_sell = 0
        for ticket in self.initial:
            order_data_db = self.local_api.get_order_by_ticket(ticket)
            orderobj = order(order_data_db, self.is_pending,
                             self.mt5, self.local_api, "db", self.id)
            if orderobj.type == Mt5.ORDER_TYPE_SELL:
                total_sell += 1
        return total_sell

    def count_initial_buy_orders(self):
        total_buy = 0
        for ticket in self.initial:
            order_data_db = self.local_api.get_order_by_ticket(ticket)
            orderobj = order(order_data_db, self.is_pending,
                             self.mt5, self.local_api, "db", self.id)
            if orderobj.type == Mt5.ORDER_TYPE_BUY:
                total_buy += 1
        return total_buy

    def hedge_buy_order(self):
        self.orders = self.combine_orders()
        self.sellLots = 0
        self.buyLots = 0
        for order_ticket in self.initial:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            if order_data:
                if order_data.type == Mt5.ORDER_TYPE_SELL:
                    self.sellLots += order_data.volume
                elif order_data.type == Mt5.ORDER_TYPE_BUY:
                    self.buyLots += order_data.volume
        hedge_lot = self.buyLots-self.sellLots

        if hedge_lot <= 0 or len(self.hedge) > 0:
            return
        hedge_order = self.mt5.sell(
            self.symbol, hedge_lot, self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "hedge")
        self.zone_index = min(self.zone_index + 1, len(self.bot.zones) - 1)
        if len(hedge_order) > 0:
            # add the order to the hedge list
            self.hedge.append(hedge_order[0].ticket)
            # create a new order
            order_obj = order(
                hedge_order[0], False, self.mt5, self.local_api, "mt5", self.id)
            order_obj.create_order()
            if self.status != "initial":
                self.lower_bound = float(hedge_order[0].price_open) - float(
                    self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))
                self.upper_bound = float(hedge_order[0].price_open) + float(
                    self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))

        # update the upper and lower by the zone index
    def recovery_buy_order(self):
        if self.bot.enable_recovery:
            recovery_order = self.mt5.buy(
                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "recovery")
            if len(recovery_order) > 0:
                self.recovery.append(recovery_order[0].ticket)
                # create a new order
                order_obj = order(
                    recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                order_obj.create_order()

    def threshold_buy_order(self, threshold, lot_index=0):
        lot_idx = lot_index if hasattr(self.bot, 'lot_sizes') else 0
        lot_size = self.bot.lot_sizes[lot_idx] if hasattr(
            self.bot, 'lot_sizes') and lot_idx < len(self.bot.lot_sizes) else self.bot.lot_sizes[0]

        threshold_order = self.mt5.buy(
            self.symbol, lot_size, self.bot.bot.magic, self.bot.hedges_numbers, 0, "PIPS", self.bot.slippage, "threshold")
        if len(threshold_order) > 0:
            # add the order to the threshold list
            self.threshold_upper = threshold
            self.threshold.append(threshold_order[0].ticket)
            # create a new order
            order_obj = order(
                threshold_order[0], False, self.mt5, self.local_api, "mt5", self.id)
            order_obj.create_order()

    def threshold_sell_order(self, threshold, lot_index=0):
        lot_idx = lot_index if hasattr(self.bot, 'lot_sizes') else 0
        lot_size = self.bot.lot_sizes[lot_idx] if hasattr(
            self.bot, 'lot_sizes') and lot_idx < len(self.bot.lot_sizes) else self.bot.lot_sizes[0]

        threshold_order = self.mt5.sell(
            self.symbol, lot_size, self.bot.bot.magic, self.bot.hedges_numbers, 0, "PIPS", self.bot.slippage, "threshold")
        if len(threshold_order) > 0:
            # add the order to the threshold list
            self.threshold_lower = threshold
            self.threshold.append(threshold_order[0].ticket)
            # create a new order
            order_obj = order(
                threshold_order[0], False, self.mt5, self.local_api, "mt5", self.id)
            order_obj.create_order()

    def hedge_sell_order(self):
        self.orders = self.combine_orders()

        self.sellLots = 0
        self.buyLots = 0
        for order_ticket in self.initial:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            if order_data:
                if order_data.type == Mt5.ORDER_TYPE_SELL:
                    self.sellLots += order_data.volume
                elif order_data.type == Mt5.ORDER_TYPE_BUY:
                    self.buyLots += order_data.volume

        hedge_lot = self.sellLots-self.buyLots

        # hedge order
        if hedge_lot <= 0 or len(self.hedge) > 0:
            return
        hedge_order = self.mt5.buy(
            self.symbol, hedge_lot, self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "hedge")
        self.zone_index = min(self.zone_index + 1, len(self.bot.zones) - 1)
        if len(hedge_order) > 0:
            # add the order to the hedge list
            self.hedge.append(hedge_order[0].ticket)
            # create a new order
            order_obj = order(
                hedge_order[0], False, self.mt5, self.local_api, "mt5", self.id)
            order_obj.create_order()
            # update the upper and lower by the zone index
            if self.status != "initial":
                self.lower_bound = float(hedge_order[0].price_open) - float(
                    self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))
                self.upper_bound = float(hedge_order[0].price_open) + float(
                    self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))

    def recovery_sell_order(self):
        # recovery order
        if self.bot.enable_recovery:
            recovery_order = self.mt5.sell(
                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "recovery")
            if len(recovery_order) > 0:
                self.recovery.append(recovery_order[0].ticket)
                # create a new order
                order_obj = order(
                    recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                order_obj.create_order()

    def go_opposite_direction(self):
        # check recovery order length
        if len(self.recovery) < 1:
            return
        if len(self.recovery) > 0:
            ask = self.mt5.get_ask(self.symbol)
            bid = self.mt5.get_bid(self.symbol)
            if ask > self.upper_bound:
                self.close_recovery_orders()
                self.hedge_sell_order()
                self.recovery_sell_order()
            elif bid < self.lower_bound:
                self.close_recovery_orders()
                self.hedge_buy_order()
                self.recovery_buy_order()

    def close_recovery_orders(self):
        for ticket in self.recovery:
            order_data_db = self.local_api.get_order_by_ticket(ticket)
            orderobj = order(order_data_db, self.is_pending,
                             self.mt5, self.local_api, "db", self.id)
            orderobj.close_order()
            orderobj.is_closed = True
            orderobj.update_order()
            self.recovery.remove(ticket)
            self.closed.append(ticket)

    def go_hedge_direction(self):
        if len(self.hedge) > 0:
            ask = self.mt5.get_ask(self.symbol)
            bid = self.mt5.get_bid(self.symbol)
            if ask > self.upper_bound:
                last_hedge = self.hedge[-1]
                order_data_db = self.local_api.get_order_by_ticket(last_hedge)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                last_hedge_type = orderobj.type
                last_hedge_profit = orderobj.profit
                # if last_hedge_type == Mt5.ORDER_TYPE_SELL and last_hedge_profit < 0:
                if (len(self.recovery) > 0):
                    last_recovery = self.recovery[-1]
                    order_data_recovery_db = self.local_api.get_order_by_ticket(
                        last_recovery)
                    if (order_data_recovery_db.type == Mt5.ORDER_TYPE_SELL):
                        return
                self.close_recovery_orders()
                self.hedge_sell_order()
                self.recovery_sell_order()
            elif bid < self.lower_bound:
                last_hedge = self.hedge[-1]
                order_data_db = self.local_api.get_order_by_ticket(last_hedge)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                last_hedge_type = orderobj.type
                last_hedge_profit = orderobj.profit
                # if last_hedge_type == Mt5.ORDER_TYPE_BUY and last_hedge_profit < 0:
                if (len(self.recovery) > 0):
                    last_recovery = self.recovery[-1]
                    order_data_recovery_db = self.local_api.get_order_by_ticket(
                        last_recovery)
                    if (order_data_recovery_db.type == Mt5.ORDER_TYPE_BUY):
                        return
                self.close_recovery_orders()
                self.hedge_buy_order()
                self.recovery_buy_order()

    def update_CT_cycle(self):
        self.local_api.Update_cycle(self.id, self.to_dict())
    #  close   cycle when hits  takeprofit

    async def close_cycle_on_takeprofit(self, take_profit, remote_api):
        self.update_CT_cycle()
        if self.total_profit >= take_profit:
            self.is_pending = False
            self.is_closed = True
            self.close_cycle(False, 0, "MetaTrader5")
            remote_api.update_CT_cycle_by_id(
                self.cycle_id, self.to_remote_dict())

    # New methods for zone forward threshold order system
    def mark_price_level_as_done(self, price_level, direction):
        """Mark a price level as done (where an order was lost)"""
        done_level = {
            "price": price_level,
            "direction": direction
        }

        # Check if this price level is already marked as done
        for level in self.done_price_levels:
            if abs(level["price"] - price_level) < self.mt5.get_pips(self.symbol) * 0.5 and level["direction"] == direction:
                return

        self.done_price_levels.append(done_level)
        self.update_CT_cycle()

    def should_skip_price_level(self, price_level, direction):
        """Check if a price level should be skipped because it's marked as done"""
        for done_level in self.done_price_levels:
            price_diff = abs(done_level["price"] - price_level)
            min_diff = self.mt5.get_pips(
                self.symbol) * 0.5  # Half pip tolerance

            if price_diff <= min_diff and done_level["direction"] == direction:
                return True

        return False

    def check_direction_switch(self, significant_drop_pips=200):
        """Check if direction should be switched from BUY to SELL or vice versa"""
        if self.is_closed:
            return

        # Check if all buy orders are lost when in BUY mode
        if self.current_direction == "BUY":
            all_buy_orders_lost = True
            for order_id in self.initial + self.hedge + self.threshold:
                order_data = self.local_api.get_order_by_ticket(order_id)
                if order_data and order_data.type == Mt5.ORDER_TYPE_BUY and not order_data.is_closed:
                    all_buy_orders_lost = False
                    break

            if all_buy_orders_lost:
                # Get current price
                current_price = self.mt5.get_bid(self.symbol)
                # If price dropped significantly below initial price
                significant_drop = significant_drop_pips * \
                    self.mt5.get_pips(self.symbol)

                if self.initial_threshold_price > 0 and current_price < (self.initial_threshold_price - significant_drop):
                    self.current_direction = "SELL"
                    self.direction_switched = True
                    # Continue with next lot size index
                    if hasattr(self.bot, 'lot_sizes') and self.next_order_index < len(self.bot.lot_sizes) - 1:
                        self.next_order_index += 1
                    self.update_CT_cycle()

        # Check if all sell orders are lost when in SELL mode
        elif self.current_direction == "SELL":
            all_sell_orders_lost = True
            for order_id in self.initial + self.hedge + self.threshold:
                order_data = self.local_api.get_order_by_ticket(order_id)
                if order_data and order_data.type == Mt5.ORDER_TYPE_SELL and not order_data.is_closed:
                    all_sell_orders_lost = False
                    break

            if all_sell_orders_lost:
                # Get current price
                current_price = self.mt5.get_ask(self.symbol)
                # If price rose significantly above initial price
                significant_rise = significant_drop_pips * \
                    self.mt5.get_pips(self.symbol)

                if self.initial_threshold_price > 0 and current_price > (self.initial_threshold_price + significant_rise):
                    self.current_direction = "BUY"
                    self.direction_switched = True
                    # Continue with next lot size index
                    if hasattr(self.bot, 'lot_sizes') and self.next_order_index < len(self.bot.lot_sizes) - 1:
                        self.next_order_index += 1
                    self.update_CT_cycle()
