from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from functools import wraps
import hashlib

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# ฟังก์ชันเชื่อมต่อฐานข้อมูล
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# สร้างตารางในฐานข้อมูล
def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            fullname TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            transaction_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

# เข้ารหัสรหัสผ่าน
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ตรวจสอบการล็อกอิน
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('กรุณาเข้าสู่ระบบก่อนใช้งาน', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# หน้าแรก (ถ้ายังไม่ล็อกอิน จะไปหน้าล็อกอิน)
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

# หน้าล็อกอิน
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', 
                          (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['fullname'] = user['fullname']
            flash(f'ยินดีต้อนรับ {user["fullname"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    
    return render_template('login.html')

# หน้าสมัครสมาชิก
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        fullname = request.form['fullname']
        
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password, fullname) VALUES (?, ?, ?)',
                        (username, password, fullname))
            conn.commit()
            flash('สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('ชื่อผู้ใช้นี้มีอยู่ในระบบแล้ว', 'danger')
        finally:
            conn.close()
    
    return render_template('register.html')

# หน้าหลัก - สรุปการเงิน
@app.route('/index')
@login_required
def index():
    conn = get_db()
    
    # คำนวณรายรับ
    income = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total 
        FROM transactions 
        WHERE user_id = ? AND type = "income"
    ''', (session['user_id'],)).fetchone()['total']
    
    # คำนวณรายจ่าย
    expense = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total 
        FROM transactions 
        WHERE user_id = ? AND type = "expense"
    ''', (session['user_id'],)).fetchone()['total']
    
    # ยอดคงเหลือ
    balance = income - expense
    
    # รายการล่าสุด 5 รายการ
    recent = conn.execute('''
        SELECT * FROM transactions 
        WHERE user_id = ? 
        ORDER BY transaction_date DESC, created_at DESC 
        LIMIT 5
    ''', (session['user_id'],)).fetchall()
    
    # นับจำนวนรายการทั้งหมด
    total_count = conn.execute('''
        SELECT COUNT(*) as count FROM transactions WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()['count']
    
    conn.close()
    
    return render_template('index.html', 
                         income=income, 
                         expense=expense, 
                         balance=balance,
                         recent=recent,
                         total_count=total_count)

# หน้าเพิ่มรายการ
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        type_trans = request.form['type']
        amount = float(request.form['amount'])
        category = request.form['category']
        description = request.form['description']
        transaction_date = request.form['transaction_date']
        
        conn = get_db()
        conn.execute('''
            INSERT INTO transactions (user_id, type, amount, category, description, transaction_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], type_trans, amount, category, description, transaction_date))
        conn.commit()
        conn.close()
        
        flash('เพิ่มรายการสำเร็จ!', 'success')
        return redirect(url_for('list_transactions'))
    
    return render_template('add.html', today=datetime.now().strftime('%Y-%m-%d'))

# หน้ารายการทั้งหมด
@app.route('/list')
@login_required
def list_transactions():
    filter_type = request.args.get('type', 'all')
    
    conn = get_db()
    
    if filter_type == 'all':
        transactions = conn.execute('''
            SELECT * FROM transactions 
            WHERE user_id = ? 
            ORDER BY transaction_date DESC, created_at DESC
        ''', (session['user_id'],)).fetchall()
    else:
        transactions = conn.execute('''
            SELECT * FROM transactions 
            WHERE user_id = ? AND type = ?
            ORDER BY transaction_date DESC, created_at DESC
        ''', (session['user_id'], filter_type)).fetchall()
    
    conn.close()
    
    return render_template('list.html', transactions=transactions, filter_type=filter_type)

# แก้ไขรายการ
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    conn = get_db()
    
    if request.method == 'POST':
        type_trans = request.form['type']
        amount = float(request.form['amount'])
        category = request.form['category']
        description = request.form['description']
        transaction_date = request.form['transaction_date']
        
        conn.execute('''
            UPDATE transactions 
            SET type = ?, amount = ?, category = ?, description = ?, transaction_date = ?
            WHERE id = ? AND user_id = ?
        ''', (type_trans, amount, category, description, transaction_date, id, session['user_id']))
        conn.commit()
        conn.close()
        
        flash('แก้ไขรายการสำเร็จ!', 'success')
        return redirect(url_for('list_transactions'))
    
    transaction = conn.execute('SELECT * FROM transactions WHERE id = ? AND user_id = ?', 
                              (id, session['user_id'])).fetchone()
    conn.close()
    
    if not transaction:
        flash('ไม่พบรายการที่ต้องการแก้ไข', 'danger')
        return redirect(url_for('list_transactions'))
    
    return render_template('add.html', transaction=transaction, edit_mode=True)

# ลบรายการ
@app.route('/delete/<int:id>')
@login_required
def delete(id):
    conn = get_db()
    conn.execute('DELETE FROM transactions WHERE id = ? AND user_id = ?', 
                (id, session['user_id']))
    conn.commit()
    conn.close()
    
    flash('ลบรายการสำเร็จ!', 'success')
    return redirect(url_for('list_transactions'))

# ออกจากระบบ
@app.route('/logout')
def logout():
    session.clear()
    flash('ออกจากระบบเรียบร้อยแล้ว', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
