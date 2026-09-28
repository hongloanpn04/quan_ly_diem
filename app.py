import json
import math
import os
import sqlite3
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
app.secret_key = "ptit_secret_key_no_hash"
app.json.ensure_ascii = False


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()

    # 1. Bảng vai trò
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vai_tro (
            id INTEGER PRIMARY KEY,
            ten_vai_tro TEXT NOT NULL UNIQUE
        )
    """)

    # 2. Bảng người dùng (Lưu mật khẩu dạng text thuần)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nguoi_dung (
            id INTEGER PRIMARY KEY,
            ten_dang_nhap TEXT NOT NULL UNIQUE,
            mat_khau TEXT NOT NULL,
            vai_tro_id INTEGER NOT NULL,
            FOREIGN KEY (vai_tro_id) REFERENCES vai_tro (id)
        )
    """)

    # 3. Bảng lớp học
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lop_hoc (
            id INTEGER PRIMARY KEY,
            ma_lop TEXT NOT NULL UNIQUE,
            ten_lop TEXT NOT NULL,
            khoa TEXT
        )
    """)

    # 4. Bảng giảng viên
    conn.execute("""
        CREATE TABLE IF NOT EXISTS giang_vien (
            id INTEGER PRIMARY KEY,
            ma_giang_vien TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            email TEXT,
            so_dien_thoai TEXT,
            nguoi_dung_id INTEGER UNIQUE,
            FOREIGN KEY (nguoi_dung_id) REFERENCES nguoi_dung (id) ON DELETE CASCADE
        )
    """)

    # 5. Bảng sinh viên
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sinh_vien (
            id INTEGER PRIMARY KEY,
            ma_sinh_vien TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            ngay_sinh TEXT,
            gioi_tinh TEXT,
            email TEXT,
            so_dien_thoai TEXT,
            dia_chi TEXT,
            lop_hoc_id INTEGER NOT NULL,
            nguoi_dung_id INTEGER UNIQUE,
            FOREIGN KEY (lop_hoc_id) REFERENCES lop_hoc (id) ON DELETE CASCADE,
            FOREIGN KEY (nguoi_dung_id) REFERENCES nguoi_dung (id) ON DELETE SET NULL
        )
    """)

    # 6. Bảng môn học
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mon_hoc (
            id INTEGER PRIMARY KEY,
            ma_mon TEXT NOT NULL UNIQUE,
            ten_mon TEXT NOT NULL,
            so_tin_chi INTEGER DEFAULT 3
        )
    """)

    # 7. Bảng phân công giảng dạy
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phan_cong_giang_day (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giang_vien_id INTEGER NOT NULL,
            mon_hoc_id INTEGER NOT NULL,
            lop_hoc_id INTEGER NOT NULL,
            hoc_ky INTEGER DEFAULT 1,
            nam_hoc TEXT DEFAULT '2024-2025',
            trang_thai TEXT DEFAULT 'DANG_DAY' CHECK(trang_thai IN ('DANG_DAY', 'HOAN_THANH')),
            FOREIGN KEY (giang_vien_id) REFERENCES giang_vien (id) ON DELETE CASCADE,
            FOREIGN KEY (mon_hoc_id) REFERENCES mon_hoc (id) ON DELETE CASCADE,
            FOREIGN KEY (lop_hoc_id) REFERENCES lop_hoc (id) ON DELETE CASCADE,
            UNIQUE(giang_vien_id, mon_hoc_id, lop_hoc_id, hoc_ky, nam_hoc)
        )
    """)

    # 8. Bảng điểm
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bang_diem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinh_vien_id INTEGER NOT NULL,
            mon_hoc_id INTEGER NOT NULL,
            diem_qua_trinh REAL,
            diem_thi REAL,
            diem_tong_ket REAL,
            FOREIGN KEY (sinh_vien_id) REFERENCES sinh_vien (id) ON DELETE CASCADE,
            FOREIGN KEY (mon_hoc_id) REFERENCES mon_hoc (id) ON DELETE CASCADE,
            UNIQUE (sinh_vien_id, mon_hoc_id)
        )
    """)

    # Nạp dữ liệu từ data_seed.json nếu DB rỗng
    if os.path.exists(SEED_FILE) and conn.execute("SELECT COUNT(*) FROM vai_tro").fetchone()[0] == 0:
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        for vt in data.get("vai_tro", []):
            conn.execute("INSERT OR IGNORE INTO vai_tro (id, ten_vai_tro) VALUES (?, ?)", (vt["id"], vt["ten_vai_tro"]))

        for nd in data.get("nguoi_dung", []):
            conn.execute(
                "INSERT OR IGNORE INTO nguoi_dung (id, ten_dang_nhap, mat_khau, vai_tro_id) VALUES (?, ?, ?, ?)",
                (nd["id"], nd["ten_dang_nhap"].strip().upper(), str(nd["mat_khau"]).strip(), nd["vai_tro_id"])
            )

        for lh in data.get("lop_hoc", []):
            conn.execute(
                "INSERT OR IGNORE INTO lop_hoc (id, ma_lop, ten_lop, khoa) VALUES (?, ?, ?, ?)",
                (lh["id"], lh["ma_lop"].strip(), lh["ten_lop"].strip(), lh.get("khoa"))
            )

        for gv in data.get("giang_vien", []):
            conn.execute(
                """INSERT OR IGNORE INTO giang_vien (id, ma_giang_vien, ho_ten, email, so_dien_thoai, nguoi_dung_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (gv["id"], gv["ma_giang_vien"].strip().upper(), gv["ho_ten"].strip(), gv.get("email"), gv.get("so_dien_thoai"), gv.get("nguoi_dung_id"))
            )

        for mh in data.get("mon_hoc", []):
            conn.execute(
                "INSERT OR IGNORE INTO mon_hoc (id, ma_mon, ten_mon, so_tin_chi) VALUES (?, ?, ?, ?)",
                (mh["id"], mh["ma_mon"].strip().upper(), mh["ten_mon"].strip(), mh.get("so_tin_chi", 3))
            )

        for sv in data.get("sinh_vien", []):
            conn.execute(
                """INSERT OR IGNORE INTO sinh_vien (id, ma_sinh_vien, ho_ten, ngay_sinh, gioi_tinh, email, so_dien_thoai, dia_chi, lop_hoc_id, nguoi_dung_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sv["id"], sv["ma_sinh_vien"].strip().upper(), sv["ho_ten"].strip(), sv.get("ngay_sinh"), sv.get("gioi_tinh"), sv.get("email"), sv.get("so_dien_thoai"), sv.get("dia_chi"), sv["lop_hoc_id"], sv.get("nguoi_dung_id"))
            )

        for pc in data.get("phan_cong_giang_day", []):
            # Quy ước: Các phân công học kỳ 1 năm 2024-2025 là HOAN_THANH (lớp cũ chỉ xem), học kỳ 2 là DANG_DAY (được nhập điểm)
            trang_thai = "HOAN_THANH" if pc.get("hoc_ky") == 1 else "DANG_DAY"
            conn.execute(
                """INSERT OR IGNORE INTO phan_cong_giang_day (id, giang_vien_id, mon_hoc_id, lop_hoc_id, hoc_ky, nam_hoc, trang_thai)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pc["id"], pc["giang_vien_id"], pc["mon_hoc_id"], pc["lop_hoc_id"], pc.get("hoc_ky", 1), pc.get("nam_hoc", "2024-2025"), trang_thai)
            )

        for bd in data.get("bang_diem", []):
            conn.execute(
                """INSERT OR IGNORE INTO bang_diem (id, sinh_vien_id, mon_hoc_id, diem_qua_trinh, diem_thi, diem_tong_ket)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (bd["id"], bd["sinh_vien_id"], bd["mon_hoc_id"], bd.get("diem_qua_trinh"), bd.get("diem_thi"), bd.get("diem_tong_ket"))
            )

    conn.commit()
    conn.close()


def parse_diem(value):
    if value is None or value == "":
        return None
    d = float(value)
    if math.isnan(d) or d < 0 or d > 10:
        raise ValueError
    return d


def tinh_tong_ket(diem_qt, diem_ck):
    tk = Decimal(str(diem_qt)) * Decimal("0.4") + Decimal(str(diem_ck)) * Decimal("0.6")
    return float(tk.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def loi(message, status=400):
    return jsonify({"message": message}), status


@app.route("/")
@app.route("/index.html")
def trang_chu():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return "Không tìm thấy index.html", 404


# ===============================
# AUTHENTICATION (TEXT THUẦN)
# ===============================
@app.route("/api/dang-nhap", methods=["POST"])
def api_dang_nhap():
    body = request.get_json(silent=True) or {}
    tk = str(body.get("tai_khoan", "")).strip().upper()
    mk = str(body.get("mat_khau", "")).strip()

    if not tk or not mk:
        return loi("Vui lòng nhập tài khoản và mật khẩu.")

    conn = get_db_connection()
    user = conn.execute("""
        SELECT nd.*, vt.ten_vai_tro 
        FROM nguoi_dung nd 
        JOIN vai_tro vt ON nd.vai_tro_id = vt.id 
        WHERE UPPER(nd.ten_dang_nhap) = ? AND nd.mat_khau = ?
    """, (tk, mk)).fetchone()

    if not user:
        conn.close()
        return loi("Tài khoản hoặc mật khẩu không đúng.", 401)

    vai_tro = user["ten_vai_tro"]
    is_admin = (vai_tro == "ADMIN")
    ho_ten = tk
    gv_id = None

    if vai_tro in ("ADMIN", "GIANG_VIEN"):
        gv = conn.execute("SELECT * FROM giang_vien WHERE nguoi_dung_id = ?", (user["id"],)).fetchone()
        if gv:
            ho_ten = gv["ho_ten"]
            gv_id = gv["id"]
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
    session["giang_vien_id"] = gv_id

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
    return jsonify({"message": "Đã đăng xuất."})


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
# SINH VIÊN: CHỈ XEM ĐIỂM CÁ NHÂN
# ===============================
@app.route("/api/sinh-vien/bang-diem")
def api_sv_bang_diem():
    if session.get("vai_tro") != "SINH_VIEN":
        return loi("Chỉ sinh viên mới được truy cập trang này.", 403)

    conn = get_db_connection()
    sv = conn.execute("""
        SELECT sv.*, lh.ma_lop, lh.ten_lop 
        FROM sinh_vien sv 
        JOIN lop_hoc lh ON sv.lop_hoc_id = lh.id 
        WHERE sv.nguoi_dung_id = ?
    """, (session["user_id"],)).fetchone()

    if not sv:
        conn.close()
        return loi("Không tìm thấy hồ sơ sinh viên.", 404)

    rows = conn.execute("""
        SELECT mh.ma_mon, mh.ten_mon, mh.so_tin_chi,
               bd.diem_qua_trinh AS diem_qt, bd.diem_thi AS diem_ck, bd.diem_tong_ket AS diem_tk
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
# GIẢNG VIÊN & ADMIN: QUẢN LÝ LỚP
# ===============================
@app.route("/api/classes")
def api_classes():
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Không có quyền truy cập.", 403)

    is_admin = session.get("is_admin", False)
    gv_id = session.get("giang_vien_id")
    conn = get_db_connection()

    if is_admin:
        # Admin xem được toàn bộ các lớp
        rows = conn.execute("""
            SELECT lh.ma_lop, COUNT(DISTINCT sv.id) AS so_luong_sv,
                   COALESCE(pc.trang_thai, 'DANG_DAY') AS trang_thai,
                   COALESCE(gv.ho_ten, 'Nhiều GV / Chưa gán') AS gv_phu_trach
            FROM lop_hoc lh
            LEFT JOIN sinh_vien sv ON lh.id = sv.lop_hoc_id
            LEFT JOIN phan_cong_giang_day pc ON lh.id = pc.lop_hoc_id
            LEFT JOIN giang_vien gv ON pc.giang_vien_id = gv.id
            GROUP BY lh.ma_lop
            ORDER BY lh.ma_lop
        """).fetchall()
    else:
        # GV thường: chỉ xem lớp mình đang dạy hoặc lớp cũ đã hoàn thành
        rows = conn.execute("""
            SELECT lh.ma_lop, COUNT(DISTINCT sv.id) AS so_luong_sv,
                   pc.trang_thai, gv.ho_ten AS gv_phu_trach
            FROM phan_cong_giang_day pc
            JOIN lop_hoc lh ON pc.lop_hoc_id = lh.id
            JOIN giang_vien gv ON pc.giang_vien_id = gv.id
            LEFT JOIN sinh_vien sv ON lh.id = sv.lop_hoc_id
            WHERE pc.giang_vien_id = ?
            GROUP BY lh.ma_lop, pc.trang_thai
            ORDER BY pc.trang_thai DESC, lh.ma_lop
        """, (gv_id,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/class/<ma_lop>")
def api_class_detail(ma_lop):
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Không có quyền truy cập.", 403)

    is_admin = session.get("is_admin", False)
    gv_id = session.get("giang_vien_id")
    conn = get_db_connection()

    lop = conn.execute("SELECT * FROM lop_hoc WHERE ma_lop = ?", (ma_lop,)).fetchone()
    if not lop:
        conn.close()
        return loi("Lớp không tồn tại.", 404)

    # Quyền truy cập lớp
    pc = conn.execute("SELECT * FROM phan_cong_giang_day WHERE lop_hoc_id = ? AND giang_vien_id = ?", (lop["id"], gv_id)).fetchone()
    if not is_admin and not pc:
        conn.close()
        return loi("Bạn không được phân công dạy lớp này.", 403)

    # Chỉ cho sửa điểm nếu là Admin hoặc là GV dạy lớp ở trạng thái DANG_DAY
    co_quyen_sua_diem = False
    if is_admin:
        co_quyen_sua_diem = True
    elif pc and pc["trang_thai"] == "DANG_DAY":
        co_quyen_sua_diem = True

    subjects = conn.execute("SELECT * FROM mon_hoc ORDER BY id").fetchall()
    mon_id = request.args.get("mon_id", type=int)
    ids_hop_le = {s["id"] for s in subjects}
    if mon_id not in ids_hop_le and subjects:
        mon_id = subjects[0]["id"]

    students = conn.execute("""
        SELECT sv.id AS sv_id, sv.ma_sinh_vien AS mssv, sv.ho_ten,
               'Cong nghe Thong tin' AS chuyen_nganh,
               bd.diem_qua_trinh AS diem_qt, bd.diem_thi AS diem_ck, bd.diem_tong_ket AS diem_tk
        FROM sinh_vien sv
        LEFT JOIN bang_diem bd ON bd.sinh_vien_id = sv.id AND bd.mon_hoc_id = ?
        WHERE sv.lop_hoc_id = ?
        ORDER BY sv.ma_sinh_vien
    """, (mon_id, lop["id"])).fetchall()
    conn.close()

    return jsonify({
        "ma_lop": ma_lop,
        "current_mon_id": mon_id,
        "subjects": [dict(s) for s in subjects],
        "students": [dict(s) for s in students],
        "co_quyen_sua_diem": co_quyen_sua_diem,
        "trang_thai_lop": pc["trang_thai"] if pc else "DANG_DAY"
    })


@app.route("/api/class/<ma_lop>/update-grades", methods=["POST"])
def api_update_grades(ma_lop):
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Không có quyền cập nhật điểm.", 403)

    is_admin = session.get("is_admin", False)
    gv_id = session.get("giang_vien_id")
    conn = get_db_connection()

    lop = conn.execute("SELECT * FROM lop_hoc WHERE ma_lop = ?", (ma_lop,)).fetchone()
    if not lop:
        conn.close()
        return loi("Lớp không tồn tại.", 404)

    if not is_admin:
        pc = conn.execute(
            "SELECT * FROM phan_cong_giang_day WHERE lop_hoc_id = ? AND giang_vien_id = ? AND trang_thai = 'DANG_DAY'",
            (lop["id"], gv_id)
        ).fetchone()
        if not pc:
            conn.close()
            return loi("Lớp này đã hoàn thành hoặc bạn không có quyền sửa điểm.", 403)

    body = request.get_json(silent=True) or {}
    try:
        mon_id = int(body.get("mon_id"))
    except (TypeError, ValueError):
        conn.close()
        return loi("Mã môn học không hợp lệ.")

    grades = body.get("grades") or []
    try:
        for g in grades:
            sv_id = int(g.get("sv_id"))
            diem_qt = parse_diem(g.get("diem_qt"))
            diem_ck = parse_diem(g.get("diem_ck"))

            if diem_qt is None and diem_ck is None:
                conn.execute("DELETE FROM bang_diem WHERE sinh_vien_id = ? AND mon_hoc_id = ?", (sv_id, mon_id))
                continue

            diem_tk = tinh_tong_ket(diem_qt, diem_ck) if (diem_qt is not None and diem_ck is not None) else None
            conn.execute("""
                INSERT INTO bang_diem (sinh_vien_id, mon_hoc_id, diem_qua_trinh, diem_thi, diem_tong_ket)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (sinh_vien_id, mon_hoc_id) DO UPDATE SET
                    diem_qua_trinh = excluded.diem_qua_trinh,
                    diem_thi = excluded.diem_thi,
                    diem_tong_ket = excluded.diem_tong_ket
            """, (sv_id, mon_id, diem_qt, diem_ck, diem_tk))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return loi(f"Lỗi khi lưu điểm: {str(e)}", 500)

    conn.close()
    return jsonify({"message": "Đã lưu bảng điểm thành công!"})


# ===============================
# ADMIN: QUẢN LÝ MÔN HỌC
# ===============================
@app.route("/api/admin/mon-hoc", methods=["GET", "POST"])
def api_admin_mon_hoc():
    if not session.get("is_admin"):
        return loi("Chỉ Quản trị viên mới được thao tác.", 403)

    conn = get_db_connection()
    if request.method == "GET":
        rows = conn.execute("SELECT * FROM mon_hoc ORDER BY ma_mon").fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    body = request.get_json(silent=True) or {}
    ma_mon = str(body.get("ma_mon", "")).strip().upper()
    ten_mon = str(body.get("ten_mon", "")).strip()
    so_tc = int(body.get("so_tin_chi", 3))

    if not ma_mon or not ten_mon:
        conn.close()
        return loi("Mã môn và tên môn không được rỗng.")

    try:
        conn.execute("INSERT INTO mon_hoc (ma_mon, ten_mon, so_tin_chi) VALUES (?, ?, ?)", (ma_mon, ten_mon, so_tc))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return loi("Mã môn học này đã tồn tại.", 409)

    conn.close()
    return jsonify({"message": "Thêm môn học thành công!"}), 201


@app.route("/api/admin/mon-hoc/<int:mon_id>", methods=["DELETE"])
def api_admin_xoa_mon(mon_id):
    if not session.get("is_admin"):
        return loi("Chỉ Quản trị viên mới được thao tác.", 403)
    conn = get_db_connection()
    conn.execute("DELETE FROM mon_hoc WHERE id = ?", (mon_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã xóa môn học."})


# ===============================
# ADMIN: PHÂN CÔNG GIẢNG DẠY
# ===============================
@app.route("/api/admin/phan-cong", methods=["GET", "POST"])
def api_admin_phan_cong():
    if not session.get("is_admin"):
        return loi("Chỉ Quản trị viên mới được thao tác.", 403)

    conn = get_db_connection()
    if request.method == "GET":
        rows = conn.execute("""
            SELECT pc.id, lh.ma_lop, mh.ma_mon, mh.ten_mon, gv.ma_giang_vien, gv.ho_ten AS ten_gv, pc.trang_thai
            FROM phan_cong_giang_day pc
            JOIN lop_hoc lh ON pc.lop_hoc_id = lh.id
            JOIN mon_hoc mh ON pc.mon_hoc_id = mh.id
            JOIN giang_vien gv ON pc.giang_vien_id = gv.id
            ORDER BY pc.id DESC
        """).fetchall()

        gv_list = conn.execute("SELECT id, ma_giang_vien, ho_ten FROM giang_vien ORDER BY ho_ten").fetchall()
        mh_list = conn.execute("SELECT id, ma_mon, ten_mon FROM mon_hoc ORDER BY ma_mon").fetchall()
        lh_list = conn.execute("SELECT id, ma_lop, ten_lop FROM lop_hoc ORDER BY ma_lop").fetchall()
        conn.close()

        return jsonify({
            "phan_cong": [dict(r) for r in rows],
            "giang_vien": [dict(g) for g in gv_list],
            "mon_hoc": [dict(m) for m in mh_list],
            "lop_hoc": [dict(l) for l in lh_list]
        })

    body = request.get_json(silent=True) or {}
    gv_id = body.get("giang_vien_id")
    lop_id = body.get("lop_hoc_id")
    mon_id = body.get("mon_id")
    trang_thai = body.get("trang_thai", "DANG_DAY")

    try:
        conn.execute("""
            INSERT INTO phan_cong_giang_day (giang_vien_id, lop_hoc_id, mon_hoc_id, trang_thai)
            VALUES (?, ?, ?, ?)
        """, (gv_id, lop_id, mon_id, trang_thai))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return loi("Phân công này đã tồn tại trong hệ thống.", 409)

    conn.close()
    return jsonify({"message": "Phân công thành công!"}), 201


@app.route("/api/admin/phan-cong/<int:pc_id>", methods=["DELETE"])
def api_admin_xoa_phan_cong(pc_id):
    if not session.get("is_admin"):
        return loi("Chỉ Quản trị viên mới được thao tác.", 403)
    conn = get_db_connection()
    conn.execute("DELETE FROM phan_cong_giang_day WHERE id = ?", (pc_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã hủy phân công!"})


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)