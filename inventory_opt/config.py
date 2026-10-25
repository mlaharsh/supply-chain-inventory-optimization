"""Project-wide configuration and path helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

# The portfolio dataset covers two complete fiscal years. Keeping the horizon
# fixed makes every report, screenshot, and test reproducible.
DEFAULT_START_DATE = date(2024, 10, 1)
DEFAULT_END_DATE = date(2026, 9, 30)
DEFAULT_SEED = 42
DEFAULT_PRODUCT_COUNT = 60
DEFAULT_SUPPLIER_COUNT = 12

# Cycle service levels required by the brief.
SERVICE_LEVELS: tuple[float, float, float] = (0.90, 0.95, 0.99)

ABC_A_THRESHOLD = 0.80
ABC_B_THRESHOLD = 0.95
XYZ_X_THRESHOLD = 0.50
XYZ_Y_THRESHOLD = 1.00

RISK_HIGH_THRESHOLD = 0.50
RISK_MEDIUM_THRESHOLD = 0.25
RISK_WATCH_THRESHOLD = 0.10


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved project directories, independent of the current working dir."""

    root: Path
    raw: Path
    outputs: Path
    analytics: Path
    tableau: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> "ProjectPaths":
        base = (root or Path(__file__).resolve().parent.parent).resolve()
        outputs = base / "outputs"
        return cls(
            root=base,
            raw=base / "data" / "raw",
            outputs=outputs,
            analytics=outputs / "analytics",
            tableau=outputs / "tableau",
        )

    def ensure(self) -> None:
        """Create all generated-data directories."""

        for directory in (self.raw, self.outputs, self.analytics, self.tableau):
            directory.mkdir(parents=True, exist_ok=True)
