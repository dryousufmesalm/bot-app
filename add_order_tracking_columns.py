import sqlite3
import os
from Views.globals.app_logger import app_logger as logger

def add_order_tracking_columns():
    """Add order tracking columns to the global_loss_tracker table"""
    try:
        # Get the database path (same as in db_engine.py)
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.db")
        print(f"Using database at: {db_path}")
        logger.info(f"Using database at: {db_path}")
        
        # Check if database file exists
        if not os.path.exists(db_path):
            print(f"Database file not found at {db_path}")
            logger.error(f"Database file not found at {db_path}")
            
            # Try the project root directory
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "database.db")
            print(f"Trying alternative path: {db_path}")
            logger.info(f"Trying alternative path: {db_path}")
            
            if not os.path.exists(db_path):
                print(f"Database file not found at alternative path {db_path}")
                logger.error(f"Database file not found at alternative path {db_path}")
                return False
        
        # Connect to the database
        print(f"Connecting to database: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='global_loss_tracker'")
        if not cursor.fetchone():
            print("global_loss_tracker table does not exist, creating it")
            logger.info("global_loss_tracker table does not exist, creating it")
            
            # Create the table with all columns
            cursor.execute('''
            CREATE TABLE global_loss_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                total_accumulated_losses REAL DEFAULT 0.0,
                active_cycles_count INTEGER DEFAULT 0,
                closed_cycles_count INTEGER DEFAULT 0,
                initial_order_losses REAL DEFAULT 0.0,
                threshold_order_losses REAL DEFAULT 0.0,
                recovery_order_losses REAL DEFAULT 0.0,
                last_cycle_id TEXT,
                last_loss_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                zone_based_losses REAL DEFAULT 0.0,
                direction_switch_count INTEGER DEFAULT 0,
                batch_stop_loss_triggers INTEGER DEFAULT 0,
                max_single_cycle_loss REAL DEFAULT 0.0,
                average_cycle_loss REAL DEFAULT 0.0,
                loss_trend TEXT DEFAULT 'stable',
                total_cycles_processed INTEGER DEFAULT 0,
                profitable_cycles INTEGER DEFAULT 0,
                loss_making_cycles INTEGER DEFAULT 0,
                last_order_ticket INTEGER,
                last_order_type TEXT,
                last_order_price REAL,
                last_order_lot_size REAL,
                last_order_source TEXT,
                total_orders_placed INTEGER DEFAULT 0,
                initial_orders_placed INTEGER DEFAULT 0,
                interval_orders_placed INTEGER DEFAULT 0,
                reversal_orders_placed INTEGER DEFAULT 0
            )
            ''')
            
            # Create indexes for faster queries
            cursor.execute("CREATE INDEX idx_global_loss_tracker_bot_id ON global_loss_tracker (bot_id)")
            cursor.execute("CREATE INDEX idx_global_loss_tracker_account_id ON global_loss_tracker (account_id)")
            cursor.execute("CREATE INDEX idx_global_loss_tracker_symbol ON global_loss_tracker (symbol)")
            
            print("Created global_loss_tracker table with all columns")
            logger.info("Created global_loss_tracker table with all columns")
        else:
            print("global_loss_tracker table exists, checking for missing columns")
            logger.info("global_loss_tracker table exists, checking for missing columns")
            
            # Get existing columns
            cursor.execute("PRAGMA table_info(global_loss_tracker)")
            existing_columns = [info[1] for info in cursor.fetchall()]
            print(f"Existing columns: {existing_columns}")
            
            # Add the new columns if they don't exist
            columns_to_add = [
                ("last_order_ticket", "INTEGER"),
                ("last_order_type", "TEXT"),
                ("last_order_price", "REAL"),
                ("last_order_lot_size", "REAL"),
                ("last_order_source", "TEXT"),
                ("total_orders_placed", "INTEGER DEFAULT 0"),
                ("initial_orders_placed", "INTEGER DEFAULT 0"),
                ("interval_orders_placed", "INTEGER DEFAULT 0"),
                ("reversal_orders_placed", "INTEGER DEFAULT 0")
            ]
            
            for column_name, column_type in columns_to_add:
                try:
                    if column_name not in existing_columns:
                        cursor.execute(f"ALTER TABLE global_loss_tracker ADD COLUMN {column_name} {column_type}")
                        print(f"Added column {column_name} to global_loss_tracker")
                        logger.info(f"Added column {column_name} to global_loss_tracker")
                    else:
                        print(f"Column {column_name} already exists in global_loss_tracker")
                        logger.info(f"Column {column_name} already exists in global_loss_tracker")
                except sqlite3.OperationalError as e:
                    print(f"Error adding column {column_name}: {e}")
                    logger.error(f"Error adding column {column_name}: {e}")
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        print("Successfully updated global_loss_tracker table")
        logger.info("Successfully updated global_loss_tracker table")
        return True
    
    except Exception as e:
        print(f"Error updating global_loss_tracker table: {e}")
        logger.error(f"Error updating global_loss_tracker table: {e}")
        return False

if __name__ == "__main__":
    add_order_tracking_columns() 