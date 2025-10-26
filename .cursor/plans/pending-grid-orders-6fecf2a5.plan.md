<!-- 6fecf2a5-0be0-4823-8d7d-6a0b43191115 4265868b-474c-420c-b5fc-b542327a046b -->
# Convert MoveGuard Grid Orders to Pending Orders

## Overview

Transform the MoveGuard grid trading system from market orders to pending orders for precise execution at exact grid levels without slippage. System will place next 3 grid levels as pending orders, cancel and replace on grid restart, and use mixed order types based on price position.

## Implementation Strategy

### 1. Add MT5 Pending Order Support (MetaTrader/MT5.py)

The MT5 wrapper already has pending order methods but needs order cancellation support:

**Add cancel_pending_order method:**

```python
def cancel_pending_order(self, order_id, symbol):
    """Cancel a pending order"""
    request = {
        "action": Mt5.TRADE_ACTION_REMOVE,
        "order": order_id,
        "symbol": symbol
    }
    result = Mt5.order_send(request)
    return result
```

**Add wrapper methods for grid pending orders:**

- `place_pending_buy_order(symbol, price, volume, sl, tp, comment)` - Auto-selects BUY_STOP or BUY_LIMIT
- `place_pending_sell_order(symbol, price, volume, sl, tp, comment)` - Auto-selects SELL_STOP or SELL_LIMIT

**Logic for order type selection:**

- BUY: If target_price > current_price, use BUY_STOP, else use BUY_LIMIT
- SELL: If target_price < current_price, use SELL_STOP, else use SELL_LIMIT

### 2. Add Pending Order Tracking (Strategy/MoveGuard.py)

**Add cycle attributes for pending order management:**

```python
cycle.pending_orders = []  # Track pending order IDs and levels
cycle.pending_order_levels = set()  # Quick lookup of levels with pending orders
```

**Location:** Initialize in `_place_initial_order()` after first order placement (around line 1938)

### 3. Replace Grid Placement Logic (Strategy/MoveGuard.py)

**Current flow (lines 1862-1930):**

- Wait for price to reach target_price
- Place market order when triggered
- Update all orders' SL

**New flow:**

- After placing initial order (level 0), place pending orders for levels 1-3
- Monitor pending orders and place next pending orders as they trigger
- Maintain 3 pending orders ahead at all times

**Key changes in `_process_grid_logic()`:**

```python
# After initial order placement (around line 1823)
if active_order_count > 0:
    # Ensure we have 3 pending orders ahead
    self._maintain_pending_grid_orders(cycle, current_price, 3)
    
# Remove old market order placement logic (lines 1862-1930)
# Replace with pending order monitoring
```

### 4. Create Pending Order Management Methods

**Add new methods to MoveGuard class:**

**_maintain_pending_grid_orders(cycle, current_price, num_levels=3)**

- Calculate next grid levels that need pending orders
- Check which levels don't have pending orders
- Place pending orders for missing levels
- Location: Add after `_place_grid_sell_order()` (around line 3600)

**_place_pending_grid_order(cycle, grid_level, target_price, order_type)**

- Calculate SL for pending order (use current trailing_stop_loss)
- Determine order type (BUY_STOP/BUY_LIMIT/SELL_STOP/SELL_LIMIT)
- Place pending order via MT5
- Store pending order info in cycle.pending_orders
- Location: Add after `_maintain_pending_grid_orders()`

**_cancel_cycle_pending_orders(cycle)**

- Iterate through cycle.pending_orders
- Cancel each pending order via MT5
- Clear cycle.pending_orders and cycle.pending_order_levels
- Location: Add after `_place_pending_grid_order()`

**_update_pending_order_on_trigger(cycle, order_id)**

- Called when pending order becomes active position
- Move order from pending_orders to active orders
- Place next pending order to maintain 3 ahead
- Location: Add after `_cancel_cycle_pending_orders()`

### 5. Update Initial Order Placement

**Convert `_place_initial_order()` (around line 1938):**

- Change from market order to pending order
- For BUY: If current_price >= upper + offset, place BUY_STOP at current_price
- For SELL: If current_price <= lower - offset, place SELL_STOP at current_price
- After placing, immediately call `_maintain_pending_grid_orders()` to place levels 1-3

### 6. Handle Grid Restart

**Update grid restart logic (lines 1796-1806):**

```python
if is_grid_restart:
    # Cancel all existing pending orders
    self._cancel_cycle_pending_orders(cycle)
    
    # Store restart price
    cycle.grid_restart_start_price = current_price
    
    # Clear pending order tracking
    cycle.pending_orders = []
    cycle.pending_order_levels = set()
```

**After placing restart initial order:**

- Place next 3 pending orders from restart price
- Use restart price as new grid_start_price

### 7. Update Trailing Stop Loss Logic

**Modify `_update_all_orders_trailing_sl()` (existing method):**

- Only update SL for active positions (not pending orders)
- Pending orders keep their initial SL
- When pending order triggers and becomes active, it will get updated SL

**Location:** Lines around 4500-4600 (existing method)

### 8. Monitor Pending Order Status

**Add monitoring in main processing loop:**

```python
def _monitor_pending_orders(self, cycle, current_price):
    """Check if any pending orders have been triggered"""
    for pending_order in cycle.pending_orders[:]:  # Copy list
        # Query MT5 to check if order is still pending or became position
        order_status = self._check_pending_order_status(pending_order['order_id'])
        
        if order_status == 'filled':
            # Order triggered, update tracking
            self._update_pending_order_on_trigger(cycle, pending_order['order_id'])
            
        elif order_status == 'cancelled':
            # Order was cancelled (shouldn't happen normally)
            cycle.pending_orders.remove(pending_order)
```

**Call from `_process_grid_logic()` before grid placement checks**

## Files to Modify

1. **MetaTrader/MT5.py**

   - Add `cancel_pending_order()` method
   - Add `place_pending_buy_order()` wrapper
   - Add `place_pending_sell_order()` wrapper

2. **Strategy/MoveGuard.py**

   - Update `_place_initial_order()` to use pending orders
   - Replace market order grid placement with pending order system
   - Add `_maintain_pending_grid_orders()`
   - Add `_place_pending_grid_order()`
   - Add `_cancel_cycle_pending_orders()`
   - Add `_update_pending_order_on_trigger()`
   - Add `_monitor_pending_orders()`
   - Update `_update_all_orders_trailing_sl()` to skip pending orders
   - Update grid restart logic to cancel pending orders

## Benefits

- Precise execution at exact grid levels
- No slippage on grid entries
- Reduced bot processing during price movements
- Broker handles order execution automatically
- Clean grid restart by canceling old pending orders

## Testing Checklist

- Initial order placement as pending order
- Next 3 levels placed as pending orders after initial order
- Pending orders trigger correctly at target prices
- New pending orders placed after each trigger
- Grid restart cancels old pending orders and places new ones
- SL only updates on active positions, not pending orders
- Both BUY and SELL cycles work correctly
- Mixed order types (STOP/LIMIT) selected correctly based on price position

### To-dos

- [ ] Add cancel_pending_order() and wrapper methods to MT5.py
- [ ] Add pending order tracking attributes to cycle objects
- [ ] Create pending order management methods (_maintain, _place, _cancel, _update)
- [ ] Convert _place_initial_order() to use pending orders
- [ ] Replace market order grid placement with pending order system
- [ ] Update grid restart to cancel pending orders
- [ ] Add pending order status monitoring in processing loop
- [ ] Modify trailing SL update to skip pending orders
- [ ] Test pending order system with both BUY and SELL cycles