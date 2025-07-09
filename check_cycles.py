from DB.db_engine import engine
from DB.ct_strategy.repositories.ct_repo import CTRepo


def check_cycles():
    """Check if all cycles have the required fields"""
    repo = CTRepo(engine)
    cycles = repo.get_all_cycles()

    if not cycles:
        print("No cycles found in the database.")
        return

    print(f"Found {len(cycles)} cycles in the database.")

    # Check each cycle for required fields
    for cycle in cycles:
        try:
            # Try to access all the new fields to ensure they exist
            print(f"Cycle ID: {cycle.id}, Remote ID: {cycle.remote_id}")
            print(f"  Current Direction: {cycle.current_direction}")
            print(
                f"  Initial Threshold Price: {cycle.initial_threshold_price}")
            print(f"  Direction Switched: {cycle.direction_switched}")
            print(f"  Next Order Index: {cycle.next_order_index}")
            print(f"  Done Price Levels: {cycle.done_price_levels}")
            print("  All fields are accessible.")
        except AttributeError as e:
            print(f"  Error: {e}")

    print("Diagnostic check completed.")


if __name__ == "__main__":
    check_cycles()
