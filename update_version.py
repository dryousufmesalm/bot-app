#!/usr/bin/env python3
"""
Version Management Script for Patrick Display Bot
Use this script to update version numbers and create releases
"""

import os
import sys
import subprocess
from pathlib import Path

def get_current_version():
    """Get the current version from version.txt"""
    version_file = Path("version.txt")
    if version_file.exists():
        return version_file.read_text().strip()
    return  "2.2"

def update_version(new_version):
    """Update the version in version.txt"""
    version_file = Path("version.txt")
    version_file.write_text(new_version)
    print(f"✅ Updated version to: {new_version}")

def increment_version(version_type="patch"):
    """Increment version automatically"""
    current = get_current_version()
    try:
        parts = current.split('.')
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        
        if version_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif version_type == "minor":
            minor += 1
            patch = 0
        else:  # patch
            patch += 1
            
        new_version = f"{major}.{minor}.{patch}"
        update_version(new_version)
        return new_version
    except (ValueError, IndexError):
        print(f"❌ Invalid version format: {current}")
        return None

def create_git_tag(version):
    """Create and push a git tag"""
    tag_name = f"v{version}"
    try:
        # Check if we're in a git repository
        subprocess.run(["git", "status"], check=True, capture_output=True)
        
        # Add version.txt to git
        subprocess.run(["git", "add", "version.txt"], check=True)
        subprocess.run(["git", "commit", "-m", f"Bump version to {version}"], check=True)
        
        # Create and push tag
        subprocess.run(["git", "tag", tag_name], check=True)
        subprocess.run(["git", "push", "origin", tag_name], check=True)
        subprocess.run(["git", "push"], check=True)
        
        print(f"✅ Created and pushed tag: {tag_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Git operation failed: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("📋 Patrick Display Bot Version Manager")
        print("=====================================")
        print(f"📦 Current version: {get_current_version()}")
        print("")
        print("Usage:")
        print("  python update_version.py show                    # Show current version")
        print("  python update_version.py set <version>           # Set specific version")
        print("  python update_version.py patch                   # Increment patch (1.0.72 -> 1.0.73)")
        print("  python update_version.py minor                   # Increment minor (1.0.72 -> 1.1.0)")
        print("  python update_version.py major                   # Increment major (1.0.72 -> 2.0.0)")
        print("  python update_version.py release patch           # Increment patch and create release")
        print("  python update_version.py release minor           # Increment minor and create release")
        print("  python update_version.py release major           # Increment major and create release")
        return

    command = sys.argv[1]
    
    if command == "show":
        print(f"📦 Current version: {get_current_version()}")
        
    elif command == "set":
        if len(sys.argv) < 3:
            print("❌ Please specify a version number")
            return
        new_version = sys.argv[2]
        update_version(new_version)
        
    elif command in ["patch", "minor", "major"]:
        new_version = increment_version(command)
        if new_version:
            print(f"📦 Version updated: {new_version}")
            
    elif command == "release":
        if len(sys.argv) < 3:
            print("❌ Please specify release type: patch, minor, or major")
            return
        
        release_type = sys.argv[2]
        if release_type not in ["patch", "minor", "major"]:
            print("❌ Release type must be: patch, minor, or major")
            return
            
        print(f"🚀 Creating {release_type} release...")
        new_version = increment_version(release_type)
        if new_version:
            print(f"📦 Version updated to: {new_version}")
            if create_git_tag(new_version):
                print("🎉 Release created successfully!")
                print(f"🔗 GitHub Actions will build and publish the release automatically")
                print(f"📥 Download will be available at: https://github.com/your-repo/releases/tag/v{new_version}")
            else:
                print("❌ Failed to create git tag")
    else:
        print(f"❌ Unknown command: {command}")

if __name__ == "__main__":
    main() 