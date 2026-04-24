#!/usr/bin/env python3
"""Command-line interface for SqlMigrationController."""

import argparse
import logging
import sys
from pathlib import Path

from src.config import Config, DatabaseConfig, MigrationConfig
from src.controller import SqlMigrationController, create_config_from_env


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def cmd_validate(args):
    """Validate migration scripts."""
    config = create_config_from_env()
    
    if args.database:
        config.database.database = args.database
    if args.host:
        config.database.host = args.host
    if args.user:
        config.database.username = args.user
    
    controller = SqlMigrationController(config)
    errors = controller.validate()
    
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print("✓ All migration scripts are valid")
        return 0


def cmd_status(args):
    """Show current migration status."""
    config = create_config_from_env()
    
    if args.database:
        config.database.database = args.database
    if args.host:
        config.database.host = args.host
    if args.user:
        config.database.username = args.user
    if args.password:
        config.database.password = args.password
    
    try:
        with SqlMigrationController(config) as controller:
            status = controller.status()
            
            print(f"\n=== Migration Status ===")
            print(f"Applied: {status['applied_count']}")
            print(f"Pending: {status['pending_count']}")
            
            if status['applied_versions']:
                print(f"\nApplied versions: {', '.join(status['applied_versions'])}")
            
            if status['pending_versions']:
                print(f"Pending versions: {', '.join(status['pending_versions'])}")
            
            if status['last_applied']:
                print(f"Last applied: {status['last_applied']}")
            
            return 0
            
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_migrate(args):
    """Apply pending migrations."""
    config = create_config_from_env()
    
    if args.database:
        config.database.database = args.database
    if args.host:
        config.database.host = args.host
    if args.user:
        config.database.username = args.user
    if args.password:
        config.database.password = args.password
    
    config.migration.dry_run = args.dry_run
    config.migration.stop_on_error = not args.continue_on_error
    
    try:
        with SqlMigrationController(config) as controller:
            # First validate
            errors = controller.validate()
            if errors:
                print("Validation failed:")
                for error in errors:
                    print(f"  - {error}")
                return 1
            
            # Check for modifications
            modifications = controller.check_for_modifications()
            if modifications and not args.force:
                print("Warning: Detected modifications to applied migrations:")
                for mod in modifications:
                    print(f"  - {mod}")
                print("\nUse --force to proceed anyway")
                return 1
            
            # Apply migrations
            batch = controller.apply_migrations()
            
            print(f"\n=== Migration Complete ===")
            print(f"Status: {batch.status}")
            print(f"Scripts executed: {len(batch.scripts)}")
            
            if batch.start_time and batch.end_time:
                duration = (batch.end_time - batch.start_time).total_seconds()
                print(f"Total time: {duration:.2f}s")
            
            return 0 if batch.status == "completed" else 1
            
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            logging.exception("Detailed error:")
        return 1


def cmd_rollback(args):
    """Rollback migrations."""
    config = create_config_from_env()
    
    if args.database:
        config.database.database = args.database
    if args.host:
        config.database.host = args.host
    if args.user:
        config.database.username = args.user
    if args.password:
        config.database.password = args.password
    
    try:
        with SqlMigrationController(config) as controller:
            if args.version:
                success = controller.rollback_migration(args.version)
                if success:
                    print(f"✓ Rolled back migration {args.version}")
                else:
                    print(f"Failed to rollback migration {args.version}")
                    return 1
            else:
                success = controller.rollback_last()
                if success:
                    print("✓ Rolled back last migration")
                else:
                    print("No migrations to rollback")
            
            return 0
            
    except Exception as e:
        print(f"Error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="SqlMigrationController - Batch SQL migration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s validate
  %(prog)s status --database MyDB --host localhost --user sa
  %(prog)s migrate --database MyDB --user sa --password secret
  %(prog)s migrate --dry-run
  %(prog)s rollback --version 001
  %(prog)s rollback
        """
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate migration scripts")
    validate_parser.add_argument("--database", "-d", help="Database name")
    validate_parser.add_argument("--host", help="Database host")
    validate_parser.add_argument("--user", "-u", help="Database user")
    validate_parser.set_defaults(func=cmd_validate)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show migration status")
    status_parser.add_argument("--database", "-d", required=True, help="Database name")
    status_parser.add_argument("--host", default="localhost", help="Database host")
    status_parser.add_argument("--user", "-u", required=True, help="Database user")
    status_parser.add_argument("--password", "-p", help="Database password")
    status_parser.set_defaults(func=cmd_status)
    
    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Apply pending migrations")
    migrate_parser.add_argument("--database", "-d", required=True, help="Database name")
    migrate_parser.add_argument("--host", default="localhost", help="Database host")
    migrate_parser.add_argument("--user", "-u", required=True, help="Database user")
    migrate_parser.add_argument("--password", "-p", help="Database password")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show what would be executed")
    migrate_parser.add_argument("--force", action="store_true", help="Force apply despite modifications")
    migrate_parser.add_argument("--continue-on-error", action="store_true", help="Continue on errors")
    migrate_parser.set_defaults(func=cmd_migrate)
    
    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument("--database", "-d", required=True, help="Database name")
    rollback_parser.add_argument("--host", default="localhost", help="Database host")
    rollback_parser.add_argument("--user", "-u", required=True, help="Database user")
    rollback_parser.add_argument("--password", "-p", help="Database password")
    rollback_parser.add_argument("--version", "-V", help="Specific version to rollback")
    rollback_parser.set_defaults(func=cmd_rollback)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
