from pocketbase import PocketBase
import threading
import logging
import json
import datetime
from typing import Dict, Any, Optional, Union


class API:
    """ The base class for all the API handlers"""

    def __init__(self, base_url, token=None):
        self.base_url = base_url
        self.token = token
        self.authenticated = False
        self.user_name = None
        self.user_email = None
        self.is_active = False
        self.user_id = None
        self.client = PocketBase(self.base_url)

    def login(self, username, password):
        """Authenticate with the API using the provided username and password."""
        try:
            user_data = self.client.collection(
                "users").auth_with_password(username, password)
            self.token = user_data.token
            self.user_id = user_data.record.id
            self.authenticated = user_data.is_valid
            # Set the user_name from the record
            self.user_name = username
            self.user_email = user_data.record.email
            self.is_active = user_data.record.active
            return user_data
        except Exception as e:
            logging.error(f"Failed to login: {e}")
            return None

    def Refresh_token(self):
        """Refresh the token."""
        try:
            user_data = self.client.collection("users").authRefresh()
            self.client.auth_store.save(user_data.token)
            self.token = user_data.token
            self.authenticated = user_data.is_valid
            
            # Update user_name if it's not set or if we have fresh data
            if not self.user_name and hasattr(user_data.record, 'username'):
                self.user_name = user_data.record.username
            
            account_name = self.user_name if self.user_name else "Unknown"
            print(f"Token refreshed for account {account_name}!")
            print(f"is authenticated: {self.authenticated}")
            return user_data
        except Exception as e:
            logging.error(f"Failed to refresh token: {e}")
            return None

    def logout(self):
        """Log out the current user."""
        try:
            self.token = None
            self.authenticated = False
            self.user_name = None
            self.user_email = None
            self.is_active = False
            self.user_id = None
            return True
        except Exception as e:
            logging.error(f"Failed to logout: {e}")
            return False

    def get_accounts(self, userid):
        """Get all accounts for the current user."""
        try:
            accounts = self.client.collection("accounts").get_full_list(200, {
                "filter": f"user = '{userid}'"
            })
            return accounts
        except Exception as e:
            logging.error(f"Failed to get accounts: {e}")
            return []

    def get_accounts_by_id(self, account_id):
        """Get an account by its ID."""
        try:
            return self.client.collection("accounts").get_full_list(200, {
                "filter": f"user = '{self.user_id}' && id = '{account_id}'"
            })
        except Exception as e:
            logging.error(f"Failed to get account by ID: {e}")
            return None

    def get_accounts_by_metatrader_id(self, account_id):
        """Get an account by its MetaTrader ID."""
        try:
            return self.client.collection("accounts").get_full_list(200, {
                "filter": f"user = '{self.user_id}' && meta_trader_id = '{account_id}'"
            })
        except Exception as e:
            logging.error(f"Failed to get account by MetaTrader ID: {e}")
            return None

    def update_account(self, account_id, data):
        """Update an account."""
        try:
            return self.client.collection("accounts").update(account_id, data)
        except Exception as e:
            logging.error(f"Failed to update account: {e}")
            return None

    def update_account_symbols(self, account_id, data):
        """Update an account."""
        try:
            return self.client.collection("accounts").update(account_id, data)
        except Exception as e:
            logging.error(f"Failed to update account symbols: {e}")
            return None

    def get_account_bots(self, account_id):
        """Get all bots for the current user."""
        try:
            return self.client.collection("bots").get_full_list(200, {"filter": f"account = '{account_id}'"})
        except Exception as e:
            logging.error(f"Failed to get account bots: {e}")
            return []

    def get_account_bots_by_id(self, bot_id):
        """Get a bot by its ID."""
        try:
            return self.client.collection("bots").get_full_list(200, {"filter": f"id = '{bot_id}'"})
        except Exception as e:
            logging.error(f"Failed to get bot by ID: {e}")
            return None

    def get_bots_by_magic(self, magic):
        """Get a bot by its magic numbers."""
        try:
            return self.client.collection("bots").get_full_list(200, {"filter": f"magic = '{magic}'"})
        except Exception as e:
            logging.error(f"Failed to get bots by magic: {e}")
            return None

    def get_strategy_by_id(self, strategy_id):
        """Get a strategy by its ID."""
        try:
            return self.client.collection("strategies").get_full_list(200, {"filter": f"id = '{strategy_id}'"})
        except Exception as e:
            logging.error(f"Failed to get strategy by ID: {e}")
            return None

    def delete_event(self, event_id):
        """Delete an event from the event collection."""
        try:
            self.client.collection("events").delete(event_id)
        except Exception as e:
            logging.error(f"Failed to delete event: {e}")

    def subscribe_events(self, handle_events):
        """Subscribe to the event collection."""
        try:
            print("Subscribing to events...")
            # CRITICAL FIX: Check if collection exists and is accessible
            events_collection = self.client.collection("events")
            if not events_collection:
                logging.error("Failed to access events collection")
                return False
                
            # Try to get a test event to verify collection access
            try:
                test_events = events_collection.get_list(1, 1)
                if test_events is None:
                    logging.error("Events collection returned None")
                    return False
            except Exception as e:
                logging.error(f"Failed to test events collection access: {e}")
                return False
            
            # Subscribe to events
            events_collection.subscribe(handle_events)
            print("✅ Successfully subscribed to events")
            return True
            
        except Exception as e:
            logging.error(f"Failed to subscribe to events: {e}")
            return False

    def get_all_events(self):
        """Get all events."""
        try:
            return self.client.collection("events").get_full_list(200)
        except Exception as e:
            logging.error(f"An error occurred while fetching events: {e}")
            return None

    def get_events_by_bot(self, bot_id: str):
        """Get events specific to a bot."""
        try:
            return self.client.collection("events").get_full_list(200, {"filter": f"bot = '{bot_id}'"})
        except Exception as e:
            logging.error(f"An error occurred while fetching events for bot {bot_id}: {e}")
            return None

    def get_events_by_account_and_bot(self, account_id: str, bot_id: str):
        """Get events specific to an account and bot combination."""
        try:
            return self.client.collection("events").get_full_list(200, {"filter": f"account = '{account_id}' && bot = '{bot_id}'"})
        except Exception as e:
            logging.error(f"An error occurred while fetching events for account {account_id} and bot {bot_id}: {e}")
            return None

    def get_symbol_by_id(self, symbol_id):
        """Get a symbol by its ID."""
        try:
            return self.client.collection("symbols").get_full_list(200, {"filter": f"id = '{symbol_id}'"})
        except Exception as e:
            logging.error(f"Failed to get symbol by ID: {e}")
            return None

    def get_symbols_by_account(self, account):
        """Get a symbol by its name."""
        try:
            return self.client.collection("symbols").get_full_list(200, {"filter": f"account = '{account}'"})
        except Exception as e:
            logging.error(f"Failed to get symbol: {e}")
            return None

    def get_symbol(self, account_id):
        """Get a symbol by its name."""
        try:
            return self.client.collection("symbols").get_full_list(200, {"filter": f"account = '{account_id}'"})
        except Exception as e:
            logging.error(f"Failed to get symbol: {e}")
            return None

    def get_symbol_by_name(self, symbol_name, account_id):
        """Get a symbol by its name and account."""
        try:
            return self.client.collection("symbols").get_full_list(200, {"filter": f"name = '{symbol_name}' && account = '{account_id}'"})
        except Exception as e:
            logging.error(f"Failed to get symbol by name: {e}")
            return None

    def create_symbol(self, data):
        """Create a symbol."""
        try:
            return self.client.collection("symbols").create(data)
        except Exception as e:
            logging.error(f"Failed to create symbol: {e}")
            return None

    def update_symbol(self, symbol_id, data):
        """Update a symbol."""
        try:
            return self.client.collection("symbols").update(symbol_id, data)
        except Exception as e:
            logging.error(f"Failed to update symbol: {e}")
            return None

    def create_AH_cycle(self, data):
        """Create a cycle."""
        try:
            return self.client.collection("adaptive_hedge_cycles").create(data)
        except Exception as e:
            logging.error(f"Failed to create AH cycle: {e}")
            return None

    def delete_AH_cycle(self, data):
        """Delete a cycle."""
        try:
            return self.client.collection("adaptive_hedge_cycles").delete(data)
        except Exception as e:
            logging.error(f"Failed to delete AH cycle: {e}")
            return None

    def get_AH_cycle_by_id(self, cycle_id):
        """Get a cycle by its ID."""
        try:
            return self.client.collection("adaptive_hedge_cycles").get_full_list(200, {"filter": f"id = '{cycle_id}'"})
        except Exception as e:
            logging.error(f"Failed to get AH cycle by ID: {e}")
            return None

    def get_all_AH_active_cycles(self):
        """Get all active cycles."""
        try:
            return self.client.collection("adaptive_hedge_cycles").get_full_list(200, {"filter": "is_closed = False"})
        except Exception as e:
            logging.error(f"An error occurred while fetching AH cycles: {e}")
            return []

    def get_all_AH_active_cycles_by_account(self, account_id):
        """Get all active cycles by account."""
        try:
            return self.client.collection("adaptive_hedge_cycles").get_full_list(200, {"filter": f"account = '{account_id}' && is_closed = False"})
        except Exception as e:
            logging.error(
                f"An error occurred while fetching AH cycles by account: {e}")
            return []

    def update_AH_cycle_by_id(self, cycle_id, data):
        """Update a cycle by its ID."""
        try:
            return self.client.collection("adaptive_hedge_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to update AH cycle by ID: {e}")

            return None

    def close_AH_cycle(self, cycle_id):
        """Close a cycle by its ID."""
        try:
            data = {"is_closed": True}
            return self.client.collection("adaptive_hedge_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to close AH cycle: {e}")
            return None

    def create_CT_cycle(self, data):
        """Create a cycle."""
        try:
            return self.client.collection("cycles_trader_cycles").create(data)
        except Exception as e:
            logging.error(f"Failed to create CT cycle: {e}")
            return None

    def delete_CT_cycle(self, data):
        """Delete a cycle."""
        try:
            return self.client.collection("cycles_trader_cycles").delete(data)
        except Exception as e:
            logging.error(f"Failed to delete CT cycle: {e}")
            return None

    def get_CT_cycle_by_id(self, cycle_id):
        """Get a cycle by its ID."""
        try:
            return self.client.collection("cycles_trader_cycles").get_full_list(200, {"filter": f"id = '{cycle_id}'"})
        except Exception as e:
            logging.error(f"Failed to get CT cycle by ID: {e}")
            return None

    def get_all_CT_active_cycles(self):
        """Get all active cycles."""
        try:
            return self.client.collection("cycles_trader_cycles").get_full_list(200, {"filter": "is_closed = false"})
        except Exception as e:
            logging.error(f"An error occurred while fetching CT cycles: {e}")
            return []

    def get_all_CT_active_cycles_by_account(self, account_id):
        """Get all active cycles by account."""
        try:
            logging.info(f"Fetching CT cycles for account ID: {account_id}")
            if not account_id:
                logging.error("Account ID is empty or None")
                return []

            filter_query = f"account = '{account_id}' && is_closed = False"
            logging.info(f"Using filter query: {filter_query}")

            cycles = self.client.collection("cycles_trader_cycles").get_full_list(
                200, {"filter": filter_query})
            logging.info(f"Retrieved {len(cycles)} cycles")
            return cycles
        except Exception as e:
            logging.error(
                f"An error occurred while fetching CT cycles by account: {e}")
            return []

    def update_CT_cycle_by_id(self, cycle_id, data):
        """Update a cycle by its ID."""
        try:
            return self.client.collection("cycles_trader_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to update CT cycle by ID: {e}")
            return None

    def close_CT_cycle(self, cycle_id):
        """Close a cycle by its ID."""
        try:
            data = {"is_closed": True}
            return self.client.collection("cycles_trader_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to close CT cycle: {e}")
            return None

    def set_bot_stopped(self, bot_id):
        """Set a bot as stopped."""
        try:
            data = {"settings": {"stopped": True}}
            return self.client.collection("bots").update(bot_id, data)
        except Exception as e:
            logging.error(f"Failed to set bot as stopped: {e}")
            return None

    def set_bot_running(self, bot_id):
        """Set a bot as running."""
        try:
            data = {"settings": {"stopped": False}}
            return self.client.collection("bots").update(bot_id, data)
        except Exception as e:
            logging.error(f"Failed to set bot as running: {e}")
            return None

    def update_bot_magic_number(self, bot_id, magic_number):
        """Update a bot's magic number."""
        try:
            data = {"magic_number": magic_number}
            result = self.client.collection("bots").update(bot_id, data)
            logging.info(f"✅ Successfully updated magic number for bot {bot_id} to {magic_number}")
            return result
        except Exception as e:
            logging.error(f"❌ Failed to update magic number for bot {bot_id}: {e}")
            return None

    def send_log(self, data):
        """Create a log."""
        try:
            return self.client.collection("terminal_logs").create(data)
        except Exception as e:
            logging.error(f"Failed to create log: {e}")
            return None

    # Advanced Cycles Trader (ACT) methods
    def ensure_json_serializable(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure all fields in the data dictionary are JSON serializable."""
        serialized_data = {}
        for key, value in data.items():
            if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
                serialized_data[key] = value.isoformat() if value else None
            elif isinstance(value, (list, dict)):
                # If it's already a JSON string, keep it as is
                if isinstance(value, str):
                    try:
                        json.loads(value)  # Validate it's a valid JSON string
                        serialized_data[key] = value
                    except json.JSONDecodeError:
                        serialized_data[key] = json.dumps(value)
                else:
                    serialized_data[key] = json.dumps(value)
            else:
                try:
                    json.dumps(value)  # Test if value is JSON serializable
                    serialized_data[key] = value
                except (TypeError, ValueError):
                    serialized_data[key] = str(value)
        return serialized_data

    def create_ACT_cycle(self, data: Dict[str, Any]) -> Optional[Any]:
        """Create an Advanced Cycles Trader cycle with proper JSON serialization."""
        try:
            # First ensure all numeric fields are properly converted
            numeric_fields = [
                'magic_number', 'entry_price', 'stop_loss', 'take_profit', 'lot_size',
                'zone_base_price', 'initial_threshold_price', 'reversal_threshold_pips',
                'order_interval_pips', 'initial_order_stop_loss', 'next_order_index',
                'zone_based_losses', 'batch_stop_loss_triggers', 'lot_idx',
                'lower_bound', 'upper_bound', 'cycle_interval'
            ]
            
            for field in numeric_fields:
                if field in data:
                    try:
                        data[field] = float(data[field])
                    except (ValueError, TypeError):
                        logging.error(f"❌ Field {field} is not a valid number: {data[field]}")
                        data[field] = 0.0
                        logging.info(f"Auto-fixed {field} to 0.0")
            
            # Ensure all data is JSON serializable
            serialized_data = self.ensure_json_serializable(data)
            
            try:
                result = self.client.collection("advanced_cycles_trader_cycles").create(serialized_data)
                logging.info(f"✅ ACT cycle creation successful: {result.id if result else 'NO_RESULT'}")
                return result
            except Exception as e:
                logging.error(f"❌ Failed to create ACT cycle: {str(e)}")
                # Try to extract more detailed error information
                error_message = str(e)
                if "failed validation" in error_message.lower():
                    logging.error("Schema validation error detected")
                    if hasattr(e, 'data') and e.data:
                        for field, errors in e.data.items():
                            logging.error(f"Field '{field}': {errors}")
                return None
                
        except Exception as e:
            logging.error(f"❌ Failed to create ACT cycle: {e}")
            logging.error(f"Data keys sent: {list(data.keys()) if data else 'NO_DATA'}")
            # Log more detailed error information
            for key, value in data.items():
                if key in ['active_orders', 'completed_orders', 'orders', 'done_price_levels', 
                          'opened_by', 'closing_method', 'batch_losses', 'orders_config']:
                    logging.error(f"Field {key} type: {type(value)}")
                    if not isinstance(value, str):
                        logging.error(f"Field {key} is not a string, which may cause the error")
            return None

    def delete_ACT_cycle(self, data):
        """Delete an Advanced Cycles Trader cycle."""
        try:
            return self.client.collection("advanced_cycles_trader_cycles").delete(data)
        except Exception as e:
            logging.error(f"Failed to delete ACT cycle: {e}")
            return None

    def get_ACT_cycle_by_id(self, cycle_id):
        """Get an Advanced Cycles Trader cycle by its ID."""
        try:
            return self.client.collection("advanced_cycles_trader_cycles").get_full_list(200, {"filter": f"id = '{cycle_id}'"})
        except Exception as e:
            logging.error(f"Failed to get ACT cycle by ID: {e}")
            return None

    def get_all_ACT_active_cycles(self):
        """Get all active Advanced Cycles Trader cycles."""
        try:
            return self.client.collection("advanced_cycles_trader_cycles").get_full_list(200, {"filter": "is_closed = false"})
        except Exception as e:
            logging.error(f"An error occurred while fetching ACT cycles: {e}")
            return []

    def get_all_ACT_active_cycles_by_account(self, account_id):
        """Get all active Advanced Cycles Trader cycles by account."""
        try:
            logging.info(f"Fetching ACT cycles for account ID: {account_id}")
            if not account_id:
                logging.error("Account ID is empty or None")
                return []

            filter_query = f"account = '{account_id}' && is_closed = False"
            logging.info(f"Using filter query: {filter_query}")

            cycles = self.client.collection("advanced_cycles_trader_cycles").get_full_list(
                200, {"filter": filter_query})
            logging.info(f"Retrieved {len(cycles)} ACT cycles")
            return cycles
        except Exception as e:
            logging.error(
                f"An error occurred while fetching ACT cycles by account: {e}")
            return []
    def get_all_ACT_active_cycles_by_bot_id(self, bot_id):
        """Get all active Advanced Cycles Trader cycles by bot ID."""
        try:
            return self.client.collection("advanced_cycles_trader_cycles").get_full_list(200, {"filter": f"bot = '{bot_id}' && is_closed = false"})
        except Exception as e:
            logging.error(f"An error occurred while fetching ACT cycles by bot ID: {e}")
            return []
    def update_ACT_cycle_by_id(self, cycle_id, data):
        """Update an Advanced Cycles Trader cycle by its ID."""
        try:
            # No need to map fields anymore since we're using the correct names directly
            return self.client.collection("advanced_cycles_trader_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to update ACT cycle by ID: {e}")
            return None

    def close_ACT_cycle(self, cycle_id):
        """Close an Advanced Cycles Trader cycle by its ID."""
        try:
            data = {"is_closed": True}
            return self.client.collection("advanced_cycles_trader_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to close ACT cycle: {e}")
            return None

    # Global Loss Tracker methods for Advanced Cycles Trader
    def create_global_loss_tracker(self, data):
        """Create a global loss tracker record."""
        try:
            return self.client.collection("global_loss_tracker").create(data)
        except Exception as e:
            logging.error(f"Failed to create global loss tracker: {e}")
            return None

    def get_global_loss_tracker(self, bot_id, account_id, symbol):
        """Get global loss tracker by bot_id, account_id, and symbol."""
        try:
            filter_query = f"bot_id = '{bot_id}' && account_id = '{account_id}' && symbol = '{symbol}'"
            return self.client.collection("global_loss_tracker").get_full_list(200, {"filter": filter_query})
        except Exception as e:
            logging.error(f"Failed to get global loss tracker: {e}")
            return None

    def update_global_loss_tracker(self, tracker_id, data):
        """Update a global loss tracker record."""
        try:
            return self.client.collection("global_loss_tracker").update(tracker_id, data)
        except Exception as e:
            logging.error(f"Failed to update global loss tracker: {e}")
            return None

    def get_all_collections(self):
        """Get all collections in PocketBase."""
        try:
            # This is a basic implementation - PocketBase SDK may have different method
            return self.client.collections.get_full_list()
        except Exception as e:
            logging.error(f"Failed to get collections: {e}")
            return []

    # Generic cycle methods for compatibility
    def get_cycles_by_bot(self, bot_id):
        """Get all cycles by bot ID (ACT cycles)."""
        try:
            if not bot_id:
                logging.error("Bot ID is empty or None")
                return []

            filter_query = f"bot = '{bot_id}'"
            logging.info(f"Fetching cycles for bot ID: {bot_id}")

            cycles = self.client.collection("advanced_cycles_trader_cycles").get_full_list(
                200, {"filter": filter_query})
            logging.info(f"Retrieved {len(cycles)} cycles for bot {bot_id}")
            return cycles
        except Exception as e:
            logging.error(f"An error occurred while fetching cycles by bot: {e}")
            return []

    def update_cycle(self, cycle_id, data):
        """Update a cycle by its ID (generic method for ACT cycles)."""
        try:
            # No need to map fields anymore since we're using the correct names directly
            return self.client.collection("advanced_cycles_trader_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to update cycle by ID: {e}")
            return None

    def close_all_cycles_by_bot(self, bot_id):
        """Close all cycles for a specific bot."""
        try:
            if not bot_id:
                logging.error("Bot ID is empty or None")
                return False

            # Get all active cycles for this bot
            cycles = self.get_cycles_by_bot(bot_id)
            if not cycles:
                logging.info(f"No cycles found for bot {bot_id}")
                return True

            closed_count = 0
            for cycle in cycles:
                if not getattr(cycle, 'is_closed', True):  # Only close if not already closed
                    try:
                        result = self.close_ACT_cycle(cycle.id)
                        if result:
                            closed_count += 1
                            logging.info(f"Closed cycle {cycle.id}")
                        else:
                            logging.error(f"Failed to close cycle {cycle.id}")
                    except Exception as e:
                        logging.error(f"Error closing cycle {cycle.id}: {e}")

            logging.info(f"Closed {closed_count} cycles for bot {bot_id}")
            return True

        except Exception as e:
            logging.error(f"Failed to close all cycles for bot {bot_id}: {e}")
            return False

    def get_cycle_by_external_id(self, external_id):
        """Get a cycle by its external ID (cycle_id field)."""
        try:
            filter_query = f"cycle_id = '{external_id}'"
            result = self.client.collection("advanced_cycles_trader_cycles").get_full_list(
                200, {"filter": filter_query})
            return result
        except Exception as e:
            logging.error(f"Failed to get cycle by external ID: {e}")
            return None

    def get_active_ACT_cycles(self, bot_id):
        """Get active Advanced Cycles Trader cycles for a specific bot."""
        try:
            logging.info(f"Fetching active ACT cycles for bot ID: {bot_id}")
            if not bot_id:
                logging.error("Bot ID is empty or None")
                return []

            filter_query = f"bot = '{bot_id}' && is_closed = false"
            logging.info(f"Using filter query: {filter_query}")

            cycles = self.client.collection("advanced_cycles_trader_cycles").get_full_list(
                200, {"filter": filter_query})
            logging.info(f"Retrieved {len(cycles)} active ACT cycles for bot {bot_id}")
            return cycles
        except Exception as e:
            logging.error(f"An error occurred while fetching active ACT cycles for bot: {e}")
            return []

    # ==================== MOVEGUARD CYCLES METHODS ====================
    def create_MG_cycle(self, data: Dict[str, Any]) -> Optional[Any]:
        """Create a MoveGuard cycle with proper JSON serialization."""
        try:
            serialized_data = self.ensure_json_serializable(data)
            result = self.client.collection("moveguard_cycles").create(serialized_data)
            logging.info(f"✅ MoveGuard cycle creation successful: {result.id if result else 'NO_RESULT'}")
            return result
        except Exception as e:
            logging.error(f"❌ Failed to create MoveGuard cycle: {str(e)}")
            return None

    def update_MG_cycle_by_id(self, cycle_id: str, data: Dict[str, Any]) -> Optional[Any]:
        """Update a MoveGuard cycle by its ID."""
        try:
            return self.client.collection("moveguard_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to update MoveGuard cycle by ID: {e}")
            return None

    def get_MG_cycle_by_id(self, cycle_id: str):
        """Get a MoveGuard cycle by its ID."""
        try:
            return self.client.collection("moveguard_cycles").get_full_list(200, {"filter": f"id = '{cycle_id}'"})
        except Exception as e:
            logging.error(f"Failed to get MoveGuard cycle by ID: {e}")
            return None

    def get_all_MG_active_cycles(self):
        """Get all active MoveGuard cycles."""
        try:
            return self.client.collection("moveguard_cycles").get_full_list(200, {"filter": "is_closed = false"})
        except Exception as e:
            logging.error(f"An error occurred while fetching MoveGuard cycles: {e}")
            return []

    def get_all_MG_active_cycles_by_account(self, account_id: str):
        """Get all active MoveGuard cycles by account."""
        try:
            return self.client.collection("moveguard_cycles").get_full_list(200, {"filter": f"account = '{account_id}' && is_closed = False"})
        except Exception as e:
            logging.error(f"An error occurred while fetching MoveGuard cycles by account: {e}")
            return []

    def get_all_MG_active_cycles_by_bot_id(self, bot_id: str):
        """Get all active MoveGuard cycles by bot ID."""
        try:
            return self.client.collection("moveguard_cycles").get_full_list(200, {"filter": f"bot = '{bot_id}' && is_closed = false"})
        except Exception as e:
            logging.error(f"An error occurred while fetching MoveGuard cycles by bot ID: {e}")
            return []

    def close_MG_cycle(self, cycle_id: str):
        """Close a MoveGuard cycle by its ID."""
        try:
            data = {"is_closed": True}
            return self.client.collection("moveguard_cycles").update(cycle_id, data)
        except Exception as e:
            logging.error(f"Failed to close MoveGuard cycle: {e}")
            return None

    def get_MG_cycles_by_bot(self, bot_id: str):
        """Get all MoveGuard cycles by bot ID."""
        try:
            if not bot_id:
                logging.error("Bot ID is empty or None")
                return []
            filter_query = f"bot = '{bot_id}'"
            cycles = self.client.collection("moveguard_cycles").get_full_list(200, {"filter": filter_query})
            return cycles
        except Exception as e:
            logging.error(f"An error occurred while fetching MoveGuard cycles by bot: {e}")
            return []

    def get_MG_cycle_by_external_id(self, external_id: str):
        """Get a MoveGuard cycle by its external ID (cycle_id field)."""
        try:
            filter_query = f"cycle_id = '{external_id}'"
            return self.client.collection("moveguard_cycles").get_full_list(200, {"filter": filter_query})
        except Exception as e:
            logging.error(f"Failed to get MoveGuard cycle by external ID: {e}")
            return None
