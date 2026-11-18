from datetime import datetime

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from sqlalchemy import select
from wtforms import IntegerField, RadioField, SelectField, StringField, TextAreaField
from wtforms.validators import (
    DataRequired,
    Email,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from extensions import db
from models import Book, Category
from utils import is_valid_image


def strip(value):
    return value.strip() if isinstance(value, str) else value


def _exists_casefold(model, column, value, exclude_id=None):
    """So sánh không phân biệt hoa thường (kể cả tiếng Việt có dấu).

    SQLite chỉ hạ chữ thường được ASCII nên so sánh trong Python.
    """
    wanted = (value or "").strip().casefold()
    for row_id, text in db.session.execute(select(model.id, column)).all():
        if row_id != exclude_id and (text or "").strip().casefold() == wanted:
            return True
    return False


# ---- ④ Thông tin khách hàng -----------------------------------------------------
class CheckoutForm(FlaskForm):
    full_name = StringField(
        "Họ tên",
        filters=[strip],
        validators=[DataRequired("Vui lòng nhập họ tên."), Length(max=100)],
    )
    phone = StringField(
        "Số điện thoại",
        filters=[strip],
        validators=[
            DataRequired("Vui lòng nhập số điện thoại."),
            Regexp(r"^0\d{9}$", message="Số điện thoại gồm 10 chữ số, bắt đầu bằng 0."),
        ],
    )
    email = StringField(
        "Email",
        filters=[strip],
        validators=[Optional(), Email("Email không đúng định dạng."), Length(max=120)],
    )
    address = StringField(
        "Địa chỉ giao hàng",
        filters=[strip],
        validators=[DataRequired("Vui lòng nhập địa chỉ giao hàng."), Length(max=255)],
    )
    note = TextAreaField("Ghi chú", filters=[strip], validators=[Optional(), Length(max=500)])
    payment_method = RadioField(
        "Thanh toán",
        choices=[("cod", "Tiền mặt khi nhận hàng"), ("bank", "Chuyển khoản")],
        default="cod",
        validators=[DataRequired("Vui lòng chọn hình thức thanh toán.")],
    )


# ---- ⑧ Thêm / sửa sách ----------------------------------------------------------
class BookForm(FlaskForm):
    title = StringField(
        "Tên sách",
        filters=[strip],
        validators=[DataRequired("Vui lòng nhập tên sách."), Length(max=200)],
    )
    author = StringField(
        "Tác giả",
        filters=[strip],
        validators=[DataRequired("Vui lòng nhập tác giả."), Length(max=150)],
    )
    publisher = StringField("Nhà xuất bản", filters=[strip], validators=[Optional(), Length(max=150)])
    category_id = SelectField(
        "Danh mục",
        coerce=int,
        validators=[DataRequired("Vui lòng chọn danh mục.")],
    )
    year = IntegerField("Năm xuất bản", validators=[Optional()])
    price = IntegerField(
        "Giá (đồng)",
        validators=[
            InputRequired("Vui lòng nhập giá."),
            NumberRange(min=1000, message="Giá tối thiểu 1.000 đồng."),
        ],
    )
    stock = IntegerField(
        "Tồn kho",
        validators=[
            InputRequired("Vui lòng nhập tồn kho."),
            NumberRange(min=0, message="Tồn kho không âm."),
        ],
    )
    description = TextAreaField("Mô tả", filters=[strip], validators=[Optional()])
    # Đặt tên khác "cover" để không bị điền nhầm từ thuộc tính Book.cover (chuỗi)
    cover_file = FileField(
        "Ảnh bìa",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Chỉ nhận ảnh JPG, PNG, WEBP."),
            FileSize(max_size=2 * 1024 * 1024, message="Ảnh tối đa 2 MB."),
        ],
    )

    def __init__(self, *args, book_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.book_id = book_id
        cats = db.session.scalars(select(Category).order_by(Category.name)).all()
        self.category_id.choices = [(c.id, c.name) for c in cats]

    def validate_title(self, field):
        if _exists_casefold(Book, Book.title, field.data, exclude_id=self.book_id):
            raise ValidationError("Tên sách đã tồn tại.")

    def validate_year(self, field):
        if field.data is None:
            return
        this_year = datetime.now().year
        if not 1900 <= field.data <= this_year:
            raise ValidationError(f"Năm xuất bản từ 1900 đến {this_year}.")

    def validate_cover_file(self, field):
        if field.data and not is_valid_image(field.data):
            raise ValidationError("Tệp không phải ảnh JPG, PNG, WEBP hợp lệ.")


# ---- ⑨ Danh mục -----------------------------------------------------------------
class CategoryForm(FlaskForm):
    name = StringField(
        "Tên",
        filters=[strip],
        validators=[DataRequired("Vui lòng nhập tên danh mục."), Length(max=100)],
    )
    description = TextAreaField("Mô tả", filters=[strip], validators=[Optional()])

    def __init__(self, *args, category_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id = category_id

    def validate_name(self, field):
        if _exists_casefold(Category, Category.name, field.data, exclude_id=self.category_id):
            raise ValidationError("Danh mục đã tồn tại.")
