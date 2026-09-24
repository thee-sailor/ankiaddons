# Paste from ChatGPT

Converts ChatGPT-copied **Markdown** into rendered Anki HTML — equations,
tables, arrows, lists, code, headings — automatically.

Why it works: ChatGPT's *Copy* button puts both a rich-HTML and a plain-text
(Markdown) version on the clipboard. Anki's normal paste uses the HTML one,
which mangles equations. This add-on reads the clean **Markdown** instead and
renders it itself, using Anki's native `<anki-mathjax>` for equations.

## What it does

- **On paste (Ctrl+V):** if the clipboard looks like Markdown/LaTeX it is
  rendered and inserted; plain text, images, internal copies and drag-drops
  paste normally. The equation shows up rendered right away.
- **On startup:** any older notes that still contain raw LaTeX delimiters
  (`\[…\]`, `\(…\)`, `$$…$$`) are converted to `<anki-mathjax>` so they render.
  This runs quietly, only touches notes that need it, and is undoable. Lone
  `$…$` is left alone so real dollar signs are never disturbed.

## Settings

- **`auto`** — when `true` (default), Ctrl+V renders ChatGPT Markdown
  automatically. Set to `false` to paste everything raw. Restart Anki after
  changing.

## Note

Copied text never includes images, so pictures/diagrams in a ChatGPT reply
won't come across — paste those manually.
