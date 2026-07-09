import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# Phạm vi quyền truy cập: cho phép đọc, ghi, tạo và xóa các tệp trên Drive
SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_credentials():
    """Xác thực người dùng và trả về thông tin credentials."""
    creds = None
    # Tệp token.json lưu trữ mã thông báo truy cập sau lần đăng nhập đầu tiên
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Nếu không có thông tin xác thực hợp lệ, tiến hành đăng nhập
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                raise FileNotFoundError(
                    "Không tìm thấy tệp 'credentials.json'. Hãy tải xuống từ Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Lưu lại thông tin xác thực cho lần chạy sau
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def create_folder(service, folder_name):
    """Tạo một thư mục mới trên Google Drive và trả về ID của thư mục đó."""
    try:
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        # Gọi API tạo thư mục
        folder = service.files().create(body=file_metadata, fields="id").execute()
        folder_id = folder.get("id")
        print(f" Thư mục '{folder_name}' đã được tạo thành công.")
        print(f"   Folder ID: {folder_id}")
        return folder_id
    except HttpError as error:
        print(f"Đã xảy ra lỗi khi tạo thư mục: {error}")
        return None


def upload_file_to_folder(service, file_path, folder_id):
    """Tải một tệp cục bộ lên một thư mục cụ thể trên Google Drive."""
    if not os.path.exists(file_path):
        print(f"Lỗi: Không tìm thấy tệp tin '{file_path}' ở máy cục bộ.")
        return None

    try:
        file_name = os.path.basename(file_path)
        file_metadata = {
            "name": file_name,
            "parents": [folder_id],  # Định vị thư mục cha bằng ID
        }

        # Chuẩn bị dữ liệu tệp để tải lên
        media = MediaFileUpload(file_path, resumable=True)

        # Gọi API tải tệp lên
        uploaded_file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        print(f" Tệp '{file_name}' đã được tải lên thành công.")
        print(f"   File ID: {uploaded_file.get('id')}")
        return uploaded_file.get("id")
    except HttpError as error:
        print(f"Đã xảy ra lỗi khi tải tệp lên: {error}")
        return None


def main():
    try:
        # Bước A: Lấy thông tin xác thực và khởi tạo dịch vụ Drive
        creds = get_credentials()
        service = build("drive", "v3", credentials=creds)

        # Bước B: Định nghĩa tên thư mục và tiến hành tạo
        ten_thu_muc = "Tai Lieu Python"
        folder_id = create_folder(service, ten_thu_muc)

        if folder_id:
            # Bước C: Định nghĩa tệp cần tải lên (Ví dụ tạo một file test nhanh)
            ten_file_tai_len = "test_drive.txt"
            with open(ten_file_tai_len, "w", encoding="utf-8") as f:
                f.write("Xin chào! Đây là tệp được tải lên tự động từ mã Python.")

            # Tiến hành tải tệp vào thư mục vừa tạo
            upload_file_to_folder(service, ten_file_tai_len, folder_id)

    except Exception as e:
        print(f"Quá trình thực thi thất bại: {e}")


if __name__ == "__main__":
    main()
