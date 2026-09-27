"""Trích xuất dữ liệu cheatsheet từ các file HTML gốc → db/seed.sql (+ data/*.json để soát).

Mỗi file có cấu trúc riêng nên có parser riêng; parser dựng cây card → section → item,
sau đó `flatten()` trải phẳng thành `entries` (đơn vị tìm kiếm) + `layout` (để render web).
Code block có thể copy từng dòng được tách thành 1 entry / lệnh, comment đứng trước làm mô tả.
Bản dịch tiếng Việt (data/translations.vi.json, sinh bởi cheatsheet.translate) được ghép vào
entry qua content_hash → thêm description_vi + embed_text_vi (vector thứ hai cho câu hỏi tiếng Việt).

    uv run -m cheatsheet.extract            # đọc *.html ở thư mục gốc
"""

import hashlib
import json
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

from cheatsheet.config import ROOT

# Từ khoá để search_entries() tự nhận diện sheet trong câu hỏi (ngoài slug + tên tool).
ALIASES = {"neovim": ["nvim", "vim"]}
TRANSLATIONS = ROOT / "data" / "translations.vi.json"


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def load_translations():
    """{content_hash: {"vi": mô tả, "q": [cụm từ tìm kiếm]}} — rỗng nếu chưa dịch."""
    return json.loads(TRANSLATIONS.read_text(encoding="utf-8")) if TRANSLATIONS.exists() else {}


# ---------------------------------------------------------------- helpers

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def inline(el):
    """HTML inline → text, <code>/<kbd> thành `backtick`."""
    if el is None:
        return None
    out = []
    for node in el.children:
        if isinstance(node, NavigableString):
            out.append(str(node))
        elif node.name in ("code", "kbd"):
            out.append(f"`{node.get_text()}`")
        else:
            out.append(inline(node))
    return clean("".join(out)) or None


def new_section(label=None, kind="table", **kw):
    return {"label": label, "kind": kind, "lang": None, "content": None,
            "copy_lines": False, "columns": None, "items": [], **kw}


def new_item(key, key_style="plain", description=None, **kw):
    return {"key": key, "key_style": key_style, "description": description, **kw}


def links_of(el):
    return [{"label": clean(a.get_text()), "url": a["href"]}
            for a in (el.find_all("a", href=True) if el else [])]


def canonical(soup):
    link = soup.find("link", rel="canonical")
    return link["href"] if link else None


def meta_desc(soup):
    m = soup.find("meta", attrs={"name": "description"})
    return m["content"] if m else None


# ---------------------------------------------------------------- atuin-style
# card > .card-header(h2) + .card-body chứa .section-label / table / pre / .row

def atuin_key(td):
    if td.select_one("kbd.copyable"):
        return new_item(clean(td.get_text()), "cmd")
    if td.find("kbd"):
        return new_item(clean(td.get_text()), "keys")
    mode = td.select_one("span.mode")
    if mode:
        variant = next((c.removeprefix("mode-").removeprefix("search-")
                        for c in mode["class"] if c != "mode"), None)
        small = td.find("small")
        return new_item(clean(mode.get_text()), "mode", variant=variant,
                        note=clean(small.get_text()) if small else None)
    if td.find("code"):
        return new_item(clean(td.get_text()), "code")
    return new_item(clean(td.get_text()))


def atuin_title(h2):
    small = h2.find("small")
    note = clean(small.extract().get_text()) if small else None
    accent = h2.find("span")
    return clean(h2.get_text()), (clean(accent.get_text()) if accent else None), note


def parse_atuin(soup):
    header = soup.find("header")
    logo = header.find("img")
    sheet = {
        "title": clean(header.find("h1").get_text()),
        "subtitle": clean(header.find("p").get_text()),
        "badge": clean(header.select_one(".badge").get_text()) if header.select_one(".badge") else None,
        "logo": logo["src"] if logo else None,
        "links": links_of(soup.select_one("footer p")),
        "meta": {},
        "cards": [],
    }

    for card_el in soup.select("main .card"):
        head = card_el.select_one(":scope > .card-header")
        title, accent, note = atuin_title(head.find("h2"))
        body = card_el.select_one(":scope > .card-body")
        card = {
            "icon": clean(head.select_one(".icon").get_text()) if head.select_one(".icon") else None,
            "title": title, "title_accent": accent, "title_note": note,
            "color": None, "tip": None,
            "layout": "wide" if "grid-wide" in card_el.parent.get("class", []) else "grid",
            "body_cols": 2 if body.select_one(":scope > .grid-wide") else 1,
            "sections": [],
        }
        state = {"label": None, "cur": None}

        def push(sec):
            card["sections"].append(sec)
            state["label"], state["cur"] = None, sec
            return sec

        def walk(parent):
            for el in parent.children:
                if not isinstance(el, Tag):
                    continue
                cls = el.get("class", [])
                if "section-label" in cls:
                    state["label"], state["cur"] = clean(el.get_text()), None
                elif "card-header" in cls:  # tiêu đề phụ lồng trong card
                    t, _, n = atuin_title(el.find("h2"))
                    state["label"], state["cur"] = f"{t} {n}" if n else t, None
                elif el.name == "table":
                    ths = [clean(th.get_text()) for th in el.select("thead th")]
                    sec = push(new_section(state["label"], columns=ths or None))
                    for tr in el.select("tr"):
                        tds = tr.find_all("td")
                        if not tds:
                            continue
                        it = atuin_key(tds[0])
                        it["description"] = inline(tds[1]) if len(tds) > 1 else None
                        sec["items"].append(it)
                elif "pre-wrap" in cls or el.name == "pre":
                    pre = el if el.name == "pre" else el.find("pre")
                    push(new_section(state["label"], "code",
                                     lang="toml" if pre.select_one(".key") else "bash",
                                     content=pre.get_text().rstrip(),
                                     copy_lines=bool(pre.select_one(".copyable-line"))))
                elif "row" in cls:
                    tags = el.select("span.tag")
                    kind = "tags" if tags else "rows"
                    cur = state["cur"]
                    sec = cur if cur and cur["kind"] == kind and state["label"] is None \
                        else push(new_section(state["label"], kind))
                    if tags:
                        sec["items"] += [new_item(clean(t.get_text())) for t in tags]
                    else:
                        sec["items"].append(new_item(clean(el.select_one(".label").get_text()), "plain",
                                                     inline(el.select_one(".right"))))
                else:
                    walk(el)

        walk(body)
        sheet["cards"].append(card)
    return sheet


# ---------------------------------------------------------------- neovim-style
# card > .card-header[data-tip] + table; tr[data-tip|data-example|data-danger]

def parse_neovim(soup):
    main = soup.find("main")
    legend = []
    for span in main.select(".legend > span"):
        badge = span.select_one(".badge")
        if not badge:  # "Custom binding" — tính năng sửa phím của trang gốc, không port
            continue
        legend.append({
            "badge": clean(badge.get_text()) if badge else None,
            "badge_class": next((c for c in badge["class"] if c != "badge"), None) if badge else None,
            "label": clean(span.get_text().replace(badge.get_text(), "", 1) if badge else span.get_text()),
            "tip": span.get("data-tip"),
        })
    sheet = {
        "title": clean(main.find("h1").get_text()),
        "subtitle": clean(main.select_one("p.subtitle").get_text()),
        "badge": None, "logo": None,
        "links": [l for l in links_of(soup.find("footer")) if "vigodlabs" not in l["url"]][:1],
        "meta": {"legend": legend},
        "cards": [],
    }
    for card_el in main.select("#grid > .card"):
        head = card_el.select_one(".card-header")
        colors = [c for c in head["class"] if c != "card-header"]
        sec = new_section()
        for tr in card_el.select("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            small = tds[0].find("span")
            note = clean(small.extract().get_text()) if small else None
            sec["items"].append(new_item(
                clean(tds[0].get_text()), "key", inline(tds[1]) if len(tds) > 1 else None,
                note=note, tip=tr.get("data-tip"), example=tr.get("data-example"),
                danger=tr.get("data-danger")))
        sheet["cards"].append({
            "icon": None, "title": clean(head.get_text()), "title_accent": None,
            "title_note": None, "color": colors[0] if colors else None,
            "tip": head.get("data-tip"), "layout": "grid", "body_cols": 1,
            "sections": [sec],
        })
    return sheet


# ---------------------------------------------------------------- devhints-style
# section.h3-section > h3 + .body chứa h4 / pre.language-* / p

def parse_devhints(soup):
    h1 = soup.select_one("h1 .MainHeading__title") or soup.find("h1")
    sheet = {
        "title": f"{clean(h1.get_text())} Cheatsheet",
        "subtitle": meta_desc(soup),
        "badge": None, "logo": None,
        "links": [], "meta": {}, "cards": [],
    }
    for sec_el in soup.select("main section.h3-section"):
        card = {"icon": None, "title": clean(sec_el.find("h3").get_text()), "title_accent": None,
                "title_note": None, "color": None, "tip": None, "layout": "grid",
                "body_cols": 1, "sections": []}
        label = None
        for el in sec_el.select_one(".body").children:
            if not isinstance(el, Tag):
                continue
            if el.name == "h4":
                label = clean(el.get_text())
            elif el.name == "pre":
                lang = next((c.removeprefix("language-") for c in el.get("class", [])
                             if c.startswith("language-")), None)
                card["sections"].append(new_section(label, "code", lang=lang,
                                                    content=el.get_text().rstrip(),
                                                    copy_lines=True))
                label = None
            elif el.name == "p":
                card["sections"].append(new_section(label, "text", content=inline(el)))
                label = None
        sheet["cards"].append(card)
    return sheet


# ---------------------------------------------------------------- flatten → entries

KIND_BY_STYLE = {"cmd": "command", "keys": "shortcut", "key": "shortcut",
                 "code": "option", "mode": "option", "plain": "option"}
PROMPT_RE = re.compile(r"^(\$|mysql>)\s+")


def split_code(content, lang):
    """Code block → [{command, description, raw, prompt}], mỗi phần tử là một lệnh.

    Comment/dòng trống đứng trước gắn vào lệnh ngay sau (làm mô tả); dòng thụt lề là
    phần nối tiếp của lệnh trước; comment cuối dòng (`cmd  # note`) cũng thành mô tả.
    """
    com = "--" if lang == "sql" else "#"
    trail_re = re.compile(r"\s" + re.escape(com) + r"\s+(.*)$")
    out, pending = [], []
    for line in content.split("\n"):
        s = line.strip()
        if not s or s.startswith(com):
            pending.append(line)
        elif line[:1].isspace() and out and not pending:
            out[-1]["raw"].append(line)
            out[-1]["lines"].append(line)
        else:
            out.append({"raw": pending + [line], "lines": [line],
                        "comments": [p.strip().lstrip(com + " ").strip() for p in pending if p.strip()]})
            pending = []
    if pending and out:
        out[-1]["raw"] += pending
    result = []
    for e in out:
        first = e["lines"][0]
        m = trail_re.search(first)
        trail = m.group(1).strip() if m else None
        if m:
            first = first[:m.start()]
        p = PROMPT_RE.match(first)
        prompt = p.group(1) if p else None
        first = first[p.end():] if p else first
        command = "\n".join([first.rstrip()] + e["lines"][1:]).strip()
        desc = " — ".join(e["comments"] + ([trail] if trail else [])) or None
        result.append({"command": command, "description": desc,
                       "raw": "\n".join(e["raw"]), "prompt": prompt})
    return result


def tool_name(title):
    return re.sub(r"\s*cheat ?sheet\s*$", "", title, flags=re.I)


def flatten(sheet, translations):
    tool = tool_name(sheet["title"])
    layout, entries = [], []
    for cpos, card in enumerate(sheet["cards"], 1):
        card_ctx = f"{card['title']} {card['title_note']}" if card.get("title_note") else card["title"]
        lcard = {k: v for k, v in card.items() if k != "sections" and v is not None}
        lcard["sections"] = []
        layout.append(lcard)
        for spos, sec in enumerate(card["sections"], 1):
            lcard["sections"].append({k: sec[k] for k in ("label", "kind", "lang", "columns", "copy_lines")
                                      if sec.get(k) is not None})
            base = {"card_pos": cpos, "section_pos": spos, "card": card_ctx, "section": sec["label"],
                    "lang": sec.get("lang")}
            rows = []
            if sec["kind"] in ("table", "rows"):
                for it in sec["items"]:
                    rows.append({"kind": KIND_BY_STYLE.get(it["key_style"], "option"),
                                 "command": it["key"], "description": it.get("description"),
                                 "details": it.get("tip"), "example": it.get("example"),
                                 "danger": it.get("danger"),
                                 "display": {k: it[k] for k in ("key_style", "variant", "note") if it.get(k)}})
            elif sec["kind"] == "tags":
                tags = [it["key"] for it in sec["items"]]
                rows.append({"kind": "note", "command": None, "description": ", ".join(tags),
                             "display": {"tags": tags}})
            elif sec["kind"] == "text":
                rows.append({"kind": "note", "command": None, "description": sec["content"], "display": {}})
            elif sec["kind"] == "code" and sec.get("copy_lines"):
                for c in split_code(sec["content"], sec.get("lang")):
                    rows.append({"kind": "command", "command": c["command"], "description": c["description"],
                                 "display": {"raw": c["raw"], **({"prompt": c["prompt"]} if c["prompt"] else {})}})
            elif sec["kind"] == "code":
                rows.append({"kind": "snippet", "command": sec["content"], "description": None,
                             "display": {"raw": sec["content"]}})
            for pos, r in enumerate(rows, 1):
                e = {"details": None, "example": None, "danger": None, **base, **r, "position": pos}
                ctx = " › ".join(x for x in (tool, card_ctx, sec["label"]) if x)
                e["embed_text"] = "\n".join(x for x in (ctx, e["command"], e["description"], e["details"]) if x)
                e["content_hash"] = sha256(e["embed_text"])
                vi = translations.get(e["content_hash"])
                e["description_vi"] = vi["vi"] if vi else None
                e["embed_text_vi"] = "\n".join(x for x in (ctx, e["command"], vi["vi"], *vi["q"]) if x) if vi else None
                e["content_hash_vi"] = sha256(e["embed_text_vi"]) if vi else None
                entries.append(e)
    aliases = sorted({sheet["slug"], tool.lower(), *ALIASES.get(sheet["slug"], [])})
    return layout, entries, aliases


# ---------------------------------------------------------------- SQL output

def detect(soup):
    if soup.select_one("main section.h3-section"):
        return parse_devhints
    if soup.select_one("#grid .card-header[data-tip]"):
        return parse_neovim
    if soup.select_one("main .card .card-body"):
        return parse_atuin
    return None


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, tuple):  # text[]
        return "ARRAY[" + ", ".join(lit(x) for x in v) + "]::text[]"
    if isinstance(v, (list, dict)):
        return lit(json.dumps(v, ensure_ascii=False)) + "::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def insert(table, row):
    cols = ", ".join(row)
    vals = ", ".join(lit(v) for v in row.values())
    return f"INSERT INTO {table} ({cols}) VALUES ({vals});"


SHEET_COLS = ("slug", "title", "subtitle", "badge", "description", "logo", "source_url", "links", "meta")
ENTRY_COLS = ("card_pos", "section_pos", "position", "card", "section", "kind", "command", "description",
              "details", "example", "danger", "lang", "display", "embed_text", "content_hash",
              "description_vi", "embed_text_vi", "content_hash_vi")


def to_sql(sheets):
    out = ["-- Generated by cheatsheet/extract.py — đừng sửa tay, chạy lại script.",
           "-- Không đụng tới bảng embeddings: vector cũ tự khớp lại qua content_hash.",
           "BEGIN;", "TRUNCATE entries, sheets RESTART IDENTITY CASCADE;"]
    n_entries = 0
    for sid, sh in enumerate(sheets, 1):
        out.append(f"\n-- {sh['slug']}")
        out.append(insert("sheets", {"id": sid, **{k: sh[k] for k in SHEET_COLS},
                                     "aliases": tuple(sh["aliases"]), "layout": sh["layout"]}))
        for e in sh["entries"]:
            out.append(insert("entries", {"sheet_id": sid, **{k: e[k] for k in ENTRY_COLS}}))
        n_entries += len(sh["entries"])
    out.append(f"DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('sheets', 'id'), {max(len(sheets), 1)}); END $$;")
    out.append("COMMIT;")
    return "\n".join(out) + "\n", n_entries


def main():
    sheets, translations = [], load_translations()
    (ROOT / "data").mkdir(exist_ok=True)
    for path in sorted(ROOT.glob("*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        parser = detect(soup)
        if not parser:
            print(f"skip {path.name}: không nhận ra cấu trúc", file=sys.stderr)
            continue
        sheet = {"slug": path.stem, "description": meta_desc(soup),
                 "source_url": canonical(soup), **parser(soup)}
        sheet["layout"], sheet["entries"], sheet["aliases"] = flatten(sheet, translations)
        del sheet["cards"]
        sheets.append(sheet)
        (ROOT / "data" / f"{path.stem}.json").write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
        kinds = {}
        for e in sheet["entries"]:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        print(f"{path.name:14} [{parser.__name__}] cards={len(sheet['layout'])} "
              f"entries={len(sheet['entries'])} {kinds}")
    sql, n = to_sql(sheets)
    (ROOT / "db" / "seed.sql").write_text(sql, encoding="utf-8")
    n_vi = sum(1 for sh in sheets for e in sh["entries"] if e["description_vi"])
    print(f"→ db/seed.sql ({len(sheets)} sheets, {n} entries, {n_vi} có bản dịch tiếng Việt)")


if __name__ == "__main__":
    main()
