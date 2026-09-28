function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

function loadClasses() {
    const classList = document.getElementById("classList");
    const loading = document.getElementById("loading");

    fetch("/api/classes")
        .then(response => {
            if (!response.ok) {
                throw new Error("Không thể tải danh sách lớp.");
            }
            return response.json();
        })
        .then(classes => {
            loading.style.display = "none";

            // Không có lớp
            if (classes.length === 0) {
                classList.innerHTML = `
                    <div class="col-12">
                        <div class="alert alert-info text-center">
                            Chưa có dữ liệu lớp học nào.
                        </div>
                    </div>
                `;
                return;
            }

            // Tạo các card lớp
            classes.forEach(c => {
                const card = document.createElement("div");
                card.className = "col-md-4";
                card.innerHTML = `
                    <div class="card shadow-sm border-primary h-100 class-card">
                        <div class="card-body text-center p-4">
                            <h4 class="card-title fw-bold text-primary">
                                ${esc(c.ma_lop)}
                            </h4>

                            <p class="text-muted mb-3">
                                Sĩ số:
                                <strong>${c.so_luong_sv}</strong>
                                sinh viên
                            </p>

                            <a
                                href="class.html?ma_lop=${encodeURIComponent(c.ma_lop)}"
                                class="btn btn-primary w-100 fw-bold"
                            >
                                👉 Vào Sổ Điểm
                            </a>
                        </div>
                    </div>
                `;
                classList.appendChild(card);
            });
        })
        .catch(error => {
            console.error(error);
            loading.style.display = "block";
            loading.innerHTML = `
                <div class="alert alert-danger">
                    Không thể tải danh sách lớp.
                </div>
            `;
        });
}

// Chạy khi trang được mở
loadClasses();