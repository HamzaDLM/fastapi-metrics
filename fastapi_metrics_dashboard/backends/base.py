from abc import ABC, abstractmethod
from typing import Dict, Any


class MetricsStore(ABC):
    @abstractmethod
    async def record_request_metrics(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        pass

    @abstractmethod
    async def record_system_metrics(self) -> None:
        pass

    @abstractmethod
    async def get_metrics(self, ts_from: int, ts_to: int) -> Dict[str, Any]:
        pass
