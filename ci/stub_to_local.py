"""Turn firmware/ha-stub.example.yaml into a local build that includes
../common.yaml instead of fetching main from GitHub, so CI checks the stub
against the common.yaml in this commit."""
import re, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
s, n = re.subn(r"packages:\n  stake:\n(    .*\n)+", "packages:\n  stake: !include ../common.yaml\n", s)
assert n == 1, "couldn't find the remote packages block in the stub"
open(dst, "w").write(s)
print("wrote", dst)
