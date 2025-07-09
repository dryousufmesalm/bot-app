# Tech Context - Technology Stack & Development Environment

## Dual-Platform Technology Stack

### Python Desktop Application (Primary Trading Interface)

#### Core Framework & UI
- **Flet 0.25.2**: Modern Python UI framework for desktop applications
- **FletX 0.2.0**: Enhanced navigation and routing for Flet applications
- **Material Design**: Consistent UI components and theming

#### Trading & Market Data
- **MetaTrader5 5.0.4687**: Official MetaTrader 5 Python API integration
- **PythonMetaTrader5 1.0.9**: Additional MetaTrader 5 utilities
- **Real-time Data Processing**: Live market data streaming and analysis

#### Database & Data Management
- **SQLAlchemy 2.0.37**: Modern Python SQL toolkit and ORM
- **SQLModel 0.0.22**: Pydantic-based ORM for type-safe database operations
- **SQLite**: Local high-performance database for strategy data
- **Migration System**: Automated database schema evolution

#### Scientific Computing & Analysis
- **NumPy 2.1.3**: Numerical computing for trading algorithms
- **Pandas 2.2.3**: Data analysis and manipulation
- **SciPy 1.15.1**: Scientific computing for advanced calculations
- **Matplotlib 3.9.4**: Data visualization and charting

#### Advanced Trading Libraries
- **CVXPY 1.6.0**: Convex optimization for portfolio management
- **Emcee 3.1.6**: MCMC sampling for statistical analysis
- **Corner 2.2.3**: Bayesian analysis and visualization

#### Authentication & Security
- **PocketBase 0.12.3**: Cloud database and authentication
- **Python-dotenv 1.0.1**: Environment variable management
- **Secure credential storage**: Encrypted credential management

### Flutter Mobile/Web Application (Cross-Platform Interface)

#### Core Framework
- **Flutter SDK 3.7.0+**: Google's UI toolkit for cross-platform development
- **Dart**: Modern programming language optimized for UI development

#### State Management & Architecture
- **Riverpod 2.6.1**: Reactive state management with compile-time safety
- **Hooks Riverpod 2.6.1**: Flutter hooks integration for Riverpod
- **Riverpod Annotation 2.6.1**: Code generation for type-safe providers

#### UI & Design System
- **Material Design 3**: Modern Material Design implementation
- **Flex Color Scheme 8.0.2**: Advanced theming and color management
- **Flutter Animate**: Smooth animations and transitions
- **Animate Do 4.2.0**: Pre-built animation components

#### Navigation & Routing
- **Go Router 14.6.3**: Declarative routing with deep linking support
- **Navigation 2.0**: Modern Flutter navigation patterns

#### Data Persistence & Storage
- **PocketBase 0.22.0**: Cloud-first database with real-time sync
- **Shared Preferences 2.3.5**: Local key-value storage
- **Get Storage 2.1.1**: High-performance local storage
- **Flutter Secure Storage 9.2.4**: Encrypted local storage

#### Development & Debugging
- **Talker Flutter 4.6.3**: Advanced logging and debugging
- **Sentry Flutter 8.14.1**: Error tracking and performance monitoring
- **Flutter Launcher Icons 0.14.3**: Automated app icon generation

### Shared Cloud Infrastructure

#### Backend Services
- **PocketBase Cloud**: Real-time database and authentication service
  - **API URL**: `https://pdapp.fppatrading.com` (Production)
  - **Demo URL**: `https://demo.fppatrading.com` (Staging)
  - **Features**: Real-time sync, user authentication, file storage

#### MCP (Model Context Protocol) Integration
- **PocketBase MCP Server**: AI-assisted development tools
- **Node.js Runtime**: MCP server execution environment
- **Admin Token Authentication**: Secure API access for development

### Development Tools & Environment

#### AI-Assisted Development
- **Memory Bank v0.7-beta**: Hierarchical workflow management system
- **Custom Modes**: VAN, PLAN, CREATIVE, IMPLEMENT, REFLECT, ARCHIVE
- **Cursor Integration**: AI-powered development environment
- **MCP Server**: Real-time database access for development

#### Version Control & Deployment
- **Git**: Distributed version control
- **GitHub**: Repository hosting and collaboration
- **Multi-platform Deployment**: Windows, Web, iOS, Android

#### Testing & Quality Assurance
- **Flutter Test**: Comprehensive testing framework for Flutter
- **Python unittest**: Unit testing for Python components
- **Integration Testing**: End-to-end testing across platforms
- **100% Test Coverage**: Achieved for critical trading components

### Package Management & Dependencies

#### Python Dependencies (87 packages)
- **Core**: flet, sqlalchemy, pocketbase, metatrader5
- **Scientific**: numpy, pandas, scipy, matplotlib
- **Development**: python-dotenv, pydantic, requests
- **Trading**: cvxpy, emcee, corner (advanced analytics)

#### Flutter Dependencies (Modular Package Architecture)
```
Core Packages:
├── app_logger/          # Centralized logging system
├── app_theme/           # Design system and theming
├── auth/                # Authentication management
├── globals/             # Global state and utilities
├── kv_store/            # Key-value storage abstraction
├── notifications/       # Push notifications and alerts
└── useful_widgets/      # Reusable UI components

Feature Packages:
├── events_service/      # Event handling and processing
├── pocketbase_service/  # PocketBase integration
└── m_table/            # Advanced table components

Strategy Packages:
├── cycles_trader/       # Cycles trading strategy
├── adaptive_hedge/      # Adaptive hedging strategy
└── stocks_trader/       # Stock trading strategy
```

### Development Environment Setup

#### Prerequisites
- **Python 3.7+**: Modern Python runtime
- **Flutter SDK 3.7.0+**: Flutter development toolkit
- **Node.js**: For MCP server execution
- **Virtual Environment**: Isolated Python environment

#### Installation Commands
```bash
# Python Dependencies
pip install -r requirements.txt

# Flutter Dependencies
flutter pub get

# MCP Server Setup
cd mcp-servers/pocketbase-mcp
npm install
npm run build
```

#### Environment Configuration
- **Python Virtual Environment**: Isolated dependency management
- **Environment Variables**: Secure configuration management
- **Multi-platform Support**: Windows, macOS, Linux, Web, Mobile

### Performance & Scalability

#### Optimization Features
- **Local-first Processing**: High-speed local database operations
- **Cloud Synchronization**: Real-time data sync across platforms
- **Efficient State Management**: Riverpod for optimal Flutter performance
- **Memory Management**: Optimized resource usage across platforms

#### Monitoring & Analytics
- **Sentry Integration**: Real-time error tracking and performance monitoring
- **Comprehensive Logging**: Multi-level logging across all components
- **Performance Metrics**: Real-time system performance monitoring

This comprehensive technology stack ensures professional-grade performance, reliability, and scalability for both desktop trading and mobile monitoring applications.
