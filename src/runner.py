"""לוגיקת ההרצה: בניית מסמכים, מניעת כפילויות, הפקה ודוח סיכום."""
import json
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR
from .excel_parser import Order
from .greeninvoice import GreenInvoiceClient, GreenInvoiceError


# ---------- מניעת כפילויות ----------
def _processed_path(environment: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"processed_{environment}.json"


def _log_path(environment: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"runlog_{environment}.jsonl"


def log_event(environment: str, entry: dict) -> None:
    """מוסיף שורת לוג עמידה (JSONL) לכל מסמך שהופק/נכשל — עם חותמת זמן."""
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "env": environment, **entry}
    with open(_log_path(environment), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_log(environment: str) -> list[dict]:
    """קורא את לוג ההרצות (JSONL). מחזיר רשימה, האחרון בסוף."""
    path = _log_path(environment)
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_processed(environment: str) -> dict:
    path = _processed_path(environment)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_processed(environment: str, processed: dict) -> None:
    with open(_processed_path(environment), "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)


# ---------- בניית payload ----------
def build_payload(order: Order, settings: dict) -> dict:
    tpl_vars = {
        "event": order.event,
        "order_id": order.order_id,
        "name": order.full_name,
        "date": order.date.strftime("%d.%m.%Y") if order.date else "",
    }
    description = settings["service_description_template"].format(**tpl_vars) or order.event
    # תיאור השירות זמין גם בתבנית ההערות (כדי שיופיע על קבלה, שבה אין שורת שירות)
    tpl_vars["description"] = description
    remarks = settings["remarks_template"].format(**tpl_vars)

    if settings.get("date_source") == "order_date" and order.date:
        doc_date = order.date.strftime("%Y-%m-%d")
    else:
        doc_date = datetime.now().strftime("%Y-%m-%d")

    pay_map = settings["payment_type_map"]
    payment_type = pay_map.get(order.payment_form, pay_map.get("default", 10))

    client = {
        "name": order.full_name,
        "phone": order.phone,
        "add": bool(settings.get("add_client_to_crm", False)),
    }
    if settings.get("send_email", True) and order.email:
        client["emails"] = [order.email]

    payload = {
        "type": int(settings["document_type"]),
        "date": doc_date,
        "lang": settings.get("language", "he"),
        "currency": settings.get("currency", "ILS"),
        "vatType": int(settings.get("document_vat_type", 0)),
        "remarks": remarks,
        "client": client,
        "income": [
            {
                "description": description,
                "quantity": 1,
                "price": order.amount,
                "currency": settings.get("currency", "ILS"),
                "vatType": int(settings.get("income_vat_type", 0)),
            }
        ],
        "payment": [
            {
                "type": int(payment_type),
                "price": order.amount,
                "currency": settings.get("currency", "ILS"),
                "date": doc_date,
            }
        ],
    }
    return payload


# ---------- הרצה ----------
def plan_run(orders: list[Order], settings: dict, processed: dict) -> list[dict]:
    """מסווג כל שורה: להפקה / דילוג / חריגה. משמש גם ל-Dry Run."""
    plan = []
    seen_in_file = set()
    for order in orders:
        item = {"order": order, "action": "create", "reason": ""}
        if order.order_id in processed:
            doc = processed[order.order_id]
            item["action"] = "skip"
            item["reason"] = f"כבר הופק מסמך {doc.get('doc_number', doc.get('doc_id', ''))}"
        elif order.order_id in seen_in_file:
            item["action"] = "skip"
            item["reason"] = "מספר הזמנה כפול בקובץ"
        elif settings.get("skip_zero_amount", True) and order.amount <= 0:
            item["action"] = "skip"
            item["reason"] = "סכום 0 ₪"
        elif order.issues:
            item["action"] = "error"
            item["reason"] = ", ".join(order.issues)
        seen_in_file.add(order.order_id)
        plan.append(item)
    return plan


def retry_error_ids(environment: str) -> set[str]:
    """מזהי הזמנות שנכשלו בהרצות קודמות (לפי הלוג) ועדיין לא הופקו בהצלחה."""
    processed = set(load_processed(environment).keys())
    errored = {str(e.get("order_id")) for e in load_log(environment) if e.get("status") == "error"}
    return errored - processed


def restrict_to_retry(plan: list[dict], retry_ids: set[str]) -> list[dict]:
    """מצב ניסיון חוזר: משאיר להפקה רק הזמנות שנכשלו בעבר. השאר מסומנות כדילוג."""
    for item in plan:
        if item["action"] == "create" and item["order"].order_id not in retry_ids:
            item["action"] = "skip"
            item["reason"] = "מצב ניסיון חוזר — מעובדות רק הזמנות שנכשלו"
    return plan


def skip_previous_errors(plan: list[dict], error_ids: set[str]) -> list[dict]:
    """מצב רגיל: מדלג על הזמנות שנכשלו בעבר (עד שיופעל 'ניסיון חוזר')."""
    for item in plan:
        if item["action"] == "create" and item["order"].order_id in error_ids:
            item["action"] = "skip"
            item["reason"] = "נכשלה בעבר — הפעל 'ניסיון חוזר' בהגדרות כדי לנסות שוב"
    return plan


def limit_creates(plan: list[dict], max_creates: int | None) -> list[dict]:
    """מגביל את מספר השורות להפקה ל-max_creates הראשונות. השאר מסומנות כדילוג.
    שימושי לריצת בדיקה בייצור (למשל 3 מסמכים בלבד). None = ללא הגבלה."""
    if max_creates is None:
        return plan
    seen = 0
    for item in plan:
        if item["action"] != "create":
            continue
        seen += 1
        if seen > max_creates:
            item["action"] = "skip"
            item["reason"] = f"מעל מגבלת ההרצה ({max_creates})"
    return plan


def execute_run(
    plan: list[dict],
    client: GreenInvoiceClient,
    settings: dict,
    environment: str,
    progress_callback=None,
) -> list[dict]:
    """מבצע את התוכנית מול ה-API. מחזיר תוצאות מפורטות."""
    processed = load_processed(environment)
    results = []
    to_create = [item for item in plan if item["action"] == "create"]

    for i, item in enumerate(plan):
        order: Order = item["order"]
        result = {
            "order_id": order.order_id,
            "name": order.full_name,
            "email": order.email,
            "amount": order.amount,
            "status": item["action"],
            "detail": item["reason"],
            "doc_number": "",
            "link": "",
        }
        if item["action"] == "create":
            try:
                payload = build_payload(order, settings)
                resp = client.create_document(payload)
                doc_id = resp.get("id", "")
                doc_number = resp.get("number", resp.get("docNumber", ""))
                link = ""
                if doc_id:
                    try:
                        links = client.get_download_links(doc_id)
                        link = links.get("origin", "")
                    except GreenInvoiceError:
                        pass
                processed[order.order_id] = {
                    "doc_id": doc_id,
                    "doc_number": doc_number,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "amount": order.amount,
                    "email": order.email,
                }
                save_processed(environment, processed)
                result.update(status="created", detail="הופק ונשלח", doc_number=str(doc_number), link=link)
            except GreenInvoiceError as e:
                result.update(status="error", detail=str(e))
            log_event(environment, {
                "order_id": order.order_id,
                "name": order.full_name,
                "email": order.email,
                "amount": order.amount,
                "status": result["status"],
                "detail": result["detail"],
                "doc_number": result["doc_number"],
                "link": result["link"],
            })
        results.append(result)
        if progress_callback and item["action"] == "create":
            done = sum(1 for r in results if r["status"] in ("created", "error") and r["detail"])
            progress_callback(min(done / max(len(to_create), 1), 1.0))

    return results
