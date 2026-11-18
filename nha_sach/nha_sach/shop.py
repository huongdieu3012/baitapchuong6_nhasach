from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import or_, select

from extensions import db
from forms import CheckoutForm
from models import PENDING, Book, Category, Order, OrderItem, OrderLog
from utils import (
    FREE_SHIPPING_FROM,
    cart_lines,
    get_cart,
    safe_next,
    save_cart,
    shipping_fee,
)

bp = Blueprint("shop", __name__)


@bp.route("/")
def home():
    return redirect(url_for("shop.book_list"))


# ---- ① Danh sách sách --------------------------------------------------------
@bp.route("/books")
def book_list():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)

    stmt = select(Book).order_by(Book.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Book.title.ilike(like), Book.author.ilike(like)))
    if category_id:
        stmt = stmt.where(Book.category_id == category_id)

    books = db.session.scalars(stmt).all()
    categories = db.session.scalars(select(Category).order_by(Category.name)).all()
    return render_template(
        "shop/book_list.html", books=books, categories=categories, q=q, category_id=category_id
    )


# ---- ② Chọn sách ------------------------------------------------------------
@bp.route("/books/<int:book_id>")
def book_detail(book_id):
    book = db.get_or_404(Book, book_id)
    in_cart = get_cart().get(str(book.id), 0)
    max_add = max(book.stock - in_cart, 0)
    return render_template("shop/book_detail.html", book=book, in_cart=in_cart, max_add=max_add)


@bp.post("/cart/add/<int:book_id>")
def cart_add(book_id):
    book = db.get_or_404(Book, book_id)
    target = safe_next(request.form.get("next"), url_for("shop.book_detail", book_id=book.id))

    try:
        qty = int(request.form.get("quantity", 1))
    except ValueError:
        qty = 0

    cart = get_cart()
    in_cart = cart.get(str(book.id), 0)
    max_add = book.stock - in_cart

    if book.stock <= 0:
        flash(f"“{book.title}” đã hết hàng.", "danger")
        return redirect(target)
    if max_add <= 0:
        flash(f"Trong giỏ đã có {in_cart} cuốn “{book.title}”, bằng số lượng tồn kho.", "warning")
        return redirect(target)
    if qty < 1 or qty > max_add:
        flash(f"Số lượng không hợp lệ: chọn từ 1 đến {max_add}.", "danger")
        return redirect(target)

    cart[str(book.id)] = in_cart + qty  # sách đã có: cộng dồn
    save_cart(cart)
    flash(f"Đã thêm {qty} × {book.title} vào giỏ hàng.", "success")
    return redirect(target)


# ---- ③ Giỏ hàng -------------------------------------------------------------
@bp.route("/cart")
def cart():
    lines, subtotal = cart_lines()
    return render_template("shop/cart.html", lines=lines, subtotal=subtotal)


@bp.post("/cart/increase/<int:book_id>")
def cart_increase(book_id):
    book = db.get_or_404(Book, book_id)
    cart = get_cart()
    qty = cart.get(str(book.id))
    if qty is not None:
        if qty + 1 > book.stock:
            flash(f"“{book.title}” chỉ còn {book.stock} cuốn.", "warning")
        else:
            cart[str(book.id)] = qty + 1
            save_cart(cart)
    return redirect(url_for("shop.cart"))


@bp.post("/cart/decrease/<int:book_id>")
def cart_decrease(book_id):
    cart = get_cart()
    key = str(book_id)
    if key in cart:
        if cart[key] - 1 <= 0:
            del cart[key]
        else:
            cart[key] -= 1
        save_cart(cart)
    return redirect(url_for("shop.cart"))


@bp.post("/cart/remove/<int:book_id>")
def cart_remove(book_id):
    cart = get_cart()
    if cart.pop(str(book_id), None) is not None:
        save_cart(cart)
        flash("Đã bỏ sách khỏi giỏ hàng.", "info")
    return redirect(url_for("shop.cart"))


@bp.post("/cart/clear")
def cart_clear():
    save_cart({})
    flash("Đã xoá toàn bộ giỏ hàng.", "info")
    return redirect(url_for("shop.cart"))


# ---- ④ Thông tin khách hàng / đặt hàng ----------------------------------------
@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, subtotal = cart_lines()
    if not lines:
        flash("Giỏ hàng trống, hãy chọn sách trước khi đặt hàng.", "warning")
        return redirect(url_for("shop.cart"))

    fee = shipping_fee(subtotal)
    form = CheckoutForm()

    if form.validate_on_submit():
        # Kiểm tra lại tồn kho ngay lúc xác nhận
        shortages = [
            f"“{l['book'].title}” (còn {l['book'].stock}, bạn chọn {l['qty']})"
            for l in lines
            if l["qty"] > l["book"].stock
        ]
        if shortages:
            flash("Không đủ hàng: " + "; ".join(shortages) + ". Vui lòng điều chỉnh giỏ hàng.", "danger")
            return redirect(url_for("shop.cart"))

        order = Order(
            full_name=form.full_name.data,
            phone=form.phone.data,
            email=form.email.data or None,
            address=form.address.data,
            note=form.note.data or None,
            payment_method=form.payment_method.data,
            status=PENDING,
            subtotal=subtotal,
            shipping_fee=fee,
            total=subtotal + fee,
        )
        for l in lines:
            order.items.append(
                OrderItem(book_id=l["book"].id, quantity=l["qty"], unit_price=l["book"].price)
            )
            l["book"].stock -= l["qty"]
        order.logs.append(OrderLog(status=PENDING, note="Đặt hàng"))

        db.session.add(order)
        db.session.commit()

        save_cart({})
        mine = session.get("my_orders", [])
        mine.append(order.id)
        session["my_orders"] = mine
        return redirect(url_for("shop.order_success", order_id=order.id))

    return render_template(
        "shop/checkout.html",
        form=form, lines=lines, subtotal=subtotal, fee=fee, free_from=FREE_SHIPPING_FROM,
    )


# ---- ⑤ Đặt thành công ---------------------------------------------------------
@bp.route("/orders/<int:order_id>")
def order_success(order_id):
    order = db.get_or_404(Order, order_id)
    # Khách chỉ xem được đơn do chính phiên của mình vừa đặt
    if order.id not in session.get("my_orders", []):
        abort(404)
    return render_template("shop/order_success.html", order=order)
