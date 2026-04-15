import re
from datetime import datetime

def clean_onpe_date(date_text):
    """Convierte '14/04/2026 A LAS 05:04:16 p. m.' a formato ISO datestring."""
    clean_text = date_text.replace("ACTUALIZADO AL ", "").replace(" A LAS ", " ").strip()
    clean_text = clean_text.replace("p. m.", "PM").replace("a. m.", "AM")
    try:
        dt = datetime.strptime(clean_text, "%d/%m/%Y %I:%M:%S %p")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return clean_text

def extract_number(text):
    """Limpia números con formato peruano (ej: 27'325,432 o 21.585 % *) -> 27325432 o 21.585"""
    if not text or text == "-":
        return "-"
    # Limpiamos apóstrofes, comas, porcentajes y asteriscos
    clean_text = text.replace("'", "").replace(",", "").replace("%", "").replace("*", "").strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", clean_text)
    return nums[0] if nums else "0"

def calculate_absolute_voters(percentage_str, total_electores):
    """Convierte un porcentaje (ej. '59.928') a cantidad de personas reales."""
    try:
        pct = float(extract_number(percentage_str))
        return int(round((pct / 100.0) * float(total_electores)))
    except Exception:
        return 0