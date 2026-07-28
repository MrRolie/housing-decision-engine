"""Shared gate helpers for tests/test_probe_p3..p5.py.

Imported relatively (`from ._probe_asserts import …`) — tests/ IS a package.

DELIBERATELY NOT SHARED with test_probe_p1/p2: p2's `_recorded_failure_type` matches
a DIFFERENT marker literal (`LIVE PULL FAILED:`, which is what run_p2.py emits) and
its `NETWORK_EXCEPTIONS` is a 17-member set MISSING `NoResponse`. Adopting the set
below for p2 would WIDEN what counts as an excusable failure there — directionally
the cheap all-clear. p2 keeps its own copies.
"""

import re
import urllib.request

# Exception types that may legitimately excuse a recorded failure. Anything outside
# this set is a code/structural fault and must FAIL even when the source is
# unreachable — an outage must never launder a real bug into a green-looking skip.
# EXACTLY the 18-member set p3/p4/p5 already shared (they differed only in line
# formatting). Adding a member here widens every probe's excusable set at once.
NETWORK_EXCEPTIONS = frozenset({
    "URLError", "HTTPError", "ContentTooShortError", "TimeoutError", "timeout",
    "socket.timeout", "gaierror", "herror", "ConnectionError", "ConnectionResetError",
    "ConnectionRefusedError", "ConnectionAbortedError", "RemoteDisconnected",
    "IncompleteRead", "BadStatusLine", "SSLError", "SSLEOFError",
    "NoResponse",  # the probes' own marker for "nothing answered at all"
})


def token(text: str, name: str) -> str | None:
    """The value of a backtick-delimited `NAME: value` token, or None if absent.

    Prefers the code span, which is how every probe emits its DECISION tokens. A
    greedy to-end-of-line parse would swallow anything trailing the closing backtick,
    so an unresolved token followed by leftover prose could read as resolved — the
    parser must not be the thing that launders a placeholder into an answer.
    """
    span = re.search(rf"`{re.escape(name)}:\s*(.*?)`", text)
    if span:
        return span.group(1).strip()
    found = re.search(rf"{re.escape(name)}:\s*(.*)", text)
    return found.group(1).strip().rstrip("`").strip() if found else None


def recorded_failure_type(text: str) -> str | None:
    """The exception TYPE a note recorded for a `LIVE PROBE FAILED:` marker, or None."""
    found = re.search(r"LIVE PROBE FAILED:\s*([A-Za-z_][A-Za-z0-9_.]*)\s*:", text)
    return found.group(1) if found else None


def source_reachable(
    url: str,
    *,
    timeout: float,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    ok_statuses: tuple[int, ...] = (200,),
) -> bool:
    """Cheap liveness probe. Any exception means unreachable.

    `method` is an EXPLICIT parameter, never inferred: the reachability probe must
    use the SAME HTTP method as the real call it stands in for. `getCubeMetadata`
    rejects GET, so a GET-based check reports 'unreachable' against a perfectly
    healthy service and every recorded failure then launders itself into a skip —
    the cheap all-clear these gates exist to prevent (caught for real once: with a
    GET probe, p3's fail-when-reachable branch was dead code). Each caller keeps its
    own thin wrapper naming its method, url, timeout, payload and accepted statuses;
    those wrappers, not this function, are the enforcement artifact.
    """
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in ok_statuses
    except Exception:
        return False
