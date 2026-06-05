# 🌡️ Sensibo Climate Dashboard

דשבורד אינטראקטיבי לצפייה בנתוני **טמפרטורה, לחות, תחושה, אות WiFi וצריכת חשמל** ממכשירי Sensibo.
פועל אוטומטית על GitHub Actions + GitHub Pages — **בחינם לחלוטין**.

תומך במספר מזגנים עם הספק שונה לכל אחד, לפי שמותיהם באפליקציית Sensibo.

---

## מבנה הפרויקט

```
sensibo-dashboard/
├── .github/
│   └── workflows/
│       └── daily.yml              ← ריצה שעתית אוטומטית (GitHub Actions)
├── data/
│   ├── measurements.json          ← טמפ׳ + לחות + תחושה + WiFi  [נוצר אוטומטית]
│   └── energy.json                ← kWh + עלות ₪                 [נוצר אוטומטית]
├── config.json                    ← הגדרות הספק ומחיר חשמל  ← תערוך זה
├── fetch_data.py                  ← סקריפט שמושך נתונים מה-API
├── generate_password_hash.py      ← כלי חד-פעמי ליצירת סיסמא מוצפנת
├── index.html                     ← הדשבורד האינטראקטיבי
└── README.md
```

---

## הגדרה — שלב אחר שלב

### שלב 1 — צור GitHub Repo

1. היכנס ל-[github.com](https://github.com) → **New repository**
2. שם: `sensibo-dashboard` — **Public** (נדרש ל-GitHub Pages בחינם)
3. צור את הריפו → העלה את כל הקבצים

```bash
git clone https://github.com/<USERNAME>/sensibo-dashboard.git
cd sensibo-dashboard
# העתק את כל קבצי הפרויקט לתיקייה זו
git add .
git commit -m "init"
git push
```

---

### שלב 2 — קבל API Key מ-Sensibo

1. אפליקציית Sensibo → **Settings → API Integration → Add API Key**
2. תן שם (למשל `dashboard`) → **העתק את המפתח**

אפשר גם דרך הדפדפן: https://home.sensibo.com/me/api

---

### שלב 3 — הוסף Secret ב-GitHub

**Settings → Secrets and variables → Actions → New repository secret**

| שם | ערך |
|----|-----|
| `SENSIBO_API_KEY` | המפתח מ-Sensibo |

זה הדבר היחיד שמוגדר כ-Secret.

---

### שלב 4 — ערוך את config.json

```json
{
  "price_per_kwh": 0.65,
  "default_power_kw": 2.5,
  "devices": {
    "סלון": { "power_kw": 3.5 },
    "חדר שינה": { "power_kw": 2.0 }
  }
}
```

- שמות המזגנים **חייבים להיות זהים** לשמות ב-Sensibo
- מזגן שאינו מופיע יקבל את `default_power_kw`
- `price_per_kwh` — תעריף נוכחי בישראל: כ-**0.65 ₪/kWh**
- הספק (kW) מופיע בשורה **Rated Input** על תווית המזגן

---

### שלב 5 — הפעל GitHub Pages

**Settings → Pages → Branch: main / root → Save**

הדשבורד יהיה זמין בכתובת:
`https://<USERNAME>.github.io/sensibo-dashboard/`

---

### שלב 6 — ריצה ראשונה (ידנית)

**Actions → Fetch Sensibo Data → Run workflow**

---

## שינוי סיסמא

הסיסמא מוצפנת (SHA-256) ב-`index.html`. לשינוי:

```bash
python generate_password_hash.py
# הזן סיסמא → קבל hash → פתח index.html
# חפש: const PASSWORD_HASH = "..."
# החלף בערך החדש → push
```

---

## תזמון אוטומטי

הסקריפט רץ **כל שעה** (cron: `0 * * * *`).
כ-144 דקות/חודש מתוך 2,000 המוקצות בחינם.

---

## מה הדשבורד מציג

| פיצ׳ר | תיאור |
|-------|-------|
| **בחירת מזגן** | תפריט לפי שמות מאפליקציית Sensibo |
| **כרטיסי סטטיסטיקה** | טמפ׳/לחות/תחושה עכשיו, ממוצע 24ש׳, מקס/מין, אות WiFi, צריכה ועלות |
| **גרף טמפ׳/לחות/תחושה** | 24ש׳ / שבוע / חודש / 3 חודשים |
| **מפת חום שבועית** | ממוצע טמפ׳ לפי שעה × יום (7 ימים אחרונים) |
| **גרף WiFi (RSSI)** | עוצמת אות לאורך זמן — שימושי לזיהוי ניתוקים |
| **גרף אנרגיה** | עמודות kWh + קו עלות ₪ — 30 ימים אחרונים |

נתוני אנרגיה מחושבים מ-AC state events × הספק שהוגדר ב-`config.json`.
כל הנתונים נשמרים **90 יום** אחורה.

---

## אבטחה

- ה-`SENSIBO_API_KEY` מוצפן ב-GitHub Secrets — לעולם לא נחשף בקוד
- הדשבורד מוגן בסיסמא מוצפנת SHA-256
- נתוני ה-JSON גלויים לכל (repo פומבי) — אין בהם מידע אישי רגיש
