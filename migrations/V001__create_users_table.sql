-- Создание таблицы пользователей
CREATE TABLE users (
    id INT IDENTITY(1,1) PRIMARY KEY,
    username NVARCHAR(50) NOT NULL UNIQUE,
    email NVARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT GETDATE()
);

-- Создание индекса для email
CREATE INDEX IX_users_email ON users(email);
