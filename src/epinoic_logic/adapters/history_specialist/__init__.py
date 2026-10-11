from .parser import HistorySpecialistAdapter  # noqa: F401
from .structural import structural_checks  # noqa: F401
from . import fixtures  # noqa: F401

try:  # register with the adapters registry when it is available
    from ..base import register as _register
    _register(HistorySpecialistAdapter())
except Exception:  # pragma: no cover - registry absent or already holds this id
    pass
