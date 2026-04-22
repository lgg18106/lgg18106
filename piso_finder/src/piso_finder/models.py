from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Property:
    source: str
    url: str
    title: str
    price: float
    municipio: str
    barrio: Optional[str] = None
    rooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_m2: Optional[float] = None
    has_garage: bool = False
    has_pool: bool = False
    has_elevator: bool = False
    has_terrace: bool = False
    is_exterior: bool = False
    orientation: Optional[str] = None
    is_new_build: bool = False
    energy_cert: Optional[str] = None
    state_flags: list[str] = field(default_factory=list)
    description: Optional[str] = None
    raw: dict = field(default_factory=dict)
    score: float = 0.0

    @property
    def price_per_m2(self) -> Optional[float]:
        if self.area_m2 and self.area_m2 > 0:
            return round(self.price / self.area_m2, 2)
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price_per_m2"] = self.price_per_m2
        d.pop("raw", None)
        return d
