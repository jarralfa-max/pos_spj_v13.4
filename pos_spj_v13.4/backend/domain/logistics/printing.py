from typing import Protocol

from backend.domain.logistics.entities import PrintJob


class PrinterGateway(Protocol):
    def submit(self, job: PrintJob, payload: str) -> None: ...
