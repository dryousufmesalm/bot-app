# Quick PocketBase Schema Update Guide

## 🔗 Access Admin Interface
Go to: **https://pdapp.fppatrading.com/_/**
Login: `dev@mail.com` / `1223334444`

## 📋 Step-by-Step Instructions

### 1. Update `advanced_cycles_trader_cycles` Collection

1. Click **Collections** in the left sidebar
2. Find and click **advanced_cycles_trader_cycles**
3. Click the **Edit** button (pencil icon)
4. Click **+ New field** to add each field below:

#### Essential Fields (Add these first):
```
cycle_id     | Text    | Required ✓ | Unique ✓
bot_id       | Text    | Required ✓
symbol       | Text    | Required ✓
magic_number | Number  | Required ✓
entry_price  | Number  | Optional
stop_loss    | Number  | Optional
take_profit  | Number  | Optional
lot_size     | Number  | Optional
```

#### Direction Fields:
```
direction         | Select | Required ✓ | Values: BUY,SELL
current_direction | Select | Optional   | Values: BUY,SELL
```

#### Zone Trading Fields:
```
zone_base_price        | Number | Optional
initial_threshold_price| Number | Optional
zone_threshold_pips    | Number | Optional
order_interval_pips    | Number | Optional
batch_stop_loss_pips   | Number | Optional
zone_range_pips        | Number | Optional
```

#### Direction Management:
```
direction_switched | Bool   | Optional
direction_switches | Number | Optional | Min: 0 | Integer ✓
```

#### Order Management:
```
done_price_levels  | JSON | Optional | Max size: 2000000
next_order_index   | Number | Optional | Min: 1 | Integer ✓
active_orders      | JSON | Optional | Max size: 2000000
completed_orders   | JSON | Optional | Max size: 2000000
current_batch_id   | Text | Optional
```

#### Timing & Status:
```
last_order_time    | Date   | Optional
last_order_price   | Number | Optional
accumulated_loss   | Number | Optional | Min: 0
batch_losses       | JSON   | Optional | Max size: 2000000
is_active          | Bool   | Optional
is_closed          | Bool   | Optional
close_reason       | Text   | Optional
close_time         | Date   | Optional
```

#### Performance:
```
total_profit      | Number | Optional
total_orders      | Number | Optional | Min: 0 | Integer ✓
profitable_orders | Number | Optional | Min: 0 | Integer ✓
loss_orders       | Number | Optional | Min: 0 | Integer ✓
duration_minutes  | Number | Optional | Min: 0 | Integer ✓
```

5. Click **Save** after adding all fields

### 2. Update `global_loss_tracker` Collection

1. Click **Collections** → **global_loss_tracker** → **Edit**
2. Add these fields:

#### Identification:
```
bot_id     | Text | Required ✓
account_id | Text | Required ✓
symbol     | Text | Required ✓
```

#### Loss Tracking:
```
total_accumulated_losses | Number | Optional
active_cycles_count      | Number | Optional | Min: 0 | Integer ✓
closed_cycles_count      | Number | Optional | Min: 0 | Integer ✓
initial_order_losses     | Number | Optional
threshold_order_losses   | Number | Optional
recovery_order_losses    | Number | Optional
```

#### Cycle Management:
```
last_cycle_id    | Text   | Optional
last_loss_amount | Number | Optional
```

#### ACT Specific:
```
zone_based_losses        | Number | Optional
direction_switch_count   | Number | Optional | Min: 0 | Integer ✓
batch_stop_loss_triggers | Number | Optional | Min: 0 | Integer ✓
```

#### Risk Management:
```
max_single_cycle_loss | Number | Optional
average_cycle_loss    | Number | Optional
loss_trend           | Select | Optional | Values: increasing,decreasing,stable
```

#### Performance:
```
total_cycles_processed | Number | Optional | Min: 0 | Integer ✓
profitable_cycles      | Number | Optional | Min: 0 | Integer ✓
loss_making_cycles     | Number | Optional | Min: 0 | Integer ✓
```

3. Click **Save**

### 3. Set Access Rules

For **both collections**, go to **API Rules** tab and set:
```
List rule:   @request.auth.id != ""
View rule:   @request.auth.id != ""
Create rule: @request.auth.id != ""
Update rule: @request.auth.id != ""
Delete rule: @request.auth.id != ""
```

## ✅ Verification

After completing the setup:
1. Both collections should show 30+ fields each
2. Test creating a sample record in each collection
3. Your Python bot and Flutter app should now work correctly

## 🚀 Field Types Quick Reference

- **Text**: Leave min/max empty, no pattern needed
- **Number**: Set Min value if specified, check "Integer only" for count fields
- **Select**: Max select = 1, add comma-separated values
- **JSON**: Set Max size to 2000000 (2MB)
- **Bool**: No additional settings
- **Date**: No additional settings

## 📞 Need Help?

If you encounter any issues:
1. Make sure you're logged in as admin
2. Check that field names match exactly (case-sensitive)
3. Verify required/optional settings match the guide
4. Save after adding each batch of fields 