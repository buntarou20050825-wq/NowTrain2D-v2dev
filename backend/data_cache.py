# backend/data_cache.py
from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List


class DataCache:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.railways: List[Dict[str, Any]] = []
        self.stations: List[Dict[str, Any]] = []
        self.coordinates: Dict[str, Any] = {}

        # TODO (MS6): パフォーマンス最適化
        # self.railways_by_id: Dict[str, Dict[str, Any]] = {}
        # self.stations_by_id: Dict[str, Dict[str, Any]] = {}

    def load_all(self) -> None:
        self.railways = self._load_json("railways.json")
        self.stations = self._load_json("stations.json")
        self.coordinates = self._load_json("coordinates.json")

    def _load_json(self, filename: str):
        path = self.data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {path}")

        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # JSON が壊れている場合、起動時にここで落ちます。
            # 基本的な対処は「frontend/public の元データから再コピー」です。
            raise RuntimeError(f"Invalid JSON in {path}: {e}")
