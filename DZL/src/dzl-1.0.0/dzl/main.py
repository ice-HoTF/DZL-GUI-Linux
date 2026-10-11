import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

from dzl.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DZL")
    app.setApplicationDisplayName("DayZ Mod Launcher")
    app.setOrganizationName("dzl")
    app.setDesktopFileName("dzl")

    icon_path = Path("/usr/share/icons/hicolor/256x256/apps/dzl.png")
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        win = MainWindow()
    except SystemExit:
        return 1
    except Exception as e:
        QMessageBox.critical(None, "DZL", f"Fatal error: {e}")
        return 1

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
