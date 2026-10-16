# File Launcher

Attach PDFs/PPTX to notes and open them in the embedded browser, the local
browser, or the desktop app. Use **Tools → File Launcher Settings** for a UI, or
edit here:

- **`pdf_target`** / **`pptx_target`** — where each type opens:
  - `"webannotate"` *(default)* — a **browser-tab annotator**: opens next to your
    other tabs and lets you draw (pen, highlighter, eraser, text; colour, size,
    undo) directly in the browser. Marks are written back into the PDF on **Save**
    and automatically when the tab/Anki closes. Uses PyMuPDF + a local
    127.0.0.1 helper, so the file is never locked.
  - `"annotate"` — the same drawing but in a separate **window**: draw with pen,
    highlighter, eraser and text (colour + size + undo), across pages. Drawings
    are written into the PDF and **saved automatically when you close the
    window**. Uses PyMuPDF (installed on first use). PPTX is converted to PDF
    (LibreOffice) and the annotated PDF is cached so marks persist.
  - `"embedded_browser"` — a new tab in the in-Anki tabbed browser (add-on
    918010938, the Socrates one); its PDF viewer can draw but only *download* a
    separate copy (no auto-save).
  - `"local_browser"` — your system default viewer.
  - `"local_app"` — the desktop app (Adobe, PowerPoint, …).
- **`libreoffice_path`** — path to `soffice`. Usually auto-detected. PPTX is
  converted to PDF with LibreOffice so it can open (and be drawn on) in a
  browser tab; set this only if PPTX won't open.

## Use

- Click **📎** in the editor toolbar to attach a PDF/PPTX and insert a link.
- Click the link in the **editor** or during **review** to open the file.
- The embedded browser must be open for the "embedded_browser" target; if it
  isn't, the file opens in your local browser instead.
