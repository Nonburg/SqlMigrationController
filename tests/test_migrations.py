"""Tests for SqlMigrationController."""

import pytest
from pathlib import Path
import tempfile
import shutil

from src.config import Config, DatabaseConfig, MigrationConfig
from src.migrations import MigrationScript, MigrationBatch, MigrationScanner


class TestMigrationScript:
    """Tests for MigrationScript class."""
    
    def test_parse_valid_up_script(self, tmp_path):
        """Test parsing a valid UP migration script filename."""
        script_file = tmp_path / "V001__create_users_table.sql"
        script_file.write_text("CREATE TABLE users (id INT);")
        
        script = MigrationScript.from_file(script_file)
        
        assert script is not None
        assert script.version == "001"
        assert script.name == "create_users_table"
        assert script.up_file == script_file
        assert script.down_file is None
    
    def test_parse_valid_down_script(self, tmp_path):
        """Test parsing a valid DOWN migration script filename."""
        script_file = tmp_path / "V001__create_users_table_down.sql"
        script_file.write_text("DROP TABLE users;")
        
        script = MigrationScript.from_file(script_file)
        
        assert script is not None
        assert script.version == "001"
        assert script.name == "create_users_table"
        assert script.up_file is None
        assert script.down_file == script_file
    
    def test_parse_invalid_filename(self, tmp_path):
        """Test parsing an invalid filename."""
        script_file = tmp_path / "invalid_name.sql"
        script_file.write_text("SELECT 1;")
        
        script = MigrationScript.from_file(script_file)
        
        assert script is None
    
    def test_compute_checksum(self, tmp_path):
        """Test checksum computation."""
        script_file = tmp_path / "V001__test.sql"
        script_file.write_text("CREATE TABLE test (id INT);")
        
        script = MigrationScript.from_file(script_file)
        checksum = script.compute_checksum()
        
        assert len(checksum) == 64  # SHA256 hex length
        assert checksum == script.compute_checksum()  # Consistent
    
    def test_full_name_property(self, tmp_path):
        """Test full_name property."""
        script_file = tmp_path / "V001__create_table.sql"
        script = MigrationScript.from_file(script_file)
        
        assert script.full_name == "V001__create_table"


class TestMigrationBatch:
    """Tests for MigrationBatch class."""
    
    def test_add_script_sorts_by_version(self, tmp_path):
        """Test that scripts are sorted by version when added."""
        batch = MigrationBatch()
        
        script3 = MigrationScript(
            version="003", name="third", up_file=tmp_path / "V003.sql"
        )
        script1 = MigrationScript(
            version="001", name="first", up_file=tmp_path / "V001.sql"
        )
        script2 = MigrationScript(
            version="002", name="second", up_file=tmp_path / "V002.sql"
        )
        
        batch.add_script(script3)
        batch.add_script(script1)
        batch.add_script(script2)
        
        assert batch.versions == ["001", "002", "003"]
    
    def test_initial_status(self):
        """Test initial batch status."""
        batch = MigrationBatch()
        assert batch.status == "pending"
        assert len(batch.scripts) == 0


class TestMigrationScanner:
    """Tests for MigrationScanner class."""
    
    def test_scan_empty_directory(self, tmp_path):
        """Test scanning an empty directory."""
        scanner = MigrationScanner(tmp_path)
        scripts = scanner.scan()
        
        assert len(scripts) == 0
    
    def test_scan_with_migrations(self, tmp_path):
        """Test scanning directory with migration files."""
        # Create migration files
        (tmp_path / "V001__create_users.sql").write_text("CREATE TABLE users;")
        (tmp_path / "V001__create_users_down.sql").write_text("DROP TABLE users;")
        (tmp_path / "V002__add_email.sql").write_text("ALTER TABLE users ADD email;")
        
        scanner = MigrationScanner(tmp_path)
        scripts = scanner.scan()
        
        assert len(scripts) == 2
        assert scripts[0].version == "001"
        assert scripts[0].down_file is not None
        assert scripts[1].version == "002"
    
    def test_validate_scripts_empty(self, tmp_path):
        """Test validation with no scripts."""
        scanner = MigrationScanner(tmp_path)
        errors = scanner.validate_scripts([])
        
        assert len(errors) == 0
    
    def test_validate_scripts_missing_up(self, tmp_path):
        """Test validation with missing UP script."""
        down_file = tmp_path / "V001__test_down.sql"
        down_file.write_text("DROP TABLE;")
        
        script = MigrationScript.from_file(down_file)
        scanner = MigrationScanner(tmp_path)
        errors = scanner.validate_scripts([script])
        
        assert any("Missing UP script" in err for err in errors)
    
    def test_validate_scripts_empty_content(self, tmp_path):
        """Test validation with empty script content."""
        up_file = tmp_path / "V001__test.sql"
        up_file.write_text("")  # Empty file
        
        script = MigrationScript.from_file(up_file)
        scanner = MigrationScanner(tmp_path)
        errors = scanner.validate_scripts([script])
        
        assert any("Empty UP script" in err for err in errors)


class TestConfig:
    """Tests for configuration classes."""
    
    def test_database_config_default(self):
        """Test default database configuration."""
        config = DatabaseConfig()
        
        assert config.host == "localhost"
        assert config.port == 1433
        assert config.driver == "ODBC Driver 17 for SQL Server"
    
    def test_database_config_connection_string(self):
        """Test connection string generation."""
        config = DatabaseConfig(
            host="myserver",
            port=1433,
            database="MyDB",
            username="sa",
            password="secret"
        )
        
        conn_str = config.connection_string
        assert "SERVER=myserver,1433" in conn_str
        assert "DATABASE=MyDB" in conn_str
        assert "UID=sa" in conn_str
        assert "PWD=secret" in conn_str
    
    def test_migration_config_creates_directories(self, tmp_path):
        """Test that migration config creates required directories."""
        migrations_dir = tmp_path / "migrations"
        log_dir = tmp_path / "logs"
        rollback_dir = tmp_path / "rollback"
        
        config = MigrationConfig(
            migrations_dir=migrations_dir,
            log_dir=log_dir,
            rollback_dir=rollback_dir
        )
        
        assert migrations_dir.exists()
        assert log_dir.exists()
        assert rollback_dir.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
