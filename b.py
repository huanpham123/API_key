import os
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
app.secret_key = os.environ.get('FLASK_SECRET', secrets.token_hex(16))

# Lấy URL kết nối database từ biến môi trường
DATABASE_URL = os.environ.get('POSTGRES_URL')

# Thiết lập mật khẩu admin
SITE_PASSWORD = os.environ.get('SITE_PASSWORD', 'admin123@@')
SITE_PASSWORD_HASH = os.environ.get('SITE_PASSWORD_HASH')
if not SITE_PASSWORD_HASH:
    SITE_PASSWORD_HASH = generate_password_hash(SITE_PASSWORD)

# Cho phép CORS cho các API endpoint
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- Tiện ích Database (PostgreSQL) ---

def get_db_connection():
    """Tạo kết nối đến database PostgreSQL."""
    if not DATABASE_URL:
        raise ValueError("Biến môi trường POSTGRES_URL chưa được thiết lập.")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Lỗi kết nối database: {e}")
        return None

def init_db():
    """Hàm khởi tạo bảng trong DB, chạy một lần duy nhất."""
    print("Đang khởi tạo database...")
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_keys (
                        id SERIAL PRIMARY KEY,
                        key_hash TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()
            conn.close()
            print("✅ Khởi tạo database thành công.")
    except Exception as e:
        print(f"❌ Lỗi khi khởi tạo database: {e}")

def store_key_hash(key_hash: str):
    """Lưu hash của API key vào database."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO api_keys (key_hash) VALUES (%s)",
                    (key_hash,),
                )
            conn.commit()
        except psycopg2.IntegrityError:
            # Key đã tồn tại, bỏ qua
            pass
        finally:
            conn.close()

def key_exists_hash(key_hash: str) -> bool:
    """Kiểm tra xem hash của key đã tồn tại trong DB chưa."""
    conn = get_db_connection()
    found = False
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS(SELECT 1 FROM api_keys WHERE key_hash = %s)", (key_hash,))
                found = cur.fetchone()[0]
        finally:
            conn.close()
    return found

# --- Helpers ---

def hash_key(key: str) -> str:
    """Hash một chuỗi key bằng SHA256."""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

def login_required(f):
    """Decorator yêu cầu đăng nhập."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes: Giao diện web ---

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
            error = 'Mật khẩu không chính xác. Vui lòng thử lại.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# --- Helpers cho models ---

def get_available_models():
    """Lấy danh sách các model có sẵn từ g4f và một danh sách dự phòng."""
    models = set()
    # Danh sách dự phòng các model phổ biến
    fallback_models = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
        "gemini-1.5-pro-latest", "gemini-1.5-flash-latest",
        "claude-3-opus-20240229", "claude-3-sonnet-20240229",
        "llama3-70b-8192", "llama3-8b-8192"
    }
    models.update(fallback_models)
    
    # Cố gắng lấy danh sách model động từ thư viện
    try:
        g4f_models = g4f.models._all_models
        models.update(g4f_models)
    except Exception as e:
        print(f"⚠️ Không thể lấy danh sách model động từ g4f: {e}")
    
    # Lọc bỏ những thứ không phải chuỗi và sắp xếp
    return sorted([m for m in models if isinstance(m, str)])

# --- API Endpoints ---

@app.route('/api/models', methods=['GET'])
def api_models():
    """Trả về danh sách các model có sẵn."""
    try:
        models = get_available_models()
        return jsonify({'models': models})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create_key', methods=['POST'])
@login_required
def api_create_key():
    """Tạo API key mới, lưu hash và trả về key gốc một lần duy nhất."""
    raw_key = f"g4f-{secrets.token_urlsafe(32)}"
    key_hash = hash_key(raw_key)
    try:
        store_key_hash(key_hash)
        return jsonify({'api_key': raw_key})
    except Exception as e:
        return jsonify({'error': f'Không thể lưu key: {str(e)}'}), 500

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Endpoint chính để xử lý yêu cầu chat, proxy đến g4f."""
    data = request.get_json(force=True)
    api_key = data.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
    model = data.get('model')
    messages = data.get('messages')

    if not api_key or not model or not messages:
        return jsonify({'error': 'Thiếu các trường bắt buộc (api_key, model, messages)'}), 400

    if not key_exists_hash(hash_key(api_key)):
        return jsonify({'error': 'API key không hợp lệ'}), 403

    try:
        response = g4f.ChatCompletion.create(
            model=model,
            messages=messages,
        )
        # Chuẩn hóa response theo format OpenAI
        chat_response = {
            "id": f"chatcmpl-{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response,
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        return jsonify(chat_response)
    except Exception as e:
        return jsonify({'error': f'Lỗi từ g4f: {str(e)}'}), 500

# Khởi tạo database khi ứng dụng bắt đầu
init_db()

if __name__ == '__main__':
    app.run(debug=True)
