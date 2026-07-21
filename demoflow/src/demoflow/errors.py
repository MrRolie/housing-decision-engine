"""Flat error taxonomy for demoflow. Follows hde's sole precedent
(ConfigValidationError(Exception), src/hde/config.py:27): no hierarchy
unless the degenerate taxonomy genuinely forces one."""


class LoaderError(Exception):
    """Raised when a data source drifts from its pinned contract
    (404 / size / checksum / schema / degenerate cell) — never impute,
    never warn-and-continue."""


class CalibrationError(Exception):
    """Raised when a cohort roll-forward violates a calibration gate
    (reconciliation band, q out of [0,1])."""


class BasisError(Exception):
    """Raised when the active mortality basis is not the Québec basis
    before a get_qx call. Explicit if-check, never a bare assert."""
