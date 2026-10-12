"""Build the index at the top of each Markdown doc from its headings.

    python3 ci/toc.py README.md deploy/README.md ...           # update the indexes
    python3 ci/toc.py --check README.md deploy/README.md ...   # CI: fail if any is stale

The index sits between <!-- toc --> and <!-- /toc -->. It lists ## and ###
headings (### indented under their ##), skipping headings inside code blocks.
Links use GitHub's anchor rules, so they match what GitHub renders. If a doc has
no index yet, it's added after the first paragraph under the title.
"""
import re
import sys

START, END = "<!-- toc -->", "<!-- /toc -->"


def plain(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # [label](url) -> label
    return text.replace("`", "")


def slug(text, seen):
    s = plain(text).strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    s = s.replace(" ", "-")
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def build_index(lines):
    # Anchors are numbered across every heading level (as GitHub does), so all
    # levels go through slug(); only ## and ### are listed.
    out = ["**Contents**", ""]
    seen = {}
    in_code = False
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6}) (.+?)\s*#*\s*$", line)
        if not m:
            continue
        level, text = len(m.group(1)), m.group(2)
        anchor = slug(text, seen)
        if level in (2, 3):
            indent = "  " if level == 3 else ""
            out.append(f"{indent}- [{plain(text)}](#{anchor})")
    return [START] + out + [END]


def update(path, check):
    original = open(path, encoding="utf-8").read()
    lines = original.split("\n")

    # drop an existing index (marker block, or an old one-line "**Contents:**")
    if START in lines and END in lines:
        a, b = lines.index(START), lines.index(END)
        insert_at = a
        del lines[a:b + 1]
    else:
        old = [i for i, l in enumerate(lines) if l.startswith("**Contents:**")]
        if old:
            insert_at = old[0]
            del lines[old[0]]
        else:
            # after the first paragraph following the title
            title = next(i for i, l in enumerate(lines) if l.startswith("# "))
            i = title + 1
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            while i < len(lines) and lines[i].strip() != "":
                i += 1
            lines[i:i] = [""]          # blank line before the index; the original one follows it
            insert_at = i + 1

    body_for_index = lines[:insert_at] + lines[insert_at:]
    lines[insert_at:insert_at] = build_index(body_for_index)
    result = "\n".join(lines)

    if result == original:
        return False
    if check:
        print(f"{path}: index is out of date (run: python3 ci/toc.py {path})")
    else:
        open(path, "w", encoding="utf-8").write(result)
        print(f"{path}: index updated")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    check = "--check" in args
    files = [a for a in args if a != "--check"]
    stale = [f for f in files if update(f, check)]
    if check and stale:
        sys.exit(1)
    if check:
        print(f"{len(files)} index(es) up to date")
