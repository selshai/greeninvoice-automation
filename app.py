"""אוטומציית הפקת קבלות — חשבונית ירוקה (morning)
הרצה: streamlit run app.py
"""
import pandas as pd
import streamlit as st

from src.config import (
    DOC_VAT_TYPES,
    DOCUMENT_TYPES,
    INCOME_VAT_TYPES,
    credentials_ok,
    get_credentials,
    load_settings,
)
from src.excel_parser import parse_excel
from src.greeninvoice import GreenInvoiceClient, GreenInvoiceError
from src.runner import (
    build_payload,
    execute_run,
    limit_creates,
    load_log,
    load_processed,
    plan_run,
    restrict_to_retry,
    retry_error_ids,
    skip_previous_errors,
)

st.set_page_config(page_title="הפקת קבלות — חשבונית ירוקה", page_icon="🧾", layout="wide")

# RTL
st.markdown(
    "<style>.stApp, .stMarkdown, div[data-testid='stDataFrame'] {direction: rtl;}</style>",
    unsafe_allow_html=True,
)

settings = load_settings()
env = settings["environment"]
doc_type_label = DOCUMENT_TYPES.get(settings["document_type"], settings["document_type"])

def render_receipt_preview(order, settings):
    """מציג תצוגה מקדימה של המסמך כפי שיופק — לפני שליחה."""
    payload = build_payload(order, settings)
    doc_label = DOCUMENT_TYPES.get(payload["type"], payload["type"])
    doc_vat = DOC_VAT_TYPES.get(payload["vatType"], payload["vatType"])
    line = payload["income"][0]
    line_vat = INCOME_VAT_TYPES.get(line["vatType"], line["vatType"])
    pay = payload["payment"][0]
    emails = payload["client"].get("emails")
    email_line = f"📧 יישלח אל: {', '.join(emails)}" if emails else "✉️ לא יישלח מייל ללקוח"

    st.markdown(
        f"""
<div style="border:1px solid #3a3a3a;border-radius:12px;padding:20px;background:#161616;direction:rtl;max-width:560px">
  <div style="font-size:1.3em;font-weight:700;margin-bottom:2px">{doc_label}</div>
  <div style="color:#888;margin-bottom:14px">תאריך המסמך: {payload['date']} · {payload['currency']} · {doc_vat}</div>
  <div style="font-weight:600">לקוח</div>
  <div>{payload['client']['name']} · ☎ {payload['client'].get('phone','—')}</div>
  <div style="color:#7fd18b;margin:6px 0 14px">{email_line}</div>
  <div style="border-top:1px solid #333;padding-top:10px;font-weight:600">שורת שירות</div>
  <div style="display:flex;justify-content:space-between">
    <span>{line['description']}</span>
    <span>{line['price']:.2f} {line['currency']}</span>
  </div>
  <div style="color:#888;font-size:0.85em">כמות {line['quantity']} · מע״מ: {line_vat}</div>
  <div style="border-top:1px solid #333;margin-top:10px;padding-top:10px;font-weight:600">תשלום</div>
  <div style="display:flex;justify-content:space-between">
    <span>קוד תשלום {pay['type']} · {order.payment_form or '—'}</span>
    <span>{pay['price']:.2f} {pay['currency']}</span>
  </div>
  <div style="border-top:2px solid #444;margin-top:12px;padding-top:10px;display:flex;justify-content:space-between;font-size:1.15em;font-weight:700">
    <span>סה״כ</span><span>{line['price']:.2f} {line['currency']}</span>
  </div>
  <div style="color:#888;margin-top:12px;font-size:0.9em">הערות: {payload['remarks']}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("🔧 ה-JSON המדויק שיישלח ל-API"):
        st.json(payload)


st.title("🧾 הפקת קבלות אוטומטית")

# ---- סרגל מצב ----
col1, col2, col3 = st.columns(3)
with col1:
    if env == "production":
        st.error("סביבה: **ייצור (Production)** — מסמכים אמיתיים!")
    else:
        st.success("סביבה: **Sandbox** (בדיקות)")
with col2:
    st.info(f"סוג מסמך: **{doc_type_label}**")
with col3:
    if credentials_ok(env):
        st.success("מפתחות API: נטענו ✓")
    else:
        st.error("מפתחות API חסרים — ראה קובץ ‎.env")

st.caption("שינוי סביבה, סוג מסמך ותיאור השירות — בדף ⚙️ Settings בתפריט הצד.")

# ---- לוג הרצות מתמשך ----
log_entries = load_log(env)
with st.expander(f"📜 לוג הרצות ({env}) — {len(log_entries)} רשומות"):
    if log_entries:
        log_df = pd.DataFrame(log_entries).rename(
            columns={
                "ts": "זמן",
                "order_id": "מספר הזמנה",
                "name": "שם",
                "email": "מייל",
                "amount": "סכום",
                "status": "סטטוס",
                "detail": "פירוט",
                "doc_number": "מספר מסמך",
                "link": "קישור",
            }
        )
        st.dataframe(log_df.iloc[::-1], use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ הורדת הלוג המלא (CSV)",
            log_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"runlog_{env}.csv",
            mime="text/csv",
        )
    else:
        st.write("עדיין לא בוצעה הרצה בסביבה זו.")

ACTION_LABELS = {"create": "✅ להפקה", "skip": "⏭️ דילוג", "error": "⚠️ חריגה"}


def build_plan(orders):
    processed = load_processed(env)
    plan = plan_run(orders, settings, processed)
    err_ids = retry_error_ids(env)
    if settings.get("retry_only_errors"):
        plan = restrict_to_retry(plan, err_ids)
    else:
        plan = skip_previous_errors(plan, err_ids)
    if settings.get("limit_enabled"):
        plan = limit_creates(plan, int(settings.get("limit_count", 3)))
    return plan


def plan_to_df(plan):
    return pd.DataFrame(
        [
            {
                "מספר הזמנה": p["order"].order_id,
                "שם": p["order"].full_name,
                "מייל": p["order"].email,
                "אירוע": p["order"].event,
                "סכום": p["order"].amount,
                "צורת תשלום": p["order"].payment_form,
                "פעולה": ACTION_LABELS[p["action"]],
                "סיבה": p["reason"],
            }
            for p in plan
        ]
    )


orders = st.session_state.get("orders")
stage = st.session_state.get("stage", "select")

# ======================= שלב 1: בחירה =======================
if stage == "select":
    st.header("שלב 1 — בחירה ותצוגה מקדימה")
    uploaded = st.file_uploader("העלאת אקסל לקוחות", type=["xlsx", "xls"], key="uploader")
    if uploaded is not None:
        new_orders, errors = parse_excel(uploaded, settings.get("column_mapping"))
        if errors:
            for e in errors:
                st.error(e)
            st.stop()
        st.session_state["orders"] = new_orders
        st.session_state["source_name"] = uploaded.name
        st.session_state.pop("results", None)
        orders = new_orders

    if not orders:
        st.info("העלה קובץ אקסל כדי להתחיל. הקובץ צריך לכלול את העמודות: מספר הזמנה, תאריך, שם פרטי, שם משפחה, טלפון, מייל, אירוע, סכום, צורת תשלום.")
        st.stop()

    c_a, c_b = st.columns([4, 1])
    c_a.caption(f"קובץ טעון: **{st.session_state.get('source_name','')}** · {len(orders)} שורות")
    if c_b.button("🗑️ נקה קובץ"):
        for k in ("orders", "source_name", "results"):
            st.session_state.pop(k, None)
        st.rerun()

    plan = build_plan(orders)
    n_create = sum(1 for p in plan if p["action"] == "create")
    n_skip = sum(1 for p in plan if p["action"] == "skip")
    n_err = sum(1 for p in plan if p["action"] == "error")
    n_prev_err = len(retry_error_ids(env))
    if settings.get("retry_only_errors"):
        st.info(f"🔁 מצב ניסיון חוזר פעיל: מעובדות רק **{n_prev_err}** הזמנות שנכשלו בעבר (משתנה בדף ⚙️ Settings).")
    elif n_prev_err:
        st.info(f"ℹ️ **{n_prev_err}** הזמנות שנכשלו בעבר ידולגו. להפקתן — הפעל 'ניסיון חוזר' בדף ⚙️ Settings.")
    if settings.get("limit_enabled"):
        st.info(f"⚠️ פעילה הגבלת הרצה: עד **{settings.get('limit_count', 3)}** מסמכים (משתנה בדף ⚙️ Settings).")

    st.subheader("תצוגה מקדימה (Dry Run)")
    st.write(f"**{n_create}** להפקה · **{n_skip}** דילוגים · **{n_err}** חריגות")
    st.caption("👆 לחץ על שורה כדי לראות איך ייראה המסמך לפני השליחה.")
    selection = st.dataframe(
        plan_to_df(plan),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="plan_table",
    )

    sel_rows = selection.selection.rows if selection and selection.selection else []
    if sel_rows:
        sel_order = plan[sel_rows[0]]["order"]
        sel_action = plan[sel_rows[0]]["action"]
        st.markdown(f"#### תצוגת מסמך — {sel_order.full_name}")
        if sel_action != "create":
            st.info(f"שורה זו לא תופק ({ACTION_LABELS[sel_action]}: {plan[sel_rows[0]]['reason']}). זו תצוגה בלבד.")
        render_receipt_preview(sel_order, settings)

    st.divider()
    if n_create == 0:
        st.warning("אין שורות להפקה. בדוק את הקובץ או את ההגדרות.")
    else:
        if st.button(f"המשך לאישור והרצה ({n_create} מסמכים) ←", type="primary"):
            st.session_state["stage"] = "execute"
            st.rerun()

# ======================= שלב 2: הרצה =======================
elif stage == "execute":
    st.header("שלב 2 — אישור והרצה")
    if st.button("→ חזרה לבחירה"):
        st.session_state["stage"] = "select"
        st.rerun()

    if not orders:
        st.warning("לא נטען קובץ. חזור לשלב הבחירה.")
        st.stop()

    plan = build_plan(orders)
    n_create = sum(1 for p in plan if p["action"] == "create")

    # אם כבר בוצעה הרצה — הצג את התוצאות (נשמרות כדי שלא יאבדו ברענון)
    if st.session_state.get("results") is not None:
        results = st.session_state["results"]
        res_df = pd.DataFrame(results).rename(
            columns={
                "order_id": "מספר הזמנה", "name": "שם", "email": "מייל", "amount": "סכום",
                "status": "סטטוס", "detail": "פירוט", "doc_number": "מספר מסמך", "link": "קישור",
            }
        )
        created = sum(1 for r in results if r["status"] == "created")
        failed = sum(1 for r in results if r["status"] == "error" and r["detail"])
        st.success(f"הופקו {created} מסמכים. חריגות/כשלים: {failed}.")
        st.dataframe(
            res_df, use_container_width=True, hide_index=True,
            column_config={"קישור": st.column_config.LinkColumn("קישור")},
        )
        st.download_button(
            "⬇️ הורדת דוח סיכום (CSV)",
            res_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="run_report.csv", mime="text/csv",
        )
        if st.button("🆕 הרצה חדשה / קובץ אחר"):
            for k in ("orders", "source_name", "results"):
                st.session_state.pop(k, None)
            st.session_state["stage"] = "select"
            st.rerun()
        st.stop()

    st.write(f"עומדים להפיק **{n_create}** מסמכי **{doc_type_label}** בסביבת **{env}**.")
    if n_create == 0:
        st.warning("אין שורות להפקה. חזור לשלב הבחירה.")
        st.stop()
    if env == "production":
        st.warning("שים לב: הרצה בייצור מפיקה מסמכים חשבונאיים אמיתיים ושולחת מיילים ללקוחות.")

    confirmed = st.checkbox(f"אני מאשר/ת הפקה של {n_create} מסמכי {doc_type_label} בסביבת {env}")
    if st.button(f"🚀 הפק {n_create} מסמכים", type="primary", disabled=not confirmed):
        if not credentials_ok(env):
            st.error("מפתחות API חסרים לסביבה הנוכחית. מלא אותם בקובץ ‎.env והפעל מחדש.")
            st.stop()
        creds = get_credentials(env)
        client = GreenInvoiceClient(creds["base_url"], creds["api_key"], creds["api_secret"])
        try:
            client.test_connection()
        except GreenInvoiceError as e:
            st.error(f"החיבור ל-API נכשל: {e}")
            st.stop()

        bar = st.progress(0.0, text="מפיק מסמכים...")
        results = execute_run(plan, client, settings, env, progress_callback=lambda p: bar.progress(p))
        bar.progress(1.0, text="הסתיים")
        st.session_state["results"] = results
        st.rerun()
