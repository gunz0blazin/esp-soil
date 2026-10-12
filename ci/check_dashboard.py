"""Sanity checks for dashboard/ that promtool and compose don't cover.

- every file in prometheus/targets/ is a list of {targets: [host:port], labels: {board}}
- no duplicate addresses or board names
- the dashboard JSON parses, and the home dashboard path in docker-compose.yml exists
"""
import json, pathlib, re, sys
import yaml

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dashboard")
errors = []

seen_addr, seen_board = set(), set()
target_files = sorted((root / "prometheus" / "targets").glob("*.yml"))
if not target_files:
    errors.append("no files in prometheus/targets/")
for f in target_files:
    groups = yaml.safe_load(f.read_text()) or []
    if not isinstance(groups, list):
        errors.append(f"{f}: must be a list of target groups"); continue
    for i, g in enumerate(groups):
        where = f"{f.name} entry {i + 1}"
        tg = g.get("targets") if isinstance(g, dict) else None
        if not tg or not all(isinstance(t, str) and re.fullmatch(r"[\w.\-]+:\d+", t) for t in tg):
            errors.append(f"{where}: targets must be a list of host:port strings")
            continue
        board = (g.get("labels") or {}).get("board")
        if not board:
            errors.append(f"{where}: missing labels.board")
        for t in tg:
            if t in seen_addr: errors.append(f"{where}: duplicate address {t}")
            seen_addr.add(t)
        if board in seen_board: errors.append(f"{where}: duplicate board {board}")
        seen_board.add(board)

dash_dir = root / "grafana" / "dashboards"
for f in sorted(dash_dir.glob("*.json")):
    try:
        d = json.loads(f.read_text())
        assert d.get("uid") and d.get("title"), "needs uid and title"
    except Exception as e:
        errors.append(f"{f}: {e}")

compose = (root / "docker-compose.yml").read_text()
m = re.search(r"GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/(\S+)", compose)
if m and not (dash_dir / m.group(1)).exists():
    errors.append(f"home dashboard {m.group(1)} not found in grafana/dashboards/")

print(f"{len(target_files)} target file(s), {len(seen_addr)} stake(s), "
      f"{len(list(dash_dir.glob('*.json')))} dashboard(s)")
if errors:
    print("\n".join("ERROR: " + e for e in errors)); sys.exit(1)
print("dashboard checks passed")
