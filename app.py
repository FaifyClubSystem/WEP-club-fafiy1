from flask import Flask, render_template_string, request, redirect, url_for, session, send_file
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # مفتاح سري لإدارة الجلسات (Sessions)

# إعدادات مجلد الملفات المرفوعة
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# إعداد قاعدة البيانات وتجهيز جدول المستخدمين والمستندات
def init_db():
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    
    # جدول الأرشيف للمستندات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            filename TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            uploaded_by TEXT NOT NULL
        )
    ''')
    
    # إضافة مستخدم افتراضي للتجربة (مدير عام)
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       ('admin', '123456', 'مدير عام'))
        
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== قالب تسجيل الدخول ====================
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول - نظام أرشفة نادي فيفا</title>
    <!-- Favicon (شعار المتصفح) -->
    <link rel="shortcut icon" href="{{ url_for('static', filename='logo.png') }}" type="image/png">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { background-color: #f8f9fa; height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-card { width: 100%; max-width: 400px; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); background: white; }
    </style>
</head>
<body>
    <div class="login-card">
        <h3 class="text-center mb-4 text-success">نادي فيفا الرياضي</h3>
        <h5 class="text-center mb-4 text-muted">تسجيل الدخول للنظام</h5>
        {% if error %}
            <div class="alert alert-danger" role="alert">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="mb-3">
                <label for="username" class="form-label">اسم المستخدم</label>
                <input type="text" class="form-control" id="username" name="username" required>
            </div>
            <div class="mb-3">
                <label for="password" class="form-label">كلمة المرور</label>
                <input type="password" class="form-control" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-success w-100">دخول</button>
        </form>
    </div>
</body>
</html>
'''

# ==================== قالب لوحة التحكم الرئيسية ====================
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة التحكم - نظام أرشفة نادي فيفا</title>
    <!-- Favicon (شعار المتصفح) -->
    <link rel="shortcut icon" href="{{ url_for('static', filename='logo.png') }}" type="image/png">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-success">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">نظام أرشفة نادي فيفا</a>
            <div class="d-flex">
                <span class="navbar-text text-white me-3">مرحباً، {{ session['username'] }} ({{ session['role'] }})</span>
                <a href="{{ url_for('logout') }}" class="btn btn-outline-light btn-sm">تسجيل الخروج</a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <!-- أزرار الإجراءات السريعة -->
        <div class="row mb-4">
            <div class="col-md-12">
                <a href="{{ url_for('quick_upload') }}" class="btn btn-success btn-lg">📁 رفع مستند جديد</a>
            </div>
        </div>

        <!-- جدول المستندات المؤرشفة -->
        <div class="card shadow-sm">
            <div class="card-header bg-white">
                <h5 class="mb-0 text-success">المستندات المؤرشفة</h5>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-striped align-middle">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>عنوان المستند</th>
                                <th>التصنيف</th>
                                <th>تاريخ الرفع</th>
                                <th>المستخدم المسؤول</th>
                                <th>الإجراءات</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for doc in documents %}
                            <tr>
                                <td>{{ doc[0] }}</td>
                                <td>{{ doc[1] }}</td>
                                <td><span class="badge bg-secondary">{{ doc[2] }}</span></td>
                                <td>{{ doc[4] }}</td>
                                <td>{{ doc[5] }}</td>
                                <td>
                                    <a href="{{ url_for('download_file', filename=doc[3]) }}" class="btn btn-sm btn-primary">تحميل</a>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="6" class="text-center text-muted">لا توجد مستندات مرفوعة حالياً.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
'''

# ==================== قالب صفحة الرفع الفوري ====================
UPLOAD_HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>رفع مستند جديد - نادي فيفا</title>
    <!-- Favicon (شعار المتصفح) -->
    <link rel="shortcut icon" href="{{ url_for('static', filename='logo.png') }}" type="image/png">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
</head>
<body class="bg-light">
    <div class="container mt-5" style="max-width: 600px;">
        <div class="card shadow-sm">
            <div class="card-header bg-success text-white">
                <h4 class="mb-0">رفع مستند جديد للأرشيف</h4>
            </div>
            <div class="card-body">
                <form method="POST" enctype="multipart/form-data">
                    <div class="mb-3">
                        <label for="title" class="form-label">عنوان المستند</label>
                        <input type="text" class="form-control" id="title" name="title" required>
                    </div>
                    <div class="mb-3">
                        <label for="category" class="form-label">التصنيف</label>
                        <select class="form-select" id="category" name="category" required>
                            <option value="مالي وإداري">مالي وإداري</option>
                            <option value="النشاط الرياضي">النشاط الرياضي</option>
                            <option value="قرارات وتعميمات">قرارات وتعميمات</option>
                            <option value="أخرى">أخرى</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label for="file" class="form-label">اختر الملف (PDF, الصور, المستندات)</label>
                        <input type="file" class="form-control" id="file" name="file" required>
                    </div>
                    <div class="d-flex justify-content-between">
                        <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">إلغاء والعودة</a>
                        <button type="submit" class="btn btn-success">رفع وحفظ</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</body>
</html>
'''

# ==================== مسارات التطبيق (Routes) ====================

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('archive.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['username'] = user[1]
            session['role'] = user[3]
            return redirect(url_for('dashboard'))
        else:
            error = 'اسم المستخدم أو كلمة المرور غير صحيحة.'
            
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents ORDER BY id DESC")
    documents = cursor.fetchall()
    conn.close()
    
    return render_template_string(DASHBOARD_HTML, documents=documents)

@app.route('/quick_upload', methods=['GET', 'POST'])
def quick_upload():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        title = request.form['title']
        category = request.form['category']
        file = request.files['file']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # إضافة ختم زمني لمنع تكرار أسماء الملفات
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            
            upload_date = datetime.now().strftime('%Y-%m-%d %H:%M')
            uploaded_by = session['username']
            
            conn = sqlite3.connect('archive.db')
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO documents (title, category, filename, upload_date, uploaded_by) 
                VALUES (?, ?, ?, ?, ?)
            """, (title, category, unique_filename, upload_date, uploaded_by))
            conn.commit()
            conn.close()
            
            return redirect(url_for('dashboard'))
            
    return render_template_string(UPLOAD_HTML)

@app.route('/download/<filename>')
def download_file(filename):
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
