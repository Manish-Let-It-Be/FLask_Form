from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, abort
from functools import wraps
import json
import uuid
import os
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import io

app = Flask(__name__)
app.secret_key = 'manish9234'  

ENVIRONMENT = os.getenv('ENVIRONMENT', 'local')  

DATA_FILE = 'data/user_data.json'
USER_DATA_FILE = 'data/user_accounts.json'

# SQLite database path for Vercel
SQLITE_DB = '/tmp/app.db' if ENVIRONMENT == 'vercel' else 'app.db'

if ENVIRONMENT == 'local':
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(USER_DATA_FILE), exist_ok=True)

def init_db():
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS divisions
                 (name TEXT PRIMARY KEY)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT, division_name TEXT,
                 FOREIGN KEY (division_name) REFERENCES divisions(name))''')
    
    conn.commit()
    conn.close()

# Helper Functions
def load_data():
    if ENVIRONMENT == 'local':
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        return {'divisions': {}}
    else:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        
        # Loading from SQLite
        c.execute("SELECT name FROM divisions")
        divisions = {row[0]: [] for row in c.fetchall()}
        
        c.execute("SELECT id, name, email, phone, division_name FROM students")
        for row in c.fetchall():
            student = {
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'phone': row[3],
                'division': row[4]
            }
            divisions[row[4]].append(student)
        
        conn.close()
        return {'divisions': divisions}

def save_data(data):
    if ENVIRONMENT == 'local':
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    else:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        
        # Saving to SQLite
        for division_name, students in data['divisions'].items():
            c.execute("INSERT OR IGNORE INTO divisions (name) VALUES (?)", (division_name,))
            for student in students:
                c.execute('''INSERT OR REPLACE INTO students
                             (id, name, email, phone, division_name) VALUES (?, ?, ?, ?, ?)''',
                          (student['id'], student['name'], student['email'], student['phone'], division_name))
        
        conn.commit()
        conn.close()

def load_user_data():
    if ENVIRONMENT == 'local':
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r') as f:
                return json.load(f)
        return {}
    else:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        c.execute("SELECT username, password FROM users")
        users = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return users

def save_user_data(data):
    if ENVIRONMENT == 'local':
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    else:
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        for username, password in data.items():
            c.execute("INSERT OR REPLACE INTO users (username, password) VALUES (?, ?)",
                      (username, password))
        conn.commit()
        conn.close()

def generate_student_id():
    return f"stu{uuid.uuid4().hex[:5]}"

def login_required(f):
    @wraps(f)  
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('You need to log in first!', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

init_db()

@app.route('/')
@login_required
def home():
    data = load_data()
    divisions = data['divisions']
    return render_template('add_division.html', divisions=divisions)

@app.route('/search', methods=['GET'])
@login_required
def search_students():
    query = request.args.get('query', '').lower()
    data = load_data()
    all_students = []

    for division_name, students in data['divisions'].items():
        for student in students:
            student['division'] = division_name  
            all_students.append(student)

    # Filtering by name
    filtered_students = [s for s in all_students if query in s['name'].lower()]
    # Filtering by id
    filtered_students_id = [s for s in all_students if query in s['id']]

    if filtered_students_id:
        filtered_students = filtered_students_id

    return render_template('search_results.html', students=filtered_students)

@app.route('/add_division', methods=['POST'])
@login_required
def add_division():
    division_name = request.form['division_name']
    data = load_data()
    
    if division_name not in data['divisions']:
        data['divisions'][division_name] = []
        save_data(data)
        flash(f'Division "{division_name}" added successfully!', 'success')
    else:
        flash(f'Division "{division_name}" already exists!', 'error')

    return redirect(url_for('home'))

@app.route('/delete_division/<division_name>', methods=['POST'])
@login_required
def delete_division(division_name):
    data = load_data()
    if division_name in data['divisions']:
        del data['divisions'][division_name]
        save_data(data)
        flash(f'Division "{division_name}" deleted successfully!', 'success')
    else:
        flash(f'Division "{division_name}" does not exist!', 'error')

    return redirect(url_for('home'))

@app.route('/choose_division/<division_name>')
@login_required
def choose_division(division_name):
    data = load_data()
    students = data['divisions'].get(division_name, [])
    return render_template('display_students.html', students=students, division_name=division_name)

@app.route('/add_student/<division_name>', methods=['GET', 'POST'])
@login_required
def add_student(division_name):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        student_id = generate_student_id()

        new_student = {
            'id': student_id,
            'name': name,
            'email': email,
            'phone': phone
        }

        data = load_data()
        data['divisions'][division_name].append(new_student)
        save_data(data)

        flash('Student added successfully!', 'success')
        return redirect(url_for('choose_division', division_name=division_name))

    return render_template('add_student.html', division_name=division_name)

@app.route('/update/<student_id>', methods=['GET', 'POST'])
@login_required
def update_student(student_id):
    data = load_data()
    all_students = []

    for division_name, students in data['divisions'].items():
        for student in students:
            student['division'] = division_name  
            all_students.append(student)

    student_to_update = next((s for s in all_students if s['id'] == student_id), None)

    if request.method == 'POST':
        student_to_update['name'] = request.form['name']
        student_to_update['email'] = request.form['email']
        student_to_update['phone'] = request.form['phone']
        save_data(data)

        flash('Student updated successfully!', 'success')
        return redirect(url_for('search_students'))

    return render_template('update_student.html', student=student_to_update)

@app.route('/delete_student/<division_name>/<student_id>', methods=['POST'])
@login_required
def delete_student(division_name, student_id):
    data = load_data()
    data['divisions'][division_name] = [s for s in data['divisions'][division_name] if s['id'] != student_id]
    save_data(data)
    flash('Student deleted successfully!', 'success')
    return redirect(url_for('choose_division', division_name=division_name))

@app.route('/export/<division_name>')
@login_required
def export_to_excel(division_name):
    try:
        data = load_data()
        students = data['divisions'].get(division_name, [])
        
        for student in students:
            student['division'] = division_name
        
        df = pd.DataFrame(students)
        
        # BytesIO buffer to hold the Excel file
        excel_buffer = io.BytesIO()
        
        # Writing DataFrame to the buffer as an Excel file
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        # Seek to the beginning of the buffer
        excel_buffer.seek(0)
        
        # Return the file as a response
        return send_file(
            excel_buffer,
            as_attachment=True,
            download_name=f'{division_name}_students.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"Error exporting division {division_name}: {e}")
        abort(500, description="An error occurred while exporting the file.")

@app.route('/export/all_students')
@login_required
def export_all_students():
    try:
        data = load_data()
        all_students = []
        
        for division_name, students in data['divisions'].items():
            for student in students:
                student['division'] = division_name  
                all_students.append(student)

        df = pd.DataFrame(all_students)
        
        excel_buffer = io.BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        excel_buffer.seek(0)
        
        return send_file(
            excel_buffer,
            as_attachment=True,
            download_name='All_Students.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"Error exporting all students: {e}")
        abort(500, description="An error occurred while exporting the file.")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_data = load_user_data()
        
        if username in user_data:
            flash('Username already exists!', 'error')
        else:
            user_data[username] = generate_password_hash(password)
            save_user_data(user_data)
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_data = load_user_data()
        
        if username in user_data and check_password_hash(user_data[username], password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
else:
    application = app