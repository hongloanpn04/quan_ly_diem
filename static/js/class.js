let students = [];
let subjects = [];

const params = new URLSearchParams(window.location.search);
const maLop = params.get("ma_lop");
let monId = params.get("mon_id");   // có thể null khi vào từ trang chủ

if (!maLop) {
    alert("Thiếu mã lớp.");
    window.location.href = "index.html";
} else {
    document.getElementById("maLop").textContent = maLop;
}


// ===============================
// HÀM HỖ TRỢ
// ===============================

function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

// Gọi API bằng fetch().then(); tự đọc JSON và ném lỗi kèm message của server
function goiApi(url, options) {
    return fetch(url, options).then(response =>
        response
            .json()
            .catch(() => ({}))
            .then(data => {
                if (!response.ok) {
                    throw new Error(data.message || "Yêu cầu thất bại.");
                }
                return data;
            })
    );
}


// ===============================
// TẢI DỮ LIỆU
// ===============================

function loadData() {
    let url = `/api/class/${encodeURIComponent(maLop)}`;
    if (monId) {
        url += `?mon_id=${encodeURIComponent(monId)}`;
    }

    goiApi(url)
        .then(data => {
            students = data.students;
            subjects = data.subjects;

            // Server trả về môn đang được chọn (môn đầu tiên nếu chưa chọn)
            monId = String(data.current_mon_id);

            hienThiMonHoc();
            hienThiSinhVien();
        })
        .catch(error => {
            console.error(error);
            alert(error.message || "Không thể tải dữ liệu lớp.");
        });
}


// ===============================
// HIỂN THỊ MÔN HỌC
// ===============================

function hienThiMonHoc() {
    const select = document.getElementById("monHoc");
    select.innerHTML = "";

    subjects.forEach(mon => {
        const option = document.createElement("option");
        option.value = mon.id;
        option.textContent =
            `${mon.ma_mon} - ${mon.ten_mon} (${mon.so_tin_chi} TC)`;
        if (String(mon.id) === String(monId)) {
            option.selected = true;
        }
        select.appendChild(option);
    });

    const monHienTai = subjects.find(m => String(m.id) === String(monId));
    if (monHienTai) {
        document.getElementById("tenMon").textContent = monHienTai.ten_mon;
        document.getElementById("maMon").textContent = monHienTai.ma_mon;
    }
}


// ===============================
// HIỂN THỊ SINH VIÊN
// ===============================

function hienThiSinhVien() {
    const tbody = document.getElementById("studentTableBody");
    tbody.innerHTML = "";

    document.getElementById("siSo").textContent = students.length;

    if (students.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-muted py-4">
                    Chưa có sinh viên nào trong lớp.
                </td>
            </tr>
        `;
        return;
    }

    students.forEach((sv, index) => {
        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td>${index + 1}</td>
            <td><strong>${esc(sv.mssv)}</strong></td>
            <td class="text-start">${esc(sv.ho_ten)}</td>
            <td>
                <input type="number" step="0.1" min="0" max="10"
                       class="form-control form-control-sm text-center fw-bold"
                       id="qt_${sv.sv_id}" value="${sv.diem_qt ?? ""}">
            </td>
            <td>
                <input type="number" step="0.1" min="0" max="10"
                       class="form-control form-control-sm text-center fw-bold"
                       id="ck_${sv.sv_id}" value="${sv.diem_ck ?? ""}">
            </td>
            <td id="tk_${sv.sv_id}">${hienThiTongKet(sv.diem_tk)}</td>
            <td id="loai_${sv.sv_id}">${xepLoai(sv.diem_tk)}</td>
            <td>
                <button class="btn btn-outline-danger btn-sm"
                        onclick="xoaSinhVien(${sv.sv_id})">
                    Xóa
                </button>
            </td>
        `;

        tbody.appendChild(tr);
    });
}


// ===============================
// TÍNH ĐIỂM TỔNG KẾT
// ===============================

function tinhTongKet(diemQt, diemCk) {
    if (diemQt === null || diemQt === "" || diemCk === null || diemCk === "") {
        return null;
    }
    return (Number(diemQt) * 0.4 + Number(diemCk) * 0.6).toFixed(1);
}

// Tự cập nhật Tổng Kết + Xếp Loại khi đang nhập điểm
document
    .getElementById("studentTableBody")
    .addEventListener("input", function (e) {
        const id = e.target.id;
        if (!id.startsWith("qt_") && !id.startsWith("ck_")) return;

        const svId = id.slice(3);
        const qt = document.getElementById(`qt_${svId}`).value;
        const ck = document.getElementById(`ck_${svId}`).value;
        const tk = tinhTongKet(qt, ck);

        document.getElementById(`tk_${svId}`).innerHTML = hienThiTongKet(tk);
        document.getElementById(`loai_${svId}`).innerHTML = xepLoai(tk);
    });


// ===============================
// XẾP LOẠI
// ===============================

function xepLoai(diem) {
    if (diem === null || diem === undefined) {
        return `<span class="badge bg-light text-muted border">Chưa xét</span>`;
    }

    diem = Number(diem);

    if (diem >= 8.5) return `<span class="badge bg-success">Giỏi (A)</span>`;
    if (diem >= 7.0) return `<span class="badge bg-info text-dark">Khá (B)</span>`;
    if (diem >= 5.5) return `<span class="badge bg-warning text-dark">TB (C)</span>`;
    if (diem >= 4.0) return `<span class="badge bg-secondary">Yếu (D)</span>`;
    return `<span class="badge bg-danger">Học Lại (F)</span>`;
}

function hienThiTongKet(diem) {
    if (diem === null || diem === undefined) {
        return `<span class="text-muted fst-italic">Chưa có</span>`;
    }
    return `<strong class="text-primary fs-6">${diem}</strong>`;
}


// ===============================
// LƯU ĐIỂM
// ===============================

function luuDiem() {
    const danhSachDiem = [];

    for (const sv of students) {
        const qt = document.getElementById(`qt_${sv.sv_id}`).value;
        const ck = document.getElementById(`ck_${sv.sv_id}`).value;

        const diemQt = qt === "" ? null : Number(qt);
        const diemCk = ck === "" ? null : Number(ck);

        const hopLe = d => d === null || (d >= 0 && d <= 10);
        if (!hopLe(diemQt) || !hopLe(diemCk)) {
            alert(`Điểm của ${sv.mssv} phải từ 0 đến 10.`);
            return;
        }

        danhSachDiem.push({ sv_id: sv.sv_id, diem_qt: diemQt, diem_ck: diemCk });
    }

    goiApi(`/api/class/${encodeURIComponent(maLop)}/update-grades`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            mon_id: Number(monId),
            grades: danhSachDiem
        })
    })
        .then(() => {
            alert("Đã lưu bảng điểm.");
            loadData();
        })
        .catch(error => {
            console.error(error);
            alert(error.message || "Có lỗi khi kết nối máy chủ.");
        });
}


// ===============================
// TÌM SINH VIÊN (chỉ lọc theo MSSV và họ tên)
// ===============================

function timSinhVien() {
    const keyword = document
        .getElementById("searchInput")
        .value.trim()
        .toLowerCase();

    document.querySelectorAll("#studentTableBody tr").forEach(row => {
        if (row.cells.length < 3) return;   // dòng "chưa có sinh viên"
        const text =
            (row.cells[1].textContent + " " + row.cells[2].textContent)
                .toLowerCase();
        row.style.display = text.includes(keyword) ? "" : "none";
    });
}

function boLoc() {
    document.getElementById("searchInput").value = "";
    timSinhVien();   // chỉ hiện lại các dòng, không làm mất điểm đang nhập
}

document.getElementById("searchInput").addEventListener("input", timSinhVien);


// ===============================
// XÓA SINH VIÊN
// ===============================

function xoaSinhVien(id) {
    if (!confirm("Bạn có chắc muốn xóa sinh viên này? Điểm của sinh viên ở mọi môn cũng bị xóa.")) {
        return;
    }

    goiApi(`/api/class/${encodeURIComponent(maLop)}/delete-student/${id}`, {
        method: "DELETE"
    })
        .then(() => {
            alert("Đã xóa sinh viên.");
            loadData();
        })
        .catch(error => {
            console.error(error);
            alert(error.message || "Có lỗi khi xóa sinh viên.");
        });
}


// ===============================
// THÊM SINH VIÊN
// ===============================

document
    .getElementById("addStudentForm")
    .addEventListener("submit", function (event) {
        event.preventDefault();

        const mssv = document.getElementById("mssv").value.trim();
        const hoTen = document.getElementById("hoTen").value.trim();

        goiApi(`/api/class/${encodeURIComponent(maLop)}/add-student`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mssv: mssv, ho_ten: hoTen })
        })
            .then(() => {
                alert("Đã thêm sinh viên.");
                document.getElementById("addStudentForm").reset();
                bootstrap.Modal
                    .getInstance(document.getElementById("addStudentModal"))
                    .hide();
                loadData();
            })
            .catch(error => {
                console.error(error);
                alert(error.message || "Có lỗi khi thêm sinh viên.");
            });
    });


// ===============================
// ĐỔI MÔN
// ===============================

document.getElementById("monHoc").addEventListener("change", function () {
    window.location.href =
        `class.html?ma_lop=${encodeURIComponent(maLop)}&mon_id=${this.value}`;
});


// CHẠY KHI MỞ TRANG
if (maLop) {
    loadData();
}