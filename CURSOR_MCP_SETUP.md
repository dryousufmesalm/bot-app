# PocketBase MCP Server Setup for Cursor

## ✅ Server Status: TESTED AND WORKING

Your PocketBase MCP server is running successfully with your admin token!

## Cursor MCP Configuration

### Step 1: Find Cursor MCP Settings File

Cursor uses a different configuration approach than Cline. Look for:

**Windows Locations:**
- `%APPDATA%\Cursor\User\globalStorage\cursor-ai.cursor\mcp_settings.json`
- `%USERPROFILE%\AppData\Roaming\Cursor\User\globalStorage\cursor-ai.cursor\mcp_settings.json`
- `%LOCALAPPDATA%\Programs\Cursor\resources\app\mcp_settings.json`

### Step 2: Create/Update MCP Settings

Create or update the MCP settings file with this configuration:

```json
{
  "mcpServers": {
    "pocketbase-mcp": {
      "command": "node",
      "args": ["D:/Code/Pocket-base patrick display/Patrick-Display-1.0.71/Patrick-Display-1.0.71/mcp-servers/pocketbase-mcp/build/index.js"],
      "env": {
        "POCKETBASE_API_URL": "https://pdapp.fppatrading.com",
        "POCKETBASE_ADMIN_TOKEN": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2xsZWN0aW9uSWQiOiJwYmNfMzE0MjYzNTgyMyIsImV4cCI6MTc1MDU2MDExNCwiaWQiOiI1a2E1eDQ1Z2o4cjIydDgiLCJyZWZyZXNoYWJsZSI6ZmFsc2UsInR5cGUiOiJhdXRoIn0.VXhRiMiCfakOq1kye5V7WMXeWuUgbJ9mInCPNBf4lD0"
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

### Step 3: Alternative - Cursor Settings UI

If Cursor has a settings UI for MCP servers:

1. **Open Cursor Settings** (Ctrl+,)
2. **Search for "MCP" or "Model Context Protocol"**
3. **Add new server** with these details:
   - **Name**: `pocketbase-mcp`
   - **Command**: `node`
   - **Args**: `["D:/Code/Pocket-base patrick display/Patrick-Display-1.0.71/Patrick-Display-1.0.71/mcp-servers/pocketbase-mcp/build/index.js"]`
   - **Environment Variables**:
     - `POCKETBASE_API_URL`: `https://pdapp.fppatrading.com`
     - `POCKETBASE_ADMIN_TOKEN`: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2xsZWN0aW9uSWQiOiJwYmNfMzE0MjYzNTgyMyIsImV4cCI6MTc1MDU2MDExNCwiaWQiOiI1a2E1eDQ1Z2o4cjIydDgiLCJyZWZyZXNoYWJsZSI6ZmFsc2UsInR5cGUiOiJhdXRoIn0.VXhRiMiCfakOq1kye5V7WMXeWuUgbJ9mInCPNBf4lD0`

### Step 4: Restart Cursor

1. **Close Cursor completely**
2. **Restart Cursor**
3. **The MCP server should be detected automatically**

## Testing in Cursor

Once configured, you can test with these prompts:

```
List all collections in my PocketBase
```

```
Show me the schema for the users collection
```

```
List records from the accounts collection
```

```
Show me all trading bots
```

## Cursor-Specific Features

With Cursor + PocketBase MCP, you can:

### Direct Database Queries
- "Show me all active trading cycles"
- "List accounts with balance > 1000"
- "Find bots that are currently running"

### Real-time Monitoring
- "Check recent trading events"
- "Show me the latest API logs"
- "Monitor system performance"

### Development Assistance
- "Create a new trading strategy record"
- "Update bot configuration for bot ID xyz"
- "Upload configuration file to strategy record"

### Advanced Cycles Trader Integration
- "Query cycles for symbol EURUSD"
- "Show performance statistics for ACT strategy"
- "List all zone-based trading events"
- "Monitor loss accumulation across cycles"

## Troubleshooting for Cursor

### Common Issues

1. **MCP Server Not Detected**
   - Check Cursor version (needs MCP support)
   - Verify configuration file location
   - Restart Cursor completely

2. **Path Issues**
   - Use forward slashes in JSON: `D:/Code/...`
   - Ensure absolute paths are correct
   - Verify Node.js is in PATH

3. **Token Issues**
   - Your token expires: `1750560114` (Unix timestamp)
   - Token is valid until: **April 21, 2025**
   - Regenerate token if expired

### Cursor Version Check

Make sure you're using a recent version of Cursor that supports MCP:
- **Minimum Version**: Cursor 0.40+
- **Recommended**: Latest version

## Benefits for Your Advanced Cycles Trader

With PocketBase MCP in Cursor, you can:

1. **Real-time Strategy Monitoring**
   - Query cycle performance directly
   - Monitor order execution
   - Track loss accumulation

2. **Development Efficiency**
   - No need to write API code for data queries
   - Direct database access through natural language
   - Instant data visualization

3. **Debugging Support**
   - Access trading logs instantly
   - Query system state
   - Monitor bot performance

4. **Data Management**
   - Create test data easily
   - Update configurations
   - Manage trading parameters

## Next Steps

1. ✅ **Server Running**: PocketBase MCP server is working
2. ⏳ **Configure Cursor**: Add MCP server to Cursor settings
3. ⏳ **Test Integration**: Try the test commands above
4. ⏳ **Use for Development**: Integrate with your trading project

The server is ready and tested with your token - just need to configure Cursor to use it! 