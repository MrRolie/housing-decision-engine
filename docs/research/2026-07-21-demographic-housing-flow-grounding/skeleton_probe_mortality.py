"""Walking-skeleton boundary probe: fire actuarial-system's mortality engine
live with the Quebec CIA CPM2014 basis + CPM-B improvement scale, calendar
year 2035, ages 75-100, both genders. Run from inside the actuarial-system
repo via `uv run python` so the package + its uv-managed deps resolve.
"""
import json
import sys

from mcp_server.engine import mortality

# Set the Quebec/CIA basis explicitly -- the engine defaults to US RP2014+MP2021
# (per the mortality provider's documented gotcha). CPM2014_combined is the general
# (not sector-split public/private) CIA table; CPM-B is the sex-specific
# improvement scale.
mortality.set_active_mortality("CPM2014_combined", "CPM-B")
active = mortality.active_mortality()
print(f"active_mortality() -> {active}", file=sys.stderr)
assert active == ("CPM2014_combined", "CPM-B"), "basis did not stick"

CALENDAR_YEAR = 2035
ages = list(range(75, 101))

out = {"active_basis": active, "calendar_year": CALENDAR_YEAR, "qx": {"M": {}, "F": {}}}
for gender in ("M", "F"):
    for age in ages:
        qx = mortality.get_qx(age, gender, CALENDAR_YEAR)
        out["qx"][gender][age] = qx

print(json.dumps(out, indent=2))
