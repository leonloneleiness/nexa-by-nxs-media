# Thư mục cache model

Không đưa model vào Git/ZIP. Tải bằng:

```bat
.venv\Scripts\python scripts\download_models.py            :: cả hai
.venv\Scripts\python scripts\download_models.py --hands    :: MediaPipe hand_landmarker.task (~7.6 MB)
.venv\Scripts\python scripts\download_models.py --whisper medium
```

- `hand_landmarker.task`: từ `storage.googleapis.com/mediapipe-models/...` (nguồn chính thức của Google), kiểm tra
  MD5 theo header `x-goog-hash` do máy chủ cung cấp.
- `whisper/`: cache Hugging Face của `Systran/faster-whisper-<tên>` do faster-whisper tải.
