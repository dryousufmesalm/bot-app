from Views.globals.app_logger import app_logger
from Views.globals.app_configs import AppConfigs
from helpers.store import store
from helpers.actions_creators import add_user, add_mt5, GetUser
from Api.APIHandler import API
# from Views.globals.app_state import store
import asyncio
from Bots.account import Account

from Orders.orders_manager import orders_manager
from cycles.cycles_manager import cycles_manager
from helpers.store import store

import multiprocessing
from multiprocessing import Queue
import logging
from helpers.sync import MT5_LOCK, sync_manager

# Create a Manager object

# Create an MetaTrader of the MetaTraderExpert class
# Check if the connection was successful
# Initialize the API handler

# Start PocketBase

# start_pocketbase(local_auth,local_user,local_password)
# Wait until PocketBase is fully launched
# Adjust the sleep time as needed
# Authenticate with the API
# get accounts


async def login(
    username: str, password: str
) -> tuple[bool, str]:
    """login function, to authenticate the user and set the token in the [AppState.token]

    Returns:
        tuple[bool, str]: return a tuple with the login status as (True in case of successful login ) and (False in case any error)
        and a message, in case of success and failure.
    """

    try:

        # On successful login, set the token in the AppState
        # ******* Do other stuff Here ********
        app_configs = AppConfigs()
        auth = API(app_configs.pb_url)
        user_data = auth.login(username, password)
        if user_data is None:
            return (False, "Login failed")
        store.dispatch(add_user(user_data, auth, username, password))

        # return success status and messge
        return (True, "Login successful")

    except Exception as e:
        # Show snackbar with the error message
        # # log the error
        app_logger.error(f"Login failed: {e}")
        return (False, "Login failed")


# launch the metatrader
def launch_metatrader(data, authorized):
    from MetaTrader.MT5 import MetaTrader
    import logging
    import time
    from helpers.sync import MT5_LOCK, sync_manager

    # Configure additional logging for synchronization issues
    sync_logger = logging.getLogger("sync_issues")
    sync_logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler("sync_issues.log")
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    sync_logger.addHandler(handler)

    username = data.get('username')
    password = data.get('password')
    server = data.get('server')
    program_path = data.get('program_path')
    server_username = data.get('server_username')
    server_password = data.get('server_password')
    try:
        # ******* Do other stuff Here ********
        expert = MetaTrader(username, password, server)
        logged = expert.initialize(program_path)

        if not logged:
            app_logger.error("Failed to initialize MetaTrader 5")
            authorized.put(False)
            return False

        # Verify account information is available
        try:
            acc = expert.get_account_info()
            if not acc:
                app_logger.error(
                    "Failed to get account information from MetaTrader 5")
                authorized.put(False)
                return False

            app_logger.info(
                f"Successfully connected to MetaTrader 5 account: {acc['login']}")
            sync_logger.info(
                f"MT5 Connection established for account: {acc['login']}")
        except Exception as acc_error:
            app_logger.error(
                f"Error accessing MT5 account information: {acc_error}")
            authorized.put(False)
            return False

        # Connect to remote API
        app_configs = AppConfigs()
        auth = API(app_configs.pb_url)
        auth_result = auth.login(server_username, server_password)

        if not auth_result:
            app_logger.error("Failed to authenticate with remote API")
            authorized.put(False)
            return False

        # Initialize account and managers
        user_account = Account(auth, expert)
        # Use asyncio.run to handle the awaitable
        asyncio.run(user_account.on_init())

        # Initialize order and cycle managers with synchronized access
        OrdersManager = orders_manager(expert)
        # Set a reasonable sync delay
        OrdersManager.sync_delay = 0.5  # Half second between operations

        cyclesManager = cycles_manager(expert, auth, user_account)

        # Share the MT5_LOCK with the sync_manager for consistent locking
        sync_manager.mt5_lock = MT5_LOCK

        async def main():
            try:
                # Start account background task
                task1 = asyncio.create_task(user_account.run_in_background())

                # Add a small delay between task starts to prevent initial race conditions
                await asyncio.sleep(1)

                # Start orders manager with error handling
                task2 = asyncio.create_task(OrdersManager.run_in_thread())

                # Add another delay before cycles manager
                await asyncio.sleep(1)

                # Start cycles manager with error handling
                task3 = asyncio.create_task(cyclesManager.run_in_thread())

                # Log successful startup
                sync_logger.info("All background tasks started successfully")

                # Wait for all tasks
                await asyncio.gather(task1, task2, task3)
            except Exception as task_error:
                app_logger.error(f"Error in background tasks: {task_error}")
                sync_logger.error(f"Background task error: {task_error}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(main())
        loop.run_forever()
        authorized.put(True)

        # Monitor for synchronization issues
        while True:
            # Check if MT5 is still connected
            if not expert.authorized:
                sync_logger.critical("MT5 connection lost")
                app_logger.error(
                    "MT5 connection lost, attempting to reconnect")
                # Could add reconnection logic here

            # Prevent busy waiting - use regular time.sleep instead of await
            time.sleep(30)  # Check every 30 seconds

    except Exception as e:
        # Show snackbar with the error message
        # log the error
        app_logger.error(f"Metatrader launch failed: {e}")
        sync_logger.critical(f"Fatal error in Metatrader launch: {e}")
        authorized.put(False)
        return False


def launch_metatrader_in_process(data):
    # ns=multiprocessing.Manager().Namespace()
    authorized = Queue()
    p = multiprocessing.Process(
        target=launch_metatrader, args=(data, authorized))
    p.daemon = True
    p.start()
    return p.is_alive

    # store.dispatch(add_mt5(user, account, expert))
    # user_data = GetUser(user)
    # auth = user_data.get('auth_api')


def set_app_token(token: str):
    """Set the token in the AppState

    Args:
        token (str): the token to be set in the AppState
    """

    app_logger.info("Token set in the AppState")


def set_login_data(data: dict[str, str]):
    """Set the login data in the AppState

    Args:
        data (dict[str, str]): the login data to be set in the AppState
    """
    # store.login_data = data
    app_logger.info("Login data set in the AppState")
