from dataclasses import dataclass

@dataclass
class TradeEvent:
    uuid: str
    accountId: str
    contents: dict[str, any]
    botId: str | None  = None
    strategyId: str | None = None

class TradeEventMessages:
    OPEN_ORDER = "open_order"
    CLOSE_ORDER = "close_order"
    CLOSE_PENDING_ORDER = "close_pending_order"
    CLOSE_ALL_ORDERS = "close_all_orders"
    CLOSE_ALL_PENDING_ORDERS = "close_all_pending_orders"
    CLOSE_CYCLE = "close_cycle"
    CLOSE_ALL_CYCLES = "close_all_cycles"
    UPDATE_BOT = "update_bot"
    DELETE_BOT = "delete_bot"
    CREATE_BOT = "create_bot"
    STOP_BOT = "stop_bot"
    START_BOT = "start_bot"
    UPDATE_ORDER_CONFIGS = "update_order_configs"
