"""קריאה ופרסור של אקסל הלקוחות.

מבנה צפוי (כותרות בעברית):
מספר הזמנה | תאריך | שם פרטי | שם משפחה | טלפון | מייל | אירוע | סכום | סכום לפי מטבע דיפולטיבי | צורת תשלום
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# כותרות ברירת מחדל (עברית). ניתן לעקוף/להוסיף דרך מיפוי עמודות בהגדרות.
DEFAULT_ALIASES = {
    "order_id": ["מספר הזמנה"],
    "date": ["תאריך"],
    "first_name": ["שם פרטי"],
    "last_name": ["שם משפחה"],
    "phone": ["טלפון"],
    "email": ["מייל", "אימייל", "דוא\"ל"],
    "event": ["אירוע"],
    "amount": ["סכום לפי מטבע דיפולטיבי", "סכום"],
    "payment_form": ["צורת תשלום"],
}

# תוויות בעברית לשדות (לשימוש בהגדרות ובהודעות שגיאה)
FIELD_LABELS = {
    "order_id": "מספר הזמנה",
    "date": "תאריך",
    "first_name": "שם פרטי",
    "last_name": "שם משפחה",
    "phone": "טלפון",
    "email": "מייל",
    "event": "אירוע / תיאור",
    "amount": "סכום",
    "payment_form": "צורת תשלום",
}

REQUIRED_FIELDS = ("order_id", "email", "amount")


@dataclass
class Order:
    order_id: str
    date: datetime | None
    first_name: str
    last_name: str
    phone: str
    email: str
    event: str
    amount: float
    payment_form: str
    issues: list = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def _clean_amount(value) -> float:
    if pd.isna(value):
        return 0.0
    s = str(value)
    s = re.sub(r"[^\d.\-]", "", s)  # מסיר ¦, ₪, פסיקים ורווחים
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _parse_date(value) -> datetime | None:
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _norm_header(value) -> str:
    """מנרמל כותרת: מחליף רווח קשיח (NBSP) ורווחים כפולים ברווח רגיל."""
    s = str(value).replace("\xa0", " ").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    cols = {_norm_header(c): c for c in df.columns}
    for alias in aliases:
        if _norm_header(alias) in cols:
            return cols[_norm_header(alias)]
    return None


def preview_column_match(file, column_map: dict | None = None):
    """בודק אילו כותרות באקסל תואמות לכל שדה, לפי המיפוי הנוכחי.
    מחזיר (רשימת שורות בדיקה, רשימת כל הכותרות בקובץ)."""
    column_map = column_map or {}
    df = pd.read_excel(file, nrows=1)
    df.columns = [str(c).strip() for c in df.columns]
    rows = []
    for key, aliases in DEFAULT_ALIASES.items():
        configured = str(column_map.get(key, "")).strip()
        search = ([configured] if configured else []) + aliases
        col = _find_column(df, search)
        rows.append({
            "שדה": FIELD_LABELS[key],
            "כותרת שהוגדרה": configured or "(ברירת מחדל)",
            "כותרת שנמצאה בקובץ": col or "—",
            "חובה": "כן" if key in REQUIRED_FIELDS else "",
            "תקין": "✅" if col is not None else ("❌" if key in REQUIRED_FIELDS else "⚠️"),
        })
    return rows, list(df.columns)


def parse_excel(file, column_map: dict | None = None) -> tuple[list[Order], list[str]]:
    """מחזיר (רשימת הזמנות, רשימת שגיאות מבנה).
    column_map: מיפוי אופציונלי {שדה: שם כותרת באקסל} שגובר על ברירות המחדל."""
    column_map = column_map or {}
    df = pd.read_excel(file)
    df.columns = [str(c).strip() for c in df.columns]

    errors = []
    colmap = {}
    for key, aliases in DEFAULT_ALIASES.items():
        configured = str(column_map.get(key, "")).strip()
        search = ([configured] if configured else []) + aliases
        col = _find_column(df, search)
        if col is None and key in REQUIRED_FIELDS:
            errors.append(f"עמודה חסרה בקובץ: {search[0]}")
        colmap[key] = col

    if errors:
        return [], errors

    orders = []
    for _, row in df.iterrows():
        def get(key, default=""):
            col = colmap.get(key)
            if col is None or pd.isna(row.get(col)):
                return default
            return str(row[col]).strip()

        order = Order(
            order_id=get("order_id"),
            date=_parse_date(row.get(colmap["date"])) if colmap.get("date") else None,
            first_name=get("first_name"),
            last_name=get("last_name"),
            phone=get("phone"),
            email=get("email"),
            event=get("event"),
            amount=_clean_amount(row.get(colmap["amount"])),
            payment_form=get("payment_form"),
        )

        if not order.order_id:
            continue  # שורה ריקה
        if not order.email or not EMAIL_RE.match(order.email):
            order.issues.append("מייל חסר או לא תקין")
        if not order.full_name:
            order.issues.append("שם חסר")

        orders.append(order)

    return orders, errors
