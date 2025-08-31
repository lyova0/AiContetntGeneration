# bot.py
import asyncio
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
import calendar as cal
from google import genai

# ----------------- Настройки -----------------
load_dotenv()
BOT_TOKEN = "8060762724:AAFXjNaBbnPOtlPUp0rJpF1YBAxepH7wHMg"
# В некоторых конфигурациях ключ называется OPENAI_API_KEY или GOOGLE_API_KEY
GOOGLE_API_KEY = "AIzaSyDuRm1NgCLhNp9mBJzska8t3cmJiPfmeOU"
DB_PATH = os.getenv("DB_PATH", "calendar.db")
TRANSLATIONS_DB = os.getenv("TRANSLATIONS_DB", "translations.db")

if not BOT_TOKEN or not GOOGLE_API_KEY:
    raise RuntimeError("Set BOT_TOKEN and OPENAI_API_KEY / GOOGLE_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GOOGLE_API_KEY)

MAX_FREE_REQUESTS = 5  # бесплатные запросы в день

# ----------------- Временные хранилища -----------------
user_state = {}            # {user_id: state dict or string}
pending_post_calendar = {} # {token: {"user_id": uid, "text": text}}
user_language = {}         # {user_id: "ru"|"en"|"am"}
user_requests = {}         # {user_id: {"count": int, "last_reset": datetime}}

# ----------------- Инициализация translations.db -----------------
def init_translations_db(path=TRANSLATIONS_DB):
    if os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE translations (
        key TEXT,
        lang TEXT,
        text TEXT,
        PRIMARY KEY (key, lang)
    )
    """)
    data = [
        ("start", "ru", "👋 Привет! Выберите язык:"),
        ("start", "en", "👋 Hello! Choose your language:"),
        ("start", "am", "👋 Բարև! Ընտրեք լեզուն:"),
        ("menu", "ru", "✅ Язык установлен: Русский\n\nУслуги:\n/idea — идеи постов и рилсов\n/calendar — календарь постов\n/tip — советы дня\n/language — сменить язык"),
        ("menu", "en", "✅ Language set: English\n\nServices:\n/idea — post & reels ideas\n/calendar — post calendar\n/tip — daily tips\n/language — change language"),
        ("menu", "am", "✅ Լեզուն ընտրված է՝ Հայերեն\n\nԾառայություններ:\n/idea — գրառումների և ռիլսերի գաղափարներ\n/calendar — գրառումների օրացույց\n/tip — օրվա խորհուրդներ\n/language — փոխել լեզուն"),
        ("choose_lang", "ru", "Выберите язык:"),
        ("choose_lang", "en", "Choose your language:"),
        ("choose_lang", "am", "Ընտրեք լեզուն:"),
        ("ask_niche", "ru", "✏️ Отлично! Напиши, какая у тебя ниша, и я сгенерирую идеи."),
        ("ask_niche", "en", "✏️ Great! Tell me your niche and I’ll generate ideas."),
        ("ask_niche", "am", "✏️ Գերազանց։ Նշիր քո թեման, և ես գաղափարներ կստեղծեմ։"),
        ("limit", "ru", "❌ Лимит 5 запросов в день. Попробуйте завтра или поддержите проект для безлимита."),
        ("limit", "en", "❌ Limit of 5 requests per day. Try again tomorrow or support for unlimited access."),
        ("limit", "am", "❌ Օրվա սահմանաչափը՝ 5 հարցումներ։ Փորձեք վաղը։"),
        ("calendar_menu", "ru", "Выберите действие:"),
        ("calendar_menu", "en", "Choose an action:"),
        ("calendar_menu", "am", "Ընտրեք գործողությունը:"),
        ("show_posts", "ru", "📅 Показать запланированные посты"),
        ("show_posts", "en", "📅 Show scheduled posts"),
        ("show_posts", "am", "📅 Ցուցադրել պլանավորված գրառումները"),
        ("add_post", "ru", "📝 Добавить свой пост"),
        ("add_post", "en", "📝 Add your post"),
        ("add_post", "am", "📝 Ավելացնել սեփական գրառում"),
        ("gen_random", "ru", "🎲 Сгенерировать случайный пост"),
        ("gen_random", "en", "🎲 Generate a random post"),
        ("gen_random", "am", "🎲 Ստեղծել պատահական գրառում"),
        ("choose_date", "ru", "📆 Выберите дату (только будущее):"),
        ("choose_date", "en", "📆 Choose a date (future only):"),
        ("choose_date", "am", "📆 Ընտրեք ամսաթիվը (միայն մոտիկ ապագա):"),
        ("choose_hour", "ru", "⏰ Выберите час (учитываются только будущие):"),
        ("choose_hour", "en", "⏰ Choose an hour (future only):"),
        ("choose_hour", "am", "⏰ Ընտրեք ժամը (միայն ապագա):"),
        ("reminder_choice", "ru", "Когда напомнить?"),
        ("reminder_choice", "en", "When to remind?"),
        ("reminder_choice", "am", "Երբ հիշեցում ուղարկել?"),
        ("rem_1440", "ru", "За 24 часа"),
        ("rem_1440", "en", "24 hours before"),
        ("rem_1440", "am", "24 ժամ առաջ"),
        ("rem_60", "ru", "За 1 час"),
        ("rem_60", "en", "1 hour before"),
        ("rem_60", "am", "1 ժամ առաջ"),
        ("rem_10", "ru", "За 10 минут"),
        ("rem_10", "en", "10 minutes before"),
        ("rem_10", "am", "10 րոպե առաջ"),
        ("rem_none", "ru", "Без напоминания"),
        ("rem_none", "en", "No reminder"),
        ("rem_none", "am", "Առանց հիշեցման"),
        ("added", "ru", "✅ Пост запланирован!"),
        ("added", "en", "✅ Post scheduled!"),
        ("added", "am", "✅ Գրառումը պլանավորվեց։"),
        ("no_posts", "ru", "📭 Ваш календарь пуст."),
        ("no_posts", "en", "📭 Your calendar is empty."),
        ("no_posts", "am", "📭 Ձեր օրացույցը դատարկ է։"),
        ("status_sent", "ru", "✅ Отправлен"),
        ("status_sent", "en", "✅ Sent"),
        ("status_sent", "am", "✅ Ուղարկված է"),
        ("status_scheduled", "ru", "⏳ Запланирован"),
        ("status_scheduled", "en", "⏳ Scheduled"),
        ("status_scheduled", "am", "⏳ Պլանավորված"),
        ("mark_posted", "ru", "Отметить как опубликованный"),
        ("mark_posted", "en", "Mark as posted"),
        ("mark_posted", "am", "Նշել որպես հրապարակված"),
        ("delete", "ru", "Удалить"),
        ("delete", "en", "Delete"),
        ("delete", "am", "Ջնջել"),
        ("posted_ok", "ru", "🎉 Готово! Отмечено как опубликованное."),
        ("posted_ok", "en", "🎉 Great! Marked as posted."),
        ("posted_ok", "am", "🎉 Պատրաստ է։ Նշվեց որպես հրապարակված։"),
        ("deleted_ok", "ru", "🗑️ Удалено из календаря."),
        ("deleted_ok", "en", "🗑️ Deleted from calendar."),
        ("deleted_ok", "am", "🗑️ Հեռացվեց օրացույցից։"),
        ("reminder", "ru", "⏰ Напоминание: ваш пост выйдет скоро:"),
        ("reminder", "en", "⏰ Reminder: your post is coming soon:"),
        ("reminder", "am", "⏰ Հիշեցում․ ձեր գրառումը շուտով կհրապարակվի․"),
        ("add_to_calendar", "ru", "Добавить в календарь"),
        ("add_to_calendar", "en", "Add to calendar"),
        ("add_to_calendar", "am", "Ավելացնել օրացույցում"),
        ("write_your_post", "ru", "✏️ Отправьте текст своего поста:"),
        ("write_your_post", "en", "✏️ Send the text of your post:"),
        ("write_your_post", "am", "✏️ Ուղարկեք ձեր գրառման տեքստը:"),
        ("post_label", "ru", "Идея поста"),
        ("post_label", "en", "Post idea"),
        ("post_label", "am", "Գրառման գաղափար"),
        ("reel_label", "ru", "Идея рилса"),
        ("reel_label", "en", "Reel idea"),
        ("reel_label", "am", "Ռիլսի գաղափար"),
        ("gen_fail", "ru", "❌ Генерация идей не удалась. Попробуйте снова."),
        ("gen_fail", "en", "❌ Idea generation failed. Please try again."),
        ("gen_fail", "am", "❌ Գաղափարների ստեղծումը չստացվեց։"),
    ]
    cur.executemany("INSERT INTO translations(key, lang, text) VALUES (?, ?, ?)", data)
    conn.commit()
    conn.close()

init_translations_db()

# ----------------- Функция получения перевода -----------------
def get_translation(key, lang):
    try:
        conn = sqlite3.connect(TRANSLATIONS_DB)
        cur = conn.cursor()
        cur.execute("SELECT text FROM translations WHERE key=? AND lang=?", (key, lang))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else key
    except Exception:
        return key

# ----------------- Инициализация DB календаря -----------------
if not os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        post_text TEXT,
        publish_datetime TEXT,
        sent INTEGER DEFAULT 0,
        reminded INTEGER DEFAULT 0,
        reminder_offset INTEGER DEFAULT 1440
    )
    """)
    conn.commit()
    conn.close()

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cols = [c[1] for c in cursor.execute("PRAGMA table_info(posts)").fetchall()]
if 'reminder_offset' not in cols:
    try:
        cursor.execute("ALTER TABLE posts ADD COLUMN reminder_offset INTEGER DEFAULT 1440")
        conn.commit()
    except Exception:
        pass

# ----------------- Лимит запросов -----------------
def check_limit(user_id):
    now = datetime.now()
    data = user_requests.get(user_id)
    if not data or (now - data["last_reset"]).days >= 1:
        user_requests[user_id] = {"count": 0, "last_reset": now}
        return True
    return data["count"] < MAX_FREE_REQUESTS

def increment_requests(user_id):
    if user_id not in user_requests:
        user_requests[user_id] = {"count": 1, "last_reset": datetime.now()}
    else:
        user_requests[user_id]["count"] += 1

# ----------------- UI helpers -----------------
def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇦🇲 Հայերեն", callback_data="lang:am")]
    ])

def calendar_menu_kb(uid):
    lang = user_language.get(uid, "ru")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_translation("show_posts", lang), callback_data="show_posts")],
        [InlineKeyboardButton(text=get_translation("add_post", lang), callback_data="custom_post")],
        [InlineKeyboardButton(text=get_translation("gen_random", lang), callback_data="gen_random")]
    ])

def add_to_calendar_kb(token, uid):
    lang = user_language.get(uid, "ru")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_translation("add_to_calendar", lang), callback_data=f"calendar:{token}")]
    ])

def post_item_kb(uid, pid, sent):
    if sent:
        return None
    lang = user_language.get(uid, "ru")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_translation("mark_posted", lang), callback_data=f"posted:{pid}")],
        [InlineKeyboardButton(text=get_translation("delete", lang), callback_data=f"delete:{pid}")]
    ])

# ----------------- Календарь (реквизиты клавиатуры) -----------------
def month_header(uid, year, month, token=None):
    name = cal.month_name[month]
    token_part = f":{token}" if token else ""
    return [
        InlineKeyboardButton(text="«", callback_data=f"cal:prev:{year}:{month}{token_part}"),
        InlineKeyboardButton(text=f"{name} {year}", callback_data="ignore"),
        InlineKeyboardButton(text="»", callback_data=f"cal:next:{year}:{month}{token_part}")
    ]

def weekday_row(uid):
    lang = user_language.get(uid, "ru")
    if lang == "ru":
        wd = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    elif lang == "am":
        wd = ["Երկ","Երք","Չոր","Հնգ","Ուր","Շբ","Կիր"]
    else:
        wd = ["Mo","Tu","We","Th","Fr","Sa","Su"]
    return [InlineKeyboardButton(text=w, callback_data="ignore") for w in wd]

def create_month_calendar(uid, year=None, month=None, token=None):
    now = datetime.now()
    if year is None: year = now.year
    if month is None: month = now.month

    first_wd, last_day = cal.monthrange(year, month)  # first_wd: 0=Mon
    grid = []
    week = []

    # Fill empty days before first weekday
    for _ in range(first_wd):
        week.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

    for day in range(1, last_day+1):
        # disable past days in current month
        if year == now.year and month == now.month and day < now.day:
            week.append(InlineKeyboardButton(text=str(day), callback_data="ignore"))
        else:
            cb = f"pickday:{year}:{month}:{day}"
            week.append(InlineKeyboardButton(text=str(day), callback_data=cb))
        if len(week) == 7:
            grid.append(week)
            week = []

    if week:
        while len(week) < 7:
            week.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        grid.append(week)

    kb = [month_header(uid, year, month, token), weekday_row(uid)]
    kb.extend(grid)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def create_hour_keyboard(uid, year, month, day):
    now = datetime.now()
    rows = []
    row = []
    for h in range(24):
        if year == now.year and month == now.month and day == now.day and h <= now.hour:
            row.append(InlineKeyboardButton(text=f"{h:02d}:00", callback_data="ignore"))
        else:
            row.append(InlineKeyboardButton(text=f"{h:02d}:00", callback_data=f"pickhour:{h}"))
        if len(row) == 6:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ----------------- Gemini helper (retry with backoff) -----------------
async def generate_with_retry(prompt, retries=4, base_delay=1):
    delay = base_delay
    last_exc = None
    for i in range(retries):
        try:
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            text = getattr(resp, "text", None)
            if text:
                return text
            last_exc = Exception("Empty response")
        except Exception as e:
            last_exc = e
            # if overloaded, wait and retry
            await asyncio.sleep(delay)
            delay *= 2
    raise last_exc

# ----------------- Генерация идей -----------------
async def generate_ideas(uid, niche):
    lang = user_language.get(uid, "ru")
    human = {"ru": "Русский", "en": "English", "am": "Armenian"}[lang]
    prompt = (
        f"Язык ответа: {human}. Ты эксперт по маркетингу и контенту.\n"
        "Сгенерируй 3 идеи для постов и 2 идеи для рилсов для ниши ниже.\n"
        "Строго пометь идеи токенами на отдельных строках: /post1, /post2, /post3, /reel1, /reel2.\n"
        "Идеи пиши строго по этому принципу: заголовок/ Подробный сценарий /текст под пост или рилс /хештеги \n"
        "После каждого токена дай готовый текст идеи (заголовок, суть, CTA, визуал).\n"
        f"Ответ должен быть на языке: {human}.\nНиша: {niche}"
    )
    try:
        answer = await generate_with_retry(prompt)
    except Exception:
        await bot.send_message(uid, get_translation("gen_fail", lang))
        return

    # разделяем по токенам (учитываем варианты с кириллицей тоже)
    parts = re.split(r'(/post\d+|/reel\d+|/пост\d+|/рилс\d+)', answer, flags=re.IGNORECASE)
    ideas = []
    for i in range(1, len(parts), 2):
        tag = parts[i].strip()
        text = parts[i+1].strip() if i+1 < len(parts) else ""
        ideas.append((tag, text))

    if not ideas:
        # fallback: отправим всё как один блок
        token = str(uuid.uuid4())
        pending_post_calendar[token] = {"user_id": uid, "text": answer}
        await bot.send_message(uid, answer, reply_markup=add_to_calendar_kb(token, uid))
        return

    for tag, text in ideas:
        token = str(uuid.uuid4())
        pending_post_calendar[token] = {"user_id": uid, "text": text}
        label_key = "post_label" if re.search(r'post|пост', tag, re.IGNORECASE) else "reel_label"
        label = get_translation(label_key, lang)
        await bot.send_message(uid, f"{label}\n\n{text}", reply_markup=add_to_calendar_kb(token, uid))

# ----------------- Обработчики команд -----------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        get_translation("start", "ru") + "\n\n" + get_translation("start", "en") + "\n\n" + get_translation("start", "am"),
        reply_markup=lang_keyboard()
    )

@dp.message(Command("language"))
async def cmd_language(message: Message):
    uid = message.from_user.id
    await message.answer(get_translation("choose_lang", user_language.get(uid, "ru")), reply_markup=lang_keyboard())

@dp.message(Command("tip"))
async def cmd_tip(message: Message):
    uid = message.from_user.id
    lang = user_language.get(uid, "ru")
    tips = {
        "ru": ["🎯 Ставь цель для каждого поста — вовлечь, продать или обучить!", "🔥 Первые 3 секунды — ключевые!"],
        "en": ["🎯 Give each post a goal: engage, sell, or educate.", "🔥 First 3 seconds are crucial!"],
        "am": ["🎯 Յուրաքանչյուր գրառման համար նշիր նպատակ։", "🔥 Առաջին 3 վայրկյանը կարևոր է։"]
    }
    tip = tips[lang][datetime.now().day % len(tips[lang])]
    await message.answer(get_translation("tip_title", lang) + "\n" + tip)

@dp.message(Command("idea"))
async def cmd_idea(message: Message):
    uid = message.from_user.id
    user_state[uid] = "waiting_for_niche"
    await message.answer(get_translation("ask_niche", user_language.get(uid, "ru")))

@dp.message(Command("calendar"))
async def cmd_calendar(message: Message):
    uid = message.from_user.id
    await message.answer(get_translation("calendar_menu", user_language.get(uid, "ru")), reply_markup=calendar_menu_kb(uid))

# ----------------- Callback router (все inline-кнопки) -----------------
@dp.callback_query()
async def cb_router(query: CallbackQuery):
    uid = query.from_user.id
    data = (query.data or "")

    # language selection: "lang:en"
    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        user_language[uid] = lang
        user_state.pop(uid, None)
        await query.message.answer(get_translation("menu", lang))
        await query.answer()
        return

    if data == "ignore":
        await query.answer()
        return

    # calendar menu:
    if data == "show_posts":
        lang = user_language.get(uid, "ru")
        cursor.execute("SELECT id, post_text, publish_datetime, sent FROM posts WHERE user_id=? ORDER BY publish_datetime", (uid,))
        rows = cursor.fetchall()
        if not rows:
            await query.message.answer(get_translation("no_posts", lang))
        else:
            for pid, text, dt, sent in rows:
                status = get_translation("status_sent", lang) if sent else get_translation("status_scheduled", lang)
                await query.message.answer(f"{text}\n🕒 {dt if dt else '-'} | {status}", reply_markup=post_item_kb(uid, pid, sent))
        await query.answer()
        return

    if data == "custom_post":
        user_state[uid] = {"step": "await_custom_text"}
        await query.message.answer(get_translation("write_your_post", user_language.get(uid, "ru")))
        await query.answer()
        return

    if data == "gen_random":
        lang = user_language.get(uid, "ru")
        human = {"ru": "Русский", "en": "English", "am": "Armenian"}[lang]
        prompt = (
            f"Language: {human}. Generate a single practical social media post idea for a content creator.\n"
            "Return it in the user's language. Put token /post1 on its own line before the idea.\n"
            "Include CTA and visual suggestions."
        )
        try:
            text = await generate_with_retry(prompt)
        except Exception:
            await query.message.answer(get_translation("gen_fail", lang))
            await query.answer()
            return
        # parse token /post1 optionally
        parts = re.split(r'(/post\d+)', text, flags=re.IGNORECASE)
        idea_text = parts[2].strip() if len(parts) >= 3 else text
        token = str(uuid.uuid4())
        pending_post_calendar[token] = {"user_id": uid, "text": idea_text}
        await query.message.answer(get_translation("post_label", lang) + "\n\n" + idea_text, reply_markup=add_to_calendar_kb(token, uid))
        await query.answer()
        return

    # add idea to calendar: calendar:token
    if data.startswith("calendar:"):
        token = data.split(":", 1)[1]
        pending = pending_post_calendar.get(token)
        if not pending or pending.get("user_id") != uid:
            await query.answer(get_translation("gen_fail", user_language.get(uid, "ru")))
            return
        now = datetime.now()
        user_state[uid] = {"step": "calendar_pick_day", "year": now.year, "month": now.month, "token": token}
        await query.message.answer(get_translation("choose_date", user_language.get(uid, "ru")), reply_markup=create_month_calendar(uid, now.year, now.month, token))
        await query.answer()
        return

    # calendar month navigation: cal:prev:YYYY:MM[:token]
    if data.startswith("cal:"):
        parts = data.split(":")
        # parts example: ["cal", "prev", "2025", "8", "<token>"]
        if len(parts) < 4:
            await query.answer()
            return
        cmd = parts[1]
        year = int(parts[2]); month = int(parts[3])
        token = parts[4] if len(parts) >= 5 else None
        today = datetime.now()
        if cmd == "prev":
            # allow prev only if resulting month >= current month
            new_month = month - 1
            new_year = year
            if new_month == 0:
                new_month = 12; new_year -= 1
            # prevent navigating to months completely in the past
            if new_year < today.year or (new_year == today.year and new_month < today.month):
                await query.answer()
                return
            year, month = new_year, new_month
        else:  # next
            new_month = month + 1
            new_year = year
            if new_month == 13:
                new_month = 1; new_year += 1
            year, month = new_year, new_month

        st = user_state.get(uid, {}) or {}
        st.update({"step": "calendar_pick_day", "year": year, "month": month})
        if token:
            st["token"] = token
        user_state[uid] = st
        try:
            await query.message.edit_reply_markup(reply_markup=create_month_calendar(uid, year, month, token))
        except Exception:
            await query.message.answer(create_month_calendar(uid, year, month, token))
        await query.answer()
        return

    # pickday:pickday:YYYY:MM:DD
    if data.startswith("pickday:"):
        parts = data.split(":")
        if len(parts) != 4:  # should be pickday:YYYY:MM:DD
            await query.answer()
            return
        y, mo, d = int(parts[1]), int(parts[2]), int(parts[3])
        now = datetime.now()
        if y == now.year and mo == now.month and d < now.day:
            await query.answer()
            return
        st = user_state.get(uid, {}) or {}
        st.update({"step": "calendar_pick_hour", "year": y, "month": mo, "day": d})
        user_state[uid] = st
        await query.message.answer(get_translation("choose_hour", user_language.get(uid, "ru")), reply_markup=create_hour_keyboard(uid, y, mo, d))
        await query.answer()
        return

    # pick hour: pickhour:H
    if data.startswith("pickhour:"):
        parts = data.split(":")
        if len(parts) != 2:
            await query.answer()
            return
        hour = int(parts[1])
        st = user_state.get(uid)
        if not st or st.get("step") != "calendar_pick_hour":
            await query.answer()
            return
        token = st.get("token")
        if not token:
            await query.answer(get_translation("gen_fail", user_language.get(uid, "ru")))
            return
        pending = pending_post_calendar.get(token)
        if not pending:
            await query.answer(get_translation("gen_fail", user_language.get(uid, "ru")))
            return
        text = pending.get("text")
        y, mo, day = st["year"], st["month"], st["day"]
        publish_dt = datetime(y, mo, day, hour, 0)
        st.update({"step": "choose_reminder", "publish_dt": publish_dt.isoformat()})
        user_state[uid] = st
        lang = user_language.get(uid, "ru")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_translation("rem_1440", lang), callback_data="rem:1440")],
            [InlineKeyboardButton(text=get_translation("rem_60", lang), callback_data="rem:60")],
            [InlineKeyboardButton(text=get_translation("rem_10", lang), callback_data="rem:10")],
            [InlineKeyboardButton(text=get_translation("rem_none", lang), callback_data="rem:-1")],
        ])
        await query.message.answer(get_translation("reminder_choice", lang), reply_markup=kb)
        await query.answer()
        return

    # reminder selection rem:X
    if data.startswith("rem:"):
        parts = data.split(":")
        if len(parts) != 2:
            await query.answer()
            return
        minutes = int(parts[1])
        st = user_state.get(uid)
        if not st or st.get("step") != "choose_reminder":
            await query.answer()
            return
        publish_dt = datetime.fromisoformat(st.get("publish_dt"))
        token = st.get("token")
        pending = pending_post_calendar.get(token)
        if not pending:
            await query.answer(get_translation("gen_fail", user_language.get(uid, "ru")))
            return
        text = pending.get("text")
        cursor.execute(
            "INSERT INTO posts (user_id, post_text, publish_datetime, sent, reminded, reminder_offset) VALUES (?,?,?,?,?,?)",
            (uid, text, publish_dt.strftime("%Y-%m-%d %H:%M"), 0, 0, (minutes if minutes >= 0 else -1))
        )
        conn.commit()
        await query.message.answer(f"{get_translation('added', user_language.get(uid, 'ru'))}\n{text}\n🕒 {publish_dt.strftime('%Y-%m-%d %H:%M')}")
        pending_post_calendar.pop(token, None)
        user_state.pop(uid, None)
        await query.answer()
        return

    # delete
    if data.startswith("delete:"):
        pid = int(data.split(":",1)[1])
        cursor.execute("DELETE FROM posts WHERE id=?", (pid,))
        conn.commit()
        await query.message.answer(get_translation("deleted_ok", user_language.get(uid, "ru")))
        await query.answer()
        return

    # posted
    if data.startswith("posted:"):
        pid = int(data.split(":",1)[1])
        cursor.execute("UPDATE posts SET sent=1 WHERE id=?", (pid,))
        conn.commit()
        await query.message.answer(get_translation("posted_ok", user_language.get(uid, "ru")))
        await query.answer()
        return

    await query.answer()

# ----------------- Обработчик входящих текстовых сообщений ---------------
@dp.message()
async def messages_handler(message: Message):
    uid = message.from_user.id
    st = user_state.get(uid)

    # awaiting custom post text
    if isinstance(st, dict) and st.get("step") == "await_custom_text":
        text = message.text.strip()
        if not text:
            await message.answer("❌ Empty text")
            return
        token = str(uuid.uuid4())
        pending_post_calendar[token] = {"user_id": uid, "text": text}
        now = datetime.now()
        user_state[uid] = {"step": "calendar_pick_day", "year": now.year, "month": now.month, "token": token}
        await message.answer(get_translation("choose_date", user_language.get(uid, "ru")), reply_markup=create_month_calendar(uid, now.year, now.month, token))
        return

    # niche input for /idea
    if st == "waiting_for_niche":
        if not check_limit(uid):
            await message.answer(get_translation("limit", user_language.get(uid, "ru")))
            return
        user_state[uid] = None
        increment_requests(uid)
        niche = message.text.strip()
        await generate_ideas(uid, niche)
        return

    # otherwise ignore or handle other free text
    # (could add more flows here)
    return

# ----------------- Reminder background task -----------------
async def reminder_task():
    while True:
        now = datetime.now()
        cursor.execute("SELECT id, user_id, post_text, publish_datetime, reminded, reminder_offset FROM posts WHERE sent=0")
        rows = cursor.fetchall()
        for pid, uid, text, dt_s, reminded, offset in rows:
            try:
                publish_dt = datetime.strptime(dt_s, "%Y-%m-%d %H:%M")
            except Exception:
                continue
            if offset is None:
                offset = 1440
            # if offset < 0 => no reminder
            if offset < 0:
                continue
            remind_time = publish_dt - timedelta(minutes=offset)
            # send reminder if not yet sent and now >= remind_time
            if not reminded and now >= remind_time:
                lang = user_language.get(uid, "ru")
                try:
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_translation("mark_posted", lang), callback_data=f"posted:{pid}")]
                    ])
                    await bot.send_message(uid, f"{get_translation('reminder', lang)}\n{text}\n🕒 {dt_s}", reply_markup=kb)
                    cursor.execute("UPDATE posts SET reminded=1 WHERE id=?", (pid,))
                    conn.commit()
                except Exception:
                    # ignore send failures (user blocked bot etc.)
                    pass
        await asyncio.sleep(30)

# ----------------- Запуск -----------------
async def main():
    # старт фоновой задачи
    asyncio.create_task(reminder_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

