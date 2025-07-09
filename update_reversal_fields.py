#!/usr/bin/env python3
"""
Update reversal trading fields using multiple methods
"""

import os
import sys
import logging
import subprocess
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def run_script(script_path):
    """Run a Python script and return success status"""
    logger.info(f"Running script: {script_path}")
    
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Log output
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info(f"[{script_path}] {line}")
        
        if result.stderr:
            for line in result.stderr.splitlines():
                logger.warning(f"[{script_path}] {line}")
        
        if result.returncode == 0:
            logger.info(f"Script {script_path} completed successfully")
            return True
        else:
            logger.error(f"Script {script_path} failed with return code {result.returncode}")
            return False
    except Exception as e:
        logger.error(f"Error running script {script_path}: {e}")
        return False

def update_reversal_fields():
    """Update reversal trading fields using multiple methods"""
    
    # Script paths - using relative paths
    script_paths = [
        "apply_reversal_migration.py",
        "add_reversal_fields_directly.py"
    ]
    
    # Check if scripts exist
    for script_path in script_paths:
        if not os.path.exists(script_path):
            logger.error(f"Script not found: {script_path}")
            return False
    
    # Try each script in sequence
    success = False
    
    for script_path in script_paths:
        logger.info(f"Attempting update using {script_path}")
        
        if run_script(script_path):
            success = True
            logger.info(f"Update successful using {script_path}")
            break
        else:
            logger.warning(f"Update failed using {script_path}, trying next method")
            # Wait a bit before trying the next method
            time.sleep(2)
    
    if not success:
        # If all methods fail, try one more time with the direct method
        logger.warning("All methods failed, trying direct method one more time")
        time.sleep(5)  # Wait a bit longer
        
        if run_script(script_paths[1]):  # add_reversal_fields_directly.py
            success = True
            logger.info("Update successful on final attempt")
    
    return success

if __name__ == "__main__":
    logger.info("Starting reversal trading fields update")
    success = update_reversal_fields()
    
    if success:
        logger.info("Reversal trading fields update completed successfully")
        sys.exit(0)
    else:
        logger.error("Reversal trading fields update failed")
        sys.exit(1) 