"""Switch the branch-specific parts of the docs between `testing` and `main`.

    python3 ci/branch_docs.py testing          # docs say: clone testing, show the testing banner
    python3 ci/branch_docs.py main             # docs say: clone main, no banner
    python3 ci/branch_docs.py --check main     # CI: fail if the docs aren't in main mode

What changes:
  - setup clone commands (git clone ... esp-soil.git /tmp/esp-soil) get `-b <branch>`,
    except a code block preceded by <!-- branch-docs: fixed -->, which is left alone
    (e.g. the "test on a spare Pi" instructions always clone testing)
  - README.md: the block between <!-- branch-banner --> and <!-- /branch-banner -->
    holds the testing banner on `testing` and is empty on `main`

Release flow (deploy/README.md, "Making a change"): run `main` before opening the
pull request into main, and `testing` after fast-forwarding testing back to main.
"""
import re
import sys

FILES = ["README.md", "deploy/README.md", "deploy/TAILSCALE.md", "dashboard/SETUP.md"]
CLONE = re.compile(r"git clone (?:-b \S+ )?(https://github\.com/gunz0blazin/esp-soil\.git /tmp/esp-soil)")
FIXED = "<!-- branch-docs: fixed -->"
B_START, B_END = "<!-- branch-banner -->", "<!-- /branch-banner -->"

BANNER = """> **This is the `testing` branch.** It holds changes that are written but not yet merged into `main`, which is what the site runs. The setup commands on this branch clone `testing`, so a test box runs exactly this code. To see what's new here, compare the branches: [`main...testing`](https://github.com/gunz0blazin/esp-soil/compare/main...testing). Once a change is checked on a test box, it goes to `main` with a pull request."""


def convert(text, branch):
    lines = text.split("\n")
    out, skip_block, in_code = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped == FIXED:
            skip_block = True
        if stripped.startswith("```"):
            if in_code:
                in_code = False
                skip_block = False      # a fixed marker covers one code block only
            else:
                in_code = True
        if in_code and not skip_block:
            line = CLONE.sub(rf"git clone -b {branch} \1", line)
        out.append(line)
    text = "\n".join(out)

    if B_START in text and B_END in text:
        a = text.index(B_START) + len(B_START)
        b = text.index(B_END)
        inner = f"\n{BANNER}\n" if branch == "testing" else "\n"
        text = text[:a] + inner + text[b:]
    return text


def main():
    args = sys.argv[1:]
    check = "--check" in args
    branches = [a for a in args if a in ("testing", "main")]
    if len(branches) != 1:
        print(__doc__)
        sys.exit(2)
    branch = branches[0]
    wrong = []
    for path in FILES:
        original = open(path, encoding="utf-8").read()
        converted = convert(original, branch)
        if converted != original:
            wrong.append(path)
            if not check:
                open(path, "w", encoding="utf-8").write(converted)
                print(f"{path}: switched to {branch}")
    if check:
        if wrong:
            print(f"Docs aren't set for '{branch}': {', '.join(wrong)}")
            print(f"Run: python3 ci/branch_docs.py {branch}, commit and push.")
            sys.exit(1)
        print(f"Docs are set for '{branch}'")
    elif not wrong:
        print(f"Docs were already set for '{branch}'")


if __name__ == "__main__":
    main()
