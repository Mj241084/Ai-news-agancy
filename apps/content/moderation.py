from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from django.conf import settings

# ۱. کلمات کوتاه یا ریشه‌ای که اگر داخل کلمه مجاز دیگری باشند نباید فیلتر شوند
# (مثلاً "کس" در "عکس"، یا "کونی" در "مسکونی"، یا "لاشی" در "متلاشی")
DEFAULT_EXACT_BLOCKED_WORDS = (
    "کیر", "کیری", "کص", "کس", "عن", "گوه",
    "کونی", "لاشی", "تخمی", "بگا", "بگام",
    "cum", "ass", "dick", "slut", "whore"
)

# ۲. کلماتی که در هر حالتی نوشته شوند نامناسب هستند (حتی چسبیده به کلمات دیگر)
DEFAULT_SUBSTRING_BLOCKED_WORDS = (
    "کصکش", "کسکش", "جنده", "جاکش", "حرومی", "حرومزاده",
    "مادرجنده", "مادرقحبه", "ننه_قحبه", "خوارکسه", "خواهرکسه", 
    "پفیوز", "دیوث", "گاییدم",
    "fuck", "motherfucker", "bitch", "asshole", "bullshit"
)

_ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
    "ؤ": "و", "أ": "ا", "إ": "ا", "آ": "ا"
})

# حذف اعراب و نیم‌فاصله‌ها
_DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670\u0640\u200c\u200d]")

def clean_text_for_filtering(text: str) -> str:
    """
    متن را یکدست می‌کند و تمام علائم نگارشی را حذف می‌کند اما فاصله‌ها و حروف را نگه می‌دارد.
    مثال: "f.u.c.k! کیر" -> "f u c k کیر"
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.translate(_ARABIC_TO_PERSIAN)
    # Leetspeak normalization: map latin 'i' between Persian letters to 'ی'
    text = re.sub(r"(?<=[\u0600-\u06FF])[iı](?=[\u0600-\u06FF])", "ی", text)
    text = _DIACRITICS_RE.sub("", text)
    # تمام کاراکترهایی که حرف، عدد یا فاصله نیستند را حذف کن
    text = re.sub(r'[^\w\s]', '', text)
    return text

@lru_cache(maxsize=1)
def _get_compiled_blocked_patterns() -> list[re.Pattern]:
    """
    الگوهای رگولار اکسپرشن هوشمند را برای هر کلمه تولید می‌کند.
    """
    exact_words = getattr(settings, "COMMENT_EXACT_BLOCKED_WORDS", DEFAULT_EXACT_BLOCKED_WORDS)
    substring_words = getattr(settings, "COMMENT_SUBSTRING_BLOCKED_WORDS", DEFAULT_SUBSTRING_BLOCKED_WORDS)
    
    patterns =[]
    
    # پردازش کلمات Exact (مثل "کیر" یا "کس")
    for word in exact_words:
        cleaned_word = clean_text_for_filtering(str(word)).strip()
        if not cleaned_word:
            continue
        # تبدیل "کیر" به الگوی: \bک+\s*ی+\s*ر+\b
        # این الگو هم "ککککک یییی رررر" را می‌گیرد، هم "ک ی ر" را، اما "دستگیره" را نمی‌گیرد.
        parts =[re.escape(char) + r"+" for char in cleaned_word.replace(" ", "")]
        regex_str = r"\b" + r"\s*".join(parts) + r"\b"
        patterns.append(re.compile(regex_str))

    # پردازش کلمات Substring (مثل "کصکش")
    for word in substring_words:
        cleaned_word = clean_text_for_filtering(str(word)).strip()
        if not cleaned_word:
            continue
        # تبدیل "کصکش" به الگوی: ک+\s*ص+\s*ک+\s*ش+
        # نیازی به \b (مرز کلمه) ندارد.
        parts = [re.escape(char) + r"+" for char in cleaned_word.replace(" ", "")]
        regex_str = r"\s*".join(parts)
        patterns.append(re.compile(regex_str))

    return patterns

def contains_blocked_comment_word(text: str) -> bool:
    cleaned_text = clean_text_for_filtering(text)
    if not cleaned_text:
        return False
        
    patterns = _get_compiled_blocked_patterns()
    for pattern in patterns:
        if pattern.search(cleaned_text):
            return True
            
    return False