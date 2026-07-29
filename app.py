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

# --- صفحة إنجازات الشهر ---
@app.route('/monthly_achievements')
def monthly_achievements():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
        
    dept_id = session['dept_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM departments WHERE id = %s', (dept_id,))
    current_dept = cursor.fetchone()
    is_admin = is_admin_user(session.get('dept_name'))
    
    if current_dept['can_page_achievements'] != 1 and not is_admin:
        cursor.close()
        conn.close()
        return '''<script>alert("عذراً، لا تملك صلاحية الوصول لإنجازات الشهر."); window.location.href="/dashboard";</script>'''
    
    cursor.execute('SELECT id, name FROM departments')
    depts = cursor.fetchall()

    if current_dept['can_view_all_achievements'] == 1 or is_admin:
        cursor.execute('''
            SELECT ma.*, d.name as dept_name 
            FROM monthly_achievements ma 
            JOIN departments d ON ma.dept_id = d.id 
            ORDER BY ma.id DESC
        ''')
    else:
        cursor.execute('''
            SELECT ma.*, d.name as dept_name 
            FROM monthly_achievements ma 
            JOIN departments d ON ma.dept_id = d.id 
            WHERE ma.dept_id = %s 
            ORDER BY ma.id DESC
        ''', (dept_id,))
    achievements = cursor.fetchall()
    
    cursor.close()
    conn.close()

    html_code = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إنجازات الشهر - نادي فيفا الرياضي</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap" rel="stylesheet">
        <style>
            :root { --fifa-green: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; }
            .top-navbar { background-color: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1rem; }
            .nav-logo { height: 42px; width: auto; object-fit: contain; }
            .main-wrapper { display: flex; min-height: calc(100vh - 76px); position: relative; }
            .sidebar { width: 260px; background-color: var(--fifa-green); color: #ecf0f1; padding-top: 1rem; flex-shrink: 0; }
            .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
            .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
            .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
            .content-body { flex: 1; padding: 1.5rem; }
            .modern-card { background: rgba(255, 255, 255, 0.95); border-radius: 12px; border: 1px solid #d5e2d8; box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); }
        </style>
    </head>
    <body>
        <nav class="navbar top-navbar sticky-top">
            <div class="container-fluid">
                <a class="navbar-brand d-flex align-items-center gap-2 m-0" href="/dashboard">
                    <img src="{{ url_for('static', filename='logo.png') }}" alt="نادي فيفا" class="nav-logo" onerror="this.style.display='none'">
                    <span class="fw-bold fs-6" style="color: var(--fifa-green);">نادي فيفا الرياضي - إنجازات الشهر</span>
                </a>
                <a href="/logout" class="btn btn-sm btn-outline-danger"><i class='bx bx-log-out ms-1'></i>تسجيل الخروج</a>
            </div>
        </nav>
        <div class="main-wrapper">
            <aside class="sidebar d-none d-lg-block">
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                <a href="/monthly_achievements" class="sidebar-link active"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                {% if is_admin %}
                <a href="/admin/dashboard" class="sidebar-link" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
                {% endif %}
            </aside>
            <main class="content-body">
                <div class="container-fluid">
                    <div class="row mb-4">
                        <div class="col-md-12">
                            <div class="modern-card p-4">
                                <h4 class="fw-bold mb-3" style="color: var(--fifa-green);"><i class='bx bxs-trophy ms-2 text-warning'></i> رفع إنجاز شهري جديد</h4>
                                <form action="/upload_achievement" method="post" enctype="multipart/form-data">
                                    <div class="row">
                                        {% if is_admin %}
                                        <div class="col-md-4 mb-3">
                                            <label class="form-label fw-bold fs-7">الإدارة المعنية</label>
                                            <select name="dept_id" class="form-select fs-7" required>
                                                {% for d in depts %}
                                                <option value="{{ d.id }}" {% if d.id == session.dept_id %}selected{% endif %}>{{ d.name }}</option>
                                                {% endfor %}
                                            </select>
                                        </div>
                                        {% else %}
                                        <input type="hidden" name="dept_id" value="{{ session.dept_id }}">
                                        {% endif %}
                                        <div class="col-md-4 mb-3">
                                            <label class="form-label fw-bold fs-7">عنوان الإنجاز</label>
                                            <input type="text" name="title" class="form-control fs-7" placeholder="مثال: إنجازات شهر يونيو" required>
                                        </div>
                                        <div class="col-md-4 mb-3">
                                            <label class="form-label fw-bold fs-7">ملف الإنجاز (PDF / صور)</label>
                                            <input type="file" name="file" class="form-control fs-7" required>
                                        </div>
                                    </div>
                                    <button type="submit" class="btn btn-success fw-bold px-4" style="background-color: var(--fifa-green);">رفع الإنجاز</button>
                                </form>
                            </div>
                        </div>
                    </div>

                    <div class="modern-card p-4">
                        <h4 class="fw-bold mb-4" style="color: var(--fifa-green);">سجل الإنجازات الشهرية المرفوعة</h4>
                        {% if achievements %}
                        <div class="table-responsive">
                            <table class="table table-hover align-middle">
                                <thead class="table-light">
                                    <tr>
                                        <th>الإدارة</th>
                                        <th>عنوان الإنجاز</th>
                                        <th>تاريخ الرفع</th>
                                        <th>الملف</th>
                                        <th>الإجراءات</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for ach in achievements %}
                                    <tr>
                                        <td class="fw-bold text-success">{{ ach.dept_name }}</td>
                                        <td>{{ ach.title }}</td>
                                        <td><small class="text-muted">{{ ach.uploaded_at }}</small></td>
                                        <td>
                                            {% if ach.file_data %}
                                            <a href="/download_ach_file/{{ ach.id }}" class="btn btn-sm btn-outline-success">تحميل الملف</a>
                                            {% else %}
                                            <span class="text-muted">بدون ملف</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if is_admin or ach.dept_id == session.dept_id %}
                                            <a href="/admin/clear_monthly_files/{{ ach.dept_id }}" class="btn btn-sm btn-outline-warning" onclick="return confirm('هل تريد أرشفة وتفريغ ملفات إنجازات هذه الإدارة؟');">أرشفة وتفريغ</a>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% else %}
                        <p class="text-muted text-center py-4">لا توجد إنجازات مرفوعة حالياً.</p>
                        {% endif %}
                    </div>
                </div>
            </main>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''
    return render_template_string(html_code, achievements=achievements, depts=depts, is_admin=is_admin)

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

# --- صفحة لوحة التحكم الشاملة ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'dept_id' not in session or not is_admin_user(session.get('dept_name')):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM departments')
    total_depts = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM letters')
    total_letters = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM monthly_achievements')
    total_achievements = cursor.fetchone()['count']
    
    cursor.execute('SELECT * FROM departments ORDER BY id DESC')
    departments = cursor.fetchall()
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
            :root { --fifa-green: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; }
            .top-navbar { background-color: rgba(255, 255, 255, 0.95); border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1rem; }
            .nav-logo { height: 42px; width: auto; object-fit: contain; }
            .main-wrapper { display: flex; min-height: calc(100vh - 76px); position: relative; }
            .sidebar { width: 260px; background-color: var(--fifa-green); color: #ecf0f1; padding-top: 1rem; flex-shrink: 0; }
            .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
            .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
            .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
            .content-body { flex: 1; padding: 1.5rem; }
            .stat-card { background: #fff; border-radius: 12px; border-right: 5px solid var(--fifa-gold); padding: 20px; box-shadow: 0 4px 15px rgba(18, 56, 38, 0.05); }
        </style>
    </head>
    <body>
        <nav class="navbar top-navbar sticky-top">
            <div class="container-fluid">
                <a class="navbar-brand d-flex align-items-center gap-2 m-0" href="/dashboard">
                    <img src="{{ url_for('static', filename='logo.png') }}" alt="نادي فيفا" class="nav-logo" onerror="this.style.display='none'">
                    <span class="fw-bold fs-6" style="color: var(--fifa-green);">نادي فيفا الرياضي - لوحة التحكم الشاملة</span>
                </a>
                <a href="/logout" class="btn btn-sm btn-outline-danger"><i class='bx bx-log-out ms-1'></i>تسجيل الخروج</a>
            </div>
        </nav>
        <div class="main-wrapper">
            <aside class="sidebar d-none d-lg-block">
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                <a href="/monthly_achievements" class="sidebar-link"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                <a href="/admin/dashboard" class="sidebar-link active" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
            </aside>
            <main class="content-body">
                <div class="container-fluid">
                    <div class="row g-3 mb-4">
                        <div class="col-md-4">
                            <div class="stat-card">
                                <h6 class="text-muted">إجمالي الإدارات والسامات</h6>
                                <h3 class="fw-bold mt-2" style="color: var(--fifa-green);">{{ total_depts }}</h3>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="stat-card">
                                <h6 class="text-muted">إجمالي المعاملات والخطابات</h6>
                                <h3 class="fw-bold mt-2" style="color: var(--fifa-green);">{{ total_letters }}</h3>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="stat-card">
                                <h6 class="text-muted">إجمالي إنجازات الشهر</h6>
                                <h3 class="fw-bold mt-2" style="color: var(--fifa-green);">{{ total_achievements }}</h3>
                            </div>
                        </div>
                    </div>

                    <div class="card border-0 shadow-sm p-4 rounded-3">
                        <h4 class="fw-bold mb-3" style="color: var(--fifa-green);">قائمة الإدارات المسجلة في النظام</h4>
                        <div class="table-responsive">
                            <table class="table table-hover align-middle">
                                <thead class="table-light">
                                    <tr>
                                        <th>معرف الإدارة</th>
                                        <th>اسم الإدارة / القسم</th>
                                        <th>اسم المستخدم</th>
                                        <th>الإجراءات</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for dept in departments %}
                                    <tr>
                                        <td>#{{ dept.id }}</td>
                                        <td class="fw-bold">{{ dept.name }}</td>
                                        <td><code>{{ dept.username }}</code></td>
                                        <td>
                                            <a href="/admin/permissions" class="btn btn-sm btn-outline-success">تعديل الصلاحيات</a>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </main>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''
    return render_template_string(html_code, total_depts=total_depts, total_letters=total_letters, total_achievements=total_achievements, departments=departments)

# --- صفحة إدارة الصلاحيات ---
@app.route('/admin/permissions', methods=['GET', 'POST'])
def admin_permissions():
    if 'dept_id' not in session or not is_admin_user(session.get('dept_name')):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        dept_id = request.form.get('dept_id')
        can_delete = 1 if request.form.get('can_delete') == '1' else 0
        can_add_user = 1 if request.form.get('can_add_user') == '1' else 0
        can_view_all_archive = 1 if request.form.get('can_view_all_archive') == '1' else 0
        can_page_inbox = 1 if request.form.get('can_page_inbox') == '1' else 0
        can_page_outbox = 1 if request.form.get('can_page_outbox') == '1' else 0
        can_page_achievements = 1 if request.form.get('can_page_achievements') == '1' else 0
        can_page_archive = 1 if request.form.get('can_page_archive') == '1' else 0
        can_page_quick_upload = 1 if request.form.get('can_page_quick_upload') == '1' else 0
        
        cursor.execute('''
            UPDATE departments 
            SET can_delete = %s, can_add_user = %s, can_view_all_archive = %s, 
                can_page_inbox = %s, can_page_outbox = %s, can_page_achievements = %s, 
                can_page_archive = %s, can_page_quick_upload = %s
            WHERE id = %s
        ''', (can_delete, can_add_user, can_view_all_archive, can_page_inbox, can_page_outbox, can_page_achievements, can_page_archive, can_page_quick_upload, dept_id))
        conn.commit()
        
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
            :root { --fifa-green: #123826; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; }
            body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; }
            .top-navbar { background-color: rgba(255, 255, 255, 0.95); border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1rem; }
            .nav-logo { height: 42px; width: auto; object-fit: contain; }
            .main-wrapper { display: flex; min-height: calc(100vh - 76px); position: relative; }
            .sidebar { width: 260px; background-color: var(--fifa-green); color: #ecf0f1; padding-top: 1rem; flex-shrink: 0; }
            .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
            .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
            .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
            .content-body { flex: 1; padding: 1.5rem; }
        </style>
    </head>
    <body>
        <nav class="navbar top-navbar sticky-top">
            <div class="container-fluid">
                <a class="navbar-brand d-flex align-items-center gap-2 m-0" href="/dashboard">
                    <img src="{{ url_for('static', filename='logo.png') }}" alt="نادي فيفا" class="nav-logo" onerror="this.style.display='none'">
                    <span class="fw-bold fs-6" style="color: var(--fifa-green);">نادي فيفا الرياضي - إدارة الصلاحيات</span>
                </a>
                <a href="/logout" class="btn btn-sm btn-outline-danger"><i class='bx bx-log-out ms-1'></i>تسجيل الخروج</a>
            </div>
        </nav>
        <div class="main-wrapper">
            <aside class="sidebar d-none d-lg-block">
                <a href="/dashboard" class="sidebar-link"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
                <a href="/outbox" class="sidebar-link"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
                <a href="/monthly_achievements" class="sidebar-link"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
                <a href="/archive" class="sidebar-link"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
                <a href="/admin/dashboard" class="sidebar-link" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
                <a href="/admin/permissions" class="sidebar-link active"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
            </aside>
            <main class="content-body">
                <div class="container-fluid">
                    <div class="card border-0 shadow-sm p-4 rounded-3">
                        <h4 class="fw-bold mb-3" style="color: var(--fifa-green);"><i class='bx bxs-shield ms-2'></i> تحكم بصلاحيات الإدارات والسامات</h4>
                        <p class="text-muted small mb-4">قم بتعديل الصلاحيات الممنوحة لكل إدارة لحفظ التغييرات مباشرة.</p>
                        
                        <div class="accordion" id="permissionsAccordion">
                            {% for dept in departments %}
                            <div class="accordion-item mb-2 border rounded shadow-sm">
                                <h2 class="accordion-header" id="heading{{ dept.id }}">
                                    <button class="accordion-button collapsed fw-bold" type="button" data-bs-toggle="collapse" data-bs-target="#collapse{{ dept.id }}">
                                        {{ dept.name }} <small class="text-muted ms-2">({{ dept.username }})</small>
                                    </button>
                                </h2>
                                <div id="collapse{{ dept.id }}" class="accordion-collapse collapse" data-bs-parent="#permissionsAccordion">
                                    <div class="accordion-body bg-light">
                                        <form action="/admin/permissions" method="post">
                                            <input type="hidden" name="dept_id" value="{{ dept.id }}">
                                            <div class="row g-3">
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_delete" value="1" id="del{{ dept.id }}" {% if dept.can_delete == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="del{{ dept.id }}">صلاحية الحذف</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_add_user" value="1" id="add{{ dept.id }}" {% if dept.can_add_user == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="add{{ dept.id }}">إضافة إدارة جديدة</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_view_all_archive" value="1" id="view{{ dept.id }}" {% if dept.can_view_all_archive == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="view{{ dept.id }}">عرض كل الأرشيف</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_page_inbox" value="1" id="inb{{ dept.id }}" {% if dept.can_page_inbox == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="inb{{ dept.id }}">الوصول للصندوق الوارد</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_page_outbox" value="1" id="out{{ dept.id }}" {% if dept.can_page_outbox == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="out{{ dept.id }}">الوصول للخطابات الصادرة</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_page_achievements" value="1" id="ach{{ dept.id }}" {% if dept.can_page_achievements == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="ach{{ dept.id }}">الوصول لإنجازات الشهر</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_page_archive" value="1" id="arc{{ dept.id }}" {% if dept.can_page_archive == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="arc{{ dept.id }}">الوصول لأرشيف الإدارة</label>
                                                    </div>
                                                </div>
                                                <div class="col-md-3">
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="checkbox" name="can_page_quick_upload" value="1" id="qck{{ dept.id }}" {% if dept.can_page_quick_upload == 1 %}checked{% endif %}>
                                                        <label class="form-check-label" for="qck{{ dept.id }}">الرفع الفوري</label>
                                                    </div>
                                                </div>
                                            </div>
                                            <div class="mt-3 text-end">
                                                <button type="submit" class="btn btn-sm btn-success fw-bold px-3">حفظ الصلاحيات</button>
                                            </div>
                                        </form>
                                    </div>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </main>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''
    return render_template_string(html_code, departments=departments)

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
            cursor.close()
            conn.close()
            return '''<script>alert("خطأ: اسم المستخدم أو اسم الإدارة مسجل مكرر بالفعل!"); window.location.href="/register";</script>'''
            
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
            .register-card { background: rgba(255, 255, 255, 0.95); border-radius: 16px; border: 1px solid #d5e2d8; box-shadow: 0 10px 30px rgba(18, 56, 38, 0.08); width: 100%; max-width: 450px; padding: 1.5rem; position: relative; }
            .btn-fifa-gold { background-color: var(--fifa-gold); color: #ffffff; border-radius: 8px; padding: 0.75rem; font-weight: 700; border: none; width: 100%; }
        </style>
    </head>
    <body>
        <div class="register-card text-center">
            <h5 class="fw-bold mb-1" style="color: var(--fifa-green);">تسجيل إدارة/قسم جديد</h5>
            <form action="/register" method="post">
                <div class="mb-3 text-start">
                    <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);">اسم الإدارة / القسم</label>
                    <input type="text" name="dept_name" class="form-control" required>
                </div>
                <div class="mb-3 text-start">
                    <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);">اسم المستخدم (للدخول)</label>
                    <input type="text" name="username" class="form-control" required>
                </div>
                <div class="mb-4 text-start">
                    <label class="form-label fw-bold fs-7" style="color: var(--fifa-green);">كلمة المرور</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-fifa-gold mb-3">تسجيل الحساب</button>
            </form>
            <div class="border-top pt-3">
                <a href="/dashboard" class="text-muted text-decoration-none fs-7"><i class='bx bx-right-arrow-alt ms-1'></i>العودة للوحة التحكم</a>
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
        :root { --fifa-green-primary: #123826; --fifa-green-light: #1e563b; --fifa-gold: #c5a059; --fifa-bg: #eaf3ec; --fifa-card-border: #d5e2d8; }
        body { font-family: 'Almarai', sans-serif; background-color: var(--fifa-bg); color: #2b302e; overflow-x: hidden; }
        .top-navbar { background-color: rgba(255, 255, 255, 0.95); backdrop-filter: blur(5px); border-bottom: 3px solid var(--fifa-gold); padding: 0.6rem 1rem; }
        .nav-logo { height: 42px; width: auto; object-fit: contain; }
        .main-wrapper { display: flex; min-height: calc(100vh - 76px); position: relative; }
        .sidebar { width: 260px; background-color: var(--fifa-green-primary); color: #ecf0f1; padding-top: 1rem; flex-shrink: 0; }
        .sidebar-link { display: flex; align-items: center; color: #d1e0d8; text-decoration: none; padding: 12px 20px; border-right: 4px solid transparent; transition: all 0.25s; font-size: 0.95rem; }
        .sidebar-link:hover, .sidebar-link.active { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; border-right-color: var(--fifa-gold); font-weight: 700; }
        .sidebar-link i { font-size: 1.35rem; margin-left: 12px; color: var(--fifa-gold); }
        .content-body { flex: 1; padding: 1.25rem; width: 100%; }
        .modern-card { background: rgba(255, 255, 255, 0.95); border-radius: 12px; border: 1px solid var(--fifa-card-border); box-shadow: 0 4px 15px rgba(18, 56, 38, 0.03); }
        .section-header { font-weight: 800; color: var(--fifa-green-primary); margin-bottom: 1.5rem; position: relative; padding-bottom: 10px; font-size: 1.3rem; }
        .letter-item { border-bottom: 1px solid #f0f4f2; padding: 1rem; }
        .priority-badge { font-size: 0.75rem; padding: 4px 10px; border-radius: 20px; font-weight: 700; color: #fff; background-color: var(--fifa-green-primary); }
        .btn-fifa-primary { background-color: var(--fifa-green-primary); color: #ffffff; border-radius: 8px; padding: 0.6rem 1.2rem; font-weight: 700; border: none; }
    </style>
</head>
<body>
    <nav class="navbar top-navbar sticky-top">
        <div class="container-fluid">
            <a class="navbar-brand d-flex align-items-center gap-2 m-0" href="/dashboard">
                <img src="{{ url_for('static', filename='logo.png') }}" alt="نادي فيفا" class="nav-logo" onerror="this.style.display='none'">
                <span class="fw-bold fs-6" style="color: var(--fifa-green-primary);">نادي فيفا الرياضي</span>
            </a>
            <div class="dropdown">
                <button class="btn btn-light dropdown-toggle border py-1 px-2" type="button" data-bs-toggle="dropdown">
                    <span class="fw-bold fs-7" style="color: var(--fifa-green-primary);">{{ dept_name }}</span>
                </button>
                <ul class="dropdown-menu dropdown-menu-start shadow">
                    <li><a class="dropdown-item text-danger py-2" href="/logout"><i class='bx bx-log-out ms-2'></i>تسجيل الخروج</a></li>
                </ul>
            </div>
        </div>
    </nav>
    <div class="main-wrapper">
        <aside class="sidebar d-none d-lg-block">
            <a href="/dashboard" class="sidebar-link {{ 'active' if current_page == 'inbox' else '' }}"><i class='bx bxs-inbox'></i>الصندوق الوارد</a>
            <a href="/outbox" class="sidebar-link {{ 'active' if current_page == 'outbox' else '' }}"><i class='bx bxs-paper-plane'></i>الخطابات الصادرة</a>
            <a href="/monthly_achievements" class="sidebar-link {{ 'active' if current_page == 'achievements' else '' }}"><i class='bx bxs-trophy'></i>إنجازات الشهر</a>
            <a href="/archive" class="sidebar-link {{ 'active' if current_page == 'archive' else '' }}"><i class='bx bxs-file-archive'></i>أرشيف الإدارة</a>
            <a href="/quick_upload" class="sidebar-link {{ 'active' if current_page == 'quick_upload' else '' }}"><i class='bx bx-cloud-upload' style="color: var(--fifa-gold);"></i>رفع وتوثيق فوري</a>
            {% if is_admin %}
            <a href="/admin/dashboard" class="sidebar-link {{ 'active' if current_page == 'admin_dashboard' else '' }}" style="background-color: rgba(197, 160, 89, 0.2);"><i class='bx bxs-cog' style="color: var(--fifa-gold);"></i>لوحة التحكم الشاملة</a>
            <a href="/admin/permissions" class="sidebar-link {{ 'active' if current_page == 'permissions' else '' }}"><i class='bx bxs-shield'></i>إدارة الصلاحيات</a>
            {% endif %}
            <a href="/register" class="sidebar-link"><i class='bx bxs-user-plus'></i>إضافة إدارة جديدة</a>
        </aside>
        <main class="content-body">
            <h4 class="section-header">{{ page_title }}</h4>
            <div class="modern-card p-3">
                {% if letters %}
                    <div class="letters-list">
                        {% for letter in letters %}
                            <div class="letter-item d-flex justify-content-between align-items-center">
                                <div>
                                    <span class="fw-bold text-dark fs-6">{{ letter.title }}</span>
                                    <p class="text-secondary small mb-1">{{ letter.content }}</p>
                                    <small class="text-muted">{% if current_page == 'outbox' %}إلى: {{ letter.receiver_name }}{% else %}من: {{ letter.sender_name }}{% endif %}</small>
                                </div>
                                <div class="d-flex gap-2">
                                    {% if letter.file_data %}
                                        <a href="/view_letter_file/{{ letter.id }}" target="_blank" class="btn btn-sm btn-success">فتح</a>
                                        <a href="/download_letter_file/{{ letter.id }}" class="btn btn-sm btn-outline-success">تحميل</a>
                                    {% endif %}
                                    <span class="priority-badge">{{ letter.priority }}</span>
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="text-center py-5 text-muted"><p>لا توجد بيانات حالياً.</p></div>
                {% endif %}
            </div>
        </main>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
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
    
    cursor.execute('SELECT l.*, d.name as sender_name FROM letters l JOIN departments d ON l.sender_id = d.id WHERE l.receiver_id = %s ORDER BY l.id DESC', (dept_id,))
    letters = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template_string(DASHBOARD_HTML, page_title="الصندوق الوارد", current_page="inbox", letters=letters, dept_name=session['dept_name'], is_admin=is_admin)

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
    
    cursor.execute('SELECT l.*, d.name as receiver_name FROM letters l JOIN departments d ON l.receiver_id = d.id WHERE l.sender_id = %s ORDER BY l.id DESC', (dept_id,))
    letters = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template_string(DASHBOARD_HTML, page_title="الخطابات الصادرة", current_page="outbox", letters=letters, dept_name=session['dept_name'], is_admin=is_admin)

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
    
    cursor.execute('SELECT l.*, s.name as sender_name, r.name as receiver_name FROM letters l LEFT JOIN departments s ON l.sender_id = s.id LEFT JOIN departments r ON l.receiver_id = r.id WHERE l.archive_dept_id = %s ORDER BY l.id DESC', (dept_id,))
    letters = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template_string(DASHBOARD_HTML, page_title="أرشيف الإدارة", current_page="archive", letters=letters, dept_name=session['dept_name'], is_admin=is_admin)

@app.route('/quick_upload', methods=['GET', 'POST'])
def quick_upload():
    if 'dept_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('archive'))

if __name__ == '__main__':
    app.run(debug=True)
