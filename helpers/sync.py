"""
Synchronization utilities to prevent race conditions between MetaTrader 5 and the database.
This module provides helper functions and classes to ensure data consistency.
"""

import asyncio
import functools
import logging
import time
import threading
from typing import Callable, Any, TypeVar, Optional

logger = logging.getLogger(__name__)

# Define type variable for function return types
T = TypeVar('T')

# Create a dummy lock class that doesn't actually block


class DummyLock:
    """A dummy lock that doesn't actually block - used to disable MT5_LOCK"""

    def __enter__(self):
        # Log that we're entering a section that would have been locked
        logger.debug(
            "MT5_LOCK disabled: entering section that would have been locked")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Log that we're exiting a section that would have been locked
        logger.debug(
            "MT5_LOCK disabled: exiting section that would have been locked")
        return False

    def acquire(self, blocking=True, timeout=-1):
        # Always return True to indicate success
        return True

    def release(self):
        # Do nothing
        pass


# Global lock for MetaTrader 5 operations - replaced with dummy lock
MT5_LOCK = DummyLock()  # Previously: threading.Lock()


class SyncManager:
    """
    Manager class for synchronization between MT5 and database operations.
    Provides methods to safely execute operations and prevent race conditions.
    """

    def __init__(self):
        self.mt5_lock = MT5_LOCK
        # Default synchronization delay between operations (in seconds)
        self.default_delay = 0.5

    def with_mt5_lock(self, func):
        """
        Decorator to execute a function with MT5 lock.

        Args:
            func: The function to execute with MT5 lock.

        Returns:
            Decorated function that acquires and releases the lock.
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self.mt5_lock:
                return func(*args, **kwargs)
        return wrapper

    async def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        max_retries: int = 3,
        retry_delay: float = 0.2,
        **kwargs
    ) -> Optional[T]:
        """
        Execute a function with retry logic in case of failure.

        Args:
            func: The function to execute.
            args: Positional arguments to pass to the function.
            max_retries: Maximum number of retry attempts.
            retry_delay: Delay between retry attempts in seconds.
            kwargs: Keyword arguments to pass to the function.

        Returns:
            The result of the function or None if all retries failed.
        """
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Error executing {func.__name__}, retrying ({attempt+1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"All retries failed for {func.__name__}: {e}"
                    )
                    return None

    async def sync_delay(self, duration: float = None):
        """
        Introduce a delay to ensure synchronization between operations.

        Args:
            duration: The delay duration in seconds. If None, uses default_delay.
        """
        await asyncio.sleep(duration or self.default_delay)


# Create a singleton instance
sync_manager = SyncManager()

# Decorators for easy use


def with_mt5_lock(func):
    """
    Decorator to execute a function with MT5 lock.

    Args:
        func: The function to execute with MT5 lock.

    Returns:
        Decorated function that acquires and releases the lock.
    """
    return sync_manager.with_mt5_lock(func)

# Functions for direct use in code


async def execute_with_retry(func, *args, max_retries=3, retry_delay=0.2, **kwargs):
    """
    Execute a function with retry logic in case of failure.

    Args:
        func: The function to execute.
        args: Positional arguments to pass to the function.
        max_retries: Maximum number of retry attempts.
        retry_delay: Delay between retry attempts in seconds.
        kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the function or None if all retries failed.
    """
    return await sync_manager.execute_with_retry(
        func, *args, max_retries=max_retries, retry_delay=retry_delay, **kwargs
    )


async def sync_delay(duration=None):
    """
    Introduce a delay to ensure synchronization between operations.

    Args:
        duration: The delay duration in seconds. If None, uses default_delay.
    """
    await sync_manager.sync_delay(duration)

# Function to verify order status with double-check


async def verify_order_status(mt5, ticket, retries=2, delay=0.1):
    """
    Verify order status with multiple checks to ensure consistency.

    Args:
        mt5: MetaTrader instance to use for verification.
        ticket: Order ticket to verify.
        retries: Number of verification retries.
        delay: Delay between verification attempts.

    Returns:
        Tuple of (is_open, is_closed, is_pending) status flags.
    """
    # Lock disabled - perform direct checks without locking
    # First check
    positions = mt5.get_position_by_ticket(ticket=ticket)
    pending_orders = mt5.get_order_by_ticket(ticket=ticket)

    is_position = positions is not None and len(positions) > 0
    is_pending = pending_orders is not None and len(pending_orders) > 0

    # If order is active, we can return immediately
    if is_position or is_pending:
        return (is_position, False, is_pending)

    # Order not found in active orders, perform multiple checks for closed status
    is_closed_checks = []

    for _ in range(retries):
        is_closed_checks.append(mt5.check_order_is_closed(ticket))
        await asyncio.sleep(delay)

    # Order is considered closed only if ALL checks confirm it
    is_closed = all(is_closed_checks)

    return (False, is_closed, False)

# Function to synchronize cycle updates


async def sync_cycle_update(cycle, remote_api):
    """
    Synchronize cycle update operation to prevent race conditions.

    Args:
        cycle: The cycle to update.
        remote_api: Remote API to use for updates.
    """
    # Use a short delay to stabilize cycle state
    await sync_delay(0.2)

    # Update cycle locally
    if hasattr(cycle, 'update_CT_cycle'):
        cycle.update_CT_cycle()
    elif hasattr(cycle, 'update_AH_cycle'):
        cycle.update_AH_cycle()

    # Small delay before remote update
    await sync_delay(0.2)

    # Update cycle remotely
    if hasattr(cycle, 'update_CT_cycle'):
        remote_api.update_CT_cycle_by_id(
            cycle.cycle_id, cycle.to_remote_dict())
    elif hasattr(cycle, 'update_AH_cycle'):
        remote_api.update_AH_cycle_by_id(
            cycle.cycle_id, cycle.to_remote_dict())
