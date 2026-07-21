"""P1 — cross-env actuarial import. Runs live, records an observation note.
Sets the Québec basis and pulls q_x(75, M/F, 2035); compares to skeleton spot
values (M75=0.0156, F75=0.0115)."""
from pathlib import Path

from mcp_server.engine.mortality import active_mortality, get_qx, set_active_mortality

OUT = Path(__file__).resolve().parent / "P1-actuarial-cross-env.md"


def main() -> None:
    set_active_mortality("CPM2014_combined", "CPM-B")
    base, scale = active_mortality()
    m75 = get_qx(75, "M", 2035)
    f75 = get_qx(75, "F", 2035)
    m100 = get_qx(100, "M", 2035)
    lines = [
        "# P1 — Cross-env actuarial import (RECORDED OBSERVATION)",
        "",
        f"- active_mortality() after set = ({base!r}, {scale!r})",
        f"- get_qx(75,'M',2035) = {m75:.4f}  (skeleton oracle 0.0156)",
        f"- get_qx(75,'F',2035) = {f75:.4f}  (skeleton oracle 0.0115)",
        f"- get_qx(100,'M',2035) = {m100:.4f} (100+ cap resolves; skeleton 0.3534)",
        "- VERDICT: cross-env get_qx fires with QC basis." ,
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
