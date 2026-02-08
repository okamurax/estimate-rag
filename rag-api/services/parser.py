import io
from datetime import date

import pandas as pd
from pydantic import ValidationError

from models.estimate import EstimateRecord


REQUIRED_COLUMNS = {"id", "name", "material", "diameter_mm", "length_mm", "application", "price"}


def parse_file(content: bytes, filename: str) -> tuple[list[EstimateRecord], list[str]]:
    """CSV/Excelファイルをパースし、バリデーション済みレコードとエラーリストを返す。"""
    if filename.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    else:
        # UTF-8 BOMあり/なし両対応
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("utf-8")
        df = pd.read_csv(io.StringIO(text))

    # カラム名の正規化（前後の空白除去）
    df.columns = [col.strip() for col in df.columns]

    # 必須列チェック
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return [], [f"必須列が不足しています: {', '.join(sorted(missing))}"]

    records: list[EstimateRecord] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # ヘッダー行 + 0-indexed → 実際の行番号
        try:
            raw = row.where(pd.notna(row), None).to_dict()
            # 型変換
            raw["id"] = int(raw["id"])
            raw["price"] = int(raw["price"])
            raw["diameter_mm"] = float(raw["diameter_mm"])
            raw["length_mm"] = float(raw["length_mm"])
            if raw.get("weight_kg") is not None:
                raw["weight_kg"] = float(raw["weight_kg"])
            if raw.get("quantity") is not None:
                raw["quantity"] = int(raw["quantity"])
            if raw.get("unit_price") is not None:
                raw["unit_price"] = int(raw["unit_price"])
            if raw.get("estimate_date") is not None:
                val = raw["estimate_date"]
                if not isinstance(val, date):
                    raw["estimate_date"] = pd.to_datetime(str(val)).date()

            record = EstimateRecord(**raw)
            records.append(record)
        except (ValidationError, ValueError, TypeError) as e:
            errors.append(f"行{row_num}: {e}")

    return records, errors
