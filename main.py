"""YouTube Gelismis Arama - giris noktasi."""
import os
import sys


def main() -> int:
    from app.utils.paths import ensure_dirs
    ensure_dirs()
    from app.utils.logger import setup_logger
    log = setup_logger()
    log.info("Uygulama baslatildi")

    from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("YouTubeSearch")
    app.setOrganizationName("YouTubeSearch")

    from app.utils.paths import icon_path
    icon_file = icon_path()
    if os.path.isfile(icon_file):
        app.setWindowIcon(QIcon(icon_file))

    QLocale.setDefault(QLocale("tr_TR"))
    translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_tr", translations_path):
        app.installTranslator(translator)

    from app.services.settings_service import SettingsService
    settings = SettingsService()

    from app.ui.theme import apply_theme
    apply_theme(app, settings.theme)

    from app.ui.main_window import MainWindow
    window = MainWindow(settings)
    from app.ui.theme import sync_titlebar
    sync_titlebar(window)
    window.show()

    # Otomatik sinama modu: YTARA_SELFTEST=1 iken pencere kisa surede kapanir
    if os.environ.get("YTARA_SELFTEST") == "1":
        QTimer.singleShot(2000, app.quit)

    code = app.exec()
    log.info("Uygulama kapandi (kod %s)", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
