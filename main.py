import json
import re
from datetime import datetime
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

import typer
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

import env
from database.config import SessionLocal
from database.models import GoogleAccount, TransferJob, User

app = typer.Typer(help="Google Drive local OAuth tools.")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive",
]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_WORKSPACE_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}


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


def get_local_credentials(port: int) -> Credentials:
    """Open browser locally and return newly authorized Google credentials."""
    flow = InstalledAppFlow.from_client_config(
        load_google_client_config(),
        SCOPES,
    )
    return flow.run_local_server(
        port=port,
        access_type="offline",
        prompt="consent",
    )


def refresh_credentials_from_database(
    db: Session,
    gmail_address: str,
) -> Credentials:
    credentials = credentials_from_database(db, gmail_address)
    if credentials is None:
        raise ValueError(f"No saved Google account found for {gmail_address}.")

    if not credentials.refresh_token:
        raise ValueError(
            f"Saved Google account for {gmail_address} has no refresh_token."
        )

    credentials.refresh(Request())
    return credentials


def get_refreshed_credentials(db: Session, gmail_address: str) -> Credentials:
    credentials = refresh_credentials_from_database(db, gmail_address)
    token_data = json.loads(credentials.to_json())
    upsert_google_account(db, gmail_address, token_data)
    return credentials


def build_drive_service(credentials: Credentials):
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def get_hanoi_time(format_str: str = "%d-%m-%Y %H-%M-%S") -> str:
    now_hanoi = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return now_hanoi.strftime(format_str)


def extract_drive_folder_id(folder_url_or_id: str) -> str:
    folder_value = folder_url_or_id.strip()
    folder_match = re.search(r"/folders/([a-zA-Z0-9_-]+)", folder_value)
    if folder_match:
        return folder_match.group(1)

    id_match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", folder_value)
    if id_match:
        return id_match.group(1)

    if re.fullmatch(r"[a-zA-Z0-9_-]+", folder_value):
        return folder_value

    raise typer.BadParameter("Invalid Google Drive folder URL or ID.")


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


def create_drive_folder(service, folder_name: str, parent_id: str | None = None) -> str:
    metadata: dict[str, Any] = {
        "name": folder_name,
        "mimeType": FOLDER_MIME_TYPE,
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_or_create_drive_folder(
    service,
    folder_name: str,
    parent_id: str | None = None,
) -> str:
    escaped_folder_name = escape_drive_query_value(folder_name)
    parent_query = (
        f" and '{parent_id}' in parents" if parent_id else " and 'root' in parents"
    )
    response = (
        service.files()
        .list(
            q=(
                f"name = '{escaped_folder_name}' "
                f"and mimeType = '{FOLDER_MIME_TYPE}' "
                f"and trashed = false{parent_query}"
            ),
            fields="files(id)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    folders = response.get("files", [])
    if folders:
        return folders[0]["id"]

    return create_drive_folder(service, folder_name, parent_id)


def create_destination_folder_tree(dest_service) -> str:
    contents_id = find_or_create_drive_folder(dest_service, "contents")
    project_id = find_or_create_drive_folder(
        dest_service,
        "auto-upload-google-drive",
        contents_id,
    )
    return create_drive_folder(dest_service, get_hanoi_time(), project_id)


def list_folder_children(source_service, folder_id: str) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    page_token = None

    while True:
        response = (
            source_service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        children.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return children


def download_file(source_service, file_id: str, mime_type: str) -> BytesIO:
    file_buffer = BytesIO()
    if mime_type in GOOGLE_WORKSPACE_EXPORTS:
        export_mime_type, _ = GOOGLE_WORKSPACE_EXPORTS[mime_type]
        request = source_service.files().export_media(
            fileId=file_id,
            mimeType=export_mime_type,
        )
    else:
        request = source_service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(file_buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    file_buffer.seek(0)
    return file_buffer


def upload_file(
    dest_service,
    file_name: str,
    parent_id: str,
    source_mime_type: str,
    file_buffer: BytesIO,
) -> str:
    upload_mime_type = source_mime_type
    if source_mime_type in GOOGLE_WORKSPACE_EXPORTS:
        upload_mime_type, extension = GOOGLE_WORKSPACE_EXPORTS[source_mime_type]
        if not file_name.endswith(extension):
            file_name = f"{file_name}{extension}"

    metadata = {"name": file_name, "parents": [parent_id]}
    media = MediaIoBaseUpload(file_buffer, mimetype=upload_mime_type, resumable=True)
    uploaded_file = (
        dest_service.files()
        .create(body=metadata, media_body=media, fields="id")
        .execute()
    )
    return uploaded_file["id"]


def trash_source_item(source_service, item_id: str) -> None:
    source_service.files().update(
        fileId=item_id,
        body={"trashed": True},
        supportsAllDrives=True,
    ).execute()


def copy_item_then_delete_source(
    source_service,
    dest_service,
    item: dict[str, Any],
    dest_parent_id: str,
) -> None:
    item_id = item["id"]
    item_name = item["name"]
    item_mime_type = item["mimeType"]

    if item_mime_type == FOLDER_MIME_TYPE:
        new_folder_id = create_drive_folder(dest_service, item_name, dest_parent_id)
        copy_folder_contents_then_delete_source(
            source_service,
            dest_service,
            item_id,
            new_folder_id,
        )
        trash_source_item(source_service, item_id)
        logger.info(f"Moved folder: {item_name}")
        return

    file_buffer = download_file(source_service, item_id, item_mime_type)
    upload_file(dest_service, item_name, dest_parent_id, item_mime_type, file_buffer)
    trash_source_item(source_service, item_id)
    logger.info(f"Moved file: {item_name}")


def copy_folder_contents_then_delete_source(
    source_service,
    dest_service,
    source_folder_id: str,
    dest_folder_id: str,
) -> None:
    for child in list_folder_children(source_service, source_folder_id):
        copy_item_then_delete_source(
            source_service, dest_service, child, dest_folder_id
        )


@app.command("local-auth")
def local_auth(
    port: int = typer.Option(
        0,
        help="Local callback port. Use 0 to choose a free port automatically.",
    ),
) -> None:
    """Open the browser on this computer, authorize Google, and save token to DB."""
    credentials = get_local_credentials(port)
    authenticated_gmail_address = get_google_email(credentials)
    token_data = json.loads(credentials.to_json())

    db = SessionLocal()
    try:
        upsert_google_account(db, authenticated_gmail_address, token_data)
    finally:
        db.close()

    typer.echo(f"Saved Google account to database: {authenticated_gmail_address}")


@app.command("refresh")
def refresh(
    gmail_address: str = typer.Option(
        "",
        help="Gmail address to refresh. Defaults to GOOGLE_REFRESH_GMAIL.",
    ),
) -> None:
    """Refresh a saved Google token from the database and write it back."""
    target_gmail_address = gmail_address or env.GOOGLE_REFRESH_GMAIL
    if not target_gmail_address:
        raise typer.BadParameter("Provide --gmail-address or set GOOGLE_REFRESH_GMAIL.")

    db = SessionLocal()
    try:
        credentials = refresh_credentials_from_database(db, target_gmail_address)
        authenticated_gmail_address = get_google_email(credentials)
        token_data = json.loads(credentials.to_json())
        upsert_google_account(db, authenticated_gmail_address, token_data)
    finally:
        db.close()

    typer.echo(f"Refreshed Google account in database: {authenticated_gmail_address}")


@app.command("transfer")
def transfer(
    source_gmail: str = typer.Option(
        ...,
        help="Gmail account that owns the source folder.",
    ),
    source_folder: str = typer.Option(
        ...,
        help="Source Google Drive folder URL or ID.",
    ),
    dest_gmail: str = typer.Option(
        ...,
        help="Gmail account that receives the copied files.",
    ),
) -> None:
    """Move all contents from a source Drive folder to a timestamped destination folder."""
    source_folder_id = extract_drive_folder_id(source_folder)

    db = SessionLocal()
    transfer_job: TransferJob | None = None
    try:
        source_credentials = get_refreshed_credentials(db, source_gmail)
        dest_credentials = get_refreshed_credentials(db, dest_gmail)

        transfer_job = create_transfer_job(
            db,
            source_gmail,
            source_folder_id,
            dest_gmail,
        )

        source_service = build_drive_service(source_credentials)
        dest_service = build_drive_service(dest_credentials)
        dest_folder_id = create_destination_folder_tree(dest_service)

        copy_folder_contents_then_delete_source(
            source_service,
            dest_service,
            source_folder_id,
            dest_folder_id,
        )
        complete_transfer_job(db, transfer_job)
    except Exception as error:
        if transfer_job is not None:
            fail_transfer_job(db, transfer_job, error)
        raise
    finally:
        db.close()

    typer.echo(
        f"Transferred source folder contents to destination folder: {dest_folder_id}"
    )


def main() -> None:
    logger.info("Google local OAuth CLI started")
    app()


if __name__ == "__main__":
    main()
