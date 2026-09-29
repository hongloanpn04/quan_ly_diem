import json
import math
import os
import shutil
import sqlite3
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from flask import Flask, jsonify, render_template, request, session
from jinja2 import TemplateNotFound

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "quanly_thucte.db")
SEED_FILE = os.path.join(BASE_DIR, "data_seed.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Tăng số này mỗi khi đổi cấu trúc bảng: DB cũ sẽ được sao lưu (.bak) và nạp lại từ seed.
SCHEMA_VERSION = 8

# False -> Admin/Giáo vụ (GV001-GV005) cũng chỉ thấy lớp mình được phân công; việc quản lý nằm ở menu QL Môn/QL Lớp.
# True  -> Admin xem và sửa điểm được lớp của mọi giảng viên.
ADMIN_XEM_TAT_CA = False

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="",
    template_folder=TEMPLATES_DIR,
)
app.secret_key = "ptit_secret_key_no_hash"
app.json.ensure_ascii = False


# ===============================
# HỌC KỲ THEO THỜI GIAN THỰC
# Tháng 8 -> 1 : học kỳ 1 | Tháng 2 -> 7 : học kỳ 2
# ===============================
def hoc_ky_hien_tai(today=None):
    today = today or date.today()
    m, y = today.month, today.year
    if m >= 8:
        return 1, f"{y}-{y + 1}"
    if m == 1:
        return 1, f"{y - 1}-{y}"
    return 2, f"{y - 1}-{y}"


def khoa_hoc_ky(hoc_ky, nam_hoc):
    """Khóa so sánh thứ tự thời gian: (năm bắt đầu, học kỳ)."""
    try:
        return int(str(nam_hoc)[:4]), int(hoc_ky)
    except (TypeError, ValueError):
        return 0, 0


def trang_thai_theo_thoi_gian(hoc_ky, nam_hoc):
    """DANG_DAY: đúng học kỳ hiện tại | HOAN_THANH: đã qua | CHUA_BAT_DAU: chưa tới."""
    hien_tai = khoa_hoc_ky(*hoc_ky_hien_tai())
    khoa = khoa_hoc_ky(hoc_ky, nam_hoc)
    if khoa == hien_tai:
        return "DANG_DAY"
    return "HOAN_THANH" if khoa < hien_tai else "CHUA_BAT_DAU"


def thu_tu_hien_thi(pc):
    rank = {"DANG_DAY": 0, "CHUA_BAT_DAU": 1, "HOAN_THANH": 2}[pc["trang_thai"]]
    nam, hk = khoa_hoc_ky(pc["hoc_ky"], pc["nam_hoc"])
    return rank, -nam, -hk, pc["ma_lop"], pc["ma_mon"]


# ===============================
# DATABASE
# ===============================
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn



def tao_bang(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vai_tro (
            id INTEGER PRIMARY KEY,
            ma_vai_tro TEXT NOT NULL UNIQUE,
            ten_vai_tro TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nguoi_dung (
            id INTEGER PRIMARY KEY,
            ten_dang_nhap TEXT NOT NULL UNIQUE,
            mat_khau TEXT NOT NULL,
            vai_tro_id INTEGER NOT NULL,
            trang_thai INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (vai_tro_id) REFERENCES vai_tro(id)
        );

        CREATE TABLE IF NOT EXISTS lop_hoc (
            id INTEGER PRIMARY KEY,
            ma_lop TEXT NOT NULL UNIQUE,
            ten_lop TEXT NOT NULL,
            khoa INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS giang_vien (
            id INTEGER PRIMARY KEY,
            mgv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            email TEXT,
            sdt TEXT NOT NULL,
            quyen_quan_ly_sv INTEGER NOT NULL DEFAULT 0,
            ghi_chu TEXT,
            nguoi_dung_id INTEGER NOT NULL UNIQUE,
            FOREIGN KEY (nguoi_dung_id) REFERENCES nguoi_dung(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sinh_vien (
            id INTEGER PRIMARY KEY,
            mssv TEXT NOT NULL UNIQUE,
            ho_ten TEXT NOT NULL,
            mail TEXT,
            sdt TEXT NOT NULL,
            nguoi_dung_id INTEGER NOT NULL UNIQUE,
            lop_hoc_id INTEGER NOT NULL,
            FOREIGN KEY (nguoi_dung_id) REFERENCES nguoi_dung(id) ON DELETE CASCADE,
            FOREIGN KEY (lop_hoc_id) REFERENCES lop_hoc(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS mon_hoc (
            id INTEGER PRIMARY KEY,
            ma_mon TEXT NOT NULL UNIQUE,
            ten_mon TEXT NOT NULL,
            so_tin_chi INTEGER NOT NULL DEFAULT 3,
            ty_le_qt REAL NOT NULL DEFAULT 0.4,
            ty_le_gk REAL NOT NULL DEFAULT 0.0,
            ty_le_ck REAL NOT NULL DEFAULT 0.6,
            CHECK (so_tin_chi > 0),
            CHECK (ty_le_qt >= 0 AND ty_le_qt <= 1),
            CHECK (ty_le_gk >= 0 AND ty_le_gk <= 1),
            CHECK (ty_le_ck >= 0 AND ty_le_ck <= 1),
            CHECK (ABS((ty_le_qt + ty_le_gk + ty_le_ck) - 1.0) < 0.000001)
        );

        CREATE TABLE IF NOT EXISTS phan_cong_giang_day (
            id INTEGER PRIMARY KEY,
            giang_vien_id INTEGER NOT NULL,
            mon_hoc_id INTEGER NOT NULL,
            lop_hoc_id INTEGER NOT NULL,
            hoc_ky INTEGER NOT NULL,
            nam_hoc TEXT NOT NULL,
            trang_thai TEXT NOT NULL DEFAULT 'CHUA_BAT_DAU',
            FOREIGN KEY (giang_vien_id) REFERENCES giang_vien(id) ON DELETE CASCADE,
            FOREIGN KEY (mon_hoc_id) REFERENCES mon_hoc(id) ON DELETE CASCADE,
            FOREIGN KEY (lop_hoc_id) REFERENCES lop_hoc(id) ON DELETE CASCADE,
            UNIQUE (giang_vien_id, mon_hoc_id, lop_hoc_id, hoc_ky, nam_hoc),
            CHECK (hoc_ky IN (1,2)),
            CHECK (nam_hoc GLOB '20[0-9][0-9]-20[0-9][0-9]'),
            CHECK (trang_thai IN ('DANG_DAY','HOAN_THANH','CHUA_BAT_DAU'))
        );

        CREATE TABLE IF NOT EXISTS bang_diem (
            id INTEGER PRIMARY KEY,
            sinh_vien_id INTEGER NOT NULL,
            phan_cong_id INTEGER NOT NULL,
            diem_qua_trinh REAL,
            diem_giua_ky REAL,
            diem_cuoi_ky REAL,
            diem_tong_ket REAL,
            FOREIGN KEY (sinh_vien_id) REFERENCES sinh_vien(id) ON DELETE CASCADE,
            FOREIGN KEY (phan_cong_id) REFERENCES phan_cong_giang_day(id) ON DELETE CASCADE,
            UNIQUE (sinh_vien_id, phan_cong_id),
            CHECK (diem_qua_trinh IS NULL OR (diem_qua_trinh >= 0 AND diem_qua_trinh <= 10)),
            CHECK (diem_giua_ky IS NULL OR (diem_giua_ky >= 0 AND diem_giua_ky <= 10)),
            CHECK (diem_cuoi_ky IS NULL OR (diem_cuoi_ky >= 0 AND diem_cuoi_ky <= 10)),
            CHECK (diem_tong_ket IS NULL OR (diem_tong_ket >= 0 AND diem_tong_ket <= 10))
        );
    """)




def nap_seed(conn):
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    hk_now, nam_now = hoc_ky_hien_tai()

    for vt in data.get("vai_tro", []):
        conn.execute(
            "INSERT OR IGNORE INTO vai_tro (id, ma_vai_tro, ten_vai_tro) VALUES (?, ?, ?)",
            (vt["id"], vt["ma_vai_tro"], vt["ten_vai_tro"])
        )

    for nd in data.get("nguoi_dung", []):
        conn.execute(
            """INSERT OR IGNORE INTO nguoi_dung
               (id, ten_dang_nhap, mat_khau, vai_tro_id, trang_thai)
               VALUES (?, ?, ?, ?, ?)""",
            (nd["id"], nd["ten_dang_nhap"].strip().upper(), str(nd["mat_khau"]).strip(),
             nd["vai_tro_id"], 1 if nd.get("trang_thai", True) else 0)
        )

    for lh in data.get("lop_hoc", []):
        conn.execute(
            """INSERT OR IGNORE INTO lop_hoc
               (id, ma_lop, ten_lop, khoa)
               VALUES (?, ?, ?, ?)""",
            (lh["id"], lh["ma_lop"].strip().upper(), lh["ten_lop"].strip(), int(lh["khoa"]))
        )

    for gv in data.get("giang_vien", []):
        conn.execute(
            """INSERT OR IGNORE INTO giang_vien
               (id, mgv, ho_ten, email, sdt, quyen_quan_ly_sv, ghi_chu, nguoi_dung_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (gv["id"], (gv.get("mgv") or gv.get("ma_giang_vien")).strip().upper(),
             gv["ho_ten"].strip(), gv.get("email"), gv.get("sdt"),
             1 if gv.get("quyen_quan_ly_sv") else 0, gv.get("ghi_chu"), gv["nguoi_dung_id"])
        )

    for mh in data.get("mon_hoc", []):
        ty_le_qt = float(mh.get("ty_le_qt", 0.4))
        ty_le_gk = float(mh.get("ty_le_gk", 0.0))
        ty_le_ck = float(mh.get("ty_le_ck", 1 - ty_le_qt - ty_le_gk))
        conn.execute(
            """INSERT OR IGNORE INTO mon_hoc
               (id, ma_mon, ten_mon, so_tin_chi, ty_le_qt, ty_le_gk, ty_le_ck)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (mh["id"], mh["ma_mon"].strip().upper(), mh["ten_mon"].strip(),
             int(mh.get("so_tin_chi", 3)), ty_le_qt, ty_le_gk, ty_le_ck)
        )

    for sv in data.get("sinh_vien", []):
        conn.execute(
            """INSERT OR IGNORE INTO sinh_vien
               (id, mssv, ho_ten, mail, sdt, nguoi_dung_id, lop_hoc_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sv["id"], (sv.get("mssv") or sv.get("ma_sinh_vien")).strip().upper(),
             sv["ho_ten"].strip(), sv.get("mail"), sv.get("sdt"),
             sv["nguoi_dung_id"], sv["lop_hoc_id"])
        )

    for pc in data.get("phan_cong_giang_day", []):
        hk = int(pc.get("hoc_ky") or hk_now)
        nam = str(pc.get("nam_hoc") or nam_now)
        trang_thai = trang_thai_theo_thoi_gian(hk, nam)
        conn.execute(
            """INSERT OR IGNORE INTO phan_cong_giang_day
               (id, giang_vien_id, mon_hoc_id, lop_hoc_id, hoc_ky, nam_hoc, trang_thai)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pc["id"], pc["giang_vien_id"], pc["mon_hoc_id"], pc["lop_hoc_id"],
             hk, nam, trang_thai)
        )

    for bd in data.get("bang_diem", []):
        conn.execute(
            """INSERT OR IGNORE INTO bang_diem
               (id, sinh_vien_id, phan_cong_id,
                diem_qua_trinh, diem_giua_ky, diem_cuoi_ky, diem_tong_ket)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (bd["id"], bd["sinh_vien_id"], bd["phan_cong_id"],
             bd.get("diem_qua_trinh", bd.get("diem_qt")),
             bd.get("diem_giua_ky", bd.get("diem_gk")),
             bd.get("diem_cuoi_ky", bd.get("diem_ck", bd.get("diem_thi"))),
             bd.get("diem_tong_ket", bd.get("diem_tk")))
        )



def init_db():
    if os.path.exists(DB_NAME):
        c = sqlite3.connect(DB_NAME)
        ver = c.execute("PRAGMA user_version").fetchone()[0]
        c.close()
        if ver != SCHEMA_VERSION:  # DB cũ khác cấu trúc -> sao lưu rồi tạo lại
            shutil.move(DB_NAME, DB_NAME + f".v{ver}.bak")

    conn = get_db_connection()
    tao_bang(conn)
    if os.path.exists(SEED_FILE) and conn.execute("SELECT COUNT(*) FROM vai_tro").fetchone()[0] == 0:
        nap_seed(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()


# ===============================
# TIỆN ÍCH
# ===============================

def parse_diem(value):
    if value is None or value == "":
        return None
    d = float(value)
    if math.isnan(d) or d < 0 or d > 10:
        raise ValueError
    return d


def tinh_tong_ket(diem_qt, diem_gk, diem_ck, ty_le_qt=0.3, ty_le_gk=0.0, ty_le_ck=0.7):
    if diem_qt is None or diem_ck is None:
        return None
    if ty_le_gk > 0 and diem_gk is None:
        return None

    tk = Decimal("0")
    tk += Decimal(str(diem_qt)) * Decimal(str(ty_le_qt))
    if ty_le_gk > 0:
        tk += Decimal(str(diem_gk)) * Decimal(str(ty_le_gk))
    tk += Decimal(str(diem_ck)) * Decimal(str(ty_le_ck))
    return float(tk.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))



def loi(message, status=400):
    return jsonify({"message": message}), status


def nhan_hoc_ky():
    hk, nam = hoc_ky_hien_tai()
    return {"hoc_ky": hk, "nam_hoc": nam, "nhan": f"HK{hk} • {nam}"}


def xem_tat_ca():
    """Admin xem/sửa điểm mọi lớp khi cấu hình bật, hoặc khi gọi từ menu QL Lớp Học (?all=1)."""
    if not session.get("is_admin"):
        return False
    return ADMIN_XEM_TAT_CA or request.args.get("all") == "1"


def lay_phan_cong(conn, lop_id, mon_id=None):
    """Các phân công của giảng viên đang đăng nhập (hoặc của mọi GV nếu là Admin xem tất cả) trong 1 lớp."""
    sql = """
        SELECT pc.*, mh.ma_mon, mh.ten_mon, lh.ma_lop, gv.ho_ten AS gv_phu_trach
        FROM phan_cong_giang_day pc
        JOIN mon_hoc mh ON pc.mon_hoc_id = mh.id
        JOIN lop_hoc lh ON pc.lop_hoc_id = lh.id
        JOIN giang_vien gv ON pc.giang_vien_id = gv.id
        WHERE pc.lop_hoc_id = ?
    """
    params = [lop_id]
    if not xem_tat_ca():
        sql += " AND pc.giang_vien_id = ?"
        params.append(session.get("giang_vien_id"))
    if mon_id is not None:
        sql += " AND pc.mon_hoc_id = ?"
        params.append(mon_id)
    rows = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        d["trang_thai"] = trang_thai_theo_thoi_gian(d["hoc_ky"], d["nam_hoc"])
        rows.append(d)
    rows.sort(key=thu_tu_hien_thi)
    return rows


@app.route("/")
@app.route("/index.html")
def trang_chu():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return "Không tìm thấy index.html", 404


# ===============================
# AUTHENTICATION
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
        SELECT nd.*, vt.ma_vai_tro
        FROM nguoi_dung nd JOIN vai_tro vt ON nd.vai_tro_id = vt.id
        WHERE UPPER(nd.ten_dang_nhap) = ? AND nd.mat_khau = ? AND nd.trang_thai = 1
    """, (tk, mk)).fetchone()
    if not user:
        conn.close()
        return loi("Tài khoản hoặc mật khẩu không đúng.", 401)

    vai_tro = user["ma_vai_tro"]
    ho_ten, gv_id = tk, None
    if vai_tro in ("ADMIN", "GIANG_VIEN"):
        gv = conn.execute("SELECT * FROM giang_vien WHERE nguoi_dung_id = ?", (user["id"],)).fetchone()
        if gv:
            ho_ten, gv_id = gv["ho_ten"], gv["id"]
    else:
        sv = conn.execute("SELECT * FROM sinh_vien WHERE nguoi_dung_id = ?", (user["id"],)).fetchone()
        if sv:
            ho_ten = sv["ho_ten"]
    conn.close()

    session.clear()
    session["user_id"] = user["id"]
    session["ten_dang_nhap"] = tk
    session["vai_tro"] = vai_tro
    session["ho_ten"] = ho_ten
    session["is_admin"] = (vai_tro == "ADMIN")
    session["giang_vien_id"] = gv_id

    return jsonify({
        "message": "Đăng nhập thành công!",
        "user": {"ten_dang_nhap": tk, "ho_ten": ho_ten, "vai_tro": vai_tro, "is_admin": vai_tro == "ADMIN"},
        "hoc_ky": nhan_hoc_ky(),
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
            "is_admin": session.get("is_admin", False),
        },
        "hoc_ky": nhan_hoc_ky(),
    })


@app.route("/api/hoc-ky-hien-tai")
def api_hoc_ky_hien_tai():
    return jsonify(nhan_hoc_ky())


@app.route("/api/doi-mat-khau", methods=["POST"])
def api_doi_mat_khau():
    if "user_id" not in session:
        return loi("Chưa đăng nhập.", 401)
    body = request.get_json(silent=True) or {}
    mk_cu = str(body.get("mk_cu", "")).strip()
    mk_moi = str(body.get("mk_moi", "")).strip()
    if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$", mk_moi):
        return loi("Mật khẩu mới phải có ít nhất 8 ký tự, gồm chữ Hoa, chữ thường, số và ký tự đặc biệt.")

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
        SELECT sv.id, sv.mssv, sv.ho_ten, lh.ma_lop, lh.ten_lop
        FROM sinh_vien sv
        JOIN lop_hoc lh ON sv.lop_hoc_id = lh.id
        WHERE sv.nguoi_dung_id = ?
    """, (session["user_id"],)).fetchone()

    if not sv:
        conn.close()
        return loi("Không tìm thấy hồ sơ sinh viên.", 404)

    rows = conn.execute("""
        SELECT mh.ma_mon, mh.ten_mon, mh.so_tin_chi,
               pc.hoc_ky, pc.nam_hoc,
               bd.diem_qua_trinh AS diem_qt,
               bd.diem_giua_ky AS diem_gk,
               bd.diem_cuoi_ky AS diem_ck,
               bd.diem_tong_ket AS diem_tk
        FROM bang_diem bd
        JOIN phan_cong_giang_day pc ON bd.phan_cong_id = pc.id
        JOIN mon_hoc mh ON pc.mon_hoc_id = mh.id
        WHERE bd.sinh_vien_id = ?
        ORDER BY pc.nam_hoc DESC, pc.hoc_ky DESC, mh.ma_mon
    """, (sv["id"],)).fetchall()

    conn.close()
    return jsonify({"sinh_vien": dict(sv), "bang_diem": [dict(r) for r in rows]})



# ===============================
# GIẢNG VIÊN & ADMIN: LỚP HỌC PHẦN
# ===============================
@app.route("/api/classes")
def api_classes():
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Không có quyền truy cập.", 403)

    conn = get_db_connection()
    sql = """
        SELECT pc.id AS pc_id, lh.id AS lop_id, lh.ma_lop, lh.ten_lop,
               mh.id AS mon_hoc_id, mh.ma_mon, mh.ten_mon,
               gv.ho_ten AS gv_phu_trach, pc.hoc_ky, pc.nam_hoc,
               (SELECT COUNT(*) FROM sinh_vien sv WHERE sv.lop_hoc_id = lh.id) AS so_luong_sv
        FROM phan_cong_giang_day pc
        JOIN lop_hoc lh ON pc.lop_hoc_id = lh.id
        JOIN mon_hoc mh ON pc.mon_hoc_id = mh.id
        JOIN giang_vien gv ON pc.giang_vien_id = gv.id
    """
    params = ()
    if not xem_tat_ca():
        sql += " WHERE pc.giang_vien_id = ?"   # CHỈ lớp được phân công cho người đăng nhập
        params = (session.get("giang_vien_id"),)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()

    for r in rows:
        r["trang_thai"] = trang_thai_theo_thoi_gian(r["hoc_ky"], r["nam_hoc"])
    rows.sort(key=thu_tu_hien_thi)
    return jsonify(rows)



@app.route("/api/class/<ma_lop>")
def api_class_detail(ma_lop):
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Không có quyền truy cập.", 403)

    tat_ca = xem_tat_ca()
    conn = get_db_connection()
    lop = conn.execute("SELECT * FROM lop_hoc WHERE ma_lop = ?", (ma_lop,)).fetchone()
    if not lop:
        conn.close()
        return loi("Lớp không tồn tại.", 404)

    pcs = lay_phan_cong(conn, lop["id"])
    if not pcs and not tat_ca:
        conn.close()
        return loi("Bạn không được phân công dạy lớp này.", 403)

    subjects_ids, seen = [], set()
    for p in pcs:
        if p["mon_hoc_id"] not in seen:
            seen.add(p["mon_hoc_id"])
            subjects_ids.append(p["mon_hoc_id"])

    if subjects_ids:
        marks = ",".join("?" * len(subjects_ids))
        subjects = conn.execute(
            f"SELECT * FROM mon_hoc WHERE id IN ({marks}) ORDER BY ma_mon",
            subjects_ids
        ).fetchall()
    else:
        subjects = conn.execute("SELECT * FROM mon_hoc ORDER BY ma_mon").fetchall()

    mon_id = request.args.get("mon_id", type=int)
    if mon_id not in {s["id"] for s in subjects}:
        mon_id = subjects[0]["id"] if subjects else None

    if mon_id is None:
        conn.close()
        return loi("Lớp này chưa có môn học nào được phân công.", 404)

    pc = next((p for p in pcs if p["mon_hoc_id"] == mon_id), None)
    if pc is None:
        conn.close()
        return loi("Không tìm thấy phân công cho môn này.", 404)

    trang_thai = pc["trang_thai"]
    co_quyen_sua_diem = bool(tat_ca or trang_thai == "DANG_DAY")

    students = conn.execute("""
        SELECT sv.id AS sv_id, sv.mssv AS mssv, sv.ho_ten,
               bd.diem_qua_trinh AS diem_qt,
               bd.diem_giua_ky AS diem_gk,
               bd.diem_cuoi_ky AS diem_ck,
               bd.diem_tong_ket AS diem_tk
        FROM sinh_vien sv
        LEFT JOIN bang_diem bd
          ON bd.sinh_vien_id = sv.id
         AND bd.phan_cong_id = ?
        WHERE sv.lop_hoc_id = ?
        ORDER BY sv.mssv
    """, (pc["id"], lop["id"])).fetchall()

    conn.close()

    return jsonify({
        "ma_lop": ma_lop,
        "khoa": lop["khoa"],
        "current_pc_id": pc["id"],
        "current_mon_id": mon_id,
        "subjects": [dict(s) for s in subjects],
        "students": [dict(s) for s in students],
        "co_quyen_sua_diem": co_quyen_sua_diem,
        "trang_thai_lop": trang_thai,
        "hoc_ky_lop": f"HK{pc['hoc_ky']} • {pc['nam_hoc']}"
    })




@app.route("/api/class/<ma_lop>/update-grades", methods=["POST"])
def api_update_grades(ma_lop):
    if session.get("vai_tro") not in ("ADMIN", "GIANG_VIEN"):
        return loi("Không có quyền cập nhật điểm.", 403)

    conn = get_db_connection()
    lop = conn.execute("SELECT * FROM lop_hoc WHERE ma_lop = ?", (ma_lop,)).fetchone()
    if not lop:
        conn.close()
        return loi("Lớp không tồn tại.", 404)

    body = request.get_json(silent=True) or {}
    try:
        mon_id = int(body.get("mon_id"))
    except (TypeError, ValueError):
        conn.close()
        return loi("Mã môn học không hợp lệ.")

    mon = conn.execute("SELECT * FROM mon_hoc WHERE id = ?", (mon_id,)).fetchone()
    if not mon:
        conn.close()
        return loi("Môn học không tồn tại.", 404)

    pcs = lay_phan_cong(conn, lop["id"], mon_id)
    if not pcs:
        conn.close()
        return loi("Không tìm thấy phân công dạy môn này ở lớp này.", 403)

    pc = pcs[0]
    if not xem_tat_ca() and pc["trang_thai"] != "DANG_DAY":
        conn.close()
        return loi("Môn này không thuộc học kỳ hiện tại nên chỉ được xem, không được sửa điểm.", 403)

    sv_hop_le = {
        r["id"] for r in conn.execute(
            "SELECT id FROM sinh_vien WHERE lop_hoc_id = ?", (lop["id"],)
        )
    }

    try:
        for g in body.get("grades") or []:
            sv_id = int(g.get("sv_id"))
            if sv_id not in sv_hop_le:
                raise ValueError("Sinh viên không thuộc lớp này.")

            diem_qt = parse_diem(g.get("diem_qt"))
            diem_gk = parse_diem(g.get("diem_gk"))
            diem_ck = parse_diem(g.get("diem_ck", g.get("diem_thi")))

            if diem_qt is None and diem_gk is None and diem_ck is None:
                conn.execute(
                    "DELETE FROM bang_diem WHERE sinh_vien_id = ? AND phan_cong_id = ?",
                    (sv_id, pc["id"])
                )
                continue

            diem_tk = tinh_tong_ket(
                diem_qt, diem_gk, diem_ck,
                mon["ty_le_qt"], mon["ty_le_gk"], mon["ty_le_ck"]
            )

            conn.execute("""
                INSERT INTO bang_diem (
                    sinh_vien_id, phan_cong_id,
                    diem_qua_trinh, diem_giua_ky,
                    diem_cuoi_ky, diem_tong_ket
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (sinh_vien_id, phan_cong_id) DO UPDATE SET
                    diem_qua_trinh = excluded.diem_qua_trinh,
                    diem_giua_ky = excluded.diem_giua_ky,
                    diem_cuoi_ky = excluded.diem_cuoi_ky,
                    diem_tong_ket = excluded.diem_tong_ket
            """, (
                sv_id, pc["id"], diem_qt, diem_gk, diem_ck, diem_tk
            ))

        conn.commit()

    except ValueError as e:
        conn.rollback()
        conn.close()
        return loi(str(e) or "Điểm không hợp lệ (phải từ 0 đến 10).")
    except Exception as e:
        conn.rollback()
        conn.close()
        return loi(f"Lỗi khi lưu điểm: {e}", 500)

    conn.close()
    return jsonify({"message": "Đã lưu bảng điểm thành công!", "phan_cong_id": pc["id"]})



# ===============================
# ADMIN: QUẢN LÝ MÔN HỌC
# ===============================
def can_admin():
    return None if session.get("is_admin") else loi("Chỉ Quản trị viên mới được thao tác.", 403)



@app.route("/api/admin/mon-hoc", methods=["GET", "POST"])
def api_admin_mon_hoc():
    if (e := can_admin()):
        return e
    conn = get_db_connection()
    if request.method == "GET":
        rows = conn.execute("SELECT * FROM mon_hoc ORDER BY ma_mon").fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    body = request.get_json(silent=True) or {}
    ma_mon = str(body.get("ma_mon", "")).strip().upper()
    ten_mon = str(body.get("ten_mon", "")).strip()
    try:
        so_tc = int(body.get("so_tin_chi", 3))
        ty_le_qt = float(body.get("ty_le_qt", 0.4))
        ty_le_gk = float(body.get("ty_le_gk", 0.0))
        ty_le_ck = float(body.get("ty_le_ck", 1 - ty_le_qt - ty_le_gk))
    except (TypeError, ValueError):
        conn.close()
        return loi("Thông tin môn học không hợp lệ.")
    if not ma_mon or not ten_mon:
        conn.close()
        return loi("Mã môn và tên môn không được rỗng.")
    if so_tc <= 0 or min(ty_le_qt, ty_le_gk, ty_le_ck) < 0 or abs(ty_le_qt + ty_le_gk + ty_le_ck - 1) > 1e-6:
        conn.close()
        return loi("Số tín chỉ hoặc tỷ lệ điểm không hợp lệ.")
    try:
        conn.execute("""
            INSERT INTO mon_hoc (ma_mon, ten_mon, so_tin_chi, ty_le_qt, ty_le_gk, ty_le_ck)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ma_mon, ten_mon, so_tc, ty_le_qt, ty_le_gk, ty_le_ck))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return loi("Mã môn học này đã tồn tại.", 409)
    conn.close()
    return jsonify({"message": "Thêm môn học thành công!"}), 201


@app.route("/api/admin/mon-hoc/<int:mon_id>", methods=["PUT", "DELETE"])
def api_admin_mon_hoc_id(mon_id):
    if (e := can_admin()):
        return e
    conn = get_db_connection()
    if request.method == "DELETE":
        conn.execute("DELETE FROM mon_hoc WHERE id = ?", (mon_id,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Đã xóa môn học."})

    body = request.get_json(silent=True) or {}
    ten_mon = str(body.get("ten_mon", "")).strip()
    try:
        so_tc = int(body.get("so_tin_chi", 3))
        ty_le_qt = float(body.get("ty_le_qt", 0.4))
        ty_le_gk = float(body.get("ty_le_gk", 0.0))
        ty_le_ck = float(body.get("ty_le_ck", 1 - ty_le_qt - ty_le_gk))
    except (TypeError, ValueError):
        conn.close()
        return loi("Thông tin môn học không hợp lệ.")
    if not ten_mon:
        conn.close()
        return loi("Tên môn không được rỗng.")
    if so_tc <= 0 or min(ty_le_qt, ty_le_gk, ty_le_ck) < 0 or abs(ty_le_qt + ty_le_gk + ty_le_ck - 1) > 1e-6:
        conn.close()
        return loi("Số tín chỉ hoặc tỷ lệ điểm không hợp lệ.")

    conn.execute("""
        UPDATE mon_hoc
        SET ten_mon = ?, so_tin_chi = ?,
            ty_le_qt = ?, ty_le_gk = ?, ty_le_ck = ?
        WHERE id = ?
    """, (ten_mon, so_tc, ty_le_qt, ty_le_gk, ty_le_ck, mon_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Cập nhật môn học thành công!"})



# ===============================
# ADMIN: QUẢN LÝ LỚP HỌC
# ===============================

@app.route("/api/admin/lop-hoc", methods=["GET", "POST"])
def api_admin_lop_hoc():
    if (e := can_admin()):
        return e
    conn = get_db_connection()
    if request.method == "GET":
        rows = conn.execute("""
            SELECT lh.id, lh.ma_lop, lh.ten_lop, lh.khoa,
                   COUNT(sv.id) AS so_sv
            FROM lop_hoc lh
            LEFT JOIN sinh_vien sv ON sv.lop_hoc_id = lh.id
            GROUP BY lh.id
            ORDER BY lh.ma_lop
        """).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    body = request.get_json(silent=True) or {}
    ma_lop = str(body.get("ma_lop", "")).strip().upper()
    ten_lop = str(body.get("ten_lop", "")).strip()
    try:
        khoa_raw = body.get("khoa")
        if khoa_raw in (None, ""):
            m = re.search(r"^D(\d{2})", ma_lop)
            if not m:
                raise ValueError
            khoa = 2000 + int(m.group(1))
        else:
            khoa = int(khoa_raw)
    except (TypeError, ValueError):
        conn.close()
        return loi("Khóa học không hợp lệ.")
    if not ma_lop or not ten_lop:
        conn.close()
        return loi("Mã lớp và tên lớp không được rỗng.")
    try:
        conn.execute(
            "INSERT INTO lop_hoc (ma_lop, ten_lop, khoa) VALUES (?, ?, ?)",
            (ma_lop, ten_lop, khoa)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return loi("Mã lớp này đã tồn tại.", 409)
    conn.close()
    return jsonify({"message": "Tạo lớp học thành công!"}), 201


@app.route("/api/admin/lop-hoc/<int:lop_id>", methods=["PUT", "DELETE"])
def api_admin_lop_hoc_id(lop_id):
    if (e := can_admin()):
        return e
    conn = get_db_connection()
    if request.method == "DELETE":
        conn.execute("DELETE FROM lop_hoc WHERE id = ?", (lop_id,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Đã xóa lớp học."})

    body = request.get_json(silent=True) or {}
    ten_lop = str(body.get("ten_lop", "")).strip()
    current = conn.execute("SELECT * FROM lop_hoc WHERE id = ?", (lop_id,)).fetchone()
    if not current:
        conn.close()
        return loi("Lớp không tồn tại.", 404)

    try:
        khoa = int(body.get("khoa", current["khoa"]))
    except (TypeError, ValueError):
        conn.close()
        return loi("Khóa học không hợp lệ.")
    if not ten_lop:
        conn.close()
        return loi("Tên lớp không được rỗng.")

    conn.execute("UPDATE lop_hoc SET ten_lop = ?, khoa = ? WHERE id = ?", (ten_lop, khoa, lop_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Cập nhật lớp học thành công!"})



# ===============================
# ADMIN: PHÂN CÔNG GIẢNG DẠY
# ===============================

@app.route("/api/admin/phan-cong", methods=["GET", "POST"])
def api_admin_phan_cong():
    if (e := can_admin()):
        return e
    conn = get_db_connection()
    if request.method == "GET":
        rows = [dict(r) for r in conn.execute("""
            SELECT pc.id, lh.ma_lop, mh.ma_mon, mh.ten_mon,
                   gv.mgv AS ma_giang_vien, gv.ho_ten AS ten_gv,
                   pc.hoc_ky, pc.nam_hoc, pc.trang_thai
            FROM phan_cong_giang_day pc
            JOIN lop_hoc lh ON pc.lop_hoc_id = lh.id
            JOIN mon_hoc mh ON pc.mon_hoc_id = mh.id
            JOIN giang_vien gv ON pc.giang_vien_id = gv.id
            ORDER BY pc.id DESC
        """).fetchall()]
        for r in rows:
            r["trang_thai"] = trang_thai_theo_thoi_gian(r["hoc_ky"], r["nam_hoc"])
        out = {
            "phan_cong": rows,
            "giang_vien": [dict(g) for g in conn.execute(
                "SELECT id, mgv AS ma_giang_vien, ho_ten FROM giang_vien ORDER BY ho_ten")],
            "mon_hoc": [dict(m) for m in conn.execute(
                "SELECT id, ma_mon, ten_mon FROM mon_hoc ORDER BY ma_mon")],
            "lop_hoc": [dict(l) for l in conn.execute(
                "SELECT id, ma_lop, ten_lop, khoa FROM lop_hoc ORDER BY ma_lop")],
            "hoc_ky": nhan_hoc_ky(),
        }
        conn.close()
        return jsonify(out)

    body = request.get_json(silent=True) or {}
    hk_now, nam_now = hoc_ky_hien_tai()
    try:
        gv_id = int(body["giang_vien_id"])
        mon_id = int(body["mon_id"])
        lop_id = int(body["lop_hoc_id"])
        hoc_ky = int(body.get("hoc_ky") or hk_now)
        nam_hoc = str(body.get("nam_hoc") or nam_now).strip()
        if hoc_ky not in (1, 2) or not re.fullmatch(r"\d{4}-\d{4}", nam_hoc):
            raise ValueError
        st = trang_thai_theo_thoi_gian(hoc_ky, nam_hoc)
        conn.execute("""
            INSERT INTO phan_cong_giang_day
            (giang_vien_id, mon_hoc_id, lop_hoc_id, hoc_ky, nam_hoc, trang_thai)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (gv_id, mon_id, lop_id, hoc_ky, nam_hoc, st))
        conn.commit()
    except (KeyError, TypeError, ValueError):
        conn.close()
        return loi("Dữ liệu phân công không hợp lệ.")
    except sqlite3.IntegrityError:
        conn.close()
        return loi("Phân công này đã tồn tại hoặc tham chiếu sai dữ liệu.", 409)
    conn.close()
    return jsonify({"message": "Phân công thành công!"}), 201



@app.route("/api/admin/phan-cong/<int:pc_id>", methods=["DELETE"])
def api_admin_xoa_phan_cong(pc_id):
    if (e := can_admin()):
        return e
    conn = get_db_connection()
    conn.execute("DELETE FROM phan_cong_giang_day WHERE id = ?", (pc_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã hủy phân công!"})


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)