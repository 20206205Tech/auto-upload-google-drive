import json

from sqlalchemy.orm import Session

from database.models import TransferJob
from utils.auth import (
    build_drive_service,
    credentials_from_google_account,
    get_google_email,
    refresh_credentials,
)
from utils.database import (
    complete_transfer_job,
    create_transfer_job,
    fail_transfer_job,
    get_saved_google_account,
    upsert_google_account,
)
from utils.drive import (
    copy_folder_contents_then_delete_source,
    create_destination_folder_tree,
)
from utils.parsing import extract_drive_folder_id


def get_refreshed_credentials(db: Session, gmail_address: str):
    google_account = get_saved_google_account(db, gmail_address)
    if google_account is None:
        raise ValueError(f"No saved Google account found for {gmail_address}.")

    credentials = credentials_from_google_account(google_account)
    credentials = refresh_credentials(credentials, gmail_address)
    token_data = json.loads(credentials.to_json())
    upsert_google_account(db, gmail_address, token_data)
    return credentials


def transfer_folder_contents(
    db: Session,
    source_gmail: str,
    source_folder: str,
    dest_gmail: str,
) -> str:
    source_folder_id = extract_drive_folder_id(source_folder)
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

    return dest_folder_id


def refresh_all_google_accounts(db: Session, google_accounts) -> list[str]:
    refreshed_gmail_addresses: list[str] = []

    for google_account in google_accounts:
        credentials = credentials_from_google_account(google_account)
        credentials = refresh_credentials(credentials, google_account.gmail_address)
        authenticated_gmail_address = get_google_email(credentials)
        token_data = json.loads(credentials.to_json())
        upsert_google_account(db, authenticated_gmail_address, token_data)
        refreshed_gmail_addresses.append(authenticated_gmail_address)

    return refreshed_gmail_addresses
