"""Configuration settings for SqlMigrationController."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DatabaseConfig:
    """SQL Server database configuration."""
    
    host: str = "localhost"
    port: int = 1433
    database: str = ""
    username: str = ""
    password: str = ""
    driver: str = "ODBC Driver 17 for SQL Server"
    
    @property
    def connection_string(self) -> str:
        """Build ODBC connection string."""
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password}"
        )


@dataclass
class MigrationConfig:
    """Migration controller configuration."""
    
    migrations_dir: Path = Path("./migrations")
    log_dir: Path = Path("./logs")
    rollback_dir: Path = Path("./rollback")
    state_table: str = "MigrationState"
    dry_run: bool = False
    stop_on_error: bool = True
    
    def __post_init__(self):
        """Ensure directories exist."""
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.rollback_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    """Main application configuration."""
    
    database: DatabaseConfig
    migration: MigrationConfig = None
    
    def __post_init__(self):
        if self.migration is None:
            self.migration = MigrationConfig()
