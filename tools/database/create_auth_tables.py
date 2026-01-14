"""Script to create authentication tables with UUID user IDs."""
from sqlalchemy import create_engine
from models.database import Base, User, UserSession
from utils.logger import logger
import os

def create_auth_tables():
    """Create authentication tables in the database."""
    try:
        # Get database URL from environment
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/pr_analysis')
        
        # Create engine
        engine = create_engine(db_url)
        
        # Create tables
        logger.info("Creating authentication tables...")
        Base.metadata.create_all(engine, tables=[User.__table__, UserSession.__table__])
        
        logger.info("Authentication tables created successfully!")
        print("✓ Users table created with UUID primary key")
        print("✓ UserSessions table created with UUID foreign key")
        
    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")
        print(f"✗ Error: {str(e)}")
        raise

if __name__ == "__main__":
    create_auth_tables()
