from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import env

engine = create_engine(
    env.DATABASE_URL,
    pool_pre_ping=True,  # QUAN TRỌNG: Kiểm tra connection (SELECT 1) trước khi dùng
    pool_recycle=1800,  # Chủ động thay mới connection sau mỗi 30 phút (1800 giây)
    pool_timeout=30,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
