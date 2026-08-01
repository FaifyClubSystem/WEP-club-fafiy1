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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_certificates (
            id SERIAL PRIMARY KEY,
            dept_id INTEGER,
            title TEXT,
            file_name TEXT,
            file_data BYTEA,
            file_mimetype TEXT,
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

    conn.commit()
    cursor.close()
    conn.close()

init_db()

# --- مسارات التحميل والمعاينة لكل ملفات النظام ---

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

@app.route('/view_ach_file/<int:ach_id>')
def view_ach_file(ach_id):
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
            as_attachment=False,
            download_name=row['file_name'] or 'file'
        )
    return "الملف غير موجود", 404

@app.route('/download_cert_file/<int:cert_id>')
def download_cert_file(cert_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT file_name, file_data, file_mimetype FROM course_certificates WHERE id = %s', (cert_id,))
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

@app.route('/view_cert_file/<int:cert_id>')
def view_cert_file(cert_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT file_name, file_data, file_mimetype FROM course_certificates WHERE id = %s', (cert_id,))
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

@app.route('/upload_certificate', methods=['POST'])
def upload_certificate():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = request.form.get('dept_id')
    title = request.form.get('title')
    file = request.files.get('file')
    
    is_admin = is_admin_user(session.get('dept_name'))
    if str(session['dept_id']) != str(dept_id) and not is_admin:
        return '''<script>alert("غير مسموح لك برفع شهادات دورات لهذه الإدارة."); window.location.href="/monthly_achievements";</script>'''
    
    if file and file.filename != '':
        original_name = secure_filename(file.filename)
        file_name = f"cert_{int(datetime.now().timestamp())}_{original_name}"
        file_bytes = file.read()
        file_mimetype = file.content_type or 'application/octet-stream'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO course_certificates (dept_id, title, file_name, file_data, file_mimetype, uploaded_at)
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

    cursor.execute('SELECT * FROM course_certificates WHERE dept_id = %s', (dept_id,))
    certs = cursor.fetchall()
    for cert in certs:
        cursor.execute('''
            INSERT INTO letters (title, content, priority, sender_id, receiver_id, file_name, file_data, file_mimetype, created_at, archive_dept_id)
            VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s)
        ''', (
            f"أرشيف شهادات دورات: {cert['title']}",
            f"تمت الأرشفة التلقائية من قسم شهادات الدورات بتاريخ: {current_time}",
            "عادي",
            cert['file_name'],
            cert.get('file_data'),
            cert.get('file_mimetype'),
            current_time,
            dept_id
        ))
    
    cursor.execute('DELETE FROM monthly_achievements WHERE dept_id = %s', (dept_id,))
    cursor.execute('DELETE FROM course_certificates WHERE dept_id = %s', (dept_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    return '''<script>alert("تم تفريغ وأرشفة الإنجازات وشهادات الدورات للإدارة بنجاح إلى أرشيفها الخاص!"); window.location.href="/monthly_achievements";</script>'''

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
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Almarai:wght@300;400;700;800&family=Aref+Ruqaa:wght@400;700&family=Cairo:wght@400;700&family=Changa:wght@400;700&display=swap" rel="stylesheet">
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
 
        /* ================= ورقة خطاب Word رسمية مقاس A4 حقيقي مع أدوات التحكّم بالخط ================= */
        .paper-toolbar {
            background: #ffffff;
            border: 1px solid #c8d6cd;
            border-bottom: none;
            border-radius: 10px 10px 0 0;
            padding: 8px 12px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 6px;
            width: 210mm;
            max-width: 100%;
            margin: 0 auto;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            box-sizing: border-box;
        }
        .paper-toolbar button, .paper-toolbar select, .paper-toolbar input[type="color"] {
            border: 1px solid #d5e2d8;
            background: #f8faf9;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 0.85rem;
            font-weight: bold;
            color: #123826;
            cursor: pointer;
            transition: all 0.2s;
        }
        .paper-toolbar button:hover {
            background: #123826;
            color: #ffffff;
        }
        .word-paper-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 2rem;
            overflow-x: auto;
            padding-bottom: 8px;
        }
        /* مقاس A4 الحقيقي: 210مم × 297مم، تماماً مثل صفحة الوورد */
        .word-paper {
            background: #ffffff;
            width: 210mm;
            min-height: 297mm;
            max-width: 210mm;
            padding: 18mm 20mm 32mm 20mm;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border: 1px solid #c8d6cd;
            border-radius: 0 0 4px 4px;
            position: relative;
            font-family: 'Amiri', 'Traditional Arabic', serif;
            color: #000;
            line-height: 1.8;
            box-sizing: border-box;
            flex-shrink: 0;
        }
        @media (max-width: 860px) {
            .word-paper, .paper-toolbar { width: 100%; min-width: 210mm; }
        }
        .word-paper-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 2.5rem;
            line-height: 1.4;
        }
        .word-paper-right {
            text-align: right;
            font-size: 1.15rem;
            font-weight: bold;
            color: #000;
            flex: 1;
        }
        .word-paper-center {
            text-align: center;
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .word-paper-center img {
            max-height: 85px;
            width: auto;
            object-fit: contain;
            margin-bottom: 2px;
        }
        .word-paper-center .brand-name-sub {
            font-weight: 800;
            font-size: 1.3rem;
            color: #000;
            letter-spacing: 1px;
            font-family: Arial, sans-serif;
            text-transform: uppercase;
        }
        .word-paper-left {
            text-align: right;
            font-size: 1.05rem;
            font-weight: bold;
            color: #000;
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }
        .word-paper-left-inner {
            text-align: right;
            min-width: 180px;
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
        /* منطقة نص الخطاب القابلة للكتابة والتكبير والتصغير */
        .word-paper-body {
            font-size: 1.15rem;
            text-align: justify;
            text-justify: inter-word;
            margin-bottom: 2rem;
            min-height: 250px;
            outline: none;
            padding: 8px;
            border: 1px dashed transparent;
            border-radius: 6px;
            transition: border 0.2s;
        }
        .word-paper-body:hover, .word-paper-body:focus {
            border-color: #c5a059;
            background-color: #fafcfb;
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
        /* تذييل الورقة: صف بيانات التواصل + شريط الموجة المستخرج من النموذج الرسمي */
        .word-paper-footer {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
        }
        .word-paper-contacts {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 14px;
            direction: ltr;
            font-size: 0.92rem;
            color: #1c1c1c;
            font-family: Arial, sans-serif;
            font-weight: bold;
            padding-bottom: 6px;
        }
        .word-paper-contacts span {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .word-paper-contacts i {
            font-size: 1.05rem;
            color: var(--fifa-green-primary);
        }
        .word-paper-wave-img {
            display: block;
            width: 100%;
            height: auto;
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
 
        /* نافذة معاينة الخطاب A4 */
        #previewLetterModal .modal-body {
            background: #6b6f70;
            display: flex;
            justify-content: center;
            padding: 24px 10px;
            overflow: auto;
            max-height: 85vh;
        }
        #previewLetterContainer .word-paper {
            box-shadow: 0 15px 40px rgba(0,0,0,0.35);
        }
        #previewLetterContainer input {
            border: none !important;
            background: transparent !important;
            pointer-events: none;
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
                    <div class="d-flex gap-2 flex-wrap">
                        <button type="button" class="btn btn-outline-dark d-flex align-items-center gap-2 shadow-sm fw-bold" onclick="previewLetterPaper()">
                            <i class='bx bx-show fs-5'></i> معاينة الخطاب
                        </button>
                        <button type="button" class="btn btn-danger d-flex align-items-center gap-2 shadow-sm fw-bold" onclick="downloadLetterPDF()">
                            <i class='bx bxs-file-pdf fs-5'></i> تحميل PDF
                        </button>
                    </div>
                    {% endif %}
                </div>
 
                {% if current_page == 'outbox' or current_page == 'inbox' %}
                <!-- ============ ورقة الخطاب الرسمية المباشرة مع شريط التنسيق ============ -->
                <div class="word-paper-container">
                    
                    <!-- شريط أدوات التنسيق وتكبير/تصغير الخط للنص المحدد -->
                    <div class="paper-toolbar">
                        <span class="fw-bold fs-8 text-muted me-1"><i class='bx bx-font'></i> تنسيق الخط المحدد:</span>
                        <button type="button" onclick="changeFontSize(1)" title="تكبير النص المحدد"><i class='bx bx-font-plus fs-6'></i> A+</button>
                        <button type="button" onclick="changeFontSize(-1)" title="تصغير النص المحدد"><i class='bx bx-font-minus fs-6'></i> A-</button>
                        <span id="currentFontSizeLabel" class="badge bg-light text-dark border fs-8">18px</span>
                        
                        <div class="vr mx-1"></div>
 
                        <select id="fontFamilySelect" onchange="changeFontFamily(this.value)" title="نوع الخط">
                            <option value="'Amiri', serif">خط الأميري النسخي</option>
                            <option value="'Almarai', sans-serif">خط المراعي العادي</option>
                            <option value="'Aref Ruqaa', serif">خط الرقعة</option>
                            <option value="'Cairo', sans-serif">خط كايرو</option>
                            <option value="'Changa', sans-serif">خط شانغا</option>
                        </select>
 
                        <div class="vr mx-1"></div>
 
                        <button type="button" onclick="formatDoc('bold')" title="تغميق (Bold)"><i class='bx bx-bold fs-6'></i></button>
                        <button type="button" onclick="formatDoc('underline')" title="تحته خط"><i class='bx bx-underline fs-6'></i></button>
                        <input type="color" id="textColorPicker" onchange="formatDoc('foreColor', this.value)" title="لون الخط" style="width: 32px; height: 28px; padding: 2px;">
 
                        <div class="vr mx-1"></div>
 
                        <button type="button" onclick="formatDoc('justifyRight')" title="محاذاة لليمين"><i class='bx bx-align-right fs-6'></i></button>
                        <button type="button" onclick="formatDoc('justifyCenter')" title="محاذاة للوسط"><i class='bx bx-align-middle fs-6'></i></button>
                        <button type="button" onclick="formatDoc('justifyLeft')" title="محاذاة لليصار"><i class='bx bx-align-left fs-6'></i></button>
                        <button type="button" onclick="formatDoc('justifyFull')" title="ضبط المحاذاة"><i class='bx bx-align-justify fs-6'></i></button>
 
                        <div class="vr mx-1"></div>
 
 
                    </div>
 
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
                                
                            </div>
                            <div class="word-paper-left">
                                <div class="word-paper-left-inner">
                                    الرقم : <input type="text" id="paperLetterNumInput" class="" value="" style="width: 100px;"><br>
                                    التاريخ : <input type="text" id="paperLetterDateInput" class="" value="{{ now.strftime('%Y/%m/%dم') }}" style="width: 100px;"><br>
                                    المشفوعات : <input type="text" id="paperLetterAttachInput" class="" value="" style="width: 100px;">
                                </div>
                            </div>
                        </div>
 
                    
 
                        <!-- نص الخطاب المباشر القابل للتعديل والتكبير والتصغير للكتابة المباشرة -->
                        <div class="word-paper-body" id="paperBodyText" contenteditable="true" oninput="syncTextareaWithPaper()">
 
                        </div>
 
                       
 
                        
 
                        <div class="word-paper-footer">
                            <div class="word-paper-contacts">
                                <span><i class='bx bx-envelope'></i> fifaclub1436@gmail.com</span>
                                <i class='bx bxl-tiktok'></i>
                                <i class='bx bxl-twitter'></i>
                                <i class='bx bxl-instagram'></i>
                                <span>faifaclub1</span>
                            </div>
                            <img class="word-paper-wave-img" src="{{ url_for('static', filename='footer_wave.png') }}" alt="">
                        </div>
                    </div>
                </div>
 
                <!-- ============ نموذج أسفل ورقة الخطاب لتحديد البيانات والإرسال ============ -->
                <div class="modern-card p-4 mb-4">
                    <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-paper-plane ms-1'></i> تفاصيل إرسال المعاملة / الخطاب</h5>
                    <form id="letterSendForm" action="/send_letter" method="post" enctype="multipart/form-data">
                        <input type="hidden" name="letter_id" id="editLetterId" value="">
                        <div class="row g-3">
                            <div class="col-md-6">
                                <label class="form-label fw-bold fs-7">الإدارة المستلمة:</label>
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
                                <label class="form-label fw-bold fs-7">صيغة ومحتوى الخطاب (مرتبط بالورقة أعلاه):</label>
                                <textarea name="content" id="letterContentInput" class="form-control fs-7" rows="5" placeholder="اكتب صيغة الخطاب هنا أو اكتبها مباشرة في الورقة أعلاه..." oninput="syncPaperWithTextarea(this.value)"></textarea>
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
                                            {% if letter.content %}<p class="text-secondary small mb-2" id="letter-text-{{ letter.id }}">{{ letter.content }}</p>{% endif %}
 
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
                                    
                                    <div class="d-flex align-items-center gap-2 w-100 justify-content-end mt-2 mt-sm-0 flex-wrap">
                                        {% if current_page == 'inbox' or current_page == 'outbox' %}
                                            <button type="button" class="btn btn-sm btn-outline-dark py-1 px-2 fs-7" onclick='previewSavedLetter(this)' data-title="{{ letter.title }}" data-content="{{ letter.content or '' }}" data-date="{{ letter.created_at.split(' ')[0] if letter.created_at else '' }}" data-number="{{ letter.letter_number or '' }}">
                                                <i class='bx bx-show ms-1'></i> معاينة الخطاب
                                            </button>
                                            <button type="button" class="btn btn-sm btn-outline-primary py-1 px-2 fs-7" onclick='loadLetterToEditor("{{ letter.id }}", {{ letter.title|tojson }}, "{{ letter.receiver_id if current_page == "outbox" else letter.sender_id }}", "{{ letter.priority }}")'>
                                                <i class='bx bx-edit ms-1'></i> تعديل / إرسال
                                            </button>
                                        {% endif %}
 
                                        {% if letter.file_data %}
                                            <button type="button" class="btn btn-sm btn-info py-1 px-2 fs-7 text-white" onclick="previewFile('/view_letter_file/{{ letter.id }}', '{{ letter.title }}')">
                                                <i class='bx bx-show ms-1'></i> معاينة الملف
                                            </button>
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
 
                        {% if current_page == 'archive' and (can_delete == 1 or is_admin) %}
                        </form>
                        {% endif %}
 
                    {% else %}
                        <div class="text-center py-5 text-muted"><p class="fs-7">لا توجد خطابات حالياً.</p></div>
                    {% endif %}
                </div>
            </div>
        </main>
    </div>
 
    <!-- نافذة معاينة الملفات الموحدة Modal -->
    <div class="modal fade" id="previewFileModal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-xl modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header bg-dark text-white py-2">
            <h6 class="modal-title fw-bold" id="previewFileTitle">معاينة المستند</h6>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body p-0" style="height: 80vh; background: #525659;">
            <iframe id="previewFrame" src="" style="width:100%; height:100%; border:none;"></iframe>
          </div>
        </div>
      </div>
    </div>
 
    <!-- نافذة معاينة الخطاب نفسه (مقاس A4) قبل الطباعة أو التحميل -->
    <div class="modal fade" id="previewLetterModal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-xl modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header bg-dark text-white py-2">
            <h6 class="modal-title fw-bold"><i class='bx bx-show ms-1'></i> معاينة الخطاب (مقاس A4)</h6>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <div id="previewLetterContainer"></div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إغلاق</button>
            <button type="button" class="btn btn-danger fw-bold" onclick="downloadLetterPDF()"><i class='bx bxs-file-pdf ms-1'></i> تحميل PDF</button>
          </div>
        </div>
      </div>
    </div>
 
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // دالة تنفيذ تنسيقات النص العامة
        function formatDoc(cmd, value = null) {
            document.execCommand(cmd, false, value);
            syncTextareaWithPaper();
        }
 
        // دالة تكبير وتصغير حجم الخط للنص المحدد فقط
        function changeFontSize(step) {
            var selection = window.getSelection();
            if (!selection.rangeCount) return;
 
            var range = selection.getRangeAt(0);
            var paperBody = document.getElementById('paperBodyText');
 
            if (!paperBody.contains(range.commonAncestorContainer)) {
                alert('يرجى تحديد النص المراد تكبيره أو تصغيره داخل ورقة الخطاب أولاً.');
                return;
            }
 
            if (range.collapsed) {
                // إذا لم يحدد نصاً معيناً، يطبق التغيير على حاوية الخطاب بالكامل
                var currentSize = parseInt(window.getComputedStyle(paperBody).fontSize) || 18;
                var newSize = currentSize + (step * 2);
                if (newSize >= 10 && newSize <= 50) {
                    paperBody.style.fontSize = newSize + 'px';
                    document.getElementById('currentFontSizeLabel').innerText = newSize + 'px';
                }
            } else {
                // تكبير/تصغير النص المحدد فقط عبر عنصر span
                var span = document.createElement('span');
                var selectedElement = range.commonAncestorContainer.parentElement;
                
                var currentSize = 18;
                if (selectedElement && selectedElement !== paperBody && selectedElement.style.fontSize) {
                    currentSize = parseInt(selectedElement.style.fontSize);
                } else {
                    currentSize = parseInt(window.getComputedStyle(paperBody).fontSize) || 18;
                }
 
                var newSize = currentSize + (step * 2);
                if (newSize < 10) newSize = 10;
                if (newSize > 50) newSize = 50;
 
                span.style.fontSize = newSize + 'px';
                span.appendChild(range.extractContents());
                range.insertNode(span);
                
                document.getElementById('currentFontSizeLabel').innerText = newSize + 'px';
            }
            syncTextareaWithPaper();
        }
 
        // دالة تغيير نوع الخط للنص المحدد
        function changeFontFamily(fontFamily) {
            var selection = window.getSelection();
            if (!selection.rangeCount) return;
 
            var range = selection.getRangeAt(0);
            var paperBody = document.getElementById('paperBodyText');
 
            if (range.collapsed) {
                paperBody.style.fontFamily = fontFamily;
            } else {
                var span = document.createElement('span');
                span.style.fontFamily = fontFamily;
                span.appendChild(range.extractContents());
                range.insertNode(span);
            }
            syncTextareaWithPaper();
        }
 
        // المزامنة بين نص الورقة ونموذج الإرسال بالأسفل
        function syncTextareaWithPaper() {
            var paperBody = document.getElementById('paperBodyText');
            var textarea = document.getElementById('letterContentInput');
            if (paperBody && textarea) {
                textarea.value = paperBody.innerText;
            }
        }
 
        function syncPaperWithTextarea(val) {
            var paperBody = document.getElementById('paperBodyText');
            if (paperBody) {
                paperBody.innerText = val.trim() !== '' ? val : "أدخل نص الخطاب...";
            }
        }
 
        function previewFile(url, title) {
            document.getElementById('previewFileTitle').innerText = 'معاينة: ' + title;
            document.getElementById('previewFrame').src = url;
            var modal = new bootstrap.Modal(document.getElementById('previewFileModal'));
            modal.show();
        }
 
        // تحويل نسخة من ورقة الخطاب إلى نسخة جاهزة للطباعة/PDF (استبدال حقول الإدخال بنصوص ثابتة)
        function buildPdfReadyClone(sourceEl) {
            var clone = sourceEl.cloneNode(true);
            clone.removeAttribute('id');
            clone.querySelectorAll('input').forEach(function (inp) {
                var span = document.createElement('span');
                span.innerText = inp.value || '';
                span.style.fontWeight = 'bold';
                inp.parentNode.replaceChild(span, inp);
            });
            return clone;
        }
 
        // معاينة الخطاب الرسمي بمقاس A4 داخل نافذة منبثقة قبل الطباعة/التحميل (الورقة الحالية قيد التحرير)
        function previewLetterPaper() {
            var original = document.getElementById('officialPaper');
            var clone = buildPdfReadyClone(original);
 
            var container = document.getElementById('previewLetterContainer');
            container.innerHTML = '';
            clone.id = 'previewOfficialPaper';
            container.appendChild(clone);
 
            var modalEl = document.getElementById('previewLetterModal');
            var modal = new bootstrap.Modal(modalEl);
            modal.show();
 
            setTimeout(function () {
                scaleClonedPaperToFit(clone, modalEl);
            }, 150);
        }
 
        // معاينة خطاب محفوظ سابقاً (من الوارد أو الصادر) بنفس شكل الورقة الرسمية دون التأثير على المحرر الحالي
        function previewSavedLetter(btn) {
            var title = btn.getAttribute('data-title') || '';
            var content = btn.getAttribute('data-content') || '';
            var date = btn.getAttribute('data-date') || '';
            var number = btn.getAttribute('data-number') || '';
 
            var original = document.getElementById('officialPaper');
            var clone = original.cloneNode(true);
            clone.removeAttribute('id');
 
            clone.querySelectorAll('input').forEach(function (inp) {
                var span = document.createElement('span');
                if (inp.id === 'paperLetterNumInput') {
                    span.innerText = number;
                } else if (inp.id === 'paperLetterDateInput') {
                    span.innerText = date;
                } else {
                    span.innerText = inp.value || '';
                }
                span.style.fontWeight = 'bold';
                inp.parentNode.replaceChild(span, inp);
            });
 
            var body = clone.querySelector('.word-paper-body');
            if (body) { body.innerText = content; }
 
            var container = document.getElementById('previewLetterContainer');
            container.innerHTML = '';
            clone.id = 'previewOfficialPaper';
            container.appendChild(clone);
 
            var modalEl = document.getElementById('previewLetterModal');
            var modal = new bootstrap.Modal(modalEl);
            modal.show();
 
            setTimeout(function () {
                scaleClonedPaperToFit(clone, modalEl);
            }, 150);
        }
 
        function scaleClonedPaperToFit(clone, modalEl) {
            var modalBodyWidth = modalEl.querySelector('.modal-body').clientWidth - 20;
            var paperWidthPx = clone.getBoundingClientRect().width;
            var scale = Math.min(1, modalBodyWidth / paperWidthPx);
            clone.style.transform = 'scale(' + scale + ')';
            clone.style.transformOrigin = 'top center';
            clone.style.marginBottom = (paperWidthPx * (scale - 1)) + 'px';
        }
 
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
 
        function updateReceiverTitle(selectElem) {
            var selectedOption = selectElem.options[selectElem.selectedIndex];
            var deptName = selectedOption.getAttribute('data-name');
        }
 
        // تحميل خطاب سابق (وارد أو صادر) في نموذج التحرير مع الحفاظ على رقم الخطاب والمستلم الصحيح
        function loadLetterToEditor(id, title, receiverId, priority) {
            var textElem = document.getElementById('letter-text-' + id);
            var content = textElem ? textElem.innerText : '';
 
            document.getElementById('editLetterId').value = id;
            document.getElementById('letterTitleInput').value = title;
            document.getElementById('letterContentInput').value = content;
            document.getElementById('letterPriority').value = priority;
 
            var receiverSelect = document.getElementById('receiverSelect');
            if (receiverSelect && receiverId) {
                receiverSelect.value = receiverId;
            }
 
            syncPaperWithTextarea(content);
 
            var paperBody = document.getElementById('officialPaper');
            if (paperBody) {
                paperBody.scrollIntoView({ behavior: 'smooth' });
            }
        }
 
        // تصدير الخطاب إلى PDF بجودة عالية مع دعم صحيح للنص العربي (لا يظهر ملخبطاً)
        function exportElementToPDF(sourceEl, filename) {
            var clone = buildPdfReadyClone(sourceEl);
            clone.style.boxShadow = 'none';
            clone.style.transform = 'none';
            clone.style.margin = '0';
 
            var holder = document.createElement('div');
            holder.style.position = 'fixed';
            holder.style.top = '0';
            holder.style.left = '-99999px';
            holder.appendChild(clone);
            document.body.appendChild(holder);
 
            var opt = {
                margin: 0,
                filename: filename,
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 3, useCORS: true, allowTaint: true, foreignObjectRendering: true },
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
            };
 
            function runExport() {
                html2pdf().set(opt).from(clone).save().then(function () {
                    document.body.removeChild(holder);
                }).catch(function () {
                    document.body.removeChild(holder);
                });
            }
 
            if (document.fonts && document.fonts.ready) {
                document.fonts.ready.then(runExport);
            } else {
                runExport();
            }
        }
 
        function downloadLetterPDF() {
            var previewClone = document.getElementById('previewOfficialPaper');
            var source = previewClone || document.getElementById('officialPaper');
            exportElementToPDF(source, 'خطاب_رسمي_نادي_فيفا.pdf');
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
 
        window.addEventListener('DOMContentLoaded', function() {
            syncTextareaWithPaper();
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

    cursor.execute('''
        SELECT cc.*, d.name as dept_name 
        FROM course_certificates cc
        JOIN departments d ON cc.dept_id = d.id
        ORDER BY cc.id DESC
    ''')
    certificates = cursor.fetchall()
    
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إنجازات وشهادات الدورات - نادي فيفا</title>
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
            .sub-section-title { font-weight: 700; font-size: 0.85rem; color: var(--fifa-green-primary); border-bottom: 2px solid var(--fifa-gold); padding-bottom: 3px; margin-bottom: 10px; }
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
                        <h4 class="fw-bold fs-5" style="color: var(--fifa-green-primary);"><i class='bx bxs-trophy ms-2' style="color: var(--fifa-gold);"></i>إنجازات وشهادات دورات الإدارات</h4>
                    </div>
                    <div class="row">
                        {% for d in depts %}
                        <div class="col-lg-6">
                            <div class="dept-card">
                                <div class="dept-header d-flex flex-wrap justify-content-between align-items-center gap-2">
                                    <span class="fw-bold fs-7"><i class='bx bxs-folder-open ms-2' style="color: var(--fifa-gold);"></i>{{ d.name }}</span>
                                    <div class="d-flex gap-2">
                                        {% if is_admin or can_delete == 1 %}
                                            <a href="/admin/clear_monthly_files/{{ d.id }}" class="btn btn-sm btn-outline-light fs-8" onclick="return confirm('تأكيد تفريغ وأرشفة الإنجازات والشهادات لهذا الشهر ونقلها لأرشيف الإدارة؟');">
                                                <i class='bx bx-archive-in ms-1'></i>تفريغ وأرشفة
                                            </a>
                                        {% endif %}
                                    </div>
                                </div>
                                <div class="p-3">
                                    <div class="sub-section-title"><i class='bx bxs-award ms-1'></i> ملفات الإنجازات الشهرية</div>
                                    <div class="list-group mb-3 fs-7" id="dept-files-{{ d.id }}">
                                        {% set ns = namespace(found=false) %}
                                        {% for a in achievements %}
                                            {% if a.dept_id == d.id %}
                                                {% set ns.found = true %}
                                                <div class="list-group-item d-flex justify-content-between align-items-center bg-transparent p-2">
                                                    <div>
                                                        <i class='bx bxs-file-pdf text-danger fs-5 align-middle ms-1'></i>
                                                        <strong class="text-dark fs-7">{{ a.title }}</strong>
                                                        <span class="text-muted d-block fs-8">{{ a.uploaded_at }}</span>
                                                    </div>
                                                    <div class="d-flex gap-1">
                                                        <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_ach_file/{{ a.id }}', '{{ a.title }}')">معاينة</button>
                                                        <a href="/download_ach_file/{{ a.id }}" target="_blank" class="btn btn-sm btn-outline-success py-0 px-2 fs-8">تنزيل</a>
                                                    </div>
                                                </div>
                                            {% endif %}
                                        {% endfor %}
                                        {% if not ns.found %}
                                            <div class="text-center py-2 text-muted fs-8">لا توجد إنجازات مرفوعة.</div>
                                        {% endif %}
                                    </div>

                                    {% if session['dept_id'] == d.id or is_admin %}
                                    <form action="/upload_achievement" method="post" enctype="multipart/form-data" class="bg-white p-2 rounded border mb-3">
                                        <input type="hidden" name="dept_id" value="{{ d.id }}">
                                        <div class="d-flex flex-column flex-sm-row gap-2">
                                            <input type="text" name="title" class="form-control fs-8" placeholder="عنوان الإنجاز..." required>
                                            <input type="file" name="file" class="form-control fs-8" required>
                                            <button class="btn btn-fifa-gold fs-8 text-nowrap" type="submit">رفع إنجاز</button>
                                        </div>
                                    </form>
                                    {% endif %}

                                    <div class="sub-section-title"><i class='bx bxs-certification ms-1'></i> شهادات الدورات التدريبية</div>
                                    <div class="list-group mb-3 fs-7" id="dept-certs-{{ d.id }}">
                                        {% set ns_c = namespace(found=false) %}
                                        {% for c in certificates %}
                                            {% if c.dept_id == d.id %}
                                                {% set ns_c.found = true %}
                                                <div class="list-group-item d-flex justify-content-between align-items-center bg-transparent p-2">
                                                    <div>
                                                        <i class='bx bxs-certification text-primary fs-5 align-middle ms-1'></i>
                                                        <strong class="text-dark fs-7">{{ c.title }}</strong>
                                                        <span class="text-muted d-block fs-8">{{ c.uploaded_at }}</span>
                                                    </div>
                                                    <div class="d-flex gap-1">
                                                        <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_cert_file/{{ c.id }}', '{{ c.title }}')">معاينة</button>
                                                        <a href="/download_cert_file/{{ c.id }}" target="_blank" class="btn btn-sm btn-outline-primary py-0 px-2 fs-8">تنزيل</a>
                                                    </div>
                                                </div>
                                            {% endif %}
                                        {% endfor %}
                                        {% if not ns_c.found %}
                                            <div class="text-center py-2 text-muted fs-8">لا توجد شهادات دورات مرفوعة.</div>
                                        {% endif %}
                                    </div>

                                    {% if session['dept_id'] == d.id or is_admin %}
                                    <form action="/upload_certificate" method="post" enctype="multipart/form-data" class="bg-light p-2 rounded border">
                                        <input type="hidden" name="dept_id" value="{{ d.id }}">
                                        <div class="d-flex flex-column flex-sm-row gap-2">
                                            <input type="text" name="title" class="form-control fs-8" placeholder="عنوان أو اسم شهادة الدورة..." required>
                                            <input type="file" name="file" class="form-control fs-8" required>
                                            <button class="btn btn-primary fs-8 text-nowrap" type="submit">رفع شهادة</button>
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
        <div class="modal fade" id="previewFileModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-xl modal-dialog-centered">
            <div class="modal-content">
              <div class="modal-header bg-dark text-white py-2">
                <h6 class="modal-title fw-bold" id="previewFileTitle">معاينة المستند</h6>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
              </div>
              <div class="modal-body p-0" style="height: 80vh; background: #525659;">
                <iframe id="previewFrame" src="" style="width:100%; height:100%; border:none;"></iframe>
              </div>
            </div>
          </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function previewFile(url, title) {
                document.getElementById('previewFileTitle').innerText = 'معاينة: ' + title;
                document.getElementById('previewFrame').src = url;
                var modal = new bootstrap.Modal(document.getElementById('previewFileModal'));
                modal.show();
            }
            function toggleSidebar() {
                document.getElementById('sidebarMenu').classList.toggle('show-sidebar');
                document.getElementById('mobileOverlay').classList.toggle('active');
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_code, depts=depts, achievements=achievements, certificates=certificates, dept_name=session['dept_name'], can_delete=current_dept['can_delete'], can_add_user=current_dept['can_add_user'], current_dept=current_dept, is_admin=is_admin)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE id = %s', (session['dept_id'],))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، هذه الصفحة مخصصة لمدير النظام فقط."); window.location.href="/dashboard";</script>'''

    cursor.execute('SELECT * FROM departments')
    depts = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) as count FROM letters')
    total_letters = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM monthly_achievements')
    total_ach = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM course_certificates')
    total_certs = cursor.fetchone()['count']

    # احصائيات مفصلة لكل إدارة مع ملفاتها في الصفحات المختلفة
    dept_stats = []
    for d in depts:
        d_id = d['id']

        # الصندوق الوارد لهذه الإدارة (تفصيل كامل بالملفات)
        cursor.execute('''
            SELECT l.*, s.name as sender_name FROM letters l
            LEFT JOIN departments s ON l.sender_id = s.id
            WHERE l.receiver_id = %s ORDER BY l.id DESC
        ''', (d_id,))
        inbox_files = cursor.fetchall()
        inbox_count = len(inbox_files)

        # الخطابات الصادرة من هذه الإدارة (تفصيل كامل بالملفات)
        cursor.execute('''
            SELECT l.*, r.name as receiver_name FROM letters l
            LEFT JOIN departments r ON l.receiver_id = r.id
            WHERE l.sender_id = %s ORDER BY l.id DESC
        ''', (d_id,))
        outbox_files = cursor.fetchall()
        outbox_count = len(outbox_files)

        # أرشيف هذه الإدارة (تفصيل كامل بالملفات)
        cursor.execute('''
            SELECT l.* FROM letters l
            WHERE (l.sender_id = l.receiver_id AND l.sender_id = %s) OR (l.archive_dept_id = %s)
            ORDER BY l.id DESC
        ''', (d_id, d_id))
        archive_files = cursor.fetchall()
        archive_count = len(archive_files)
        
        cursor.execute('SELECT COUNT(*) as count FROM monthly_achievements WHERE dept_id = %s', (d_id,))
        ach_count = cursor.fetchone()['count']
        
        cursor.execute('SELECT * FROM monthly_achievements WHERE dept_id = %s', (d_id,))
        ach_files = cursor.fetchall()

        cursor.execute('SELECT COUNT(*) as count FROM course_certificates WHERE dept_id = %s', (d_id,))
        cert_count = cursor.fetchone()['count']
        
        cursor.execute('SELECT * FROM course_certificates WHERE dept_id = %s', (d_id,))
        cert_files = cursor.fetchall()

        dept_stats.append({
            'id': d_id,
            'name': d['name'],
            'inbox_count': inbox_count,
            'inbox_files': inbox_files,
            'outbox_count': outbox_count,
            'outbox_files': outbox_files,
            'archive_count': archive_count,
            'archive_files': archive_files,
            'ach_count': ach_count,
            'ach_files': ach_files,
            'cert_count': cert_count,
            'cert_files': cert_files
        })
    
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
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

            .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
            .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
            .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
            .content-body { flex: 1; padding: 1.25rem; }
            .stat-box { background: rgba(255, 255, 255, 0.95); border-radius: 12px; border: 1px solid var(--fifa-card-border); padding: 1.2rem; box-shadow: 0 4px 15px rgba(0,0,0,0.03); text-align: center; }
            .modern-card { background: rgba(255, 255, 255, 0.95); border-radius: 12px; border: 1px solid var(--fifa-card-border); padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 15px rgba(0,0,0,0.03); }
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
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                <a href="/monthly_achievements" class="sidebar-link"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                <a href="/quick_upload" class="sidebar-link"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
                <a href="/admin/dashboard" class="sidebar-link active" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
                <a href="/register" class="sidebar-link"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
                <div class="border-top border-secondary my-3 opacity-25"></div>
                <a href="/logout" class="sidebar-link text-danger"><i class='bx bx-log-out text-danger'></i>تسجيل الخروج</a>
            </aside>
            <main class="content-body">
                <div class="container-fluid p-0">
                    <div class="mb-4">
                        <h4 class="fw-bold fs-5" style="color: var(--fifa-green-primary);"><i class='bx bxs-cog ms-2' style="color: var(--fifa-gold);"></i>لوحة التحكم والإحصائيات الشاملة</h4>
                    </div>

                    <!-- إحصائيات عامة سريعة -->
                    <div class="row g-3 mb-4">
                        <div class="col-md-4">
                            <div class="stat-box">
                                <h3 class="fw-bold text-success">{{ depts|length }}</h3>
                                <p class="text-muted fs-7 mb-0">إجمالي الإدارات والأقسام</p>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="stat-box">
                                <h3 class="fw-bold text-primary">{{ total_letters }}</h3>
                                <p class="text-muted fs-7 mb-0">إجمالي الخطابات والمعاملات</p>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="stat-box">
                                <h3 class="fw-bold text-warning">{{ total_ach + total_certs }}</h3>
                                <p class="text-muted fs-7 mb-0">إجمالي الإنجازات والشهادات</p>
                            </div>
                        </div>
                    </div>

                    <!-- قسم إجمالي الإدارات بالتفصيل الكامل للملفات -->
                    <div class="modern-card">
                        <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-group ms-1'></i> إجمالي الإدارات والأقسام وتفصيل ملفاتها</h5>
                        <div class="table-responsive">
                            <table class="table table-bordered table-hover align-middle fs-7">
                                <thead class="table-success text-dark">
                                    <tr>
                                        <th>اسم الإدارة / القسم</th>
                                        <th class="text-center">الصندوق الوارد</th>
                                        <th class="text-center">الخطابات الصادرة</th>
                                        <th class="text-center">أرشيف الإدارة</th>
                                        <th class="text-center">إنجازات الشهر</th>
                                        <th class="text-center">شهادات الدورات</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for stat in dept_stats %}
                                    <tr>
                                        <td class="fw-bold text-success"><i class='bx bxs-folder ms-1 text-warning'></i> {{ stat.name }}</td>
                                        <td class="text-center"><span class="badge bg-secondary px-2 py-1">{{ stat.inbox_count }} ملفات</span></td>
                                        <td class="text-center"><span class="badge bg-primary px-2 py-1">{{ stat.outbox_count }} ملفات</span></td>
                                        <td class="text-center"><span class="badge bg-success px-2 py-1">{{ stat.archive_count }} ملفات</span></td>
                                        <td class="text-center"><span class="badge bg-warning text-dark px-2 py-1">{{ stat.ach_count }} ملفات</span></td>
                                        <td class="text-center"><span class="badge bg-info text-white px-2 py-1">{{ stat.cert_count }} ملفات</span></td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- قسم تفصيل الصندوق الوارد لكل إدارة -->
                    <div class="modern-card">
                        <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-inbox ms-1' style="color: var(--fifa-gold);"></i> تفصيل قسم الصندوق الوارد لكل إدارة</h5>
                        <div class="row g-3">
                            {% for stat in dept_stats %}
                            <div class="col-md-6">
                                <div class="border rounded p-3 bg-light">
                                    <h6 class="fw-bold text-success border-bottom pb-2">{{ stat.name }} ({{ stat.inbox_count }} خطابات)</h6>
                                    {% if stat.inbox_files %}
                                        <ul class="list-unstyled mb-0 fs-8 mt-2">
                                            {% for l in stat.inbox_files %}
                                            <li class="d-flex justify-content-between align-items-center mb-1 bg-white p-2 rounded border">
                                                <span><i class='bx bxs-envelope text-secondary ms-1'></i> {{ l.title }} <small class="text-muted">من: {{ l.sender_name or '-' }} ({{ l.created_at }})</small></span>
                                                {% if l.file_data %}
                                                <div class="d-flex gap-1">
                                                    <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_letter_file/{{ l.id }}', '{{ l.title }}')">معاينة</button>
                                                    <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-success py-0 px-2 fs-8">تنزيل</a>
                                                </div>
                                                {% endif %}
                                            </li>
                                            {% endfor %}
                                        </ul>
                                    {% else %}
                                        <p class="text-muted fs-8 mb-0 mt-2">لا توجد خطابات واردة لهذه الإدارة.</p>
                                    {% endif %}
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <!-- قسم تفصيل الخطابات الصادرة لكل إدارة -->
                    <div class="modern-card">
                        <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-paper-plane ms-1' style="color: var(--fifa-gold);"></i> تفصيل قسم الخطابات الصادرة لكل إدارة</h5>
                        <div class="row g-3">
                            {% for stat in dept_stats %}
                            <div class="col-md-6">
                                <div class="border rounded p-3 bg-light">
                                    <h6 class="fw-bold text-primary border-bottom pb-2">{{ stat.name }} ({{ stat.outbox_count }} خطابات)</h6>
                                    {% if stat.outbox_files %}
                                        <ul class="list-unstyled mb-0 fs-8 mt-2">
                                            {% for l in stat.outbox_files %}
                                            <li class="d-flex justify-content-between align-items-center mb-1 bg-white p-2 rounded border">
                                                <span><i class='bx bxs-send text-primary ms-1'></i> {{ l.title }} <small class="text-muted">إلى: {{ l.receiver_name or '-' }} ({{ l.created_at }})</small></span>
                                                {% if l.file_data %}
                                                <div class="d-flex gap-1">
                                                    <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_letter_file/{{ l.id }}', '{{ l.title }}')">معاينة</button>
                                                    <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-success py-0 px-2 fs-8">تنزيل</a>
                                                </div>
                                                {% endif %}
                                            </li>
                                            {% endfor %}
                                        </ul>
                                    {% else %}
                                        <p class="text-muted fs-8 mb-0 mt-2">لا توجد خطابات صادرة من هذه الإدارة.</p>
                                    {% endif %}
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <!-- قسم تفصيل أرشيف الإدارة لكل إدارة -->
                    <div class="modern-card">
                        <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-file-archive ms-1' style="color: var(--fifa-gold);"></i> تفصيل قسم أرشيف الإدارة لكل إدارة</h5>
                        <div class="row g-3">
                            {% for stat in dept_stats %}
                            <div class="col-md-6">
                                <div class="border rounded p-3 bg-light">
                                    <h6 class="fw-bold text-success border-bottom pb-2">{{ stat.name }} ({{ stat.archive_count }} ملفات)</h6>
                                    {% if stat.archive_files %}
                                        <ul class="list-unstyled mb-0 fs-8 mt-2">
                                            {% for l in stat.archive_files %}
                                            <li class="d-flex justify-content-between align-items-center mb-1 bg-white p-2 rounded border">
                                                <span><i class='bx bxs-folder-open text-success ms-1'></i> {{ l.title }} <small class="text-muted">({{ l.created_at }})</small></span>
                                                {% if l.file_data %}
                                                <div class="d-flex gap-1">
                                                    <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_letter_file/{{ l.id }}', '{{ l.title }}')">معاينة</button>
                                                    <a href="/download_letter_file/{{ l.id }}" class="btn btn-sm btn-outline-success py-0 px-2 fs-8">تنزيل</a>
                                                </div>
                                                {% endif %}
                                            </li>
                                            {% endfor %}
                                        </ul>
                                    {% else %}
                                        <p class="text-muted fs-8 mb-0 mt-2">لا توجد ملفات في أرشيف هذه الإدارة.</p>
                                    {% endif %}
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <!-- قسم إنجازات الشهر المفصل لكل إدارة -->
                    <div class="modern-card">
                        <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-trophy ms-1' style="color: var(--fifa-gold);"></i> تفصيل قسم إنجازات الشهر لكل إدارة</h5>
                        <div class="row g-3">
                            {% for stat in dept_stats %}
                            <div class="col-md-6">
                                <div class="border rounded p-3 bg-light">
                                    <h6 class="fw-bold text-success border-bottom pb-2">{{ stat.name }} ({{ stat.ach_count }} إنجازات)</h6>
                                    {% if stat.ach_files %}
                                        <ul class="list-unstyled mb-0 fs-8 mt-2">
                                            {% for ach in stat.ach_files %}
                                            <li class="d-flex justify-content-between align-items-center mb-1 bg-white p-2 rounded border">
                                                <span><i class='bx bxs-file-pdf text-danger ms-1'></i> {{ ach.title }} <small class="text-muted">({{ ach.uploaded_at }})</small></span>
                                                <div class="d-flex gap-1">
                                                    <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_ach_file/{{ ach.id }}', '{{ ach.title }}')">معاينة</button>
                                                    <a href="/download_ach_file/{{ ach.id }}" class="btn btn-sm btn-outline-success py-0 px-2 fs-8">تنزيل</a>
                                                </div>
                                            </li>
                                            {% endfor %}
                                        </ul>
                                    {% else %}
                                        <p class="text-muted fs-8 mb-0 mt-2">لا توجد إنجازات مرفوعة لهذه الإدارة.</p>
                                    {% endif %}
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <!-- قسم شهادات ودورات المفصل لكل إدارة -->
                    <div class="modern-card">
                        <h5 class="fw-bold mb-3" style="color: var(--fifa-green-primary);"><i class='bx bxs-certification ms-1' style="color: var(--fifa-gold);"></i> تفصيل قسم شهادات ودورات لكل إدارة</h5>
                        <div class="row g-3">
                            {% for stat in dept_stats %}
                            <div class="col-md-6">
                                <div class="border rounded p-3 bg-light">
                                    <h6 class="fw-bold text-primary border-bottom pb-2">{{ stat.name }} ({{ stat.cert_count }} شهادات)</h6>
                                    {% if stat.cert_files %}
                                        <ul class="list-unstyled mb-0 fs-8 mt-2">
                                            {% for cert in stat.cert_files %}
                                            <li class="d-flex justify-content-between align-items-center mb-1 bg-white p-2 rounded border">
                                                <span><i class='bx bxs-file-pdf text-primary ms-1'></i> {{ cert.title }} <small class="text-muted">({{ cert.uploaded_at }})</small></span>
                                                <div class="d-flex gap-1">
                                                    <button type="button" class="btn btn-sm btn-info py-0 px-2 fs-8 text-white" onclick="previewFile('/view_cert_file/{{ cert.id }}', '{{ cert.title }}')">معاينة</button>
                                                    <a href="/download_cert_file/{{ cert.id }}" class="btn btn-sm btn-outline-primary py-0 px-2 fs-8">تنزيل</a>
                                                </div>
                                            </li>
                                            {% endfor %}
                                        </ul>
                                    {% else %}
                                        <p class="text-muted fs-8 mb-0 mt-2">لا توجد شهادات دورات مرفوعة لهذه الإدارة.</p>
                                    {% endif %}
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                </div>
            </main>
        </div>
        <div class="modal fade" id="previewFileModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-xl modal-dialog-centered">
            <div class="modal-content">
              <div class="modal-header bg-dark text-white py-2">
                <h6 class="modal-title fw-bold" id="previewFileTitle">معاينة المستند</h6>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
              </div>
              <div class="modal-body p-0" style="height: 80vh; background: #525659;">
                <iframe id="previewFrame" src="" style="width:100%; height:100%; border:none;"></iframe>
              </div>
            </div>
          </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function previewFile(url, title) {
                document.getElementById('previewFileTitle').innerText = 'معاينة: ' + title;
                document.getElementById('previewFrame').src = url;
                var modal = new bootstrap.Modal(document.getElementById('previewFileModal'));
                modal.show();
            }
            function toggleSidebar() {
                document.getElementById('sidebarMenu').classList.toggle('show-sidebar');
                document.getElementById('mobileOverlay').classList.toggle('active');
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_code, depts=depts, total_letters=total_letters, total_ach=total_ach, total_certs=total_certs, dept_stats=dept_stats)

# --- إدارة الصلاحيات ---
@app.route('/admin/permissions', methods=['GET', 'POST'])
def admin_permissions():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    is_admin = is_admin_user(session.get('dept_name'))
    if not is_admin:
        return '''<script>alert("عذراً، صفحة إدارة الصلاحيات مخصصة للمسؤولين فقط."); window.location.href="/dashboard";</script>'''
 
    conn = get_db_connection()
    cursor = conn.cursor()
 
    if request.method == 'POST':
        dept_id = request.form.get('dept_id')
        can_delete = 1 if request.form.get('can_delete') else 0
        can_view_all_archive = 1 if request.form.get('can_view_all_archive') else 0
        can_view_all_achievements = 1 if request.form.get('can_view_all_achievements') else 0
        can_add_user = 1 if request.form.get('can_add_user') else 0
        can_page_inbox = 1 if request.form.get('can_page_inbox') else 0
        can_page_outbox = 1 if request.form.get('can_page_outbox') else 0
        can_page_achievements = 1 if request.form.get('can_page_achievements') else 0
        can_page_archive = 1 if request.form.get('can_page_archive') else 0
        can_page_quick_upload = 1 if request.form.get('can_page_quick_upload') else 0
        new_password = request.form.get('new_password')
 
        if new_password and new_password.strip() != '':
            cursor.execute('''
                UPDATE departments 
                SET can_delete = %s, can_view_all_archive = %s, can_view_all_achievements = %s, can_add_user = %s,
                    can_page_inbox = %s, can_page_outbox = %s, can_page_achievements = %s, can_page_archive = %s, can_page_quick_upload = %s,
                    password = %s
                WHERE id = %s
            ''', (can_delete, can_view_all_archive, can_view_all_achievements, can_add_user, can_page_inbox, can_page_outbox, can_page_achievements, can_page_archive, can_page_quick_upload, new_password.strip(), dept_id))
        else:
            cursor.execute('''
                UPDATE departments 
                SET can_delete = %s, can_view_all_archive = %s, can_view_all_achievements = %s, can_add_user = %s,
                    can_page_inbox = %s, can_page_outbox = %s, can_page_achievements = %s, can_page_archive = %s, can_page_quick_upload = %s
                WHERE id = %s
            ''', (can_delete, can_view_all_archive, can_view_all_achievements, can_add_user, can_page_inbox, can_page_outbox, can_page_achievements, can_page_archive, can_page_quick_upload, dept_id))
 
        conn.commit()
        cursor.close()
        conn.close()
        return '''<script>alert("تم تحديث الصلاحيات وبيانات الإدارة بنجاح!"); window.location.href="/admin/permissions";</script>'''
 
    cursor.execute('SELECT * FROM departments ORDER BY id ASC')
    departments = cursor.fetchall()
    cursor.close()
    conn.close()
 
    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إدارة الصلاحيات - نادي فيفا</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green-primary: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; padding: 20px 10px; }
            .perm-card { background: #ffffff; border-radius: 12px; border: 1px solid #d5e2d8; box-shadow: 0 4px 15px rgba(0,0,0,0.04); margin-bottom: 1.5rem; overflow: hidden; }
            .perm-header { background-color: var(--fifa-green-primary); color: #fff; padding: 1rem; font-weight: bold; font-size: 1.1rem; }
            .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; font-weight: 700; border: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
                <h4 class="fw-bold m-0" style="color: var(--fifa-green-primary);"><i class='bx bxs-shield ms-2' style="color: var(--fifa-gold);"></i>لوحة إدارة صلاحيات الإدارات والشبكة</h4>
                <a href="/dashboard" class="btn btn-outline-success fw-bold fs-7"><i class='bx bx-right-arrow-alt ms-1'></i>العودة للنظام</a>
            </div>
 
            <div class="row">
                {% for d in departments %}
                <div class="col-lg-6">
                    <div class="perm-card">
                        <div class="perm-header d-flex justify-content-between align-items-center">
                            <span><i class='bx bxs-building ms-2'></i>{{ d.name }}</span>
                            <span class="badge bg-warning text-dark fs-8">{{ d.username }}</span>
                        </div>
                        <div class="p-3">
                            <form action="/admin/permissions" method="post">
                                <input type="hidden" name="dept_id" value="{{ d.id }}">
                                
                                <h6 class="fw-bold text-success mb-2 fs-7 border-bottom pb-1"><i class='bx bx-check-shield ms-1'></i>الصلاحيات العامة:</h6>
                                <div class="row g-2 mb-3">
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_delete" {{ 'checked' if d.can_delete == 1 else '' }}>
                                            <label class="form-check-label">صلاحية الحذف</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_add_user" {{ 'checked' if d.can_add_user == 1 else '' }}>
                                            <label class="form-check-label">إضافة إدارات جديدة</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_view_all_archive" {{ 'checked' if d.can_view_all_archive == 1 else '' }}>
                                            <label class="form-check-label">رؤية كامل أرشيف للنادي</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_view_all_achievements" {{ 'checked' if d.can_view_all_achievements == 1 else '' }}>
                                            <label class="form-check-label">رؤية إنجازات كافة الإدارات</label>
                                        </div>
                                    </div>
                                </div>
 
                                <h6 class="fw-bold text-success mb-2 fs-7 border-bottom pb-1"><i class='bx bx-layout ms-1'></i>صلاحيات فتح الصفحات:</h6>
                                <div class="row g-2 mb-3">
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_page_inbox" {{ 'checked' if d.can_page_inbox == 1 else '' }}>
                                            <label class="form-check-label">الصندوق الوارد</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_page_outbox" {{ 'checked' if d.can_page_outbox == 1 else '' }}>
                                            <label class="form-check-label">الخطابات الصادرة</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_page_achievements" {{ 'checked' if d.can_page_achievements == 1 else '' }}>
                                            <label class="form-check-label">إنجازات الشهر</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_page_archive" {{ 'checked' if d.can_page_archive == 1 else '' }}>
                                            <label class="form-check-label">أرشيف الإدارة</label>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="form-check form-switch fs-7">
                                            <input class="form-check-input" type="checkbox" name="can_page_quick_upload" {{ 'checked' if d.can_page_quick_upload == 1 else '' }}>
                                            <label class="form-check-label">رفع وتوثيق فوري</label>
                                        </div>
                                    </div>
                                </div>
 
                                <div class="mb-3">
                                    <label class="form-label fw-bold fs-8 mb-1" style="color: var(--fifa-green-primary);">تغيير كلمة المرور (اتركه فارغاً للإبقاء):</label>
                                    <input type="password" name="new_password" class="form-control fs-8" placeholder="كلمة مرور جديدة...">
                                </div>
 
                                <button type="submit" class="btn btn-fifa-gold w-100 fs-7 shadow-sm py-2">تحديث صلاحيات {{ d.name }}</button>
                            </form>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_code, departments=departments)
 
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
