from io import BytesIO
from typing import Any

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from loguru import logger

from utils.time import get_hanoi_time

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
            source_service,
            dest_service,
            child,
            dest_folder_id,
        )
