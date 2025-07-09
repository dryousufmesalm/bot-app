import datetime
from Orders.order import order
import MetaTrader5 as Mt5
from DB.db_engine import engine
from DB.ah_strategy.repositories.ah_repo import AHRepo
from types import SimpleNamespace
from helpers.sync import verify_order_status, sync_delay, MT5_LOCK


class cycle:
    def __init__(self, data, mt5, bot, source=None):
        self.bot_id = data.bot if source in ("db", "remote") else data["bot"]
        self.initial = data.initial if source == "db" else [
        ] if source == "remote" else data["initial"]
        self.hedge = data.hedge if source == "db" else [
        ] if source == "remote" else data["hedge"]
        self.recovery = data.recovery if source == "db" else [
        ] if source == "remote" else data["recovery"]
        self.pending = data.pending if source == "db" else [
        ] if source == "remote" else data["pending"]
        self.closed = data.closed if source == "db" else [
        ] if source == "remote" else data["closed"]
        self.max_recovery = data.max_recovery if source == "db" else [
        ] if source == "remote" else data["max_recovery"]
        self.is_closed = data.is_closed if source in (
            "db", "remote") else data['is_closed']
        self.lower_bound = data.lower_bound if source in (
            "db", "remote") else data['lower_bound']
        self.upper_bound = data.upper_bound if source in (
            "db", "remote") else data['upper_bound']
        self.lot_idx = data.lot_idx if source in (
            "db", "remote") else data['lot_idx']
        self.zone_index = data.zone_index if source == "db" else 0 if source == "remote" else data[
            'zone_index']
        self.status = data.status if source in (
            "db", "remote") else data['status']
        self.symbol = data.symbol if source in (
            "db", "remote") else data['symbol']
        self.total_profit = data.total_profit if source in (
            "db", "remote") else data['total_profit']
        self.total_volume = data.total_volume if source in (
            "db", "remote") else data['total_volume']
        self.closing_method = data.closing_method if source in (
            "db", "remote") else data['closing_method']
        self.opened_by = data.opened_by if source in (
            "db", "remote") else data['opened_by']
        self.account = data.account if source in (
            "db", "remote") else data['account']
        self.cycle_id = data.id if source in ("db", "remote") else ""
        self.is_pending = data.is_pending if source == "db" else False if source == "remote" else data[
            'is_pending']
        self.cycle_type = data.cycle_type if source == "db" else data['cycle_type']
        self.local_api = AHRepo(engine=engine)
        self.mt5 = mt5
        self.bot = bot
        self.orders = self.get_orders_from_remote(
            data.orders['orders']) if source == 'remote' else self.combine_orders()

    def combine_orders(self):
        return self.initial + self.hedge + self.pending + self.recovery + self.max_recovery

    def get_orders_from_remote(self, orders):
        for order_data in orders:
            # convet orderdata to subscrible

            order_obj = order(SimpleNamespace(order_data),
                              self.is_pending, self.mt5, self.local_api, "db")
            order_obj.create_order()
            # add the order to the orders list
            order_kind = order_obj.kind
            order_ticket = order_obj.ticket
            if order_kind == "initial":
                self.remove_initial_order(order_ticket)
            elif order_kind == "hedge":
                self.remove_hedge_order(order_ticket)
            elif order_kind == "recovery":
                self.remove_recovery_order(order_ticket)
            elif order_kind == "pending":
                self.remove_pending_order(order_ticket)
    # create cycle data

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
            "max_recovery": self.max_recovery,
            "opened_by": self.opened_by,
            "id": self.cycle_id,
            "cycle_type": self.cycle_type,

        }

        return data
    # create cycle  data to  send to remote server

    def to_remote_dict(self):
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
            "total_profit": round(float(self.total_profit), 2),
            "total_volume": round(float(self.total_volume), 2),
            "closing_method": self.closing_method,
            "orders": {
                "orders": []},
            "opened_by": self.opened_by,
            "cycle_type": self.cycle_type,



        }
        #  go through the orders and add them to the data
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.mt5, self.local_api, "db")
            data["orders"]["orders"].append(order_obj.to_dict())

        for order_ticket in self.closed:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.mt5, self.local_api, "db")
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

    # update cylce orders
    async def update_cycle(self, remote_api):
        self.orders = self.combine_orders()
        self.total_profit = 0
        self.total_volume = 0
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            if order_data:
                self.total_profit += order_data.profit+order_data.swap+order_data.commission
                self.total_volume += order_data.volume
                if order_data.is_closed is True:
                    self.orders.remove(order_ticket)
                    self.closed.append(order_ticket)
                    if order_data.kind == "hedge":
                        self.hedge.remove(order_ticket)
                    if order_data.kind == "recovery":
                        self.recovery.remove(order_ticket)
                    if order_data.kind == "pending":
                        self.pending.remove(order_ticket)
                    if order_data.kind == "initial":
                        self.initial.remove(order_ticket)
        for closed_order in self.closed:
            if closed_order not in self.orders:
                self.orders.remove(closed_order)

        # Directly check with MT5 if any orders are still open
        any_still_open = False
        all_order_tickets = self.initial + self.hedge + self.pending + self.recovery
        for ticket in all_order_tickets:
            positions = self.mt5.get_position_by_ticket(ticket=ticket)
            pending_orders = self.mt5.get_order_by_ticket(ticket=ticket)
            if (positions is not None and len(positions) > 0) or (pending_orders is not None and len(pending_orders) > 0):
                any_still_open = True
                break

        # Only mark cycle as closed if no orders are left and there are no open orders in MT5
        if len(self.orders) == 0 and not any_still_open:
            self.status = "closed"
            self.is_closed = True
            self.closing_method["sent_by_admin"] = False
            self.closing_method["status"] = "MetaTrader5"
            self.closing_method["username"] = "MetaTrader5"
        elif any_still_open and self.is_closed:
            # If marked as closed but has open orders, fix it
            self.is_closed = False
            self.status = "open"
            print(f"Fixed AH cycle {self.id} incorrectly marked as closed")

        # If cycle is over
        if len(self.pending) == 0 and len(self.initial) == 0 and self.is_closed is False and len(self.hedge) == 0:
            # Make a hedge
            if self.hedge_direction == 0:  # BUY
                result = self.hedge_buy_order(False)
            else:  # SELL
                result = self.hedge_sell_order(False)
        self.local_api.Update_cycle(self.id, self.to_dict())
    # create a new cycle

    def create_cycle(self):
        self.orders = self.combine_orders()
        cycle_data = self.local_api.create_cycle(self.to_dict())
        # update the orders in  the cycle  with  the cycle  id
        for order_ticket in self.orders:
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_objec = order(order_data, order_data.is_pending,
                                self.mt5, self.local_api, "db", cycle_data.id)
            order_objec.update_order()
        return cycle_data
    # close cycle

    def close_cycle(self, sent_by_admin, user_id, username):

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
        self.closing_method["user_id"] = user_id
        self.closing_method["username"] = username
        self.local_api.Update_cycle(self.id, self.to_dict())

        return True

    async def manage_cycle_orders(self):
        if self.status == "initial":
            ask = self.mt5.get_ask(self.symbol)
            bid = self.mt5.get_bid(self.symbol)
            if ask > self.upper_bound:
                self.close_initial_buy_orders()
                total_sell = self.count_initial_sell_orders()
                if total_sell >= 1:
                    self.hedge_sell_order()
                    self.status = "recovery"
                    self.update_AH_cycle()
            elif bid < self.lower_bound:
                self.close_initial_sell_orders()
                total_buy = self.count_initial_buy_orders()
                if total_buy >= 1:
                    self.hedge_buy_order()
                    self.status = "recovery"
                    self.update_AH_cycle()
        elif self.status in ["recovery", "max_recovery"]:
            if not self.bot.disable_new_cycle_recovery:
                self.go_opposite_direction()
            self.go_hedge_direction()

        # self.max_recovery_order()
    def max_recovery_order(self):
        bid = self.mt5.get_bid(self.symbol)
        ask = self.mt5.get_ask(self.symbol)
        pip = self.mt5.get_pips(self.symbol)
        if (len)(self.hedge) == 0:
            return
        last_hedge = self.hedge[-1]
        last_hedge_order_data_db = self.local_api.get_order_by_ticket(
            last_hedge)
        last_hedge_orderobj = order(
            last_hedge_order_data_db[0], self.is_pending, self.mt5, self.local_api, "db", self.id)
        if last_hedge_orderobj.type == Mt5.ORDER_TYPE_SELL and bid < last_hedge_orderobj.open_price:
            if last_hedge_orderobj.profit > 0:
                if len(self.max_recovery) < self.bot.max_recovery:
                    last_max_recovery = self.max_recovery[-1] if len(
                        self.max_recovery) > 0 else -1
                    if last_max_recovery > 0:
                        last_max_recovery_order_data_db = self.local_api.get_order_by_ticket(
                            last_max_recovery)
                        last_max_recovery_orderobj = order(
                            last_max_recovery_order_data_db[0], self.is_pending, self.mt5, self.local_api, "db", self.id)
                        last_max_recovery_open_price = last_max_recovery_orderobj.open_price
                        if (ask < last_max_recovery_open_price-self.bot.zone_forward*pip*10 and last_hedge_orderobj.type == Mt5.ORDER_TYPE_SELL and last_max_recovery_open_price > last_hedge_orderobj.open_price) or (ask < last_max_recovery_open_price-self.bot.zone_forward*pip*10 and last_hedge_orderobj.type == Mt5.ORDER_TYPE_SELL and last_max_recovery_open_price < last_hedge_orderobj.open_price):
                            max_recovery_order = self.mt5.buy(self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery") if self.bot.max_recovery_direction == "opposite" else self.mt5.sell(
                                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery")
                            self.max_recovery.append(
                                max_recovery_order[0].ticket)
                            # create a new order
                            order_obj = order(
                                max_recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                            order_obj.create_order()
                            return True
                    else:
                        if ask > last_hedge_orderobj.open_price-self.bot.zone_forward*pip*10 and len(self.max_recovery) == 0:
                            max_recovery_order = self.mt5.buy(self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery") if self.bot.max_recovery_direction == "opposite" else self.mt5.sell(
                                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery")
                            self.max_recovery.append(
                                max_recovery_order[0].ticket)
                            # create a new order
                            order_obj = order(
                                max_recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                            order_obj.create_order()
                            return True
        elif last_hedge_orderobj.type == Mt5.ORDER_TYPE_BUY and ask > last_hedge_orderobj.open_price:
            if last_hedge_orderobj.profit > 0:
                if len(self.max_recovery) < self.bot.max_recovery:
                    last_max_recovery = self.max_recovery[-1] if len(
                        self.max_recovery) > 0 else -1
                    if last_max_recovery > 0:
                        last_max_recovery_order_data_db = self.local_api.get_order_by_ticket(
                            last_max_recovery)
                        last_max_recovery_orderobj = order(
                            last_max_recovery_order_data_db[0], self.is_pending, self.mt5, self.local_api, "db", self.id)
                        last_max_recovery_open_price = last_max_recovery_orderobj.open_price
                        if (bid > last_max_recovery_open_price+self.bot.zone_forward*pip*10 and last_hedge_orderobj.type == Mt5.ORDER_TYPE_BUY and last_max_recovery_open_price < last_hedge_orderobj.open_price) or (bid > last_max_recovery_open_price+self.bot.zone_forward*pip*10 and last_max_recovery_orderobj.type == Mt5.ORDER_TYPE_BUY and last_max_recovery_open_price > last_hedge_orderobj.open_price):
                            max_recovery_order = self.mt5.sell(self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery") if self.bot.max_recovery_direction == "opposite" else self.mt5.buy(
                                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery")
                            self.max_recovery.append(
                                max_recovery_order[0].ticket)
                            # create a new order
                            order_obj = order(
                                max_recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                            order_obj.create_order()
                            return True
                    else:
                        if bid < last_hedge_orderobj.open_price+self.bot.zone_forward*pip*10 and len(self.max_recovery) == 0:
                            max_recovery_order = self.mt5.sell(self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery") if self.bot.max_recovery_direction == "opposite" else self.mt5.buy(
                                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "max_recovery")
                            self.max_recovery.append(
                                max_recovery_order[0].ticket)
                            # create a new order
                            order_obj = order(
                                max_recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                            order_obj.create_order()
                            return True

    def close_initial_buy_orders(self):
        total_initial = len(self.initial)
        if total_initial >= 1:
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

    def close_initial_sell_orders(self):
        total_sells = len(self.initial)
        if total_sells >= 1:
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

    def hedge_buy_order(self, sent_by_admin):
        self.lot_idx = min(self.lot_idx + 1, len(self.bot.lot_sizes) - 1)
        hedge_order = self.mt5.sell(
            self.symbol, self.bot.lot_sizes[self.lot_idx], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "hedge")
        self.zone_index = min(self.zone_index + 1, len(self.bot.zones) - 1)
        if len(hedge_order) > 0:
            # add the order to the hedge list
            self.hedge.append(hedge_order[0].ticket)
            # create a new order
            order_obj = order(
                hedge_order[0], False, self.mt5, self.local_api, "mt5", self.id)
            order_obj.create_order()

        if self.bot.enable_recovery:
            recovery_order = self.mt5.buy(
                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "recovery")
            if len(recovery_order) > 0:
                self.recovery.append(recovery_order[0].ticket)
                # create a new order
                order_obj = order(
                    recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                order_obj.create_order()
        # update the upper and lower by the zone index
        self.lower_bound = float(hedge_order[0].price_open) - float(
            self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))
        self.upper_bound = float(hedge_order[0].price_open) + float(
            self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))

    def hedge_sell_order(self, sent_by_admin):
        self.lot_idx = min(self.lot_idx + 1, len(self.bot.lot_sizes) - 1)
        hedge_order = self.mt5.buy(
            self.symbol, self.bot.lot_sizes[self.lot_idx], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "hedge")
        self.zone_index = min(self.zone_index + 1, len(self.bot.zones) - 1)
        if len(hedge_order) > 0:
            # add the order to the hedge list
            self.hedge.append(hedge_order[0].ticket)
            # create a new order
            order_obj = order(
                hedge_order[0], False, self.mt5, self.local_api, "mt5", self.id)
            order_obj.create_order()
        if self.bot.enable_recovery:
            recovery_order = self.mt5.sell(
                self.symbol, self.bot.lot_sizes[0], self.bot.bot.magic, 0, 0, "PIPS", self.bot.slippage, "recovery")
            if len(recovery_order) > 0:
                self.recovery.append(recovery_order[0].ticket)
                # create a new order
                order_obj = order(
                    recovery_order[0], False, self.mt5, self.local_api, "mt5", self.id)
                order_obj.create_order()
        # update the upper and lower by the zone index
        self.lower_bound = float(hedge_order[0].price_open) - float(
            self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))
        self.upper_bound = float(hedge_order[0].price_open) + float(
            self.bot.zones[self.zone_index]) * float(self.mt5.get_pips(self.symbol))

    def go_opposite_direction(self):
        # check recovery order length
        if len(self.recovery) < 1:
            return
        if len(self.recovery) > 0:
            ask = self.mt5.get_ask(self.symbol)
            bid = self.mt5.get_bid(self.symbol)
            if ask > self.upper_bound:
                last_recovery = self.recovery[-1]
                order_data_db = self.local_api.get_order_by_ticket(
                    last_recovery)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                last_recovery_type = orderobj.type
                last_recovery_profit = orderobj.profit
                if last_recovery_type == Mt5.ORDER_TYPE_SELL and last_recovery_profit < 0:
                    # create  a new  cycle
                    new_cycle = self.create_new_cycle(
                        orderobj.open_price, last_recovery)
                    new_cycle.hedge_sell_order()
                    self.remove_recovery_order(last_recovery)
            elif bid < self.lower_bound:
                last_recovery = self.recovery[-1]
                order_data_db = self.local_api.get_order_by_ticket(
                    last_recovery)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                last_recovery_type = orderobj.type
                last_recovery_profit = orderobj.profit
                if last_recovery_type == Mt5.ORDER_TYPE_BUY and last_recovery_profit < 0:
                    # create  a new  cycle
                    new_cycle = self.create_new_cycle(
                        orderobj.open_price, last_recovery)
                    new_cycle.hedge_buy_order()
                    self.remove_recovery_order(last_recovery)

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
                if last_hedge_type == Mt5.ORDER_TYPE_SELL and last_hedge_profit < 0:
                    self.close_recovery_orders()
                    self.hedge_sell_order()
            elif bid < self.lower_bound:
                last_hedge = self.hedge[-1]
                order_data_db = self.local_api.get_order_by_ticket(last_hedge)
                orderobj = order(order_data_db, self.is_pending,
                                 self.mt5, self.local_api, "db", self.id)
                last_hedge_type = orderobj.type
                last_hedge_profit = orderobj.profit
                if last_hedge_type == Mt5.ORDER_TYPE_BUY and last_hedge_profit < 0:
                    self.close_recovery_orders()
                    self.hedge_buy_order()

    def update_AH_cycle(self):
        self.local_api.Update_cycle(self.id, self.to_dict())
    #  close   cycle when hits  takeprofit

    async def close_cycle_on_takeprofit(self, take_profit, remote_api):
        if self.total_profit >= take_profit:
            self.is_pending = False
            self.is_closed = True
            self.close_cycle(False, 0, "MetaTrader5")
            self.update_AH_cycle()
            remote_api.update_AH_cycle_by_id(
                self.cycle_id, self.to_remote_dict())

    def create_new_cycle(self, price_open, recovery_order):
        """
        This function creates a cycle.

        Parameters:
        data (dict): The cycle data.

        Returns:
        None
        """
        lower_bound = float(
            price_open) - float(self.bot.zones[0]) * float(self.mt5.get_pips(self.symbol))
        upper_bound = float(
            price_open) + float(self.bot.zones[0]) * float(self.mt5.get_pips(self.symbol))

        data = {
            "account": self.account,
            "bot": self.bot_id,
            "is_closed": False,
            "symbol":  self.symbol,
            "closing_method": {},
            "opened_by": {
                "sent_by_admin": False,
                "status": "Opened by MetaTrader5",
                "user_id": 0,
                "user_name": "MetaTrader5",
            },
            "lot_idx": 0,
            "status": "initial",
            "lower_bound": round(lower_bound, 2),
            "upper_bound": round(upper_bound, 2),
            "is_pending": False,
            "type": "initial",
            "total_volume": round(123, 2),
            "total_profit": round(123, 2),
            "initial": [recovery_order],
            "hedge": [],
            "pending": [],
            "closed": [],
            "recovery": [],
            "max_recovery": [],
            "cycle_id": "",
            "zone_index": 0,


        }
        New_cycle = cycle(data, self.local_api, self.mt5, self)
        res = self.bot.create_AH_cycle(New_cycle.to_remote_dict())
        New_cycle.cycle_id = str(res.id)
        New_cycle.create_cycle()
        return New_cycle
