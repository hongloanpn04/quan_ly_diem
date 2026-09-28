import json
import math
import os
import sqlite3
import sys
from decimal import Decimal, ROUND_HALF_UP

from flask import Flask, jsonify, render_template, request, session
from jinja2 import TemplateNotFound

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "quanly_thucte.db")
SEED_FILE = os.path.join(BASE_DIR, "data_seed.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates", "html")

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="",
    template_folder=TEMPLATES_DIR,
)
app.secret_key = "ptit_he_thong_quan_ly_dao_tao_secret_key"
app.json.ensure_ascii = False


# ===============================
# DATABASE & INIT
# ===============================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()

    # 1. Bảng người dùng
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nguoi_dung (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ten_dang_nhap TEXT NOT NULL UNIQUE,
            mat_khau TEXT NOT NULL,
            vai_tro TEXT NOT NULL CHECK(vai_tro IN ('ADMIN', 'GIANG_VIEN', 'SINH_VIEN'))
        )
    """)

    # 2. Bảng giảng viên
    conn.execute("""
        CREATE TABLE IF NOT EXISTS giang_vien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mgv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            email TEXT,
            sdt TEXT,
            khoa TEXT,
            quyen_quan_ly_sv INTEGER DEFAULT 0,
            nguoi_dung_id INTEGER,
            FOREIGN KEY (nguoi_dung_id) REFERENCES nguoi_dung (id) ON DELETE CASCADE
        )
    """)

    # 3. Bảng sinh viên
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sinh_vien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mssv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            ma_lop TEXT NOT NULL,
            chuyen_nganh TEXT DEFAULT 'Cong nghe Thong tin',
            gmail TEXT,
            sdt TEXT,
            nguoi_dung_id INTEGER,
            FOREIGN KEY (nguoi_dung_id) REFERENCES nguoi_dung (id) ON DELETE SET NULL
        )
    """)

    # 4. Bảng môn học
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mon_hoc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ma_mon TEXT NOT NULL UNIQUE,
            ten_mon TEXT NOT NULL,
            so_tin_chi INTEGER DEFAULT 3
        )
    """)

    # 5. Bảng điểm
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

    # Nạp dữ liệu mẫu ban đầu nếu rỗng
    if os.path.exists(SEED_FILE) and conn.execute("SELECT COUNT(*) FROM mon_hoc").fetchone()[0] == 0:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Nạp môn học
        for mh in data.get("mon_hoc", []):
            conn.execute(
                "INSERT OR IGNORE INTO mon_hoc (ma_mon, ten_mon, so_tin_chi) VALUES (?, ?, ?)",
                (mh["ma_mon"], mh["ten_mon"], mh.get("so_tin_chi", 3)),
            )

        # Nạp giảng viên & tài khoản (mật khẩu mặc định 123456)
        for gv in data.get("giang_vien", []):
            quyen = 1 if gv.get("quyen_quan_ly_sv") else 0
            vai_tro = "ADMIN" if quyen == 1 else "GIANG_VIEN"
            cur = conn.execute(
                "INSERT OR IGNORE INTO nguoi_dung (ten_dang_nhap, mat_khau, vai_tro) VALUES (?, '123456', ?)",
                (gv["mgv"].strip().upper(), vai_tro)
            )
            u_id = cur.lastrowid
            conn.execute(
                """INSERT OR IGNORE INTO giang_vien (mgv, ho_ten, email, sdt, khoa, quyen_quan_ly_sv, nguoi_dung_id)
                   VALUES (?, ?, ?, '0912345678', 'Cong nghe Thong tin', ?, ?)""",
                (gv["mgv"].strip().upper(), gv["ho_ten"].strip(), gv.get("email"), quyen, u_id)
            )

        # Nạp sinh viên & tài khoản (mật khẩu mặc định 123456)
        for sv in data.get("sinh_vien", []):
            mssv = sv["mssv"].strip().upper()
            cur = conn.execute(
                "INSERT OR IGNORE INTO nguoi_dung (ten_dang_nhap, mat_khau, vai_tro) VALUES (?, '123456', 'SINH_VIEN')",
                (mssv,)
            )
            u_id = cur.lastrowid
            conn.execute(
                """INSERT OR IGNORE INTO sinh_vien (mssv, ho_ten, ma_lop, chuyen_nganh, gmail, sdt, nguoi_dung_id)
                   VALUES (?, ?, ?, 'Cong nghe Thong tin', ?, '0987654321', ?)""",
                (mssv, sv["ho_ten"].strip(), sv["ma_lop"].strip(), f"{mssv.lower()}@gmail.com", u_id)
            )

    conn.commit()
    conn.close()


def parse_diem(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError
    d = float(value)
    if math.isnan(d) or d < 0 or d > 10:
        raise ValueError
    return d


def tinh_tong_ket(diem_qt, diem_ck):
    tk = Decimal(str(diem_qt)) * Decimal("0.4") + Decimal(str(diem_ck)) * Decimal("0.6")
    return float(tk.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def loi(message, status=400):
    return jsonify({"message": message}), status


# ===============================
# ROUTE GIAO DIỆN
# ===============================

def gui_trang(*ten_file):
    for ten in ten_file:
        try:
            return render_template(ten)
        except TemplateNotFound:
            continue
    return "Không tìm thấy file giao diện trong templates/html/", 404


@app.route("/")
@app.route("/index.html")
def trang_chu():
    return gui_trang("index.html")


@app.route("/class.html")
def trang_lop():
    return gui_trang("class.html", "class_detail.html")


# ===============================
# AUTHENTICATION APIS
# ===============================

@app.route("/api/dang-nhap", methods=["POST"])
def api_dang_nhap():
    body = request.get_json(silent=True) or {}
    tk = str(body.get("tai_khoan", "")).strip().upper()
    mk = str(body.get("mat_khau", "")).strip()

    if not tk or not mk:
        return loi("Vui lòng nhập tài khoản và mật khẩu.")

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM nguoi_dung WHERE ten_dang_nhap = ? AND mat_khau = ?", (tk, mk)
    ).fetchone()

    if not user:
        conn.close()
        return loi("Tài khoản hoặc mật khẩu không đúng.", 401)

    vai_tro = user["vai_tro"]
    ho_ten = tk
    is_admin = False

    if vai_tro in ("ADMIN", "GIANG_VIEN"):
        gv = conn.execute("SELECT * FROM giang_vien WHERE nguoi_dung_id = ?", (user["id"],)).fetchone()
        if gv:
            ho_ten = gv["ho_ten"]
            is_admin = (gv["quyen_quan_ly_sv"] == 1)
    else:
        sv = conn.execute("SELECT * FROM sinh_vien WHERE nguoi_dung_id = ?", (user["id"],)).fetchone()
        if sv:
            ho_ten = sv["ho_ten"]

    conn.close()

    session["user_id"] = user["id"]
    session["ten_dang_nhap"] = tk
    session["vai_tro"] = vai_tro
    session["ho_ten"] = ho_ten
    session["is_admin"] = is_admin

    return jsonify({
        "message": "Đăng nhập thành công!",
        "user": {
            "ten_dang_nhap": tk,
            "ho_ten": ho_ten,
            "vai_tro": vai_tro,
            "is_admin": is_admin
        }
    })


@app.route("/api/dang-xuat", methods=["POST"])
def api_dang_xuat():
    session.clear()
    return jsonify({"message": "Đã đăng xuất thành công."})


@app.route("/api/me", methods=["GET"])
def api_me():
    if "user_id" not in session:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "user": {
            "ten_dang_nhap": session.get("ten_dang_nhap"),
            "ho_ten": session.get("ho_ten"),
            "vai_tro": session.get("vai_tro"),
            "is_admin": session.get("is_admin", False)
        }
    })


@app.route("/api/doi-mat-khau", methods=["POST"])
def api_doi_mat_khau():
    if "user_id" not in session:
        return loi("Chưa đăng nhập.", 401)

    body = request.get_json(silent=True) or {}
    mk_cu = str(body.get("mk_cu", "")).strip()
    mk_moi = str(body.get("mk_moi", "")).strip()

    if len(mk_moi) < 6:
        return loi("Mật khẩu mới phải từ 6 ký tự trở lên.")

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM nguoi_dung WHERE id = ?", (session["user_id"],)).fetchone()
    if not user or user["mat_khau"] != mk_cu:
        conn.close()
        return loi("Mật khẩu cũ không chính xác.")

    conn.execute("UPDATE nguoi_dung SET mat_khau = ? WHERE id = ?", (mk_moi, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đổi mật khẩu thành công!"})


# ===============================
# SINH VIÊN: XEM ĐIỂM CÁ NHÂN
# ===============================

@app.route("/api/sinh-vien/bang-diem")
def api_sv_bang_diem():
    if "user_id" not in session:
        return loi("Chưa đăng nhập.", 401)
    if session.get("vai_tro") != "SINH_VIEN":
        return loi("Chỉ sinh viên mới có quyền xem bảng điểm cá nhân.", 403)

    conn = get_db_connection()
    sv = conn.execute("SELECT * FROM sinh_vien WHERE nguoi_dung_id = ?", (session["user_id"],)).fetchone()
    if not sv:
        conn.close()
        return loi("Không tìm thấy thông tin sinh viên.", 404)

    rows = conn.execute("""
        SELECT 
            mh.ma_mon, 
            mh.ten_mon, 
            mh.so_tin_chi, 
            bd.diem_qt, 
            bd.diem_ck, 
            bd.diem_tk
        FROM mon_hoc mh
        LEFT JOIN bang_diem bd ON mh.id = bd.mon_hoc_id AND bd.sinh_vien_id = ?
        ORDER BY mh.ma_mon
    """, (sv["id"],)).fetchall()
    conn.close()

    return jsonify({
        "sinh_vien": dict(sv),
        "bang_diem": [dict(r) for r in rows]
    })


# ===============================
# GIẢNG VIÊN & ADMIN: QUẢN LÝ LỚP & ĐIỂM
# ===============================

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


@app.route("/api/class/<ma_lop>")
def api_class_detail(ma_lop):
    conn = get_db_connection()
    subjects = conn.execute("SELECT * FROM mon_hoc ORDER BY id").fetchall()
    if not subjects:
        conn.close()
        return loi("Chưa có môn học nào.", 404)

    ids_hop_le = {s["id"] for s in subjects}
    mon_id = request.args.get("mon_id", type=int)
    if mon_id not in ids_hop_le:
        mon_id = subjects[0]["id"]

    students = conn.execute("""
        SELECT
            sv.id AS sv_id,
            sv.mssv,
            sv.ho_ten,
            sv.ma_lop,
            sv.chuyen_nganh,
            sv.gmail,
            sv.sdt,
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
        "is_admin": session.get("is_admin", False)
    })


@app.route("/api/class/<ma_lop>/update-grades", methods=["POST"])
def api_update_grades(ma_lop):
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Chỉ giảng viên mới có quyền nhập điểm.", 403)

    body = request.get_json(silent=True) or {}
    try:
        mon_id = int(body.get("mon_id"))
    except (TypeError, ValueError):
        return loi("Thiếu hoặc sai mã môn học.")

    grades = body.get("grades")
    if not isinstance(grades, list):
        return loi("Dữ liệu điểm không hợp lệ.")

    conn = get_db_connection()
    sv_trong_lop = {
        r["id"]: r["mssv"]
        for r in conn.execute("SELECT id, mssv FROM sinh_vien WHERE ma_lop = ?", (ma_lop,))
    }

    hop_le = []
    for g in grades:
        try:
            sv_id = int(g.get("sv_id"))
        except (TypeError, ValueError, AttributeError):
            conn.close()
            return loi("Có dòng điểm thiếu mã sinh viên.")

        if sv_id not in sv_trong_lop:
            conn.close()
            return loi(f"Sinh viên không thuộc lớp {ma_lop}.")

        try:
            diem_qt = parse_diem(g.get("diem_qt"))
            diem_ck = parse_diem(g.get("diem_ck"))
        except (TypeError, ValueError):
            conn.close()
            return loi(f"Điểm của {sv_trong_lop[sv_id]} phải từ 0 đến 10.")

        hop_le.append((sv_id, diem_qt, diem_ck))

    try:
        for sv_id, diem_qt, diem_ck in hop_le:
            if diem_qt is None and diem_ck is None:
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
    return jsonify({"message": "Đã lưu bảng điểm thành công!"})


# ===============================
# CRUD SINH VIÊN (CHỈ DÀNH CHO ADMIN)
# ===============================

# 1. Thêm sinh viên
@app.route("/api/class/<ma_lop>/add-student", methods=["POST"])
def api_add_student(ma_lop):
    if not session.get("is_admin"):
        return loi("Chỉ giảng viên có quyền Quản trị (Admin) mới được thêm sinh viên!", 403)

    body = request.get_json(silent=True) or {}
    mssv = str(body.get("mssv", "")).strip().upper()
    ho_ten = " ".join(str(body.get("ho_ten", "")).split())
    sdt = str(body.get("sdt", "")).strip()
    gmail = str(body.get("gmail", "")).strip()
    chuyen_nganh = str(body.get("chuyen_nganh", "Cong nghe Thong tin")).strip()

    if not mssv or not ho_ten:
        return loi("MSSV và họ tên không được để trống.")

    conn = get_db_connection()
    try:
        cur_u = conn.execute(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau, vai_tro) VALUES (?, '123456', 'SINH_VIEN')",
            (mssv,)
        )
        u_id = cur_u.lastrowid

        cur_sv = conn.execute(
            """INSERT INTO sinh_vien (mssv, ho_ten, ma_lop, chuyen_nganh, gmail, sdt, nguoi_dung_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (mssv, ho_ten, ma_lop, chuyen_nganh, gmail, sdt, u_id)
        )
        conn.commit()
        new_id = cur_sv.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return loi(f"MSSV {mssv} đã tồn tại trong hệ thống.", 409)
    conn.close()

    return jsonify({"message": "Đã thêm sinh viên thành công!", "sv_id": new_id}), 201


# 2. Sửa thông tin sinh viên
@app.route("/api/class/<ma_lop>/edit-student/<int:student_id>", methods=["PUT"])
def api_edit_student(ma_lop, student_id):
    if not session.get("is_admin"):
        return loi("Chỉ giảng viên có quyền Quản trị (Admin) mới được sửa thông tin sinh viên!", 403)

    body = request.get_json(silent=True) or {}
    ho_ten = " ".join(str(body.get("ho_ten", "")).split())
    sdt = str(body.get("sdt", "")).strip()
    gmail = str(body.get("gmail", "")).strip()
    chuyen_nganh = str(body.get("chuyen_nganh", "")).strip()

    if not ho_ten:
        return loi("Họ tên không được để trống.")

    conn = get_db_connection()
    conn.execute(
        """UPDATE sinh_vien 
           SET ho_ten = ?, sdt = ?, gmail = ?, chuyen_nganh = ?
           WHERE id = ? AND ma_lop = ?""",
        (ho_ten, sdt, gmail, chuyen_nganh, student_id, ma_lop)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã cập nhật thông tin sinh viên thành công!"})


# 3. Xóa sinh viên (Cascade xóa tài khoản và điểm)
@app.route("/api/class/<ma_lop>/delete-student/<int:student_id>", methods=["DELETE"])
def api_delete_student(ma_lop, student_id):
    if not session.get("is_admin"):
        return loi("Chỉ giảng viên có quyền Quản trị (Admin) mới được xóa sinh viên!", 403)

    conn = get_db_connection()
    sv = conn.execute("SELECT nguoi_dung_id FROM sinh_vien WHERE id = ? AND ma_lop = ?", (student_id, ma_lop)).fetchone()
    if not sv:
        conn.close()
        return loi("Không tìm thấy sinh viên.", 404)

    u_id = sv["nguoi_dung_id"]
    conn.execute("DELETE FROM sinh_vien WHERE id = ?", (student_id,))
    if u_id:
        conn.execute("DELETE FROM nguoi_dung WHERE id = ?", (u_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Đã xóa sinh viên và toàn bộ điểm liên quan!"})


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)