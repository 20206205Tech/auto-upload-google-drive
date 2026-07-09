import json
from typing import Any

import typer
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

import env
from database.config import SessionLocal
from database.models import GoogleAccount, User

app = typer.Typer(help="Google Drive local OAuth tools.")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive",
]


@app.callback()
def callback() -> None:
    """Google Drive local OAuth tools."""


def load_google_client_config() -> dict[str, Any]:
    """Load Google OAuth client JSON from GOOGLE_CREDENTIALS."""
    raw_credentials = env.GOOGLE_CREDENTIALS.strip()

    if not raw_credentials:
        raise ValueError("Missing GOOGLE_CREDENTIALS environment variable.")

    return json.loads(raw_credentials)


def get_saved_google_account(db: Session, gmail_address: str) -> GoogleAccount | None:
    return db.scalar(
        select(GoogleAccount).join(User).where(User.email == gmail_address)
    )


def credentials_from_database(
    db: Session,
    gmail_address: str,
) -> Credentials | None:
    google_account = get_saved_google_account(db, gmail_address)
    if google_account is None:
        return None

    return Credentials.from_authorized_user_info(google_account.token_data, SCOPES)


def get_local_credentials(
    db: Session,
    gmail_address: str | None,
    port: int,
) -> Credentials:
    """Open browser locally only when no usable token exists in the database."""
    credentials = (
        credentials_from_database(db, gmail_address) if gmail_address else None
    )
    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_config(
            load_google_client_config(),
            SCOPES,
        )
        credentials = flow.run_local_server(
            port=port,
            access_type="offline",
            prompt="consent",
        )

    return credentials


def get_google_email(credentials: Credentials) -> str:
    session = AuthorizedSession(credentials)
    response = session.get("https://www.googleapis.com/oauth2/v2/userinfo", timeout=30)
    response.raise_for_status()

    email = response.json().get("email")
    if not email:
        raise RuntimeError("Google did not return an email for this account.")

    return email


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


@app.command("local-auth")
def local_auth(
    gmail_address: str
    | None = typer.Option(
        None,
        help="Existing Gmail address to refresh from database before opening browser.",
    ),
    port: int = typer.Option(
        0,
        help="Local callback port. Use 0 to choose a free port automatically.",
    ),
) -> None:
    """Open the browser on this computer, authorize Google, and save token to DB."""
    db = SessionLocal()
    try:
        credentials = get_local_credentials(db, gmail_address, port)
        authenticated_gmail_address = get_google_email(credentials)
        token_data = json.loads(credentials.to_json())
        upsert_google_account(db, authenticated_gmail_address, token_data)
    finally:
        db.close()

    typer.echo(f"Saved Google account to database: {authenticated_gmail_address}")


def main() -> None:
    logger.info("Google local OAuth CLI started")
    app()


if __name__ == "__main__":
    main()
