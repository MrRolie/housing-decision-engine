# Seat-run dispatch record — run 9 (T13b completion + T15c, successor to wf_6c14d455-b03)

- date: 2026-08-08
- dispatcher: RE-arc steering seat
- script: canonical spine mm-sdd-pipeline.js, sha256 `7e458dd8d5ae5a54c9e7c0bdc57ef749f702ca9d1629f94ea62b0782991000e1`
- args: `2026-08-08-sdd-run9-t13b-completion-t15c.args.json` (sha256 `4532deefd19c00de11212e4ba0e2d930f02ef59925020ee1c16ee0edb0fa0c98`); task 1 =
  T13b completion carrying the seat ruling (read-only fetch of published 98-10-0231-01
  cells AUTHORIZED — the seat's original P2-citation was an ERROR, owned in the run-8
  record) + fresh review of the inherited diff; task 2 = T15c bytes unchanged (never ran);
  wrapper sha256 `02797cfde157cd7724de9d9a5efb878cf2b9e13f7615dcba8c1b3a529e04155f`
- models: opus/opus; load_bearing: T13b-completion; money_path: false; WAVE-0 vacuous
- preconditions: T13b delivery inherited UNCOMMITTED (191+274 at halt); worktree unoccupied
- run id: wf_d83d9d90-c1c (dispatched 2026-08-08)
- outcome (run close 2026-08-08): 2/2 APPROVE (T13b-completion: 1 fix round; T15c: 0),
  verify PASS 191+285. The two external anchors verified genuinely external (reviewer
  re-fetched all 12 cells live with independently-resolved member ids: 0 mismatches;
  releaseTime 2022-09-21 — no restatement on the cells that matter; the WDS zip-order trap
  was HIT INDEPENDENTLY by the reviewer, confirming coordinate-keying is load-bearing).
  10/10 anchor mutants red. F-A ruled correct (the retired 4th decimals were self-referential
  — the DIV record publishes 3dp). DIV F2 CLOSED end-to-end minus one disclosed residual
  (the 850MB raw member's live hash unverified — mutation-verified only). CARRIES → charter:
  ownership strict-key misdirecting message (one-line fix, next run); headship
  multiplicand_note + ownership as_of/Anchor-typing at the first pipeline consumer (T25/26);
  audit remaining pullers for zip-order pairing; mutation-battery hygiene
  PYTHONDONTWRITEBYTECODE=1 (stale-pyc same-second trap, measured — mm-spine harvest
  candidate). T13b + T15c landed; **DIV findings F1/F2/F3 ALL CLOSED; loader tranche
  COMPLETE at 191+285.**
