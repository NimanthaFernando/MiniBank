"""
MiniBank DB integration tests.
Requires SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD env vars to be set.
Skipped automatically if DB is not available.
"""
import os
import pytest

# Skip entire module if DB env vars are not set
pytestmark = pytest.mark.skipif(
    not all([
        os.environ.get('SQL_SERVER'),
        os.environ.get('SQL_DATABASE'),
        os.environ.get('SQL_USER'),
        os.environ.get('SQL_PASSWORD'),
    ]),
    reason="DB environment variables not set — skipping DB tests"
)

import pyodbc


def get_conn():
    """Create a fresh DB connection from env vars."""
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_USER']};"
        f"PWD={os.environ['SQL_PASSWORD']};"
        f"Encrypt=yes;TrustServerCertificate=no;",
        timeout=15
    )


# --- Connection Tests ---

def test_db_connection():
    """Can connect to Azure SQL and run a basic query."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    conn.close()
    assert result[0] == 1


def test_users_table_exists():
    """The 'users' table exists in the database."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='users'"
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "Table 'users' does not exist"


def test_transactions_table_exists():
    """The 'transactions' table exists in the database."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='transactions'"
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "Table 'transactions' does not exist"


# --- Schema Validation Tests ---

def test_users_table_columns():
    """The 'users' table has the expected columns."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='users' ORDER BY ORDINAL_POSITION"
    )
    columns = [row[0] for row in cursor.fetchall()]
    conn.close()
    for expected in ['id', 'username', 'password', 'email', 'balance']:
        assert expected in columns, f"Column '{expected}' missing from users table"


def test_transactions_table_columns():
    """The 'transactions' table has the expected columns."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='transactions' ORDER BY ORDINAL_POSITION"
    )
    columns = [row[0] for row in cursor.fetchall()]
    conn.close()
    for expected in ['id', 'user_id', 'type', 'amount', 'description', 'timestamp']:
        assert expected in columns, f"Column '{expected}' missing from transactions table"


# --- CRUD Tests (uses a test user, cleaned up after) ---

TEST_USERNAME = "__ci_test_user__"


@pytest.fixture(autouse=True)
def cleanup_test_user():
    """Remove the CI test user before and after each test."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE user_id IN (SELECT id FROM users WHERE username=?)", (TEST_USERNAME,))
    cursor.execute("DELETE FROM users WHERE username=?", (TEST_USERNAME,))
    conn.commit()
    conn.close()
    yield
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE user_id IN (SELECT id FROM users WHERE username=?)", (TEST_USERNAME,))
    cursor.execute("DELETE FROM users WHERE username=?", (TEST_USERNAME,))
    conn.commit()
    conn.close()


def test_insert_and_select_user():
    """Can insert a user and read it back."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (username, password, email, balance) VALUES (?, ?, ?, ?)",
        (TEST_USERNAME, "fakehash123", "ci@test.com", 0)
    )
    conn.commit()

    cursor.execute("SELECT username, email, balance FROM users WHERE username=?", (TEST_USERNAME,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == TEST_USERNAME
    assert row[1] == "ci@test.com"
    assert row[2] == 0


def test_update_balance():
    """Can deposit (update balance) for a user."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (username, password, email, balance) VALUES (?, ?, ?, ?)",
        (TEST_USERNAME, "fakehash123", "ci@test.com", 0)
    )
    conn.commit()

    cursor.execute("UPDATE users SET balance = balance + ? WHERE username=?", (500.0, TEST_USERNAME))
    conn.commit()

    cursor.execute("SELECT balance FROM users WHERE username=?", (TEST_USERNAME,))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == 500.0


def test_insert_transaction():
    """Can insert a transaction record linked to a user."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (username, password, email, balance) VALUES (?, ?, ?, ?)",
        (TEST_USERNAME, "fakehash123", "ci@test.com", 100)
    )
    conn.commit()

    cursor.execute("SELECT id FROM users WHERE username=?", (TEST_USERNAME,))
    user_id = cursor.fetchone()[0]

    cursor.execute(
        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, "deposit", 100.0, "CI test deposit")
    )
    conn.commit()

    cursor.execute("SELECT type, amount, description FROM transactions WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "deposit"
    assert row[1] == 100.0
    assert row[2] == "CI test deposit"
