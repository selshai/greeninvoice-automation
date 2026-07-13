"""דף הגדרות האוטומציה."""
import json

import pandas as pd
import streamlit as st

from src.config import (
    DOC_VAT_TYPES,
    DOCUMENT_TYPES,
    INCOME_VAT_TYPES,
    credentials_ok,
    get_credentials,
    load_settings,
    save_credentials,
    save_settings,
)
from src.excel_parser import FIELD_LABELS, REQUIRED_FIELDS, preview_column_match
from src.greeninvoice import GreenInvoiceClient, GreenInvoiceError

st.set_page_config(page_title="הגדרות", page_icon="⚙️", layout="wide")
st.markdown("<style>.stApp {direction: rtl;}</style>", unsafe_allow_html=True)

st.title("⚙️ הגדרות האוטומציה")
settings = load_settings()

# ---- סביבה ומפתחות ----
st.header("סביבת עבודה")
env = st.radio(
    "סביבה",
    ["sandbox", "production"],
    index=0 if settings["environment"] == "sandbox" else 1,
    format_func=lambda x: "🧪 Sandbox (בדיקות)" if x == "sandbox" else "🔴 ייצור (Production)",
    horizontal=True,
)
creds = get_credentials(env)
if credentials_ok(env):
    st.success(f"מפתחות לסביבה זו קיימים ✓ (כתובת: {creds['base_url']})")
else:
    st.warning("לא נמצאו מפתחות לסביבה זו — הזן אותם למטה.")

with st.expander("🔑 עדכון מפתחות API לסביבה זו", expanded=not credentials_ok(env)):
    st.caption(
        "המפתחות נשמרים בקובץ ‎.env המקומי בלבד (לא ב-git). "
        "השאר שדה ריק כדי לא לשנות את הערך הקיים."
    )
    key_in = st.text_input(
        "API Key (מזהה)",
        value="",
        type="password",
        placeholder="מוגדר ✓" if creds["api_key"] else "הדבק כאן את ה-Key",
    )
    secret_in = st.text_input(
        "API Secret (סוד)",
        value="",
        type="password",
        placeholder="מוגדר ✓" if creds["api_secret"] else "הדבק כאן את ה-Secret",
    )
    c_save, c_test = st.columns(2)
    if c_save.button("💾 שמירת מפתחות"):
        if not key_in.strip() and not secret_in.strip():
            st.warning("לא הוזנו ערכים חדשים.")
        else:
            save_credentials(env, key_in, secret_in)
            st.success("המפתחות נשמרו בקובץ ‎.env ✓")
            st.rerun()
    if c_test.button("🔌 בדיקת חיבור"):
        c = get_credentials(env)
        if not (c["api_key"] and c["api_secret"]):
            st.error("חסרים מפתחות לבדיקה.")
        else:
            try:
                GreenInvoiceClient(c["base_url"], c["api_key"], c["api_secret"]).test_connection()
                st.success("החיבור הצליח ✓")
            except GreenInvoiceError as e:
                st.error(f"החיבור נכשל: {e}")

# ---- מסמך ----
st.header("סוג המסמך")
st.caption("העמותה מפיקה כיום קבלות. ניתן לעבור לקבלה על תרומה (מוכרת למס) או לחשבוניות בעתיד.")
doc_type = st.selectbox(
    "סוג מסמך להפקה",
    options=list(DOCUMENT_TYPES.keys()),
    index=list(DOCUMENT_TYPES.keys()).index(settings["document_type"])
    if settings["document_type"] in DOCUMENT_TYPES
    else 0,
    format_func=lambda k: f"{DOCUMENT_TYPES[k]} ({k})",
)
if doc_type == 405:
    st.info("קבלה על תרומה מחייבת שלעסק בחשבונית ירוקה מוגדר אישור סעיף 46 (מוסד ציבורי מוכר). ודא זאת בהגדרות העסק במורנינג.")

col1, col2 = st.columns(2)
with col1:
    doc_vat = st.selectbox(
        "מע\"מ ברמת המסמך (vatType)",
        options=list(DOC_VAT_TYPES.keys()),
        index=list(DOC_VAT_TYPES.keys()).index(settings.get("document_vat_type", 0)),
        format_func=lambda k: f"{DOC_VAT_TYPES[k]} ({k})",
    )
with col2:
    income_vat = st.selectbox(
        "מע\"מ ברמת שורת ההכנסה",
        options=list(INCOME_VAT_TYPES.keys()),
        index=list(INCOME_VAT_TYPES.keys()).index(settings.get("income_vat_type", 0)),
        format_func=lambda k: f"{INCOME_VAT_TYPES[k]} ({k})",
    )

# ---- תיאור השירות ----
st.header("תיאור השירות והערות")
st.caption("משתנים זמינים: ‎{event}‎ ‎{order_id}‎ ‎{name}‎ ‎{date}‎ ‎{description}‎")
st.caption("💡 בקבלה (סוג 400) תיאור השירות לא מוצג כשורה — השתמש ב-‎{description}‎ בהערות כדי שיופיע על המסמך.")
desc_tpl = st.text_input("תיאור השורה במסמך", value=settings["service_description_template"])
remarks_tpl = st.text_input("הערות במסמך", value=settings["remarks_template"])

# ---- התנהגות ----
st.header("התנהגות האוטומציה")
col1, col2, col3 = st.columns(3)
with col1:
    send_email = st.toggle("שליחת המסמך למייל הלקוח", value=settings.get("send_email", True))
with col2:
    skip_zero = st.toggle("דילוג על שורות בסכום 0 ₪", value=settings.get("skip_zero_amount", True))
with col3:
    add_client = st.toggle("הוספת הלקוח לניהול לקוחות", value=settings.get("add_client_to_crm", False))

date_source = st.radio(
    "תאריך המסמך",
    ["order_date", "today"],
    index=0 if settings.get("date_source") == "order_date" else 1,
    format_func=lambda x: "תאריך ההזמנה מהאקסל" if x == "order_date" else "תאריך ההפקה (היום)",
    horizontal=True,
)

st.subheader("הגבלת מספר מסמכים בהרצה")
st.caption("מומלץ לבדיקה — מפיק רק את השורות הראשונות עד המספר שנבחר. השאר יסומנו כדילוג.")
lim_col1, lim_col2 = st.columns([1, 2])
with lim_col1:
    limit_enabled = st.toggle("הפעלת הגבלה", value=settings.get("limit_enabled", False))
with lim_col2:
    limit_count = st.number_input(
        "מספר מסמכים מרבי",
        min_value=1,
        value=int(settings.get("limit_count", 3)),
        step=1,
        disabled=not limit_enabled,
    )

st.subheader("ניסיון חוזר להזמנות שנכשלו")
retry_only = st.toggle(
    "עבד רק הזמנות שנכשלו בהרצות קודמות",
    value=settings.get("retry_only_errors", False),
    help="כשמסומן — יופקו רק ההזמנות שנכשלו בעבר (לפי הלוג) ועדיין לא הופקו. שאר ההזמנות ידולגו.",
)

# ---- מיפוי עמודות האקסל ----
st.header("מיפוי עמודות האקסל")
st.caption("שם הכותרת בקובץ האקסל שלך עבור כל שדה — לתמיכה בקבצים עם כותרות שונות. שדות עם * הם חובה.")
col_map_current = settings.get("column_mapping", {})
column_mapping = {}
cmap_cols = st.columns(3)
for i, (field, label) in enumerate(FIELD_LABELS.items()):
    star = " *" if field in REQUIRED_FIELDS else ""
    with cmap_cols[i % 3]:
        column_mapping[field] = st.text_input(
            f"{label}{star}",
            value=col_map_current.get(field, ""),
            key=f"colmap_{field}",
        )

with st.expander("🧪 בדיקת מיפוי על קובץ לדוגמה"):
    st.caption("העלה קובץ אקסל כדי לראות אילו כותרות תואמות למיפוי הנוכחי (לפני שמירה). הבדיקה משתמשת בערכים שהוזנו למעלה.")
    sample = st.file_uploader("קובץ לבדיקה", type=["xlsx", "xls"], key="colmap_test")
    if sample is not None:
        try:
            rows, headers = preview_column_match(sample, {k: v.strip() for k, v in column_mapping.items()})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            missing = [r["שדה"] for r in rows if r["תקין"] == "❌"]
            if missing:
                st.error("שדות חובה שלא נמצאו: " + ", ".join(missing) + " — עדכן את המיפוי למעלה.")
            else:
                st.success("כל שדות החובה נמצאו ✓")
            st.caption("כותרות בקובץ: " + " · ".join(str(h) for h in headers))
        except Exception as e:
            st.error(f"קריאת הקובץ נכשלה: {e}")

# ---- מיפוי צורות תשלום ----
st.header("מיפוי צורות תשלום")
st.caption("מיפוי בין הטקסט בעמודת 'צורת תשלום' באקסל לקוד התשלום ב-API (3=אשראי, 1=מזומן, 2=צ'ק, 4=העברה, 5=PayPal, 10=אחר)")
pay_map_text = st.text_area(
    "מיפוי (JSON)",
    value=json.dumps(settings["payment_type_map"], ensure_ascii=False, indent=2),
    height=220,
)

# ---- שמירה ----
if st.button("💾 שמירת הגדרות", type="primary"):
    try:
        pay_map = json.loads(pay_map_text)
    except json.JSONDecodeError as e:
        st.error(f"מיפוי צורות התשלום אינו JSON תקין: {e}")
        st.stop()
    settings.update(
        environment=env,
        document_type=int(doc_type),
        document_vat_type=int(doc_vat),
        income_vat_type=int(income_vat),
        service_description_template=desc_tpl,
        remarks_template=remarks_tpl,
        send_email=send_email,
        skip_zero_amount=skip_zero,
        add_client_to_crm=add_client,
        date_source=date_source,
        limit_enabled=bool(limit_enabled),
        limit_count=int(limit_count),
        retry_only_errors=bool(retry_only),
        column_mapping={k: v.strip() for k, v in column_mapping.items()},
        payment_type_map=pay_map,
    )
    save_settings(settings)
    st.success("ההגדרות נשמרו ✓")
