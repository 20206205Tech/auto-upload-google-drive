import datetime
import uuid

from sqlalchemy import (
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    userId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    google_accounts: Mapped[list["GoogleAccount"]] = relationship(back_populates="user")


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    # Ràng buộc Unique Composite
    __table_args__ = (
        UniqueConstraint("userId", "gmail_address", name="uq_user_gmail"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    userId: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.userId"), nullable=False
    )
    gmail_address: Mapped[str] = mapped_column(String, nullable=False)

    # Sử dụng JSONB của PostgreSQL
    token_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="Lưu nội dung token.json (Nên được mã hóa)"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="google_accounts")


class TransferJob(Base):
    __tablename__ = "transfer_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Tham chiếu trực tiếp đến cột email của bảng users như thiết kế DBML
    source_gmail: Mapped[str] = mapped_column(ForeignKey("users.email"), nullable=False)
    source_folder_id: Mapped[str] = mapped_column(String, nullable=False)
    dest_gmail: Mapped[str] = mapped_column(ForeignKey("users.email"), nullable=False)

    status: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Relationships (Tuỳ chọn: Hỗ trợ query ngược từ TransferJob ra User)
    source_user: Mapped["User"] = relationship("User", foreign_keys=[source_gmail])
    dest_user: Mapped["User"] = relationship("User", foreign_keys=[dest_gmail])
