#!/bin/bash
# הכנה והפעלה אוטומטית של אפליקציית הפקת הקבלות ב-macOS.
# מתקין Python (אם חסר), יוצר סביבה וירטואלית, מתקין ספריות, ומפעיל את השרת.
# להפעלה: לחיצה כפולה ב-Finder, או ‏‎./run.command‎ בטרמינל.

cd "$(dirname "$0")" || exit 1

TOTAL=4
stage() {
    echo ""
    echo "===== שלב $1/$TOTAL — $2 ====="
}
fail() {
    echo ""
    echo "[עצירה] $1"
    read -r -p "הקש Enter לסגירה..." _
    exit 1
}

# ---------- שלב 1: Python ----------
stage 1 "בדיקת Python"
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
    echo "נמצא Python: $PYTHON"
else
    echo "Python לא מותקן — מתחיל התקנה אוטומטית."

    # ניסיון 1: Homebrew
    if command -v brew >/dev/null 2>&1; then
        echo "מתקין באמצעות Homebrew..."
        brew install python
    else
        echo "Homebrew לא נמצא — מתקין Homebrew תחילה (ייתכן שתתבקש להזין סיסמה)..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # הוספת brew ל-PATH (Apple Silicon / Intel)
        if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
        if [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
        if command -v brew >/dev/null 2>&1; then
            echo "מתקין Python..."
            brew install python
        fi
    fi

    if command -v python3 >/dev/null 2>&1; then
        PYTHON="$(command -v python3)"
        echo "Python הותקן: $PYTHON"
    else
        fail "התקנת Python האוטומטית לא הושלמה. התקן ידנית מ- https://www.python.org/downloads/macos/ והפעל שוב."
    fi
fi

# ---------- שלב 2: סביבה וירטואלית ----------
stage 2 "יצירת סביבה וירטואלית"
VENV_PY="./.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    "$PYTHON" -m venv .venv || fail "יצירת הסביבה הווירטואלית נכשלה."
    echo "הסביבה נוצרה."
else
    echo "סביבה קיימת — מדלג."
fi

# ---------- שלב 3: התקנת ספריות ----------
stage 3 "התקנת ספריות"
"$VENV_PY" -m pip install --upgrade pip --quiet --disable-pip-version-check
REQS=$(grep -vE '^\s*#|^\s*$' requirements.txt)
COUNT=$(echo "$REQS" | wc -l | tr -d ' ')
i=0
while IFS= read -r pkg; do
    [ -z "$pkg" ] && continue
    i=$((i + 1))
    pct=$((i * 100 / COUNT))
    printf "  [%3d%%] מתקין: %s\n" "$pct" "$pkg"
    "$VENV_PY" -m pip install "$pkg" --quiet --disable-pip-version-check || fail "התקנת החבילה '$pkg' נכשלה."
done <<< "$REQS"
echo "כל הספריות הותקנו."

# יצירת .env אם חסר (המפתחות מוזנים דרך דף ההגדרות)
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then cp ".env.example" ".env"; else echo "# מפתחות API — ניתן להזין דרך דף ההגדרות" > ".env"; fi
fi

# ---------- שלב 4: הפעלה ----------
stage 4 "הפעלת השרת ופתיחת הדפדפן"
echo "השרת עולה בכתובת http://localhost:8501 — הדפדפן ייפתח אוטומטית."
echo "לעצירה: סגור חלון זה או הקש Ctrl+C."
( sleep 4; open "http://localhost:8501" ) &
"$VENV_PY" -m streamlit run app.py --server.headless=true

read -r -p "השרת נעצר. הקש Enter לסגירה..." _
