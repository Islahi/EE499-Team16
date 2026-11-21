"""Show the saved HTML in Qt WebEngine or the system browser."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout


def show_dashboard(parent, path):
    path = Path(path).resolve(strict=True)
    url = QUrl.fromLocalFile(str(path))

    def external():
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(parent, "Results dashboard", f"Open this saved report in a browser: {path}")

    try:
        from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
                                             QWebEngineUrlRequestInterceptor)
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except (ImportError, OSError):
        parent.statusBar().showMessage("Qt WebEngine is unavailable. Opening the saved report in your browser.", 8000)
        external()
        return None

    class OfflineRequests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, request):
            target = request.requestUrl()
            if target != url and target.scheme() not in ("blob", "data", "about"):
                request.block(True)

    dialog = QDialog(parent)
    dialog.setWindowTitle("Saved run dashboard")
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    layout = QVBoxLayout(dialog)
    buttons = QHBoxLayout()
    browser = QPushButton("Open in browser", dialog)
    browser.clicked.connect(external)
    buttons.addWidget(browser)
    buttons.addStretch()
    layout.addLayout(buttons)
    view = QWebEngineView(dialog)
    # The view owns its page. Give the profile the dialog lifetime and defer
    # its destruction until after the page has been deleted.
    profile = QWebEngineProfile(parent)
    guard = OfflineRequests(profile)
    profile.setUrlRequestInterceptor(guard)
    page = QWebEnginePage(profile, view)
    page.destroyed.connect(profile.deleteLater)
    view.setPage(page)
    layout.addWidget(view)

    for option in ("LocalContentCanAccessRemoteUrls", "LocalContentCanAccessFileUrls",
                   "JavascriptCanOpenWindows", "DnsPrefetchEnabled"):
        page.settings().setAttribute(getattr(QWebEngineSettings.WebAttribute, option), False)

    def download(request):
        target, _ = QFileDialog.getSaveFileName(dialog, "Save chart image",
                                               request.downloadFileName(), "PNG images (*.png)")
        if target:
            destination = Path(target)
            request.setDownloadDirectory(str(destination.parent.resolve()))
            request.setDownloadFileName(destination.name)
            request.accept()
        else:
            request.cancel()

    def print_to_pdf():
        target, _ = QFileDialog.getSaveFileName(dialog, "Save printed report",
                                               str(path.with_suffix(".pdf")), "PDF documents (*.pdf)")
        if target:
            if Path(target).resolve() == path:
                QMessageBox.warning(dialog, "Results dashboard", "Choose a separate PDF filename.")
                return
            page.printToPdf(target)

    def pdf_finished(filename, success):
        if not success:
            QMessageBox.warning(dialog, "Results dashboard", f"Could not write PDF: {filename}")

    profile.downloadRequested.connect(download)
    page.printRequested.connect(print_to_pdf)
    page.pdfPrintingFinished.connect(pdf_finished)
    view.loadFinished.connect(lambda ok: None if ok else browser.setText("Report could not load · Open in browser"))
    view.load(url)
    dialog.resize(1220, 820)
    dialog.show()
    return dialog
