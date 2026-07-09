import re


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

    raise ValueError("Invalid Google Drive folder URL or ID.")
