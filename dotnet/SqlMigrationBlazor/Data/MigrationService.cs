using SqlMigrationBlazor.Models;

namespace SqlMigrationBlazor.Data;

/// <summary>
/// Service for managing migration configuration and operations.
/// </summary>
public class MigrationService
{
    private Config _config;

    public MigrationService()
    {
        _config = new Config
        {
            Database = new DatabaseConfig
            {
                Host = "localhost",
                Port = 1433,
                Database = "",
                Username = "",
                Password = ""
            },
            Migration = new MigrationConfig
            {
                MigrationsDir = "./migrations",
                StateTable = "MigrationState",
                DryRun = false,
                StopOnError = true
            }
        };
    }

    public Config Config => _config;

    public void UpdateDatabaseConfig(DatabaseConfig config)
    {
        _config.Database = config;
    }

    public void UpdateMigrationConfig(MigrationConfig config)
    {
        _config.Migration = config;
    }

    public void SetMigrationsDirectory(string path)
    {
        _config.MigrationsDir = path;
    }
}
