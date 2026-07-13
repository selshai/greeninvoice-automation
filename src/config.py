"""טעינת קונפיגורציה: מפתחות API מ-.env (מאובטח), הגדרות אוטומציה מ-settings.json."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "settings.json"
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"

load_dotenv(ENV_PATH)

# סוגי מסמכים נתמכים (ניתן להרחיב בעתיד)
DOCUMENT_TYPES = {
    400: "קבלה",
    405: "קבלה על תרומה (מוכרת למס — סעיף 46)",
    320: "חשבונית מס-קבלה",
    305: "חשבונית מס",
}

# vatType ברמת המסמך
DOC_VAT_TYPES = {
    0: "כולל מע\"מ",
    1: "לא כולל מע\"מ",
    2: "פטור ממע\"מ (עמותה / עוסק פטור)",
}

# vatType ברמת שורת ההכנסה
INCOME_VAT_TYPES = {
    0: "ברירת מחדל של העסק",
    1: "כולל מע\"מ",
    2: "פטור ממע\"מ",
}

DEFAULT_SETTINGS = {
    "environment": "sandbox",
    "document_type": 400,
    "language": "he",
    "currency": "ILS",
    "document_vat_type": 0,
    "income_vat_type": 2,
    "service_description_template": "{event}",
    "remarks_template": "מספר הזמנה: {order_id}",
    "send_email": True,
    "email_subject": "",
    "add_client_to_crm": False,
    "skip_zero_amount": True,
    "date_source": "order_date",
    "limit_enabled": False,
    "limit_count": 3,
    "retry_only_errors": False,
    "column_mapping": {
        "order_id": "מספר הזמנה",
        "date": "תאריך",
        "first_name": "שם פרטי",
        "last_name": "שם משפחה",
        "phone": "טלפון",
        "email": "מייל",
        "event": "אירוע",
        "amount": "סכום",
        "payment_form": "צורת תשלום",
    },
    "payment_type_map": {
        "אשראי": 3,
        "מזומן": 1,
        "צ'ק": 2,
        "העברה בנקאית": 4,
        "PayPal": 5,
        "ביט": 10,
        "default": 10,
    },
}


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            settings.update(json.load(f))
    return settings


def save_settings(settings: dict) -> None:
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_credentials(environment: str) -> dict:
    """מחזיר את פרטי הגישה לסביבה המבוקשת. המפתחות נטענים מ-.env בלבד."""
    env = environment.upper()  # SANDBOX / PRODUCTION → PROD
    prefix = "GI_SANDBOX" if env == "SANDBOX" else "GI_PROD"
    default_base = (
        "https://sandbox.d.greeninvoice.co.il/api/v1"
        if env == "SANDBOX"
        else "https://api.greeninvoice.co.il/api/v1"
    )
    creds = {
        "base_url": os.getenv(f"{prefix}_BASE_URL", default_base),
        "api_key": os.getenv(f"{prefix}_API_KEY", ""),
        "api_secret": os.getenv(f"{prefix}_API_SECRET", ""),
    }
    return creds


def credentials_ok(environment: str) -> bool:
    c = get_credentials(environment)
    return bool(c["api_key"] and c["api_secret"])


def save_credentials(environment: str, api_key: str = "", api_secret: str = "") -> None:
    """שומר מפתח/סוד ל-.env עבור הסביבה הנבחרת. ערכים ריקים אינם דורסים קיימים.
    שאר השורות בקובץ נשמרות כפי שהן."""
    prefix = "GI_SANDBOX" if environment.upper() == "SANDBOX" else "GI_PROD"
    updates = {}
    if api_key.strip():
        updates[f"{prefix}_API_KEY"] = api_key.strip()
    if api_secret.strip():
        updates[f"{prefix}_API_SECRET"] = api_secret.strip()
    if not updates:
        return

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    # לשקף מיד בתהליך הנוכחי כדי ש-credentials_ok יזהה
    for k, v in updates.items():
        os.environ[k] = v
