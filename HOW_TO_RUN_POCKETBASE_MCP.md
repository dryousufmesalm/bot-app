# How to Run PocketBase MCP Server with Cline

## Current Status: ✅ Server Built and Ready

**Location**: `D:\Code\Pocket-base patrick display\Patrick-Display-1.0.71\Patrick-Display-1.0.71\mcp-servers\pocketbase-mcp\build\index.js`

## Prerequisites

### 1. Get Your PocketBase Admin Token 🔑

**IMPORTANT**: You need a real admin token from your PocketBase instance.

1. **Open PocketBase Admin**: https://pdapp.fppatrading.com/_/
2. **Login** with your admin credentials
3. **Go to Settings → API Keys**
4. **Create new API key** with admin permissions
5. **Copy the token** (you'll need this)

## Running Options

### Option 1: Quick Test (Manual)

Test the server with a temporary token:

```powershell
# Navigate to the server directory
cd "D:\Code\Pocket-base patrick display\Patrick-Display-1.0.71\Patrick-Display-1.0.71\mcp-servers\pocketbase-mcp"

# Set environment variables and run
$env:POCKETBASE_API_URL="https://pdapp.fppatrading.com"
$env:POCKETBASE_ADMIN_TOKEN="YOUR_REAL_TOKEN_HERE"
node build/index.js
```

**Replace `YOUR_REAL_TOKEN_HERE` with your actual admin token.**

### Option 2: Cline Integration (Recommended)

Since you're using **Cline**, you need to configure it for Cline specifically.

#### Step 1: Find Cline MCP Settings

Cline typically uses one of these locations:
- `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

#### Step 2: Create/Update Cline MCP Settings

Create or update the `cline_mcp_settings.json` file:

```json
{
  "mcpServers": {
    "pocketbase-mcp": {
      "command": "node",
      "args": ["D:/Code/Pocket-base patrick display/Patrick-Display-1.0.71/Patrick-Display-1.0.71/mcp-servers/pocketbase-mcp/build/index.js"],
      "env": {
        "POCKETBASE_API_URL": "https://pdapp.fppatrading.com",
        "POCKETBASE_ADMIN_TOKEN": "YOUR_REAL_ADMIN_TOKEN_HERE"
      },
      "disabled": false,
      "autoApprove": [
        "fetch_record",
        "list_collections",
        "get_collection_schema",
        "list_logs",
        "get_log",
        "get_logs_stats",
        "list_cron_jobs"
      ]
    }
  }
}
```

#### Step 3: Restart Cline

1. **Close Cline/VS Code**
2. **Restart the application**
3. **Cline should detect the new MCP server**

### Option 3: VS Code Extension Settings

If Cline is integrated with VS Code, you might need to add MCP settings to VS Code settings:

1. **Open VS Code Settings** (Ctrl+,)
2. **Search for "cline"**
3. **Look for MCP server settings**
4. **Add the PocketBase MCP server configuration**

## Testing the Connection

Once configured, test with these commands in Cline:

```
List all collections in my PocketBase
```

```
Show me the schema for the users collection
```

```
List records from the accounts collection
```

## Available Commands

Once running, you can use these PocketBase operations:

### Basic Operations
- **List Collections**: "Show me all PocketBase collections"
- **Get Schema**: "What's the schema for the [collection] collection?"
- **List Records**: "List records from [collection]"
- **Fetch Record**: "Get record [id] from [collection]"

### Advanced Operations
- **Create Records**: "Create a new record in [collection] with [data]"
- **Update Records**: "Update record [id] in [collection] with [data]"
- **File Operations**: "Upload file to [collection] record [id]"
- **Logs**: "Show me recent PocketBase API logs"

### Trading-Specific Operations
- **Account Management**: "List all trading accounts"
- **Bot Monitoring**: "Show me all active bots"
- **Strategy Analysis**: "List all trading strategies"
- **Event Tracking**: "Show recent trading events"
- **Cycle Management**: "List all trading cycles"

## Troubleshooting

### Common Issues

1. **"POCKETBASE_ADMIN_TOKEN environment variable is required"**
   - ✅ **Solution**: Get real admin token from PocketBase admin panel

2. **"Connection refused" or "Network error"**
   - ✅ **Check**: PocketBase URL is accessible (https://pdapp.fppatrading.com)
   - ✅ **Test**: Open the URL in browser

3. **"Authentication failed"**
   - ✅ **Verify**: Admin token is correct and has admin permissions
   - ✅ **Check**: Token hasn't expired

4. **"Server not found in Cline"**
   - ✅ **Restart**: Close and reopen Cline/VS Code
   - ✅ **Check**: Configuration file path is correct
   - ✅ **Verify**: JSON syntax is valid

### Testing Steps

1. **Test PocketBase Access**:
   ```powershell
   # Test if PocketBase is accessible
   curl https://pdapp.fppatrading.com/api/health
   ```

2. **Test Admin Token**:
   ```powershell
   # Replace YOUR_TOKEN with your actual token
   curl -H "Authorization: Admin YOUR_TOKEN" https://pdapp.fppatrading.com/api/collections
   ```

3. **Test MCP Server**:
   ```powershell
   # Run the server manually to see if it starts
   $env:POCKETBASE_API_URL="https://pdapp.fppatrading.com"
   $env:POCKETBASE_ADMIN_TOKEN="YOUR_TOKEN"
   node build/index.js
   ```

## Next Steps

1. ✅ **Get Admin Token**: From PocketBase admin panel
2. ⏳ **Configure Cline**: Add MCP server to Cline settings
3. ⏳ **Test Integration**: Try basic commands
4. ⏳ **Use for Development**: Integrate with Advanced Cycles Trader project

## Benefits for Your Project

Once running, the PocketBase MCP server will help with:

- **Real-time Data Access**: Query trading data directly
- **Development Efficiency**: No need to write API code for basic operations
- **Debugging**: Easy access to logs and system state
- **Data Management**: Create, update, and manage records easily
- **Strategy Monitoring**: Track Advanced Cycles Trader performance

The MCP server will be especially valuable for monitoring and debugging your Advanced Cycles Trader implementation! 