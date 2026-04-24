"""SQL Server database operations for migration tracking."""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

import pyodbc

from .config import DatabaseConfig
from .migrations import MigrationScript

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages SQL Server database connections."""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection: Optional[pyodbc.Connection] = None
    
    def connect(self) -> "DatabaseConnection":
        """Establish database connection."""
        try:
            self.connection = pyodbc.connect(self.config.connection_string)
            logger.info(f"Connected to database: {self.config.database}")
            return self
        except pyodbc.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    def __enter__(self) -> "DatabaseConnection":
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
    
    @property
    def cursor(self) -> pyodbc.Cursor:
        """Get database cursor."""
        if not self.connection:
            raise RuntimeError("Not connected to database")
        return self.connection.cursor()


class MigrationStateRepository:
    """Tracks migration state in the database."""
    
    def __init__(self, db_connection: DatabaseConnection, state_table: str = "MigrationState"):
        self.db = db_connection
        self.state_table = state_table
    
    def initialize(self):
        """Create migration state table if it doesn't exist."""
        create_table_sql = f"""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.state_table}' and xtype='U')
        CREATE TABLE {self.state_table} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            version NVARCHAR(50) NOT NULL UNIQUE,
            name NVARCHAR(255) NOT NULL,
            checksum NVARCHAR(64) NOT NULL,
            applied_at DATETIME NOT NULL DEFAULT GETDATE(),
            success BIT NOT NULL DEFAULT 1,
            execution_time_ms INT,
            error_message NVARCHAR(MAX),
            rolled_back BIT NOT NULL DEFAULT 0
        )
        """
        with self.db.cursor as cursor:
            cursor.execute(create_table_sql)
            cursor.commit()
        logger.info(f"Initialized migration state table: {self.state_table}")
    
    def get_applied_migrations(self) -> List[str]:
        """Get list of successfully applied migration versions."""
        query = f"""
        SELECT version FROM {self.state_table} 
        WHERE success = 1 AND rolled_back = 0 
        ORDER BY version
        """
        with self.db.cursor as cursor:
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]
    
    def get_all_migrations(self) -> List[Tuple[str, str, str, datetime, bool]]:
        """Get all migration records with details."""
        query = f"""
        SELECT version, name, checksum, applied_at, success 
        FROM {self.state_table} 
        ORDER BY version
        """
        with self.db.cursor as cursor:
            cursor.execute(query)
            return [(row[0], row[1], row[2], row[3], bool(row[4])) for row in cursor.fetchall()]
    
    def record_migration(
        self,
        version: str,
        name: str,
        checksum: str,
        success: bool,
        execution_time_ms: int = 0,
        error_message: Optional[str] = None
    ):
        """Record a migration attempt."""
        insert_sql = f"""
        INSERT INTO {self.state_table} 
        (version, name, checksum, success, execution_time_ms, error_message)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        with self.db.cursor as cursor:
            cursor.execute(
                insert_sql,
                (version, name, checksum, success, execution_time_ms, error_message)
            )
            cursor.commit()
        
        status = "success" if success else "failed"
        logger.info(f"Recorded migration {version}: {status}")
    
    def record_rollback(self, version: str):
        """Mark a migration as rolled back."""
        update_sql = f"""
        UPDATE {self.state_table} 
        SET rolled_back = 1 
        WHERE version = ?
        """
        with self.db.cursor as cursor:
            cursor.execute(update_sql, (version,))
            cursor.commit()
        logger.info(f"Marked migration {version} as rolled back")
    
    def is_version_applied(self, version: str) -> bool:
        """Check if a specific version has been applied."""
        return version in self.get_applied_migrations()
    
    def detect_modifications(self, scripts: List[MigrationScript]) -> List[str]:
        """Detect if any applied migrations have been modified since application."""
        modifications = []
        applied = self.get_all_migrations()
        applied_map = {v: (name, checksum) for v, name, checksum, _, _ in applied}
        
        for script in scripts:
            if script.version in applied_map:
                stored_name, stored_checksum = applied_map[script.version]
                current_checksum = script.compute_checksum()
                
                if stored_checksum != current_checksum:
                    modifications.append(
                        f"Migration {script.version} has been modified since application"
                    )
                elif stored_name != script.name:
                    modifications.append(
                        f"Migration {script.version} name changed from {stored_name} to {script.name}"
                    )
        
        return modifications
