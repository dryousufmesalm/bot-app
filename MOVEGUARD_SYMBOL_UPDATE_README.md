# MoveGuard Symbol Update Functionality

## Overview

The MoveGuard strategy now supports dynamic symbol updates without requiring a restart. This allows users to change the trading symbol for their MoveGuard bots while maintaining all existing configuration and state.

## Features

- **Dynamic Symbol Updates**: Change symbols on-the-fly without restarting the strategy
- **Symbol Validation**: Automatic validation of new symbols against MetaTrader
- **Component Re-initialization**: All symbol-dependent components are automatically re-initialized
- **State Management**: Symbol-specific internal state is properly reset
- **Error Handling**: Graceful handling of invalid symbols with fallback to current symbol
- **Comprehensive Logging**: Detailed logging of all symbol update operations

## How It Works

### 1. Symbol Update Process

When a symbol update is requested:

1. **Validation**: The new symbol is validated against MetaTrader
   - Checks if symbol exists
   - Verifies symbol has valid pip values
   - Confirms symbol is accessible for trading

2. **Update**: If validation passes:
   - Internal symbol reference is updated
   - Symbol-dependent components are re-initialized
   - MetaTrader symbol information is refreshed
   - Symbol-specific state is reset

3. **Fallback**: If validation fails:
   - Current symbol is maintained
   - Error is logged
   - Strategy continues operating with existing symbol

### 2. Components Re-initialized

The following components are automatically re-initialized when the symbol changes:

- **EnhancedZoneDetection**: Zone boundary calculations
- **EnhancedOrderManager**: Order placement and management  
- **DirectionController**: Trading direction management

### 3. State Reset

Symbol-specific internal state is reset during updates:

- Market data tracking
- Zone state tracking
- Grid state tracking
- Zone movement history

**Note**: Active cycles are NOT automatically closed during symbol updates. Users should manage cycle transitions manually.

## Usage

### Command Line (update_bot_config.py)

```bash
# Update symbol for a specific bot
python update_bot_config.py <bot_id> --symbol GBPUSD

# Update symbol along with other parameters
python update_bot_config.py <bot_id> --symbol EURUSD --lot-size 0.02 --zone-threshold 250

# Update from configuration file
python update_bot_config.py <bot_id> --config-file config.json
```

### Configuration File Example

```json
{
  "symbol": "GBPUSD",
  "lot_size": 0.02,
  "zone_threshold_pips": 250,
  "order_interval_pips": 75,
  "max_cycles": 5
}
```

### API Integration

The symbol update functionality is automatically available when updating bot configuration through the API:

```python
# Update bot configuration including symbol
config_updates = {
    "symbol": "USDJPY",
    "lot_size": 0.01,
    "zone_threshold_pips": 300
}

# The strategy will automatically handle symbol updates
bot.strategy._initialize_strategy_configuration(config_updates)
```

## Supported Symbols

The strategy supports all symbols available in MetaTrader, including:

- **Major Pairs**: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD
- **Minor Pairs**: EURGBP, EURJPY, GBPJPY, etc.
- **Exotic Pairs**: EURTRY, USDZAR, etc.
- **Indices**: SPX500, NAS100, etc.
- **Commodities**: XAUUSD (Gold), XAGUSD (Silver), etc.

## Validation Requirements

For a symbol to be accepted, it must meet these criteria:

1. **Existence**: Symbol must exist in MetaTrader
2. **Pip Value**: Symbol must have valid point values
3. **Accessibility**: Symbol must be accessible for trading operations
4. **Bid/Ask**: Symbol must return valid bid and ask prices

## Error Handling

### Invalid Symbol

If an invalid symbol is provided:

```
❌ Symbol 'INVALID_SYMBOL' not found in MetaTrader
❌ Failed to update symbol to 'INVALID_SYMBOL' - keeping current symbol 'EURUSD'
```

### Component Re-initialization Failure

If component re-initialization fails:

```
❌ Error re-initializing symbol-dependent components: [error details]
❌ Error updating symbol: [error details]
```

### MetaTrader Issues

If MetaTrader operations fail:

```
❌ Cannot get bid/ask for symbol 'EURUSD': [error details]
❌ Error updating MetaTrader symbol info: [error details]
```

## Testing

### Run Test Suite

```bash
python test_symbol_update.py
```

### Test Scenarios

The test suite covers:

1. **Valid Symbol Updates**: EURUSD → GBPUSD → USDJPY
2. **Invalid Symbol Handling**: Graceful fallback for invalid symbols
3. **Component Re-initialization**: Verification of component updates
4. **State Management**: Confirmation of state reset operations

## Logging

### Symbol Update Logs

```
🔄 MoveGuard symbol updated: EURUSD → GBPUSD
✅ Symbol 'GBPUSD' validation successful
🔄 Re-initializing symbol-dependent components for symbol: GBPUSD
✅ EnhancedZoneDetection re-initialized
✅ EnhancedOrderManager re-initialized
✅ DirectionController re-initialized
✅ Symbol-specific state reset for GBPUSD
✅ All symbol-dependent components re-initialized for GBPUSD
✅ MetaTrader symbol info updated for GBPUSD: bid=1.2650, ask=1.2652
```

### Error Logs

```
❌ Symbol 'INVALID_SYMBOL' not found in MetaTrader
❌ Failed to update symbol to 'INVALID_SYMBOL' - keeping current symbol 'EURUSD'
```

## Best Practices

### 1. Symbol Selection

- Choose symbols with good liquidity and tight spreads
- Avoid symbols with high volatility during market open/close
- Consider trading hours for the selected symbol

### 2. Update Timing

- Update symbols during low market activity periods
- Avoid updates during major news events
- Consider timezone differences for global markets

### 3. Cycle Management

- Close active cycles before changing symbols if appropriate
- Monitor existing cycles after symbol changes
- Consider symbol-specific trading characteristics

### 4. Testing

- Test symbol updates in demo environment first
- Verify all components re-initialize correctly
- Monitor strategy performance after symbol changes

## Troubleshooting

### Common Issues

1. **Symbol Not Found**
   - Verify symbol exists in MetaTrader
   - Check symbol spelling and format
   - Ensure MetaTrader is connected

2. **Component Re-initialization Failures**
   - Check component dependencies
   - Verify configuration parameters
   - Review error logs for specific issues

3. **MetaTrader Connection Issues**
   - Verify MetaTrader connection
   - Check symbol availability
   - Ensure proper permissions

### Debug Mode

Enable detailed logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

Planned improvements for symbol update functionality:

1. **Batch Symbol Updates**: Update multiple symbols simultaneously
2. **Symbol Presets**: Pre-configured symbol configurations
3. **Automatic Symbol Selection**: AI-powered symbol selection based on market conditions
4. **Symbol Performance Tracking**: Monitor performance across different symbols
5. **Symbol Rotation**: Automatic symbol rotation based on performance metrics

## Support

For issues or questions regarding the MoveGuard symbol update functionality:

1. Check the logs for detailed error information
2. Verify MetaTrader connection and symbol availability
3. Test with known valid symbols first
4. Review this documentation for usage examples

## Version History

- **v1.0**: Initial symbol update functionality
  - Basic symbol validation
  - Component re-initialization
  - State management
  - Error handling and logging

