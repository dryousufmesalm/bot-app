# Reversal Trading Fields Update

This directory contains scripts to add reversal trading fields to the Advanced Cycles Trader collection in PocketBase.

## Collection Name

The correct collection name for Advanced Cycles Trader cycles is:

```
advanced_cycles_trader_cycles
```

## Available Scripts

1. **add_reversal_fields_directly.py**
   - Directly updates the collection schema by adding new fields
   - Does not use the migration system
   - Most reliable method for adding fields

2. **apply_reversal_migration.py**
   - Attempts to apply the migration file to the collection
   - Tries multiple endpoints for compatibility with different PocketBase versions
   - Falls back to direct schema update if migration fails

3. **update_reversal_fields.py**
   - Master script that tries both methods in sequence
   - Provides the highest chance of success
   - Recommended approach for most cases

## New Fields Added

The scripts add the following fields to the collection:

- `reversal_threshold_pips` (number) - Threshold in pips for triggering a reversal
- `highest_buy_price` (number) - Highest price recorded during buy direction
- `lowest_sell_price` (number) - Lowest price recorded during sell direction
- `reversal_count` (number) - Number of direction reversals that occurred
- `closed_orders_pl` (number) - Profit/loss from closed orders
- `open_orders_pl` (number) - Profit/loss from currently open orders
- `total_cycle_pl` (number) - Total profit/loss across all directions
- `last_reversal_time` (date) - Timestamp of the last direction reversal
- `reversal_history` (json) - History of reversal events

## Usage

Run the master script for the best chance of success:

```bash
python update_reversal_fields.py
```

Or run individual scripts directly:

```bash
python add_reversal_fields_directly.py
python apply_reversal_migration.py
```

## Troubleshooting

If you encounter errors:

1. Check that the PocketBase server is running and accessible
2. Verify that the admin credentials are correct
3. Check if the collection already has the fields
4. Try running the scripts with admin privileges
5. Check the logs for specific error messages

## Environment Variables

The scripts use the following environment variables:

- `POCKETBASE_URL` - URL of the PocketBase server (default: https://pdapp.fppatrading.com)
- `POCKETBASE_ADMIN_EMAIL` - Admin email for authentication
- `POCKETBASE_ADMIN_PASSWORD` - Admin password for authentication 