# Patrick Display - Dual-Platform Trading Ecosystem

Patrick Display is a comprehensive dual-platform trading ecosystem consisting of a Python desktop application and Flutter cross-platform client, designed for professional algorithmic trading with MetaTrader 5 integration.

## 🏗️ Architecture Overview

### 🖥️ Bot App (Python Desktop Application)
**Primary Trading Interface**
- **Framework**: Flet 0.25.2 with FletX 0.2.0 navigation
- **Purpose**: Direct MetaTrader 5 integration and strategy execution
- **Core Features**: Advanced algorithmic trading strategies, real-time market data processing
- **Database**: SQLAlchemy 2.0.37 with local SQLite + cloud sync

### 📱 Flutter App (Cross-Platform Client)
**Monitoring & Management Interface**
- **Framework**: Flutter 3.32.4 with Dart 3.8.1
- **Purpose**: Real-time monitoring, account management, notifications
- **Core Features**: Multi-platform support, responsive UI, strategy monitoring

## 🚀 Trading Strategies

- **Advanced Cycles Trader (ACT)**: Zone-based reversal trading with sophisticated order management
- **Cycle Trader (CT)**: Traditional cycle-based trading approach with automated entry/exit
- **Adaptive Hedging (AH)**: Dynamic hedging strategy for risk mitigation
- **Stock Trader**: Equity-focused trading algorithms with portfolio management

## 🛠️ Technology Stack

- **Backend**: Python 3.x with Flet, SQLAlchemy, MetaTrader5 API
- **Database**: SQLite (local) + PocketBase/Supabase (cloud sync)
- **UI Framework**: Flet for desktop, Flutter for cross-platform
- **Cloud Services**: PocketBase for real-time sync, Supabase for advanced features
- **Development**: Memory Bank v0.7-beta for AI-assisted development

## 📋 Prerequisites

- Python 3.8+
- MetaTrader 5 Terminal
- Virtual environment (recommended)

## 🔧 Setup

### 1. Clone the repository
```bash
git clone <repository-url>
cd patrick-display
```

### 2. Create and activate virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### 4. Configure environment
1. Copy `sample_config.json` to `config.json`
2. Update configuration with your MetaTrader 5 credentials
3. Set up PocketBase/Supabase connection details

## 🚀 Running the Application

### Desktop Bot App
```bash
flet run main.py
```

### Development Mode
```bash
python main.py
```

## 📁 Project Structure

```
├── Api/                    # API handlers and event systems
├── Bots/                   # Trading bot implementations
├── DB/                     # Database models and repositories
├── MetaTrader/             # MT5 integration utilities
├── Strategy/               # Trading strategy implementations
├── Views/                  # UI components and views
├── helpers/                # Utility functions and middleware
├── memory-bank/            # AI development context (Memory Bank v0.7-beta)
├── mcp-servers/           # MCP server integrations
└── cycles/                # Cycle management implementations
```

## 🔐 Security

- Never commit credentials or API keys
- Use environment variables for sensitive configuration
- Keep trading data and logs in ignored directories
- Regularly update dependencies for security patches

## 🤝 Development Workflow

This project uses Memory Bank v0.7-beta for AI-assisted development:
- **VAN Mode**: Project initialization and complexity assessment
- **PLAN Mode**: Detailed implementation planning
- **CREATIVE Mode**: Design decisions for complex components
- **IMPLEMENT Mode**: Systematic code implementation
- **REFLECT Mode**: Review and lessons learned
- **ARCHIVE Mode**: Comprehensive documentation

## 📊 Features

- ✅ Real-time MetaTrader 5 integration
- ✅ Multiple algorithmic trading strategies
- ✅ Advanced order management and risk controls
- ✅ Cloud synchronization across devices
- ✅ Comprehensive logging and monitoring
- ✅ Multi-account support
- ✅ Zone-based trading analysis

## 🐛 Troubleshooting

### Common Issues
1. **MetaTrader Connection**: Ensure MT5 is running and API is enabled
2. **Database Issues**: Check database permissions and file paths
3. **Cloud Sync**: Verify PocketBase/Supabase credentials and connectivity

### Logging
Check the application logs in:
- `logs/` directory (if configured)
- Console output during development
- MT5 terminal logs for trading-specific issues

## 📄 License

This project is proprietary trading software. Unauthorized distribution or modification is prohibited.

## ⚠️ Disclaimer

This software is for educational and research purposes. Trading involves substantial risk of loss. Users are responsible for their own trading decisions and any financial consequences.
