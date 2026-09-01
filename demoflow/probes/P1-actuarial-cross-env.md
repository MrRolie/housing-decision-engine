# P1 — Cross-env actuarial import (RECORDED OBSERVATION)

- active_mortality() after set = ('CPM2014_combined', 'CPM-B')
- get_qx(75,'M',2035) = 0.0156  (skeleton oracle 0.0156)
- get_qx(75,'F',2035) = 0.0115  (skeleton oracle 0.0115)
- get_qx(100,'M',2035) = 0.3534 (100+ cap resolves; skeleton 0.3534)
- VERDICT: cross-env get_qx fires with QC basis.
