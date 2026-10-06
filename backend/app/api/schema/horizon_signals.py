from typing import Literal

from pydantic import BaseModel


class HorizonSignal(BaseModel):
    horizon: Literal[
        "next_close", "3_sessions", "5_sessions", "weeks_to_months", "years"
    ]
    signal: str
    method: str
    confidence: str
    evidence: list[str]
    invalidation_basis: str
