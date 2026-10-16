# File Launcher

Attach PDFs/PPTX to notes and open them in the embedded browser, the local
browser, or the desktop app. Use **Tools → File Launcher Settings** for a UI, or
edit here:

- **`pdf_target`** / **`pptx_target`** — where each type opens:
  - `"embedded_browser"` — a new tab in the in-Anki tabbed browser (add-on
    918010938, the one with the Socrates tabs). Its PDF viewer has pen /
    highlight / text tools, so you can **draw on the PDF** and download it.
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
