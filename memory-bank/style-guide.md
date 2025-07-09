# Style Guide - Coding Standards & Patterns

## Overview

This style guide documents the coding standards, patterns, and conventions used across the Patrick Display dual-platform trading ecosystem.

## Python Desktop Application Standards

### Code Organization
```python
# File structure pattern
/Strategy/
  ├── strategy.py              # Base classes
  ├── AdvancedCyclesTrader.py  # Main strategy implementations
  └── components/              # Modular components
      ├── __init__.py
      ├── zone_detection_engine.py
      ├── advanced_order_manager.py
      └── direction_controller.py
```

### Class Design Patterns
```python
# Abstract base class pattern
class Strategy(ABC):
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize strategy components"""
        pass
    
    @abstractmethod
    async def handle_event(self, event) -> bool:
        """Handle trading events"""
        pass

# Component injection pattern
class AdvancedCyclesTrader(Strategy):
    def __init__(self, meta_trader, config, client, symbol, bot):
        # Core dependencies
        self.meta_trader = meta_trader
        self.config = config
        
        # Component initialization
        self.zone_engine = ZoneDetectionEngine(symbol, threshold_pips)
        self.order_manager = AdvancedOrderManager(meta_trader, symbol, magic)
        self.direction_controller = DirectionController(symbol)
```

### Error Handling Standards
```python
# Comprehensive error handling pattern
try:
    result = await trading_operation()
    logger.info(f"Operation successful: {result}")
    return result
    
except TradingError as e:
    logger.error(f"Trading error in {operation_name}: {e}")
    await handle_trading_error(e)
    return None
    
except Exception as e:
    logger.error(f"Unexpected error in {operation_name}: {e}")
    logger.exception("Full error details:")
    await handle_system_error(e)
    return None
```

### Database Patterns
```python
# Repository pattern implementation
class ACTRepo:
    def __init__(self, engine):
        self.engine = engine
    
    def get_or_create_loss_tracker(self, bot_id: str, account_id: str, symbol: str):
        """Get existing or create new loss tracker"""
        with Session(self.engine) as session:
            # Implementation with proper session management
            pass

# Model definition pattern
class GlobalLossTracker(SQLModel, table=True):
    __tablename__ = "global_loss_tracker"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    bot_id: str = Field(index=True)
    account_id: str = Field(index=True)
    symbol: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Logging Standards
```python
# Consistent logging pattern
from Views.globals.app_logger import app_logger as logger

# Log levels and formatting
logger.info(f"Strategy initialized for {symbol}")
logger.warning(f"Threshold breach detected at {price}")
logger.error(f"Order placement failed: {error}")
logger.debug(f"Component state: {component_state}")
```

## Flutter Application Standards

### Package Architecture
```
packages/
├── Core Packages (shared functionality)
│   ├── app_logger/           # Centralized logging
│   ├── app_theme/            # Design system
│   ├── auth/                 # Authentication
│   └── globals/              # Global utilities
├── Feature Packages (specific features)
│   ├── events_service/       # Event handling
│   ├── notifications/        # Push notifications
│   └── useful_widgets/       # Reusable components
└── Strategy Packages (trading algorithms)
    ├── cycles_trader/        # Cycles trading
    ├── adaptive_hedge/       # Hedging strategies
    └── stocks_trader/        # Stock trading
```

### State Management Pattern
```dart
// Riverpod provider pattern
@riverpod
class TradingDataNotifier extends _$TradingDataNotifier {
  @override
  Future<TradingData> build() async {
    return await _loadTradingData();
  }
  
  Future<void> updateData(TradingData data) async {
    state = const AsyncValue.loading();
    try {
      await _saveTradingData(data);
      state = AsyncValue.data(data);
    } catch (error) {
      state = AsyncValue.error(error, StackTrace.current);
    }
  }
}

// Widget consumption pattern
class TradingDashboard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tradingData = ref.watch(tradingDataNotifierProvider);
    
    return tradingData.when(
      data: (data) => _buildDashboard(data),
      loading: () => const CircularProgressIndicator(),
      error: (error, stack) => ErrorWidget(error),
    );
  }
}
```

### UI Component Standards
```dart
// Consistent component structure
class TradingCard extends StatelessWidget {
  const TradingCard({
    Key? key,
    required this.title,
    required this.data,
    this.onTap,
  }) : super(key: key);
  
  final String title;
  final TradingData data;
  final VoidCallback? onTap;
  
  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: _buildContent(),
        ),
      ),
    );
  }
}
```

## Database Design Patterns

### Table Naming Conventions
- **Snake case**: `global_loss_tracker`, `ct_cycles`, `ah_cycles`
- **Descriptive names**: Clear purpose and scope
- **Strategy prefixes**: `act_`, `ct_`, `ah_` for strategy-specific tables

### Column Standards
```sql
-- Standard columns for all tables
id INTEGER PRIMARY KEY AUTOINCREMENT,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

-- Foreign key naming
bot_id TEXT NOT NULL,
account_id TEXT NOT NULL,
symbol TEXT NOT NULL,

-- Index creation
CREATE INDEX idx_bot_account_symbol ON table_name(bot_id, account_id, symbol);
```

### Migration Patterns
```python
# Migration function pattern
def migrate_table_name():
    """Migration description"""
    try:
        with Session(engine) as session:
            # Check if migration needed
            # Execute migration
            # Verify migration success
            logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
```

## API Design Standards

### PocketBase Integration
```python
# Consistent API client usage
class API:
    def __init__(self, base_url, token=None):
        self.base_url = base_url
        self.client = PocketBase(self.base_url)
    
    def get_records(self, collection: str, filter_query: str = ""):
        """Get records with consistent error handling"""
        try:
            return self.client.collection(collection).get_full_list(200, {
                "filter": filter_query
            })
        except Exception as e:
            logging.error(f"Failed to get {collection} records: {e}")
            return []
```

### REST API Patterns
- **Consistent endpoints**: `/api/v1/resource`
- **Standard HTTP methods**: GET, POST, PUT, DELETE
- **Error response format**: `{"error": "message", "code": "ERROR_CODE"}`
- **Pagination**: `{"data": [...], "total": 100, "page": 1, "limit": 20}`

## Testing Standards

### Python Testing
```python
# Test class structure
class TestAdvancedCyclesTrader:
    def setup_method(self):
        """Setup test environment"""
        self.trader = create_test_trader()
    
    def test_component_initialization(self):
        """Test component initialization"""
        assert self.trader.zone_engine is not None
        assert self.trader.order_manager is not None
        assert self.trader.direction_controller is not None
    
    def test_zone_detection(self):
        """Test zone detection logic"""
        # Test implementation
        pass
```

### Flutter Testing
```dart
// Widget test pattern
void main() {
  group('TradingCard Widget Tests', () {
    testWidgets('displays trading data correctly', (WidgetTester tester) async {
      final testData = TradingData(/* test data */);
      
      await tester.pumpWidget(
        MaterialApp(
          home: TradingCard(
            title: 'Test Card',
            data: testData,
          ),
        ),
      );
      
      expect(find.text('Test Card'), findsOneWidget);
      expect(find.byType(TradingCard), findsOneWidget);
    });
  });
}
```

## Documentation Standards

### Code Documentation
```python
def calculate_take_profit(self, loss_amount: float, lot_size: float) -> float:
    """
    Calculate take profit adjusted for accumulated losses.
    
    Args:
        loss_amount: Total accumulated loss amount
        lot_size: Current position lot size
        
    Returns:
        Adjusted take profit value in pips
        
    Raises:
        ValueError: If loss_amount or lot_size is negative
    """
```

### README Structure
```markdown
# Component Name

## Overview
Brief description of component purpose

## Installation
Setup instructions

## Usage
Code examples and usage patterns

## API Reference
Detailed API documentation

## Testing
How to run tests

## Contributing
Contribution guidelines
```

## Performance Standards

### Response Time Targets
- **Critical trading operations**: < 1 second
- **UI interactions**: < 200ms
- **Database queries**: < 100ms
- **API calls**: < 2 seconds

### Memory Management
- **Component cleanup**: Proper disposal of resources
- **Event unsubscription**: Clean event listener removal
- **Database connections**: Proper session management
- **Memory leaks**: Regular monitoring and prevention

## Security Standards

### Authentication
- **Token management**: Secure token storage and refresh
- **Session handling**: Proper session lifecycle management
- **API security**: Rate limiting and input validation

### Data Protection
- **Sensitive data**: Encryption for credentials and financial data
- **Logging**: No sensitive data in logs
- **Environment variables**: Secure configuration management

This style guide ensures consistency, maintainability, and professional quality across the entire Patrick Display trading platform ecosystem. 