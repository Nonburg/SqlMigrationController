-- Откат таблицы пользователей
DROP INDEX IF EXISTS IX_users_email ON users;
DROP TABLE IF EXISTS users;
