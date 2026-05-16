-- ================================================================
--  MiniBank — Database Schema for OIDC (Microsoft Entra ID)
-- ================================================================
--  Run this against your Azure SQL Database to create or migrate
--  the tables for OAuth 2.0 / OpenID Connect identity management.
--
--  Key change: the 'password' column is removed; users are now
--  identified by their Entra ID Object ID ('oid' claim).
-- ================================================================

-- Drop old tables if starting fresh (CAUTION: destroys data)
-- DROP TABLE IF EXISTS transactions;
-- DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    oid         NVARCHAR(128)  NOT NULL UNIQUE,   -- Entra ID Object ID
    username    NVARCHAR(255)  NOT NULL,           -- Display name from ID token
    email       NVARCHAR(255),                     -- preferred_username claim
    balance     DECIMAL(18,2)  NOT NULL DEFAULT 0
);

CREATE TABLE transactions (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    user_id     INT            NOT NULL,
    type        NVARCHAR(50)   NOT NULL,
    amount      DECIMAL(18,2)  NOT NULL,
    description NVARCHAR(255),
    timestamp   DATETIME       NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_transactions_users FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for fast user lookup by Entra ID Object ID
CREATE INDEX IX_users_oid ON users(oid);

-- ================================================================
--  If you are MIGRATING from the old password-based schema:
-- ================================================================
--  ALTER TABLE users ADD oid NVARCHAR(128) NULL;
--  ALTER TABLE users DROP COLUMN password;
--  -- After migration, make oid NOT NULL + UNIQUE:
--  -- UPDATE users SET oid = NEWID() WHERE oid IS NULL;  -- placeholder
--  -- ALTER TABLE users ALTER COLUMN oid NVARCHAR(128) NOT NULL;
--  -- CREATE UNIQUE INDEX UX_users_oid ON users(oid);
-- ================================================================
