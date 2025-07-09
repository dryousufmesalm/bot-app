from DB.ah_strategy.models.ah_cycles_orders import AhCyclesOrders
from DB.ah_strategy.models.ah_cycles import AHCycle
from DB.ct_strategy.models.ct_config import CTConfig
from DB.ct_strategy.models.ct_cycles_orders import CtCyclesOrders
from DB.ct_strategy.models.ct_cycles import CTCycle
from DB.mt5_login.models.mt5_login import Mt5Login
from DB.remote_login.models.remote_login import RemoteLogin
from sqlmodel import SQLModel, create_engine
from typing import TYPE_CHECKING
import os
import logging
from sqlmodel import create_engine, SQLModel, Session
from typing import Dict, List
from sqlmodel import create_engine, SQLModel, Session, Field, Column, JSON, select
import uuid
from dotenv import load_dotenv
from datetime import datetime
from os import path

logger = logging.getLogger(__name__)

load_dotenv()

# Import db models

# Create the database file path

db_path = os.path.join(os.getcwd(), 'database.db')

print(f"Database will be created at: {db_path}")

# Ensure database directory exists
db_directory = os.path.dirname(db_path)
if not os.path.exists(db_directory):
    os.makedirs(db_directory)
    print(f"Created database directory: {db_directory}")

# Check if database file exists
if not os.path.exists(db_path):
    logger.info(
        f"Database file does not exist. Creating new database at {db_path}")
    print(f"Creating new empty database file at: {db_path}")
    # Create an empty file to ensure the database can be created
    try:
        with open(db_path, 'w') as f:
            pass  # Just create an empty file
        print(f"Empty database file created successfully")
    except Exception as e:
        print(f"ERROR: Failed to create database file: {e}")
        logger.error(f"Failed to create database file: {e}")
        logger.exception("Database file creation error details:")
else:
    print(f"Database file already exists at: {db_path}")

# db connection string
sqlite_url = f"sqlite:///{db_path}"

# Create the engine
engine = create_engine(sqlite_url, echo=False)

# Create the db tables


def create_db_and_tables():
    try:
        # Check if this is the first time creating the database
        is_new_db = not os.path.exists(
            db_path) or os.path.getsize(db_path) == 0

        # Create all tables based on the models
        logger.info("Creating database tables...")
        SQLModel.metadata.create_all(engine)

        if is_new_db:
            logger.info("New database created successfully")
        # After creating tables, run migrations if database file exists and is not new
        elif os.path.exists(db_path) and not is_new_db:
            logger.info("Running database migrations...")
            try:
                # Import and run the migration script
                from DB.migrate_ct_cycles import migrate_ct_cycles
                migrate_ct_cycles()

                # Run the CT config migration
                from DB.migrate_ct_config import run_migration
                run_migration()

                logger.info("Database migrations completed successfully.")
            except Exception as e:
                logger.error(f"Error running database migrations: {e}")
                logger.exception("Migration error details:")
    except Exception as e:
        logger.error(f"Error creating database and tables: {e}")
        logger.exception("Database creation error details:")

# Connect to the db


def get_session():
    """Get a session to the db"""
    with Session(engine) as session:
        yield session


create_db_and_tables()

# Ensure database is created when this module is imported
if __name__ == "__main__":
    print("DB module running directly, creating database...")
    create_db_and_tables()
else:
    print("DB module imported, creating database tables...")
    create_db_and_tables()
