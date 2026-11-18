# Nhà sách Sông Hương

Bài tập tổng hợp Chương 5–6 (Phần mềm mã nguồn mở): trang bán hàng ①–⑤ và trang quản trị ⑥–⑪.
Flask · Flask-SQLAlchemy · Flask-Migrate · Flask-WTF · Jinja2 · Bootstrap 5 · SQLite.

## Chạy ứng dụng

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

flask --app app db init           # chỉ lần đầu: tạo thư mục migrations
flask --app app db migrate -m "tao bang ban dau"
flask --app app db upgrade
flask --app app seed              # 6 danh mục + 6 sách mẫu

flask --app app run --debug
```

- Trang bán hàng: http://127.0.0.1:5000/books
- Trang quản trị: http://127.0.0.1:5000/admin

## Cấu trúc

| File | Vai trò |
|---|---|
| `app.py` | Tạo app, đăng ký blueprint, bộ lọc `vnd`, xử lý lỗi, lệnh `flask seed` |
| `models.py` | Category, Book, Order, OrderItem, OrderLog + hằng trạng thái |
| `forms.py` | CheckoutForm, BookForm, CategoryForm (Flask-WTF) |
| `shop.py` | ① Danh sách · ② Chọn sách · ③ Giỏ hàng · ④ Đặt hàng · ⑤ Thành công |
| `admin.py` | ⑥ Tổng quan · ⑦⑧ Sách · ⑨ Danh mục · ⑩⑪ Đơn hàng |
| `utils.py` | Giỏ hàng trong session, phí giao hàng, xử lý ảnh bìa |

## Ghi chú thiết kế

- Giỏ hàng lưu trong session dạng `{id_sách: số lượng}`; giá luôn đọc mới từ CSDL.
- Mọi thao tác thay đổi dữ liệu là form POST có CSRF token và chuyển hướng (PRG).
- Đặt hàng: kiểm tra lại tồn kho → tạo Order + OrderItem (lưu đơn giá lúc đặt) → trừ kho → xoá giỏ.
- Huỷ đơn hoàn lại tồn kho; mỗi lần đổi trạng thái ghi vào `OrderLog` để hiện lịch sử.
- Trang `/orders/<id>` chỉ xem được với đơn do chính phiên trình duyệt đó vừa đặt (tránh lộ thông tin khách).
- Đề không yêu cầu đăng nhập nên `/admin` chưa có xác thực; không đưa lên mạng công khai khi chưa thêm đăng nhập.
- Tìm kiếm dùng `ILIKE` của SQLite nên chỉ không phân biệt hoa thường với chữ không dấu; việc kiểm tra trùng tên sách/danh mục thì so sánh trong Python nên đúng cả với tiếng Việt có dấu.
