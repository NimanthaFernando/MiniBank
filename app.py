from flask import Flask, render_template, request, redirect, session, flash, url_for
import msal
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')

# --- Server-side sessions (required for MSAL auth flow state) ---
from flask_session import Session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

# --- Microsoft Entra ID (Azure AD) Configuration ---
AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID', '')
AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET', '')
AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID', 'common')
AZURE_REDIRECT_URI = os.environ.get('AZURE_REDIRECT_URI', 'http://localhost:5000/auth/callback')

AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
SCOPE = ["User.Read"]  # Microsoft Graph scope for basic profile info

OIDC_CONFIGURED = bool(AZURE_CLIENT_ID and AZURE_CLIENT_SECRET)

if OIDC_CONFIGURED:
    print("[INFO] Microsoft Entra ID (OIDC) configured.")
else:
    print("[WARNING] AZURE_CLIENT_ID / AZURE_CLIENT_SECRET not set. OIDC login unavailable.")

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


# ────────────────────────────────────────────
#  Database helpers
# ────────────────────────────────────────────

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


# ────────────────────────────────────────────
#  MSAL helpers
# ────────────────────────────────────────────

def _build_msal_app():
    """Create a confidential MSAL application instance."""
    return msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=AUTHORITY,
        client_credential=AZURE_CLIENT_SECRET,
    )


def _get_or_create_db_user(user_info):
    """Auto-provision a user record in the database on first OIDC login.

    Uses the Entra ID Object ID (oid) as the unique key. On subsequent
    logins the display name and email are synced from the ID token.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    oid = user_info['oid']

    cursor.execute('SELECT * FROM users WHERE oid = ?', (oid,))
    row = cursor.fetchone()
    user = row_to_dict(cursor, row)

    if not user:
        # First-time login — create user with zero balance
        cursor.execute(
            "INSERT INTO users (oid, username, email, balance) VALUES (?, ?, ?, ?)",
            (oid, user_info['name'], user_info['email'], 0)
        )
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE oid = ?', (oid,))
        user = row_to_dict(cursor, cursor.fetchone())
    else:
        # Sync display name / email from Entra ID
        cursor.execute(
            "UPDATE users SET username = ?, email = ? WHERE oid = ?",
            (user_info['name'], user_info['email'], oid)
        )
        conn.commit()
        user['username'] = user_info['name']
        user['email'] = user_info['email']

    conn.close()
    return user


# ────────────────────────────────────────────
#  Routes — Authentication (OAuth 2.0 / OIDC)
# ────────────────────────────────────────────

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', oidc_configured=OIDC_CONFIGURED)


@app.route('/login')
def login():
    """Initiate the OAuth 2.0 authorization-code flow via Microsoft Entra ID."""
    if not OIDC_CONFIGURED:
        flash('Microsoft Entra ID is not configured. '
              'Set AZURE_CLIENT_ID and AZURE_CLIENT_SECRET.', 'danger')
        return redirect(url_for('index'))

    try:
        flow = _build_msal_app().initiate_auth_code_flow(
            scopes=SCOPE,
            redirect_uri=AZURE_REDIRECT_URI,
        )
        session['auth_flow'] = flow
        return redirect(flow['auth_uri'])
    except Exception as e:
        flash(f'Could not start sign-in flow: {e}', 'danger')
        return redirect(url_for('index'))


@app.route('/auth/callback')
def auth_callback():
    """Handle the redirect from Microsoft Entra ID after user authentication."""
    flow = session.pop('auth_flow', None)
    if flow is None:
        flash('Authentication session expired. Please try again.', 'danger')
        return redirect(url_for('index'))

    try:
        result = _build_msal_app().acquire_token_by_auth_code_flow(
            flow,
            request.args,
        )
    except ValueError as e:
        flash(f'Authentication error: {e}', 'danger')
        return redirect(url_for('index'))

    if 'error' in result:
        desc = result.get('error_description', result.get('error'))
        flash(f'Sign-in failed: {desc}', 'danger')
        return redirect(url_for('index'))

    # Extract user identity from the ID-token claims
    claims = result.get('id_token_claims', {})
    user_info = {
        'oid': claims.get('oid'),
        'name': claims.get('name', 'User'),
        'email': claims.get('preferred_username', claims.get('email', '')),
    }
    session['user'] = user_info

    # Auto-provision user in the database
    if DB_AVAILABLE:
        try:
            db_user = _get_or_create_db_user(user_info)
            session['db_user_id'] = db_user['id']
        except Exception as e:
            print(f"[WARNING] DB user provisioning failed: {e}")

    flash(f'Welcome, {user_info["name"]}!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    """Clear the local session and redirect to the Microsoft logout endpoint."""
    was_oidc = OIDC_CONFIGURED and 'user' in session
    session.clear()

    if was_oidc:
        # Single sign-out: redirect the user to Microsoft's logout page,
        # which then redirects back to our index page.
        post_logout = url_for('index', _external=True)
        return redirect(
            f"{AUTHORITY}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={post_logout}"
        )

    flash('You have been signed out.', 'info')
    return redirect(url_for('index'))


# ────────────────────────────────────────────
#  Routes — Banking features
# ────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('index'))

    user_info = session['user']

    if not DB_AVAILABLE:
        # Render dashboard with identity info only (no DB data)
        return render_template('dashboard.html', user={
            'username': user_info['name'],
            'email': user_info['email'],
            'balance': 0,
        }, transactions=[], db_available=False)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE oid=?", (user_info['oid'],))
    user = row_to_dict(cursor, cursor.fetchone())

    if not user:
        user = _get_or_create_db_user(user_info)

    cursor.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY timestamp DESC",
        (user['id'],)
    )
    transactions = rows_to_dicts(cursor, cursor.fetchall())

    conn.close()

    return render_template('dashboard.html', user=user,
                           transactions=transactions, db_available=True)


@app.route('/deposit', methods=['POST'])
def deposit():
    if 'user' not in session:
        return redirect(url_for('index'))

    if not DB_AVAILABLE:
        flash('Database not configured. Deposits are unavailable.', 'danger')
        return redirect(url_for('dashboard'))

    amount = float(request.form['amount'])
    user_oid = session['user']['oid']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE oid=?", (user_oid,))
    row = cursor.fetchone()
    if not row:
        flash('User record not found. Please sign out and sign in again.', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    user_id = row[0]
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                   (amount, user_id))
    cursor.execute(
        "INSERT INTO transactions (user_id, type, amount, description) "
        "VALUES (?, 'deposit', ?, ?)",
        (user_id, amount, 'Deposit')
    )
    conn.commit()
    conn.close()

    flash('Deposit successful!', 'success')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
