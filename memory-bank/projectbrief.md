# Project Brief: Patrick Display Dual-Platform Trading Ecosystem

## Overview

Patrick Display is a comprehensive dual-platform trading ecosystem consisting of a Python desktop application and a Flutter cross-platform client, designed for professional algorithmic trading with MetaTrader 5 integration.

## Dual-Application Architecture

### 🖥️ Bot App (Python Desktop Application)
**Primary Trading Interface**
- **Framework**: Flet 0.25.2 with FletX 0.2.0 navigation
- **Purpose**: Direct MetaTrader 5 integration and strategy execution
- **Core Features**: Advanced algorithmic trading strategies, real-time market data processing
- **Database**: SQLAlchemy 2.0.37 with local SQLite + PocketBase cloud sync

### 📱 Flutter App (Cross-Platform Client)
**Monitoring & Management Interface**
- **Framework**: Flutter 3.32.4 with Dart 3.8.1
- **Purpose**: Real-time monitoring, account management, notifications
- **Core Features**: Multi-platform support, responsive UI, strategy monitoring
- **Architecture**: Modular package system with 13 custom packages

## Key Trading Strategies

### Advanced Cycles Trader (ACT)
- Zone-based reversal trading with sophisticated order management
- Component-based architecture with specialized engines
- Real-time monitoring and adaptive position management

### Cycle Trader (CT)
- Traditional cycle-based trading approach
- Automated entry/exit based on market cycles
- Risk management with stop-loss and take-profit

### Adaptive Hedging (AH)
- Dynamic hedging strategy for risk mitigation
- Multi-position management and correlation analysis
- Advanced loss recovery mechanisms

### Stock Trader
- Equity-focused trading algorithms
- Market analysis and trend following
- Portfolio management capabilities

## Technology Integration

### Cloud Infrastructure
- **PocketBase**: Real-time data synchronization between applications
- **Supabase**: Advanced database features and real-time subscriptions
- **MCP Servers**: Custom integration for enhanced functionality

### Development Tools
- **Python**: 87 dependencies managed via UV/pip
- **Flutter**: 162 dependencies with workspace management
- **Visual Studio**: Windows development support
- **Git**: Version control with comprehensive .gitignore

## Project Status: OPERATIONAL ✅

### Bot App Status
- ✅ **Core Framework**: Fully functional Flet desktop application
- ✅ **Trading Strategies**: All 4 strategies implemented and tested
- ✅ **MetaTrader Integration**: Live trading capabilities operational
- ✅ **Database Layer**: SQLAlchemy with repository pattern complete

### Flutter App Status
- ✅ **Build System**: Windows build issues resolved (12/23/2024)
- ✅ **Core Architecture**: Modular package system operational
- ✅ **UI Framework**: Material Design 3 with responsive layouts
- ✅ **State Management**: Riverpod with hooks integration complete

## Current Development Focus

### Immediate Priorities
1. **Memory Bank Update**: Comprehensive documentation of both applications
2. **Cross-Platform Testing**: Ensure Flutter app works on all target platforms
3. **Integration Testing**: Verify data sync between bot app and Flutter app
4. **Performance Optimization**: Monitor real-time data processing efficiency

### Next Phase Opportunities
1. **Enhanced Notifications**: Re-enable flutter_local_notifications with proper Windows support
2. **Secure Storage**: Implement proper flutter_secure_storage for production
3. **Advanced Analytics**: Real-time trading performance dashboards
4. **Mobile Features**: Push notifications and mobile-specific trading tools

## Architecture Principles

### Separation of Concerns
- **Bot App**: Heavy computation, direct trading, strategy execution
- **Flutter App**: User interface, monitoring, configuration, notifications

### Data Flow
- **Real-time Sync**: PocketBase ensures consistent state across applications
- **Local Performance**: SQLite for high-speed bot app operations
- **Cloud Backup**: All critical data replicated to cloud infrastructure

### Security & Reliability
- **Multi-layer Authentication**: MetaTrader + PocketBase + Biometric (mobile)
- **Error Handling**: Comprehensive logging and recovery mechanisms
- **Data Integrity**: Transactional operations with rollback capabilities

This dual-platform approach provides the best of both worlds: the power and speed of a native desktop application for trading execution, combined with the flexibility and accessibility of a modern cross-platform mobile/web client for monitoring and management.
