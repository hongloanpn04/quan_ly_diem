import json
import os
from flask import Flask, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = "khoa_bi_mat_de_nho"
FILE_DATA = "data.json"


# Hai hàm cơ bản: Đọc file và Ghi file
def doc_json():
    with open(FILE_DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def ghi_json(du_lieu):
    with open(FILE_DATA, "w", encoding="utf-8") as f:
        json.dump(du_lieu, f, ensure_ascii=False, indent=2)


@app.route("/")
def trang_chu():
    return render_template("index.html")


# 1. ĐĂNG NHẬP
@app.route("/api/dang-nhap", methods=["POST"])
def dang_nhap():
    body = request.get_json()
    tk = body.get("tai_khoan")
    mk = body.get("mat_khau")
    db = doc_json()

    # Kiểm tra xem có phải Giảng viên không
    for gv in db["giang_vien"]:
        if gv["ma_gv"] == tk and gv["mat_khau"] == mk:
            session["user_id"] = gv["id"]
            session["vai_tro"] = gv["vai_tro"]
            session["la_giang_vien"] = True
            return jsonify(
                {
                    "ok": True,
                    "ten": gv["name"],
                    "vai_tro": gv["vai_tro"],
                    "la_gv": True,
                }
            )

    # Kiểm tra xem có phải Sinh viên không
    for sv in db["sinh_vien"]:
        if sv["ma_sv"] == tk and sv["mat_khau"] == mk:
            session["user_id"] = sv["id"]
            session["vai_tro"] = "sinh_vien"
            session["la_giang_vien"] = False
            return jsonify(
                {"ok": True, "ten": sv["name"], "vai_tro": "SV", "la_gv": False}
            )

    return jsonify({"ok": False, "tin_nhan": "Sai tài khoản hoặc mật khẩu!"})


# 2. ĐĂNG XUẤT
@app.route("/api/dang-xuat", methods=["POST"])
def dang_xuat():
    session.clear()
    return jsonify({"ok": True})


# 3. SINH VIÊN: XEM ĐIỂM
@app.route("/api/sv-xem-diem")
def sv_xem_diem():
    sv_id = session.get("user_id")
    db = doc_json()
    danh_sach = []

    for bd in db["bang_diem"]:
        if bd["sinh_vien_id"] == sv_id:
            # Tìm thông tin môn học tương ứng
            mon = next(
                (m for m in db["lop_hoc_phan"] if m["id"] == bd["lop_id"]), None
            )
            danh_sach.append(
                {
                    "ma_mon": mon["ma_mon"],
                    "ten_mon": mon["ten_mon"],
                    "diem": bd["diem"],
                }
            )

    return jsonify(danh_sach)


# 4. GIẢNG VIÊN: LẤY DANH SÁCH LỚP HỌC
@app.route("/api/gv-lop-hoc")
def gv_lop_hoc():
    db = doc_json()
    gv_id = session.get("user_id")
    vai_tro = session.get("vai_tro")

    # Quản trị viên xem được hết; Giảng viên thường chỉ xem lớp mình dạy
    if vai_tro == "quan_tri":
        return jsonify(db["lop_hoc_phan"])
    else:
        lop_cua_minh = [
            m for m in db["lop_hoc_phan"] if m["giang_vien_id"] == gv_id
        ]
        return jsonify(lop_cua_minh)


# 5. GIẢNG VIÊN: LẤY DANH SÁCH ĐIỂM CỦA 1 LỚP ĐỂ NHẬP/SỬA
@app.route("/api/gv-bang-diem-lop")
def gv_bang_diem_lop():
    lop_id = int(request.args.get("lop_id"))
    db = doc_json()
    ket_qua = []

    for sv in db["sinh_vien"]:
        # Tìm xem sinh viên này có điểm môn đó chưa
        tim_diem = next(
            (
                d
                for d in db["bang_diem"]
                if d["sinh_vien_id"] == sv["id"] and d["lop_id"] == lop_id
            ),
            None,
        )
        ket_qua.append(
            {
                "sv_id": sv["id"],
                "ma_sv": sv["ma_sv"],
                "ten_sv": sv["name"],
                "diem": tim_diem["diem"] if tim_diem else "",
            }
        )

    return jsonify(ket_qua)


# 6. GIẢNG VIÊN: LƯU ĐIỂM
@app.route("/api/gv-luu-diem", methods=["POST"])
def gv_luu_diem():
    body = request.get_json()
    sv_id = int(body["sv_id"])
    lop_id = int(body["lop_id"])
    diem = float(body["diem"])

    if diem < 0 or diem > 10:
        return jsonify({"ok": False, "tin_nhan": "Điểm từ 0 đến 10!"})

    db = doc_json()
    # Nếu đã có điểm thì sửa, chưa có thì thêm mới
    da_co = False
    for d in db["bang_diem"]:
        if d["sinh_vien_id"] == sv_id and d["lop_id"] == lop_id:
            d["diem"] = diem
            da_co = True
            break

    if not da_co:
        db["bang_diem"].append(
            {
                "id": len(db["bang_diem"]) + 1,
                "sinh_vien_id": sv_id,
                "lop_id": lop_id,
                "diem": diem,
            }
        )

    ghi_json(db)
    return jsonify({"ok": True, "tin_nhan": "Đã lưu điểm thành công!"})


# 7. QUẢN TRỊ VIÊN: THÊM & XÓA SINH VIÊN
@app.route("/api/admin-sinh-vien", methods=["GET", "POST", "DELETE"])
def admin_sinh_vien():
    db = doc_json()

    # Xem danh sách
    if request.method == "GET":
        return jsonify(db["sinh_vien"])

    # Thêm sinh viên mới
    if request.method == "POST":
        body = request.get_json()
        new_sv = {
            "id": len(db["sinh_vien"]) + 1,
            "ma_sv": body["ma_sv"],
            "mat_khau": "123456",
            "name": body["name"],
            "lop": body["lop"],
        }
        db["sinh_vien"].append(new_sv)
        ghi_json(db)
        return jsonify({"ok": True, "tin_nhan": "Thêm sinh viên thành công!"})

    # Xóa sinh viên (và xóa luôn điểm của sinh viên đó)
    if request.method == "DELETE":
        sv_id = int(request.args.get("id"))
        db["sinh_vien"] = [s for s in db["sinh_vien"] if s["id"] != sv_id]
        db["bang_diem"] = [
            d for d in db["bang_diem"] if d["sinh_vien_id"] != sv_id
        ]
        ghi_json(db)
        return jsonify({"ok": True, "tin_nhan": "Đã xóa sinh viên!"})


if __name__ == "__main__":
    app.run(debug=True)