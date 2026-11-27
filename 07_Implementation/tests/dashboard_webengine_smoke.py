"""Run the small offline report through its actual Qt WebEngine renderer.

Usage: python tests/dashboard_webengine_smoke.py REPORT_HTML [--pdf PATH]
Run under a normal desktop session if the platform cannot initialize WebEngine.
"""
import argparse
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication


class Offline(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, request):
        if request.requestUrl().scheme() not in ("data", "about", "blob"):
            request.block(True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--pdf", type=Path)
    args = parser.parse_args()
    html = args.report.read_text(encoding="utf-8")
    if len(html.encode("utf-8")) > 1_000_000:
        parser.error("Choose a small report (under 1 MB) for this in-memory smoke test.")
    app = QApplication([])
    profile = QWebEngineProfile()
    guard = Offline(profile)
    profile.setUrlRequestInterceptor(guard)
    page = QWebEnginePage(profile)
    view = QWebEngineView()
    view.setPage(page)
    view.resize(1380, 940)
    view.show()

    checks = [
        """async () => {
            if (document.querySelector('#tabs button:first-child')?.textContent!=='Summary' ||
                document.querySelector('#tabs button[aria-selected="true"]')?.textContent!=='Summary')
              throw Error('Summary is not the active first page');
            const cards = document.querySelectorAll('.workspace-card canvas').length;
            if (cards < 4) throw Error('Expected four Summary charts, found ' + cards);
            const style = getComputedStyle(document.querySelector('.workspace-grid')).gridTemplateColumns;
            if (style.split(' ').length !== 2) throw Error('Expected a two-column grid');
            if (!document.querySelector('.math-typeset img')?.naturalWidth) throw Error('Math image did not load');
            const advanced=document.getElementById('advanced-chart-controls');
            const toggle=document.querySelector('[aria-controls="advanced-chart-controls"]');
            if(!advanced.hidden)throw Error('Advanced controls opened by default');
            const snapshot=JSON.stringify(workspace.state.time);
            toggle.click();
            if(advanced.hidden)throw Error('Show controls did not reveal advanced fields');
            toggle.click();
            if(!advanced.hidden||JSON.stringify(workspace.state.time)!==snapshot)throw Error('Control state changed when hidden');
        }""",
        """async () => {
            const toolbar = document.querySelector('.workspace-toolbar');
            [...toolbar.querySelectorAll('button')].find(b=>b.textContent==='Focus').click();
            await new Promise(r=>setTimeout(r,320));
            if(document.querySelectorAll('.workspace-card').length!==1)throw Error('Focus mode did not expand a chart');
            [...document.querySelectorAll('.workspace-toolbar button')].find(b=>b.textContent==='Engineering').click();
            await new Promise(r=>setTimeout(r,320));
            if(!document.querySelector('.workspace-sidebar'))throw Error('Engineering mode did not open the editor');
            [...document.querySelectorAll('.workspace-toolbar button')].find(b=>b.textContent==='Grid').click();
            await new Promise(r=>setTimeout(r,320));
            if(document.querySelectorAll('.workspace-card').length<4)throw Error('Grid mode did not restore presets');
        }""",
        """async () => {
            const button=[...document.querySelectorAll('#tabs button')].find(b=>b.textContent==='Network');
            button.click();
            await new Promise(r=>setTimeout(r,500));
            const target=document.querySelector('.feeder [data-kind="bus"][data-entity="6"]');
            if(!target)throw Error('Bus 6 is unavailable');
            target.onclick();
            await new Promise(r=>setTimeout(r,500));
            if(!document.querySelector('#point-drawer').textContent.includes('bus 6'))throw Error('Bus drawer did not follow feeder');
            if(!document.querySelector('.workspace-card canvas'))throw Error('Selected bus update lost its charts');
            const overall=[...document.querySelectorAll('button')].find(b=>b.textContent.startsWith('Overall Health'));
            if(overall&&!overall.disabled){
              overall.click();
              await new Promise(r=>setTimeout(r,400));
              if(!document.querySelector('.workspace-feeder').textContent.includes('Entire recorded study'))
                throw Error('Overall Health did not display recorded coverage');
            }
        }""",
        """async () => {
            const chart=workspace.state.charts['Network:bus'];
            workspace.state.pinned=[chart.id];
            const saved=JSON.stringify(workspace.state);
            const restored=layoutFromJSON(JSON.parse(saved),run.manifest.run_id);
            if(restored.pinned[0]!==chart.id)throw Error('Pinned chart layout was lost');
            [...document.querySelectorAll('#tabs button')].find(b=>b.textContent==='My Dashboard').click();
            await new Promise(r=>setTimeout(r,320));
            if(!document.querySelector('.workspace-card canvas'))throw Error('Pinned chart is not visible');
        }""",
    ]

    def fail(message):
        print(message, flush=True)
        app.exit(1)

    def finish():
        if not args.pdf:
            print("Passed: Summary, disclosure, chart modes, equation images, feeder inspector and pinned layout")
            app.quit()
            return

        def verify(filename, success):
            if not success or not Path(filename).read_bytes().startswith(b"%PDF"):
                fail("Print/PDF failed")
            else:
                print("Passed: interactive overview, modes, math images, feeder drawer, pinned layout and PDF")
                app.quit()
        page.pdfPrintingFinished.connect(verify)
        page.runJavaScript("document.querySelector('.model-information').open=true",
                           lambda _: page.printToPdf(str(args.pdf.resolve())))

    def check_next(index=0):
        if index == len(checks):
            finish()
            return
        expression = checks[index]
        page.runJavaScript(f"window.testState='checking'; ({expression})().then(()=>window.testState='ok',e=>window.testState=e.message);")
        QTimer.singleShot(1800, lambda: page.runJavaScript(
            "window.testState", lambda value: check_next(index + 1) if value == "ok" else fail(f"Check {index + 1}: {value}")))

    page.loadFinished.connect(lambda ok: QTimer.singleShot(1200, check_next) if ok else fail("The report could not load."))
    QTimer.singleShot(25_000, lambda: fail("Timed out starting or testing Qt WebEngine."))
    page.setHtml(html)
    status = app.exec()
    view.close()
    page.deleteLater()
    app.processEvents()
    return status


if __name__ == "__main__":
    raise SystemExit(main())

