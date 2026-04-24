using System.Data;
using Microsoft.Data.SqlClient;
using SqlMigrationBlazor.Models;

namespace SqlMigrationBlazor.Services;

/// <summary>
/// Manages SQL Server database connections.
/// </summary>
public class DatabaseConnection : IDisposable
{
    private readonly DatabaseConfig _config;
    private SqlConnection? _connection;
    private bool _disposed;

    public DatabaseConnection(DatabaseConfig config)
    {
        _config = config;
    }

    public DatabaseConnection Connect()
    {
        try
        {
            _connection = new SqlConnection(_config.ConnectionString);
            _connection.Open();
            return this;
        }
        catch (SqlException e)
        {
            throw new InvalidOperationException($"Failed to connect to database: {e.Message}", e);
        }
    }

    public void Disconnect()
    {
        if (_connection != null)
        {
            if (_connection.State == ConnectionState.Open)
                _connection.Close();
            _connection.Dispose();
            _connection = null;
        }
    }

    public IDbCommand CreateCommand()
    {
        if (_connection == null || _connection.State != ConnectionState.Open)
            throw new InvalidOperationException("Not connected to database");
        
        return _connection.CreateCommand();
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
/// Tracks migration state in the database.
/// </summary>
public class MigrationStateRepository
{
    private readonly DatabaseConnection _db;
    private readonly string _stateTable;

    public MigrationStateRepository(DatabaseConnection db, string stateTable = "MigrationState")
    {
        _db = db;
        _stateTable = stateTable;
    }

    public void Initialize()
    {
        var createTableSql = $@"
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{_stateTable}' and xtype='U')
        CREATE TABLE {_stateTable} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            version NVARCHAR(50) NOT NULL UNIQUE,
            name NVARCHAR(255) NOT NULL,
            checksum NVARCHAR(64) NOT NULL,
            applied_at DATETIME NOT NULL DEFAULT GETDATE(),
            success BIT NOT NULL DEFAULT 1,
            execution_time_ms INT,
            error_message NVARCHAR(MAX),
            rolled_back BIT NOT NULL DEFAULT 0
        )";

        using var cmd = _db.CreateCommand();
        cmd.CommandText = createTableSql;
        cmd.ExecuteNonQuery();
    }

    public List<string> GetAppliedMigrations()
    {
        var query = $@"
        SELECT version FROM {_stateTable} 
        WHERE success = 1 AND rolled_back = 0 
        ORDER BY version";

        var result = new List<string>();
        using var cmd = _db.CreateCommand();
        cmd.CommandText = query;
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            result.Add(reader.GetString(0));
        }
        return result;
    }

    public List<(string Version, string Name, string Checksum, DateTime AppliedAt, bool Success)> GetAllMigrations()
    {
        var query = $@"
        SELECT version, name, checksum, applied_at, success 
        FROM {_stateTable} 
        ORDER BY version";

        var result = new List<(string, string, string, DateTime, bool)>();
        using var cmd = _db.CreateCommand();
        cmd.CommandText = query;
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            result.Add((
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetDateTime(3),
                reader.GetBoolean(4)
            ));
        }
        return result;
    }

    public void RecordMigration(
        string version,
        string name,
        string checksum,
        bool success,
        int executionTimeMs = 0,
        string? errorMessage = null)
    {
        var insertSql = $@"
        INSERT INTO {_stateTable} 
        (version, name, checksum, success, execution_time_ms, error_message)
        VALUES (@version, @name, @checksum, @success, @executionTimeMs, @errorMessage)";

        using var cmd = _db.CreateCommand();
        cmd.CommandText = insertSql;
        cmd.Parameters.AddWithValue("@version", version);
        cmd.Parameters.AddWithValue("@name", name);
        cmd.Parameters.AddWithValue("@checksum", checksum);
        cmd.Parameters.AddWithValue("@success", success);
        cmd.Parameters.AddWithValue("@executionTimeMs", executionTimeMs);
        cmd.Parameters.AddWithValue("@errorMessage", (object?)errorMessage ?? DBNull.Value);
        cmd.ExecuteNonQuery();
    }

    public void RecordRollback(string version)
    {
        var updateSql = $@"
        UPDATE {_stateTable} 
        SET rolled_back = 1 
        WHERE version = @version";

        using var cmd = _db.CreateCommand();
        cmd.CommandText = updateSql;
        cmd.Parameters.AddWithValue("@version", version);
        cmd.ExecuteNonQuery();
    }

    public bool IsVersionApplied(string version)
    {
        return GetAppliedMigrations().Contains(version);
    }

    public List<string> DetectModifications(List<MigrationScript> scripts)
    {
        var modifications = new List<string>();
        var applied = GetAllMigrations();
        var appliedMap = applied.ToDictionary(v => v.Version, v => (v.Name, v.Checksum));

        foreach (var script in scripts)
        {
            if (appliedMap.ContainsKey(script.Version))
            {
                var (storedName, storedChecksum) = appliedMap[script.Version];
                var currentChecksum = script.ComputeChecksum();

                if (storedChecksum != currentChecksum)
                {
                    modifications.Add($"Migration {script.Version} has been modified since application");
                }
                else if (storedName != script.Name)
                {
                    modifications.Add($"Migration {script.Version} name changed from {storedName} to {script.Name}");
                }
            }
        }

        return modifications;
    }
}
