from pathlib import Path

import demoflow
from demoflow.errors import BasisError, CalibrationError, LoaderError

DATA = Path(__file__).resolve().parent.parent / "data"


def test_error_classes_are_flat_exceptions():
    for cls in (LoaderError, CalibrationError, BasisError):
        assert issubclass(cls, Exception)
        assert cls.__bases__ == (Exception,)


def test_public_api_reexports_errors():
    assert demoflow.LoaderError is LoaderError


def test_committed_workbooks_present():
    names = {p.name for p in DATA.glob("*.xlsx")}
    assert names == {
        "pop-as-rmr-base.xlsx", "pop-as-ra-base.xlsx", "pop-as-qc-base.xlsx",
        "compo-rmr-base.xlsx", "compo-ra-base.xlsx",
    }
