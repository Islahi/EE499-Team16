"""Offline typesetting for the model's curated LaTeX math expressions."""

from base64 import b64encode
from functools import lru_cache
from html import escape
from io import BytesIO
from threading import RLock

EQUATION_VERSION = 2
_RENDER_LOCK = RLock()

EXPRESSIONS = {
    "Radial Forward/Backward Sweep": (
        r"s_j=\frac{P_{\mathrm{load}}-P_{\mathrm{PV}}-P_{\mathrm{BESS}}"
        r"+\mathrm{j}(Q_{\mathrm{load}}-Q_{\mathrm{PV}}-Q_{\mathrm{BESS}})}{S_{\mathrm{base}}}",
        r"i_j=\operatorname{conj}(s_j/v_j),\quad I_{ij}=i_j+\sum_k I_{jk}",
        r"v_j=v_i-z_{ij}I_{ij},\quad \max_j |v_{j,\mathrm{new}}-v_{j,\mathrm{old}}|\leq\epsilon",
    ),
    "Battery energy and SOC": (
        r"P_{\mathrm{BESS}}=P_{\mathrm{dis}}-P_{\mathrm{ch}}",
        r"E_{t+1}=E_t+\left(\eta_{\mathrm{ch}}P_{\mathrm{ch}}"
        r"-\frac{P_{\mathrm{dis}}}{\eta_{\mathrm{dis}}}\right)\Delta t",
        r"\mathrm{SOC}_t=\frac{E_t}{E_{\mathrm{rated}}},\quad "
        r"\mathrm{SOC}_{\min}\leq\mathrm{SOC}_t\leq\mathrm{SOC}_{\max}",
    ),
    "Corrective actions and network limits": (
        r"P_{\mathrm{served}}=P_{\mathrm{requested}}-P_{\mathrm{shed}},\quad "
        r"0\leq P_{\mathrm{shed}}\leq P_{\mathrm{requested}}",
        r"Q_{\mathrm{served}}=Q_{\mathrm{requested}}\frac{P_{\mathrm{served}}}{P_{\mathrm{requested}}}"
        r"\quad(P_{\mathrm{requested}}>0)",
        r"P_{\mathrm{PV,used}}=P_{\mathrm{PV,available}}-P_{\mathrm{curt}},\quad "
        r"0\leq P_{\mathrm{curt}}\leq P_{\mathrm{PV,available}}",
    ),
    "Uncontrolled operating point": (
        r"P_{\mathrm{load}}=P_{\mathrm{requested}},\quad Q_{\mathrm{load}}=Q_{\mathrm{requested}}",
        r"P_{\mathrm{PV}}=P_{\mathrm{available}},\quad Q_{\mathrm{PV}}=Q_{\mathrm{available}}",
        r"P_{\mathrm{BESS}}=Q_{\mathrm{BESS}}=0,\quad E_{\mathrm{final}}=E_{\mathrm{initial}}",
    ),
    "Daily restoration and operating mode": (
        r"0\leq P_{\mathrm{ch}}\leq z P_{\mathrm{ch,max}},\quad "
        r"0\leq P_{\mathrm{dis}}\leq(1-z)P_{\mathrm{dis,max}},\quad z\in\{0,1\}",
        r"E_{\mathrm{end}}=E_{\mathrm{start}}\quad(\mathrm{MILP}),\quad "
        r"|E_{\mathrm{end}}-E_{\mathrm{start}}|\leq\epsilon_E\quad(\mathrm{audit})",
    ),
    "Battery P/Q and inverter capability": (
        r"\mathrm{PF}=\frac{P_{\mathrm{dis}}}{\sqrt{P_{\mathrm{dis}}^2+Q_{\mathrm{BESS}}^2}}"
        r"\geq\mathrm{PF}_{\min}\quad(P_{\mathrm{dis}}>0)",
        r"0\leq Q_{\mathrm{BESS}}\leq P_{\mathrm{dis}}\tan(\arccos(\mathrm{PF}_{\min}))",
        r"P_{\mathrm{BESS}}^2+Q_{\mathrm{BESS}}^2\leq S_{\mathrm{rated}}^2",
        r"S_{\mathrm{rated}}=P_{\mathrm{rated}}\max(k_{\mathrm{BESS}},1/\mathrm{PF}_{\min})",
    ),
    "Joint GA objective and fitness": (
        r"F_{\mathrm{screen}}=C_{\mathrm{CAPEX}}(\mathrm{CRF}+f_{\mathrm{OM}})"
        r"+\sum_d w_d(C_{\mathrm{energy},d}+C_{\mathrm{penalty},d}+C_{\mathrm{inventory},d})",
        r"\mathrm{Fitness}(r)=N-r+1,\quad r=1,\ldots,N",
    ),
    "Chronological annual operating cost": (
        r"C_{\mathrm{operating}}=\sum_t\Delta t\,(c_{\mathrm{import}}P_{\mathrm{import}}"
        r"-c_{\mathrm{export}}P_{\mathrm{export}}+c_{\mathrm{shed}}P_{\mathrm{shed}}"
        r"+c_{\mathrm{curt}}P_{\mathrm{curt}})+C_{\mathrm{inventory}}",
        r"C_{\mathrm{inventory}}=\sum_b c_{\mathrm{import}}"
        r"\frac{\max(E_{\mathrm{initial}}-E_{\mathrm{final}},0)}{\eta_{\mathrm{ch}}}",
        r"C_{\mathrm{annual}}=C_{\mathrm{operating}}+C_{\mathrm{capital}}+C_{\mathrm{OM}}",
    ),
}


def ownership_expressions(economics):
    basis = economics.get("power_cost_basis")
    if basis == "kva":
        lines = [r"C_{\mathrm{CAPEX}}=\sum_b(c_E E_{\mathrm{rated}}+c_S S_{\mathrm{rated}})"]
    elif basis == "kw":
        lines = [r"C_{\mathrm{CAPEX}}=\sum_b(c_E E_{\mathrm{rated}}+c_P P_{\mathrm{rated}})"]
    else:
        lines = []
    method = economics.get("annualization_method")
    if method == "real_crf":
        lines.extend((
            r"r=\frac{1+i_{\mathrm{nominal}}}{1+\pi}-1",
            r"\mathrm{CRF}=\frac{r(1+r)^n}{(1+r)^n-1},\quad "
            r"\mathrm{CRF}=\frac{1}{n}\quad (|r|<10^{-12})",
        ))
    elif method == "straight_line":
        lines.append(r"\mathrm{CRF}=\frac{1}{n}")
    lines.append(r"C_{\mathrm{capital}}=\mathrm{CRF}\, C_{\mathrm{CAPEX}},\quad "
                 r"C_{\mathrm{OM}}=f_{\mathrm{OM}} C_{\mathrm{CAPEX}}")
    return lines


def equation_records(equations, economics):
    return [
        {"id": title.lower().replace(" ", "-"), "title": title, "version": EQUATION_VERSION,
         "latex": list(ownership_expressions(economics) if title == "Battery investment and annual ownership"
                       else EXPRESSIONS[title]), "text": formula, "note": note}
        for title, formula, note in equations
    ]


@lru_cache(maxsize=128)
def math_image(expression):
    """Render LaTeX math to a PNG without TeX subprocesses, JS or font downloads."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import math_to_image
    from struct import unpack

    output = BytesIO()
    with _RENDER_LOCK:
        math_to_image("$" + expression + "$", output, prop=FontProperties(size=13, math_fontfamily="stix"),
                      dpi=192, format="png", color="#142632")
    data = output.getvalue()
    width, height = unpack(">II", data[16:24])
    return "data:image/png;base64," + b64encode(data).decode("ascii"), width // 2, height // 2


def equation_html(record, *, reference_version, archived=False):
    if not isinstance(record, dict):
        if not isinstance(record, (list, tuple)) or len(record) != 3:
            return ""
        title, formula, note = record
        return _fallback(title, formula, note, "Archived equation text", reference_version)
    title, formula, note = (str(record.get(key, "")) for key in ("title", "text", "note"))
    lines = record.get("latex")
    if (record.get("version") != EQUATION_VERSION or not isinstance(lines, (list, tuple))
            or not 1 <= len(lines) <= 8 or any(not isinstance(line, str) or len(line) > 600 for line in lines)):
        return _fallback(title, formula, note, "Archived equation text", reference_version)
    try:
        pictures = [math_image(line) for line in lines]
    except (ImportError, ValueError, RuntimeError, OSError, RecursionError):
        return _fallback(title, formula, note, "Equation renderer unavailable. Readable source", reference_version)
    alternatives = formula.splitlines()
    rendered = "".join(f'<p class="math-line"><img src="{uri}" width="{width}" height="{height}" '
                       f'alt="{escape(alternatives[index] if len(alternatives) == len(pictures) else title, quote=True)}"></p>'
                       for index, (uri, width, height) in enumerate(pictures))
    archive_label = "<p class='fine'>Typeset from matching archived equation text · version 1</p>" if archived else ""
    return (f"<h3>{escape(title)}</h3>{archive_label}<div class='model-equation math-typeset' aria-label='{escape(formula, quote=True)}'>"
            f"{rendered}</div><p>{escape(note)}</p>")


def _fallback(title, formula, note, label, version):
    safe = escape(str(formula)).replace("\n", "<br>")
    return (f"<h3>{escape(str(title))}</h3><p class='fine'>{label} · version {escape(str(version))}</p>"
            f"<p class='model-equation'>{safe}</p><p>{escape(str(note))}</p>")
