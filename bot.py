"""
Button Poll Bot — স্ক্রিনশটের মতো বাটন পোল (নিজের কোড, কপি না)
মেনু: Make Poll | My Profile | Statistics | Support
কাজ: Make Poll -> প্রশ্ন লেখো -> অপশনগুলো আলাদা লাইনে লেখো
      -> বট বাটন পোল পাঠাবে, ভোট দিলে সংখ্যা অটোমেটিক বাড়বে।

বৈশিষ্ট্য:
• প্রতিটা অপশনের পাশে ভোটের সংখ্যা দেখায়: "২৪ | অপশন"
• মোট ভোট (Total Votes) অটোমেটিক আপডেট হয়
• একজন একটাই ভোট দিতে পারবে — নতুন অপশনে ভোট দিলে পুরনো অপশন থেকে
  ভোট কেটে নতুনটায় যোগ হবে, অটোমেটিক
• "ভোট প্রত্যাহার করুন" চাপলে ভোট কেটে যাবে, সংখ্যা কমে যাবে
• "পোল বন্ধ করুন" শুধু পোল যে বানিয়েছে সেই চাপতে পারবে
• My Profile: নিজের নাম, ইউজারনেম, ইউজার আইডি, মোট পোল দেখায়
• Statistics: মোট ব্যবহারকারী, মোট পোল, মোট ভোট, চলমান পোল দেখায়
  (চ্যানেল/গ্রুপ সংখ্যা দেখানো হয় না, কারণ বট সেই তথ্য ট্র্যাক করে না)
• Support: সাহায্যের লেখা + চ্যানেলের বাটন। ২৪/৭ টিমের দাবি করা হয় না,
  কারণ টিম নেই — উত্তর দেওয়ার চেষ্টা করা হবে, এটাই লেখা আছে।
• চ্যানেলে বট নিজে পোস্ট করতে চাইলে বটকে চ্যানেলের অ্যাডমিন করতে হবে
  (Post Messages পারমিশন সহ)। নিজে ফরওয়ার্ড করলে অ্যাডমিন লাগবে না।
• চ্যানেল/গ্রুপ ছাড়লে ভোট অটোমেটিক কাটা যায় না — Telegram বটকে
  চ্যানেল সাবস্ক্রাইবার ছাড়ার আপডেট দেয় না। তাই ভোট কাটাতে হলে
  "ভোট প্রত্যাহার করুন" বাটনই নিয়ম।

চ্যানেল: https://t.me/TonmoyDeveloperBD24
অ্যাডমিন প্যানেল: /admin — শুধু ADMIN_ID-র মানুষটা ব্যবহার করতে পারবে।
  /admin দিয়ে Support-এর contact/link বদলানো যায়, কোডে হাত দিতে হয় না।
  ডিফল্ট Support = চ্যানেলের লিংক।
চালানো: Render Environment-এ BOT_TOKEN + ADMIN_ID বসিয়ে -> python bot.py
  ADMIN_ID = সংখ্যা (নাম্বার) আইডি, @username না। @userinfobot-এ /start
  দিলে নিজের সংখ্যা আইডি পাওয়া যায়।
টোকেন কোথাও কোডে লেখা নেই — শুধু Environment থেকে আসবে।
"""

import json
import os
import sqlite3
import threading

from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poll_bot.db")
CHANNEL_URL = "https://t.me/TonmoyDeveloperBD24"
CHANNEL_NAME = "Tonmoy Developer"

QUESTION, OPTIONS, ADMIN_SUPPORT = range(3)

MENU = ReplyKeyboardMarkup(
    [
        ["📊 Make Poll"],
        ["👤 My Profile", "📈 Statistics"],
        ["📞 Support"],
    ],
    resize_keyboard=True,
)

CHANNEL_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("🌐 আমাদের চ্যানেল", url=CHANNEL_URL)]]
)

HELP_TEXT = (
    "🤖 *Button Poll Bot* — যা করতে পারি:\n\n"
    "📊 Make Poll — প্রশ্ন আর অপশন দিলেই বাটন পোল বানিয়ে দিই\n"
    "👤 My Profile — নিজের প্রোফাইল কার্ড দেখায়\n"
    "📈 Statistics — বটের লাইভ পরিসংখ্যান দেখায়\n"
    "📞 Support — সাহায্যের জন্য যোগাযোগের তথ্য দেয়\n\n"
    "নিয়ম:\n"
    "• প্রশ্ন: ১ লাইন, সর্বোচ্চ ৩০০ অক্ষর\n"
    "• অপশন: কমপক্ষে ২টি, সর্বোচ্চ ১০টি\n"
    "• প্রতিটা অপশন আলাদা লাইনে লিখতে হবে\n"
    "• প্রতিটা অপশন সর্বোচ্চ ১০০ অক্ষর\n\n"
    "ভোটের নিয়ম:\n"
    "• একজন একটাই ভোট দিতে পারবে\n"
    "• নতুন অপশনে ভোট দিলে পুরনো ভোট কেটে নতুনটায় যোগ হবে\n"
    "• ভোট প্রত্যাহার করলে সংখ্যা কমে যাবে\n"
    "• পোল বন্ধ শুধু পোল বানানো মানুষটা করতে পারবে\n\n"
    "বাতিল করতে চাইলে /cancel লেখো।"
)


# ---------------- database ----------------
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS polls ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "chat_id INTEGER, message_id INTEGER, creator_id INTEGER, "
        "question TEXT, options TEXT, is_closed INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS votes ("
        "poll_id INTEGER, user_id INTEGER, option_index INTEGER, "
        "PRIMARY KEY (poll_id, user_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings ("
        "key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()
    return conn


def get_support():
    conn = db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key='support'"
    ).fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return CHANNEL_URL


def set_support(value):
    conn = db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('support', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (value,),
    )
    conn.commit()
    conn.close()


def support_url(value):
    v = value.strip()
    if v.startswith("http://") or v.startswith("https://"):
        return v
    if v.startswith("@"):
        return "https://t.me/" + v[1:]
    if v.startswith("t.me/"):
        return "https://" + v
    return CHANNEL_URL


def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


def get_counts(poll_id):
    conn = db()
    rows = conn.execute(
        "SELECT option_index, COUNT(*) FROM votes WHERE poll_id=? GROUP BY option_index",
        (poll_id,),
    ).fetchall()
    conn.close()
    counts = {}
    total = 0
    for idx, cnt in rows:
        counts[idx] = cnt
        total += cnt
    return counts, total


def build_keyboard(poll_id, options, closed=False):
    if closed:
        return None
    counts, _total = get_counts(poll_id)
    keyboard = []
    for i, opt in enumerate(options):
        cnt = counts.get(i, 0)
        keyboard.append(
            [InlineKeyboardButton(f"{cnt} | {opt}", callback_data=f"vote:{poll_id}:{i}")]
        )
    keyboard.append(
        [InlineKeyboardButton("🔄 ভোট প্রত্যাহার করুন", callback_data=f"withdraw:{poll_id}")]
    )
    keyboard.append(
        [InlineKeyboardButton("🛑 পোল বন্ধ করুন", callback_data=f"close:{poll_id}")]
    )
    return InlineKeyboardMarkup(keyboard)


def poll_text(question, options, poll_id, closed=False):
    counts, total = get_counts(poll_id)
    lines = [f"📊 {question}", "", f"📈 Total Votes: {total}", ""]
    for i, opt in enumerate(options):
        lines.append(f"{counts.get(i, 0)} | {opt}")
    if closed:
        lines.append("")
        lines.append("🛑 পোল বন্ধ হয়ে গেছে।")
    else:
        lines.append("")
        lines.append("ভোট দিতে অপশনে চাপ দাও।")
    return "\n".join(lines)


# ---------------- keep-alive ----------------
web = Flask(__name__)


@web.route("/")
def home():
    return "Button Poll Bot is running ✅"


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    web.run(host="0.0.0.0", port=port)


# ---------------- menu: start / profile / statistics / support ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Button Poll Bot*-এ স্বাগতম!\n\nপোল বানাতে নিচের বাটন চাপো 👇",
        reply_markup=MENU,
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, reply_markup=MENU, parse_mode="Markdown")
    return ConversationHandler.END


async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = db()
    total_polls = conn.execute(
        "SELECT COUNT(*) FROM polls WHERE creator_id=?", (user.id,)
    ).fetchone()[0]
    conn.close()
    username = f"@{user.username}" if user.username else "নেই"
    profile_link = f"https://t.me/{user.username}" if user.username else "নেই"
    text = (
        "👑 USER PROFILE CARD\n"
        "Account Information & Settings\n"
        "──────────────────────\n\n"
        "👤 Identity\n"
        f" ├ Name: {user.full_name}\n"
        f" ├ Username: {username}\n"
        f" └ User ID: {user.id}\n\n"
        "📊 পোল পরিসংখ্যান\n"
        f" └ মোট পোল: {total_polls} টি\n\n"
        "⚙️ Details\n"
        " ├ Tier: No Premium\n"
        " ├ Language: Bangla 🇧🇩\n"
        f" └ Message ID: {update.message.message_id}\n\n"
        "🔗 Quick Actions\n"
        f" 💬 Contact • 🔗 Profile Link ({profile_link})\n\n"
        "──────────────────────\n"
        f"📢 Channel: {CHANNEL_NAME}"
    )
    await update.message.reply_text(
        text, reply_markup=CHANNEL_KEYBOARD
    )
    return ConversationHandler.END


async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    total_polls = conn.execute("SELECT COUNT(*) FROM polls").fetchone()[0]
    total_votes = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    active_polls = conn.execute(
        "SELECT COUNT(*) FROM polls WHERE is_closed=0"
    ).fetchone()[0]
    total_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM ("
        "SELECT creator_id AS user_id FROM polls "
        "UNION SELECT user_id FROM votes)"
    ).fetchone()[0]
    conn.close()
    text = (
        "✨ লাইভ স্ট্যাটিস্টিকস ✨\n\n"
        f"💡 বটের মালিক: {CHANNEL_NAME}\n"
        f"👥 মোট ব্যবহারকারী: {total_users}\n"
        f"📊 মোট পোল: {total_polls}\n"
        f"📈 মোট ভোট: {total_votes}\n"
        f"⚡ চলমান পোল: {active_polls}\n"
        "⚡ বট ভার্সন: 1.0.0\n\n"
        "💡 আপনার মতামত আমাদের জন্য গুরুত্বপূর্ণ!"
    )
    await update.message.reply_text(text, reply_markup=CHANNEL_KEYBOARD)
    return ConversationHandler.END


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_value = get_support()
    text = (
        "✨ সাপোর্টের জন্য যোগাযোগ করুন\n\n"
        "যদি কোনো সমস্যা বা সাহায্যের প্রয়োজন হয়, নিচের বাটনে ক্লিক করুন।\n\n"
        "📌 আপনার প্রশ্নের উত্তর দেওয়ার চেষ্টা করা হবে।\n\n"
        f"💬 Support: {support_value}\n"
        f"📢 চ্যানেল: {CHANNEL_NAME}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💬 সরাসরি সাহায্য পেতে ক্লিক করুন",
                    url=support_url(support_value),
                )
            ]
        ]
    )
    await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END


# ---------------- admin panel: /admin -> Support সেট করা ----------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID == 0:
        await update.message.reply_text(
            "⚠️ অ্যাডমিন সেট করা হয়নি।\n"
            "Render Environment-এ ADMIN_ID বসাও (সংখ্যা আইডি, @username না), "
            "তারপর redeploy করো, তারপর /admin দাও।",
            reply_markup=MENU,
        )
        return ConversationHandler.END
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ এই প্যানেল শুধু অ্যাডমিনের জন্য।", reply_markup=MENU
        )
        return ConversationHandler.END
    current = get_support()
    await update.message.reply_text(
        f"🔧 অ্যাডমিন প্যানেল\n\nবর্তমান Support: {current}\n\n"
        "Support বদলাতে নিচের বাটন চাপো 👇",
        reply_markup=ReplyKeyboardMarkup(
            [["📞 Support সেট করো"], ["⬅️ মূল মেনু"]],
            resize_keyboard=True,
        ),
    )
    return ConversationHandler.END


async def admin_ask_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ এই প্যানেল শুধু অ্যাডমিনের জন্য।", reply_markup=MENU
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "📞 নতুন Support-এর contact/link লেখো।\n"
        "উদাহরণ: @TonmoyDeveloperBD24 বা https://t.me/TonmoyDeveloperBD24\n"
        "বাতিল করতে /cancel লেখো।",
        reply_markup=ReplyKeyboardMarkup([["❌ বাতিল"]], resize_keyboard=True),
    )
    return ADMIN_SUPPORT


async def admin_save_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ এই প্যানেল শুধু অ্যাডমিনের জন্য।", reply_markup=MENU
        )
        return ConversationHandler.END
    value = update.message.text.strip()
    if not value:
        await update.message.reply_text("⚠️ খালি লেখা দেওয়া যাবে না, আবার লেখো:")
        return ADMIN_SUPPORT
    set_support(value)
    await update.message.reply_text(
        f"✅ Support সেট করা হয়েছে: {value}\n\n"
        "এখন থেকে Support বাটনে এটাই দেখাবে।",
        reply_markup=MENU,
    )
    return ConversationHandler.END


async def admin_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("মূল মেনুতে ফিরে গেছো।", reply_markup=MENU)
    return ConversationHandler.END


# ---------------- creation flow ----------------
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ আপনার পোলের জন্য প্রশ্ন পাঠান\n\n"
        "পোল বানানোর নিয়ম:\n"
        "১. প্রথমে প্রশ্ন পাঠাও (১ লাইনে, সর্বোচ্চ ৩০০ অক্ষর)\n"
        "২. তারপর অপশনগুলো আলাদা লাইনে পাঠাও (কমপক্ষে ২টি, সর্বোচ্চ ১০টি)\n\n"
        "📢 চ্যানেলে পোল পোস্ট করতে চাইলে: বটকে চ্যানেলের অ্যাডমিন দিতে হবে\n"
        "(Post Messages পারমিশন সহ)। নিজে ফরওয়ার্ড করলে অ্যাডমিন লাগবে না।\n\n"
        "লেখা সাজাতে চাইলে (শুধু প্রশ্নের লেখায় কাজ করবে, বাটনে না):\n"
        "➡️ মোটা লিখতে হলে: <b>আপনার লেখা</b>\n"
        "➡️ বাঁকা লিখতে হলে: <i>আপনার লেখা</i>\n"
        "➡️ কোডের মতো লিখতে: <code>আপনার লেখা</code>\n\n"
        "✅ এখন আপনার প্রশ্ন পাঠান:",
        reply_markup=ReplyKeyboardMarkup([["❌ বাতিল"]], resize_keyboard=True),
    )
    return QUESTION


async def ask_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()
    if len(question) > 300:
        await update.message.reply_text(
            "⚠️ প্রশ্নটা ৩০০ অক্ষরের বেশি হয়ে গেছে। ছোট করে আবার লেখো:"
        )
        return QUESTION
    context.user_data["question"] = question
    await update.message.reply_text(
        "✅ প্রশ্ন ঠিক আছে।\n\n"
        "এবার অপশনগুলো লেখো — প্রতিটা অপশন আলাদা লাইনে:\n"
        "যেমন:\n"
        "অপশন ১\n"
        "অপশন ২\n"
        "অপশন ৩"
    )
    return OPTIONS


async def make_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    options = [line.strip() for line in update.message.text.splitlines() if line.strip()]
    if len(options) < 2:
        await update.message.reply_text(
            "⚠️ কমপক্ষে ২টি অপশন লাগবে। আবার লেখো (প্রতিটা আলাদা লাইনে):"
        )
        return OPTIONS
    if len(options) > 10:
        await update.message.reply_text(
            "⚠️ সর্বোচ্চ ১০টি অপশন দেওয়া যাবে। কমিয়ে আবার লেখো:"
        )
        return OPTIONS
    if any(len(opt) > 100 for opt in options):
        await update.message.reply_text(
            "⚠️ একটা অপশন ১০০ অক্ষরের বেশি হয়ে গেছে। ছোট করে আবার লেখো:"
        )
        return OPTIONS

    question = context.user_data.get("question", "পোল")
    creator_id = update.effective_user.id
    chat_id = update.effective_chat.id

    conn = db()
    cur = conn.execute(
        "INSERT INTO polls (chat_id, message_id, creator_id, question, options, is_closed) "
        "VALUES (?, 0, ?, ?, ?, 0)",
        (chat_id, creator_id, question, json.dumps(options, ensure_ascii=False)),
    )
    poll_id = cur.lastrowid
    conn.commit()
    conn.close()

    text = poll_text(question, options, poll_id, closed=False)
    keyboard = build_keyboard(poll_id, options, closed=False)
    try:
        # প্রশ্নে <b> / <i> / <code> থাকলে সেটা সাজিয়ে দেখাবে
        sent = await update.message.reply_text(
            text, reply_markup=keyboard, parse_mode="HTML"
        )
    except Exception:
        # ট্যাগ ভুল হলে সাধারণ লেখা হিসেবে পাঠাবে, যাতে পোল আটকে না যায়
        sent = await update.message.reply_text(text, reply_markup=keyboard)

    conn = db()
    conn.execute("UPDATE polls SET message_id=? WHERE id=?", (sent.message_id, poll_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "🎉 পোল তৈরি! উপরের পোলে ভোট দিতে পারো।\n"
        "এই মেসেজটা চ্যানেল/গ্রুপে ফরওয়ার্ড করলেও বাটন কাজ করবে।\n"
        "আরেকটা বানাতে চাইলে 📊 Make Poll চাপো।",
        reply_markup=MENU,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ পোল বানানো বাতিল করা হয়েছে।", reply_markup=MENU)
    return ConversationHandler.END


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "পোল বানাতে 📊 Make Poll চাপো, অথবা /start লেখো।", reply_markup=MENU
    )


# ---------------- voting ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        action, poll_id_str, *rest = query.data.split(":")
        poll_id = int(poll_id_str)
    except Exception:
        await query.answer("ভুল বাটন।", show_alert=True)
        return

    user_id = query.from_user.id
    conn = db()
    row = conn.execute(
        "SELECT chat_id, message_id, creator_id, question, options, is_closed "
        "FROM polls WHERE id=?",
        (poll_id,),
    ).fetchone()
    if not row:
        conn.close()
        await query.answer("এই পোল আর পাওয়া যাচ্ছে না।", show_alert=True)
        return
    chat_id, message_id, creator_id, question, options_json, is_closed = row
    options = json.loads(options_json)

    if is_closed:
        conn.close()
        await query.answer("পোল বন্ধ হয়ে গেছে।", show_alert=True)
        return

    if action == "vote":
        idx = int(rest[0])
        existing = conn.execute(
            "SELECT option_index FROM votes WHERE poll_id=? AND user_id=?",
            (poll_id, user_id),
        ).fetchone()
        if existing and existing[0] == idx:
            conn.close()
            await query.answer("তুমি already এই অপশনেই ভোট দিয়েছো।", show_alert=True)
            return
        conn.execute(
            "INSERT INTO votes (poll_id, user_id, option_index) VALUES (?, ?, ?) "
            "ON CONFLICT(poll_id, user_id) DO UPDATE SET option_index=excluded.option_index",
            (poll_id, user_id, idx),
        )
        conn.commit()
        msg = "✅ ভোট দেওয়া হয়েছে।"
    elif action == "withdraw":
        cur = conn.execute(
            "DELETE FROM votes WHERE poll_id=? AND user_id=?", (poll_id, user_id)
        )
        if cur.rowcount == 0:
            conn.commit()
            conn.close()
            await query.answer("তুমি কোনো ভোট দাওনি।", show_alert=True)
            return
        conn.commit()
        msg = "🔄 ভোট প্রত্যাহার করা হয়েছে, সংখ্যা কমে গেছে।"
    elif action == "close":
        if user_id != creator_id:
            conn.close()
            await query.answer(
                "শুধু পোল যে বানিয়েছে সেই বন্ধ করতে পারবে।", show_alert=True
            )
            return
        conn.execute("UPDATE polls SET is_closed=1 WHERE id=?", (poll_id,))
        conn.commit()
        conn.close()
        text = poll_text(question, options, poll_id, closed=True)
        try:
            await query.edit_message_text(text, reply_markup=None, parse_mode="HTML")
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=None)
            except Exception:
                pass
        await query.answer("🛑 পোল বন্ধ করা হয়েছে।", show_alert=True)
        return
    else:
        conn.close()
        return
    conn.close()

    text = poll_text(question, options, poll_id, closed=False)
    keyboard = build_keyboard(poll_id, options, closed=False)
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            pass
    await query.answer(msg)


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN পাওয়া যায়নি — Render Environment-এ BOT_TOKEN বসাও, তারপর আবার চালাও।"
        )

    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    poll_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📊 Make Poll$"), ask_question),
        ],
        states={
            QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_options),
            ],
            OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, make_poll),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ বাতিল$"), cancel),
        ],
    )

    admin_conv = ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_panel),
            MessageHandler(filters.Regex("^📞 Support সেট করো$"), admin_ask_support),
        ],
        states={
            ADMIN_SUPPORT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_save_support),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ বাতিল$"), cancel),
            MessageHandler(filters.Regex("^⬅️ মূল মেনু$"), admin_back_to_menu),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(admin_conv)
    app.add_handler(poll_conv)
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Regex("^👤 My Profile$"), my_profile))
    app.add_handler(MessageHandler(filters.Regex("^📈 Statistics$"), statistics))
    app.add_handler(MessageHandler(filters.Regex("^📞 Support$"), support))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

    print("Button Poll Bot চালু হয়েছে ✅")
    app.run_polling()


if __name__ == "__main__":
    main()
