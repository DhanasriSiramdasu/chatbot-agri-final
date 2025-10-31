import os, json, time, base64, io, random
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from database import init_db, db, User, ChatHistory
from chatbot_model import process_message, load_kb, KB_PATH
from utils.safety import contains_blocked, sanitize_output

# --------------------------
# Setup
# --------------------------
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "super_secret_key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Database
init_db(app)

# Login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --------------------------
# Routes
# --------------------------

@app.route("/")
def index():
    recent_users = []
    if current_user.is_authenticated and current_user.role == "admin":
        recent_users = User.query.order_by(User.id.desc()).limit(20).all()
    return render_template("index.html", recent_users=recent_users)


# --------------------------
# Auth
# --------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "warning")
            return redirect(url_for("register"))
        user = User(
            email=email,
            password=generate_password_hash(request.form["password"]),
            name=request.form.get("name", ""),
            primary_crop=request.form.get("primary_crop", ""),
            region=request.form.get("region", ""),
            preferred_language=request.form.get("preferred_language", "en"),
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful — please log in", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            flash("Welcome back, " + (user.name or "Farmer") + "!", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("index"))


# --------------------------
# Profile
# --------------------------
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", "")
        current_user.primary_crop = request.form.get("primary_crop", "")
        current_user.region = request.form.get("region", "")
        current_user.preferred_language = request.form.get("preferred_language", "en")
        db.session.commit()
        flash("Profile updated", "success")
    return render_template("profile.html")


# --------------------------
# Chat API (text + image)
# --------------------------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json() or {}
        message = (data.get("message") or "").strip()
        image_data = data.get("image")

        if not message and not image_data:
            return jsonify({"response": "Please type a question or upload an image."})

        reply = ""

        # 🖼️ Handle image
        if image_data:
            try:
                # Split header from base64 data
                if "," in image_data:
                    header, encoded = image_data.split(",", 1)
                else:
                    encoded = image_data
                
                # Decode and process image
                file_bytes = io.BytesIO(base64.b64decode(encoded))
                im = Image.open(file_bytes).convert("RGB").resize((200, 200))

                pixels = list(im.getdata())
                greens = sum(1 for r, g, b in pixels if g > r + 10 and g > b + 10)
                healthy_ratio = greens / len(pixels)

                # Generate analysis based on green ratio
                if healthy_ratio < 0.05:
                    analysis = "Severe discoloration detected"
                    advice = "Possible disease or drought stress. Inspect plants closely and consider soil testing."
                elif healthy_ratio < 0.4:
                    analysis = "Partial leaf damage"
                    advice = "Early-stage pest or nutrient issue. Check for insects and consider fertilization."
                else:
                    analysis = "Healthy leaf"
                    advice = "Maintain consistent watering and sunlight. Continue current care routine."
                
                reply = f"🧪 Analysis: {analysis}\n💡 Advice: {advice}"
                
            except Exception as img_error:
                print(f"Image processing error: {img_error}")
                import traceback
                traceback.print_exc()
                return jsonify({""}), 400
        
        else:
            # 💬 Handle text
            if contains_blocked(message):
                return jsonify({"response": "⚠️ Message contains prohibited content."}), 400

            user_profile = {
                "id": current_user.id if current_user.is_authenticated else None,
                "primary_crop": getattr(current_user, "primary_crop", None),
                "region": getattr(current_user, "region", None),
                "preferred_language": getattr(current_user, "preferred_language", "en"),
            }
            reply = process_message(user_profile, message)
            reply = sanitize_output(reply)

        # 💾 Save to chat history
        try:
            ch = ChatHistory(
                user_id=current_user.id if current_user.is_authenticated else None,
                user_message=message or "Image uploaded",
                bot_response=reply,
            )
            db.session.add(ch)
            db.session.commit()
        except Exception as db_error:
            print(f"Database error (non-critical): {db_error}")
            # Continue even if DB save fails

        return jsonify({"response": reply})

    except Exception as e:
        print(f"Unexpected error in /api/chat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response": "⚠️ An unexpected error occurred. Please try again."}), 500
# --------------------------
# Image Analysis (direct upload)
# --------------------------
# ALLOWED_EXT = {"png", "jpg", "jpeg"}

# def allowed_file(filename):
#     return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# @app.route("/api/image-analyze", methods=["POST"])
# def image_analyze():
#     file = request.files.get("image")
#     if not file or not allowed_file(file.filename):
#         return jsonify({"error": "invalid_image"}), 400

#     filename = secure_filename(file.filename)
#     save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
#     file.save(save_path)

#     im = Image.open(save_path).convert("RGB").resize((200, 200))
#     pixels = list(im.getdata())
#     greens = sum(1 for r, g, b in pixels if g > r + 10 and g > b + 10)
#     healthy_ratio = greens / len(pixels)

#     if healthy_ratio < 0.05:
#         label = "Severe discoloration / possible disease"
#         advice = "Image shows low green content. Inspect plants closely."
#     elif healthy_ratio < 0.4:
#         label = "Partial damage / early symptoms"
#         advice = "Signs of stress. Check for pests or nutrient deficiency."
#     else:
#         label = "Likely healthy leaf"
#         advice = "Leaf appears healthy and vibrant."

#     return jsonify({"label": label, "advice": advice})


# --------------------------
# Admin Routes
# --------------------------
@app.route("/admin")
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        flash("Access denied", "danger")
        return redirect(url_for("index"))
    users = User.query.order_by(User.id.desc()).all()
    chats = ChatHistory.query.order_by(ChatHistory.created_at.desc()).limit(500).all()
    kb_content = ""
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            kb_content = f.read()
    except Exception:
        kb_content = "[]"
    return render_template("admin_dashboard.html", users=users, chats=chats, kb_content=kb_content)


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# --------------------------
# Run App
# --------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
