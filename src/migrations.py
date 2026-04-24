"""Migration file handling and version tracking."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class MigrationScript:
    """Represents a single migration script."""
    
    version: str
    name: str
    up_file: Path
    down_file: Optional[Path] = None
    applied_at: Optional[datetime] = None
    checksum: str = ""
    
    @classmethod
    def from_file(cls, file_path: Path) -> Optional["MigrationScript"]:
        """Parse migration script from filename.
        
        Expected format: V{version}__{name}.sql or V{version}__{name}_down.sql
        Example: V001__create_users_table.sql, V001__create_users_table_down.sql
        """
        pattern = r"^V(\d+)__(.+?)(?:_down)?\.sql$"
        match = re.match(pattern, file_path.name)
        
        if not match:
            return None
        
        version = match.group(1).zfill(3)  # Normalize to 3 digits
        name = match.group(2)
        is_down = "_down" in file_path.name
        
        return cls(
            version=version,
            name=name,
            up_file=file_path if not is_down else None,
            down_file=file_path if is_down else None,
        )
    
    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of the migration script."""
        import hashlib
        
        if not self.up_file or not self.up_file.exists():
            return ""
        
        content = self.up_file.read_text(encoding="utf-8")
        return hashlib.sha256(content.encode()).hexdigest()
    
    @property
    def full_name(self) -> str:
        """Return full migration name with version."""
        return f"V{self.version}__{self.name}"


@dataclass
class MigrationBatch:
    """Represents a batch of migrations to be applied."""
    
    scripts: List[MigrationScript] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed, rolled_back
    
    def add_script(self, script: MigrationScript):
        """Add a migration script to the batch."""
        self.scripts.append(script)
        self.scripts.sort(key=lambda s: s.version)
    
    @property
    def versions(self) -> List[str]:
        """Return list of versions in the batch."""
        return [s.version for s in self.scripts]


class MigrationScanner:
    """Scans directory for migration scripts."""
    
    def __init__(self, migrations_dir: Path):
        self.migrations_dir = migrations_dir
    
    def scan(self) -> List[MigrationScript]:
        """Scan directory and return all migration scripts."""
        if not self.migrations_dir.exists():
            return []
        
        migrations = {}
        
        for file_path in self.migrations_dir.glob("*.sql"):
            script = MigrationScript.from_file(file_path)
            if script:
                version = script.version
                
                if version not in migrations:
                    migrations[version] = script
                else:
                    existing = migrations[version]
                    if script.down_file:
                        existing.down_file = script.down_file
                    elif script.up_file:
                        existing.up_file = script.up_file
        
        result = list(migrations.values())
        result.sort(key=lambda s: s.version)
        return result
    
    def validate_scripts(self, scripts: List[MigrationScript]) -> List[str]:
        """Validate migration scripts and return list of errors."""
        errors = []
        
        for script in scripts:
            if not script.up_file or not script.up_file.exists():
                errors.append(f"Missing UP script for version {script.version}")
            elif not script.up_file.read_text(encoding="utf-8").strip():
                errors.append(f"Empty UP script for version {script.version}")
        
        # Check for gaps in version sequence (optional warning)
        if scripts:
            versions = [int(s.version) for s in scripts]
            expected = list(range(min(versions), max(versions) + 1))
            missing = set(expected) - set(versions)
            if missing:
                errors.append(f"Warning: Missing versions: {sorted(missing)}")
        
        return errors
