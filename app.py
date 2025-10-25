import os, json, time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from database import init_db, db, User, ChatHistory
from chatbot_model import process_message, load_kb, KB_PATH
from utils.safety import contains_blocked, sanitize_output
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file,session
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_login import current_user, login_required
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from database import db, User, ChatHistory


UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "super_secret_key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# init DB & default admin
init_db(app)

# login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
@app.route("/")
def index():
    recent_users = []
    if current_user.is_authenticated and current_user.role == "admin":
        recent_users = User.query.order_by(User.id.desc()).limit(20).all()
    return render_template("index.html", recent_users=recent_users)

# Register / Login / Logout / Profile
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "warning"); return redirect(url_for("register"))
        user = User(
            email=email,
            password=generate_password_hash(request.form["password"]),
            name=request.form.get("name",""),
            primary_crop=request.form.get("primary_crop",""),
            region=request.form.get("region",""),
            preferred_language=request.form.get("preferred_language","en")
        )
        db.session.add(user); db.session.commit()
        flash("Registration successful — please log in", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
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

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name","")
        current_user.primary_crop = request.form.get("primary_crop","")
        current_user.region = request.form.get("region","")
        current_user.preferred_language = request.form.get("preferred_language","en")
        db.session.commit()
        flash("Profile updated", "success")
    return render_template("profile.html")

# Chat API
@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json() or {}
        message = (data.get("message") or "").strip()
        image_data = data.get("image")  # optional base64 or filename from frontend

        if not message and not image_data:
            return jsonify({"response":"Please type a question or upload an image."})

        # If image is provided, process it first
        if image_data:
            # save and analyze image (simplified)
            from PIL import Image
            import base64, io
            header, encoded = image_data.split(",",1) if "," in image_data else ("","")
            file_bytes = io.BytesIO(base64.b64decode(encoded))
            im = Image.open(file_bytes).convert('RGB').resize((200,200))
            pixels = list(im.getdata())
            greens = sum(1 for r,g,b in pixels if g>r+10 and g>b+10)
            total=len(pixels)
            healthy_ratio = greens/total
            if healthy_ratio < 0.05:
                reply = "Severe discoloration / possible disease. Inspect plants."
            elif healthy_ratio < 0.4:
                reply = "Partial damage / early symptoms. Check for pests."
            else:
                reply = "Likely healthy leaf."
        else:
            # text-based chat
            if contains_blocked(message):
                return jsonify({"response":"Sorry, message contains prohibited content."}), 400
            user_profile = {
                "id": current_user.id if current_user.is_authenticated else None,
                "primary_crop": current_user.primary_crop if current_user.is_authenticated else None,
                "region": current_user.region if current_user.is_authenticated else None,
                "preferred_language": current_user.preferred_language if current_user.is_authenticated else None
            }
            reply = process_message(user_profile, message)
            reply = sanitize_output(reply)

        # Save chat history
        ch = ChatHistory(
            user_id=current_user.id if current_user.is_authenticated else None,
            user_message=message or "Image uploaded",
            bot_response=reply
        )
        db.session.add(ch); db.session.commit()
        return jsonify({"response": reply})

    except Exception as e:
        print("Error /api/chat:", e)
        return jsonify({"response":"Internal server error"}), 500


# Admin
@app.route("/admin")
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        flash("Access denied", "danger"); return redirect(url_for("index"))
    users = User.query.order_by(User.id.desc()).all()
    chats = ChatHistory.query.order_by(ChatHistory.created_at.desc()).limit(500).all()
    kb_content = ""
    try:
        with open(KB_PATH,"r",encoding="utf-8") as f: kb_content = f.read()
    except Exception:
        kb_content = "[]"
    return render_template("admin_dashboard.html", users=users, chats=chats, kb_content=kb_content)

@app.route("/admin/edit_kb", methods=["POST"])
@login_required
def admin_edit_kb():
    if current_user.role != "admin":
        return jsonify({"ok":False,"error":"unauthorized"}),403
    data = request.form.get("kb_data","")
    try:
        parsed = json.loads(data)
        with open(KB_PATH,"w",encoding="utf-8") as f: json.dump(parsed,f,ensure_ascii=False,indent=2)
        flash("KB updated", "success")
    except Exception as e:
        flash("Invalid JSON: "+str(e),"danger")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/upload_kb_csv", methods=["POST"])
@login_required
def admin_upload_kb_csv():
    if current_user.role != "admin": return jsonify({"ok":False,"error":"unauthorized"}),403
    f = request.files.get("csv_file")
    if not f: flash("No file uploaded","warning"); return redirect(url_for("admin_dashboard"))
    filename = secure_filename(f.filename); path = os.path.join(app.config['UPLOAD_FOLDER'], filename); f.save(path)
    # minimal CSV parse (keywords,answer_en,answer_hi,answer_ta)
    import csv
    rows = []
    try:
        with open(path,newline='',encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for r in reader:
                keys = [k.strip() for k in (r.get('keywords') or "").split(',') if k.strip()]
                rows.append({"keywords": keys, "answer_en": r.get('answer_en') or "", "answer_hi": r.get('answer_hi') or "", "answer_ta": r.get('answer_ta') or ""})
        # merge into KB
        try:
            with open(KB_PATH,"r",encoding='utf-8') as f: existing = json.load(f)
            if not isinstance(existing,list): existing=[]
        except Exception:
            existing=[]
        existing.extend(rows)
        with open(KB_PATH,"w",encoding='utf-8') as f: json.dump(existing,f,ensure_ascii=False,indent=2)
        flash(f"Imported {len(rows)} rows","success")
    except Exception as e:
        flash("CSV parse error: "+str(e),"danger")
    return redirect(url_for("admin_dashboard"))

# Image analyze endpoint (simple local heuristic)
ALLOWED_EXT = {'png','jpg','jpeg'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT
@app.route("/admin/user/<int:user_id>")
def admin_view_user(user_id):
    if not session.get("admin"):
        return redirect(url_for("admin_dashboard"))
    user = User.query.get_or_404(user_id)
    chats = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.created_at.desc()).all()
    return render_template("admin_view_user.html", user=user, chats=chats)

@app.route("/api/image-analyze", methods=["POST"])
def image_analyze():
    file = request.files.get("image")
    if not file or not allowed_file(file.filename):
        return jsonify({"error":"invalid_image"}), 400
    filename = secure_filename(file.filename); save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename); file.save(save_path)
    try:
        from PIL import Image
        im = Image.open(save_path).convert('RGB').resize((200,200))
        pixels = list(im.getdata())
        greens = sum(1 for r,g,b in pixels if g>r+10 and g>b+10); total=len(pixels)
        healthy_ratio = greens/total
        if healthy_ratio < 0.05:
            label="Severe discoloration / possible disease"; advice="Image shows low green content. Inspect plants."
        elif healthy_ratio < 0.4:
            label="Partial damage / early symptoms"; advice="Signs of stress. Check for pests."
        else:
            label="Likely healthy leaf"; advice="Leaf appears healthy."
        return jsonify({"label":label,"advice":advice})
    except Exception as e:
        print("Image analyze error:",e)
        return jsonify({"label":"image_received","advice":"Install Pillow for local analysis."})

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if current_user.role != "admin":
        flash("Access denied!", "danger")
        return redirect(url_for("index"))

    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        flash("You cannot delete another admin.", "warning")
        return redirect(url_for("admin_dashboard"))

    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/clear_chats", methods=["POST"])
@login_required
def admin_clear_chats():
    if current_user.role != "admin":
        flash("Access denied!", "danger")
        return redirect(url_for("index"))

    ChatHistory.query.delete()
    db.session.commit()
    flash("✅ All chat history cleared successfully!", "success")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
