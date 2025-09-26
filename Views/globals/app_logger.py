import logging
import os
import sys

# Set the root logger to ERROR level to override all other configurations
logging.basicConfig(level=logging.ERROR, force=True)

# Create a global logger
app_logger = logging.getLogger("app_logger")
app_logger.setLevel(logging.DEBUG)

# Set all existing loggers to ERROR level
def set_all_loggers_to_error():
    """Set all existing loggers to ERROR level only"""
    for name in logging.Logger.manager.loggerDict:
        logger_instance = logging.getLogger(name)
        logger_instance.setLevel(logging.ERROR)
        
        # Also set all handlers to ERROR level
        for handler in logger_instance.handlers:
            handler.setLevel(logging.ERROR)

# Apply error-only setting to all loggers
set_all_loggers_to_error()

# File logging disabled - no file handler created
# log_file = os.path.join(os.path.dirname(__file__), 'app.log')
# log_file = os.path.join("app.log")
# file_handler = logging.FileHandler(log_file, encoding='utf-8')
# file_handler.setLevel(logging.ERROR)  # Only write ERROR and CRITICAL messages to file

# Create a console handler with UTF-8 encoding - ERRORS ONLY
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.ERROR)  # Only show ERROR and CRITICAL messages in console

# Create a formatter and set it for console handler
# Use ASCII-safe formatter to avoid Unicode issues
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
# file_handler.setFormatter(formatter)  # File handler disabled
console_handler.setFormatter(formatter)

# Define a filter to exclude sync_CT_cycles logs
class SyncCTCyclesFilter(logging.Filter):
    def filter(self, record):
        if "sync_CT_cycles" in record.getMessage():
            return False
        return True

# Define a filter to sanitize Unicode characters
class UnicodeFilter(logging.Filter):
    def filter(self, record):
        # Replace problematic Unicode characters with ASCII equivalents
        if hasattr(record, 'msg'):
            if isinstance(record.msg, str):
                # Replace common Unicode symbols with ASCII equivalents
                record.msg = record.msg.replace('✅', '[SUCCESS]').replace('❌', '[FAILED]').replace('⚠️', '[WARNING]')
        return True

# Add filters to both handlers
sync_filter = SyncCTCyclesFilter()
unicode_filter = UnicodeFilter()

# file_handler.addFilter(sync_filter)  # File handler disabled
# file_handler.addFilter(unicode_filter)  # File handler disabled
console_handler.addFilter(sync_filter)
console_handler.addFilter(unicode_filter)

# Add handlers to the logger
# app_logger.addHandler(file_handler)  # File handler disabled
app_logger.addHandler(console_handler)

# Example usage
if __name__ == "__main__":
    app_logger.debug("This is a debug message")
    app_logger.info("This is an info message")
    app_logger.warning("This is a warning message")
    app_logger.error("This is an error message")
    app_logger.critical("This is a critical message")
