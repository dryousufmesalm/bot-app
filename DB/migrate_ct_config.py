from sqlmodel import SQLModel, create_engine
from DB.ct_strategy.models.ct_config import CTConfig
from DB.db_engine import engine


def run_migration():
    """Run the migration to create the ct_config table"""
    try:
        # Create the table
        SQLModel.metadata.create_all(engine, tables=[CTConfig.__table__])
        print("Successfully created ct_config table")
        return True
    except Exception as e:
        print(f"Error creating ct_config table: {e}")
        return False


if __name__ == "__main__":
    run_migration()
