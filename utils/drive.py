from typing import Any

from googleapiclient.errors import HttpError
from loguru import logger

from utils.time import get_hanoi_time

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


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


def trash_source_item(source_service, item_id: str) -> None:
    source_service.files().update(
        fileId=item_id,
        body={"trashed": True},
        supportsAllDrives=True,
    ).execute()


def share_source_item_with_destination(
    source_service,
    item_id: str,
    dest_gmail: str,
) -> None:
    try:
        source_service.permissions().create(
            fileId=item_id,
            body={
                "type": "user",
                "role": "reader",
                "emailAddress": dest_gmail,
            },
            sendNotificationEmail=False,
            supportsAllDrives=True,
            fields="id",
        ).execute()
    except HttpError as error:
        if getattr(error, "resp", None) is not None and error.resp.status == 409:
            return
        raise


def copy_file_server_side(
    dest_service,
    source_file_id: str,
    file_name: str,
    dest_parent_id: str,
) -> str:
    copied_file = (
        dest_service.files()
        .copy(
            fileId=source_file_id,
            body={"name": file_name, "parents": [dest_parent_id]},
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return copied_file["id"]


def copy_item_then_delete_source(
    source_service,
    dest_service,
    item: dict[str, Any],
    dest_parent_id: str,
    dest_gmail: str,
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
            dest_gmail,
        )
        trash_source_item(source_service, item_id)
        logger.info(f"Moved folder: {item_name}")
        return

    share_source_item_with_destination(source_service, item_id, dest_gmail)
    copy_file_server_side(dest_service, item_id, item_name, dest_parent_id)
    trash_source_item(source_service, item_id)
    logger.info(f"Moved file: {item_name}")


def copy_folder_contents_then_delete_source(
    source_service,
    dest_service,
    source_folder_id: str,
    dest_folder_id: str,
    dest_gmail: str,
) -> None:
    children = list_folder_children(source_service, source_folder_id)
    logger.info(f"Found {len(children)} item(s) in source folder {source_folder_id}")

    for index, child in enumerate(children, start=1):
        logger.info(f"Moving {index}/{len(children)}: {child['name']}")
        copy_item_then_delete_source(
            source_service,
            dest_service,
            child,
            dest_folder_id,
            dest_gmail,
        )
