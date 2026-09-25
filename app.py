import os
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import json
import os
app = Flask(__name__)
DB_NAME = 'quanly_thucte.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. Bảng Sinh Viên
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sinh_vien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mssv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            ma_lop TEXT NOT NULL
        )
    ''')

    # 2. Bảng Môn Học
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mon_hoc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_mon TEXT NOT NULL UNIQUE,
            ten_mon TEXT NOT NULL,
            so_tin_chi INTEGER DEFAULT 3
        )
    ''')

    # 3. Bảng Điểm (Khởi tạo trống, chỉ lưu khi giáo viên nhập điểm)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bang_diem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinh_vien_id INTEGER NOT NULL,
            mon_hoc_id INTEGER NOT NULL,
            diem_qt REAL,
            diem_ck REAL,
            diem_tk REAL,
            FOREIGN KEY (sinh_vien_id) REFERENCES sinh_vien (id) ON DELETE CASCADE,
            FOREIGN KEY (mon_hoc_id) REFERENCES mon_hoc (id) ON DELETE CASCADE,
            UNIQUE(sinh_vien_id, mon_hoc_id)
        )
    ''')

    # Đọc dữ liệu đúng theo khóa 'mon_hoc' và 'sinh_vien' từ data_seed.json
    so_luong_sv = conn.execute('SELECT COUNT(*) FROM sinh_vien').fetchone()[0]
    if so_luong_sv == 0 and os.path.exists('data_seed.json'):
        with open('data_seed.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        for mh in data.get('mon_hoc', []):
            conn.execute('''
                INSERT OR IGNORE INTO mon_hoc (ma_mon, ten_mon, so_tin_chi) 
                VALUES (?, ?, ?)
            ''', (mh['ma_mon'], mh['ten_mon'], mh.get('so_tin_chi', 3)))

        for sv in data.get('sinh_vien', []):
            conn.execute('''
                INSERT OR IGNORE INTO sinh_vien (mssv, ho_ten, ma_lop) 
                VALUES (?, ?, ?)
            ''', (sv['mssv'], sv['ho_ten'], sv['ma_lop']))

        conn.commit()

    conn.close()

# 1. Trang chủ: Danh sách các lớp học
@app.route('/')
def index():
    conn = get_db_connection()
    classes = conn.execute('''
        SELECT ma_lop, COUNT(id) as so_luong_sv 
        FROM sinh_vien 
        GROUP BY ma_lop
    ''').fetchall()
    conn.close()
    return render_template('index.html', classes=classes)

# 2. Xem sổ điểm theo Lớp và Môn học
@app.route('/class/<ma_lop>')
def class_detail(ma_lop):
    conn = get_db_connection()
    subjects = conn.execute('SELECT * FROM mon_hoc').fetchall()

    selected_mon_id = request.args.get('mon_id', type=int)
    if not selected_mon_id and subjects:
        selected_mon_id = subjects[0]['id']

    query = request.args.get('search', '')

    sql = '''
        SELECT 
            sv.id as sv_id,
            sv.mssv,
            sv.ho_ten,
            sv.ma_lop,
            bd.diem_qt,
            bd.diem_ck,
            bd.diem_tk
        FROM sinh_vien sv
        LEFT JOIN bang_diem bd ON sv.id = bd.sinh_vien_id AND bd.mon_hoc_id = ?
        WHERE sv.ma_lop = ?
    '''
    params = [selected_mon_id, ma_lop]

    if query:
        sql += ' AND (sv.ho_ten LIKE ? OR sv.mssv LIKE ?)'
        params.extend([f'%{query}%', f'%{query}%'])

    students = conn.execute(sql, params).fetchall()
    current_mon = conn.execute('SELECT * FROM mon_hoc WHERE id = ?', (selected_mon_id,)).fetchone()
    conn.close()

    return render_template(
        'class_detail.html',
        ma_lop=ma_lop,
        subjects=subjects,
        selected_mon_id=selected_mon_id,
        current_mon=current_mon,
        students=students,
        search_query=query
    )

# 3. Giáo viên cập nhật bảng điểm
@app.route('/class/<ma_lop>/update-grades', methods=['POST'])
def update_grades(ma_lop):
    mon_id = request.form.get('mon_id', type=int)
    conn = get_db_connection()
    students = conn.execute('SELECT id FROM sinh_vien WHERE ma_lop = ?', (ma_lop,)).fetchall()

    for sv in students:
        s_id = sv['id']
        qt_raw = request.form.get(f'diem_qt_{s_id}', '').strip()
        ck_raw = request.form.get(f'diem_ck_{s_id}', '').strip()

        if qt_raw != '' and ck_raw != '':
            try:
                diem_qt = max(0.0, min(10.0, float(qt_raw)))
                diem_ck = max(0.0, min(10.0, float(ck_raw)))
                diem_tk = round((diem_qt * 0.4) + (diem_ck * 0.6), 2)

                conn.execute('''
                    INSERT INTO bang_diem (sinh_vien_id, mon_hoc_id, diem_qt, diem_ck, diem_tk)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(sinh_vien_id, mon_hoc_id) 
                    DO UPDATE SET diem_qt=excluded.diem_qt, diem_ck=excluded.diem_ck, diem_tk=excluded.diem_tk
                ''', (s_id, mon_id, diem_qt, diem_ck, diem_tk))
            except ValueError:
                pass

    conn.commit()
    conn.close()
    return redirect(url_for('class_detail', ma_lop=ma_lop, mon_id=mon_id))

# 4. Thêm sinh viên mới
@app.route('/class/<ma_lop>/add-student', methods=['POST'])
def add_student(ma_lop):
    mssv = request.form['mssv'].strip().upper()
    ho_ten = request.form['ho_ten'].strip()
    mon_id = request.form.get('mon_id', type=int)

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO sinh_vien (mssv, ho_ten, ma_lop) VALUES (?, ?, ?)',
                     (mssv, ho_ten, ma_lop))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('class_detail', ma_lop=ma_lop, mon_id=mon_id))

# 5. Xóa sinh viên
@app.route('/class/<ma_lop>/delete-student/<int:student_id>')
def delete_student(ma_lop, student_id):
    mon_id = request.args.get('mon_id', type=int)
    conn = get_db_connection()
    conn.execute('DELETE FROM sinh_vien WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('class_detail', ma_lop=ma_lop, mon_id=mon_id))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)