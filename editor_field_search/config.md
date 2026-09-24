# Editor Field Search

A find bar for the note editor (Add / Edit Current).

- **`shortcut`** — key that toggles the search box (default `Ctrl+F`). The
  search icon in the editor toolbar does the same. Press it again, or `Esc`,
  to close.
- **`mode`** — highlight colour selection:
  - `"auto"` — colour changes with the time of day (default):
    - morning (05:00–11:59) → yellow
    - afternoon (12:00–17:59) → peach
    - evening / night (18:00–04:59) → maroon
  - `"morning"` / `"afternoon"` / `"evening"` — force one colour all the time.
- **`colors`** — the background (`bg`) and text (`fg`) colours used for each
  time slot. Edit these hex values to taste.

**Usage:** open a card in the editor, click the search icon in the toolbar (or
press the shortcut), type a keyword. A compact box floats in the top-right and
shows `current / total` matches. Use the ▲ / ▼ buttons — or `Enter` /
`Shift+Enter` — to jump between matches; the editor scrolls to each one and
paints its background. Matching never changes your note content.
