from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import GoogleAccount, TransferJob, User


def get_saved_google_account(db: Session, gmail_address: str) -> GoogleAccount | None:
    return db.scalar(
        select(GoogleAccount).join(User).where(User.email == gmail_address)
    )


def get_active_google_accounts(db: Session) -> list[GoogleAccount]:
    return list(db.scalars(select(GoogleAccount).where(GoogleAccount.is_active)))


def upsert_google_account(
    db: Session,
    gmail_address: str,
    token_data: dict[str, Any],
) -> None:
    user = db.scalar(select(User).where(User.email == gmail_address))
    if user is None:
        user = User(email=gmail_address)
        db.add(user)
        db.flush()

    google_account = db.scalar(
        select(GoogleAccount).where(
            GoogleAccount.userId == user.userId,
            GoogleAccount.gmail_address == gmail_address,
        )
    )

    if google_account is None:
        google_account = GoogleAccount(
            userId=user.userId,
            gmail_address=gmail_address,
            token_data=token_data,
            is_active=True,
        )
        db.add(google_account)
    else:
        google_account.token_data = token_data
        google_account.is_active = True

    db.commit()


def create_transfer_job(
    db: Session,
    source_gmail: str,
    source_folder_id: str,
    dest_gmail: str,
) -> TransferJob:
    transfer_job = TransferJob(
        source_gmail=source_gmail,
        source_folder_id=source_folder_id,
        dest_gmail=dest_gmail,
        status="running",
    )
    db.add(transfer_job)
    db.commit()
    db.refresh(transfer_job)
    return transfer_job


def complete_transfer_job(db: Session, transfer_job: TransferJob) -> None:
    transfer_job.status = "completed"
    transfer_job.completed_at = datetime.now()
    db.commit()


def fail_transfer_job(db: Session, transfer_job: TransferJob, error: Exception) -> None:
    transfer_job.status = "failed"
    transfer_job.error_message = str(error)
    transfer_job.completed_at = datetime.now()
    db.commit()
