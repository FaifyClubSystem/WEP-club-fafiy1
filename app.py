import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, send_file, send_from_directory
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
    
    conn.commit()
    cursor.close()
    conn.close()

init_db()

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

@app.route('/view_letter_file/<int:letter_id>')
def view_letter_file(letter_id):
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
            as_attachment=False,
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

@app.route('/upload_achievement', methods=['POST'])
def upload_achievement():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = request.form.get('dept_id')
    title = request.form.get('title')
    file = request.files.get('file')
    
    is_admin = is_admin_user(session.get('dept_name'))
    if str(session['dept_id']) != str(dept_id) and not is_admin:
        return '''<script>alert("غير مسموح لك برفع إنجازات لهذه الإدارة."); window.location.href="/monthly_achievements";</script>'''
    
    if file and file.filename != '':
        original_name = secure_filename(file.filename)
        file_name = f"ach_{int(datetime.now().timestamp())}_{original_name}"
        file_bytes = file.read()
        file_mimetype = file.content_type or 'application/octet-stream'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO monthly_achievements (dept_id, title, file_name, file_data, file_mimetype, uploaded_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (dept_id, title, file_name, psycopg2.Binary(file_bytes), file_mimetype, datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        cursor.close()
        conn.close()
        
    return redirect(url_for('monthly_achievements'))

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM departments WHERE username = %s AND password = %s', 
                       (username, password))
        dept = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if dept:
            session['dept_id'] = dept['id']
            session['dept_name'] = dept['name']
            
            is_admin = is_admin_user(dept['name'])
            
            if dept.get('can_page_inbox') == 1 or is_admin:
                return redirect(url_for('dashboard'))
            elif dept.get('can_page_outbox') == 1 or is_admin:
                return redirect(url_for('outbox'))
            elif dept.get('can_page_achievements') == 1 or is_admin:
                return redirect(url_for('monthly_achievements'))
            elif dept.get('can_page_archive') == 1 or is_admin:
                return redirect(url_for('archive'))
            elif dept.get('can_page_quick_upload') == 1 or is_admin:
                return redirect(url_for('quick_upload'))
            else:
                session.clear()
                return '''<script>alert("عذراً، لا تملك صلاحية الوصول لأي صفحة في النظام."); window.location.href="/";</script>'''
        else:
            return '''<script>alert("خطأ في اسم المستخدم أو كلمة المرور"); window.location.href="/";</script>'''
            
    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>تسجيل الدخول - نظام أرشفة نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green: #123826; --fifa-green-hover: #1e563b; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background: linear-gradient(135deg, #eaf3ec 0%, #d5e2d8 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 15px; }
            .login-card { background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px); border-radius: 20px; border: 1px solid rgba(197, 160, 89, 0.2); box-shadow: 0 15px 35px rgba(18, 56, 38, 0.12); width: 100%; max-width: 440px; padding: 2rem 1.5rem; position: relative; overflow: hidden; }
            .login-card::before { content: ''; position: absolute; top: 0; right: 0; left: 0; height: 6px; background: linear-gradient(90deg, var(--fifa-green), var(--fifa-gold)); }
            .brand-logo-box { margin: 0 auto 1rem auto; text-align: center; }
            .brand-logo-box img { max-height: 85px; width: auto; object-fit: contain; }
            .custom-input-wrapper { position: relative; }
            .input-group-icon { position: absolute; top: 50%; right: 15px; transform: translateY(-50%); z-index: 10; color: var(--fifa-gold); font-size: 1.2rem; }
            .btn-fifa { background-color: var(--fifa-green); color: #ffffff; border-radius: 10px; padding: 0.8rem; font-weight: 700; border: none; width: 100%; transition: all 0.3s ease; }
            .btn-fifa:hover { background-color: var(--fifa-green-hover); color: #ffffff; }
            .login-footer { margin-top: 1.5rem; border-top: 1px solid #edf2f0; padding-top: 0.8rem; font-size: 0.8rem; color: #7c8a84; }
        </style>
    </head>
    <body>
        <div class="login-card text-center">
            <div class="brand-logo-box">
                <img src="{{ url_for('static', filename='logo.png') }}" alt="شعار نادي فيفا" onerror="this.style.display='none'; document.getElementById('alt-icon').style.display='inline-block';">
                <i id="alt-icon" class='bx bxs-shield-alt-2' style="display:none; font-size: 3.5rem; color: var(--fifa-green);"></i>
            </div>
            <h4 class="fw-bold mb-1" style="color: var(--fifa-green);">نادي فيفا الرياضي</h4>
            <p class="text-muted fs-7 mb-4">نظام الأرشفة والخطابات الإلكتروني</p>
            
            <form action="/" method="post">
                <div class="mb-3 text-start">
                    <label class="form-label fw-bold fs-7 mb-1" style="color: var(--fifa-green);">اسم المستخدم</label>
                    <div class="custom-input-wrapper">
                        <i class='bx bxs-user input-group-icon'></i>
                        <input type="text" name="username" class="form-control" style="padding-right: 42px;" placeholder="أدخل اسم المستخدم" required>
                    </div>
                </div>
                
                <div class="mb-4 text-start">
                    <label class="form-label fw-bold fs-7 mb-1" style="color: var(--fifa-green);">كلمة المرور</label>
                    <div class="custom-input-wrapper">
                        <i class='bx bxs-lock-alt input-group-icon'></i>
                        <input type="password" name="password" class="form-control" style="padding-right: 42px;" placeholder="أدخل كلمة المرور" required>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-fifa mb-2">
                    <i class='bx bx-log-in-circle ms-1 fs-5 align-middle'></i> تسجيل الدخول
                </button>
            </form>
            
            <div class="login-footer">
                جميع الحقوق محفوظة &copy; نادي فيفا الرياضي 2026
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_code)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ page_title }} - نظام أرشفة نادي فيفا</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <style>
        :root {
            --fifa-green-primary: #123826;
            --fifa-green-light: #1e563b;
            --fifa-gold: #c5a059;
            --fifa-bg: #eaf3ec;
            --fifa-card-border: #d5e2d8;
        }
        body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; overflow-x: hidden; }
        .top-navbar { background-color: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1rem; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
        .nav-logo { height: 42px; width: auto; object-fit: contain; }
        .main-wrapper { display: flex; min-height: calc(100vh - 76px); position: relative; }
        
        .sidebar { width: 260px; background-color: var(--fifa-green-primary); color: #ecf0f1; padding-top: 1rem; flex-shrink: 0; transition: all 0.3s ease; z-index: 1040; }
        
        @media (max-width: 991.98px) {
            .sidebar { position: fixed; top: 0; right: -260px; height: 100vh; box-shadow: -5px 0 15px rgba(0,0,0,0.2); }
            .sidebar.show-sidebar { right: 0; }
        }

        .mobile-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0,0,0,0.5); z-index: 1030; }
        .mobile-overlay.active { display: block; }

        .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
        .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
        .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
        .content-body { flex: 1; padding: 1.25rem; width: 100%; overflow-x: hidden; }
        .modern-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 12px; border: 1px solid var(--fifa-card-border); box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); }
        .section-header { font-weight: 800; color: var(--fifa-green-primary); margin-bottom: 1.5rem; position: relative; padding-bottom: 10px; font-size: 1.3rem; }
        .section-header::after { content: ''; position: absolute; bottom: 0; right: 0; width: 55px; height: 3px; background-color: var(--fifa-gold); border-radius: 2px; }
        .letter-item { border-bottom: 1px solid #f0f4f2; padding: 1rem; }
        .letter-item:hover { background-color: rgba(244, 248, 246, 0.8); }
        .priority-badge { font-size: 0.75rem; padding: 4px 10px; border-radius: 20px; font-weight: 700; }
        .bg-fifa-green { background-color: var(--fifa-green-primary) !important; color: #fff; }
        .btn-fifa-primary { background-color: var(--fifa-green-primary); color: #ffffff; border-radius: 8px; padding: 0.6rem 1.2rem; font-weight: 700; border: none; }
        .btn-fifa-primary:hover { background-color: var(--fifa-green-light); color: #fff; }

        /* ================= ورقة خطاب Word رسمية تفاعلية للنادي ================= */
        .word-paper-container {
            display: flex;
            justify-content: center;
            margin-bottom: 2rem;
        }
        .word-paper {
            background: #ffffff;
            width: 100%;
            max-width: 800px;
            min-height: 1050px;
            padding: 3rem 3.5rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border: 1px solid #c8d6cd;
            position: relative;
            font-family: 'Amiri', 'Traditional Arabic', serif;
            color: #000;
            line-height: 1.8;
            box-sizing: border-box;
        }
        .word-paper-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 2rem;
            line-height: 1.4;
        }
        .word-paper-right {
            text-align: right;
            font-size: 1.1rem;
            font-weight: bold;
            color: #000;
        }
        .word-paper-center {
            text-align: center;
            flex: 1;
        }
        .word-paper-center img {
            max-height: 80px;
            margin-bottom: 5px;
        }
        .word-paper-left {
            text-align: right;
            font-size: 1.05rem;
            font-weight: bold;
            color: #000;
            min-width: 170px;
        }
        .word-paper-title {
            text-align: center;
            font-size: 1.35rem;
            font-weight: bold;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
        }
        .word-paper-greeting {
            text-align: center;
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 1.5rem;
        }
        .word-paper-body {
            font-size: 1.15rem;
            text-align: justify;
            text-justify: inter-word;
            margin-bottom: 2rem;
            white-space: pre-line;
            min-height: 250px;
        }
        .word-paper-footer-closing {
            text-align: center;
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 3rem;
        }
        .word-paper-signature {
            text-align: left;
            margin-left: 2rem;
            font-size: 1.15rem;
            font-weight: bold;
        }
        .word-paper-contacts {
            position: absolute;
            bottom: 2.5rem;
            right: 3.5rem;
            font-size: 0.95rem;
            color: #333;
            direction: ltr;
            text-align: right;
            font-family: sans-serif;
        }
        .word-paper-contacts div {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 6px;
        }
        .paper-editable-input {
            border: none;
            border-bottom: 1px dashed #aaa;
            background: transparent;
            font-weight: bold;
            font-family: inherit;
            font-size: inherit;
            padding: 0 4px;
        }
        .paper-editable-input:focus {
            outline: none;
            border-bottom: 1px solid var(--fifa-green-primary);
            background: #fdfdfd;
        }
    </style>
</head>
<body>

    <div class="mobile-overlay" id="mobileOverlay" onclick="toggleSidebar()"></div>

    <nav class="navbar top-navbar sticky-top">
        <div class="container-fluid">
            <div class="d-flex align-items-center gap-2">
                <button class="btn btn-outline-success d-lg-none py-1 px-2 border-0" type="button" onclick="toggleSidebar()">
                    <i class='bx bx-menu fs-2' style="color: var(--fifa-green-primary);"></i>
                </button>
                <a class="navbar-brand d-flex align-items-center gap-2 m-0" href="/dashboard">
                    <img src="{{ url_for('static', filename='logo.png') }}" alt="نادي فيفا" class="nav-logo" onerror="this.style.display='none'">
                    <div class="d-flex flex-column">
                        <span class="fw-bold fs-6 lh-1" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
                        <span class="text-muted fs-8 d-none d-sm-block mt-1">نظام الأرشفة والخطابات الإلكتروني</span>
                    </div>
                </a>
            </div>
            
            <div class="d-flex align-items-center gap-2">
                {% if can_page_quick_upload == 1 or is_admin %}
                <a href="/quick_upload" class="btn btn-sm btn-warning fw-bold text-dark d-flex align-items-center gap-1 shadow-sm px-2">
                    <i class='bx bx-cloud-upload fs-5'></i> 
                    <span class="d-none d-sm-inline">رفع وتوثيق فوري</span>
                </a>
                {% endif %}
                <div class="dropdown">
                    <button class="btn btn-light dropdown-toggle border py-1 px-2" type="button" data-bs-toggle="dropdown">
                        <i class='bx bxs-user-circle fs-4 ms-1' style="color: var(--fifa-gold);"></i>
                        <span class="fw-bold fs-7" style="color: var(--fifa-green-primary);">{{ dept_name }}</span>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-start shadow">
                        <li><a class="dropdown-item text-danger py-2" href="/logout"><i class='bx bx-log-out ms-2'></i>تسجيل الخروج</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </nav>

    <div class="main-wrapper">
        <aside class="sidebar" id="sidebarMenu">
            <div class="d-flex justify-content-between align-items-center px-3 mb-2 d-lg-none">
                <span class="fw-bold text-white">قائمة التنقل</span>
                <button class="btn text-white fs-3 p-0" onclick="toggleSidebar()">&times;</button>
            </div>
            {% if can_page_inbox == 1 or is_admin %}
            <a href="/dashboard" class="sidebar-link {{ 'active' if current_page == 'inbox' else '' }}"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
            {% endif %}
            {% if can_page_outbox == 1 or is_admin %}
            <a href="/outbox" class="sidebar-link {{ 'active' if current_page == 'outbox' else '' }}"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
            {% endif %}
            {% if can_page_achievements == 1 or is_admin %}
            <a href="/monthly_achievements" class="sidebar-link {{ 'active' if current_page == 'achievements' else '' }}"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
            {% endif %}
            {% if can_page_archive == 1 or is_admin %}
            <a href="/archive" class="sidebar-link {{ 'active' if current_page == 'archive' else '' }}"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
            {% endif %}
            {% if can_page_quick_upload == 1 or is_admin %}
            <a href="/quick_upload" class="sidebar-link {{ 'active' if current_page == 'quick_upload' else '' }}"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
            {% endif %}
            {% if is_admin %}
            <a href="/admin/dashboard" class="sidebar-link {{ 'active' if current_page == 'admin_dashboard' else '' }}" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
            <a href="/admin/permissions" class="sidebar-link {{ 'active' if current_page == 'permissions' else '' }}"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
            {% endif %}
            {% if can_add_user == 1 or is_admin %}
            <a href="/register" class="sidebar-link {{ 'active' if current_page == 'register' else '' }}"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
            {% endif %}
            <div class="border-top border-secondary my-3 opacity-25"></div>
            <a href="/logout" class="sidebar-link text-danger"><i class='bx bx-log-out text-danger'></i>تسجيل الخروج</a>
        </aside>

        <main class="content-body">
            <div class="container-fluid p-0">
                <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-3">
                    <h4 class="section-header m-0">{{ page_title }}</h4>
                    {% if current_page == 'outbox' or current_page == 'inbox' %}
                    <button type="button" class="btn btn-danger d-flex align-items-center gap-2 shadow-sm fw-bold" onclick="downloadLetterPDF()">
                        <i class='bx bxs-file-pdf fs-5'></i> تحميل PDF
                    </button>
                    {% endif %}
                </div>

                {% if current_page == 'outbox' or current_page == 'inbox' %}
                <!-- ============ ورقة الخطاب الرسمية المباشرة (ورد) ============ -->
                <div class="word-paper-container">
                    <div class="word-paper" id="officialPaper">
                        <div class="word-paper-header">
                            <div class="word-paper-right">
                                المملكة العربية السعودية<br>
                                وزارة الرياضة<br>
                                فرع وزارة الرياضة بجازان<br>
                                نادي فيفا الرياضي
                            </div>
                            <div class="word-paper-center">
                                <img src="{{ url_for('static', filename='logo.png') }}" alt="FAIFA" onerror="this.style.display='none'">
                                <div class="fw-bold text-success fs-5">FAIFA</div>
                            </div>
                            <div class="word-paper-left">
                                الرقم: <input type="text" id="paperLetterNumInput" class="paper-editable-input" value="—" style="width: 100px;"><br>
                                التاريخ : <input type="text" id="paperLetterDateInput" class="paper-editable-input" value="{{ now.strftime('%Y/%m/%dم') }}" style="width: 100px;"><br>
                                المشفوعات : <input type="text" id="paperLetterAttachInput" class="paper-editable-input" value="-" style="width: 100px;">
                            </div>
                        </div>

                        <div class="word-paper-title">
                            سعادة <input type="text" id="paperSalutationInput" class="paper-editable-input text-center" value="الرئيس التنفيذي" style="width: 250px;"> المحترم
                        </div>
                        <div class="word-paper-greeting">
                            السلام عليكم ورحمة الله وبركاته
                        </div>

                        <div class="word-paper-body" id="paperBodyText">
إشارة إلى خطابكم الكريم بشأن الملاحظات والتوصيات المعتمدة، نود الإفادة بأنه تم الاطلاع على كافة التفاصيل والتعامل معها وفق الأنظمة واللوائح المعتمدة.

شاكرين لكم حسن تعاونكم الدائم معنا.
                        </div>

                        <div class="word-paper-footer-closing">
                            شاكرين ومقدرين
                        </div>

                        <div class="word-paper-signature">
                            <input type="text" id="paperSignerTitleInput" class="paper-editable-input" value="{{ dept_name }}" style="width: 220px;"><br>
                            <span style="font-size: 1.25rem; font-weight: bold;">
                                <input type="text" id="paperSignerNameInput" class="paper-editable-input" value="مسؤول الإدارة" style="width: 220px;">
                            </span>
                        </div>

                        <div class="word-paper-contacts">
                            <div>fifaclub1436@gmail.com <i class='bx bx-envelope ms-1'></i></div>
                            <div>faifaclub1 <i class='bx bxl-twitter ms-1'></i></div>
                        </div>
                    </div>
                </div>

                <!-- ============ نموذج تفاصيل الخطاب والإرسال ============ -->
                <div class="modern-card p-4 mb-4">
                    <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-paper-plane ms-1'></i> تفاصيل إرسال المعاملة / الخطاب</h5>
                    <form id="letterSendForm" action="/send_letter" method="post" enctype="multipart/form-data">
                        <input type="hidden" name="letter_id" id="editLetterId" value="">
                        <div class="row g-3">
                            <div class="col-md-6">
                                <label class="form-label fw-bold fs-7">إلى الإدارة المستلمة:</label>
                                <select name="receiver_id" id="receiverSelect" class="form-select fs-7" required onchange="updateReceiverTitle(this)">
                                    <option value="" selected disabled>اختر الإدارة المستلمة...</option>
                                    {% for d in depts %}
                                        <option value="{{ d.id }}" data-name="{{ d.name }}">{{ d.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-bold fs-7">عنوان الخطاب (الموضوع):</label>
                                <input type="text" name="title" id="letterTitleInput" class="form-control fs-7" required placeholder="أدخل عنوان الخطاب...">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-bold fs-7">الأهمية:</label>
                                <select name="priority" id="letterPriority" class="form-select fs-7">
                                    <option value="عادي">عادي</option>
                                    <option value="عاجل">عاجل</option>
                                    <option value="سري للغاية">سري للغاية</option>
                                </select>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-bold fs-7">مرفق إضافي (اختياري):</label>
                                <input type="file" name="file" class="form-control fs-7">
                            </div>
                            <div class="col-12">
                                <label class="form-label fw-bold fs-7">صيغة ومحتوى الخطاب (تعديل مباشر للورقة أعلاه):</label>
                                <textarea name="content" id="letterContentInput" class="form-control fs-7" rows="5" placeholder="اكتب صيغة الخطاب هنا..." oninput="syncContent(this.value)"></textarea>
                            </div>
                            <div class="col-12 text-end mt-3">
                                <button type="submit" class="btn btn-fifa-primary px-5 py-2 fw-bold shadow">
                                    <i class='bx bxs-paper-plane ms-1'></i> إرسال الخطاب الآن
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
                {% endif %}

                <div class="modern-card p-2 p-sm-3">
                    {% if letters %}
                        <div class="letters-list">
                            {% for letter in letters %}
                                <div class="letter-item d-flex flex-column flex-sm-row align-items-start justify-content-between gap-2">
                                    <div class="d-flex align-items-start gap-2 w-100">
                                        <i class='bx bxs-file-archive fs-3 text-success mt-1 d-none d-sm-block'></i>
                                        <div class="w-100">
                                            <div class="d-flex flex-wrap justify-content-between align-items-center mb-1 gap-1">
                                                <span class="fw-bold text-dark fs-6">{{ letter.title }}</span>
                                                <small class="text-muted fs-8">{{ letter.created_at.split(' ')[0] if letter.created_at else '' }}</small>
                                            </div>
                                            {% if letter.content %}
                                                <p class="text-secondary small mb-2" id="letter-text-{{ letter.id }}">{{ letter.content }}</p>
                                            {% endif %}

                                            <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
                                                <span class="fs-7 text-muted">
                                                    {% if current_page == 'outbox' %}إلى: <strong>{{ letter.receiver_name }}</strong>
                                                    {% elif current_page == 'inbox' %}من: <strong>{{ letter.sender_name }}</strong>
                                                    {% elif current_page == 'archive' %}
                                                        {% if letter.archive_dept_name %}
                                                            أرشيف إدارة: <span class="badge bg-success text-white px-2 py-1">{{ letter.archive_dept_name }}</span>
                                                        {% elif letter.sender_id and letter.receiver_id %}
                                                            من: <strong>{{ letter.sender_name }}</strong> إلى: <strong>{{ letter.receiver_name }}</strong>
                                                        {% else %}
                                                            <span class="badge bg-secondary">أرشيف عام</span>
                                                        {% endif %}
                                                    {% else %}<span class="badge bg-warning text-dark">رفع فوري خاص</span>{% endif %}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="d-flex align-items-center gap-2 w-100 justify-content-end mt-2 mt-sm-0">
                                        {% if current_page == 'inbox' or current_page == 'outbox' %}
                                            <!-- زر التعديل والإرسال التفاعلي -->
                                            <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 fs-7 text-nowrap" onclick="loadLetterToEditor('{{ letter.id }}', '{{ letter.title|e }}', '{{ letter.sender_id if current_page == 'inbox' else letter.receiver_id }}', '{{ letter.priority }}')">
                                                <i class='bx bx-edit ms-1'></i> تعديل / إرسال
                                            </button>
                                        {% endif %}

                                        {% if letter.file_data %}
                                            <a href="/view_letter_file/{{ letter.id }}" target="_blank" class="btn btn-sm btn-success py-1 px-2 fs-7 shadow-sm">فتح بالموقع</a>
                                            <a href="/download_letter_file/{{ letter.id }}" class="btn btn-sm btn-outline-success py-1 px-2 fs-7">تحميل</a>
                                        {% endif %}

                                        <span class="priority-badge bg-fifa-green">{{ letter.priority }}</span>
                                        {% if can_delete == 1 or is_admin %}
                                            <a href="/delete_letter/{{ letter.id }}" class="btn btn-sm btn-outline-danger py-1 px-2 fs-7" onclick="return confirm('حذف المعاملة؟');">حذف</a>
                                        {% endif %}
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    {% else %}
                        <div class="text-center py-5 text-muted"><p class="fs-7">لا توجد سجلات مسجلة حالياً.</p></div>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function toggleSidebar() {
            document.getElementById('sidebarMenu').classList.toggle('show-sidebar');
            document.getElementById('mobileOverlay').classList.toggle('active');
        }

        function updateReceiverTitle(selectElem) {
            var selectedOption = selectElem.options[selectElem.selectedIndex];
            var deptName = selectedOption.getAttribute('data-name');
            if (deptName) {
                document.getElementById('paperSalutationInput').value = deptName;
            }
        }

        function syncContent(text) {
            var paperBody = document.getElementById('paperBodyText');
            if (paperBody) {
                paperBody.innerText = text.trim() !== '' ? text : "أدخل نص الخطاب...";
            }
        }

        // دالة لتحميل مادة الخطاب وتعبئته مباشرة بالورقة والنموذج
        function loadLetterToEditor(id, title, targetDeptId, priority) {
            var textElem = document.getElementById('letter-text-' + id);
            var content = textElem ? textElem.innerText : '';
            
            document.getElementById('letterTitleInput').value = title;
            document.getElementById('letterContentInput').value = content;
            document.getElementById('letterPriority').value = priority;
            
            // تحديد الإدارة المستهدفة في القائمة إن وُجدت
            var receiverSelect = document.getElementById('receiverSelect');
            if (receiverSelect && targetDeptId) {
                receiverSelect.value = targetDeptId;
                updateReceiverTitle(receiverSelect);
            }

            syncContent(content);

            var paperBody = document.getElementById('officialPaper');
            if (paperBody) {
                paperBody.scrollIntoView({ behavior: 'smooth' });
            }
        }

        function downloadLetterPDF() {
            var element = document.getElementById('officialPaper');
            var opt = {
              margin:       0.2,
              filename:     'خطاب_رسمي_نادي_فيفا.pdf',
              image:        { type: 'jpeg', quality: 0.98 },
              html2canvas:  { scale: 2 },
              jsPDF:        { unit: 'in', format: 'a4', orientation: 'portrait' }
            };
            html2pdf().set(opt).from(element).save();
        }

        window.addEventListener('DOMContentLoaded', function() {
            var inputContent = document.getElementById('letterContentInput');
            if (inputContent && inputContent.value.trim() !== '') {
                syncContent(inputContent.value);
            }
        });
    </script>
</body>
</html>
'''

@app.route('/dashboard')
def dashboard():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = session['dept_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM departments WHERE id = %s', (dept_id,))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_page_inbox'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الوصول للصندوق الوارد."); window.location.href="/";</script>'''
    
    cursor.execute('SELECT id, name FROM departments WHERE id != %s', (dept_id,))
    depts = cursor.fetchall()
    
    cursor.execute('''
        SELECT l.*, d.name as sender_name 
        FROM letters l 
        JOIN departments d ON l.sender_id = d.id 
        WHERE l.receiver_id = %s 
        ORDER BY l.id DESC
    ''', (dept_id,))
    letters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template_string(DASHBOARD_HTML, 
                                  page_title="الصندوق الوارد",
                                  current_page="inbox",
                                  letters=letters, 
                                  depts=depts, 
                                  dept_name=session['dept_name'],
                                  can_delete=current_dept['can_delete'],
                                  can_add_user=current_dept['can_add_user'],
                                  can_page_quick_upload=current_dept['can_page_quick_upload'],
                                  can_page_inbox=current_dept['can_page_inbox'],
                                  can_page_outbox=current_dept['can_page_outbox'],
                                  can_page_achievements=current_dept['can_page_achievements'],
                                  can_page_archive=current_dept['can_page_archive'],
                                  is_admin=is_admin,
                                  now=datetime.now())

@app.route('/outbox')
def outbox():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = session['dept_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM departments WHERE id = %s', (dept_id,))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_page_outbox'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الوصول للخطابات الصادرة."); window.location.href="/dashboard";</script>'''
    
    cursor.execute('SELECT id, name FROM departments WHERE id != %s', (dept_id,))
    depts = cursor.fetchall()
    
    cursor.execute('''
        SELECT l.*, d.name as receiver_name 
        FROM letters l 
        JOIN departments d ON l.receiver_id = d.id 
        WHERE l.sender_id = %s 
        ORDER BY l.id DESC
    ''', (dept_id,))
    letters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template_string(DASHBOARD_HTML, 
                                  page_title="الخطابات الصادرة",
                                  current_page="outbox",
                                  letters=letters, 
                                  depts=depts, 
                                  dept_name=session['dept_name'],
                                  can_delete=current_dept['can_delete'],
                                  can_add_user=current_dept['can_add_user'],
                                  can_page_quick_upload=current_dept['can_page_quick_upload'],
                                  can_page_inbox=current_dept['can_page_inbox'],
                                  can_page_outbox=current_dept['can_page_outbox'],
                                  can_page_achievements=current_dept['can_page_achievements'],
                                  can_page_archive=current_dept['can_page_archive'],
                                  is_admin=is_admin,
                                  now=datetime.now())

@app.route('/send_letter', methods=['POST'])
def send_letter():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
    
    sender_id = session['dept_id']
    receiver_id = request.form.get('receiver_id')
    title = request.form.get('title')
    priority = request.form.get('priority', 'عادي')
    content = request.form.get('content', '')
    file = request.files.get('file')
    
    conn = get_db_connection()
    cursor = conn.cursor()

    file_name = ''
    file_data = None
    file_mimetype = None
    if file and file.filename != '':
        original_name = secure_filename(file.filename)
        file_name = f"{int(datetime.now().timestamp())}_{original_name}"
        file_data = psycopg2.Binary(file.read())
        file_mimetype = file.content_type or 'application/octet-stream'
        
    cursor.execute('''
        INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, datetime.now().strftime('%Y-%m-%d %H:%M')))
        
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('outbox'))

@app.route('/archive')
def archive():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = session['dept_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM departments WHERE id = %s', (dept_id,))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_page_archive'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الوصول لأرشيف الإدارة."); window.location.href="/dashboard";</script>'''
    
    cursor.execute('SELECT id, name FROM departments WHERE id != %s', (dept_id,))
    depts = cursor.fetchall()

    if current_dept['can_view_all_archive'] == 1 or is_admin:
        cursor.execute('''
            SELECT l.*, s.name as sender_name, r.name as receiver_name, ad.name as archive_dept_name 
            FROM letters l 
            LEFT JOIN departments s ON l.sender_id = s.id 
            LEFT JOIN departments r ON l.receiver_id = r.id 
            LEFT JOIN departments ad ON l.archive_dept_id = ad.id 
            WHERE (l.sender_id = l.receiver_id AND l.sender_id IS NOT NULL) OR (l.sender_id IS NULL AND l.receiver_id IS NULL)
            ORDER BY l.id DESC
        ''')
    else:
        cursor.execute('''
            SELECT l.*, s.name as sender_name, r.name as receiver_name, ad.name as archive_dept_name 
            FROM letters l 
            LEFT JOIN departments s ON l.sender_id = s.id 
            LEFT JOIN departments r ON l.receiver_id = r.id 
            LEFT JOIN departments ad ON l.archive_dept_id = ad.id 
            WHERE ((l.sender_id = l.receiver_id AND l.sender_id = %s) OR (l.sender_id IS NULL AND l.receiver_id IS NULL AND l.archive_dept_id = %s))
            ORDER BY l.id DESC
        ''', (dept_id, dept_id))
        
    letters = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template_string(DASHBOARD_HTML, 
                                  page_title="أرشيف الإدارة",
                                  current_page="archive",
                                  letters=letters, 
                                  depts=depts, 
                                  dept_name=session['dept_name'],
                                  can_delete=current_dept['can_delete'],
                                  can_add_user=current_dept['can_add_user'],
                                  can_page_quick_upload=current_dept['can_page_quick_upload'],
                                  can_page_inbox=current_dept['can_page_inbox'],
                                  can_page_outbox=current_dept['can_page_outbox'],
                                  can_page_achievements=current_dept['can_page_achievements'],
                                  can_page_archive=current_dept['can_page_archive'],
                                  is_admin=is_admin,
                                  now=datetime.now())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
