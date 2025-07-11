# 🚀 Patrick Display Bot Release Guide

This guide explains how to create releases and manage versions for the Patrick Display Bot.

## 📋 Quick Start

**Note**: Run all commands from the `bot app` directory (project root).

### Method 1: Automatic Release (Recommended)
```bash
# Navigate to bot app directory first
cd "bot app"

# Create a patch release (1.0.72 -> 1.0.73)
python update_version.py release patch

# Create a minor release (1.0.72 -> 1.1.0)
python update_version.py release minor

# Create a major release (1.0.72 -> 2.0.0)
python update_version.py release major
```

### Method 2: Manual Version Management
```bash
# Navigate to bot app directory first
cd "bot app"

# Set a specific version
python update_version.py set 1.0.73

# Then manually create a git tag
git add version.txt
git commit -m "Bump version to 1.0.73"
git tag v1.0.73
git push origin v1.0.73
git push
```

### Method 3: GitHub Manual Trigger
1. Go to GitHub Actions
2. Select "Auto Update Bot" workflow
3. Click "Run workflow"
4. Enter version number (optional)
5. Click "Run workflow"

## 📦 What Happens During Release

### Automatic Process
1. **Version Detection**: Script reads `version.txt` or uses manual input
2. **Git Tag Creation**: Creates and pushes a version tag (e.g., `v1.0.73`)
3. **GitHub Actions Trigger**: Tag push triggers the build workflow
4. **Build Process**: 
   - Sets up Python 3.13.0 environment
   - Installs dependencies
   - Creates virtual environment
   - Builds single-file EXE with PyInstaller
5. **Release Creation**: 
   - Creates GitHub release with release notes
   - Uploads EXE file as downloadable asset
   - Marks as latest release

### Build Output
- **Executable**: `PatrickDisplayBot-v{version}.exe`
- **Size**: ~50-100MB (single-file, no dependencies)
- **Platform**: Windows 10/11 (64-bit)

## 🔧 Version Management

### Current Version
```bash
python update_version.py show
```

### Set Specific Version
```bash
python update_version.py set 1.0.73
```

### Increment Versions
```bash
# Patch: 1.0.72 -> 1.0.73 (bug fixes)
python update_version.py patch

# Minor: 1.0.72 -> 1.1.0 (new features)
python update_version.py minor

# Major: 1.0.72 -> 2.0.0 (breaking changes)
python update_version.py major
```

## 🎯 Release Types

### Patch Release (1.0.72 -> 1.0.73)
- **Use for**: Bug fixes, small improvements
- **Command**: `python update_version.py release patch`
- **Example**: Fixed signal handler error, improved logging

### Minor Release (1.0.72 -> 1.1.0)
- **Use for**: New features, enhancements
- **Command**: `python update_version.py release minor`
- **Example**: Added new trading strategy, UI improvements

### Major Release (1.0.72 -> 2.0.0)
- **Use for**: Breaking changes, major rewrites
- **Command**: `python update_version.py release major`
- **Example**: Complete architecture change, API changes

## 📁 File Structure

```
bot app/
├── version.txt                 # Current version number
├── update_version.py          # Version management script
├── RELEASE_GUIDE.md           # This guide
├── .github/
│   └── workflows/
│       └── auto-update-bot.yml # GitHub Actions workflow
└── main.py                    # Main application entry point
```

## 🔍 Troubleshooting

### "Resource not accessible by integration"
- **Solution**: GitHub Actions workflow now includes proper permissions
- **Check**: Workflow has `permissions: contents: write` section

### Build Fails
- **Check**: All dependencies in `requirements.txt`
- **Check**: `main.py` exists in bot app directory
- **Check**: Python 3.13.0 compatibility

### Release Not Created
- **Check**: Git tag was pushed successfully
- **Check**: GitHub Actions workflow completed
- **Check**: GITHUB_TOKEN has sufficient permissions

### EXE Not Working
- **Check**: Windows 10/11 compatibility
- **Check**: Antivirus not blocking the file
- **Check**: All required DLLs included in build

## 📥 Download Links

After a successful release, users can download from:
- **GitHub Releases**: `https://github.com/your-repo/releases/latest`
- **Direct EXE**: `https://github.com/your-repo/releases/download/v{version}/PatrickDisplayBot-v{version}.exe`

## 🔄 Workflow Status

Check build status at:
- **GitHub Actions**: Repository → Actions → Auto Update Bot
- **Latest Release**: Repository → Releases

## 📋 Pre-Release Checklist

Before creating a release:
- [ ] All tests pass locally
- [ ] Code is committed and pushed
- [ ] Version number is appropriate
- [ ] Release notes prepared (optional)
- [ ] Breaking changes documented

## 🎉 Post-Release

After release creation:
1. **Verify Download**: Test the EXE download and execution
2. **Update Documentation**: Update any version-specific docs
3. **Notify Users**: Announce new release if needed
4. **Monitor Issues**: Watch for bug reports

---

## 💡 Tips

- Use **patch** releases for quick fixes
- Use **minor** releases for new features  
- Use **major** releases sparingly for big changes
- Always test locally before releasing
- Keep version.txt updated and committed 