"""Convert the Doubao voice Excel into app/data/voices.json.

Run with a Python that has pandas + openpyxl (e.g. Anaconda):
    python backend/scripts/build_voices.py
Only needed when the Excel changes — the backend reads the committed JSON.
"""
import json
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, "..", "reference", "豆包2.0音色表.xlsx")
OUT = os.path.join(HERE, "..", "app", "data", "voices.json")


def gender_of(voice_type: str) -> str:
    if "female" in voice_type:
        return "female"
    if "male" in voice_type:
        return "male"
    return "unknown"


def split_list(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"[、,，/]", str(s)) if x.strip()]


def main() -> None:
    df = pd.read_excel(XLSX, sheet_name="Sheet1").fillna("")
    voices = []
    for _, r in df.iterrows():
        vt = str(r.get("voice_type", "")).strip()
        if not vt:
            continue
        voices.append(
            {
                "id": vt,
                "name": str(r.get("音色名称", "")).strip(),
                "scene": str(r.get("场景", "")).strip(),
                "gender": gender_of(vt),
                "langDialect": str(r.get("语种/方言", "")).strip(),
                "capabilities": split_list(r.get("支持能力", "")),
                "tags": split_list(r.get("特殊标签", "")),
                "provider": "doubao",
            }
        )

    data = {
        "provider": "doubao",
        "providerLabel": "豆包",
        "count": len(voices),
        "voices": voices,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT}  ({len(voices)} voices)")


if __name__ == "__main__":
    main()
