# Test PocketBase MCP Server Connection
# This script tests if the PocketBase MCP server can connect and retrieve data

Write-Host "Testing PocketBase MCP Server Connection..." -ForegroundColor Green

# Set environment variables
$env:POCKETBASE_API_URL = "https://pdapp.fppatrading.com"
$env:POCKETBASE_ADMIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2xsZWN0aW9uSWQiOiJwYmNfMzE0MjYzNTgyMyIsImV4cCI6MTc1MDU2MDExNCwiaWQiOiI1a2E1eDQ1Z2o4cjIydDgiLCJyZWZyZXNoYWJsZSI6ZmFsc2UsInR5cGUiOiJhdXRoIn0.VXhRiMiCfakOq1kye5V7WMXeWuUgbJ9mInCPNBf4lD0"

Write-Host "Environment variables set:" -ForegroundColor Yellow
Write-Host "API URL: $env:POCKETBASE_API_URL"
Write-Host "Token: $($env:POCKETBASE_ADMIN_TOKEN.Substring(0,20))..."

Write-Host "`nTesting PocketBase API directly..." -ForegroundColor Yellow

try {
    # Test basic API connectivity
    $response = Invoke-RestMethod -Uri "https://pdapp.fppatrading.com/api/health" -Method GET -ErrorAction Stop
    Write-Host "✅ PocketBase API is accessible" -ForegroundColor Green
} catch {
    Write-Host "❌ PocketBase API is not accessible: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

try {
    # Test admin authentication
    $headers = @{
        "Authorization" = "Admin $env:POCKETBASE_ADMIN_TOKEN"
    }
    $collections = Invoke-RestMethod -Uri "https://pdapp.fppatrading.com/api/collections" -Headers $headers -Method GET -ErrorAction Stop
    Write-Host "✅ Admin token is valid" -ForegroundColor Green
    Write-Host "Found $($collections.items.Count) collections" -ForegroundColor Cyan
} catch {
    Write-Host "❌ Admin token authentication failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n🚀 PocketBase connection test PASSED!" -ForegroundColor Green
Write-Host "The MCP server should work correctly with these credentials." -ForegroundColor Green

Write-Host "`nTo use with Cursor:" -ForegroundColor Yellow
Write-Host "1. Add MCP server configuration to Cursor settings"
Write-Host "2. Use the same environment variables shown above"
Write-Host "3. Restart Cursor"
Write-Host "4. Test with: 'List all collections in my PocketBase'" 