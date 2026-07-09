import json

import typer
from loguru import logger

from database.config import SessionLocal
from utils.auth import get_google_email, get_local_credentials
from utils.database import get_active_google_accounts, upsert_google_account
from utils.transfer import refresh_all_google_accounts, transfer_folder_contents

app = typer.Typer(help="Google Drive local OAuth tools.")


@app.callback()
def callback() -> None:
    """Google Drive local OAuth tools."""


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
def refresh() -> None:
    """Refresh all active saved Google tokens from the database."""
    db = SessionLocal()
    try:
        google_accounts = get_active_google_accounts(db)
        if not google_accounts:
            typer.echo("No active Google accounts found to refresh.")
            return

        refreshed_gmail_addresses = refresh_all_google_accounts(db, google_accounts)
    finally:
        db.close()

    typer.echo(
        "Refreshed Google accounts in database: " + ", ".join(refreshed_gmail_addresses)
    )


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
    dest_folder_id = transfer_folder_contents(
        source_gmail,
        source_folder,
        dest_gmail,
    )

    typer.echo(
        f"Transferred source folder contents to destination folder: {dest_folder_id}"
    )


def main() -> None:
    logger.info("Google Drive CLI started")
    app()


if __name__ == "__main__":
    main()
