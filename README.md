
Chạy lần đầu:

```bash
doppler run -p auto-upload-google-drive -c prod -- uv run python main.py local-auth
```

Chạy lại cho account đã lưu trong DB:

```bash
doppler run -p auto-upload-google-drive -c prod -- uv run python main.py local-auth --gmail-address your_email@gmail.com
```
