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
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='departments'")
    dept_columns = [col['column_name'] for col in cursor.fetchall()]
    if 'can_view_all_archive' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_view_all_archive INTEGER DEFAULT 1')
    if 'can_view_all_achievements' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_view_all_achievements INTEGER DEFAULT 0')
    if 'can_add_user' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_add_user INTEGER DEFAULT 1')
        
    if 'can_page_inbox' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_page_inbox INTEGER DEFAULT 1')
    if 'can_page_outbox' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_page_outbox INTEGER DEFAULT 1')
    if 'can_page_achievements' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_page_achievements INTEGER DEFAULT 1')
    if 'can_page_archive' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_page_archive INTEGER DEFAULT 1')
    if 'can_page_quick_upload' not in dept_columns:
        cursor.execute('ALTER TABLE departments ADD COLUMN can_page_quick_upload INTEGER DEFAULT 1')

    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='letters'")
    letter_cols = [col['column_name'] for col in cursor.fetchall()]
    if 'file_path' not in letter_cols:
        cursor.execute('ALTER TABLE letters ADD COLUMN file_path TEXT')
    if 'archive_dept_id' not in letter_cols:
        cursor.execute('ALTER TABLE letters ADD COLUMN archive_dept_id INTEGER')
    if 'file_data' not in letter_cols:
        cursor.execute('ALTER TABLE letters ADD COLUMN file_data BYTEA')
    if 'file_mimetype' not in letter_cols:
        cursor.execute('ALTER TABLE letters ADD COLUMN file_mimetype TEXT')
    if 'letter_number' not in letter_cols:
        cursor.execute('ALTER TABLE letters ADD COLUMN letter_number TEXT')

    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='monthly_achievements'")
    ach_cols = [col['column_name'] for col in cursor.fetchall()]
    if 'title' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN title TEXT')
    if 'file_name' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN file_name TEXT')
    if 'file_path' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN file_path TEXT')
    if 'month_year' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN month_year TEXT')
    if 'uploaded_at' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN uploaded_at TEXT')
    if 'file_data' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN file_data BYTEA')
    if 'file_mimetype' not in ach_cols:
        cursor.execute('ALTER TABLE monthly_achievements ADD COLUMN file_mimetype TEXT')
    
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

@app.route('/delete_selected_letters', methods=['POST'])
def delete_selected_letters():
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
        
    letter_ids_raw = request.form.getlist('letter_ids')
    action_type = request.form.get('action_type')
    dept_id = session['dept_id']

    if action_type == 'all':
        if current_dept['can_view_all_archive'] == 1 or is_admin:
            cursor.execute('''
                DELETE FROM letters 
                WHERE (sender_id = receiver_id AND sender_id IS NOT NULL) OR (sender_id IS NULL AND receiver_id IS NULL)
            ''')
        else:
            cursor.execute('''
                DELETE FROM letters 
                WHERE (sender_id = receiver_id AND sender_id = %s) OR (sender_id IS NULL AND receiver_id IS NULL AND archive_dept_id = %s)
            ''', (dept_id, dept_id))
    elif letter_ids_raw:
        letter_ids = [int(lid) for lid in letter_ids_raw if lid.isdigit()]
        if letter_ids:
            cursor.execute('DELETE FROM letters WHERE id = ANY(%s)', (letter_ids,))
        
    conn.commit()
    cursor.close()
    conn.close()
    return '''<script>alert("تمت عملية الحذف بنجاح!"); window.location.href="/archive";</script>'''

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

@app.route('/admin/clear_monthly_files/<int:dept_id>')
def clear_monthly_files(dept_id):
    if 'dept_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))

    if str(session['dept_id']) != str(dept_id) and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("غير مسموح لك بتفريغ ملفات هذه الإدارة."); window.location.href="/monthly_achievements";</script>'''
    
    cursor.execute('SELECT * FROM monthly_achievements WHERE dept_id = %s', (dept_id,))
    achievements = cursor.fetchall()
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    for ach in achievements:
        cursor.execute('''
            INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at, archive_dept_id)
            VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s)
        ''', (
            f"أرشيف إنجازات شهرية: {ach['title']}",
            f"تمت الأرشفة التلقائية من إنجازات الشهر بتاريخ: {current_time}",
            "عادي",
            ach['file_name'],
            ach.get('file_data'),
            ach.get('file_mimetype'),
            current_time,
            dept_id
        ))
    
    cursor.execute('DELETE FROM monthly_achievements WHERE dept_id = %s', (dept_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    return '''<script>alert("تم تفريغ وأرشفة ملفات الإنجازات الشهرية للإدارة بنجاح إلى أرشيفها الخاص!"); window.location.href="/monthly_achievements";</script>'''

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_add_user'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك الصلاحية لإضافة إدارة أو مستخدم جديد."); window.location.href="/dashboard";</script>'''

    if request.method == 'POST':
        dept_name = request.form['dept_name'].strip()
        username = request.form['username'].strip()
        password = request.form['password']
        
        try:
            cursor.execute('''
                INSERT INTO departments (name, username, password, can_access_archive, can_view_all_archive, can_view_all_achievements, can_add_user, can_page_inbox, can_page_outbox, can_page_achievements, can_page_archive, can_page_quick_upload) 
                VALUES (%s, %s, %s, 1, 1, 0, 1, 1, 1, 1, 1, 1)
            ''', (dept_name, username, password))
            conn.commit()
            cursor.close()
            conn.close()
            return '''<script>alert("تم إنشاء حساب الإدارة بنجاح!"); window.location.href="/admin/permissions";</script>'''
        except IntegrityError as e:
            conn.rollback()
            cursor.execute('SELECT id FROM departments WHERE username = %s', (username,))
            user_exists = cursor.fetchone()
            cursor.execute('SELECT id FROM departments WHERE name = %s', (dept_name,))
            name_exists = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_exists:
                return '''<script>alert("خطأ: اسم المستخدم (username) مستخدم مكرر بالفعل، يرجى اختيار اسم مستخدم آخر."); window.location.href="/register";</script>'''
            elif name_exists:
                return '''<script>alert("خطأ: اسم الإدارة أو القسم (name) مسجل مكرر بالفعل، يرجى تغييره."); window.location.href="/register";</script>'''
            else:
                return '''<script>alert("حدث خطأ في قاعدة البيانات أثناء التسجيل (قيمة مكررة)!"); window.location.href="/register";</script>'''
            
    cursor.close()
    conn.close()
    
    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إنشاء حساب إدارة - نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 15px; }
            .register-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 16px; border: 1px solid #d5e2d8; box-shadow: 0 10px 30px rgba(18, 56, 38, 0.08); width: 100%; max-width: 450px; padding: 1.5rem; position: relative; overflow: hidden; }
            .register-card::before { content: ''; position: absolute; top: 0; right: 0; left: 0; height: 5px; background: linear-gradient(90deg, var(--fifa-gold), var(--fifa-green)); }
            .form-control { border-radius: 8px; padding: 0.75rem 1rem; border-color: #dbe3df; }
            .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; border-radius: 8px; padding: 0.75rem; font-weight: 700; border: none; width: 100%; }
        </style>
    </head>
    <body>
        <div class="register-card text-center">
            <h5 class="fw-bold mb-1" style="color: var(--fifa-green);">تسجيل إدارة/قسم جديد</h5>
            <p class="text-muted fs-7 mb-4">إنشاء حساب إداري متصل بنظام أرشفة النادي</p>
            <form action="/register" method="post">
                <div class="mb-3 text-start">
                    <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);">اسم الإدارة / القسم</label>
                    <input type="text" name="dept_name" class="form-control" placeholder="مثال: إدارة الألعاب الرياضية" required>
                </div>
                <div class="mb-3 text-start">
                    <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);">اسم المستخدم (للدخول)</label>
                    <input type="text" name="username" class="form-control" placeholder="مثال: sports_dept" required>
                </div>
                <div class="mb-4 text-start">
                    <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);">كلمة المرور</label>
                    <input type="password" name="password" class="form-control" placeholder="أدخل كلمة مرور قوية" required>
                </div>
                <button type="submit" class="btn btn-fifa-gold mb-3">تسجيل الحساب</button>
            </form>
            <div class="border-top pt-3 mt-2">
                <a href="/dashboard" class="text-muted text-decoration-none fs-7"><i class='bx bx-right-arrow-alt ms-1'></i>العودة لوحة التحكم</a>
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
    <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
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
            .sidebar {
                position: fixed;
                top: 0;
                right: -260px;
                height: 100vh;
                box-shadow: -5px 0 15px rgba(0,0,0,0.2);
            }
            .sidebar.show-sidebar {
                right: 0;
            }
        }

        .mobile-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(0,0,0,0.5);
            z-index: 1030;
        }
        .mobile-overlay.active { display: block; }

        .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
        .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
        .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
        .content-body { flex: 1; padding: 1.25rem; width: 100%; overflow-x: hidden; }
        .modern-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 12px; border: 1px solid var(--fifa-card-border); box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); }
        .section-header { font-weight: 800; color: var(--fifa-green-primary); margin-bottom: 1.5rem; position: relative; padding-bottom: 10px; font-size: 1.3rem; }
        .section-header::after { content: ''; position: absolute; bottom: 0; right: 0; width: 55px; height: 3px; background-color: var(--fifa-gold); border-radius: 2px; }
        .btn-fifa-primary { background-color: var(--fifa-green-primary); color: #ffffff; border-radius: 8px; padding: 0.6rem 1.2rem; font-weight: 700; border: none; }
        .btn-fifa-primary:hover { background-color: var(--fifa-green-light); color: #fff; }

        /* ================= نمط الخطاب الرسمي الحقيقي (قالب ورقة A4) ================= */
        .paper-container {
            background: #ffffff;
            width: 100%;
            max-width: 820px;
            margin: 0 auto 2rem auto;
            padding: 2.5rem 3rem;
            border-radius: 4px;
            box-shadow: 0 0 20px rgba(0,0,0,0.08);
            border: 1px solid #d3d3d3;
            position: relative;
            font-family: 'Almarai', sans-serif;
            color: #111111;
        }

        .paper-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #123826;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }

        .paper-header-right {
            text-align: right;
            font-size: 0.88rem;
            font-weight: 800;
            line-height: 1.7;
            color: #123826;
        }

        .paper-header-center {
            text-align: center;
        }

        .paper-header-center img {
            max-height: 70px;
            width: auto;
            object-fit: contain;
        }

        .paper-header-left {
            text-align: right;
            font-size: 0.85rem;
            font-weight: 700;
            color: #123826;
        }

        .meta-line {
            display: flex;
            align-items: center;
            gap: 5px;
            margin-bottom: 5px;
        }

        .paper-input-inline {
            border: none;
            border-bottom: 1px dotted #123826;
            background: transparent;
            font-weight: 700;
            color: #123826;
            width: 120px;
            font-size: 0.85rem;
            padding: 0 4px;
        }
        .paper-input-inline:focus { outline: none; border-bottom: 1px solid #c5a059; }

        .paper-salutation-inputs {
            margin-bottom: 1.5rem;
        }

        .salutation-field {
            border: none;
            background: transparent;
            font-weight: 800;
            font-size: 1.05rem;
            color: #123826;
            width: 100%;
            margin-bottom: 5px;
        }
        .salutation-field:focus { outline: none; background: #fdfdfd; }

        .greeting-field {
            border: none;
            background: transparent;
            font-weight: 700;
            font-size: 0.95rem;
            color: #333333;
            width: 100%;
        }

        .paper-body-textarea {
            width: 100%;
            min-height: 250px;
            border: none;
            background: transparent;
            font-size: 0.98rem;
            line-height: 2.1;
            color: #222222;
            resize: vertical;
            padding: 0;
            font-family: 'Almarai', sans-serif;
        }
        .paper-body-textarea:focus { outline: none; }

        .paper-closing {
            text-align: center;
            font-weight: 700;
            font-size: 0.95rem;
            margin: 20px 0;
            color: #222;
        }

        .paper-signature-block {
            float: left;
            text-align: center;
            margin-top: 15px;
            min-width: 200px;
        }

        .signature-title-input, .signature-name-input {
            border: none;
            background: transparent;
            text-align: center;
            font-weight: 800;
            width: 100%;
            display: block;
        }
        .signature-title-input { font-size: 0.95rem; color: #123826; margin-bottom: 5px; }
        .signature-name-input { font-size: 0.9rem; color: #333; }

        .paper-footer {
            clear: both;
            border-top: 1px solid #123826;
            padding-top: 12px;
            margin-top: 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.78rem;
            font-weight: 700;
            color: #123826;
        }

        /* تعديلات خيارات الإرسال الملحقة بأسفل الخطاب */
        .send-controls-card {
            max-width: 820px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid var(--fifa-card-border);
            padding: 1.5rem;
            box-shadow: 0 4px 15px rgba(18, 56, 38, 0.05);
        }

        /* الطباعة PDF */
        @media print {
            body * { visibility: hidden; }
            .paper-container, .paper-container * { visibility: visible; }
            .paper-container {
                position: absolute;
                left: 0;
                top: 0;
                width: 100%;
                max-width: 100%;
                border: none;
                box-shadow: none;
                padding: 15mm 20mm;
            }
            .paper-input-inline, .salutation-field, .greeting-field, .paper-body-textarea, .signature-title-input, .signature-name-input {
                border: none !important;
            }
            .send-controls-card, .top-navbar, .sidebar, .section-header { display: none !important; }
        }
    </style>
</head>
<body>

    <nav class="top-navbar d-flex justify-content-between align-items-center">
        <div class="d-flex align-items-center">
            <button class="btn btn-sm d-lg-none me-2" onclick="toggleSidebar()" style="color: var(--fifa-green-primary); font-size: 1.5rem;">
                <i class='bx bx-menu'></i>
            </button>
            <img src="{{ url_for('static', filename='logo.png') }}" alt="شعار النادي" class="nav-logo me-2" onerror="this.style.display='none'">
            <span class="fw-bold fs-6 d-none d-sm-inline" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
        </div>
        <div class="d-flex align-items-center gap-3">
            <span class="badge bg-fifa-green px-3 py-2 rounded-pill fs-7">
                <i class='bx bxs-user-badge ms-1 align-middle'></i> {{ session.get('dept_name', 'مستخدم') }}
            </span>
            <a href="/logout" class="btn btn-outline-danger btn-sm rounded-8 fw-bold">
                <i class='bx bx-log-out align-middle'></i> خروج
            </a>
        </div>
    </nav>

    <div class="mobile-overlay" id="mobileOverlay" onclick="toggleSidebar()"></div>

    <div class="main-wrapper">
        <div class="sidebar" id="sidebarMenu">
            <div class="px-3 pb-3 mb-2 border-bottom border-light border-opacity-10 text-center">
                <small class="text-white-50 fs-8">القائمة الرئيسية</small>
            </div>
            
            {% if current_dept.can_page_inbox == 1 or is_admin %}
            <a href="/dashboard" class="sidebar-link {% if active_page == 'inbox' %}active{% endif %}">
                <i class='bx bxs-inbox'></i> البريد الوارد
            </a>
            {% endif %}

            {% if current_dept.can_page_outbox == 1 or is_admin %}
            <a href="/outbox" class="sidebar-link {% if active_page == 'outbox' %}active{% endif %}">
                <i class='bx bxs-paper-plane'></i> إنشاء خطاب (الصادر)
            </a>
            {% endif %}

            {% if current_dept.can_page_quick_upload == 1 or is_admin %}
            <a href="/quick_upload" class="sidebar-link {% if active_page == 'quick_upload' %}active{% endif %}">
                <i class='bx bxs-cloud-upload'></i> رفع سريع للخطابات
            </a>
            {% endif %}

            {% if current_dept.can_page_achievements == 1 or is_admin %}
            <a href="/monthly_achievements" class="sidebar-link {% if active_page == 'achievements' %}active{% endif %}">
                <i class='bx bxs-trophy'></i> الإنجازات الشهرية
            </a>
            {% endif %}

            {% if current_dept.can_page_archive == 1 or is_admin %}
            <a href="/archive" class="sidebar-link {% if active_page == 'archive' %}active{% endif %}">
                <i class='bx bxs-archive-in'></i> الأرشيف العام
            </a>
            {% endif %}

            {% if is_admin or current_dept.can_add_user == 1 %}
            <div class="px-3 pt-3 pb-1 mt-3 border-top border-light border-opacity-10">
                <small class="text-white-50 fs-8">الإدارة والصلاحيات</small>
            </div>
            <a href="/register" class="sidebar-link">
                <i class='bx bxs-user-plus'></i> إضافة إدارة جديدة
            </a>
            <a href="/admin/permissions" class="sidebar-link {% if active_page == 'permissions' %}active{% endif %}">
                <i class='bx bxs-shield-quarter'></i> التحكم بالصلاحيات
            </a>
            {% endif %}
        </div>

        <div class="content-body">
            
            {% if active_page == 'outbox' %}
            <div class="d-flex justify-content-between align-items-center mb-3 max-w-820 mx-auto" style="max-width: 820px;">
                <h4 class="section-header mb-0">تحرير خطاب رسمي صادر</h4>
                <button type="button" class="btn btn-outline-secondary btn-sm rounded-3 fw-bold" onclick="window.print()">
                    <i class='bx bxs-printer ms-1'></i> طباعة / تحميل PDF
                </button>
            </div>

            <form action="/send_letter" method="post" enctype="multipart/form-data">
                
                <!-- ================= الورقة الرسمية (مباشرة في الصفحة) ================= -->
                <div class="paper-container">
                    
                    <!-- هيدر الخطاب -->
                    <div class="paper-header">
                        <div class="paper-header-right">
                            <div>المملكة العربية السعودية</div>
                            <div>وزارة الرياضة</div>
                            <div>فرع وزارة الرياضة بجازان</div>
                            <div>نادي فيفا الرياضي</div>
                        </div>

                        <div class="paper-header-center">
                            <img src="{{ url_for('static', filename='logo.png') }}" alt="شعار النادي" onerror="this.src='https://via.placeholder.com/70?text=FIFA+CLUB'">
                        </div>

                        <div class="paper-header-left">
                            <div class="meta-line">
                                <span>الرقم:</span>
                                <input type="text" name="letter_number" class="paper-input-inline" value="م/تقنية/102" placeholder="الرقم الرسمى">
                            </div>
                            <div class="meta-line">
                                <span>التاريخ:</span>
                                <input type="text" name="letter_date" class="paper-input-inline" value="{{ current_date }}" placeholder="التاريخ">
                            </div>
                            <div class="meta-line">
                                <span>المشفوعات:</span>
                                <input type="text" name="attachments" class="paper-input-inline" value="-" placeholder="المشفوعات">
                            </div>
                        </div>
                    </div>

                    <!-- التحية والافتتاحية -->
                    <div class="paper-salutation-inputs">
                        <input type="text" name="salutation" class="salutation-field" value="سعادة الرئيس التنفيذي" placeholder="المرسل إليه...">
                        <input type="text" name="greeting" class="greeting-field" value="السلام عليكم ورحمة الله وبركاته،،، تحية طيبة وبعد:" placeholder="التحية...">
                    </div>

                    <!-- نص الخطاب الرئيسي -->
                    <div class="paper-body">
                        <textarea name="content" class="paper-body-textarea" placeholder="اكتب نص الخطاب هنا..." required>إشارة إلى خطابكم الكريم بشأن ملاحظات عدم الامتثال، نود الإفادة بأنه تم الاطلاع على ما ورد من ملاحظات، والعمل على معالجتها، حيث تم تعزيز الالتزام بإجراءات النسخ الاحتياطي للبيانات، ومراجعة وتحديث صلاحيات المستخدمين بما يتناسب مع طبيعة مهامهم، والتأكيد على توثيق جميع الأعطال والحوادث التقنية في السجلات الرسمية المعتمدة.

كما تم اتخاذ الإجراءات التصحيحية اللازمة لضمان رفع مستوى الالتزام ومنع تكرار هذه الملاحظات مستقبلاً، وسيتم تزويد إدارة الحوكمة والامتثال والمخاطر بتقرير يوضح ما تم اتخاذه خلال المدة المحددة.</textarea>
                    </div>

                    <div class="paper-closing">
                        شاكرين ومقدرين تعاونكم الداعم ،،،
                    </div>

                    <!-- التوقيع والمنسق -->
                    <div class="paper-signature-block">
                        <input type="text" name="sender_title" class="signature-title-input" value="مدير تقنية المعلومات">
                        <input type="text" name="sender_name" class="signature-name-input" value="عيسى حسين الفيفي">
                    </div>

                    <div style="clear: both;"></div>

                    <!-- فوتر الخطاب الرسمي -->
                    <div class="paper-footer">
                        <div><i class='bx bx-envelope ms-1'></i> fifaclub1436@gmail.com</div>
                        <div><i class='bx bxl-twitter ms-1'></i> faifaclub1</div>
                    </div>

                </div>

                <!-- ================= خيارات الحفظ والإرسال أسفل الورقة ================= -->
                <div class="send-controls-card">
                    <h6 class="fw-bold mb-3" style="color: var(--fifa-green-primary);">
                        <i class='bx bxs-send ms-1'></i> تحديد تفاصيل الإرسال والتوجيه
                    </h6>
                    
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label fw-bold fs-7">الإدارة أو القسم المستلم <span class="text-danger">*</span></label>
                            <select name="receiver_id" class="form-select" required>
                                <option value="" disabled selected>-- اختر الإدارة المستلمة --</option>
                                {% for dept in departments %}
                                    {% if dept.id != session['dept_id'] %}
                                    <option value="{{ dept.id }}">{{ dept.name }}</option>
                                    {% endif %}
                                {% endfor %}
                            </select>
                        </div>

                        <div class="col-md-6">
                            <label class="form-label fw-bold fs-7">عنوان الخطاب (في السجلات) <span class="text-danger">*</span></label>
                            <input type="text" name="title" class="form-control" placeholder="مثال: رد تقنية المعلومات على ملاحظات الامتثال" required>
                        </div>

                        <div class="col-md-6">
                            <label class="form-label fw-bold fs-7">مستوى الأهمية / الأولوية</label>
                            <select name="priority" class="form-select">
                                <option value="عادي" selected>عادي</option>
                                <option value="هام">هام</option>
                                <option value="عاجل جداً">عاجل جداً</option>
                            </select>
                        </div>

                        <div class="col-md-6">
                            <label class="form-label fw-bold fs-7">إرفاق ملف خارجي مع الخطاب (اختياري)</label>
                            <input type="file" name="file" class="form-control">
                        </div>
                    </div>

                    <div class="d-flex gap-2 justify-content-end mt-4 pt-3 border-top">
                        <button type="button" class="btn btn-outline-secondary px-4 fw-bold" onclick="window.print()">
                            <i class='bx bxs-file-pdf ms-1'></i> تحميل PDF / طباعة
                        </button>
                        <button type="submit" class="btn btn-fifa-primary px-5">
                            <i class='bx bxs-paper-plane ms-1'></i> إرسال الخطاب الآن
                        </button>
                    </div>
                </div>

            </form>

            {% elif active_page == 'inbox' %}
            <h4 class="section-header">البريد الوارد</h4>
            <div class="modern-card p-3">
                {% if letters %}
                <div class="table-responsive">
                    <table class="table table-hover align-middle">
                        <thead class="table-light">
                            <tr>
                                <th>رقم الخطاب</th>
                                <th>العنوان</th>
                                <th>الجهة المرسلة</th>
                                <th>الأولوية</th>
                                <th>التاريخ</th>
                                <th>الإجراءات</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for letter in letters %}
                            <tr>
                                <td>{{ letter.letter_number or '-' }}</td>
                                <td class="fw-bold">{{ letter.title }}</td>
                                <td>{{ letter.sender_name or 'إدارة بالنادي' }}</td>
                                <td><span class="badge bg-secondary priority-badge">{{ letter.priority }}</span></td>
                                <td>{{ letter.created_at }}</td>
                                <td>
                                    {% if letter.file_data %}
                                    <a href="/view_letter_file/{{ letter.id }}" target="_blank" class="btn btn-sm btn-outline-primary">عرض المرفق</a>
                                    {% else %}
                                    <span class="text-muted fs-8">بدون مرفق</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="text-center py-5 text-muted">
                    <i class='bx bx-inbox fs-1 d-block mb-2'></i>
                    لا توجد خطابات واردة حالياً.
                </div>
                {% endif %}
            </div>
            {% endif %}

        </div>
    </div>

    <script>
        function toggleSidebar() {
            document.getElementById('sidebarMenu').classList.toggle('show-sidebar');
            document.getElementById('mobileOverlay').classList.toggle('active');
        }
    </script>
</body>
</html>
'''

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
        WHERE l.receiver_id = %s
        ORDER BY l.id DESC
    ''', (session['dept_id'],))
    letters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template_string(
        DASHBOARD_HTML, 
        page_title='البريد الوارد', 
        active_page='inbox', 
        letters=letters, 
        current_dept=current_dept, 
        is_admin=is_admin
    )

@app.route('/outbox')
def outbox():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    cursor.execute('SELECT id, name FROM departments ORDER BY name ASC')
    departments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    current_date = datetime.now().strftime('%Y/%m/%dم')
    
    return render_template_string(
        DASHBOARD_HTML, 
        page_title='إنشاء خطاب صادر', 
        active_page='outbox', 
        departments=departments, 
        current_dept=current_dept, 
        is_admin=is_admin,
        current_date=current_date
    )

@app.route('/send_letter', methods=['POST'])
def send_letter():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    receiver_id = request.form.get('receiver_id')
    title = request.form.get('title')
    priority = request.form.get('priority', 'عادي')
    letter_number = request.form.get('letter_number')
    content = request.form.get('content')
    
    file = request.files.get('file')
    file_name = None
    file_bytes = None
    file_mimetype = None
    
    if file and file.filename != '':
        original_name = secure_filename(file.filename)
        file_name = f"doc_{int(datetime.now().timestamp())}_{original_name}"
        file_bytes = file.read()
        file_mimetype = file.content_type or 'application/octet-stream'

    sender_id = session['dept_id']
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at, letter_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        title, 
        content, 
        priority, 
        sender_id, 
        receiver_id, 
        file_name, 
        psycopg2.Binary(file_bytes) if file_bytes else None, 
        file_mimetype, 
        created_at, 
        letter_number
    ))
    conn.commit()
    cursor.close()
    conn.close()
    
    return '''<script>alert("تم إرسال الخطاب بنجاح!"); window.location.href="/outbox";</script>'''

if __name__ == '__main__':
    app.run(debug=True)
