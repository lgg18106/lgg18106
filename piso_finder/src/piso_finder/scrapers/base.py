from __future__ import annotations

import time
import urllib.robotparser
from abc import ABC, abstractmethod
from typing import Iterable

import requests

from ..models import Property


USER_AGENT = (
    "piso_finder/0.1 (personal use; respects robots.txt; "
    "contact: user@example.com)"
)


class BaseScraper(ABC):
    BASE_URL: str = ""
    NAME: str = ""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.delay = cfg.get("delay_seconds", 8)
        self.max_pages = cfg.get("max_pages", 3)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "es-ES,es;q=0.9",
            }
        )

    def robots_allows(self, path: str) -> bool:
        if not self.BASE_URL:
            return True
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{self.BASE_URL.rstrip('/')}/robots.txt")
        try:
            rp.read()
        except Exception:
            return True
        return rp.can_fetch(USER_AGENT, self.BASE_URL.rstrip("/") + path)

    def sleep(self) -> None:
        time.sleep(self.delay)

    def get(self, url: str, **kwargs) -> requests.Response:
        self.sleep()
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    def search(self, criteria: dict, zones: dict) -> Iterable[Property]:
        """Yield Property objects for the configured zones and criteria."""
        raise NotImplementedError
