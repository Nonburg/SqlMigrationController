namespace SqlMigrationBlazor.Models;

/// <summary>
/// SQL Server database configuration.
/// </summary>
public class DatabaseConfig
{
    public string Host { get; set; } = "localhost";
    public int Port { get; set; } = 1433;
    public string Database { get; set; } = string.Empty;
    public string Username { get; set; } = string.Empty;
    public string Password { get; set; } = string.Empty;
    public string Driver { get; set; } = "ODBC Driver 17 for SQL Server";

    /// <summary>
    /// Build SQL Server connection string.
    /// </summary>
    public string ConnectionString => 
        $"Server={Host},{Port};Database={Database};User Id={Username};Password={Password};TrustServerCertificate=True;";
}

/// <summary>
/// Migration controller configuration.
/// </summary>
public class MigrationConfig
{
    public string MigrationsDir { get; set; } = "./migrations";
    public string LogDir { get; set; } = "./logs";
    public string RollbackDir { get; set; } = "./rollback";
    public string StateTable { get; set; } = "MigrationState";
    public bool DryRun { get; set; } = false;
    public bool StopOnError { get; set; } = true;
}

/// <summary>
/// Main application configuration.
/// </summary>
public class Config
{
    public DatabaseConfig Database { get; set; } = new();
    public MigrationConfig Migration { get; set; } = new();
}
