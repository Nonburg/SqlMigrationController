"""Main migration controller for batch SQL script execution."""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import Config, DatabaseConfig, MigrationConfig
from .database import DatabaseConnection, MigrationStateRepository
from .migrations import MigrationBatch, MigrationScanner, MigrationScript

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Base exception for migration errors."""
    pass


class MigrationValidationError(MigrationError):
    """Raised when migration validation fails."""
    pass


class MigrationExecutionError(MigrationError):
    """Raised when migration execution fails."""
    pass


class SqlMigrationController:
    """
    Main controller for managing SQL database migrations.
    
    Features:
    - Tracks all applied migrations in the database
    - Detects modifications to already-applied migrations
    - Applies migrations sequentially in version order
    - Supports rollback mechanism
    - Provides detailed logging and error reporting
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.db_config = config.database
        self.migration_config = config.migration
        self.scanner = MigrationScanner(self.migration_config.migrations_dir)
        self.db_connection: Optional[DatabaseConnection] = None
        self.state_repo: Optional[MigrationStateRepository] = None
    
    def connect(self) -> "SqlMigrationController":
        """Establish database connection and initialize state tracking."""
        self.db_connection = DatabaseConnection(self.db_config)
        self.db_connection.connect()
        self.state_repo = MigrationStateRepository(
            self.db_connection,
            self.migration_config.state_table
        )
        self.state_repo.initialize()
        return self
    
    def disconnect(self):
        """Close database connection."""
        if self.db_connection:
            self.db_connection.disconnect()
            self.db_connection = None
            self.state_repo = None
    
    def __enter__(self) -> "SqlMigrationController":
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
    
    def validate(self) -> List[str]:
        """
        Validate all migration scripts.
        
        Returns:
            List of validation errors (empty if valid)
        """
        scripts = self.scanner.scan()
        errors = self.scanner.validate_scripts(scripts)
        
        if not scripts:
            errors.append("No migration scripts found")
        
        return errors
    
    def check_for_modifications(self) -> List[str]:
        """
        Check if any applied migrations have been modified.
        
        Returns:
            List of modification warnings
        """
        if not self.state_repo:
            raise MigrationError("Not connected to database")
        
        scripts = self.scanner.scan()
        return self.state_repo.detect_modifications(scripts)
    
    def get_pending_migrations(self) -> MigrationBatch:
        """
        Get all pending migrations that need to be applied.
        
        Returns:
            Batch of pending migration scripts
        """
        if not self.state_repo:
            raise MigrationError("Not connected to database")
        
        applied_versions = self.state_repo.get_applied_migrations()
        all_scripts = self.scanner.scan()
        
        pending = MigrationBatch()
        for script in all_scripts:
            if script.version not in applied_versions:
                pending.add_script(script)
        
        logger.info(f"Found {len(pending.scripts)} pending migrations")
        return pending
    
    def execute_script(self, script: MigrationScript) -> float:
        """
        Execute a single migration script.
        
        Args:
            script: The migration script to execute
            
        Returns:
            Execution time in milliseconds
        """
        if not self.db_connection:
            raise MigrationError("Not connected to database")
        
        if not script.up_file or not script.up_file.exists():
            raise MigrationExecutionError(f"UP script not found for {script.version}")
        
        sql_content = script.up_file.read_text(encoding="utf-8")
        
        start_time = datetime.now()
        
        try:
            with self.db_connection.cursor as cursor:
                # Execute multi-statement scripts
                for statement in sql_content.split(";"):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                cursor.commit()
            
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds() * 1000
            
            logger.info(f"Executed migration {script.version} in {execution_time:.2f}ms")
            return execution_time
            
        except Exception as e:
            raise MigrationExecutionError(f"Failed to execute {script.version}: {str(e)}")
    
    def apply_migrations(self, batch: Optional[MigrationBatch] = None) -> MigrationBatch:
        """
        Apply all pending migrations.
        
        Args:
            batch: Optional specific batch to apply. If None, applies all pending.
            
        Returns:
            The migration batch with updated status
        """
        if not self.state_repo:
            raise MigrationError("Not connected to database")
        
        if batch is None:
            batch = self.get_pending_migrations()
        
        if not batch.scripts:
            logger.info("No pending migrations to apply")
            batch.status = "completed"
            return batch
        
        # Check for modifications before applying
        modifications = self.check_for_modifications()
        if modifications:
            for warning in modifications:
                logger.warning(warning)
            if self.migration_config.stop_on_error:
                raise MigrationValidationError(
                    f"Detected modifications to applied migrations: {modifications}"
                )
        
        batch.status = "running"
        batch.start_time = datetime.now()
        
        executed_scripts = []
        
        try:
            for script in batch.scripts:
                if self.migration_config.dry_run:
                    logger.info(f"[DRY RUN] Would apply migration {script.full_name}")
                    continue
                
                checksum = script.compute_checksum()
                
                try:
                    execution_time = self.execute_script(script)
                    
                    self.state_repo.record_migration(
                        version=script.version,
                        name=script.name,
                        checksum=checksum,
                        success=True,
                        execution_time_ms=int(execution_time)
                    )
                    
                    script.applied_at = datetime.now()
                    executed_scripts.append(script)
                    
                except MigrationExecutionError as e:
                    logger.error(f"Migration failed: {e}")
                    
                    self.state_repo.record_migration(
                        version=script.version,
                        name=script.name,
                        checksum=checksum,
                        success=False,
                        error_message=str(e)
                    )
                    
                    batch.status = "failed"
                    
                    if self.migration_config.stop_on_error:
                        raise
                    
                    # Continue with next migration if stop_on_error is False
                    
        except Exception as e:
            batch.status = "failed"
            logger.error(f"Migration batch failed: {e}")
            raise
        
        finally:
            batch.end_time = datetime.now()
            if batch.status == "running":
                batch.status = "completed"
        
        logger.info(f"Migration batch completed with status: {batch.status}")
        return batch
    
    def rollback_migration(self, version: str) -> bool:
        """
        Rollback a specific migration.
        
        Args:
            version: The version to rollback
            
        Returns:
            True if rollback was successful
        """
        if not self.state_repo:
            raise MigrationError("Not connected to database")
        
        if not self.state_repo.is_version_applied(version):
            logger.warning(f"Migration {version} is not applied, skipping rollback")
            return False
        
        # Find the down script
        all_scripts = self.scanner.scan()
        script = next((s for s in all_scripts if s.version == version), None)
        
        if not script or not script.down_file or not script.down_file.exists():
            logger.error(f"No rollback script found for version {version}")
            return False
        
        sql_content = script.down_file.read_text(encoding="utf-8")
        
        try:
            with self.db_connection.cursor as cursor:
                for statement in sql_content.split(";"):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                cursor.commit()
            
            self.state_repo.record_rollback(version)
            logger.info(f"Successfully rolled back migration {version}")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed for {version}: {e}")
            raise MigrationExecutionError(f"Rollback failed: {str(e)}")
    
    def rollback_last(self) -> bool:
        """
        Rollback the most recently applied migration.
        
        Returns:
            True if rollback was successful
        """
        if not self.state_repo:
            raise MigrationError("Not connected to database")
        
        applied = self.state_repo.get_applied_migrations()
        
        if not applied:
            logger.info("No migrations to rollback")
            return False
        
        last_version = applied[-1]
        return self.rollback_migration(last_version)
    
    def status(self) -> dict:
        """
        Get current migration status.
        
        Returns:
            Dictionary with migration status information
        """
        if not self.state_repo:
            raise MigrationError("Not connected to database")
        
        applied = self.state_repo.get_applied_migrations()
        pending = self.get_pending_migrations()
        all_migrations = self.state_repo.get_all_migrations()
        
        return {
            "applied_count": len(applied),
            "pending_count": len(pending.scripts),
            "applied_versions": applied,
            "pending_versions": pending.versions,
            "last_applied": applied[-1] if applied else None,
            "all_migrations": [
                {
                    "version": v,
                    "name": n,
                    "checksum": c[:8] + "..." if c else None,
                    "applied_at": t,
                    "success": s
                }
                for v, n, c, t, s in all_migrations
            ]
        }


def create_config_from_env() -> Config:
    """Create configuration from environment variables."""
    import os
    
    db_config = DatabaseConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "1433")),
        database=os.getenv("DB_NAME", ""),
        username=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
    )
    
    migration_config = MigrationConfig(
        migrations_dir=Path(os.getenv("MIGRATIONS_DIR", "./migrations")),
        log_dir=Path(os.getenv("LOGS_DIR", "./logs")),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        stop_on_error=os.getenv("STOP_ON_ERROR", "true").lower() != "false",
    )
    
    return Config(database=db_config, migration=migration_config)
