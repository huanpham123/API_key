import os
import psycopg2

def init_db():
    """Khởi tạo bảng trong database PostgreSQL."""
    
    # Gán trực tiếp URL kết nối, không dùng biến môi trường
    # CẢNH BÁO: Không nên làm cách này trong môi trường production!
    db_url = "postgres://neondb_owner:npg_9vVoOENbyM7R@ep-summer-shape-a1w0h1ig-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    
    if not db_url:
        print("Lỗi: URL kết nối database chưa được thiết lập.")
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

