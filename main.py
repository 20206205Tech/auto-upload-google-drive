import json
from pathlib import Path
from typing import Any

import typer
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

import env
from database.config import SessionLocal
from database.models import GoogleAccount, User

app = typer.Typer(help="Google Drive OAuth tools.")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive",
]
REDIRECT_URI = "http://localhost:8080/"


def load_google_client_config() -> dict[str, Any]:
    """Load Google OAuth client JSON from env text or a file path."""
    raw_credentials = env.GOOGLE_CREDENTIALS.strip()

    if raw_credentials.startswith("{"):
        return json.loads(raw_credentials)

    credentials_path = Path(raw_credentials)
    if credentials_path.exists():
        return json.loads(credentials_path.read_text(encoding="utf-8"))

    raise typer.BadParameter(
        "GOOGLE_CREDENTIALS must be Google OAuth JSON content or a path to JSON file."
    )


def build_flow() -> Flow:
    flow = Flow.from_client_config(load_google_client_config(), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    return flow


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


@app.command("auth-url")
def auth_url() -> None:
    """Print the Google OAuth URL to authorize one Google account."""
    flow = build_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    typer.echo("Open this URL in your browser:")
    typer.echo(authorization_url)
    typer.echo("")
    typer.echo("After approving, copy the code=... value from the redirect URL.")


@app.command("save-google-account")
def save_google_account(
    code: str = typer.Option(
        ..., help="The code value copied from Google's redirect URL."
    ),
) -> None:
    """Exchange a Google OAuth code for tokens and save them to the database."""
    flow = build_flow()
    flow.fetch_token(code=code)

    credentials = flow.credentials
    gmail_address = get_google_email(credentials)
    token_data = json.loads(credentials.to_json())

    db = SessionLocal()
    try:
        upsert_google_account(db, gmail_address, token_data)
    finally:
        db.close()

    typer.echo(f"Saved Google account: {gmail_address}")


def main() -> None:
    logger.info("Google OAuth CLI started")
    app()


if __name__ == "__main__":
    main()
