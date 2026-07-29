import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
import psycopg2
import psycopg2.extras
from psycopg2 import IntegrityError
import io

app = Flask(__name__)
app.secret_key = 'fifa_club_archiving_secret_key'

# --- إعدادات الاتصال بـ Neon PostgreSQL ---
NEON_DATABASE_URL = os.environ.get(
    'DATABASE_URL', 
    'postgresql://neondb_owner:npg_6k3RhMmjqwZv@ep-tiny-unit-aubq8ke5-pooler.c-10.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
)

ADMIN_ROLES = [
    'الرئيس التنفيذي', 'رئيس تنفيذي', 'CEO',
    'مدير تقنية المعلومات', 'مدير تقنية معلومات', 'تقنية المعلومات', 'IT Manager', 'IT'
]

def is_admin_user(dept_name):
    if not dept_name:
        return False
    dept_clean = dept_name.strip()
    return any(role.lower() == dept_clean.lower() for role in ADMIN_ROLES) or 'تقنية' in dept_clean or 'تنفيذي' in dept_clean

def get_db_connection():
    conn = psycopg2.connect(NEON_DATABASE_URL, sslmode='require')
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            can_access_archive INTEGER DEFAULT 1,
            can_delete INTEGER DEFAULT 0,
            can_view_all_archive INTEGER DEFAULT 1,
            can_view_all_achievements INTEGER DEFAULT 0,
            can_add_user INTEGER DEFAULT 1,
            can_page_inbox INTEGER DEFAULT 1,
            can_page_outbox INTEGER DEFAULT 1,
            can_page_achievements INTEGER DEFAULT 1,
            can_page_archive INTEGER DEFAULT 1,
            can_page_quick_upload INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS letters (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            priority TEXT DEFAULT 'عادي',
            sender_id INTEGER,
            receiver_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            file_data BYTEA,
            file_mimetype TEXT,
            created_at TEXT,
            archive_dept_id INTEGER,
            letter_number TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_achievements (
            id SERIAL PRIMARY KEY,
            dept_id INTEGER,
            title TEXT,
            file_name TEXT,
            file_path TEXT,
            file_data BYTEA,
            file_mimetype TEXT,
            month_year TEXT,
            uploaded_at TEXT
        )
    ''')
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='departments'")
    dept_columns = [col['column_name'] for col in cursor.fetchall()]
    for col_name, default_val in [
        ('can_view_all_archive', 1), ('can_view_all_achievements', 0), ('can_add_user', 1),
        ('can_page_inbox', 1), ('can_page_outbox', 1), ('can_page_achievements', 1),
        ('can_page_archive', 1), ('can_page_quick_upload', 1)
    ]:
        if col_name not in dept_columns:
            cursor.execute(f'ALTER TABLE departments ADD COLUMN {col_name} INTEGER DEFAULT {default_val}')

    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='letters'")
    letter_cols = [col['column_name'] for col in cursor.fetchall()]
    for col_name in ['file_path', 'archive_dept_id', 'file_data', 'file_mimetype', 'letter_number']:
        if col_name not in letter_cols:
            col_type = 'BYTEA' if col_name == 'file_data' else ('INTEGER' if col_name == 'archive_dept_id' else 'TEXT')
            cursor.execute(f'ALTER TABLE letters ADD COLUMN {col_name} {col_type}')

    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='monthly_achievements'")
    ach_cols = [col['column_name'] for col in cursor.fetchall()]
    for col_name in ['title', 'file_name', 'file_path', 'month_year', 'uploaded_at', 'file_data', 'file_mimetype']:
        if col_name not in ach_cols:
            col_type = 'BYTEA' if col_name == 'file_data' else 'TEXT'
            cursor.execute(f'ALTER TABLE monthly_achievements ADD COLUMN {col_name} {col_type}')
    
    conn.commit()
    cursor.close()
    conn.close()

init_db()

# --- القالب الموحد للنظام ---
BASE_LAYOUT = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ page_title }} - نظام أرشفة نادي فيفا</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
    <style>
        :root { --fifa-green: #123826; --fifa-green-hover: #1e563b; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
        body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; }
        .top-navbar { background-color: #ffffff; border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1.5rem; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .main-wrapper { display: flex; min-height: calc(100vh - 70px); }
        .sidebar { width: 260px; background-color: var(--fifa-green); color: #ffffff; padding-top: 1rem; flex-shrink: 0; }
        .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
        .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
        .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
        .content-body { flex: 1; padding: 1.5rem; width: 100%; overflow-x: hidden; }
        .modern-card { background: #ffffff; border-radius: 12px; border: 1px solid #d5e2d8; box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); padding: 1.5rem; }
        .btn-fifa-primary { background-color: var(--fifa-green); color: #ffffff; border-radius: 8px; padding: 0.5rem 1.25rem; font-weight: 700; border: none; }
        .btn-fifa-primary:hover { background-color: var(--fifa-green-hover); color: #fff; }
        .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; border-radius: 8px; padding: 0.5rem 1.25rem; font-weight: 700; border: none; }
        .btn-fifa-gold:hover { background-color: #b08d48; color: #fff; }
    </style>
</head>
<body>
    <div class="top-navbar d-flex justify-content-between align-items-center">
        <div class="d-flex align-items-center">
            <h5 class="m-0 fw-bold" style="color: var(--fifa-green);">نادي فيفا الرياضي - نظام الأرشفة</h5>
        </div>
        <div>
            <span class="me-3 fw-bold text-muted"><i class='bx bxs-user-circle align-middle ms-1'></i> {{ session.get('dept_name', '') }}</span>
            <a href="/logout" class="btn btn-outline-danger btn-sm"><i class='bx bx-log-out align-middle'></i> خروج</a>
        </div>
    </div>
    <div class="main-wrapper">
        <div class="sidebar">
            <a href="/dashboard" class="sidebar-link {% if active_page == 'inbox' %}active{% endif %}"><i class='bx bxs-inbox'></i> البريد الوارد</a>
            <a href="/outbox" class="sidebar-link {% if active_page == 'outbox' %}active{% endif %}"><i class='bx bxs-paper-plane'></i> البريد الصادر</a>
            <a href="/quick_upload" class="sidebar-link {% if active_page == 'quick_upload' %}active{% endif %}"><i class='bx bxs-cloud-upload'></i> رفع سريع للخطابات</a>
            <a href="/monthly_achievements" class="sidebar-link {% if active_page == 'achievements' %}active{% endif %}"><i class='bx bxs-trophy'></i> الإنجازات الشهرية</a>
            <a href="/archive" class="sidebar-link {% if active_page == 'archive' %}active{% endif %}"><i class='bx bxs-archive-in'></i> الأرشيف العام</a>
            {% if is_admin or current_dept.can_add_user == 1 %}
            <a href="/register" class="sidebar-link {% if active_page == 'register' %}active{% endif %}"><i class='bx bxs-user-plus'></i> إضافة إدارة</a>
            <a href="/admin/permissions" class="sidebar-link {% if active_page == 'permissions' %}active{% endif %}"><i class='bx bxs-cog'></i> التحكم بالصلاحيات</a>
            {% endif %}
        </div>
        <div class="content-body">
            {% block content %}{% endblock %}
        </div>
    </div>
</body>
</html>
'''

@app.route('/download_letter_file/<int:letter_id>')
def download_letter_file(letter_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT file_name, file_data, file_mimetype FROM letters WHERE id = %s', (letter_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if row and row['file_data']:
        return send_file(
            io.BytesIO(row['file_data']),
            mimetype=row['file_mimetype'] or 'application/octet-stream',
            as_attachment=True,
            download_name=row['file_name'] or 'file'
        )
    return "الملف غير موجود", 404

@app.route('/download_ach_file/<int:ach_id>')
def download_ach_file(ach_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT file_name, file_data, file_mimetype FROM monthly_achievements WHERE id = %s', (ach_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if row and row['file_data']:
        return send_file(
            io.BytesIO(row['file_data']),
            mimetype=row['file_mimetype'] or 'application/octet-stream',
            as_attachment=True,
            download_name=row['file_name'] or 'file'
        )
    return "الملف غير موجود", 404

@app.route('/delete_letter/<int:letter_id>')
def delete_letter(letter_id):
    if 'dept_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_delete'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الحذف."); window.history.back();</script>'''
    
    cursor.execute('DELETE FROM letters WHERE id = %s', (letter_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return '''<script>alert("تم الحذف بنجاح"); window.history.back();</script>'''

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM departments WHERE username = %s AND password = %s', (username, password))
        dept = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if dept:
            session['dept_id'] = dept['id']
            session['dept_name'] = dept['name']
            return redirect(url_for('dashboard'))
        else:
            return '''<script>alert("خطأ في اسم المستخدم أو كلمة المرور"); window.location.href="/";</script>'''
            
    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>تسجيل الدخول - نظام أرشفة نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <style>
            body { background: #eaf3ec; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .login-card { background: #fff; padding: 2rem; border-radius: 12px; width: 100%; max-width: 400px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
            .btn-fifa { background: #123826; color: white; width: 100%; }
        </style>
    </head>
    <body>
        <div class="login-card text-center">
            <h4 class="fw-bold mb-3" style="color: #123826;">نادي فيفا الرياضي</h4>
            <form action="/" method="post">
                <div class="mb-3 text-start">
                    <label class="form-label">اسم المستخدم</label>
                    <input type="text" name="username" class="form-control" required>
                </div>
                <div class="mb-3 text-start">
                    <label class="form-label">كلمة المرور</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-fifa">تسجيل الدخول</button>
            </form>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_code)

@app.route('/dashboard')
def dashboard():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    cursor.execute('''
        SELECT l.*, d.name as sender_name 
        FROM letters l 
        LEFT JOIN departments d ON l.sender_id = d.id 
        WHERE l.receiver_id = %s OR %s = TRUE
        ORDER BY l.id DESC
    ''', (session['dept_id'], is_admin))
    letters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    content = '''
    {% extends "base" %}
    {% block content %}
    <div class="modern-card">
        <h4 class="fw-bold mb-3"><i class='bx bxs-inbox text-success'></i> البريد الوارد</h4>
        <table class="table table-hover align-middle">
            <thead>
                <tr>
                    <th>رقم الخطاب</th>
                    <th>العنوان</th>
                    <th>المرسل</th>
                    <th>التاريخ</th>
                    <th>الملف</th>
                    <th>إجراءات</th>
                </tr>
            </thead>
            <tbody>
                {% for l in letters %}
                <tr>
                    <td>{{ l.letter_number or l.id }}</td>
                    <td>{{ l.title }}</td>
                    <td>{{ l.sender_name or 'إدارة المكاتب' }}</td>
                    <td>{{ l.created_at }}</td>
                    <td>
                        {% if l.file_data %}
                        <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-primary"><i class='bx bx-download'></i> تحميل</a>
                        {% else %} - {% endif %}
                    </td>
                    <td>
                        {% if current_dept.can_delete == 1 or is_admin %}
                        <a href="/delete_letter/{{ l.id }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('هل أنت تأكد؟')"><i class='bx bx-trash'></i></a>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endblock %}
    '''
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', content), 
                                 page_title="البريد الوارد", active_page="inbox", letters=letters, current_dept=current_dept, is_admin=is_admin)

@app.route('/outbox')
def outbox():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    cursor.execute('''
        SELECT l.*, d.name as receiver_name 
        FROM letters l 
        LEFT JOIN departments d ON l.receiver_id = d.id 
        WHERE l.sender_id = %s OR %s = TRUE
        ORDER BY l.id DESC
    ''', (session['dept_id'], is_admin))
    letters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    content = '''
    {% extends "base" %}
    {% block content %}
    <div class="modern-card">
        <h4 class="fw-bold mb-3"><i class='bx bxs-paper-plane text-primary'></i> البريد الصادر</h4>
        <table class="table table-hover align-middle">
            <thead>
                <tr>
                    <th>رقم الخطاب</th>
                    <th>العنوان</th>
                    <th>المرسل إليه</th>
                    <th>التاريخ</th>
                    <th>الملف</th>
                </tr>
            </thead>
            <tbody>
                {% for l in letters %}
                <tr>
                    <td>{{ l.letter_number or l.id }}</td>
                    <td>{{ l.title }}</td>
                    <td>{{ l.receiver_name or 'عام' }}</td>
                    <td>{{ l.created_at }}</td>
                    <td>
                        {% if l.file_data %}
                        <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-primary"><i class='bx bx-download'></i> تحميل</a>
                        {% else %} - {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endblock %}
    '''
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', content), 
                                 page_title="البريد الصادر", active_page="outbox", letters=letters, current_dept=current_dept, is_admin=is_admin)

@app.route('/quick_upload', methods=['GET', 'POST'])
def quick_upload():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        receiver_id = request.form.get('receiver_id')
        file = request.files.get('file')
        
        if file and file.filename != '':
            file_name = secure_filename(file.filename)
            file_bytes = file.read()
            file_mimetype = file.content_type or 'application/octet-stream'
            
            cursor.execute('''
                INSERT INTO letters (title, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (title, session['dept_id'], receiver_id, file_name, psycopg2.Binary(file_bytes), file_mimetype, datetime.now().strftime('%Y-%m-%d %H:%M')))
            conn.commit()
            cursor.close()
            conn.close()
            return '''<script>alert("تم رفع و إرسال الخطاب بنجاح!"); window.location.href="/outbox";</script>'''

    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    cursor.close()
    conn.close()
    
    content = '''
    <div class="modern-card">
        <h4 class="fw-bold mb-3"><i class='bx bxs-cloud-upload text-warning'></i> رفع سريع للخطابات</h4>
        <form action="/quick_upload" method="post" enctype="multipart/form-data">
            <div class="mb-3">
                <label class="form-label fw-bold">عنوان الخطاب</label>
                <input type="text" name="title" class="form-control" required>
            </div>
            <div class="mb-3">
                <label class="form-label fw-bold">الجهة الموجه إليها</label>
                <select name="receiver_id" class="form-select" required>
                    {% for d in departments %}
                    <option value="{{ d.id }}">{{ d.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label fw-bold">ارفاق ملف الخطاب</label>
                <input type="file" name="file" class="form-control" required>
            </div>
            <button type="submit" class="btn btn-fifa-primary"><i class='bx bx-upload'></i> رفع وإرسال</button>
        </form>
    </div>
    '''
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', content), 
                                 page_title="رفع سريع", active_page="quick_upload", departments=departments, current_dept=current_dept, is_admin=is_admin)

@app.route('/monthly_achievements', methods=['GET'])
def monthly_achievements():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_view_all_achievements'] == 1 or is_admin:
        cursor.execute('SELECT m.*, d.name as dept_name FROM monthly_achievements m LEFT JOIN departments d ON m.dept_id = d.id ORDER BY m.id DESC')
    else:
        cursor.execute('SELECT m.*, d.name as dept_name FROM monthly_achievements m LEFT JOIN departments d ON m.dept_id = d.id WHERE m.dept_id = %s ORDER BY m.id DESC', (session['dept_id'],))
    achievements = cursor.fetchall()
    
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.close()
    conn.close()

    content = '''
    <div class="modern-card">
        <h4 class="fw-bold mb-3"><i class='bx bxs-trophy text-warning'></i> سجل الإنجازات الشهرية</h4>
        <form action="/upload_achievement" method="post" enctype="multipart/form-data" class="mb-4 row g-3">
            <input type="hidden" name="dept_id" value="{{ session['dept_id'] }}">
            <div class="col-md-5">
                <input type="text" name="title" class="form-control" placeholder="عنوان الإنجاز" required>
            </div>
            <div class="col-md-5">
                <input type="file" name="file" class="form-control" required>
            </div>
            <div class="col-md-2">
                <button type="submit" class="btn btn-fifa-gold w-100">رفع الإنجاز</button>
            </div>
        </form>
        
        <table class="table table-hover align-middle">
            <thead>
                <tr>
                    <th>عنوان الإنجاز</th>
                    <th>الإدارة</th>
                    <th>تاريخ الرفع</th>
                    <th>الملف</th>
                </tr>
            </thead>
            <tbody>
                {% for a in achievements %}
                <tr>
                    <td>{{ a.title }}</td>
                    <td>{{ a.dept_name }}</td>
                    <td>{{ a.uploaded_at }}</td>
                    <td><a href="/download_ach_file/{{ a.id }}" class="btn btn-sm btn-outline-primary"><i class='bx bx-download'></i> تحميل</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    '''
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', content), 
                                 page_title="الإنجازات الشهرية", active_page="achievements", achievements=achievements, departments=departments, current_dept=current_dept, is_admin=is_admin)

@app.route('/archive')
def archive():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    cursor.execute('SELECT * FROM letters ORDER BY id DESC')
    letters = cursor.fetchall()
    cursor.close()
    conn.close()
    
    content = '''
    <div class="modern-card">
        <h4 class="fw-bold mb-3"><i class='bx bxs-archive-in text-secondary'></i> الأرشيف العام</h4>
        <table class="table table-hover align-middle">
            <thead>
                <tr>
                    <th>رقم المعاملة</th>
                    <th>العنوان</th>
                    <th>التاريخ</th>
                    <th>الملف</th>
                </tr>
            </thead>
            <tbody>
                {% for l in letters %}
                <tr>
                    <td>{{ l.letter_number or l.id }}</td>
                    <td>{{ l.title }}</td>
                    <td>{{ l.created_at }}</td>
                    <td>
                        {% if l.file_data %}
                        <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-primary"><i class='bx bx-download'></i> تحميل</a>
                        {% else %} - {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    '''
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', content), 
                                 page_title="الأرشيف العام", active_page="archive", letters=letters, current_dept=current_dept, is_admin=is_admin)

@app.route('/admin/permissions', methods=['GET', 'POST'])
def permissions():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if not is_admin and current_dept.get('can_add_user') != 1:
        cursor.close()
        conn.close()
        return '''<script>alert("لا تملك الصلاحيات الكافية لدخول هذه الصفحة"); window.location.href="/dashboard";</script>'''

    if request.method == 'POST':
        for dept_id in request.form.getlist('dept_ids'):
            can_delete = 1 if request.form.get(f'can_delete_{dept_id}') else 0
            can_add_user = 1 if request.form.get(f'can_add_user_{dept_id}') else 0
            can_view_all_archive = 1 if request.form.get(f'can_view_all_archive_{dept_id}') else 0
            
            cursor.execute('''
                UPDATE departments 
                SET can_delete = %s, can_add_user = %s, can_view_all_archive = %s 
                WHERE id = %s
            ''', (can_delete, can_add_user, can_view_all_archive, dept_id))
        conn.commit()

    cursor.execute('SELECT * FROM departments ORDER BY id ASC')
    departments = cursor.fetchall()
    cursor.close()
    conn.close()

    content = '''
    <div class="modern-card">
        <h4 class="fw-bold mb-3"><i class='bx bxs-cog text-danger'></i> التحكم بالصلاحيات والإدارات</h4>
        <form action="/admin/permissions" method="post">
            <table class="table table-bordered align-middle">
                <thead>
                    <tr class="table-light">
                        <th>الإدارة</th>
                        <th>اسم المستخدم</th>
                        <th>صلاحية الحذف</th>
                        <th>إضافة مستخدمين</th>
                        <th>مشاهدة الأرشيف الكامل</th>
                    </tr>
                </thead>
                <tbody>
                    {% for d in departments %}
                    <tr>
                        <input type="hidden" name="dept_ids" value="{{ d.id }}">
                        <td>{{ d.name }}</td>
                        <td>{{ d.username }}</td>
                        <td><input type="checkbox" name="can_delete_{{ d.id }}" {% if d.can_delete %}checked{% endif %}></td>
                        <td><input type="checkbox" name="can_add_user_{{ d.id }}" {% if d.can_add_user %}checked{% endif %}></td>
                        <td><input type="checkbox" name="can_view_all_archive_{{ d.id }}" {% if d.can_view_all_archive %}checked{% endif %}></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <button type="submit" class="btn btn-fifa-primary"><i class='bx bx-save'></i> حفظ الصلاحيات</button>
        </form>
    </div>
    '''
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', content), 
                                 page_title="إدارة الصلاحيات", active_page="permissions", departments=departments, current_dept=current_dept, is_admin=is_admin)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
