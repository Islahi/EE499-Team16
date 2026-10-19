# Qt desktop implementation guidance

For the user's step-by-step Designer task, use
[Qt_Designer_Build_Guide.md](Qt_Designer_Build_Guide.md): form templates, widget
types, exact object names, properties, input units and the later Python boundary.

Added at the user's request on 18 Oct 2026. Apply the beneficial patterns from
[Simple-PyQt5-Password-Manager](https://github.com/Islahi/Simple-PyQt5-Password-Manager)
when implementing this project's desktop UI. This is implementation guidance,
not an instruction to copy that application, replace engineering contracts or
introduce its authentication/database features.

## 1. What was actually inspected

Static source review of `master`, verified on 18 Oct 2026 at commit
`6f8273cd04d73368403db75bb23e84b5ef2141d8`. The reference application was not run.
The source commit matches the reference behind the user's coding-style skill.

| Source evidence (pinned) | Observed Qt use | Useful adaptation here |
|---|---|---|
| [interface.py](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/interface.py), [login.py](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/login.py), [signup.py](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/signup.py) | Small `QMainWindow` subclasses call `uic.loadUi`, bind named widgets with `findChild`, and set icons | Designer forms plus small, explicit Python window/dialog classes |
| [main.py, lines 11-58](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/main.py#L11-L58) | Controller creates screens and connects `clicked`/`textChanged` to named handlers | Visible initialization and `connect_events()` methods; no hidden action routing |
| [mainUI.ui](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/assets/mainUI.ui) | Main form uses nested grid, horizontal and vertical layouts (11 layout elements) | Keep layout-driven resizing; do not translate PowerPoint coordinates into fixed positions |
| [main.py, lines 182-212](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/main.py#L182-L212) | Direct widget updates, status-bar messages and named actions | Clear run state, selected-bus details and readable feedback |
| [app.pyw](https://github.com/Islahi/Simple-PyQt5-Password-Manager/blob/6f8273cd04d73368403db75bb23e84b5ef2141d8/src/app.pyw) | Small launcher delegates to the application controller | Keep startup separate from screen construction and backend calculations |

These are observations. The safety, threading and packaging guidance below is
our adaptation for a numerical application, not a claim that the reference
implements those features.

## 2. Instructions for implementing our UI

1. Keep editable Designer `.ui` files as the layout source. Put signal bindings
   and application behavior in handwritten Python, not generated form code.
2. Keep object names descriptive and synchronized with bindings, for example
   `btn_load_data`, `btn_run_simulation`, `btn_run_optimization`,
   `btn_export_results`, `network_view`, `results_text` and `run_log`.
   Use named handlers such as `load_data()`, `run_simulation()` and
   `export_results()`; do not hide substantial logic in lambdas.
3. Initialize explicit state, construct screens, bind events and then show the
   main window. Keep a single `QApplication` and start its event loop in the
   entry function, not inside a window constructor. Do not replace the existing
   backend `src/main.py` demo just to imitate the reference's filenames.
4. Use a main window plus focused Load Data and Settings dialogs. `QDialog` is
   appropriate for those dialogs; the reference's use of `QMainWindow` for all
   three screens is not a requirement. Keep Python references/Qt ownership clear
   so windows and workers are not destroyed while in use.
5. Keep engineering work in the existing public backend modules. Dialogs collect
   values, show errors and call preparation/loading APIs. Simulation and
   optimization handlers start jobs; they must not contain FBS, BESS, PV,
   load-generation, cost or scenario equations.
6. Match the user's `02_Reports/Working/Drafts/UI.pptx` main-window layout, not
   the password manager's visual appearance: left actions, Network/Results tabs,
   stage/progress area and a collapsible read-only log. Respect later user
   revisions. Start Results with text from `results.format_summary`; graphs are
   not required for the initial version.
7. Use Qt layouts, size policies and adjustable splitters. Check both normal
   and smaller windows/Windows display scaling. Keep repeated styling in one
   stylesheet/theme location rather than copying long styles into handlers.
8. Resolve forms/assets from `Path(__file__).resolve()` or Qt resources, not
   `./assets` relative to the process working directory. If packaging an EXE,
   include all required forms/resources and test launching from another folder.

### Long-running numerical work

- Run simulation, ARIMA and GWO outside the GUI event thread. A worker `QObject`
  on a `QThread` is a suitable initial Qt pattern; deliver results/errors/stage
  updates by signals, with widget updates only on the GUI thread. Keep worker
  and thread references and clean them up after completion/failure.
- A QThread is for responsiveness, not a promise of faster CPU-bound Python.
  Consider a process only if measurements justify it; do not introduce parallel
  solvers or change results merely to imitate another application.
- Snapshot the run inputs and disable conflicting actions while running. When
  data/settings change, clear or mark earlier results stale. Do not export them
  as if they came from the new inputs. Restore controls on success and failure.
- Use real stage/count information. The backend currently lacks fine-grained
  progress/cancellation hooks: use an indeterminate busy indicator where needed
  until hooks are implemented/tested. Do not fabricate percentages, block on a
  join in the GUI, or forcibly terminate a worker. Do not advertise working
  cancellation before cooperative cancellation exists.

### Automatically arranged feeder

Use `QGraphicsScene`/`QGraphicsView` as a suitable implementation approach:
vector lines/buses, zoom, fit and selected-bus information. Designer defines the
view/placeholder; Python creates the dynamic scene from the loaded network.
Keep the layout calculation separate from drawing so it can be tested without
Qt. Preserve bus IDs and topology; positions must never change R/X or connections.
This is a schematic of an existing radial network, not geographic routing or
a manual network editor. Do not construct the feeder from many PNG fragments.
Small icons remain optional for toolbar decoration, not electrical topology.

## 3. Qt binding and form loading

The reference uses **PyQt5**, but following its structure does not require
PyQt5. The first implementation now uses **PySide6/Qt Widgets** and declares it
separately in `requirements-ui.txt`, following the previously discussed
recommendation as an implementation choice, not new advisor approval.
Do not mix PyQt5, PyQt6 and PySide6 objects.

If PySide6 is selected, `PyQt5.uic.loadUi` is NOT a drop-in PySide6 API. Use one
documented workflow consistently:

- Generate a Python form with `pyside6-uic`, wrap it in handwritten code and call
  `setupUi(self)`. Regenerate after Designer edits; never hand-edit generated code.
- Or load the `.ui` with `PySide6.QtUiTools.QUiLoader`, retain the returned root
  widget, and explicitly bind/check its children. Unlike `uic.loadUi(path, self)`,
  loading returns a widget; do not accidentally construct two main windows.

For a new PySide6 implementation, generated forms are a practical proposal for
explicit bindings/packaging; runtime loading remains valid if chosen and tested.
In either case, keep the editable `.ui` files. No dependency migration, form
generation or GUI code is authorized merely by adding this guidance.

## 4. Do not copy these parts

- Wildcard imports, unguarded `currentItem()`/`items[0]` accesses, bare `except:`,
  relative asset-path assumptions or a large all-purpose controller. Check
  selections/required widgets, handle expected errors specifically and log
  unexpected failures without mislabelling them as an ordinary input error.
- Authentication, encryption, password tables, browser launching, clipboard
  dependencies or database setup: they do not serve our current product scope.
- The reference's dependency list wholesale: it lists PyQt5/cryptography while
  its source also imports SQLAlchemy/pyperclip. Declare/test the dependencies
  actually used by this application instead.
- Icons/code/assets without checking reuse permission and attribution. This
  review records patterns and links; it does not vendor third-party code.

## 5. UI implementation acceptance checks

- Designer forms remain editable and all required object names bind correctly.
- Launch from the repo root and another working directory; later test the EXE.
- Resize and change display scaling without hiding required inputs/actions.
- Missing file, invalid settings, no selected bus and failed backend jobs show
  useful feedback; the application remains responsive and controls recover.
- A three-month run does not freeze interaction; only the GUI thread updates
  widgets. Closing during an active job has a safe, explicit policy.
- Network positions/zoom do not modify the model. Results retain completion,
  convergence, feasibility, units and shedding/curtailment warnings.
- Existing backend tests still run without importing/requiring Qt.

The original guide was documentation-only. The subsequent implementation in
`src/ui.py` uses runtime loading into concrete roots, preserving the user's
forms. `src/README_ui.md` records inputs, tests and limitations. The software
contract was updated before those public UI/backend helpers were added.

Official Qt references checked on 18 Oct 2026:
[Designer forms/loading](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html),
[QThread workers](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html),
[QGraphicsView](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html).
