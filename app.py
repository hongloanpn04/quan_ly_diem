import json
import math
import os
import sqlite3
import sys
from decimal import Decimal, ROUND_HALF_UP

from flask import Flask, jsonify, render_template, request
from jinja2 import TemplateNotFound

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "quanly_thucte.db")
SEED_FILE = os.path.join(BASE_DIR, "data_seed.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")                   # chứa css/, js/, ảnh
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates", "html")     # chứa các file .html

# static_url_path="" để trang HTML gọi được css/style.css và js/xxx.js
# (static/css/style.css -> /css/style.css, static/js/class.js -> /js/class.js)
app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="",
    template_folder=TEMPLATES_DIR,
)
app.json.ensure_ascii = False  # trả tiếng Việt có dấu trong JSON


# ===============================
# DATABASE
# ===============================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # bắt buộc để ON DELETE CASCADE hoạt động
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sinh_vien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mssv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            ma_lop TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mon_hoc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_mon TEXT NOT NULL UNIQUE,
            ten_mon TEXT NOT NULL,
            so_tin_chi INTEGER DEFAULT 3
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bang_diem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinh_vien_id INTEGER NOT NULL,
            mon_hoc_id INTEGER NOT NULL,
            diem_qt REAL,
            diem_ck REAL,
            diem_tk REAL,
            FOREIGN KEY (sinh_vien_id) REFERENCES sinh_vien (id) ON DELETE CASCADE,
            FOREIGN KEY (mon_hoc_id) REFERENCES mon_hoc (id) ON DELETE CASCADE,
            UNIQUE (sinh_vien_id, mon_hoc_id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_sv_lop ON sinh_vien (ma_lop)")

    # Nạp dữ liệu mẫu từ data_seed.json (chỉ nạp bảng nào đang trống)
    if os.path.exists(SEED_FILE):
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if conn.execute("SELECT COUNT(*) FROM mon_hoc").fetchone()[0] == 0:
            for mh in data.get("mon_hoc", []):
                conn.execute(
                    "INSERT OR IGNORE INTO mon_hoc (ma_mon, ten_mon, so_tin_chi) VALUES (?, ?, ?)",
                    (mh["ma_mon"], mh["ten_mon"], mh.get("so_tin_chi", 3)),
                )

        if conn.execute("SELECT COUNT(*) FROM sinh_vien").fetchone()[0] == 0:
            for sv in data.get("sinh_vien", []):
                conn.execute(
                    "INSERT OR IGNORE INTO sinh_vien (mssv, ho_ten, ma_lop) VALUES (?, ?, ?)",
                    (sv["mssv"].strip().upper(), sv["ho_ten"].strip(), sv["ma_lop"].strip()),
                )

    conn.commit()
    conn.close()


def reset_db():
    """Xóa database cũ để nạp lại từ data_seed.json."""
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    init_db()


# ===============================
# HÀM HỖ TRỢ
# ===============================

def parse_diem(value):
    """Trả về float trong [0, 10], hoặc None nếu để trống. Sai định dạng -> ValueError."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError
    d = float(value)
    if math.isnan(d) or d < 0 or d > 10:
        raise ValueError
    return d


def tinh_tong_ket(diem_qt, diem_ck):
    """40% quá trình + 60% cuối kỳ, làm tròn 1 chữ số (half-up, khớp với toFixed(1) bên JS)."""
    tk = Decimal(str(diem_qt)) * Decimal("0.4") + Decimal(str(diem_ck)) * Decimal("0.6")
    return float(tk.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def loi(message, status=400):
    return jsonify({"message": message}), status


# ===============================
# TRANG GIAO DIỆN (HTML tĩnh)
# ===============================

def gui_trang(*ten_file):
    for ten in ten_file:
        try:
            return render_template(ten)
        except TemplateNotFound:
            continue
    return "Không tìm thấy file giao diện trong thư mục templates/html/", 404


@app.route("/")
@app.route("/index.html")
def trang_chu():
    return gui_trang("index.html")


@app.route("/class.html")
def trang_lop():
    # Chấp nhận cả tên class.html lẫn class_detail.html
    return gui_trang("class.html", "class_detail.html")


# ===============================
# API
# ===============================

# 1. Danh sách lớp
@app.route("/api/classes")
def api_classes():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT ma_lop, COUNT(id) AS so_luong_sv
        FROM sinh_vien
        GROUP BY ma_lop
        ORDER BY ma_lop
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# 2. Chi tiết lớp: sinh viên + điểm của 1 môn + danh sách môn
@app.route("/api/class/<ma_lop>")
def api_class_detail(ma_lop):
    conn = get_db_connection()

    subjects = conn.execute("SELECT * FROM mon_hoc ORDER BY id").fetchall()
    if not subjects:
        conn.close()
        return loi("Chưa có môn học nào trong hệ thống.", 404)

    ids_hop_le = {s["id"] for s in subjects}
    mon_id = request.args.get("mon_id", type=int)  # "null" hoặc rỗng -> None
    if mon_id not in ids_hop_le:
        mon_id = subjects[0]["id"]

    students = conn.execute("""
        SELECT
            sv.id AS sv_id,
            sv.mssv,
            sv.ho_ten,
            sv.ma_lop,
            bd.diem_qt,
            bd.diem_ck,
            bd.diem_tk
        FROM sinh_vien sv
        LEFT JOIN bang_diem bd
               ON bd.sinh_vien_id = sv.id AND bd.mon_hoc_id = ?
        WHERE sv.ma_lop = ?
        ORDER BY sv.mssv
    """, (mon_id, ma_lop)).fetchall()
    conn.close()

    return jsonify({
        "ma_lop": ma_lop,
        "current_mon_id": mon_id,
        "subjects": [dict(s) for s in subjects],
        "students": [dict(s) for s in students],
    })


# 3. Lưu bảng điểm
@app.route("/api/class/<ma_lop>/update-grades", methods=["POST"])
def api_update_grades(ma_lop):
    body = request.get_json(silent=True) or {}

    try:
        mon_id = int(body.get("mon_id"))
    except (TypeError, ValueError):
        return loi("Thiếu hoặc sai mã môn học (mon_id).")

    grades = body.get("grades")
    if not isinstance(grades, list):
        return loi("Dữ liệu điểm không hợp lệ.")

    conn = get_db_connection()

    if not conn.execute("SELECT 1 FROM mon_hoc WHERE id = ?", (mon_id,)).fetchone():
        conn.close()
        return loi("Môn học không tồn tại.", 404)

    # Chỉ cho phép sửa điểm sinh viên thuộc đúng lớp này
    sv_trong_lop = {
        r["id"]: r["mssv"]
        for r in conn.execute("SELECT id, mssv FROM sinh_vien WHERE ma_lop = ?", (ma_lop,))
    }

    # Kiểm tra toàn bộ trước, không ghi dở dang
    hop_le = []
    for g in grades:
        try:
            sv_id = int(g.get("sv_id"))
        except (TypeError, ValueError, AttributeError):
            conn.close()
            return loi("Có dòng điểm thiếu mã sinh viên.")

        if sv_id not in sv_trong_lop:
            conn.close()
            return loi(f"Sinh viên (id {sv_id}) không thuộc lớp {ma_lop}.")

        try:
            diem_qt = parse_diem(g.get("diem_qt"))
            diem_ck = parse_diem(g.get("diem_ck"))
        except (TypeError, ValueError):
            conn.close()
            return loi(f"Điểm của {sv_trong_lop[sv_id]} phải là số từ 0 đến 10.")

        hop_le.append((sv_id, diem_qt, diem_ck))

    try:
        for sv_id, diem_qt, diem_ck in hop_le:
            if diem_qt is None and diem_ck is None:
                # Xóa trắng cả hai ô -> bỏ bản ghi điểm
                conn.execute(
                    "DELETE FROM bang_diem WHERE sinh_vien_id = ? AND mon_hoc_id = ?",
                    (sv_id, mon_id),
                )
                continue

            diem_tk = (
                tinh_tong_ket(diem_qt, diem_ck)
                if diem_qt is not None and diem_ck is not None
                else None
            )
            conn.execute("""
                INSERT INTO bang_diem (sinh_vien_id, mon_hoc_id, diem_qt, diem_ck, diem_tk)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (sinh_vien_id, mon_hoc_id) DO UPDATE SET
                    diem_qt = excluded.diem_qt,
                    diem_ck = excluded.diem_ck,
                    diem_tk = excluded.diem_tk
            """, (sv_id, mon_id, diem_qt, diem_ck, diem_tk))
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        conn.close()
        return loi("Lỗi cơ sở dữ liệu khi lưu điểm.", 500)

    conn.close()
    return jsonify({"message": "Đã lưu bảng điểm.", "so_dong": len(hop_le)})


# 4. Thêm sinh viên
@app.route("/api/class/<ma_lop>/add-student", methods=["POST"])
def api_add_student(ma_lop):
    body = request.get_json(silent=True) or {}
    mssv = str(body.get("mssv", "")).strip().upper()
    ho_ten = " ".join(str(body.get("ho_ten", "")).split())  # gộp khoảng trắng thừa

    if not mssv or not ho_ten:
        return loi("MSSV và họ tên không được để trống.")

    conn = get_db_connection()
    try:
        cur = conn.execute(
            "INSERT INTO sinh_vien (mssv, ho_ten, ma_lop) VALUES (?, ?, ?)",
            (mssv, ho_ten, ma_lop),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return loi(f"MSSV {mssv} đã tồn tại trong hệ thống.", 409)
    conn.close()

    return jsonify({"message": "Đã thêm sinh viên.", "sv_id": new_id}), 201


# 5. Xóa sinh viên (kèm toàn bộ điểm của sinh viên đó)
@app.route("/api/class/<ma_lop>/delete-student/<int:student_id>", methods=["DELETE"])
def api_delete_student(ma_lop, student_id):
    conn = get_db_connection()
    cur = conn.execute(
        "DELETE FROM sinh_vien WHERE id = ? AND ma_lop = ?",
        (student_id, ma_lop),
    )
    conn.commit()
    da_xoa = cur.rowcount
    conn.close()

    if da_xoa == 0:
        return loi("Không tìm thấy sinh viên trong lớp này.", 404)
    return jsonify({"message": "Đã xóa sinh viên."})


# ===============================
# KHỞI ĐỘNG
# ===============================

# Gọi ở mức module để chạy được cả với gunicorn/flask run, không chỉ python app.py
init_db()

if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_db()
        print("Đã xóa database cũ và nạp lại từ data_seed.json")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)