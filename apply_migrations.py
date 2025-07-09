#!/usr/bin/env python3
"""
Script to apply PocketBase migrations directly via API
"""

import requests
import json
import sys
import os
from pathlib import Path

def apply_migration_via_api(migration_file_path, base_url, admin_token):
    """Apply a migration file via PocketBase API"""
    
    # Read the migration file
    with open(migration_file_path, 'r') as f:
        migration_content = f.read()
    
    # Extract the migration function (this is a simplified approach)
    # In a real scenario, you'd need to parse and execute the JavaScript
    print(f"Migration content loaded from {migration_file_path}")
    print("Note: This script shows the migration content but cannot execute JavaScript directly.")
    print("You need to apply these migrations through the PocketBase admin interface.")
    print("\n" + "="*50)
    print(migration_content)
    print("="*50 + "\n")
    
    return True

def main():
    base_url = "https://pdapp.fppatrading.com"
    admin_email = "dev@autoticks.com"
    admin_password = "1223334444"
    
    # Get admin token first
    auth_response = requests.post(
        f"{base_url}/api/admins/auth-with-password",
        json={
            "identity": admin_email,
            "password": admin_password
        }
    )
    
    if auth_response.status_code != 200:
        print(f"Failed to authenticate: {auth_response.text}")
        return False
    
    auth_data = auth_response.json()
    admin_token = auth_data.get('token')
    
    print(f"Successfully authenticated as admin")
    
    # Find migration files
    migrations_dir = Path("pb_migrations")
    if not migrations_dir.exists():
        print("No pb_migrations directory found")
        return False
    
    migration_files = sorted(migrations_dir.glob("*.js"))
    
    if not migration_files:
        print("No migration files found")
        return False
    
    print(f"Found {len(migration_files)} migration files:")
    for mf in migration_files:
        print(f"  - {mf.name}")
    
    # Apply each migration
    for migration_file in migration_files:
        print(f"\nProcessing migration: {migration_file.name}")
        apply_migration_via_api(migration_file, base_url, admin_token)
    
    print("\nAll migrations processed!")
    print("\nIMPORTANT: Since PocketBase migrations are JavaScript-based,")
    print("you need to manually apply them through the admin interface or")
    print("use the PocketBase CLI tool if available.")
    
    return True

if __name__ == "__main__":
    main() 