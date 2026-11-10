"""
The PDF report, with ReportLab (pure Python, BSD) and the DejaVu fonts that ship inside
matplotlib's wheel, so it needs no system libraries, no font cache and no network: it runs the
same on ECS and as a Lambda step. Same content as the HTML page, from the same model.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from processor.render_html import duration, mb, plain, refs

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#4b5563")
LINE = colors.HexColor("#d9dee5")
SOFT = colors.HexColor("#f4f6f8")
ACCENT = colors.HexColor("#1f4e8c")
WARN_BG = colors.HexColor("#fff7e6")
WARN_LINE = colors.HexColor("#d97706")
WARN_INK = colors.HexColor("#7c2d12")
OK = colors.HexColor("#166534")
BAD = colors.HexColor("#991b1b")

PAGE_W, PAGE_H = A4
MARGIN = 17 * mm
FRAME_W = PAGE_W - 2 * MARGIN


def _fonts() -> str:
    """Register DejaVu Sans from matplotlib's bundled fonts (read-only, inside the wheel)."""
    import matplotlib

    if "DejaVu" in pdfmetrics.getRegisteredFontNames():
        return "DejaVu"
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(ttf / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ttf / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Oblique", str(ttf / "DejaVuSans-Oblique.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-BoldOblique", str(ttf / "DejaVuSans-BoldOblique.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuMono", str(ttf / "DejaVuSansMono.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu-Oblique",
                                  boldItalic="DejaVu-BoldOblique")
    return "DejaVu"


def _styles() -> dict[str, ParagraphStyle]:
    f = _fonts()
    base = ParagraphStyle("base", fontName=f, fontSize=9.5, leading=13.2, textColor=INK, alignment=TA_LEFT)
    return {
        "body": base,
        "para": ParagraphStyle("para", parent=base, spaceAfter=6),
        "title": ParagraphStyle("title", parent=base, fontName="DejaVu-Bold", fontSize=19, leading=24, spaceAfter=4),
        "sub": ParagraphStyle("sub", parent=base, textColor=MUTED, fontSize=10.5, leading=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName="DejaVu-Bold", fontSize=14, leading=18, spaceBefore=14,
                             spaceAfter=6, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=base, fontName="DejaVu-Bold", fontSize=11, leading=14, spaceBefore=9,
                             spaceAfter=3, keepWithNext=1),
        "h4": ParagraphStyle("h4", parent=base, fontName="DejaVu-Bold", fontSize=9.5, leading=12, spaceBefore=6,
                             spaceAfter=2, textColor=MUTED, keepWithNext=1),
        "note": ParagraphStyle("note", parent=base, fontSize=8.3, leading=11, textColor=MUTED),
        "cap": ParagraphStyle("cap", parent=base, fontSize=8.6, leading=11.6, spaceBefore=3, spaceAfter=8),
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.8, leading=9.8),
        "cellb": ParagraphStyle("cellb", parent=base, fontName="DejaVu-Bold", fontSize=7.8, leading=9.8),
        "ref": ParagraphStyle("ref", parent=base, fontSize=8.2, leading=10.8, spaceAfter=3),
        "warn": ParagraphStyle("warn", parent=base, textColor=WARN_INK, fontSize=8.8, leading=12),
        "meta": ParagraphStyle("meta", parent=base, fontSize=9, leading=12.5),
    }


def e(text: Any) -> str:
    return escape(str(text))


def _table(header: list[str], rows: list[list[str]], st: dict[str, ParagraphStyle], num_from: int = 1,
           widths: list[float] | None = None, kv: bool = False) -> Table:
    ncols = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 1
    if widths is None:
        # Room for the longest header word (headers wrap between words) and the cell text.
        lens = [max([max((len(w) for w in str(header[i]).split()), default=0) + 1 if i < len(header) else 0]
                    + [len(str(r[i])) for r in rows if i < len(r)])
                for i in range(ncols)]
        lens = [min(max(n, 4), 40) for n in lens]
        tot = sum(lens)
        widths = [FRAME_W * n / tot for n in lens]
        if sum(widths) > FRAME_W:
            widths = [w * FRAME_W / sum(widths) for w in widths]
    data = []
    if header:
        data.append([Paragraph(e(h), st["cellb"]) for h in header])
    for r in rows:
        data.append([Paragraph(e(c), st["cellb"] if (kv and i == 0) else st["cell"]) for i, c in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    t.setStyle(TableStyle(style))
    return t


def _box(flowables: list, st: dict[str, ParagraphStyle]) -> Table:
    t = Table([[flowables]], colWidths=[FRAME_W], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN_BG), ("LINEBEFORE", (0, 0), (0, -1), 3, WARN_LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _image(png: bytes, w_px: int, h_px: int, max_w: float = FRAME_W, max_h: float = PAGE_H * 0.58) -> Image:
    scale = min(max_w / w_px, max_h / h_px)
    return Image(io.BytesIO(png), width=w_px * scale, height=h_px * scale, hAlign="LEFT")


def _bullets(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable([ListItem(Paragraph(i, style), leftIndent=10, value="•") for i in items],
                        bulletType="bullet", start="•", leftIndent=10, bulletFontSize=7)


def write(model: dict[str, Any], overview_png: Path | None, path: Path,
          images: dict[str, tuple[bytes, int, int]]) -> Path:
    st = _styles()
    m = model
    story: list = []
    story.append(Paragraph(e(m["title"]), st["title"]))
    if m["subtitle"]:
        story.append(Paragraph(e(m["subtitle"]), st["sub"]))
    meta = [["Report written", m["generated"]]]
    if m["run_window"][0]:
        meta.append(["Steps ran", f"{m['run_window'][0]} – {m['run_window'][1]}"])
    meta.append(["Steps", f"{len(m['steps'])} (" + ", ".join(s["label"] for s in m["steps"]) + ")"])
    meta.append(["Sessions", str(len(m["sessions"]))])
    if m["datasets"]:
        meta.append(["Data", "; ".join(d["title"] + (f" (DANDI:{d['dandiset']})" if d["dandiset"] else "")
                                      for d in m["datasets"])])
    story.append(_table([], meta, st, widths=[30 * mm, FRAME_W - 30 * mm], kv=True))

    story.append(Paragraph("Overview", st["h2"]))
    wf = [w["name"] for w in m["workflows"]]
    story.append(Paragraph(
        f"This report collects the results of {len(m['steps'])} analysis step{'s' if len(m['steps']) != 1 else ''} of the "
        f"<b>{e(' and '.join(wf))}</b> workflow{'s' if len(wf) != 1 else ''} on {len(m['sessions'])} "
        f"session{'s' if len(m['sessions']) != 1 else ''}. Each step's section says what the step does, shows its headline "
        "numbers and figures with the captions the step wrote, and lists its warnings. Numbers and captions are copied "
        "from each step's own summary.json; this report does not recompute them.", st["body"]))
    if overview_png and overview_png.exists():
        from PIL import Image as PILImage

        with PILImage.open(overview_png) as im:
            w_px, h_px = im.size
        story.append(KeepTogether([
            _image(overview_png.read_bytes(), w_px, h_px, max_h=PAGE_H * 0.4),
            Paragraph("<b>Workflow overview.</b> The steps of each workflow found in this report, in pipeline order. "
                      "Filled boxes are steps whose results are included; grey dashed boxes are steps that were not "
                      "linked into the report.", st["cap"])]))
    if m["sessions"]:
        story.append(Paragraph("Sessions", st["h3"]))
        cols = [c for c in ("subject_id", "condition", "group") if any(r.get(c) for r in m["sessions"])]
        header = ["Session"] + [{"subject_id": "Subject"}.get(c, c.capitalize()) for c in cols] + ["Steps with results"]
        rows = [[r["session_id"]] + [r.get(c, "") for c in cols] + [", ".join(r["steps"])] for r in m["sessions"]]
        story.append(_table(header, rows, st))

    if m["warnings"]:
        items = [f"<b>{e(w['step'])}:</b> {e(w['text'])}" for w in m["warnings"]]
        story.append(Spacer(1, 6))
        story.append(_box([Paragraph(f"<b>Warnings ({len(items)})</b>", st["warn"]),
                           Paragraph("Read these before interpreting the results. Each is repeated in its step's "
                                     "section.", st["warn"]), _bullets(items, st["warn"])], st))

    for i, s in enumerate(m["steps"], 1):
        story.append(PageBreak())
        story.append(Paragraph(f"{i}. {e(s['title'])}", st["h2"]))
        bits = [f"{s['app']} {s['version']}"]
        if s["variant"]:
            bits.append(f"variant {s['variant']}")
        if s["wall_seconds"] is not None:
            bits.append(duration(s["wall_seconds"]))
        if s["refs"]:
            bits.append("references " + refs(s["refs"]))
        story.append(Paragraph(e(" · ".join(bits)), st["note"]))
        story.append(Paragraph(e(s["about"]) if s["about"] else
                               f"No description is built into this report for {e(s['app'])}; its results are shown "
                               "as the app wrote them.", st["body"]))
        if s["warnings"]:
            story.append(_box([Paragraph("<b>Warnings</b>", st["warn"]),
                               _bullets([e(w) for w in s["warnings"]], st["warn"])], st))
        if s["overall"]:
            story.append(Spacer(1, 4))
            story.append(_table([], [[k, v] for k, v in s["overall"]], st, widths=[55 * mm, FRAME_W - 55 * mm], kv=True))
        if s["session_rows"]:
            story.append(Paragraph("Headline numbers", st["h3"]))
            if s["transpose"] and s["app"] != "nwb-inspect":
                header = [""] + [r[0] for r in s["session_rows"]]
                rows = [[h] + [r[j] for r in s["session_rows"]] for j, h in enumerate(s["session_header"]) if j > 0]
                n = len(s["session_rows"])
                lw = 62 * mm
                story.append(_table(header, rows, st, widths=[lw] + [(FRAME_W - lw) / n] * n, kv=True))
            else:
                story.append(_table(s["session_header"], s["session_rows"], st))
        for t in s["overall_tables"]:
            story.append(Paragraph(e(t["name"]) + (f" (first {len(t['rows'])} of {t['n_rows']})" if t["truncated"] else ""),
                                   st["h4"]))
            story.append(_table(t["header"], t["rows"], st))
        for d in s["details"]:
            story.append(Paragraph("More numbers" + (f": {e(d['session'])}" if s["n_sessions"] > 1 else ""), st["h4"]))
            if d["lines"]:
                story.append(_table([], [[k, v] for k, v in d["lines"]], st, widths=[45 * mm, FRAME_W - 45 * mm], kv=True))
            for t in d["tables"]:
                story.append(Paragraph(e(t["name"]) + (f" (first {len(t['rows'])} of {t['n_rows']})" if t["truncated"] else ""),
                                       st["h4"]))
                story.append(_table(t["header"], t["rows"], st))
        if s["figures"]:
            story.append(Paragraph("Figures", st["h3"]))
        for f in s["figures"]:
            cap = Paragraph(f"<b>Figure {f['number']}.</b> {e(f['caption'] or '(no caption in summary.json)')} "
                            f"<font color='#6b7280'>({e(f['rel'])})</font>", st["cap"])
            got = images.get(f["path"])
            if got:
                story.append(KeepTogether([_image(*got), cap]))
            else:
                story.append(Paragraph(f"(figure could not be read: {e(f['rel'])})", st["note"]))
                story.append(cap)
        if s["omitted_figures"]:
            story.append(Paragraph(f"{len(s['omitted_figures'])} more figure(s) of this step (MAX_FIGURES = "
                                   f"{m['parameters']['MAX_FIGURES']}) are in its output folder: "
                                   + e(", ".join(s["omitted_figures"])) + ".", st["note"]))
        if s["missing_figures"]:
            story.append(Paragraph("Listed in summary.json but missing from the output: "
                                   + e(", ".join(s["missing_figures"])) + ".", st["note"]))
        for t in [t for t in s["tables"] if t["inline"]]:
            story.append(Paragraph("Table: " + e(t["rel"]), st["h4"]))
            if t["caption"]:
                story.append(Paragraph(e(t["caption"]), st["note"]))
            story.append(_table(t["inline"]["header"], t["inline"]["rows"], st))
        rest = [t for t in s["tables"] if not t["inline"]]
        if rest:
            story.append(Paragraph("Other tables in the step's output", st["h4"]))
            story.append(_bullets([e(t["rel"]) + (f" ({t['n_rows']:,} rows)" if t["n_rows"] is not None else "")
                                   + (": " + e(t["caption"]) if t["caption"] else "")
                                   + ("" if t["exists"] else " <b>(missing)</b>") for t in rest], st["note"]))
        if s["parameters"]:
            story.append(Paragraph("Parameters", st["h4"]))
            story.append(Paragraph(" · ".join(f"<font name='DejaVuMono'>{e(k)}</font>={e(plain(v)) or '(empty)'}"
                                              for k, v in s["parameters"].items()), st["note"]))

    story.append(PageBreak())
    story.append(Paragraph("Methods", st["h2"]))
    for s in m["steps"]:
        text = (f"<b>{e(s['title'])}.</b> {e(s['methods'])}"
                + (f" ({e(', '.join(s['main_tools']))})" if s["main_tools"] else "")
                + (f" {refs(s['refs'])}" if s["refs"] else "") + ". "
                + f"The step ran as {e(s['app'])} {e(s['version'])}"
                + (f" (variant {e(s['variant'])})" if s["variant"] else "")
                + (f" on {s['n_sessions']} session{'s' if s['n_sessions'] != 1 else ''}" if s["n_sessions"] else "")
                + f"; its parameters are listed in section {s['index']}.")
        story.append(Paragraph(text, st["para"]))
    story.append(Paragraph(f"The report was written by neuro-report {e(m['version'])} (Pennsieve), which copies each "
                           "step's numbers, figures, captions and warnings from its summary.json and its software "
                           "versions, parameters and citations from its provenance.json.", st["body"]))

    story.append(Paragraph("Software &amp; provenance", st["h2"]))
    rows = [[s["label"], s["version"], s["variant"] or "–",
             "; ".join(f"{k} {v}" for k, v in s["tools"].items()),
             duration(s["wall_seconds"]) if s["wall_seconds"] is not None else "–", mb(s["peak_rss_mb"]),
             s["gpu"] or "none"] for s in m["steps"]]
    widths = [27 * mm, 15 * mm, 22 * mm, FRAME_W - (27 + 15 + 22 + 16 + 17 + 20) * mm, 16 * mm, 17 * mm, 20 * mm]
    story.append(_table(["Step", "Version", "Variant", "Tools", "Run time", "Peak memory", "GPU"], rows, st,
                        widths=widths))
    story.append(Paragraph("Run time and peak memory are what each step recorded in its provenance.json (whole step, "
                           "all sessions).", st["note"]))

    story.append(Paragraph("References", st["h2"]))
    story.append(Paragraph("The works each step cites in its provenance.json, and the datasets. Author lists, titles "
                           "and journals come from the Pennsieve apps' CITATION.cff files, verified against Crossref, "
                           "DataCite and PubMed.", st["note"]))
    story.append(Spacer(1, 4))
    for r in m["references"]:
        link = f"<a href='{e(r['url'])}' color='#1f4e8c'>doi:{e(r['doi'])}</a>"
        if r["known"]:
            text = f"{r['n']}. {e(r['authors'])}. {e(r['title'])}. {e(r['where'])} {link}"
        else:
            text = f"{r['n']}. <font color='#991b1b'>DOI only (not in the report's citation table):</font> {link}"
        story.append(Paragraph(text, st["ref"]))

    story.append(Paragraph("Acknowledgements", st["h2"]))
    story.append(Paragraph("These analyses package other people's methods, and the credit for them is theirs. "
                           "Pennsieve packaged the methods as platform apps; it did not develop them. The steps in "
                           "this report are built on:", st["body"]))
    story.append(_bullets([f"<b>{e(a['app'])}</b>: " + ", ".join(
        (f"<a href='{e(sw['url'])}' color='#1f4e8c'>{e(sw['title'])}</a>" if sw.get("url") else e(sw["title"]))
        for sw in a["software"]) for a in m["acknowledgements"]], st["body"]))
    if m["datasets"]:
        story.append(Paragraph("Data", st["h3"]))
        items = []
        for d in m["datasets"]:
            t = (f"{e(d['creators'])}" + (f" ({e(d['year'])})" if d["year"] else "") + ". " if d["creators"] else "")
            t += f"<i>{e(d['title'])}</i>" + (f", {e(d['publisher'])}" if d["publisher"] else "")
            t += (f" (DANDI:{e(d['dandiset'])})" if d["dandiset"] else "") + f". doi:{e(d['doi'])}"
            t += (f", {e(d['licence'])}" if d["licence"] else "") + f" [{d['n']}]"
            t += (f"; described in [{d['paper']}]" if d["paper"] else "") + "."
            items.append(t)
        story.append(_bullets(items, st["body"]))
    story.append(Paragraph("The data are shared in the Neurodata Without Borders (NWB) format and the DANDI "
                           "Archive.", st["body"]))

    story.append(Paragraph("How to cite this analysis", st["h2"]))
    apps = "; ".join(f"{a['app']} {a['version']}" + (f" ({a['repository']})" if a["repository"] else "")
                     for a in m["apps_cited"])
    ds = "; ".join(f"doi:{d['doi']}" for d in m["datasets"])
    story.append(Paragraph(
        "If you use these results, please cite the methods each step rests on (References "
        + (refs([r["n"] for r in m["references"]]) if m["references"] else "") + "), the dataset"
        + ("s" if len(m["datasets"]) != 1 else "") + " analysed" + (f" ({e(ds)})" if ds else "")
        + ", and the Pennsieve apps that ran the analysis, with their versions: " + e(apps)
        + ". Each app's CITATION.cff lists the full references. Keep this report with the results: it records the "
        "parameters and software versions that produced them.", st["body"]))

    if m["issues"]:
        story.append(Paragraph("Notes on the inputs", st["h2"]))
        story.append(Paragraph("Places where a step's output does not follow the shared output contract "
                               "(conventions.md). They do not change the results above; they are listed for the app "
                               "maintainers.", st["note"]))
        story.append(_bullets([f"<b>{e(i['app'])}</b> ({e(i['folder'])}): {e(i['problem'])}" for i in m["issues"]],
                              st["note"]))

    title = m["title"]

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("DejaVu", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 10 * mm, title[:110])
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=16 * mm, title=title, author="Pennsieve neuro-report",
                            subject=", ".join(w["name"] for w in m["workflows"]), creator=f"neuro-report {m['version']}",
                            invariant=1)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
