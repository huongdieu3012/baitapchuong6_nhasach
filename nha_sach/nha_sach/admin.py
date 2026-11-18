from datetime import date, datetime, time, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from extensions import db
from forms import BookForm, CategoryForm
from models import (
    CANCELED,
    DONE,
    LOW_STOCK,
    PENDING,
    STATUSES,
    TRANSITIONS,
    Book,
    Category,
    Order,
    OrderItem,
    OrderLog,
)
from utils import delete_cover, safe_next, save_cover

bp = Blueprint("admin", __name__, url_prefix="/admin")

BOOKS_PER_PAGE = 5
ORDERS_PER_PAGE = 10


# ---- ⑥ Tổng quan ------------------------------------------------------------
@bp.route("/")
def dashboard():
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    next_month = (
        datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
    )

    total_books = db.session.scalar(select(func.count(Book.id)))
    pending = db.session.scalar(select(func.count(Order.id)).where(Order.status == PENDING))
    revenue = db.session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.status == DONE,
            Order.created_at >= month_start,
            Order.created_at < next_month,
        )
    )
    low_count = db.session.scalar(select(func.count(Book.id)).where(Book.stock <= LOW_STOCK))

    latest = db.session.scalars(select(Order).order_by(Order.id.desc()).limit(5)).all()
    low_books = db.session.scalars(
        select(Book).where(Book.stock <= LOW_STOCK).order_by(Book.stock, Book.title).limit(10)
    ).all()

    # (Tuỳ chọn) Doanh thu 7 ngày gần nhất, tính các đơn Hoàn tất
    today = date.today()
    start = datetime.combine(today - timedelta(days=6), time.min)
    rows = db.session.execute(
        select(func.date(Order.created_at), func.sum(Order.total))
        .where(Order.status == DONE, Order.created_at >= start)
        .group_by(func.date(Order.created_at))
    ).all()
    by_day = {str(d): int(s) for d, s in rows}
    chart = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        chart.append({"label": d.strftime("%d/%m"), "value": by_day.get(d.isoformat(), 0)})
    chart_max = max([c["value"] for c in chart] + [1])

    return render_template(
        "admin/dashboard.html",
        total_books=total_books, pending=pending, revenue=revenue, low_count=low_count,
        latest=latest, low_books=low_books, month=now.month,
        chart=chart, chart_max=chart_max, low_stock=LOW_STOCK,
    )


# ---- ⑦ Quản lý sách -----------------------------------------------------------
@bp.route("/books")
def books():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)
    stock = request.args.get("stock", "")
    page = request.args.get("page", 1, type=int)

    stmt = select(Book).order_by(Book.created_at.desc(), Book.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Book.title.ilike(like), Book.author.ilike(like)))
    if category_id:
        stmt = stmt.where(Book.category_id == category_id)
    if stock == "con":
        stmt = stmt.where(Book.stock > 0)
    elif stock == "sap_het":
        stmt = stmt.where(Book.stock <= LOW_STOCK)
    elif stock == "het":
        stmt = stmt.where(Book.stock == 0)

    pagination = db.paginate(stmt, page=page, per_page=BOOKS_PER_PAGE, error_out=False)
    categories = db.session.scalars(select(Category).order_by(Category.name)).all()
    # Sách đã nằm trong đơn hàng thì không xoá được
    ordered_ids = set(db.session.scalars(select(OrderItem.book_id).distinct()))

    first = (pagination.page - 1) * BOOKS_PER_PAGE + 1 if pagination.total else 0
    last = first + len(pagination.items) - 1 if pagination.total else 0
    filters = {k: v for k, v in request.args.items() if k != "page" and v}

    return render_template(
        "admin/books.html",
        pagination=pagination, categories=categories, ordered_ids=ordered_ids,
        q=q, category_id=category_id, stock=stock, filters=filters,
        first=first, last=last, low_stock=LOW_STOCK,
    )


# ---- ⑧ Thêm / sửa sách (một form, một template) --------------------------------
@bp.route("/books/new", methods=["GET", "POST"])
@bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def book_form(book_id=None):
    book = db.get_or_404(Book, book_id) if book_id else None
    form = BookForm(obj=book, book_id=book_id)

    if not form.category_id.choices:
        flash("Hãy tạo ít nhất một danh mục trước khi thêm sách.", "warning")
        return redirect(url_for("admin.categories"))

    if form.validate_on_submit():
        is_new = book is None
        if is_new:
            book = Book()
        book.title = form.title.data
        book.author = form.author.data
        book.publisher = form.publisher.data or None
        book.category_id = form.category_id.data
        book.year = form.year.data
        book.price = form.price.data
        book.stock = form.stock.data
        book.description = form.description.data or None

        new_file = form.cover_file.data
        if new_file:
            old = book.cover
            book.cover = save_cover(new_file)
            if old:
                delete_cover(old)

        db.session.add(book)
        db.session.commit()
        flash(f"Đã {'thêm' if is_new else 'cập nhật'} sách “{book.title}”.", "success")
        return redirect(url_for("admin.books"))

    return render_template("admin/book_form.html", form=form, book=book)


@bp.post("/books/<int:book_id>/delete")
def book_delete(book_id):
    book = db.get_or_404(Book, book_id)
    target = safe_next(request.form.get("next"), url_for("admin.books"))

    used = db.session.scalar(select(func.count(OrderItem.id)).where(OrderItem.book_id == book.id))
    if used:
        flash(f"Không thể xoá “{book.title}”: sách đã có trong đơn hàng.", "danger")
        return redirect(target)

    title, cover = book.title, book.cover
    db.session.delete(book)
    db.session.commit()
    delete_cover(cover)
    flash(f"Đã xoá sách “{title}”.", "success")
    return redirect(target)


# ---- ⑨ Danh mục ---------------------------------------------------------------
@bp.route("/categories", methods=["GET", "POST"])
@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
def categories(category_id=None):
    editing = db.get_or_404(Category, category_id) if category_id else None
    form = CategoryForm(obj=editing, category_id=category_id)

    if form.validate_on_submit():
        if editing:
            editing.name = form.name.data
            editing.description = form.description.data or None
            flash(f"Đã cập nhật danh mục “{editing.name}”.", "success")
        else:
            db.session.add(Category(name=form.name.data, description=form.description.data or None))
            flash(f"Đã thêm danh mục “{form.name.data}”.", "success")
        db.session.commit()
        return redirect(url_for("admin.categories"))

    # Một truy vấn group_by, outer join để vẫn hiện danh mục chưa có sách
    rows = db.session.execute(
        select(Category, func.count(Book.id))
        .outerjoin(Book, Book.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.id)
    ).all()
    return render_template("admin/categories.html", rows=rows, form=form, editing=editing)


@bp.post("/categories/<int:category_id>/delete")
def category_delete(category_id):
    category = db.get_or_404(Category, category_id)
    count = db.session.scalar(select(func.count(Book.id)).where(Book.category_id == category.id))
    if count:
        flash(f"Không thể xoá “{category.name}”: còn {count} sách.", "danger")
    else:
        name = category.name
        db.session.delete(category)
        db.session.commit()
        flash(f"Đã xoá danh mục “{name}”.", "success")
    return redirect(url_for("admin.categories"))


# ---- ⑩ Danh sách đơn hàng -------------------------------------------------------
@bp.route("/orders")
def orders():
    status = request.args.get("status", "")
    if status not in STATUSES:
        status = ""
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    conds = []
    if status:
        conds.append(Order.status == status)
    if q:
        like = f"%{q}%"
        search = [Order.full_name.ilike(like), Order.phone.ilike(like)]
        digits = q.lstrip("#")
        if digits.isdigit():
            search.append(Order.id == int(digits))
        conds.append(or_(*search))

    stmt = select(Order).where(*conds).order_by(Order.created_at.desc(), Order.id.desc())
    pagination = db.paginate(stmt, page=page, per_page=ORDERS_PER_PAGE, error_out=False)

    # Số đơn mỗi trạng thái: một truy vấn group_by
    counts = dict(
        db.session.execute(select(Order.status, func.count(Order.id)).group_by(Order.status)).all()
    )
    all_count = sum(counts.values())

    # Dòng cuối: số đơn và tổng giá trị của bộ lọc hiện tại
    sum_count, sum_total = db.session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.total), 0)).where(*conds)
    ).one()

    filters = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template(
        "admin/orders.html",
        pagination=pagination, status=status, q=q, statuses=STATUSES, counts=counts,
        all_count=all_count, sum_count=sum_count, sum_total=sum_total, filters=filters,
    )


# ---- ⑪ Chi tiết đơn hàng --------------------------------------------------------
@bp.route("/orders/<int:order_id>")
def order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    return render_template("admin/order_detail.html", order=order)


@bp.post("/orders/<int:order_id>/status")
def order_status(order_id):
    order = db.get_or_404(Order, order_id)
    new_status = request.form.get("status", "")

    if new_status not in TRANSITIONS.get(order.status, []):
        flash(f"Không thể chuyển từ “{order.status}” sang “{new_status}”.", "danger")
        return redirect(url_for("admin.order_detail", order_id=order.id))

    if new_status == CANCELED:
        for item in order.items:  # hoàn lại tồn kho
            item.book.stock += item.quantity
        note = "Huỷ đơn, hoàn lại tồn kho"
    else:
        note = "Cập nhật trạng thái"

    order.status = new_status
    order.logs.append(OrderLog(status=new_status, note=note))
    db.session.commit()
    flash(f"Đơn #{order.id} đã chuyển sang “{new_status}”.", "success")
    return redirect(url_for("admin.order_detail", order_id=order.id))
