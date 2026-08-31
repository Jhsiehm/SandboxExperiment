from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from psbx.schemas import Epoch, Question


class QuestionGenerator(ABC):
    source_name: str

    @abstractmethod
    def generate(self, epoch: Epoch, limit: int) -> Iterator[Question]:
        """Emit candidate questions. Ground truth resolved from source data."""
