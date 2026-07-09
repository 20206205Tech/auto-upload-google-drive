import json
from typing import Any

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import env
from database.models import GoogleAccount

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive",
]


def load_google_client_config() -> dict[str, Any]:
    raw_credentials = env.GOOGLE_CREDENTIALS.strip()
    if not raw_credentials:
        raise ValueError("Missing GOOGLE_CREDENTIALS environment variable.")

    return json.loads(raw_credentials)


def get_local_credentials(port: int) -> Credentials:
    flow = InstalledAppFlow.from_client_config(load_google_client_config(), SCOPES)
    return flow.run_local_server(
        port=port,
        access_type="offline",
        prompt="consent",
    )


def credentials_from_google_account(
    google_account: GoogleAccount,
) -> Credentials:
    return Credentials.from_authorized_user_info(google_account.token_data, SCOPES)


def refresh_credentials(
    credentials: Credentials,
    gmail_address: str,
) -> Credentials:
    if not credentials.refresh_token:
        raise ValueError(
            f"Saved Google account for {gmail_address} has no refresh_token."
        )

    credentials.refresh(Request())
    return credentials


def get_google_email(credentials: Credentials) -> str:
    session = AuthorizedSession(credentials)
    response = session.get("https://www.googleapis.com/oauth2/v2/userinfo", timeout=30)
    response.raise_for_status()

    email = response.json().get("email")
    if not email:
        raise RuntimeError("Google did not return an email for this account.")

    return email


def build_drive_service(credentials: Credentials):
    return build("drive", "v3", credentials=credentials, cache_discovery=False)
