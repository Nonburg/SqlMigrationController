using SqlMigrationBlazor.Models;
using SqlMigrationBlazor.Services;

namespace SqlMigrationBlazor.Services;

/// <summary>
/// Base exception for migration errors.
/// </summary>
public class MigrationException : Exception
{
    public MigrationException(string message) : base(message) { }
}

/// <summary>
/// Raised when migration validation fails.
/// </summary>
public class MigrationValidationException : MigrationException
{
    public MigrationValidationException(string message) : base(message) { }
}

/// <summary>
/// Raised when migration execution fails.
/// </summary>
public class MigrationExecutionException : MigrationException
{
    public MigrationExecutionException(string message, Exception? inner = null) 
        : base(message, inner) { }
}

/// <summary>
/// Main controller for managing SQL database migrations.
/// </summary>
public class SqlMigrationController : IDisposable
{
    private readonly Config _config;
    private readonly MigrationScanner _scanner;
    private DatabaseConnection? _dbConnection;
    private MigrationStateRepository? _stateRepo;
    private bool _disposed;

    public SqlMigrationController(Config config)
    {
        _config = config;
        _scanner = new MigrationScanner(_config.MigrationsDir);
    }

    public SqlMigrationController Connect()
    {
        _dbConnection = new DatabaseConnection(_config.Database);
        _dbConnection.Connect();
        _stateRepo = new MigrationStateRepository(_dbConnection, _config.StateTable);
        _stateRepo.Initialize();
        return this;
    }

    public void Disconnect()
    {
        if (_dbConnection != null)
        {
            _dbConnection.Dispose();
            _dbConnection = null;
            _stateRepo = null;
        }
    }

    public List<string> Validate()
    {
        var scripts = _scanner.Scan();
        var errors = _scanner.ValidateScripts(scripts);

        if (scripts.Count == 0)
        {
            errors.Add("No migration scripts found");
        }

        return errors;
    }

    public List<string> CheckForModifications()
    {
        if (_stateRepo == null)
            throw new MigrationException("Not connected to database");

        var scripts = _scanner.Scan();
        return _stateRepo.DetectModifications(scripts);
    }

    public MigrationBatch GetPendingMigrations()
    {
        if (_stateRepo == null)
            throw new MigrationException("Not connected to database");

        var appliedVersions = _stateRepo.GetAppliedMigrations();
        var allScripts = _scanner.Scan();

        var pending = new MigrationBatch();
        foreach (var script in allScripts)
        {
            if (!appliedVersions.Contains(script.Version))
            {
                pending.AddScript(script);
            }
        }

        return pending;
    }

    public double ExecuteScript(MigrationScript script)
    {
        if (_dbConnection == null)
            throw new MigrationException("Not connected to database");

        if (script.UpFile == null || !script.UpFile.Exists)
            throw new MigrationExecutionException($"UP script not found for {script.Version}");

        var sqlContent = File.ReadAllText(script.UpFile.FullName, System.Text.Encoding.UTF8);

        var startTime = DateTime.Now;

        try
        {
            using var cmd = _dbConnection.CreateCommand();
            // Execute multi-statement scripts
            foreach (var statement in sqlContent.Split(';'))
            {
                var trimmed = statement.Trim();
                if (!string.IsNullOrEmpty(trimmed))
                {
                    cmd.CommandText = trimmed;
                    cmd.ExecuteNonQuery();
                }
            }

            var endTime = DateTime.Now;
            var executionTime = (endTime - startTime).TotalMilliseconds;

            return executionTime;
        }
        catch (Exception e)
        {
            throw new MigrationExecutionException($"Failed to execute {script.Version}: {e.Message}", e);
        }
    }

    public MigrationBatch ApplyMigrations(MigrationBatch? batch = null)
    {
        if (_stateRepo == null)
            throw new MigrationException("Not connected to database");

        if (batch == null)
            batch = GetPendingMigrations();

        if (batch.Scripts.Count == 0)
        {
            batch.Status = "completed";
            return batch;
        }

        // Check for modifications before applying
        var modifications = CheckForModifications();
        if (modifications.Count > 0 && _config.StopOnError)
        {
            throw new MigrationValidationException(
                $"Detected modifications to applied migrations: {string.Join("; ", modifications)}");
        }

        batch.Status = "running";
        batch.StartTime = DateTime.Now;

        try
        {
            foreach (var script in batch.Scripts)
            {
                if (_config.DryRun)
                {
                    continue;
                }

                var checksum = script.ComputeChecksum();

                try
                {
                    var executionTime = ExecuteScript(script);

                    _stateRepo.RecordMigration(
                        version: script.Version,
                        name: script.Name,
                        checksum: checksum,
                        success: true,
                        executionTimeMs: (int)executionTime
                    );

                    script.AppliedAt = DateTime.Now;
                }
                catch (MigrationExecutionException e)
                {
                    _stateRepo.RecordMigration(
                        version: script.Version,
                        name: script.Name,
                        checksum: checksum,
                        success: false,
                        errorMessage: e.Message
                    );

                    batch.Status = "failed";

                    if (_config.StopOnError)
                        throw;
                }
            }
        }
        catch (Exception e)
        {
            batch.Status = "failed";
            throw;
        }
        finally
        {
            batch.EndTime = DateTime.Now;
            if (batch.Status == "running")
                batch.Status = "completed";
        }

        return batch;
    }

    public bool RollbackMigration(string version)
    {
        if (_stateRepo == null)
            throw new MigrationException("Not connected to database");

        if (!_stateRepo.IsVersionApplied(version))
        {
            return false;
        }

        // Find the down script
        var allScripts = _scanner.Scan();
        var script = allScripts.FirstOrDefault(s => s.Version == version);

        if (script == null || script.DownFile == null || !script.DownFile.Exists)
        {
            return false;
        }

        var sqlContent = File.ReadAllText(script.DownFile.FullName, System.Text.Encoding.UTF8);

        try
        {
            using var cmd = _dbConnection!.CreateCommand();
            foreach (var statement in sqlContent.Split(';'))
            {
                var trimmed = statement.Trim();
                if (!string.IsNullOrEmpty(trimmed))
                {
                    cmd.CommandText = trimmed;
                    cmd.ExecuteNonQuery();
                }
            }

            _stateRepo.RecordRollback(version);
            return true;
        }
        catch (Exception e)
        {
            throw new MigrationExecutionException($"Rollback failed: {e.Message}", e);
        }
    }

    public bool RollbackLast()
    {
        if (_stateRepo == null)
            throw new MigrationException("Not connected to database");

        var applied = _stateRepo.GetAppliedMigrations();

        if (applied.Count == 0)
            return false;

        var lastVersion = applied.Last();
        return RollbackMigration(lastVersion);
    }

    public MigrationStatus Status()
    {
        if (_stateRepo == null)
            throw new MigrationException("Not connected to database");

        var applied = _stateRepo.GetAppliedMigrations();
        var pending = GetPendingMigrations();
        var allMigrations = _stateRepo.GetAllMigrations();

        return new MigrationStatus
        {
            AppliedCount = applied.Count,
            PendingCount = pending.Scripts.Count,
            AppliedVersions = applied,
            PendingVersions = pending.Versions,
            LastApplied = applied.Count > 0 ? applied.Last() : null,
            AllMigrations = allMigrations.Select(m => new MigrationInfo
            {
                Version = m.Version,
                Name = m.Name,
                Checksum = m.Checksum.Length > 8 ? m.Checksum.Substring(0, 8) + "..." : m.Checksum,
                AppliedAt = m.AppliedAt,
                Success = m.Success
            }).ToList()
        };
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            Disconnect();
            _disposed = true;
        }
        GC.SuppressFinalize(this);
    }
}

/// <summary>
/// Migration status information.
/// </summary>
public class MigrationStatus
{
    public int AppliedCount { get; set; }
    public int PendingCount { get; set; }
    public List<string> AppliedVersions { get; set; } = new();
    public List<string> PendingVersions { get; set; } = new();
    public string? LastApplied { get; set; }
    public List<MigrationInfo> AllMigrations { get; set; } = new();
}

/// <summary>
/// Individual migration information.
/// </summary>
public class MigrationInfo
{
    public string Version { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string? Checksum { get; set; }
    public DateTime AppliedAt { get; set; }
    public bool Success { get; set; }
}
