from flask import Flask, render_template, request, redirect, session, flash, url_for
import hashlib
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

# --- Azure MySQL Flexible Server Configuration ---
DB_AVAILABLE = False
db_config = None

MYSQL_HOST = os.environ.get('MYSQL_HOST')       # e.g. yourserver.mysql.database.azure.com
MYSQL_USER = os.environ.get('MYSQL_USER')        # e.g. sqladmin
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DB = os.environ.get('MYSQL_DB', 'bankdb')

if MYSQL_HOST and MYSQL_USER and MYSQL_PASSWORD:
    try:
        import pymysql
        db_config = {
            'host': MYSQL_HOST,
            'user': MYSQL_USER,
            'password': MYSQL_PASSWORD,
            'database': MYSQL_DB,
            'ssl': {'ca': '/opt/ssl/DigiCertGlobalRootCA.crt.pem'},
            'cursorclass': pymysql.cursors.DictCursor,
        }
        # Test connection on startup
        test_conn = pymysql.connect(**db_config)
        test_conn.close()
        DB_AVAILABLE = True
        print("[INFO] Azure MySQL Flexible Server connected successfully.")
    except Exception as e:
        # SSL cert may not exist locally — try without SSL
        try:
            db_config_no_ssl = {
                'host': MYSQL_HOST,
                'user': MYSQL_USER,
                'password': MYSQL_PASSWORD,
                'database': MYSQL_DB,
                'cursorclass': pymysql.cursors.DictCursor,
            }
            test_conn = pymysql.connect(**db_config_no_ssl)
            test_conn.close()
            db_config = db_config_no_ssl
            DB_AVAILABLE = True
            print("[INFO] Azure MySQL connected (without SSL).")
        except Exception as e2:
            print(f"[WARNING] MySQL not available: {e2}. Running in frontend-only mode.")
else:
    print("[WARNING] MySQL env vars not set. Running in frontend-only mode.")


def get_db_connection():
    """Get a fresh database connection."""
    import pymysql
    return pymysql.connect(**db_config)


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
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        account = cursor.fetchone()
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
        cursor.execute("INSERT INTO users (username, password, email, balance) VALUES (%s, %s, %s, %s)",
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

    cursor.execute("SELECT * FROM users WHERE id=%s", (session['id'],))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY timestamp DESC", (session['id'],))
    transactions = cursor.fetchall()

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
    cursor.execute("UPDATE users SET balance = balance + %s WHERE id=%s", (amount, session['id']))
    cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, 'deposit', %s, %s)",
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
