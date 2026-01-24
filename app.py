from flask import Flask, render_template, request, redirect, session, flash, url_for
from flask_mysqldb import MySQL
import MySQLdb.cursors
import hashlib

app = Flask(__name__)
app.secret_key = 'secret123'

# --- MySQL Configuration ---
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'bankdb'

mysql = MySQL(app)


@app.route('/')
def index():
    if 'loggedin' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

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
