from datetime import datetime

from extensions import db

# ---- Trạng thái đơn hàng ----------------------------------------------------
PENDING = "Chờ xác nhận"
SHIPPING = "Đang giao"
DONE = "Hoàn tất"
CANCELED = "Đã huỷ"
STATUSES = [PENDING, SHIPPING, DONE, CANCELED]

# Chuyển trạng thái hợp lệ
TRANSITIONS = {
    PENDING: [SHIPPING, CANCELED],
    SHIPPING: [DONE, CANCELED],
    DONE: [],
    CANCELED: [],
}
STATUS_CLASS = {
    PENDING: "status-pending",
    SHIPPING: "status-shipping",
    DONE: "status-done",
    CANCELED: "status-canceled",
}
PAYMENT_LABELS = {"cod": "Tiền mặt khi nhận hàng", "bank": "Chuyển khoản"}

LOW_STOCK = 5  # sách "sắp hết" khi tồn kho <= 5


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

    books = db.relationship("Book", back_populates="category")

    def __repr__(self):
        return f"<Category {self.name}>"


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(150), nullable=False)
    publisher = db.Column(db.String(150))
    year = db.Column(db.Integer)
    price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.Text)
    cover = db.Column(db.String(100))  # tên file ảnh trong static/uploads/covers
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)

    category = db.relationship("Category", back_populates="books")
    order_items = db.relationship("OrderItem", back_populates="book")

    def __repr__(self):
        return f"<Book {self.title}>"


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    address = db.Column(db.String(255), nullable=False)
    note = db.Column(db.Text)
    payment_method = db.Column(db.String(10), nullable=False, default="cod")
    status = db.Column(db.String(20), nullable=False, default=PENDING)
    subtotal = db.Column(db.Integer, nullable=False)
    shipping_fee = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    items = db.relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    logs = db.relationship(
        "OrderLog",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLog.id",
    )

    @property
    def status_class(self):
        return STATUS_CLASS.get(self.status, "")

    @property
    def payment_label(self):
        return PAYMENT_LABELS.get(self.payment_method, self.payment_method)

    @property
    def next_status(self):
        """Bước tiếp theo trong luồng xử lý (không tính Huỷ)."""
        if self.status == PENDING:
            return SHIPPING
        if self.status == SHIPPING:
            return DONE
        return None

    @property
    def can_cancel(self):
        return CANCELED in TRANSITIONS.get(self.status, [])

    @property
    def upcoming_steps(self):
        flow = [PENDING, SHIPPING, DONE]
        if self.status not in flow:
            return []
        return flow[flow.index(self.status) + 1:]


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Integer, nullable=False)  # giá tại thời điểm đặt

    order = db.relationship("Order", back_populates="items")
    book = db.relationship("Book", back_populates="order_items")

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class OrderLog(db.Model):
    """Lịch sử đổi trạng thái của đơn hàng."""

    __tablename__ = "order_logs"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    order = db.relationship("Order", back_populates="logs")
