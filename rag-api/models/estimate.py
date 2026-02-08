from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class EstimateRecord(BaseModel):
    id: int
    name: str
    material: str
    diameter_mm: float
    length_mm: float
    weight_kg: Optional[float] = None
    application: str
    grade: Optional[str] = None
    price: int
    quantity: Optional[int] = None
    unit_price: Optional[int] = None
    customer: Optional[str] = None
    notes: Optional[str] = None
    estimate_date: Optional[date] = None

    def to_embedding_text(self) -> str:
        """Embedding対象テキストを生成する。価格・数量・顧客名・日付は含めない。"""
        parts = [
            self.name,
            self.material,
            f"Φ{self.diameter_mm}×{self.length_mm}mm",
        ]
        if self.weight_kg is not None:
            parts.append(f"{self.weight_kg}kg")
        parts.append(self.application)
        if self.grade:
            parts.append(self.grade)
        if self.notes:
            parts.append(self.notes)
        return " ".join(parts)

    def to_payload(self) -> dict:
        """Qdrantに格納するpayloadを生成する。"""
        payload = self.model_dump(mode="json")
        payload.pop("id")
        payload["text"] = self.to_embedding_text()
        return payload


class ImportResult(BaseModel):
    new_count: int = 0
    updated_count: int = 0
    errors: list[str] = Field(default_factory=list)
    total_count: int = 0
