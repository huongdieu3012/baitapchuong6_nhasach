import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "doi-khoa-bi-mat-nay-khi-trien-khai")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "nhasach.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "covers")
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024  # chặn request quá lớn; ảnh bìa tối đa 2 MB
