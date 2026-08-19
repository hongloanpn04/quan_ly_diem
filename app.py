from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import json
import os

app = Flask(__name__)
DB_NAME = 'quanly_n24.db'  # Đổi tên database để tạo mới

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. Tạo bảng Lớp học
    conn.execute('''
        CREATE TABLE IF NOT EXISTS lop_hoc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_lop TEXT NOT NULL UNIQUE,
            ten_lop TEXT NOT NULL
        )
    ''')
    
    # 2. Tạo bảng Sinh viên liên kết với Lớp qua lop_id
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sinh_vien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mssv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            lop_id INTEGER NOT NULL,
            diem_qt REAL DEFAULT 0,
            diem_ck REAL DEFAULT 0,
            diem_tk REAL DEFAULT 0,
            FOREIGN KEY (lop_id) REFERENCES lop_hoc (id) ON DELETE CASCADE
        )
    ''')

    # 3. ĐỌC VÀ NẠP DỮ LIỆU TỰ ĐỘNG TỪ FILE data_seed.json
    so_luong_lop = conn.execute('SELECT COUNT(*) FROM lop_hoc').fetchone()[0]
    if so_luong_lop == 0 and os.path.exists('data_seed.json'):
        with open('data_seed.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            cursor = conn.execute('INSERT INTO lop_hoc (ma_lop, ten_lop) VALUES (?, ?)', 
                                  (item['ma_lop'], item['ten_lop']))
            lop_id = cursor.lastrowid
            
            for sv in item.get('sinh_vien', []):
                d_qt = float(sv.get('diem_qt', 0))
                d_ck = float(sv.get('diem_ck', 0))
                d_tk = round((d_qt * 0.4) + (d_ck * 0.6), 2)
                conn.execute('''
                    INSERT INTO sinh_vien (mssv, ho_ten, lop_id, diem_qt, diem_ck, diem_tk)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (sv['mssv'], sv['ho_ten'], lop_id, d_qt, d_ck, d_tk))
        
        conn.commit()

    conn.close()

# Trang chủ: Danh sách các lớp học
@app.route('/')
def index():
    conn = get_db_connection()
    classes = conn.execute('''
        SELECT lop_hoc.*, COUNT(sinh_vien.id) as so_luong_sv 
        FROM lop_hoc 
        LEFT JOIN sinh_vien ON lop_hoc.id = sinh_vien.lop_id 
        GROUP BY lop_hoc.id
    ''').fetchall()
    conn.close()
    return render_template('index.html', classes=classes)

# Thêm lớp học mới
@app.route('/add-class', methods=['POST'])
def add_class():
    ma_lop = request.form['ma_lop'].strip().upper()
    ten_lop = request.form['ten_lop'].strip()
    if ma_lop and ten_lop:
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO lop_hoc (ma_lop, ten_lop) VALUES (?, ?)', (ma_lop, ten_lop))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()
    return redirect(url_for('index'))

# Chi tiết lớp học: Xem danh sách sinh viên của lớp đó
@app.route('/class/<int:class_id>')
def class_detail(class_id):
    conn = get_db_connection()
    current_class = conn.execute('SELECT * FROM lop_hoc WHERE id = ?', (class_id,)).fetchone()
    
    query = request.args.get('search', '')
    if query:
        students = conn.execute('''
            SELECT * FROM sinh_vien 
            WHERE lop_id = ? AND (ho_ten LIKE ? OR mssv LIKE ?)
        ''', (class_id, f'%{query}%', f'%{query}%')).fetchall()
    else:
        students = conn.execute('SELECT * FROM sinh_vien WHERE lop_id = ?', (class_id,)).fetchall()
        
    conn.close()
    return render_template('class_detail.html', current_class=current_class, students=students, search_query=query)

# Thêm sinh viên vào lớp
@app.route('/class/<int:class_id>/add-student', methods=['POST'])
def add_student(class_id):
    mssv = request.form['mssv'].strip().upper()
    ho_ten = request.form['ho_ten'].strip()
    diem_qt = float(request.form.get('diem_qt', 0))
    diem_ck = float(request.form.get('diem_ck', 0))
    diem_tk = round((diem_qt * 0.4) + (diem_ck * 0.6), 2)

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO sinh_vien (mssv, ho_ten, lop_id, diem_qt, diem_ck, diem_tk)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (mssv, ho_ten, class_id, diem_qt, diem_ck, diem_tk))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('class_detail', class_id=class_id))

# Xóa sinh viên khỏi lớp
@app.route('/class/<int:class_id>/delete-student/<int:student_id>')
def delete_student(class_id, student_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM sinh_vien WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('class_detail', class_id=class_id))
# 6. Cập nhật hàng loạt bảng điểm của cả lớp
@app.route('/class/<int:class_id>/update-grades', methods=['POST'])
def update_grades(class_id):
    conn = get_db_connection()
    students = conn.execute('SELECT id FROM sinh_vien WHERE lop_id = ?', (class_id,)).fetchall()
    
    for sv in students:
        s_id = sv['id']
        qt_key = f'diem_qt_{s_id}'
        ck_key = f'diem_ck_{s_id}'
        
        if qt_key in request.form and ck_key in request.form:
            try:
                diem_qt = float(request.form[qt_key])
                diem_ck = float(request.form[ck_key])
                # Giới hạn điểm từ 0 đến 10
                diem_qt = max(0.0, min(10.0, diem_qt))
                diem_ck = max(0.0, min(10.0, diem_ck))
                diem_tk = round((diem_qt * 0.4) + (diem_ck * 0.6), 2)
                
                conn.execute('''
                    UPDATE sinh_vien 
                    SET diem_qt = ?, diem_ck = ?, diem_tk = ? 
                    WHERE id = ?
                ''', (diem_qt, diem_ck, diem_tk, s_id))
            except ValueError:
                pass

    conn.commit()
    conn.close()
    return redirect(url_for('class_detail', class_id=class_id))

# 7. Sửa thông tin / điểm của một sinh viên cụ thể
@app.route('/class/<int:class_id>/edit-student/<int:student_id>', methods=['POST'])
def edit_student(class_id, student_id):
    ho_ten = request.form['ho_ten'].strip()
    diem_qt = float(request.form.get('diem_qt', 0))
    diem_ck = float(request.form.get('diem_ck', 0))
    diem_tk = round((diem_qt * 0.4) + (diem_ck * 0.6), 2)

    conn = get_db_connection()
    conn.execute('''
        UPDATE sinh_vien 
        SET ho_ten = ?, diem_qt = ?, diem_ck = ?, diem_tk = ? 
        WHERE id = ?
    ''', (ho_ten, diem_qt, diem_ck, diem_tk, student_id))
    conn.commit()
    conn.close()
    return redirect(url_for('class_detail', class_id=class_id))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)