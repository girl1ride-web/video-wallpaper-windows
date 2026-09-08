# Video Wallpaper

Video wallpaper cho Windows, chạy video phía sau desktop icons.

## Tính năng

- Chọn video local: MP4, MKV, WebM, MOV, AVI, M4V
- Loop video
- 720p / 1080p / 4K với nhiều mức FPS
- Không phát âm thanh
- System tray
- Đóng cửa sổ vẫn giữ wallpaper chạy
- Tự chạy cùng Windows
- Nhớ video và profile đã chọn
- Tự tạm dừng khi game/app chạy fullscreen
- Build thành một file `VideoWallpaper.exe`

## Build

Yêu cầu Windows và Python 3.12.

Chạy:

```bat
BUILD_PRODUCTION_ONE_EXE.bat
```

File sau khi build:

```text
dist\VideoWallpaper.exe
```

Sau khi build, có thể phân phối riêng `VideoWallpaper.exe`; máy nhận không cần cài Python hay renderer riêng.
