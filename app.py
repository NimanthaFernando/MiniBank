from flask import Flask, render_template, request, redirect, session, flash, url_for
import hashlib
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

# --- Azure SQL Database Configuration ---
DB_AVAILABLE = False
conn_str = None

SQL_SERVER = os.environ.get('SQL_SERVER')       # e.g. yourserver.database.windows.net
SQL_DATABASE = os.environ.get('SQL_DATABASE')    # e.g. bankdb
SQL_USER = os.environ.get('SQL_USER')            # e.g. sqladmin
SQL_PASSWORD = os.environ.get('SQL_PASSWORD')

if SQL_SERVER and SQL_USER and SQL_PASSWORD and SQL_DATABASE:
    try:
        import pyodbc
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={SQL_SERVER};"
            f"DATABASE={SQL_DATABASE};"
            f"UID={SQL_USER};"
            f"PWD={SQL_PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
        )
        # Test connection on startup
        test_conn = pyodbc.connect(conn_str, timeout=10)
        test_conn.close()
        DB_AVAILABLE = True
        print("[INFO] Azure SQL Database connected successfully.")
    except Exception as e:
        print(f"[WARNING] Azure SQL not available: {e}. Running in frontend-only mode.")
else:
    print("[WARNING] SQL env vars not set. Running in frontend-only mode.")


def get_db_connection():
    """Get a fresh database connection."""
    import pyodbc
    return pyodbc.connect(conn_str)


def row_to_dict(cursor, row):
    """Convert a pyodbc Row to a dictionary."""
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def rows_to_dicts(cursor, rows):
    """Convert a list of pyodbc Rows to a list of dictionaries."""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


@app.route('/')
def index():
    if 'loggedin' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not DB_AVAILABLE:
        flash('Database not configured. Login is currently unavailable.', 'danger')
        return render_template('login.html')

    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        row = cursor.fetchone()
        account = row_to_dict(cursor, row)
        conn.close()

        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            return redirect(url_for('dashboard'))
        else:
            msg = 'Incorrect username or password!'
    return render_template('login.html', msg=msg)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if not DB_AVAILABLE:
        flash('Database not configured. Registration is currently unavailable.', 'danger')
        return render_template('register.html')

    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        email = request.form['email']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, email, balance) VALUES (?, ?, ?, ?)",
                       (username, password, email, 0))
        conn.commit()
        conn.close()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if 'loggedin' not in session:
        return redirect(url_for('index'))

    if not DB_AVAILABLE:
        flash('Database not configured.', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=?", (session['id'],))
    user = row_to_dict(cursor, cursor.fetchone())

    cursor.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY timestamp DESC", (session['id'],))
    transactions = rows_to_dicts(cursor, cursor.fetchall())

    conn.close()

    return render_template('dashboard.html', user=user, transactions=transactions)


@app.route('/deposit', methods=['POST'])
def deposit():
    if 'loggedin' not in session:
        return redirect(url_for('index'))

    if not DB_AVAILABLE:
        flash('Database not configured.', 'danger')
        return redirect(url_for('index'))

    amount = float(request.form['amount'])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, session['id']))
    cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'deposit', ?, ?)",
                   (session['id'], amount, 'Deposit'))
    conn.commit()
    conn.close()
    flash('Deposit successful!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
