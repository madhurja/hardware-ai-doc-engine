# Local App Guide

The project can run like a browser-based software app without uploading customer files to a cloud service.

## Windows

Run:

```powershell
.\run_windows.ps1
```

Then open:

```text
http://127.0.0.1:8000
```

The script also prints Android links for the same Wi-Fi network.

## Android

1. Start the app on Windows with `.\run_windows.ps1`.
2. Keep the Windows terminal open.
3. Connect the Android phone to the same Wi-Fi network.
4. Open the printed `http://<PC-IP>:8000` link in Android Chrome.
5. Use Chrome's install option to pin it to the home screen.

## Installable Browser App

The app includes a web manifest and service worker, so supported browsers can install it as a PWA. It still runs from the local Windows server, which keeps schematic PDFs, BOMs, firmware files, and generated PDFs on the local machine.
