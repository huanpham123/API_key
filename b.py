import secrets
import hashlib
import psycopg2
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect, url_for, session
)
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

import g4f

# --- Cấu hình ---
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Secret key cố định khi deploy

# URL kết nối DB cố định (Neon / Supabase / PostgreSQL ngoài)
DATABASE_URL = "postgres://neondb_owner:npg_9vVoOENbyM7R@ep-summer-shape-a1w0h1ig-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

# Mật khẩu admin cố định
SITE_PASSWORD = "admin123@@"
SITE_PASSWORD_HASH = generate_password_hash(SITE_PASSWORD)

# Cho phép CORS cho API
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- Database ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except psycopg2.OperationalError as e:
        print(f"❌ Lỗi kết nối DB: {e}")
        return None

def init_db():
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS api_keys (
                        id SERIAL PRIMARY KEY,
                        key_hash TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
            conn.commit()
            conn.close()
            print("✅ DB đã sẵn sàng")
    except Exception as e:
        print(f"❌ Lỗi khi khởi tạo DB: {e}")

def store_key_hash(key_hash: str):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO api_keys (key_hash) VALUES (%s) ON CONFLICT (key_hash) DO NOTHING",
                    (key_hash,)
                )
            conn.commit()
        finally:
            conn.close()

def key_exists_hash(key_hash: str) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM api_keys WHERE key_hash = %s)", (key_hash,))
        found = cur.fetchone()[0]
    conn.close()
    return found

# --- Helpers ---
def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if check_password_hash(SITE_PASSWORD_HASH, password):
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Sai mật khẩu"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# Lấy danh sách model
def get_available_models():
    models = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
        "gemini-1.5-pro-latest", "gemini-1.5-flash-latest",
        "claude-3-opus-20240229", "claude-3-sonnet-20240229",
        "llama3-70b-8192", "llama3-8b-8192"
    }
    try:
        g4f_models = g4f.models._all_models
        models.update(g4f_models)
    except Exception as e:
        print(f"⚠️ Không lấy được model từ g4f: {e}")
    return sorted([m for m in models if isinstance(m, str)])

@app.route('/api/models', methods=['GET'])
def api_models():
    try:
        return jsonify({'models': get_available_models()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create_key', methods=['POST'])
@login_required
def api_create_key():
    raw_key = f"g4f-{secrets.token_urlsafe(32)}"
    store_key_hash(hash_key(raw_key))
    return jsonify({'api_key': raw_key})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json(force=True)
    api_key = data.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
    model = data.get('model')
    messages = data.get('messages')

    if not api_key or not model or not messages:
        return jsonify({'error': 'Thiếu api_key, model hoặc messages'}), 400

    if not key_exists_hash(hash_key(api_key)):
        return jsonify({'error': 'API key không hợp lệ'}), 403

    try:
        response = g4f.ChatCompletion.create(model=model, messages=messages)
        return jsonify({
            "id": f"chatcmpl-{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        })
    except Exception as e:
        return jsonify({'error': f'Lỗi từ g4f: {str(e)}'}), 500

# Khởi tạo DB khi chạy
init_db()

if __name__ == '__main__':
    app.run()
