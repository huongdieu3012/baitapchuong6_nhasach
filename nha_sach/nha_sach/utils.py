import os
import uuid

from flask import current_app, session
from PIL import Image
from sqlalchemy import select

from extensions import db
from models import Book

SHIPPING_FEE = 20000
FREE_SHIPPING_FROM = 200000

_IMAGE_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


# ---- Định dạng ---------------------------------------------------------------
def vnd(value):
    """95000 -> '95.000 đ'"""
    return f"{int(value or 0):,}".replace(",", ".") + " đ"


# ---- Chuyển hướng an toàn ----------------------------------------------------
def safe_next(target, fallback):
    """Chỉ cho phép chuyển hướng về đường dẫn nội bộ."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback


# ---- Giỏ hàng (session): {"<book_id>": số lượng} ------------------------------
def get_cart():
    cart = session.get("cart")
    return dict(cart) if isinstance(cart, dict) else {}


def save_cart(cart):
    session["cart"] = cart
    session.modified = True


def cart_count():
    return sum(int(q) for q in get_cart().values())


def cart_lines():
    """Trả về (danh sách dòng, tạm tính). Giá luôn lấy mới nhất từ CSDL."""
    cart = get_cart()
    if not cart:
        return [], 0

    ids = []
    for key in cart:
        try:
            ids.append(int(key))
        except ValueError:
            pass
    books = {
        b.id: b for b in db.session.scalars(select(Book).where(Book.id.in_(ids)))
    }

    lines, subtotal, cleaned = [], 0, {}
    for key, qty in cart.items():
        try:
            book = books.get(int(key))
            qty = int(qty)
        except (ValueError, TypeError):
            continue
        if book is None or qty < 1:
            continue  # sách đã bị xoá khỏi CSDL
        cleaned[key] = qty
        total = book.price * qty
        subtotal += total
        lines.append({"book": book, "qty": qty, "total": total})

    if cleaned != cart:
        save_cart(cleaned)
    return lines, subtotal


def shipping_fee(subtotal):
    if subtotal <= 0 or subtotal >= FREE_SHIPPING_FROM:
        return 0
    return SHIPPING_FEE


# ---- Ảnh bìa ----------------------------------------------------------------
def is_valid_image(file_storage):
    """Kiểm tra tệp thật sự là JPG/PNG/WEBP (không chỉ dựa vào đuôi tên)."""
    try:
        img = Image.open(file_storage.stream)
        fmt = img.format
        img.verify()
    except Exception:
        return False
    finally:
        file_storage.stream.seek(0)
    return fmt in _IMAGE_EXT


def save_cover(file_storage):
    """Lưu ảnh với tên ngẫu nhiên, trả về tên file."""
    img = Image.open(file_storage.stream)
    ext = _IMAGE_EXT[img.format]
    file_storage.stream.seek(0)
    name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))
    return name


def delete_cover(name):
    if not name:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(name))
    if os.path.isfile(path):
        os.remove(path)
