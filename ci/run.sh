#!/usr/bin/env bash
# ci/run.sh "<title>" <command...>
# Runs a command, shows its output as usual, and if it fails attaches the last
# 40 lines to the error annotation, so the reason is visible on the run's
# summary page without opening the full log.
set -uo pipefail
title=$1; shift
out=$(mktemp)
"$@" 2>&1 | tee "$out"
status=${PIPESTATUS[0]}
if [ "$status" -ne 0 ]; then
  msg=$(tail -n 40 "$out" | sed -e 's/%/%25/g' -e 's/\r/%0D/g' | awk 'BEGIN{ORS="%0A"} {print}')
  echo "::error title=${title} failed::${msg}" >&2
fi
exit "$status"
