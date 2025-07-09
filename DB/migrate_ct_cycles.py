import sqlite3
import os
import json

# Get the path to the database file
db_path = os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), 'database.db')


def migrate_ct_cycles():
    """Add the new zone forward fields to the ct_cycles table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(ct_cycles)")
    columns = [column[1] for column in cursor.fetchall()]

    # Add the new columns if they don't exist
    if 'done_price_levels' not in columns:
        cursor.execute(
            "ALTER TABLE ct_cycles ADD COLUMN done_price_levels TEXT DEFAULT '[]'")

    if 'current_direction' not in columns:
        cursor.execute(
            "ALTER TABLE ct_cycles ADD COLUMN current_direction TEXT DEFAULT 'BUY'")

    if 'initial_threshold_price' not in columns:
        cursor.execute(
            "ALTER TABLE ct_cycles ADD COLUMN initial_threshold_price REAL DEFAULT 0.0")

    if 'direction_switched' not in columns:
        cursor.execute(
            "ALTER TABLE ct_cycles ADD COLUMN direction_switched INTEGER DEFAULT 0")

    if 'next_order_index' not in columns:
        cursor.execute(
            "ALTER TABLE ct_cycles ADD COLUMN next_order_index INTEGER DEFAULT 0")

    # Get all existing records and update them with default values
    cursor.execute("SELECT id, initial FROM ct_cycles WHERE is_closed = 0")
    active_cycles = cursor.fetchall()

    for cycle_id, initial_json in active_cycles:
        try:
            # Parse initial orders JSON
            initial = json.loads(initial_json)

            # If there are initial orders, set the threshold price
            if initial and len(initial) > 0:
                # Get the first initial order's open price
                cursor.execute(
                    "SELECT open_price FROM ct_cycles_orders WHERE ticket = ?", (initial[0],))
                order_data = cursor.fetchone()

                if order_data and order_data[0]:
                    # Update the initial_threshold_price with the open price of the first order
                    cursor.execute(
                        "UPDATE ct_cycles SET initial_threshold_price = ? WHERE id = ?",
                        (order_data[0], cycle_id)
                    )
        except Exception as e:
            print(f"Error updating cycle {cycle_id}: {e}")

    conn.commit()
    conn.close()

    print("Migration completed successfully!")


if __name__ == "__main__":
    migrate_ct_cycles()
