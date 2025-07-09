# PocketBase Manual Schema Update Guide

## Collections to Update

You need to update these two collections that were created via MCP:
1. `advanced_cycles_trader_cycles` (ID: pbc_1596752216)
2. `global_loss_tracker` (ID: pbc_3212933115)

## Access Admin Interface

1. Go to: `https://pdapp.fppatrading.com/_/`
2. Login with: `dev@mail.com` / `1223334444`

## 1. Advanced Cycles Trader Cycles Collection

Navigate to **Collections** → **advanced_cycles_trader_cycles** → **Edit**

### Fields to Add (35 fields total):

#### Basic Trading Fields
1. **cycle_id** - Text, Required, Unique
2. **bot_id** - Text, Required
3. **symbol** - Text, Required  
4. **magic_number** - Number, Required
5. **entry_price** - Number, Optional
6. **stop_loss** - Number, Optional
7. **take_profit** - Number, Optional
8. **lot_size** - Number, Optional

#### Direction Fields
9. **direction** - Select, Required, Values: ["BUY", "SELL"]
10. **current_direction** - Select, Optional, Values: ["BUY", "SELL"]

#### Zone Trading Fields
11. **zone_base_price** - Number, Optional
12. **initial_threshold_price** - Number, Optional
13. **zone_threshold_pips** - Number, Optional
14. **order_interval_pips** - Number, Optional
15. **batch_stop_loss_pips** - Number, Optional
16. **zone_range_pips** - Number, Optional

#### Direction Management
17. **direction_switched** - Bool, Optional
18. **direction_switches** - Number, Optional, Min: 0, Integer only

#### Order Management
19. **done_price_levels** - JSON, Optional, Max size: 2MB
20. **next_order_index** - Number, Optional, Min: 1, Integer only
21. **active_orders** - JSON, Optional, Max size: 2MB
22. **completed_orders** - JSON, Optional, Max size: 2MB
23. **current_batch_id** - Text, Optional

#### Timing Fields
24. **last_order_time** - Date, Optional
25. **last_order_price** - Number, Optional

#### Loss Tracking
26. **accumulated_loss** - Number, Optional, Min: 0
27. **batch_losses** - JSON, Optional, Max size: 2MB

#### Status Fields
28. **is_active** - Bool, Optional
29. **is_closed** - Bool, Optional
30. **close_reason** - Text, Optional
31. **close_time** - Date, Optional

#### Performance Fields
32. **total_profit** - Number, Optional
33. **total_orders** - Number, Optional, Min: 0, Integer only
34. **profitable_orders** - Number, Optional, Min: 0, Integer only
35. **loss_orders** - Number, Optional, Min: 0, Integer only
36. **duration_minutes** - Number, Optional, Min: 0, Integer only

### Access Rules for advanced_cycles_trader_cycles:
- **List rule**: `@request.auth.id != ""`
- **View rule**: `@request.auth.id != ""`
- **Create rule**: `@request.auth.id != ""`
- **Update rule**: `@request.auth.id != ""`
- **Delete rule**: `@request.auth.id != ""`

## 2. Global Loss Tracker Collection

Navigate to **Collections** → **global_loss_tracker** → **Edit**

### Fields to Add (20 fields total):

#### Identification Fields
1. **bot_id** - Text, Required
2. **account_id** - Text, Required
3. **symbol** - Text, Required

#### Loss Tracking Fields
4. **total_accumulated_losses** - Number, Optional
5. **active_cycles_count** - Number, Optional, Min: 0, Integer only
6. **closed_cycles_count** - Number, Optional, Min: 0, Integer only

#### Loss Breakdown
7. **initial_order_losses** - Number, Optional
8. **threshold_order_losses** - Number, Optional
9. **recovery_order_losses** - Number, Optional

#### Cycle Management
10. **last_cycle_id** - Text, Optional
11. **last_loss_amount** - Number, Optional

#### ACT Specific Fields
12. **zone_based_losses** - Number, Optional
13. **direction_switch_count** - Number, Optional, Min: 0, Integer only
14. **batch_stop_loss_triggers** - Number, Optional, Min: 0, Integer only

#### Risk Management
15. **max_single_cycle_loss** - Number, Optional
16. **average_cycle_loss** - Number, Optional
17. **loss_trend** - Select, Optional, Values: ["increasing", "decreasing", "stable"]

#### Performance Tracking
18. **total_cycles_processed** - Number, Optional, Min: 0, Integer only
19. **profitable_cycles** - Number, Optional, Min: 0, Integer only
20. **loss_making_cycles** - Number, Optional, Min: 0, Integer only

### Access Rules for global_loss_tracker:
- **List rule**: `@request.auth.id != ""`
- **View rule**: `@request.auth.id != ""`
- **Create rule**: `@request.auth.id != ""`
- **Update rule**: `@request.auth.id != ""`
- **Delete rule**: `@request.auth.id != ""`

## Field Type Reference

### Text Fields
- Leave min/max empty for unlimited
- Pattern can be left empty

### Number Fields
- Set "Min" value where specified
- Check "Integer only" for count fields
- Leave "Max" empty for unlimited

### Select Fields
- Set "Max select" to 1
- Add values exactly as shown in brackets

### JSON Fields
- Set "Max size" to 2000000 (2MB) for large data fields

### Bool Fields
- No additional options needed

### Date Fields
- Leave min/max empty

## Verification

After adding all fields:
1. Check that both collections show the correct number of fields
2. Test creating a record with some sample data
3. Verify the Python bot and Flutter app can connect and use the collections

## Indexes (Optional but Recommended)

For better performance, consider adding these indexes:

### advanced_cycles_trader_cycles:
- `bot_id`
- `symbol` 
- `is_active`
- `is_closed`
- `created`

### global_loss_tracker:
- `bot_id`
- `account_id`
- `symbol`

Add indexes via Collections → [Collection Name] → Indexes tab. 