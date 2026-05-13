from __future__ import annotations

from dataclasses import dataclass


class OperationCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    fraction: float
    current_file: str | None = None
    bytes_downloaded: int = 0
    bytes_total: int = 0
    current_step: int = 0
    total_steps: int = 0

    @property
    def percent(self) -> float:
        return max(0.0, min(100.0, self.fraction * 100.0))


class WeightedProgress:
    def __init__(self, emit: callable | None = None, cancel_check: callable | None = None) -> None:
        self.emit = emit
        self.cancel_check = cancel_check

    def check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise OperationCancelled("Cancelled by user.")

    def step(
        self,
        phase: str,
        message: str,
        step_index: int,
        total_steps: int,
        step_fraction: float = 0.0,
        current_file: str | None = None,
        bytes_downloaded: int = 0,
        bytes_total: int = 0,
    ) -> None:
        self.check_cancelled()
        safe_total = max(total_steps, 1)
        safe_step = max(step_index, 0)
        local = max(0.0, min(1.0, step_fraction))
        fraction = min(1.0, (safe_step + local) / safe_total)
        event = ProgressEvent(
            phase=phase,
            message=message,
            fraction=fraction,
            current_file=current_file,
            bytes_downloaded=bytes_downloaded,
            bytes_total=bytes_total,
            current_step=min(safe_step + 1, safe_total),
            total_steps=safe_total,
        )
        if self.emit:
            self.emit(event)
