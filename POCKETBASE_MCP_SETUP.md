# PocketBase MCP Server Setup Guide

## Installation Status: ✅ COMPLETE

The PocketBase MCP server has been successfully installed and built in your project.

### Installation Location
- **Path**: `mcp-servers/pocketbase-mcp/`
- **Built Server**: `mcp-servers/pocketbase-mcp/build/index.js`
- **Status**: Ready for configuration

## Configuration Steps

### Step 1: Get PocketBase Admin Token

You need to obtain an admin authentication token from your PocketBase instance at `https://pdapp.fppatrading.com`.

1. **Access PocketBase Admin UI**:
   - Open: `https://pdapp.fppatrading.com/_/`
   - Login with your admin credentials

2. **Generate API Key**:
   - Navigate to Settings → API Keys
   - Create a new API key with admin permissions
   - Copy the generated token

### Step 2: Configure Claude Desktop

You need to add the PocketBase MCP server to your Claude Desktop configuration.

#### Find Claude Desktop Config File

**Windows Location** (try these paths):
- `%APPDATA%\Claude\claude_desktop_config.json`
- `%USERPROFILE%\AppData\Roaming\Claude\claude_desktop_config.json`
- `C:\Users\[YourUsername]\AppData\Roaming\Claude\claude_desktop_config.json`

#### Configuration Content

Add this configuration to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pocketbase-mcp": {
      "command": "node",
      "args": ["D:/Code/Pocket-base patrick display/Patrick-Display-1.0.71/Patrick-Display-1.0.71/mcp-servers/pocketbase-mcp/build/index.js"],
      "env": {
        "POCKETBASE_API_URL": "https://pdapp.fppatrading.com",
        "POCKETBASE_ADMIN_TOKEN": "YOUR_ADMIN_TOKEN_HERE"
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

**Replace `YOUR_ADMIN_TOKEN_HERE` with your actual admin token from Step 1.**

### Step 3: Test the Installation

After configuration, restart Claude Desktop and test the MCP server:

1. **Restart Claude Desktop**
2. **Test basic functionality**:
   - Try: "List all collections in my PocketBase"
   - Try: "Show me the schema for the users collection"
   - Try: "List records from the accounts collection"

## Available Tools

Once configured, you'll have access to these PocketBase tools:

### Record Management
- `fetch_record` - Get a single record by ID
- `list_records` - List records with filtering and pagination
- `create_record` - Create new records
- `update_record` - Update existing records

### Collection Management
- `list_collections` - List all collections
- `get_collection_schema` - Get collection schema details

### File Management
- `upload_file` - Upload files to records
- `download_file` - Get file download URLs

### Log Management
- `list_logs` - View API request logs
- `get_log` - Get specific log details
- `get_logs_stats` - Get log statistics

### Migration Management
- `create_migration` - Create new migration files
- `apply_migration` - Apply migrations
- `revert_migration` - Revert migrations
- `list_migrations` - List migration files

## Integration with Your Project

The MCP server will allow you to:

1. **Manage Trading Data**: Query and update accounts, bots, strategies
2. **Monitor Events**: Access trading events and logs
3. **Database Operations**: Perform CRUD operations on all collections
4. **Schema Management**: View and modify database schemas
5. **File Handling**: Manage file uploads and downloads

## Troubleshooting

### Common Issues

1. **Admin Token Not Working**:
   - Verify token is correct
   - Check token has admin permissions
   - Ensure PocketBase instance is accessible

2. **Path Issues**:
   - Use absolute paths in configuration
   - Ensure forward slashes in JSON paths
   - Verify build/index.js exists

3. **Connection Issues**:
   - Test PocketBase URL in browser
   - Check firewall/network settings
   - Verify admin UI is accessible

### Testing Connection

You can test your PocketBase connection manually:

```bash
# Test if PocketBase is accessible
curl https://pdapp.fppatrading.com/api/health

# Test admin authentication (replace TOKEN)
curl -H "Authorization: Admin TOKEN" https://pdapp.fppatrading.com/api/collections
```

## Next Steps

1. ✅ PocketBase MCP Server installed
2. ⏳ Get admin token from PocketBase
3. ⏳ Configure Claude Desktop
4. ⏳ Test integration
5. ⏳ Begin using MCP tools for project development

## Integration with Advanced Cycles Trader

Once the MCP server is configured, you can use it to:

- Query trading cycles and orders
- Monitor bot performance
- Manage account data
- Access real-time trading events
- Perform database migrations for new features

This will significantly enhance your ability to manage and monitor the Advanced Cycles Trader implementation. 