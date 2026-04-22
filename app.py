from flask import Flask, render_template, request, redirect, session, flash, url_for
import hashlib
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

# --- MySQL Configuration (optional - app still starts without a DB) ---
DB_AVAILABLE = False
mysql = None

MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DB = os.environ.get('MYSQL_DB', 'bankdb')

if MYSQL_HOST and MYSQL_USER and MYSQL_PASSWORD:
    try:
        from flask_mysqldb import MySQL
        import MySQLdb.cursors
        app.config['MYSQL_HOST'] = MYSQL_HOST
        app.config['MYSQL_USER'] = MYSQL_USER
        app.config['MYSQL_PASSWORD'] = MYSQL_PASSWORD
        app.config['MYSQL_DB'] = MYSQL_DB
        mysql = MySQL(app)
        DB_AVAILABLE = True
    except Exception as e:
        print(f"[WARNING] MySQL not available: {e}. Running in frontend-only mode.")
else:
    print("[WARNING] MySQL env vars not set. Running in frontend-only mode.")


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

        import MySQLdb.cursors
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        account = cursor.fetchone()
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

        cursor = mysql.connection.cursor()
        cursor.execute("INSERT INTO users (username, password, email, balance) VALUES (%s, %s, %s, %s)",
                       (username, password, email, 0))
        mysql.connection.commit()
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

    import MySQLdb.cursors
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM users WHERE id=%s", (session['id'],))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY timestamp DESC", (session['id'],))
    transactions = cursor.fetchall()

    return render_template('dashboard.html', user=user, transactions=transactions)


@app.route('/deposit', methods=['POST'])
def deposit():
    if 'loggedin' not in session:
        return redirect(url_for('index'))

    if not DB_AVAILABLE:
        flash('Database not configured.', 'danger')
        return redirect(url_for('index'))

    amount = float(request.form['amount'])
    cursor = mysql.connection.cursor()
    cursor.execute("UPDATE users SET balance = balance + %s WHERE id=%s", (amount, session['id']))
    cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, 'deposit', %s, %s)",
                   (session['id'], amount, 'Deposit'))
    mysql.connection.commit()
    flash('Deposit successful!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
