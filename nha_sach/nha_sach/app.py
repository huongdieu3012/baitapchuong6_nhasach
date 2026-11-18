import os

import click
from flask import Flask, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import func, select

from config import Config
from extensions import csrf, db, migrate
from utils import cart_count, vnd


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    import models  # noqa: F401  (đăng ký model cho migrate)
    from admin import bp as admin_bp
    from shop import bp as shop_bp

    app.register_blueprint(shop_bp)
    app.register_blueprint(admin_bp)

    app.jinja_env.filters["vnd"] = vnd

    @app.context_processor
    def inject_globals():
        data = {"cart_count": cart_count()}
        if request.blueprint == "admin":
            data["pending_orders"] = db.session.scalar(
                select(func.count(models.Order.id)).where(
                    models.Order.status == models.PENDING
                )
            )
        return data

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Không tìm thấy trang hoặc dữ liệu."), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", code=413, message="Tệp tải lên quá lớn (ảnh bìa tối đa 2 MB)."), 413

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_template(
            "error.html", code=400, message="Phiên làm việc đã hết hạn. Vui lòng tải lại trang và thử lại."
        ), 400

    register_commands(app)
    return app


def register_commands(app):
    @app.cli.command("seed")
    @click.option("--force", is_flag=True, help="Thêm dữ liệu mẫu dù CSDL đã có dữ liệu.")
    def seed(force):
        """Thêm danh mục và sách mẫu (chạy sau `flask db upgrade`)."""
        from models import Book, Category

        if db.session.scalar(select(func.count(Category.id))) and not force:
            click.echo("CSDL đã có dữ liệu. Dùng --force nếu vẫn muốn thêm.")
            return

        names = ["Lập trình", "Cơ sở dữ liệu", "Công cụ", "Mạng", "Kỹ năng lập trình", "Thiết kế"]
        cats = {n: Category(name=n) for n in names}
        db.session.add_all(cats.values())

        sample = [
            ("Lập trình Python cơ bản", "Nguyễn Văn A", "NXB Đại học Huế", 2024, 95000, 30, "Lập trình"),
            ("Giáo trình Flask", "Miguel Grinberg", "O'Reilly", 2018, 120000, 20, "Lập trình"),
            ("Cơ sở dữ liệu", "Trần Văn B", "NXB Giáo dục", 2020, 85000, 0, "Cơ sở dữ liệu"),
            ("Pro Git", "Scott Chacon", "Apress", 2014, 150000, 15, "Công cụ"),
            ("Mạng máy tính", "Lê Văn C", "NXB Khoa học và Kỹ thuật", 2019, 110000, 12, "Mạng"),
            ("Clean Code", "Robert C. Martin", "Prentice Hall", 2008, 180000, 5, "Kỹ năng lập trình"),
        ]
        for title, author, pub, year, price, stock, cat in sample:
            db.session.add(
                Book(
                    title=title, author=author, publisher=pub, year=year,
                    price=price, stock=stock, category=cats[cat],
                    description=f"Giới thiệu ngắn về cuốn \"{title}\".",
                )
            )
        db.session.commit()
        click.echo("Đã thêm 6 danh mục và 6 cuốn sách mẫu.")


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
