# Missing Order Recovery System Guide

## Overview

The Missing Order Recovery System is a comprehensive solution designed to detect, organize, and recover orders that exist in MetaTrader 5 (MT5) but aren't properly associated with cycles in the Advanced Cycles Trader (ACT) system.

## Problem Description

Sometimes orders placed in MT5 aren't properly tracked by the ACT system due to:
- Network connectivity issues during order placement
- System restarts or crashes
- Database synchronization problems
- Manual order placement outside the system
- Timing issues between order placement and cycle creation

## Solution Components

### 1. Automatic Detection (Built into ACT Strategy)

The AdvancedCyclesTrader automatically detects missing orders through:

- **Enhanced `_update_active_cycles()` method**: Runs during each strategy iteration
- **`_detect_and_organize_missing_orders()` method**: Comprehensive missing order detection
- **`_organize_missing_orders()` method**: Intelligent order categorization
- **`_process_organized_missing_orders()` method**: Automatic recovery actions

### 2. Individual Cycle Detection

Each ACT cycle has enhanced missing order detection:

- **`_check_and_add_missing_orders()` method**: Checks for orders specific to each cycle
- **`force_sync_with_mt5()` method**: Manual synchronization for individual cycles
- **Enhanced logging**: Detailed tracking of order associations

### 3. Manual Recovery Utility

A command-line utility for manual recovery operations:

```bash
# Detect missing orders
python missing_order_recovery.py --action detect

# Recover missing orders
python missing_order_recovery.py --action recover

# Force sync all bots
python missing_order_recovery.py --action force_sync

# Generate recovery report
python missing_order_recovery.py --action report

# Process specific bot
python missing_order_recovery.py --action detect --bot-id "your_bot_id"

# Verbose logging
python missing_order_recovery.py --action detect --verbose
```

## How It Works

### 1. Detection Process

1. **Scan MT5 Positions**: Get all positions from MetaTrader with the bot's magic number
2. **Filter by Symbol**: Only consider positions for the bot's trading symbol
3. **Compare with Database**: Check which orders are tracked in the system
4. **Identify Missing**: Find orders in MT5 but not in the system

### 2. Organization Process

Missing orders are categorized into three types:

- **Existing Cycle Candidates**: Orders that match existing cycles based on:
  - Direction (BUY/SELL)
  - Price proximity (within 100 pips)
  - Volume similarity
  - Timing correlation

- **New Cycle Candidates**: Orders that could form new cycles when no active cycles exist

- **Orphaned Orders**: Orders that don't match any existing cycles and need special handling

### 3. Recovery Process

1. **Add to Existing Cycles**: Missing orders are added to their best-matching cycles
2. **Create Recovery Cycles**: New cycles are created for orphaned orders
3. **Update Database**: All changes are immediately synchronized to PocketBase
4. **Log Results**: Comprehensive logging of all recovery actions

## Usage Examples

### Automatic Recovery (Recommended)

The system automatically handles missing orders during normal operation:

```python
# This happens automatically in the strategy loop
strategy._update_active_cycles()
```

### Manual Recovery for Specific Bot

```python
# Force sync a specific bot
bot.strategy._force_sync_all_cycles_with_mt5()

# Force sync a specific cycle
cycle.force_sync_with_mt5()
```

### Command Line Recovery

```bash
# Quick detection
python missing_order_recovery.py --action detect

# Full recovery
python missing_order_recovery.py --action recover

# Generate detailed report
python missing_order_recovery.py --action report --verbose
```

## Monitoring and Logging

### Key Log Messages

- `🔍 Found X missing orders for cycle Y`: Missing orders detected
- `✅ Successfully added missing order X to cycle Y`: Order recovered
- `🆕 Order X marked as new cycle candidate`: New cycle needed
- `❓ Order X appears orphaned`: Orphaned order detected
- `🔄 Force syncing cycle X with MT5 orders`: Manual sync started

### Debug Information

Enable verbose logging to see detailed information:

```bash
python missing_order_recovery.py --action detect --verbose
```

## Best Practices

### 1. Regular Monitoring

- Run detection weekly: `python missing_order_recovery.py --action detect`
- Monitor logs for missing order warnings
- Set up alerts for orphaned orders

### 2. Recovery Timing

- Run recovery during low-activity periods
- Avoid recovery during active trading sessions
- Test recovery on a demo account first

### 3. Verification

- Always verify recovery results
- Check cycle statistics after recovery
- Monitor order associations in the UI

### 4. Prevention

- Ensure stable network connectivity
- Use proper error handling in order placement
- Implement retry mechanisms for failed operations
- Regular system health checks

## Troubleshooting

### Common Issues

1. **No Missing Orders Detected**
   - Check MT5 connection
   - Verify magic number configuration
   - Ensure symbol matches

2. **Recovery Fails**
   - Check database connectivity
   - Verify API client authentication
   - Review error logs

3. **Orders Still Missing After Recovery**
   - Check for network issues
   - Verify order ownership (magic number)
   - Review cycle matching criteria

### Debug Steps

1. **Enable Verbose Logging**
   ```bash
   python missing_order_recovery.py --action detect --verbose
   ```

2. **Check Individual Cycle Status**
   ```python
   cycle.debug_order_status()
   ```

3. **Verify MT5 Connection**
   ```python
   positions = bot.meta_trader.get_all_positions()
   print(f"MT5 positions: {len(positions)}")
   ```

4. **Check Database Status**
   ```python
   cycle._update_cycle_in_database()
   ```

## Integration with Flutter UI

The recovery system integrates with the Flutter UI through:

- **Real-time Updates**: Recovery actions update the UI immediately
- **Event Notifications**: Users are notified of recovery actions
- **Status Display**: UI shows recovery status and results
- **Manual Triggers**: UI can trigger recovery operations

## Performance Considerations

- **Efficient Detection**: Only scans relevant positions (magic number + symbol)
- **Intelligent Matching**: Uses scoring system for optimal order-cycle matching
- **Batch Processing**: Handles multiple missing orders efficiently
- **Database Optimization**: Minimizes database operations during recovery

## Future Enhancements

- **Machine Learning**: Improved order-cycle matching using ML algorithms
- **Predictive Detection**: Proactive detection of potential missing orders
- **Advanced Analytics**: Detailed recovery statistics and trends
- **Automated Scheduling**: Scheduled recovery operations
- **Multi-Exchange Support**: Support for other trading platforms

## Support

For issues or questions about the Missing Order Recovery System:

1. Check the logs for detailed error information
2. Review this documentation
3. Test with the command-line utility
4. Contact the development team with specific error messages

---

**Note**: This system is designed to be robust and safe, but always verify recovery results and test in a demo environment before using in production.
