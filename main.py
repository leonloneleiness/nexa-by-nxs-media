"""Điểm chạy duy nhất của NEXA: `python main.py`."""
import sys

from nexa.desktop.win32api import set_dpi_awareness

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--nexa-check-install":
        from nexa.installation_check import main as check_install
        sys.exit(check_install(sys.argv[2]))
    if len(sys.argv) > 2 and sys.argv[1] == "--nexa-console-run":
        # cửa sổ "chạy thử tệp" do NEXA mở (nexa/code/console_run.py) — không nạp giao diện
        from nexa.code.console_run import console_main

        sys.exit(console_main(sys.argv[2]))
    # Các nhánh "tự mở khóa khi vỗ tay" — không nạp giao diện Qt (xem nexa/desktop/unlock.py).
    if len(sys.argv) > 1 and sys.argv[1] == "--nexa-unlock-service":
        # Dịch vụ SYSTEM: có thể do SCM khởi động (không thêm arg) hoặc gọi install/start thủ công.
        from nexa.desktop.unlock_service import service_main

        # HandleCommandLine đọc argv[2:]; bỏ sentinel khỏi argv để nó thấy đúng lệnh.
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        service_main()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--nexa-unlock-inject":
        # Injector chạy quyền SYSTEM trên desktop Winlogon: gõ mã mở khóa.
        from nexa.desktop.unlock import injector_main

        sys.exit(injector_main())
    if len(sys.argv) > 1 and sys.argv[1] == "--nexa-install-unlock-service":
        # Chạy sau khi đã elevate qua UAC: cài + khởi động dịch vụ rồi thoát.
        from nexa.desktop.unlock import install_service

        sys.exit(0 if install_service() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "--nexa-uninstall-unlock-service":
        from nexa.desktop.unlock import uninstall_service

        sys.exit(0 if uninstall_service() else 1)
    # Phải đặt DPI awareness TRƯỚC khi nạp Qt/pyautogui để mọi tọa độ Win32 là pixel vật lý.
    set_dpi_awareness()
    from nexa.app import run

    sys.exit(run(sys.argv))
