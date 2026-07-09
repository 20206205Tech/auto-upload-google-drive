import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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


def build_flow(
    code_verifier: str | None = None,
    autogenerate_code_verifier: bool = False,
) -> Flow:
    flow = Flow.from_client_config(
        load_google_client_config(),
        scopes=SCOPES,
        code_verifier=code_verifier,
        autogenerate_code_verifier=autogenerate_code_verifier,
    )
    flow.redirect_uri = REDIRECT_URI
    return flow


def extract_code(code_or_url: str) -> str:
    if code_or_url.startswith("http://") or code_or_url.startswith("https://"):
        parsed_url = urlparse(code_or_url)
        query_values = parse_qs(parsed_url.query)
        code_values = query_values.get("code")
        if code_values:
            return code_values[0]

    return code_or_url


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
    flow = build_flow(autogenerate_code_verifier=True)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    typer.echo("Open this URL in your browser:")
    typer.echo(authorization_url)
    typer.echo("")
    typer.echo("Save this CODE_VERIFIER for the save-google-account step:")
    typer.echo(flow.code_verifier)
    typer.echo("")
    typer.echo(
        "After approving, copy the full redirect URL or the code=... value from it."
    )


@app.command("save-google-account")
def save_google_account(
    code: str = typer.Option(
        ..., help="The full redirect URL or code value copied from Google."
    ),
    code_verifier: str = typer.Option(
        ...,
        help="The CODE_VERIFIER printed by the auth-url command.",
    ),
) -> None:
    """Exchange a Google OAuth code for tokens and save them to the database."""
    flow = build_flow(code_verifier=code_verifier)
    flow.fetch_token(code=extract_code(code))

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
