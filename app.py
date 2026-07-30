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
        
        /* ================= ورقة الخطاب الرسمية A4 ================= */
        .a4-paper-container {
            display: flex;
            justify-content: center;
            margin-bottom: 2rem;
        }
        .a4-paper {
            background: #ffffff;
            width: 100%;
            max-width: 800px;
            min-height: 1050px;
            padding: 3rem 3.5rem;
            border-radius: 4px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.08);
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            border: 1px solid #e0e0e0;
        }
        .letter-header-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid var(--fifa-green-primary);
            padding-bottom: 1.2rem;
            margin-bottom: 2rem;
        }
        .header-right { text-align: right; font-size: 0.85rem; font-weight: 800; color: var(--fifa-green-primary); line-height: 1.7; }
        .header-center { text-align: center; }
        .header-center img { max-height: 85px; width: auto; object-fit: contain; }
        .header-left { text-align: left; font-size: 0.82rem; font-weight: 700; color: var(--fifa-green-primary); line-height: 1.8; }
        .header-left input { border: none; border-bottom: 1px dotted var(--fifa-gold); font-weight: 700; width: 110px; text-align: center; color: var(--fifa-green-primary); background: transparent; }
        .header-left input:focus { outline: none; border-bottom: 2px solid var(--fifa-green-primary); }

        .letter-body-editor { flex: 1; margin-top: 1rem; font-size: 1rem; line-height: 2; color: #111; }
        .letter-field-input { border: none; border-bottom: 1px solid #ccc; font-weight: 800; color: var(--fifa-green-primary); font-size: 1.05rem; padding: 2px 8px; width: 60%; }
        .letter-field-input:focus { outline: none; border-bottom: 2px solid var(--fifa-gold); }
        .letter-textarea { width: 100%; border: 1px dashed #cfdcd5; border-radius: 8px; padding: 12px; font-size: 1rem; line-height: 2; resize: vertical; min-height: 380px; background: #fafdfb; }
        .letter-textarea:focus { outline: none; border-color: var(--fifa-green-primary); background: #ffffff; }

        .letter-footer-stamp {
            margin-top: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            padding-top: 1.5rem;
            border-top: 1px solid #eef2f0;
        }
        .footer-info { font-size: 0.78rem; color: #555; line-height: 1.6; }
        .signature-box { text-align: center; font-weight: 800; color: var(--fifa-green-primary); }
    </style>
</head>
<body>
    <div class="top-navbar d-flex justify-content-between align-items-center">
        <div class="d-flex align-items-center">
            <button class="btn d-lg-none me-2 text-dark p-0 fs-3" id="sidebarToggle"><i class='bx bx-menu'></i></button>
            <img src="{{ url_for('static', filename='logo.png') }}" alt="شعار النادي" class="nav-logo me-2" onerror="this.style.display='none'">
            <h5 class="m-0 fw-bold d-none d-sm-block" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</h5>
        </div>
        <div class="d-flex align-items-center gap-3">
            <span class="fw-bold text-muted fs-7"><i class='bx bxs-user-circle align-middle ms-1 fs-5 text-success'></i> {{ session.get('dept_name', '') }}</span>
            <a href="/logout" class="btn btn-outline-danger btn-sm rounded-pill px-3"><i class='bx bx-log-out align-middle'></i> خروج</a>
        </div>
    </div>

    <div class="mobile-overlay" id="mobileOverlay"></div>

    <div class="main-wrapper">
        <div class="sidebar" id="sidebar">
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

    <script>
        const sidebar = document.getElementById('sidebar');
        const sidebarToggle = document.getElementById('sidebarToggle');
        const mobileOverlay = document.getElementById('mobileOverlay');

        if(sidebarToggle) {
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('show-sidebar');
                mobileOverlay.classList.toggle('active');
            });
        }
        if(mobileOverlay) {
            mobileOverlay.addEventListener('click', () => {
                sidebar.classList.remove('show-sidebar');
                mobileOverlay.classList.remove('active');
            });
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
    
    cursor.execute('SELECT * FROM departments ORDER BY name ASC')
    departments = cursor.fetchall()
    
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
    <div class="row g-4">
        <!-- قالب الورقة الرسمي A4 للإرسال مباشرة -->
        <div class="col-lg-8">
            <form action="/send_official_letter" method="post" id="officialLetterForm">
                <div class="a4-paper-container">
                    <div class="a4-paper" id="paperToPdf">
                        <div>
                            <!-- هيدر الخطاب الرسمي[cite: 2] -->
                            <div class="letter-header-row">
                                <div class="header-right">
                                    المملكة العربية السعودية<br>
                                    وزارة الرياضة<br>
                                    فرع وزارة الرياضة بجازان<br>
                                    نادي فيفا الرياضي
                                </div>
                                <div class="header-center">
                                    <img src="/static/logo.png" alt="FIFA CLUB LOGO" onerror="this.src='https://via.placeholder.com/80?text=FIFA+CLUB'">
                                </div>
                                <div class="header-left">
                                    الرقم: <input type="text" name="letter_number" value="١٤٤٧ / {{ letters|length + 1 }}" required><br>
                                    التاريخ: <input type="text" name="created_at" value="''' + datetime.now().strftime('%Y/%m/%dم') + '''"><br>
                                    المشفوعات: <input type="text" value="-" style="width: 50px;">
                                </div>
                            </div>

                            <!-- محتوى وتفاصيل الخطاب -->
                            <div class="letter-body-editor">
                                <div class="mb-3 d-flex align-items-center">
                                    <span class="fw-bold me-2" style="color: var(--fifa-green-primary);">سعادة:</span>
                                    <select name="receiver_id" class="form-select letter-field-input" required>
                                        <option value="" disabled selected>-- اختر الإدارة المستلمة --</option>
                                        {% for d in departments %}
                                        <option value="{{ d.id }}">{{ d.name }}</option>
                                        {% endfor %}
                                    </select>
                                    <span class="fw-bold ms-2" style="color: var(--fifa-green-primary);">المحترم</span>
                                </div>

                                <div class="mb-3 d-flex align-items-center">
                                    <span class="fw-bold me-2" style="color: var(--fifa-green-primary);">عنوان الخطاب:</span>
                                    <input type="text" name="title" class="letter-field-input" style="width: 75%;" placeholder="أدخل موضوع/عنوان الخطاب هنا..." required>
                                </div>

                                <div class="text-center fw-bold my-3" style="color: #333;">السلام عليكم ورحمة الله وبركاته ،، تحية طيبة وبعد،،</div>

                                <div class="mb-3">
                                    <textarea name="content" class="letter-textarea" placeholder="اكتب نص الخطاب والتفاصيل هنا..." required></textarea>
                                </div>

                                <div class="text-center fw-bold my-3" style="color: #333;">شاكرين ומقدرين حسن تعاونكم ،،</div>
                            </div>
                        </div>

                        <!-- فوتر الخطاب الرسمي[cite: 2] -->
                        <div class="letter-footer-stamp">
                            <div class="footer-info">
                                <i class='bx bx-envelope'></i> fifaclub1436@gmail.com<br>
                                <i class='bx bxl-twitter'></i> faifaclub1
                            </div>
                            <div class="signature-box">
                                {{ session.get('dept_name', '') }}<br><br>
                                <span class="text-muted fw-normal" style="font-size: 0.8rem;">(التوقيع الإلكتروني)</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- أزرار الإجراءات أسفل الورقة -->
                <div class="d-flex justify-content-center gap-3 mb-5">
                    <button type="submit" class="btn btn-fifa-primary px-5 py-2 fw-bold fs-6">
                        <i class='bx bxs-paper-plane ms-1'></i> إرسال الخطاب الآن
                    </button>
                    <button type="button" onclick="downloadPDF()" class="btn btn-outline-success px-4 py-2 fw-bold">
                        <i class='bx bxs-file-pdf ms-1'></i> تحميل PDF
                    </button>
                </div>
            </form>
        </div>

        <!-- قائمة الخطابات الواردة -->
        <div class="col-lg-4">
            <div class="modern-card p-3">
                <h5 class="section-header"><i class='bx bxs-inbox text-success me-2'></i>الخطابات الواردة</h5>
                {% if letters %}
                <div class="list-group list-group-flush" style="max-height: 850px; overflow-y: auto;">
                    {% for l in letters %}
                    <div class="letter-item">
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <span class="fw-bold text-dark fs-7">{{ l.title }}</span>
                            <span class="badge bg-light text-dark border">{{ l.letter_number or l.id }}</span>
                        </div>
                        <div class="text-muted fs-8 mb-2">من: {{ l.sender_name or 'إدارة المكاتب' }} | {{ l.created_at }}</div>
                        <p class="text-secondary fs-8 mb-2 text-truncate">{{ l.content or '' }}</p>
                        <div class="d-flex gap-2">
                            {% if l.file_data %}
                            <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-primary fs-8"><i class='bx bx-download'></i> الملف</a>
                            {% endif %}
                            {% if current_dept.can_delete == 1 or is_admin %}
                            <a href="/delete_letter/{{ l.id }}" class="btn btn-sm btn-outline-danger fs-8" onclick="return confirm('هل أنت تأكد من الحذف؟')"><i class='bx bx-trash'></i></a>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="text-muted text-center py-4">لا توجد خطابات واردة حالياً.</p>
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        function downloadPDF() {
            const element = document.getElementById('paperToPdf');
            const opt = {
                margin:       0.3,
                filename:     'خطاب_رسمي_نادي_فيفا.pdf',
                image:        { type: 'jpeg', quality: 0.98 },
                html2canvas:  { scale: 2 },
                jsPDF:        { unit: 'in', format: 'a4', orientation: 'portrait' }
            };
            html2pdf().set(opt).from(element).save();
        }
    </script>
    '''
    return render_template_string(DASHBOARD_HTML.replace('{% block content %}{% endblock %}', content), 
                                 page_title="البريد الوارد والخطابات", active_page="inbox", letters=letters, departments=departments, current_dept=current_dept, is_admin=is_admin)

@app.route('/outbox')
def outbox():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    cursor.execute('SELECT * FROM departments ORDER BY name ASC')
    departments = cursor.fetchall()

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
    <div class="row g-4">
        <!-- قالب الورقة الرسمي A4 لإرسال خطاب جديد صادر -->
        <div class="col-lg-8">
            <form action="/send_official_letter" method="post" id="officialLetterFormOut">
                <div class="a4-paper-container">
                    <div class="a4-paper" id="paperToPdfOut">
                        <div>
                            <!-- هيدر الخطاب الرسمي[cite: 2] -->
                            <div class="letter-header-row">
                                <div class="header-right">
                                    المملكة العربية السعودية<br>
                                    وزارة الرياضة<br>
                                    فرع وزارة الرياضة بجازان<br>
                                    نادي فيفا الرياضي
                                </div>
                                <div class="header-center">
                                    <img src="/static/logo.png" alt="FIFA CLUB LOGO" onerror="this.src='https://via.placeholder.com/80?text=FIFA+CLUB'">
                                </div>
                                <div class="header-left">
                                    الرقم: <input type="text" name="letter_number" value="١٤٤٧ / {{ letters|length + 1 }}" required><br>
                                    التاريخ: <input type="text" name="created_at" value="''' + datetime.now().strftime('%Y/%m/%dم') + '''"><br>
                                    المشفوعات: <input type="text" value="-" style="width: 50px;">
                                </div>
                            </div>

                            <!-- محتوى وتفاصيل الخطاب الصادر -->
                            <div class="letter-body-editor">
                                <div class="mb-3 d-flex align-items-center">
                                    <span class="fw-bold me-2" style="color: var(--fifa-green-primary);">سعادة:</span>
                                    <select name="receiver_id" class="form-select letter-field-input" required>
                                        <option value="" disabled selected>-- اختر الإدارة المستلمة --</option>
                                        {% for d in departments %}
                                        <option value="{{ d.id }}">{{ d.name }}</option>
                                        {% endfor %}
                                    </select>
                                    <span class="fw-bold ms-2" style="color: var(--fifa-green-primary);">المحترم</span>
                                </div>

                                <div class="mb-3 d-flex align-items-center">
                                    <span class="fw-bold me-2" style="color: var(--fifa-green-primary);">عنوان الخطاب:</span>
                                    <input type="text" name="title" class="letter-field-input" style="width: 75%;" placeholder="أدخل موضوع/عنوان الخطاب الصادر..." required>
                                </div>

                                <div class="text-center fw-bold my-3" style="color: #333;">السلام عليكم ورحمة الله وبركاته ،، تحية طيبة وبعد،،</div>

                                <div class="mb-3">
                                    <textarea name="content" class="letter-textarea" placeholder="اكتب نص الخطاب والتفاصيل هنا..." required></textarea>
                                </div>

                                <div class="text-center fw-bold my-3" style="color: #333;">شاكرين ومقدرين حسن تعاونكم ،،</div>
                            </div>
                        </div>

                        <!-- فوتر الخطاب الرسمي[cite: 2] -->
                        <div class="letter-footer-stamp">
                            <div class="footer-info">
                                <i class='bx bx-envelope'></i> fifaclub1436@gmail.com<br>
                                <i class='bx bxl-twitter'></i> faifaclub1
                            </div>
                            <div class="signature-box">
                                {{ session.get('dept_name', '') }}<br><br>
                                <span class="text-muted fw-normal" style="font-size: 0.8rem;">(التوقيع الإلكتروني)</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- أزرار الإجراءات أسفل الورقة -->
                <div class="d-flex justify-content-center gap-3 mb-5">
                    <button type="submit" class="btn btn-fifa-primary px-5 py-2 fw-bold fs-6">
                        <i class='bx bxs-paper-plane ms-1'></i> إرسال الخطاب الصادر
                    </button>
                    <button type="button" onclick="downloadPDFOut()" class="btn btn-outline-success px-4 py-2 fw-bold">
                        <i class='bx bxs-file-pdf ms-1'></i> تحميل PDF
                    </button>
                </div>
            </form>
        </div>

        <!-- قائمة الخطابات الصادرة -->
        <div class="col-lg-4">
            <div class="modern-card p-3">
                <h5 class="section-header"><i class='bx bxs-paper-plane text-primary me-2'></i>الخطابات الصادرة</h5>
                {% if letters %}
                <div class="list-group list-group-flush" style="max-height: 850px; overflow-y: auto;">
                    {% for l in letters %}
                    <div class="letter-item">
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <span class="fw-bold text-dark fs-7">{{ l.title }}</span>
                            <span class="badge bg-light text-dark border">{{ l.letter_number or l.id }}</span>
                        </div>
                        <div class="text-muted fs-8 mb-2">إلى: {{ l.receiver_name or 'عام' }} | {{ l.created_at }}</div>
                        <p class="text-secondary fs-8 mb-2 text-truncate">{{ l.content or '' }}</p>
                        {% if l.file_data %}
                        <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-primary fs-8"><i class='bx bx-download'></i> الملف</a>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="text-muted text-center py-4">لا توجد خطابات صادر حالياً.</p>
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        function downloadPDFOut() {
            const element = document.getElementById('paperToPdfOut');
            const opt = {
                margin:       0.3,
                filename:     'خطاب_صادر_نادي_فيفا.pdf',
                image:        { type: 'jpeg', quality: 0.98 },
                html2canvas:  { scale: 2 },
                jsPDF:        { unit: 'in', format: 'a4', orientation: 'portrait' }
            };
            html2pdf().set(opt).from(element).save();
        }
    </script>
    '''
    return render_template_string(DASHBOARD_HTML.replace('{% block content %}{% endblock %}', content), 
                                 page_title="البريد الصادر والخطابات", active_page="outbox", letters=letters, departments=departments, current_dept=current_dept, is_admin=is_admin)

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

    cursor.execute('SELECT * FROM departments ORDER BY name ASC')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    cursor.close()
    conn.close()
    
    content = '''
    <div class="modern-card p-4">
        <h4 class="section-header"><i class='bx bxs-cloud-upload text-warning me-2'></i> رفع سريع للخطابات</h4>
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
            <div class="mb-4">
                <label class="form-label fw-bold">ارفاق ملف الخطاب</label>
                <input type="file" name="file" class="form-control" required>
            </div>
            <button type="submit" class="btn btn-fifa-primary px-4 py-2"><i class='bx bx-upload ms-1'></i> رفع وإرسال</button>
        </form>
    </div>
    '''
    return render_template_string(DASHBOARD_HTML.replace('{% block content %}{% endblock %}', content), 
                                 page_title="رفع سريع", active_page="quick_upload", departments=departments, current_dept=current_dept, is_admin=is_admin)
    
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

@app.route('/quick_upload', methods=['GET', 'POST'])
def quick_upload():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_page_quick_upload'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الوصول لصفحة الرفع الفوري."); window.location.href="/dashboard";</script>'''

    if request.method == 'POST':
        dept_id = session['dept_id']
        document_title = request.form.get('document_title')
        archive_category = request.form.get('archive_category')
        notes = request.form.get('notes', '')
        
        files = request.files.getlist('archive_files')
        uploaded_count = 0

        for file in files:
            if file and file.filename != '':
                original_name = secure_filename(file.filename)
                file_name = f"{int(datetime.now().timestamp())}_{original_name}"
                file_bytes = file.read()
                content_type = file.content_type or 'application/octet-stream'
                
                file_title = f"{document_title} - {original_name}" if len(files) > 1 else document_title
                
                cursor.execute('''
                    INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at, archive_dept_id)
                    VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s)
                ''', (
                    file_title, 
                    f"التصنيف: {archive_category} | ملاحظات: {notes}", 
                    "عادي", 
                    file_name, 
                    psycopg2.Binary(file_bytes),
                    content_type,
                    datetime.now().strftime('%Y-%m-%d %H:%M'),
                    dept_id
                ))
                uploaded_count += 1
                
        conn.commit()
        cursor.close()
        conn.close()
        
        if uploaded_count > 0:
            return f'''<script>alert("تم رفع وأرشفة {uploaded_count} ملف بنجاح إلى أرشيف الإدارة حصرياً!"); window.location.href="/archive";</script>'''
        else:
            return '''<script>alert("الرجاء التأكد من رفع الملفات بشكل صحيح."); window.location.href="/quick_upload";</script>'''
    
    cursor.close()
    conn.close()
    
    html_code = '''
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>رفع ملفات متعددة للأرشفة - نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green-primary: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
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
            .content-body { flex: 1; padding: 1.25rem; display: flex; align-items: center; justify-content: center; }
            .upload-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 16px; border: 1px solid #d5e2d8; box-shadow: 0 10px 30px rgba(18, 56, 38, 0.08); width: 100%; max-width: 650px; padding: 1.5rem; position: relative; }
            .btn-fifa-primary { background-color: var(--fifa-green-primary); color: #ffffff; border-radius: 10px; padding: 0.75rem; font-weight: 700; border: none; }
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
                        <span class="fw-bold fs-6 lh-1" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
                    </a>
                </div>
            </div>
        </nav>
        <div class="main-wrapper">
            <aside class="sidebar" id="sidebarMenu">
                <div class="d-flex justify-content-between align-items-center px-3 mb-2 d-lg-none">
                    <span class="fw-bold text-white">قائمة التنقل</span>
                    <button class="btn text-white fs-3 p-0" onclick="toggleSidebar()">&times;</button>
                </div>
                {% if current_dept['can_page_inbox'] == 1 or is_admin %}
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                {% endif %}
                {% if current_dept['can_page_outbox'] == 1 or is_admin %}
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                {% endif %}
                {% if current_dept['can_page_achievements'] == 1 or is_admin %}
                <a href="/monthly_achievements" class="sidebar-link"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                {% endif %}
                {% if current_dept['can_page_archive'] == 1 or is_admin %}
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                {% endif %}
                {% if current_dept['can_page_quick_upload'] == 1 or is_admin %}
                <a href="/quick_upload" class="sidebar-link active"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
                {% endif %}
                {% if is_admin %}
                <a href="/admin/dashboard" class="sidebar-link" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
                {% endif %}
                {% if current_dept['can_add_user'] == 1 or is_admin %}
                <a href="/register" class="sidebar-link"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
                {% endif %}
                <div class="border-top border-secondary my-3 opacity-25"></div>
                <a href="/logout" class="sidebar-link text-danger"><i class='bx bx-log-out text-danger'></i>تسجيل الخروج</a>
            </aside>
            <main class="content-body">
                <div class="upload-card">
                    <div class="text-center mb-4">
                        <h3 class="fw-bold fs-5" style="color: var(--fifa-green-primary);">رفع وتوثيق فوري (تظهر في أرشيف الإدارة فقط)</h3>
                    </div>
                    <form action="/quick_upload" method="post" enctype="multipart/form-data">
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">عنوان رئيسي للملفات المرفوعة</label>
                            <input type="text" name="document_title" required class="form-control py-2 fs-7" placeholder="مثال: فواتير وعقود قسم الصيانة">
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">تصنيف الأرشيف (تسجيل يدوي)</label>
                            <input type="text" name="archive_category" required class="form-control py-2 fs-7 bg-white" placeholder="أدخل تصنيف الأرشيف يدوياً...">
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">اختر الملفات</label>
                            <input type="file" name="archive_files" multiple required class="form-control fs-7">
                        </div>
                        <div class="mb-4">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">ملاحظات وصفية (اختياري)</label>
                            <textarea name="notes" rows="2" class="form-control fs-7" placeholder="أدخل تفاصيل..."></textarea>
                        </div>
                        <button type="submit" class="btn btn-fifa-primary w-100 shadow-sm py-2 fs-7">رفع وأرشفة الملفات الآن</button>
                    </form>
                </div>
            </main>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function toggleSidebar() {
                document.getElementById('sidebarMenu').classList.toggle('show-sidebar');
                document.getElementById('mobileOverlay').classList.toggle('active');
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_code, is_admin=is_admin, current_dept=current_dept)

@app.route('/monthly_achievements')
def monthly_achievements():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_page_achievements'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الوصول لصفحة إنجازات الشهر."); window.location.href="/dashboard";</script>'''
    
    can_view_all_ach = current_dept['can_view_all_achievements'] == 1 or is_admin

    if can_view_all_ach:
        cursor.execute('SELECT * FROM departments')
        depts = cursor.fetchall()
    else:
        cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
        depts = cursor.fetchall()
    
    cursor.execute('''
        SELECT ma.*, d.name as dept_name 
        FROM monthly_achievements ma
        JOIN departments d ON ma.dept_id = d.id
        ORDER BY ma.id DESC
    ''')
    achievements = cursor.fetchall()
    
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إنجازات الشهر - نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green-primary: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; --fifa-card-border: #d5e2d8; }
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
            .content-body { flex: 1; padding: 1.25rem; }
            .dept-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 12px; border: 1px solid #d5e2d8; box-shadow: 0 4px 12px rgba(0,0,0,0.03); margin-bottom: 1.5rem; }
            .dept-header { background-color: var(--fifa-green-primary); color: #fff; border-radius: 11px 11px 0 0; padding: 0.8rem 1rem; }
            .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; font-weight: 700; border: none; }
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
                        <span class="fw-bold fs-6 lh-1" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
                    </a>
                </div>
            </div>
        </nav>
        <div class="main-wrapper">
            <aside class="sidebar" id="sidebarMenu">
                <div class="d-flex justify-content-between align-items-center px-3 mb-2 d-lg-none">
                    <span class="fw-bold text-white">قائمة التنقل</span>
                    <button class="btn text-white fs-3 p-0" onclick="toggleSidebar()">&times;</button>
                </div>
                {% if current_dept['can_page_inbox'] == 1 or is_admin %}
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                {% endif %}
                {% if current_dept['can_page_outbox'] == 1 or is_admin %}
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                {% endif %}
                {% if current_dept['can_page_achievements'] == 1 or is_admin %}
                <a href="/monthly_achievements" class="sidebar-link active"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                {% endif %}
                {% if current_dept['can_page_archive'] == 1 or is_admin %}
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                {% endif %}
                {% if current_dept['can_page_quick_upload'] == 1 or is_admin %}
                <a href="/quick_upload" class="sidebar-link"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
                {% endif %}
                {% if is_admin %}
                <a href="/admin/dashboard" class="sidebar-link" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
                {% endif %}
                {% if current_dept['can_add_user'] == 1 or is_admin %}
                <a href="/register" class="sidebar-link"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
                {% endif %}
                <div class="border-top border-secondary my-3 opacity-25"></div>
                <a href="/logout" class="sidebar-link text-danger"><i class='bx bx-log-out text-danger'></i>تسجيل الخروج</a>
            </aside>
            <main class="content-body">
                <div class="container-fluid p-0">
                    <div class="mb-4">
                        <h4 class="fw-bold fs-5" style="color: var(--fifa-green-primary);"><i class='bx bxs-trophy ms-2' style="color: var(--fifa-gold);"></i>إنجازات الإدارات الشهرية</h4>
                    </div>
                    <div class="row">
                        {% for d in depts %}
                        <div class="col-lg-6">
                            <div class="dept-card">
                                <div class="dept-header d-flex flex-wrap justify-content-between align-items-center gap-2">
                                    <span class="fw-bold fs-7"><i class='bx bxs-folder-open ms-2' style="color: var(--fifa-gold);"></i>{{ d.name }}</span>
                                    <div class="d-flex gap-2">
                                        {% if is_admin or can_delete == 1 %}
                                            <a href="/admin/clear_monthly_files/{{ d.id }}" class="btn btn-sm btn-outline-light fs-8" onclick="return confirm('تأكيد تفريغ وأرشفة ملفات هذا الشهر ونقلها للأرشيف الخاص بالإدارة؟');">
                                                <i class='bx bx-archive-in ms-1'></i>تفريغ وأرشفة
                                            </a>
                                        {% endif %}
                                    </div>
                                </div>
                                <div class="p-3">
                                    <div class="list-group mb-3 fs-7" id="dept-files-{{ d.id }}">
                                        {% set ns = namespace(found=false) %}
                                        {% for a in achievements %}
                                            {% if a.dept_id == d.id %}
                                                {% set ns.found = true %}
                                                <div class="list-group-item d-flex justify-content-between align-items-center bg-transparent">
                                                    <div>
                                                        <i class='bx bxs-file-pdf text-danger fs-5 align-middle ms-1'></i>
                                                        <strong class="text-dark fs-7">{{ a.title }}</strong>
                                                        <span class="text-muted d-block fs-8">{{ a.uploaded_at }}</span>
                                                    </div>
                                                    <div>
                                                        <a href="/download_ach_file/{{ a.id }}" target="_blank" class="btn btn-sm btn-outline-success py-0 px-2 fs-8 dept-file-link">تنزيل</a>
                                                    </div>
                                                </div>
                                            {% endif %}
                                        {% endfor %}
                                        {% if not ns.found %}
                                            <div class="text-center py-3 text-muted fs-7">لا توجد ملفات مرفوعة.</div>
                                        {% endif %}
                                    </div>
                                    {% if session['dept_id'] == d.id or is_admin %}
                                    <form action="/upload_achievement" method="post" enctype="multipart/form-data" class="bg-white p-2 rounded border">
                                        <input type="hidden" name="dept_id" value="{{ d.id }}">
                                        <div class="d-flex flex-column flex-sm-row gap-2">
                                            <input type="text" name="title" class="form-control fs-8" placeholder="عنوان الإنجاز..." required>
                                            <input type="file" name="file" class="form-control fs-8" required>
                                            <button class="btn btn-fifa-gold fs-8 text-nowrap" type="submit">رفع</button>
                                        </div>
                                    </form>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                        {% endfor %}
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
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_code, depts=depts, achievements=achievements, is_admin=is_admin, can_delete=current_dept['can_delete'], current_dept=current_dept, dept_name=session.get('dept_name'), now=datetime.now())

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    is_admin = is_admin_user(session.get('dept_name'))
    if not is_admin:
        return '''<script>alert("عذراً، هذه الصفحة مخصصة للمسؤولين فقط."); window.location.href="/dashboard";</script>'''

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()

    if request.method == 'POST':
        title = request.form['title']
        content = request.form.get('content', '')
        file = request.files.get('file')
        
        file_name = None
        file_data = None
        file_mimetype = None

        if file and file.filename != '':
            original_name = secure_filename(file.filename)
            file_name = f"admin_{int(datetime.now().timestamp())}_{original_name}"
            file_data = psycopg2.Binary(file.read())
            file_mimetype = file.content_type or 'application/octet-stream'

        cursor.execute('''
            INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at, archive_dept_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (title, content, 'عادي', session['dept_id'], session['dept_id'], file_name, file_data, file_mimetype, datetime.now().strftime('%Y-%m-%d %H:%M'), session['dept_id']))
        
        conn.commit()
        cursor.close()
        conn.close()
        return '''<script>alert("تمت إضافة الملف بنجاح عبر لوحة التحكم!"); window.location.href="/admin/dashboard";</script>'''

    cursor.execute('SELECT * FROM letters ORDER BY id DESC')
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>لوحة التحكم الشاملة - نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green-primary: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; --fifa-card-border: #d5e2d8; }
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

            .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; font-size: 0.95rem; }
            .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
            .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
            .main-content { flex: 1; padding: 1.25rem; width: 100%; overflow-x: hidden; }
            .modern-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 12px; border: 1px solid var(--fifa-card-border); box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); }
            .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; font-weight: 700; border: none; border-radius: 6px; }
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
                        <span class="fw-bold fs-6 lh-1" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
                    </a>
                </div>
            </div>
        </nav>

        <div class="main-wrapper">
            <aside class="sidebar" id="sidebarMenu">
                <div class="d-flex justify-content-between align-items-center px-3 mb-2 d-lg-none">
                    <span class="fw-bold text-white">قائمة التنقل</span>
                    <button class="btn text-white fs-3 p-0" onclick="toggleSidebar()">&times;</button>
                </div>
                {% if current_dept['can_page_inbox'] == 1 or is_admin %}
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                {% endif %}
                {% if current_dept['can_page_outbox'] == 1 or is_admin %}
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                {% endif %}
                {% if current_dept['can_page_achievements'] == 1 or is_admin %}
                <a href="/monthly_achievements" class="sidebar-link"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                {% endif %}
                {% if current_dept['can_page_archive'] == 1 or is_admin %}
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                {% endif %}
                {% if current_dept['can_page_quick_upload'] == 1 or is_admin %}
                <a href="/quick_upload" class="sidebar-link"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
                {% endif %}
                {% if is_admin %}
                <a href="/admin/dashboard" class="sidebar-link active" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
                {% endif %}
                {% if current_dept['can_add_user'] == 1 or is_admin %}
                <a href="/register" class="sidebar-link"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
                {% endif %}
                <div class="border-top border-secondary my-3 opacity-25"></div>
                <a href="/logout" class="sidebar-link text-danger"><i class='bx bx-log-out text-danger'></i>تسجيل الخروج</a>
            </aside>

            <main class="main-content">
                <div class="modern-card p-3 p-md-4 mb-4">
                    <h5 class="fw-bold fs-6 mb-3" style="color: var(--fifa-green-primary);">رفع ملف جديد للقاعدة</h5>
                    <form action="/admin/dashboard" method="post" enctype="multipart/form-data">
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7">عنوان العنصر / الملف</label>
                            <input type="text" name="title" class="form-control fs-7" required placeholder="أدخل اسم أو عنوان الملف">
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7">اختر الملف المرفق</label>
                            <input type="file" name="file" class="form-control fs-7" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7">الوصف أو التفاصيل (اختياري)</label>
                            <textarea name="content" class="form-control fs-7" rows="3" placeholder="أدخل تفاصيل إضافية..."></textarea>
                        </div>
                        <button type="submit" class="btn btn-fifa-gold fs-7 py-2 px-4">رفع الملف وحفظه</button>
                    </form>
                </div>
                <div class="modern-card p-3">
                    <h5 class="fw-bold fs-6 mb-3 px-2">قائمة العناصر والملفات المسجلة</h5>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle mb-0 fs-7">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>العنوان</th>
                                    <th>الملف المرفق</th>
                                    <th>التاريخ</th>
                                    <th class="text-center">الإجراءات</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for item in items %}
                                <tr>
                                    <td>{{ loop.index }}</td>
                                    <td class="fw-bold text-dark">{{ item.title }}</td>
                                    <td>
                                        {% if item.file_data %}
                                            <a href="/view_letter_file/{{ item.id }}" target="_blank" class="btn btn-sm btn-success py-1 px-2 fs-8">فتح</a>
                                            <a href="/download_letter_file/{{ item.id }}" class="btn btn-sm btn-outline-success py-1 px-2 fs-8">تنزيل</a>
                                        {% else %}
                                            <span class="text-muted fs-8">لا يوجد ملف</span>
                                        {% endif %}
                                    </td>
                                    <td><span class="text-muted fs-8">{{ item.created_at }}</span></td>
                                    <td class="text-center">
                                        <a href="/delete_letter/{{ item.id }}" class="btn btn-sm btn-outline-danger py-1 px-2 fs-8" onclick="return confirm('حذف الملف؟');">حذف</a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
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
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_code, items=items, is_admin=is_admin, current_dept=current_dept)

@app.route('/admin/delete_department/<int:dept_id>')
def delete_department(dept_id):
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    if not is_admin_user(session.get('dept_name')):
        return '''<script>alert("عذراً، هذه الصفحة مخصصة للمسؤولين فقط."); window.location.href="/dashboard";</script>'''

    if session['dept_id'] == dept_id:
        return '''<script>alert("لا يمكنك حذف حساب الإدارة الخاص بك حالياً أثناء تسجيل الدخول به."); window.location.href="/admin/permissions";</script>'''

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM departments WHERE id = %s', (dept_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return f'''<script>alert("حدث خطأ أثناء حذف الحساب: {str(e)}"); window.location.href="/admin/permissions";</script>'''

    cursor.close()
    conn.close()
    return '''<script>alert("تم حذف المستخدم/الإدارة بنجاح!"); window.location.href="/admin/permissions";</script>'''

@app.route('/admin/permissions', methods=['GET', 'POST'])
def admin_permissions():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    is_admin = is_admin_user(session.get('dept_name'))
    if not is_admin:
        return '''<script>alert("عذراً، هذه الصفحة مخصصة للمسؤولين فقط."); window.location.href="/dashboard";</script>'''

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()

    if request.method == 'POST':
        dept_id = request.form.get('dept_id')
        can_view_all = 1 if f'can_view_all_archive_{dept_id}' in request.form else 0
        can_delete = 1 if f'can_delete_{dept_id}' in request.form else 0
        can_view_all_ach = 1 if f'can_view_all_achievements_{dept_id}' in request.form else 0
        can_add_user = 1 if f'can_add_user_{dept_id}' in request.form else 0
        
        can_page_inbox = 1 if f'can_page_inbox_{dept_id}' in request.form else 0
        can_page_outbox = 1 if f'can_page_outbox_{dept_id}' in request.form else 0
        can_page_achievements = 1 if f'can_page_achievements_{dept_id}' in request.form else 0
        can_page_archive = 1 if f'can_page_archive_{dept_id}' in request.form else 0
        can_page_quick_upload = 1 if f'can_page_quick_upload_{dept_id}' in request.form else 0

        cursor.execute('''
            UPDATE departments 
            SET can_view_all_archive = %s, can_delete = %s, can_view_all_achievements = %s, can_add_user = %s,
                can_page_inbox = %s, can_page_outbox = %s, can_page_achievements = %s, can_page_archive = %s, can_page_quick_upload = %s
            WHERE id = %s
        ''', (can_view_all, can_delete, can_view_all_ach, can_add_user, can_page_inbox, can_page_outbox, can_page_achievements, can_page_archive, can_page_quick_upload, dept_id))
        conn.commit()
        cursor.close()
        conn.close()
        return '''<script>alert("تم تحديث الصلاحيات بنجاح!"); window.location.href="/admin/permissions";</script>'''

    cursor.execute('SELECT * FROM departments ORDER BY id ASC')
    departments = cursor.fetchall()
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إدارة الصلاحيات - نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green-primary: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; --fifa-card-border: #d5e2d8; }
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

            .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; font-size: 0.95rem; }
            .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
            .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
            .main-content { flex: 1; padding: 1.25rem; width: 100%; overflow-x: hidden; }
            .modern-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-radius: 12px; border: 1px solid var(--fifa-card-border); box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); }
            .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; font-weight: 700; border: none; }
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
                        <span class="fw-bold fs-6 lh-1" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
                    </a>
                </div>
            </div>
        </nav>

        <div class="main-wrapper">
            <aside class="sidebar" id="sidebarMenu">
                <div class="d-flex justify-content-between align-items-center px-3 mb-2 d-lg-none">
                    <span class="fw-bold text-white">قائمة التنقل</span>
                    <button class="btn text-white fs-3 p-0" onclick="toggleSidebar()">&times;</button>
                </div>
                {% if current_dept['can_page_inbox'] == 1 or is_admin %}
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                {% endif %}
                {% if current_dept['can_page_outbox'] == 1 or is_admin %}
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                {% endif %}
                {% if current_dept['can_page_achievements'] == 1 or is_admin %}
                <a href="/monthly_achievements" class="sidebar-link"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                {% endif %}
                {% if current_dept['can_page_archive'] == 1 or is_admin %}
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                {% endif %}
                {% if current_dept['can_page_quick_upload'] == 1 or is_admin %}
                <a href="/quick_upload" class="sidebar-link"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
                {% endif %}
                {% if is_admin %}
                <a href="/admin/dashboard" class="sidebar-link" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link active"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
                {% endif %}
                {% if current_dept['can_add_user'] == 1 or is_admin %}
                <a href="/register" class="sidebar-link"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
                {% endif %}
                <div class="border-top border-secondary my-3 opacity-25"></div>
                <a href="/logout" class="sidebar-link text-danger"><i class='bx bx-log-out text-danger'></i>تسجيل الخروج</a>
            </aside>

            <main class="main-content">
                <div class="modern-card p-3 p-md-4">
                    <h5 class="fw-bold fs-6 mb-3" style="color: var(--fifa-green-primary);">إدارة صلاحيات الإدارات والصفحات</h5>
                    <div class="table-responsive">
                        <table class="table table-bordered align-middle fs-8">
                            <thead class="table-light">
                                <tr>
                                    <th>اسم الإدارة / القسم</th>
                                    <th class="text-center">حفظ الأرشيف</th>
                                    <th class="text-center">صلاحية الحذف</th>
                                    <th class="text-center">إضافة مستخدم</th>
                                    <th class="text-center">الوارد</th>
                                    <th class="text-center">الصادرة</th>
                                    <th class="text-center">الإنجازات</th>
                                    <th class="text-center">الأرشيف</th>
                                    <th class="text-center">الرفع الفوري</th>
                                    <th class="text-center">إجراء</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for dept in departments %}
                                <tr>
                                    <form action="/admin/permissions" method="post">
                                        <input type="hidden" name="dept_id" value="{{ dept.id }}">
                                        <td class="fw-bold text-dark text-nowrap">{{ dept.name }}</td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_view_all_archive_{{ dept.id }}" {{ 'checked' if dept.can_view_all_archive == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_delete_{{ dept.id }}" {{ 'checked' if dept.can_delete == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_add_user_{{ dept.id }}" {{ 'checked' if dept.can_add_user == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_page_inbox_{{ dept.id }}" {{ 'checked' if dept.get('can_page_inbox', 1) == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_page_outbox_{{ dept.id }}" {{ 'checked' if dept.get('can_page_outbox', 1) == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_page_achievements_{{ dept.id }}" {{ 'checked' if dept.get('can_page_achievements', 1) == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_page_archive_{{ dept.id }}" {{ 'checked' if dept.get('can_page_archive', 1) == 1 else '' }}>
                                        </td>
                                        <td class="text-center">
                                            <input class="form-check-input" type="checkbox" name="can_page_quick_upload_{{ dept.id }}" {{ 'checked' if dept.get('can_page_quick_upload', 1) == 1 else '' }}>
                                        </td>
                                        <td class="text-center text-nowrap">
                                            <button type="submit" class="btn btn-sm btn-success py-0 px-2">حفظ</button>
                                            <a href="/admin/delete_department/{{ dept.id }}" class="btn btn-sm btn-outline-danger py-0 px-1" onclick="return confirm('هل أنت متأكد من حذف حساب هذه الإدارة نهائياً؟');">حذف</a>
                                        </td>
                                    </form>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
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
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_code, departments=departments, is_admin=is_admin, current_dept=current_dept)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
