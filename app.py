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
            archive_dept_id INTEGER
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
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
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
        .letter-item { border-bottom: 1px solid #f0f4f2; padding: 1rem; }
        .letter-item:hover { background-color: rgba(244, 248, 246, 0.8); }
        .priority-badge { font-size: 0.75rem; padding: 4px 10px; border-radius: 20px; font-weight: 700; }
        .bg-fifa-green { background-color: var(--fifa-green-primary) !important; color: #fff; }
        .btn-fifa-primary { background-color: var(--fifa-green-primary); color: #ffffff; border-radius: 8px; padding: 0.6rem 1.2rem; font-weight: 700; border: none; }
        .btn-fifa-primary:hover { background-color: var(--fifa-green-light); color: #fff; }
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
                    <div class="d-flex gap-2">
                        {% if current_page == 'outbox' %}
                        <a href="/official_letter_editor" class="btn btn-outline-success fw-bold d-flex align-items-center gap-1 shadow-sm">
                            <i class='bx bxs-file-doc fs-5'></i> نموذج رد تقنية المعلومات المفتوح (صفحة كاملة)
                        </a>
                        {% endif %}
                        <button type="button" class="btn btn-fifa-primary d-flex align-items-center gap-2 shadow-sm" onclick="openNewLetterModal()">
                            <i class='bx bxs-paper-plane fs-5' style="color: var(--fifa-gold);"></i> إنشاء وإرسال خطاب جديد
                        </button>
                    </div>
                    {% endif %}
                </div>

                <div class="modern-card p-2 p-sm-3">
                    {% if letters %}
                        {% if current_page == 'archive' and (can_delete == 1 or is_admin) %}
                        <form id="bulkDeleteForm" action="/delete_selected_letters" method="post">
                            <input type="hidden" name="action_type" id="actionTypeInput" value="selected">
                            <div class="d-flex flex-wrap justify-content-between align-items-center bg-light p-2 rounded mb-3 gap-2 border">
                                <div class="form-check m-0">
                                    <input class="form-check-input" type="checkbox" id="selectAllCheckbox" onclick="toggleSelectAll(this)">
                                    <label class="form-check-label fw-bold fs-7 text-dark" for="selectAllCheckbox">تحديد الكل</label>
                                </div>
                                <div class="d-flex gap-2">
                                    <button type="button" class="btn btn-sm btn-outline-danger fs-7" onclick="submitBulkDelete('selected')">
                                        <i class='bx bx-trash ms-1'></i>حذف الملفات المحددة
                                    </button>
                                    <button type="button" class="btn btn-sm btn-danger fs-7 fw-bold" onclick="submitBulkDelete('all')">
                                        <i class='bx bx-trash-alt ms-1'></i>حذف كل الأرشيف
                                    </button>
                                </div>
                            </div>
                        {% endif %}

                        <div class="letters-list">
                            {% for letter in letters %}
                                <div class="letter-item d-flex flex-column flex-sm-row align-items-start justify-content-between gap-2">
                                    <div class="d-flex align-items-start gap-2 w-100">
                                        {% if current_page == 'archive' and (can_delete == 1 or is_admin) %}
                                            <input class="form-check-input letter-checkbox mt-2" type="checkbox" name="letter_ids" value="{{ letter.id }}" form="bulkDeleteForm">
                                        {% endif %}
                                        <i class='bx bxs-file-archive fs-3 text-success mt-1 d-none d-sm-block'></i>
                                        <div class="w-100">
                                            <div class="d-flex flex-wrap justify-content-between align-items-center mb-1 gap-1">
                                                <span class="fw-bold text-dark fs-6">{{ letter.title }}</span>
                                                <small class="text-muted fs-8">{{ letter.created_at.split(' ')[0] if letter.created_at else '' }}</small>
                                            </div>
                                            {% if letter.content %}<p class="text-secondary small mb-2" style="white-space: pre-line;">{{ letter.content }}</p>{% endif %}

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
                                        {% if letter.file_data %}
                                            <a href="/view_letter_file/{{ letter.id }}" target="_blank" class="btn btn-sm btn-success py-1 px-2 fs-7 shadow-sm">فتح بالموقع</a>
                                            <a href="/download_letter_file/{{ letter.id }}" class="btn btn-sm btn-outline-success py-1 px-2 fs-7">تحميل</a>
                                        {% endif %}
                                        
                                        {% if current_page == 'outbox' %}
                                            <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 fs-7" onclick="editLetter('{{ letter.id }}', '{{ letter.receiver_id }}', '{{ letter.title|e }}', '{{ letter.priority }}', '{{ (letter.content or '')|e }}')">تعديل وإعادة إرسال</button>
                                        {% endif %}

                                        <span class="priority-badge bg-fifa-green">{{ letter.priority }}</span>
                                        {% if can_delete == 1 or is_admin %}
                                            <a href="/delete_letter/{{ letter.id }}" class="btn btn-sm btn-outline-danger py-1 px-2 fs-7" onclick="return confirm('حذف المعاملة؟');">حذف</a>
                                        {% endif %}
                                    </div>
                                </div>
                            {% endfor %}
                        </div>

                        {% if current_page == 'archive' and (can_delete == 1 or is_admin) %}
                        </form>
                        {% endif %}

                    {% else %}
                        <div class="text-center py-5 text-muted"><p class="fs-7">لا توجد بيانات حالياً.</p></div>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>

    <!-- نافذة إرسال أو تعديل الخطاب (مودال) -->
    <div class="modal fade" id="sendLetterModal" tabindex="-1" aria-labelledby="sendLetterModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content modern-card border-0 shadow-lg">
                <div class="modal-header border-bottom px-4 py-3" style="background-color: var(--fifa-green-primary); color: #fff;">
                    <h5 class="modal-title fw-bold fs-6" id="sendLetterModalLabel"><i class='bx bxs-paper-plane ms-2' style="color: var(--fifa-gold);"></i><span id="modalTitleText">إنشاء وإرسال خطاب جديد</span></h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body p-3 p-md-4">
                    <form id="letterForm" action="/send_letter" method="post" enctype="multipart/form-data">
                        <input type="hidden" name="letter_id" id="editLetterId" value="">
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">إلى الإدارة (المستلم):</label>
                            <select name="receiver_id" id="receiverSelect" class="form-select fs-7" required>
                                <option value="" selected disabled>اختر الإدارة المستقبلة...</option>
                                {% for d in depts %}
                                    <option value="{{ d.id }}">{{ d.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">عنوان الخطاب (الموضوع):</label>
                            <input type="text" name="title" id="letterTitle" class="form-control fs-7" required placeholder="أدخل موضوع الخطاب...">
                        </div>
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">الأهمية:</label>
                                <select name="priority" id="letterPriority" class="form-select fs-7">
                                    <option value="عادي">عادي</option>
                                    <option value="عاجل">عاجل</option>
                                    <option value="سري للغاية">سري للغاية</option>
                                </select>
                            </div>
                            <div class="col-md-6 mb-3">
                                <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">المرفق (اختياري):</label>
                                <input type="file" name="file" class="form-control fs-7">
                            </div>
                        </div>
                        <div class="mb-4">
                            <label class="form-label fw-bold fs-7" style="color: var(--fifa-green-primary);">محتوى ووصف الخطاب:</label>
                            <textarea name="content" id="letterContent" class="form-control fs-7" rows="7" placeholder="اكتب تفاصيل ومحتوى الخطاب هنا..."></textarea>
                        </div>
                        <div class="d-flex justify-content-end gap-2">
                            <button type="button" class="btn btn-secondary fs-7 px-3" data-bs-dismiss="modal">إلغاء</button>
                            <button type="submit" class="btn btn-fifa-primary fs-7 px-4" id="submitBtnText">إرسال الخطاب</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function toggleSidebar() {
            document.getElementById('sidebarMenu').classList.toggle('show-sidebar');
            document.getElementById('mobileOverlay').classList.toggle('active');
        }

        function toggleSelectAll(source) {
            checkboxes = document.querySelectorAll('.letter-checkbox');
            for(var i=0, n=checkboxes.length; i<n; i++) {
                checkboxes[i].checked = source.checked;
            }
        }

        function openNewLetterModal() {
            document.getElementById('letterForm').reset();
            document.getElementById('editLetterId').value = '';
            document.getElementById('modalTitleText').innerText = 'إنشاء وإرسال خطاب جديد';
            document.getElementById('submitBtnText').innerText = 'إرسال الخطاب';
            var myModal = new bootstrap.Modal(document.getElementById('sendLetterModal'));
            myModal.show();
        }

        function editLetter(id, receiverId, title, priority, content) {
            document.getElementById('editLetterId').value = id;
            document.getElementById('receiverSelect').value = receiverId;
            document.getElementById('letterTitle').value = title;
            document.getElementById('letterPriority').value = priority;
            document.getElementById('letterContent').value = content;
            
            document.getElementById('modalTitleText').innerText = 'تعديل وإعادة إرسال الخطاب';
            document.getElementById('submitBtnText').innerText = 'حفظ وإعادة إرسال';
            var myModal = new bootstrap.Modal(document.getElementById('sendLetterModal'));
            myModal.show();
        }

        function submitBulkDelete(type) {
            document.getElementById('actionTypeInput').value = type;
            if (type === 'all') {
                if (confirm('تحذير شديد: هل أنت متأكد من حذف كافة الملفات الموجودة في الأرشيف نهائياً؟')) {
                    document.getElementById('bulkDeleteForm').submit();
                }
            } else {
                var checkedCount = document.querySelectorAll('.letter-checkbox:checked').length;
                if (checkedCount === 0) {
                    alert('الرجاء تحديد ملف واحد على الأقل للحذف.');
                    return;
                }
                if (confirm('هل أنت متأكد من حذف الملفات المحددة؟')) {
                    document.getElementById('bulkDeleteForm').submit();
                }
            }
        }
    </script>
</body>
</html>
'''

# --- صفحة محرر نموذج الخطاب الرسمي الكامل (كأنه ملف وورد مفتوح في الصفحة) ---
@app.route('/official_letter_editor')
def official_letter_editor():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = session['dept_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (dept_id,))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    cursor.execute('SELECT id, name FROM departments WHERE id != %s', (dept_id,))
    depts = cursor.fetchall()
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>نموذج الخطاب الرسمي - نادي فيفا الرياضي</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; }
            .top-navbar { background-color: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1rem; }
            .nav-logo { height: 42px; width: auto; object-fit: contain; }
            
            /* تصميم ورقة الوورد المفتوحة بالكامل داخل الصفحة */
            .word-document-container {
                max-width: 850px;
                margin: 30px auto;
                background: #ffffff;
                border: 2px solid var(--fifa-gold);
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(18, 56, 38, 0.1);
                padding: 50px;
                position: relative;
            }
            .editable-field {
                border: 1px dashed transparent;
                transition: all 0.2s;
                padding: 4px 8px;
                border-radius: 6px;
            }
            .editable-field:hover {
                border-color: var(--fifa-gold);
                background-color: rgba(197, 160, 89, 0.05);
            }
            .editable-field:focus {
                outline: none;
                border-color: var(--fifa-green);
                background-color: #fff;
                box-shadow: 0 0 0 3px rgba(18, 56, 38, 0.1);
            }
            .doc-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                border-bottom: 3px solid var(--fifa-green);
                padding-bottom: 20px;
                margin-bottom: 30px;
            }
            .doc-body-textarea {
                width: 100%;
                border: 1px dashed #d5e2d8;
                border-radius: 8px;
                padding: 20px;
                font-family: 'Almarai', sans-serif;
                font-size: 1.1rem;
                line-height: 2.3;
                color: var(--fifa-green);
                resize: vertical;
                min-height: 260px;
                background-color: #fafcfb;
            }
            .doc-body-textarea:focus {
                outline: none;
                border-color: var(--fifa-green);
                background-color: #fff;
                box-shadow: 0 0 0 3px rgba(18, 56, 38, 0.1);
            }
            .send-control-box {
                background: #f4f8f6;
                border-top: 2px solid #e2ece7;
                padding: 25px;
                margin-top: 40px;
                border-radius: 8px;
            }
        </style>
    </head>
    <body>

        <nav class="navbar top-navbar sticky-top">
            <div class="container-fluid">
                <a class="navbar-brand d-flex align-items-center gap-2 m-0" href="/outbox">
                    <img src="{{ url_for('static', filename='logo.png') }}" alt="نادي فيفا" class="nav-logo" onerror="this.style.display='none'">
                    <span class="fw-bold fs-6" style="color: var(--fifa-green);">نادي فيفا الرياضي - محرر الخطابات الرسمي</span>
                </a>
                <a href="/outbox" class="btn btn-sm btn-outline-secondary fw-bold">
                    <i class='bx bx-right-arrow-alt ms-1'></i> العودة للخطابات الصادرة
                </a>
            </div>
        </nav>

        <div class="container py-4">
            <form action="/send_official_custom_letter" method="post" id="officialLetterForm">
                <div class="word-document-container">
                    
                    <!-- رأس الخطاب الرسمي -->
                    <div class="doc-header">
                        <div>
                            <h6 class="fw-bold m-0" style="color: var(--fifa-green);">المملكة العربية السعودية</h6>
                            <h6 class="fw-bold m-0 text-muted">وزارة الرياضة</h6>
                            <h6 class="fw-bold m-0 text-muted">فرع وزارة الرياضة بجازان</h6>
                            <h6 class="fw-bold m-0" style="color: var(--fifa-gold);">نادي فيفا الرياضي</h6>
                        </div>
                        <div class="text-center">
                            <img src="{{ url_for('static', filename='logo.png') }}" alt="شعار النادي" style="max-height: 75px;" onerror="this.style.display='none'">
                        </div>
                        <div class="text-start">
                            <p class="mb-1 fs-7">الرقم: <input type="text" name="letter_number" value="---" class="editable-field d-inline-block w-50 text-center form-control-sm border"></p>
                            <p class="mb-1 fs-7">التاريخ: <input type="text" name="letter_date" value="{{ datetime.now().strftime('%Y/%m/%d') }} هـ" class="editable-field d-inline-block w-75 text-center form-control-sm border"></p>
                            <p class="mb-0 fs-7">المرفقات: <input type="text" name="attachments_count" value="بدون" class="editable-field d-inline-block w-50 text-center form-control-sm border"></p>
                        </div>
                    </div>

                    <!-- جهة الصادر إليه العنوان -->
                    <div class="mb-4">
                        <label class="form-label fw-bold fs-7 text-muted">عنوان وموجه إليه الخطاب:</label>
                        <input type="text" name="letter_subject_to" id="letterSubjectTo" class="form-control fw-bold fs-6" value="سعادة الرئيس التنفيذي" required>
                    </div>

                    <div class="mb-3">
                        <p class="fw-bold" style="color: var(--fifa-green);">السلام عليكم ورحمة الله وبركاته،</p>
                    </div>

                    <!-- عنوان الموضوع الأساسي -->
                    <div class="mb-3">
                        <label class="form-label fw-bold fs-7 text-muted">موضوع الخطاب الرئيسي:</label>
                        <input type="text" name="title" id="letterTitle" class="form-control fw-bold fs-6 border-success" value="رد تقنية المعلومات بشأن ملاحظات الامتثال" required>
                    </div>

                    <!-- محتوى الخطاب القابل للتعديل بالكامل كملف وورد -->
                    <div class="mb-4">
                        <label class="form-label fw-bold fs-7 text-muted">محتوى الخطاب (يمكنك التعديل، الحذف، والإضافة بحرية تامة):</label>
                        <textarea name="content" id="letterContent" class="doc-body-textarea" rows="8" required>إشارة إلى خطابكم الكريم بشأن ملاحظات عدم الامتثال خلال شهر أبريل، نود الإفادة بأنه تم الاطلاع على ما ورد من ملاحظات، والعمل على معالجتها، حيث تم تعزيز الالتزام بإجراءات النسخ الاحتياطي للبيانات، ومراجعة وتحديث صلاحيات المستخدمين بما يتناسب مع طبيعة مهامهم، والتأكيد على توثيق جميع الأعطال والحوادث التقنية في السجل الرسمي المعتمد.

كما تم اتخاذ الإجراءات التصحيحية اللازمة لضمان رفع مستوى الالتزام ومنع تكرار هذه الملاحظات مستقبلاً، وسيتم تزويد إدارة الحكومة والامتثال بتقرير يوضح ما تم اتخاذه خلال المدة المحددة.

شاكرين ومقدرين</textarea>
                    </div>

                    <!-- التوقيع والاعتماد -->
                    <div class="text-start mt-4 pt-3 border-top">
                        <p class="fw-bold mb-1" style="color: var(--fifa-green);">مدير تقنية المعلومات</p>
                        <input type="text" name="signer_name" class="editable-field fw-bold d-inline-block w-auto border-0 bg-transparent text-start" value="عيسى حسين الفيفي">
                    </div>

                    <!-- صندوق اختيار الإدارة وزر الإرسال -->
                    <div class="send-control-box">
                        <div class="row align-items-center">
                            <div class="col-md-7 mb-3 mb-md-0">
                                <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);"><i class='bx bxs-paper-plane ms-1'></i> اختر الإدارة المراد إرسال هذا الخطاب إليها:</label>
                                <select name="receiver_id" class="form-select fs-6 fw-bold border-success shadow-sm" required>
                                    <option value="" selected disabled>-- اضغط لاختيار الإدارة المستقبلة للخطاب --</option>
                                    {% for d in depts %}
                                        <option value="{{ d.id }}">{{ d.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="col-md-5 text-md-end">
                                <input type="hidden" name="priority" value="عاجل">
                                <button type="submit" class="btn btn-success btn-lg w-100 fw-bold shadow py-3" style="background-color: var(--fifa-green); border: none;">
                                    <i class='bx bx-send ms-2 fs-4 align-middle'></i> إرسال الخطاب الرسمي فوراً
                                </button>
                            </div>
                        </div>
                    </div>

                </div>
            </form>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''
    return render_template_string(html_code, depts=depts, datetime=datetime)

# --- مسار استقبال وحفظ الخطاب الرسمي المخصص المرسل من محرر الصفحة الكاملة ---
@app.route('/send_official_custom_letter', methods=['POST'])
def send_official_custom_letter():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    sender_id = session['dept_id']
    receiver_id = request.form.get('receiver_id')
    title = request.form.get('title')
    raw_content = request.form.get('content', '')
    letter_subject_to = request.form.get('letter_subject_to', 'سعادة الرئيس التنفيذي')
    signer_name = request.form.get('signer_name', 'مدير تقنية المعلومات')
    priority = request.form.get('priority', 'عاجل')
    
    # تنسيق المحتوى ليكون بصيغة خطاب رسمي مرتب متكامل
    formatted_content = f"إلى: {letter_subject_to}\nالسلام عليكم ورحمة الله وبركاته،\n\n{raw_content}\n\n{signer_name}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at)
        VALUES (%s, %s, %s, %s, %s, NULL, NULL, NULL, %s)
    ''', (title, formatted_content, priority, sender_id, receiver_id, datetime.now().strftime('%Y-%m-%d %H:%M')))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return '''<script>alert("تم إرسال الخطاب الرسمي بنجاح إلى الإدارة المحددة!"); window.location.href="/outbox";</script>'''

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
    letter_id = request.form.get('letter_id')
    receiver_id = request.form.get('receiver_id')
    title = request.form.get('title')
    priority = request.form.get('priority', 'عادي')
    content = request.form.get('content', '')
    
    file = request.files.get('file')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if letter_id and letter_id.isdigit():
        if file and file.filename != '':
            original_name = secure_filename(file.filename)
            file_name = f"{int(datetime.now().timestamp())}_{original_name}"
            file_data = psycopg2.Binary(file.read())
            file_mimetype = file.content_type or 'application/octet-stream'
            
            cursor.execute('''
                UPDATE letters 
                SET title = %s, content = %s, priority = %s, receiver_id = %s, file_name = %s, file_data = %s, file_mimetype = %s, created_at = %s
                WHERE id = %s AND sender_id = %s
            ''', (title, content, priority, receiver_id, file_name, file_data, file_mimetype, datetime.now().strftime('%Y-%m-%d %H:%M'), letter_id, sender_id))
        else:
            cursor.execute('''
                UPDATE letters 
                SET title = %s, content = %s, priority = %s, receiver_id = %s, created_at = %s
                WHERE id = %s AND sender_id = %s
            ''', (title, content, priority, receiver_id, datetime.now().strftime('%Y-%m-%d %H:%M'), letter_id, sender_id))
    else:
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

if __name__ == '__main__':
    app.run(debug=True)
