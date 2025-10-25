import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100))
    role = db.Column(db.String(20), default="farmer")
    primary_crop = db.Column(db.String(100))
    region = db.Column(db.String(100))
    preferred_language = db.Column(db.String(20), default="en")

class ChatHistory(db.Model):
    __tablename__ = "chat_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_message = db.Column(db.Text)
    bot_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    feedback = db.Column(db.String(20), nullable=True)

def init_db(app):
    db_uri = os.getenv("DATABASE_URL", "sqlite:///agrobot.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        admin_email = os.getenv("ADMIN_EMAIL", "admin@agrobot.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")
        if not User.query.filter_by(email=admin_email).first():
            admin = User(email=admin_email, password=generate_password_hash(admin_password), name="Administrator", role="admin", preferred_language="en")
            db.session.add(admin); db.session.commit()
            print("Created default admin:", admin_email)
