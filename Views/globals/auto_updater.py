"""
Auto Update Manager for Patrick Display Bot
Handles automatic updates from PocketBase updates collection
Similar to Flutter app auto-update system
"""

import os
import sys
import json
import time
import shutil
import zipfile
import requests
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any
from Views.globals.app_logger import app_logger as logger


class AutoUpdater:
    """
    Auto-update manager that checks PocketBase for updates and applies them automatically
    """
    
    def __init__(self, api_client, current_version: str = "1.0.71", check_interval: int = 300):
        """
        Initialize the auto updater
        
        Args:
            api_client: PocketBase API client
            current_version: Current bot version
            check_interval: Seconds between update checks (default: 5 minutes)
        """
        self.api_client = api_client
        self.current_version = current_version
        self.check_interval = check_interval
        self.is_running = False
        self.update_thread = None
        self.project_root = Path(__file__).parent.parent.parent  # bot app root
        self.backup_dir = self.project_root / "backups"
        self.temp_dir = self.project_root / "temp_updates"
        
        # Ensure directories exist
        self.backup_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        logger.info(f"Auto Updater initialized - Current version: {current_version}")
    
    def start_update_checker(self):
        """Start the background update checker thread"""
        if self.is_running:
            logger.warning("Update checker is already running")
            return
        
        self.is_running = True
        self.update_thread = threading.Thread(target=self._update_check_loop, daemon=True)
        self.update_thread.start()
        logger.info("Auto update checker started")
    
    def stop_update_checker(self):
        """Stop the background update checker"""
        self.is_running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=10)
        logger.info("Auto update checker stopped")
    
    def _update_check_loop(self):
        """Main update checking loop"""
        while self.is_running:
            try:
                self.check_for_updates()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in update check loop: {e}")
                time.sleep(60)  # Wait 1 minute on error before retrying
    
    def check_for_updates(self) -> Optional[Dict]:
        """
        Check PocketBase for available updates
        
        Returns:
            Dict with update info if available, None otherwise
        """
        try:
            # Query updates collection for bot updates
            updates = self.api_client.list_records(
                collection="updates",
                filter=f'platform="bot" && version!="{self.current_version}"',
                sort="-created",
                per_page=1
            )
            
            if not updates or len(updates) == 0:
                logger.debug("No updates available")
                return None
            
            latest_update = updates[0]
            latest_version = latest_update.get('version', '')
            
            # Check if this is a newer version
            if self._is_newer_version(latest_version, self.current_version):
                logger.info(f"🔄 New update available: {latest_version} (current: {self.current_version})")
                
                # Check if auto-update is enabled for this update
                auto_update_enabled = latest_update.get('auto_update', True)
                
                if auto_update_enabled:
                    logger.info("Auto-update is enabled, starting update process...")
                    return self._process_update(latest_update)
                else:
                    logger.info("Auto-update is disabled for this version, manual update required")
                    return latest_update
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return None
    
    def _is_newer_version(self, version1: str, version2: str) -> bool:
        """
        Compare two version strings to determine if version1 is newer than version2
        
        Args:
            version1: First version string (e.g., "1.0.72")
            version2: Second version string (e.g., "1.0.71")
            
        Returns:
            True if version1 is newer than version2
        """
        try:
            # Convert version strings to comparable tuples
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]
            
            # Pad shorter version with zeros
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))
            
            return v1_parts > v2_parts
            
        except Exception as e:
            logger.error(f"Error comparing versions {version1} vs {version2}: {e}")
            return False
    
    def _process_update(self, update_info: Dict) -> Optional[Dict]:
        """
        Process and apply an update
        
        Args:
            update_info: Update information from PocketBase
            
        Returns:
            Dict with update result
        """
        try:
            update_version = update_info.get('version', 'unknown')
            download_url = update_info.get('download_url', '')
            update_type = update_info.get('update_type', 'full')  # full, patch, hotfix
            
            logger.info(f"🚀 Starting update to version {update_version}")
            
            # Create backup of current version
            backup_path = self._create_backup()
            if not backup_path:
                logger.error("Failed to create backup, aborting update")
                return {"success": False, "error": "Backup creation failed"}
            
            # Download update package
            update_package_path = self._download_update_package(download_url, update_version)
            if not update_package_path:
                logger.error("Failed to download update package")
                return {"success": False, "error": "Download failed"}
            
            # Apply update based on type
            if update_type == "full":
                success = self._apply_full_update(update_package_path, update_version)
            elif update_type == "patch":
                success = self._apply_patch_update(update_package_path, update_version)
            else:
                success = self._apply_hotfix_update(update_package_path, update_version)
            
            if success:
                # Update version file
                self._update_version_file(update_version)
                
                # Log successful update
                logger.info(f"✅ Successfully updated to version {update_version}")
                
                # Schedule restart
                self._schedule_restart(update_info)
                
                return {
                    "success": True,
                    "version": update_version,
                    "backup_path": str(backup_path)
                }
            else:
                # Restore from backup on failure
                logger.error("Update failed, restoring from backup...")
                self._restore_from_backup(backup_path)
                return {"success": False, "error": "Update application failed"}
                
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return {"success": False, "error": str(e)}
    
    def _create_backup(self) -> Optional[Path]:
        """
        Create a backup of the current bot version
        
        Returns:
            Path to backup directory or None if failed
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_v{self.current_version}_{timestamp}"
            backup_path = self.backup_dir / backup_name
            
            logger.info(f"Creating backup: {backup_path}")
            
            # Copy entire bot app directory (excluding backups and temp)
            shutil.copytree(
                self.project_root,
                backup_path,
                ignore=shutil.ignore_patterns('backups', 'temp_updates', '__pycache__', '*.pyc', '.git')
            )
            
            logger.info(f"✅ Backup created successfully: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    def _download_update_package(self, download_url: str, version: str) -> Optional[Path]:
        """
        Download update package from URL
        
        Args:
            download_url: URL to download the update package
            version: Version being downloaded
            
        Returns:
            Path to downloaded package or None if failed
        """
        try:
            if not download_url:
                logger.error("No download URL provided")
                return None
            
            package_name = f"update_v{version}.zip"
            package_path = self.temp_dir / package_name
            
            logger.info(f"Downloading update package: {download_url}")
            
            # Download with progress
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(package_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # Log progress every 10%
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            if progress % 10 < 1:
                                logger.info(f"Download progress: {progress:.1f}%")
            
            logger.info(f"✅ Update package downloaded: {package_path}")
            return package_path
            
        except Exception as e:
            logger.error(f"Error downloading update package: {e}")
            return None
    
    def _apply_full_update(self, package_path: Path, version: str) -> bool:
        """
        Apply a full update (replace entire codebase)
        
        Args:
            package_path: Path to update package
            version: Version being applied
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Applying full update to version {version}")
            
            # Extract update package
            extract_path = self.temp_dir / f"extracted_v{version}"
            
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # Find the bot app directory in the extracted files
            bot_app_path = None
            for item in extract_path.rglob("*"):
                if item.is_dir() and item.name == "bot app":
                    bot_app_path = item
                    break
            
            if not bot_app_path:
                logger.error("Bot app directory not found in update package")
                return False
            
            # Check if Windows EXE is included
            exe_path = bot_app_path / "dist" / "PatrickDisplayBot.exe"
            has_exe = exe_path.exists()
            
            if has_exe:
                logger.info("Windows EXE found in update package")
                
                # Copy EXE to a temporary location for later replacement
                temp_exe_path = self.temp_dir / f"PatrickDisplayBot_v{version}.exe"
                shutil.copy2(exe_path, temp_exe_path)
                
                # Create update script for EXE replacement
                self._create_exe_update_script(temp_exe_path, version)
            
            # Replace current files (excluding config and data)
            self._replace_files(bot_app_path, self.project_root)
            
            # Install/update dependencies if requirements.txt exists
            requirements_file = self.project_root / "requirements.txt"
            if requirements_file.exists():
                self._update_dependencies(requirements_file)
            
            logger.info("✅ Full update applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error applying full update: {e}")
            return False

    def _create_exe_update_script(self, temp_exe_path: Path, version: str):
        """
        Create a batch script to update the EXE file after restart
        
        Args:
            temp_exe_path: Path to temporary EXE file
            version: Version being updated to
        """
        try:
            script_path = self.project_root / "update_exe.bat"
            
            script_content = f'''@echo off
echo Updating Patrick Display Bot EXE to version {version}...
timeout /t 3 /nobreak > nul

REM Wait for main process to close
:wait_loop
tasklist /FI "IMAGENAME eq PatrickDisplayBot.exe" 2>NUL | find /I /N "PatrickDisplayBot.exe">NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 2 /nobreak > nul
    goto wait_loop
)

REM Create dist directory if it doesn't exist
if not exist "dist" mkdir "dist"

REM Backup current EXE
if exist "dist\\PatrickDisplayBot.exe" (
    copy "dist\\PatrickDisplayBot.exe" "dist\\PatrickDisplayBot_backup.exe" > nul 2>&1
)

REM Copy new EXE
copy "{temp_exe_path}" "dist\\PatrickDisplayBot.exe" > nul 2>&1

if %ERRORLEVEL% == 0 (
    echo ✅ EXE updated successfully to version {version}
    REM Clean up temp files
    del "{temp_exe_path}" > nul 2>&1
    del "dist\\PatrickDisplayBot_backup.exe" > nul 2>&1
    
    REM Start new version
    echo Starting updated Patrick Display Bot...
    start "" "dist\\PatrickDisplayBot.exe"
) else (
    echo ❌ EXE update failed, restoring backup
    if exist "dist\\PatrickDisplayBot_backup.exe" (
        copy "dist\\PatrickDisplayBot_backup.exe" "dist\\PatrickDisplayBot.exe" > nul 2>&1
        start "" "dist\\PatrickDisplayBot.exe"
    )
)

REM Clean up this script
del "%~f0" > nul 2>&1
'''
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            logger.info(f"EXE update script created: {script_path}")
            
        except Exception as e:
            logger.error(f"Error creating EXE update script: {e}")
    
    def _apply_patch_update(self, package_path: Path, version: str) -> bool:
        """
        Apply a patch update (selective file replacement)
        
        Args:
            package_path: Path to update package
            version: Version being applied
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Applying patch update to version {version}")
            
            # Extract patch package
            extract_path = self.temp_dir / f"patch_v{version}"
            
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # Look for patch manifest
            manifest_file = extract_path / "patch_manifest.json"
            if manifest_file.exists():
                with open(manifest_file, 'r') as f:
                    manifest = json.load(f)
                
                # Apply changes according to manifest
                for file_change in manifest.get('files', []):
                    action = file_change.get('action', 'replace')
                    source_path = extract_path / file_change['source']
                    target_path = self.project_root / file_change['target']
                    
                    if action == 'replace' and source_path.exists():
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, target_path)
                        logger.info(f"Replaced: {target_path}")
                    elif action == 'delete' and target_path.exists():
                        target_path.unlink()
                        logger.info(f"Deleted: {target_path}")
            else:
                # No manifest, apply all files
                self._replace_files(extract_path, self.project_root)
            
            logger.info("✅ Patch update applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error applying patch update: {e}")
            return False
    
    def _apply_hotfix_update(self, package_path: Path, version: str) -> bool:
        """
        Apply a hotfix update (minimal changes)
        
        Args:
            package_path: Path to update package
            version: Version being applied
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Applying hotfix update to version {version}")
            
            # Extract hotfix package
            extract_path = self.temp_dir / f"hotfix_v{version}"
            
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # Apply hotfix files
            self._replace_files(extract_path, self.project_root)
            
            logger.info("✅ Hotfix update applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error applying hotfix update: {e}")
            return False
    
    def _replace_files(self, source_dir: Path, target_dir: Path):
        """
        Replace files from source to target directory with Windows-specific handling
        
        Args:
            source_dir: Source directory containing new files
            target_dir: Target directory to update
        """
        try:
            preserve_paths = {
                'config.json',
                'database.db',
                'backups',
                'temp_updates',
                'logs',
                '__pycache__',
                '.git',
                'dist'  # Preserve dist directory to avoid EXE conflicts
            }
            
            for source_file in source_dir.rglob('*'):
                if source_file.is_file():
                    # Calculate relative path
                    rel_path = source_file.relative_to(source_dir)
                    target_file = target_dir / rel_path
                    
                    # Skip preserved files/directories
                    if any(part in preserve_paths for part in rel_path.parts):
                        # Special handling for EXE files
                        if rel_path.name == "PatrickDisplayBot.exe":
                            # Don't replace EXE directly, let the update script handle it
                            logger.info(f"Skipping EXE replacement during file copy: {rel_path}")
                        continue
                    
                    # Create target directory if needed
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file with Windows-specific error handling
                    try:
                        shutil.copy2(source_file, target_file)
                    except PermissionError:
                        # Handle Windows file locks
                        logger.warning(f"Permission denied copying {rel_path}, attempting force copy...")
                        try:
                            # Try to remove read-only attribute and retry
                            target_file.chmod(0o666)
                            shutil.copy2(source_file, target_file)
                        except Exception as retry_error:
                            logger.error(f"Failed to copy {rel_path}: {retry_error}")
                            continue
                    
        except Exception as e:
            logger.error(f"Error replacing files: {e}")
            raise
    
    def _update_dependencies(self, requirements_file: Path):
        """
        Update Python dependencies from requirements.txt
        
        Args:
            requirements_file: Path to requirements.txt file
        """
        try:
            logger.info("Updating Python dependencies...")
            
            # Get Python executable path (use venv if available)
            venv_python = self.project_root / "venv" / "Scripts" / "python.exe"
            if venv_python.exists():
                python_exe = str(venv_python)
            else:
                python_exe = sys.executable
            
            # Run pip install
            result = subprocess.run([
                python_exe, "-m", "pip", "install", "-r", str(requirements_file)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("✅ Dependencies updated successfully")
            else:
                logger.warning(f"Dependency update warnings: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error updating dependencies: {e}")
    
    def _update_version_file(self, new_version: str):
        """
        Update the version file with new version
        
        Args:
            new_version: New version string
        """
        try:
            version_file = self.project_root / "version.txt"
            with open(version_file, 'w') as f:
                f.write(new_version)
            
            # Update current version
            self.current_version = new_version
            logger.info(f"Version file updated to {new_version}")
            
        except Exception as e:
            logger.error(f"Error updating version file: {e}")
    
    def _schedule_restart(self, update_info: Dict):
        """
        Schedule bot restart after update
        
        Args:
            update_info: Update information
        """
        try:
            restart_required = update_info.get('restart_required', True)
            restart_delay = update_info.get('restart_delay', 30)  # seconds
            
            if restart_required:
                logger.info(f"🔄 Bot restart scheduled in {restart_delay} seconds...")
                
                def delayed_restart():
                    time.sleep(restart_delay)
                    logger.info("🔄 Restarting bot for update...")
                    self._restart_bot()
                
                restart_thread = threading.Thread(target=delayed_restart, daemon=True)
                restart_thread.start()
            
        except Exception as e:
            logger.error(f"Error scheduling restart: {e}")
    
    def _restart_bot(self):
        """Restart the bot application with Windows EXE support"""
        try:
            # Check if EXE update script exists
            update_script = self.project_root / "update_exe.bat"
            exe_file = self.project_root / "dist" / "PatrickDisplayBot.exe"
            
            if update_script.exists():
                # Run EXE update script
                logger.info("Running EXE update script...")
                subprocess.Popen([str(update_script)], shell=True)
                
                # Exit current process
                logger.info("Bot restarting with EXE update...")
                os._exit(0)
                
            elif exe_file.exists():
                # Start EXE version
                logger.info("Restarting with EXE version...")
                subprocess.Popen([str(exe_file)])
                
                # Exit current process
                logger.info("Bot restarting...")
                os._exit(0)
            else:
                # Fallback to Python version
                main_script = self.project_root / "main.py"
                
                if main_script.exists():
                    # Get Python executable path (use venv if available)
                    venv_python = self.project_root / "venv" / "Scripts" / "python.exe"
                    if venv_python.exists():
                        python_exe = str(venv_python)
                    else:
                        python_exe = sys.executable
                    
                    # Restart using Python
                    subprocess.Popen([python_exe, str(main_script)])
                    
                    # Exit current process
                    logger.info("Bot restarting with Python...")
                    os._exit(0)
                else:
                    logger.error("Neither EXE nor Python main script found, manual restart required")
                
        except Exception as e:
            logger.error(f"Error restarting bot: {e}")
    
    def _restore_from_backup(self, backup_path: Path):
        """
        Restore bot from backup
        
        Args:
            backup_path: Path to backup directory
        """
        try:
            logger.info(f"Restoring from backup: {backup_path}")
            
            # Remove current files (except backups and temp)
            for item in self.project_root.iterdir():
                if item.name not in ['backups', 'temp_updates']:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            
            # Restore from backup
            for item in backup_path.iterdir():
                target = self.project_root / item.name
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            
            logger.info("✅ Backup restored successfully")
            
        except Exception as e:
            logger.error(f"Error restoring from backup: {e}")
    
    def force_check_update(self) -> Optional[Dict]:
        """
        Force an immediate update check
        
        Returns:
            Update result if available
        """
        logger.info("🔍 Force checking for updates...")
        return self.check_for_updates()
    
    def get_current_version(self) -> str:
        """Get current bot version"""
        return self.current_version
    
    def cleanup_old_backups(self, keep_count: int = 5):
        """
        Clean up old backup directories
        
        Args:
            keep_count: Number of recent backups to keep
        """
        try:
            backups = sorted(
                [d for d in self.backup_dir.iterdir() if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            # Remove old backups
            for backup in backups[keep_count:]:
                shutil.rmtree(backup)
                logger.info(f"Removed old backup: {backup.name}")
                
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}") 