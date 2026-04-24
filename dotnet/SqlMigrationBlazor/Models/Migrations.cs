using System.Security.Cryptography;
using System.Text;

namespace SqlMigrationBlazor.Models;

/// <summary>
/// Represents a single migration script.
/// </summary>
public class MigrationScript
{
    public string Version { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public FileInfo? UpFile { get; set; }
    public FileInfo? DownFile { get; set; }
    public DateTime? AppliedAt { get; set; }
    public string Checksum { get; set; } = string.Empty;

    /// <summary>
    /// Parse migration script from filename.
    /// Expected format: V{version}__{name}.sql or V{version}__{name}_down.sql
    /// Example: V001__create_users_table.sql, V001__create_users_table_down.sql
    /// </summary>
    public static MigrationScript? FromFile(FileInfo filePath)
    {
        var pattern = @"^V(\d+)__(.+?)(?:_down)?\.sql$";
        var match = System.Text.RegularExpressions.Regex.Match(filePath.Name, pattern);

        if (!match.Success)
            return null;

        var version = match.Groups[1].Value.PadLeft(3, '0');
        var name = match.Groups[2].Value;
        var isDown = filePath.Name.Contains("_down");

        return new MigrationScript
        {
            Version = version,
            Name = name,
            UpFile = !isDown ? filePath : null,
            DownFile = isDown ? filePath : null
        };
    }

    /// <summary>
    /// Compute SHA256 checksum of the migration script.
    /// </summary>
    public string ComputeChecksum()
    {
        if (UpFile == null || !UpFile.Exists)
            return string.Empty;

        var content = File.ReadAllText(UpFile.FullName, Encoding.UTF8);
        using var sha256 = SHA256.Create();
        var hash = sha256.ComputeHash(Encoding.UTF8.GetBytes(content));
        return BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant();
    }

    /// <summary>
    /// Return full migration name with version.
    /// </summary>
    public string FullName => $"V{Version}__{Name}";
}

/// <summary>
/// Represents a batch of migrations to be applied.
/// </summary>
public class MigrationBatch
{
    public List<MigrationScript> Scripts { get; set; } = new();
    public DateTime? StartTime { get; set; }
    public DateTime? EndTime { get; set; }
    public string Status { get; set; } = "pending"; // pending, running, completed, failed, rolled_back

    public void AddScript(MigrationScript script)
    {
        Scripts.Add(script);
        Scripts = Scripts.OrderBy(s => s.Version).ToList();
    }

    public List<string> Versions => Scripts.Select(s => s.Version).ToList();
}

/// <summary>
/// Scans directory for migration scripts.
/// </summary>
public class MigrationScanner
{
    private readonly DirectoryInfo _migrationsDir;

    public MigrationScanner(string migrationsDir)
    {
        _migrationsDir = new DirectoryInfo(migrationsDir);
    }

    public List<MigrationScript> Scan()
    {
        if (!_migrationsDir.Exists)
            return new List<MigrationScript>();

        var migrations = new Dictionary<string, MigrationScript>();

        foreach (var file in _migrationsDir.GetFiles("*.sql"))
        {
            var script = MigrationScript.FromFile(file);
            if (script != null)
            {
                var version = script.Version;

                if (!migrations.ContainsKey(version))
                {
                    migrations[version] = script;
                }
                else
                {
                    var existing = migrations[version];
                    if (script.DownFile != null)
                        existing.DownFile = script.DownFile;
                    else if (script.UpFile != null)
                        existing.UpFile = script.UpFile;
                }
            }
        }

        var result = migrations.Values.ToList();
        result.Sort((a, b) => string.Compare(a.Version, b.Version, StringComparison.Ordinal));
        return result;
    }

    public List<string> ValidateScripts(List<MigrationScript> scripts)
    {
        var errors = new List<string>();

        foreach (var script in scripts)
        {
            if (script.UpFile == null || !script.UpFile.Exists)
            {
                errors.Add($"Missing UP script for version {script.Version}");
            }
            else if (string.IsNullOrWhiteSpace(File.ReadAllText(script.UpFile.FullName, Encoding.UTF8)))
            {
                errors.Add($"Empty UP script for version {script.Version}");
            }
        }

        // Check for gaps in version sequence (optional warning)
        if (scripts.Count > 0)
        {
            var versions = scripts.Select(s => int.Parse(s.Version)).ToList();
            var expected = Enumerable.Range(versions.Min(), versions.Max() - versions.Min() + 1).ToList();
            var missing = expected.Except(versions).ToList();
            if (missing.Count > 0)
            {
                errors.Add($"Warning: Missing versions: {string.Join(", ", missing)}");
            }
        }

        return errors;
    }
}
