# Cheatsheet source format — `<slug>.json`

One JSON file = one cheatsheet. It is converted into search entries: every table/rows item and
every line of a `copy_lines` code block becomes ONE searchable entry. Users search in natural
language (mostly Vietnamese, translated later automatically), so each item must be a single,
self-describing command / option / key with a precise English description.

```json
{
  "title": "PostgreSQL Cheatsheet",           // "<Tool> Cheatsheet"
  "subtitle": "psql client + PostgreSQL SQL", // one short line
  "description": "One or two sentences for SEO/listing.",
  "source_url": "https://www.postgresql.org/docs/current/",
  "links": [{"label": "postgresql.org/docs", "url": "https://www.postgresql.org/docs/current/"}],
  "aliases": ["postgres", "pg"],              // extra words that identify the tool in a query (lowercase)
  "cards": [
    {
      "icon": "🔌",                            // one emoji
      "title": "Connect & Session",            // card title, unique within the sheet
      "title_accent": "Connect",               // optional: leading word of title to highlight
      "layout": "grid",                        // "grid" (default) or "wide" (full width, for big cards)
      "tip": "Optional 1-3 sentence overview shown when clicking the card header.",
      "sections": [
        {
          "label": "Connect",                  // section heading inside the card (optional but recommended)
          "kind": "table",
          "items": [
            {
              "key": "psql -h <host> -U <user> -d <db>",
              "key_style": "cmd",
              "description": "Connect to a database on a given host as a user",
              "example": "psql -h localhost -U postgres -d shop",
              "tip": "Optional longer explanation (1-2 sentences) shown in the tooltip.",
              "danger": "Optional warning for destructive/irreversible commands."
            }
          ]
        }
      ]
    }
  ]
}
```
(Real files are plain JSON — no `//` comments.)

## Section kinds
- `table` (preferred for new content): list of `items`. Optional `"columns": ["Command", "Description"]`.
- `rows`: same `items`, rendered as label → value rows (good for small reference lists, e.g. time formats).
- `tags`: `items` with only `key` (e.g. list of stored fields). Becomes ONE entry, use sparingly.
- `text`: a short note: `{"kind": "text", "content": "..."}`. One entry.
- `code`: `{"kind": "code", "lang": "bash|sql|toml|lua|js", "content": "...", "copy_lines": true}`.
  With `copy_lines: true` each non-comment line is one entry and the `# comment` / `-- comment`
  line directly above it becomes its description. Existing MySQL sheet uses this style.

## Item fields
| field | required | meaning |
|---|---|---|
| `key` | yes | The command, option, flag, key sequence, or syntax. Use `<placeholder>` for user values. |
| `key_style` | yes | `cmd` = a runnable shell/SQL command (rendered copyable); `code` = option/flag/syntax/function (`-F <sep>`, `NR`, `$regex`); `key` = one keyboard key/sequence (`dd`, `Ctrl+w v`); `keys` = several keys separated by spaces (`Ctrl R`); `plain` = anything else. |
| `description` | yes | English, ≤ ~15 words, says WHAT it does. Precise, no fluff, no trailing period needed. May use `backticks` for inline code. |
| `example` | required for ≥ 70% of items | ONE short, concrete, realistic one-liner (≤ ~100 chars) showing real usage with real-looking values. Must differ from `key`. When the key is already concrete (a flag without arguments, a fixed command), show it in a realistic context instead of dropping the example: key `--human` → `atuin history list --human --cmd-only`; key `atuin sync -f` → `atuin sync -f && atuin status`; key `NR` → `awk 'NR > 1' data.csv`. For config keys show the config line: key `style` → `style = "compact"`. Keyboard keys: show a concrete use such as `d3w` or `ci"`. |
| `tip` | optional | 1-2 sentence extra explanation / gotcha. |
| `danger` | optional | Warning text for destructive commands (delete, drop, overwrite, force). |
| `note` | optional | Tiny label rendered next to the key (e.g. `0.10+`, `GNU`). |

## Quality rules
- Accuracy first: every flag/syntax must exist in the real tool. Verify with `man <tool>`, `<tool> --help`,
  or official docs. Never invent options.
- One idea per item. Split "a / b" into two items unless they are true synonyms.
- No duplicates: the same `key` must not appear twice in the same section; avoid near-duplicates across cards.
- Group logically: 8-20 cards per sheet, 1-4 sections per card, ~5-20 items per section.
- Order from most common/basic to advanced.
- Descriptions must be distinguishable from siblings (e.g. `dd` "Delete current line" vs `dw` "Delete to start of next word").
- Plain ASCII quotes inside commands; escape properly for JSON.
