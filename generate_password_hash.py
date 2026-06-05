#!/usr/bin/env python3
"""
הרץ סקריפט זה פעם אחת כדי לייצר hash לסיסמא שלך.
את ה-hash המתקבל הדבק ב-index.html במשתנה PASSWORD_HASH.

שימוש:
    python generate_password_hash.py
"""

import hashlib
import getpass

def hash_password(password: str) -> str:
    """SHA-256 with a fixed salt — good enough for client-side protection."""
    salt = "sensibo-dashboard-v1"
    return hashlib.sha256((salt + password).encode()).hexdigest()

def main():
    print("=" * 50)
    print("  🔑  Sensibo Dashboard — Password Setup")
    print("=" * 50)
    print()
    pw  = getpass.getpass("הכנס סיסמא חדשה:       ")
    pw2 = getpass.getpass("הכנס שוב לאימות:       ")

    if pw != pw2:
        print("\n❌  הסיסמאות אינן תואמות. נסה שוב.")
        return

    if len(pw) < 4:
        print("\n⚠️   הסיסמא קצרה מדי (מינימום 4 תווים).")
        return

    h = hash_password(pw)
    print()
    print("✅  Hash נוצר בהצלחה:")
    print()
    print(f"    {h}")
    print()
    print("📋  הדבק את השורה הבאה ב-index.html")
    print("    (החלף את הערך של PASSWORD_HASH):")
    print()
    print(f'    const PASSWORD_HASH = "{h}";')
    print()

if __name__ == "__main__":
    main()
