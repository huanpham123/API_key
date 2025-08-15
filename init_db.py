import os
import psycopg2
from dotenv import load_dotenv

# Tải các biến môi trường từ file .env (nếu có, dùng cho local dev)
load_dotenv()

def init_db():
    """Khởi tạo bảng trong database PostgreSQL."""
    db_url = os.environ.get('POSTGRES_URL')
    if not db_url:
        print("Lỗi: Biến môi trường POSTGRES_URL chưa được thiết lập.")
        return
        
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        print("Đã kết nối tới PostgreSQL...")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        print("Câu lệnh CREATE TABLE đã được thực thi.")
        
        conn.commit()
        cur.close()
        print("Database đã được khởi tạo thành công!")

    except psycopg2.Error as e:
        print(f"Lỗi database: {e}")
    finally:
        if conn is not None:
            conn.close()
            print("Đã đóng kết nối database.")

if __name__ == "__main__":
    init_db()