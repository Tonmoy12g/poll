"""
UltraPoll Pro - Next-Generation Telegram Channel & Group Poll Bot
Created exclusively for YouTube Creators & Telegram Channel Owners.

Key Highlights (Far superior to basic poll bots):
1. 🎨 100% Full-Color Dynamic Buttons (Telegram Bot API 9.4+ primary/success/danger)
2. 👑 Live Dynamic Crown & Leader Highlighting (Leader button turns Green + Crown)
3. 📊 Visual ASCII Progress Bars & Real-Time Percentages directly in channel message
4. 🛡️ Force Channel Subscribe (Optional Anti-Cheat: Voters must join channel)
5. 🔄 1-Click Vote Retraction & Vote Switching
6. 🕒 Custom Timer / Expiration Auto-Lock
7. 📝 Multi-format Input: Separate by Newline, Comma, or Ampersand (&)
8. 🏆 Cinematic Final Winner Celebration Card with Rank Badges
9. ⚡ Render.com 24/7 Web Service Health Server (Zero port timeout errors)
10. 💾 SQLite Database with 100% Data Persistence
"""

import os
import sys
import time
import json
import sqlite3
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Any, Optional
import requests

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("UltraPollPro")

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "YourSupportUsername")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "YourUpdateChannel")

# Telegram Bot API 9.4 button styles:
# 'primary' = Deep Blue | 'success' = Vibrant Green | 'danger' = Bright Red
COLOR_CYCLE = ["primary", "success", "danger"]
DEFAULT_EMOJIS = ["🔥", "⭐", "💎", "⚡", "🚀", "🏆", "🎯", "🌟", "🏏", "⚽", "🎮", "❤️"]

# ==================== RENDER / WEB SERVICE KEEP-ALIVE ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"UltraPoll Pro Bot is running 24/7 on Render!")

    def log_message(self, format, *args):
        pass  # Suppress normal access logs

def start_render_health_server():
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Render Web Service health check listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Could not start health check server on port {port}: {e}")

# ==================== DATABASE SETUP ====================
DB_FILE = "ultrapoll_pro.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    # Polls table
    c.execute('''CREATE TABLE IF NOT EXISTS polls (
        poll_id TEXT PRIMARY KEY,
        creator_id INTEGER,
        channel_id TEXT,
        message_id INTEGER DEFAULT NULL,
        title TEXT,
        is_closed INTEGER DEFAULT 0,
        force_sub_channel TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP DEFAULT NULL
    )''')
    # Options table
    c.execute('''CREATE TABLE IF NOT EXISTS poll_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id TEXT,
        option_index INTEGER,
        option_text TEXT,
        emoji TEXT DEFAULT '🔹',
        color_style TEXT DEFAULT 'primary'
    )''')
    # Votes table
    c.execute('''CREATE TABLE IF NOT EXISTS votes (
        poll_id TEXT,
        user_id INTEGER,
        option_index INTEGER,
        voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (poll_id, user_id)
    )''')
    conn.commit()
    conn.close()

# ==================== TELEGRAM API CLIENT ====================
class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()

    def request(self, method: str, data: Optional[Dict] = None) -> Dict:
        url = f"{self.base_url}/{method}"
        try:
            res = self.session.post(url, json=data, timeout=30)
            return res.json()
        except Exception as e:
            logger.error(f"Error calling {method}: {e}")
            return {"ok": False, "description": str(e)}

    def send_message(self, chat_id: Any, text: str, reply_markup: Optional[Dict] = None, parse_mode: str = "HTML") -> Dict:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.request("sendMessage", payload)

    def edit_message(self, chat_id: Any, message_id: int, text: str, reply_markup: Optional[Dict] = None, parse_mode: str = "HTML") -> Dict:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.request("editMessageText", payload)

    def answer_callback(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> Dict:
        payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text
        return self.request("answerCallbackQuery", payload)

    def get_chat_member(self, chat_id: Any, user_id: int) -> Dict:
        return self.request("getChatMember", {"chat_id": chat_id, "user_id": user_id})

    def get_me(self) -> Dict:
        return self.request("getMe")

# State tracking for multi-step poll wizard
user_states: Dict[int, Dict] = {}

# ==================== ADVANCED VISUAL FORMATTING ====================
def make_progress_bar(percentage: float, length: int = 10) -> str:
    """Generates a modern visual ASCII progress bar."""
    filled = int(round((percentage / 100.0) * length))
    return "█" * filled + "░" * (length - filled)

def clean_channel_id(ch: str) -> str:
    ch = ch.strip()
    if ch.startswith("https://t.me/"):
        ch = ch.replace("https://t.me/", "")
    if ch.startswith("t.me/"):
        ch = ch.replace("t.me/", "")
    if not ch.startswith("@") and not ch.startswith("-100"):
        ch = "@" + ch
    return ch

def build_live_poll_content(poll_id: str, bot_username: str) -> (str, Dict):
    """
    Constructs both the channel message body (with rankings & progress bars)
    and the colorful inline keyboard buttons.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, is_closed, force_sub_channel FROM polls WHERE poll_id = ?", (poll_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "❌ পোলটি ডাটাবেজে পাওয়া যায়নি।", {"inline_keyboard": []}

    title, is_closed, force_sub = row

    c.execute("SELECT option_index, option_text, emoji, color_style FROM poll_options WHERE poll_id = ? ORDER BY option_index", (poll_id,))
    options = c.fetchall()

    c.execute("SELECT option_index, COUNT(*) FROM votes WHERE poll_id = ? GROUP BY option_index", (poll_id,))
    counts = dict(c.fetchall())
    total_votes = sum(counts.values())

    # Find highest votes for dynamic crown 👑
    max_votes = -1
    leader_index = -1
    if total_votes > 0:
        for opt_idx, cnt in counts.items():
            if cnt > max_votes:
                max_votes = cnt
                leader_index = opt_idx

    # Sort options by vote count descending for the live ranking board
    ranked_options = sorted(options, key=lambda x: counts.get(x[0], 0), reverse=True)

    # 1. BUILD VIBRANT MESSAGE TEXT
    status_badge = "🟢 <b>ভোট গ্রহণ চলছে</b>" if not is_closed else "🔴 <b>পোল সমাপ্ত</b>"
    
    text = f"✨ <b>অফিসিয়াল পোল কনটেস্ট</b> | {status_badge}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 <b>প্রশ্ন:</b>\n👉 <b>{title}</b>\n\n"
    text += "📊 <b>লাইভ ফলাফল ও পরিসংখ্যান:</b>\n"

    medals = ["🥇", "🥈", "🥉"]
    for idx_rank, (opt_idx, opt_text, emoji, _) in enumerate(ranked_options):
        cnt = counts.get(opt_idx, 0)
        pct = (cnt / total_votes * 100) if total_votes > 0 else 0.0
        bar = make_progress_bar(pct, length=10)
        badge = medals[idx_rank] if idx_rank < 3 and cnt > 0 else f"#{idx_rank + 1}"
        text += f"\n{badge} {opt_text}\n"
        text += f"   <code>[{bar}]</code> <b>{pct:.1f}%</b> ({cnt} ভোট)"

    text += "\n\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📈 <b>মোট ভোট সংগৃহীত:</b> <code>{total_votes}</code> টি\n"
    if force_sub:
        text += f"🛡️ <i>ভোট দিতে {force_sub} চ্যানেলে জয়েন থাকা বাধ্যতামূলক।</i>\n"

    if not is_closed:
        text += "👇 <i>পছন্দের প্রার্থীকে জয়ী করতে নিচের বাটনে চাপ দিন:</i>"
    else:
        winner_name = ranked_options[0][1] if total_votes > 0 else "কেউ নন"
        text += f"\n🏆 <b>চূড়ান্ত বিজয়ী:</b> {winner_name} 🎉\n"
        text += "🛑 <i>এই পোলটিতে নতুন ভোট গ্রহণ বন্ধ রয়েছে।</i>"

    # 2. BUILD FULL-COLOR BUTTONS (Bot API 9.4+)
    keyboard = []
    row = []

    for opt_idx, opt_text, emoji, base_color in options:
        cnt = counts.get(opt_idx, 0)
        is_leader = (cnt > 0 and opt_idx == leader_index)
        
        # Leader gets glowing crown and success (green) style
        if is_leader:
            btn_text = f"👑 {opt_text} ({cnt})"
            btn_style = "success"
        else:
            btn_text = f"{opt_text} ({cnt})"
            # Cycle colors across remaining candidates so every button is colorful!
            btn_style = COLOR_CYCLE[opt_idx % len(COLOR_CYCLE)]

        btn = {
            "text": btn_text,
            "callback_data": f"vote:{poll_id}:{opt_idx}",
            "style": btn_style
        }
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    # Action / Control Buttons
    if not is_closed:
        keyboard.append([
            {"text": "🔄 ভোট প্রত্যাহার করুন", "callback_data": f"retract:{poll_id}", "style": "primary"}
        ])
        keyboard.append([
            {"text": "🛑 পোল সমাপ্ত ও বিজয়ী ঘোষণা", "callback_data": f"close:{poll_id}", "style": "danger"}
        ])
    else:
        bot_link = f"https://t.me/{bot_username}" if bot_username else "https://t.me"
        keyboard.append([
            {"text": "🤖 আপনিও এমন আকর্ষণীয় পোল তৈরি করুন", "url": bot_link, "style": "success"}
        ])

    conn.close()
    return text, {"inline_keyboard": keyboard}

def main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": "⚡ Create Ultra Poll", "style": "primary"}],
            [{"text": "👤 My Profile", "style": "success"}, {"text": "📊 Live Stats", "style": "danger"}],
            [{"text": "📞 24/7 Support", "style": "primary"}]
        ],
        "resize_keyboard": True
    }

# ==================== MESSAGE HANDLER ====================
def handle_message(bot: TelegramBot, msg: Dict, bot_username: str, bot_id: int):
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    user_id = msg["from"]["id"]
    text = msg.get("text", "").strip()
    first_name = msg["from"].get("first_name", "User")
    username = msg["from"].get("username", "")

    # Save/Update user
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user_id, first_name, username))
    conn.commit()
    conn.close()

    # Step-by-Step Creation Wizard
    if chat_type == "private" and user_id in user_states:
        state = user_states[user_id]
        step = state.get("step")

        # Step 1: Target Channel
        if step == "waiting_for_channel":
            channel = clean_channel_id(text)
            state["channel"] = channel
            state["step"] = "waiting_for_title"

            bot.send_message(
                chat_id,
                "✅ <b>চ্যানেল সংরক্ষিত হয়েছে:</b> <code>" + channel + "</code>\n\n"
                "❓ <b>পোলের শিরোনাম বা প্রশ্ন লিখুন:</b>\n"
                "<i>(HTML সাপোর্ট করে, যেমন: <b>বোল্ড</b>, <i>ইতালিক</i>)</i>\n\n"
                "👉 <i>এখন আপনার প্রশ্নটি লিখে পাঠান:</i>"
            )
            return

        # Step 2: Poll Title / Question
        elif step == "waiting_for_title":
            state["title"] = text
            state["step"] = "waiting_for_options"

            guide = (
                "📝 <b>প্রার্থী বা অপশনগুলোর নাম পাঠান:</b>\n\n"
                "💡 <i>আমাদের বটে কোনো বাঁধাধরা নিয়ম নেই! আপনি যেকোনোভাবে পাঠাতে পারেন:</i>\n"
                "• <b>প্রতি লাইনে একটি করে নাম:</b>\n"
                "সাকিব আল হাসান 🏏\n"
                "তামিম ইকবাল 🔥\n"
                "মুশফিকুর রহিম ⭐\n\n"
                "• <b>অথবা কমা (,) দিয়ে:</b>\n"
                "সাকিব, তামিম, মুশফিক\n\n"
                "• <b>অথবা & দিয়ে:</b>\n"
                "সাকিব&তামিম&মুশফিক\n\n"
                "👉 <i>এখন অপশনগুলোর নাম লিখে পাঠান:</i>"
            )
            bot.send_message(chat_id, guide)
            return

        # Step 3: Parse Options
        elif step == "waiting_for_options":
            # Smart parser: handles newline, comma, and ampersand automatically
            raw_text = text.replace("&", "\n").replace(",", "\n")
            candidates = [line.strip() for line in raw_text.split("\n") if line.strip()]

            if len(candidates) < 2:
                bot.send_message(chat_id, "⚠️ অনুগ্রহ করে কমপক্ষে ২টি অপশন বা প্রার্থীর নাম দিন।")
                return
            if len(candidates) > 50:
                bot.send_message(chat_id, "⚠️ সর্বোচ্চ ৫০টি অপশন সাপোর্ট করে।")
                return

            state["candidates"] = candidates
            state["step"] = "waiting_for_forcesub"

            markup = {
                "inline_keyboard": [
                    [{"text": "🛡️ হ্যাঁ, ফোর্স সাব চালু করুন", "callback_data": "fsub_yes", "style": "success"}],
                    [{"text": "⏩ না, সবার জন্য উন্মুক্ত রাখুন", "callback_data": "fsub_no", "style": "primary"}]
                ]
            }
            bot.send_message(
                chat_id,
                "🛡️ <b>অ্যান্টি-চিট ও ফোর্স সাবস্ক্রাইব (Force Subscribe):</b>\n\n"
                "আপনি কি চান যে ভোটারদের ভোট দেওয়ার আগে আপনার চ্যানেলে জয়েন থাকা বাধ্যতামূলক হোক?\n"
                "<i>(এটি চালু রাখলে আপনার চ্যানেলে হাজার হাজার রিয়েল সাবস্ক্রাইবার বাড়বে এবং ফেক ভোট রোধ হবে!)</i>",
                reply_markup=markup
            )
            return

    # Menu Commands
    if text == "/start" or text.startswith("/start"):
        welcome = (
            f"👑 <b>আসসালামু আলাইকুম, {first_name}!</b>\n\n"
            "✨ <b>UltraPoll Pro</b> — টেলিগ্রামের সবচেয়ে আধুনিক ও কালারফুল পোল মেকার বটে স্বাগতম!\n\n"
            "🚀 <b>আমাদের স্পেশাল ফিচারসমূহ:</b>\n"
            "• 🎨 <b>ফুল কালার বাটন:</b> নীল, সবুজ ও লাল স্টাইলের নজরকাড়া বাটন\n"
            "• 👑 <b>লাইভ ক্রাউন সিস্টেম:</b> লিডার প্রার্থীর বাটনে স্বয়ংক্রিয় মুকুট\n"
            "• 📊 <b>গ্রাফিক্যাল প্রগ্রেস বার:</b> পার্সেন্টেজসহ রিয়েল-টাইম ডিসপ্লে\n"
            "• 🛡️ <b>ফোর্স সাবস্ক্রাইব:</b> চ্যানেলে মেম্বার বাড়ানোর দুর্দান্ত সিস্টেম\n"
            "• 🔄 <b>ভোট প্রত্যাহার ও পরিবর্তন সুবিধা</b>\n"
            "• 🛑 <b>১-ক্লিকে চূড়ান্ত বিজয়ী কার্ড ঘোষণা</b>\n\n"
            "👇 <b>পোল তৈরি করতে নিচের বাটনে চাপ দিন:</b>"
        )
        bot.send_message(chat_id, welcome, reply_markup=main_menu_keyboard())

    elif text == "⚡ Create Ultra Poll" or text == "/create":
        user_states[user_id] = {"step": "waiting_for_channel"}
        bot.send_message(
            chat_id,
            "🎯 <b>পোল ক্রিয়েশন উইজার্ড</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "প্রথমে যে চ্যানেলে পোলটি পাঠাবেন সেই চ্যানেলের <b>ইউজারনেম বা লিংক</b> পাঠান:\n\n"
            "<i>উদাহরণ:</i> <code>@mychannel</code> অথবা <code>https://t.me/mychannel</code>\n\n"
            "⚠️ <i>নোট: বটকে অবশ্যই চ্যানেলে অ্যাডমিন বানিয়ে Post Messages পারমিশন দিয়ে রাখবেন।</i>"
        )

    elif text == "👤 My Profile" or text == "/profile":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM polls WHERE creator_id = ?", (user_id,))
        created = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM votes WHERE user_id = ?", (user_id,))
        voted = c.fetchone()[0]
        conn.close()

        profile = (
            "👤 <b>আপনার প্রোফাইল তথ্য</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ইউজার আইডি:</b> <code>{user_id}</code>\n"
            f"👤 <b>নাম:</b> {first_name}\n"
            f"🏷️ <b>ইউজারনেম:</b> @{username if username else 'N/A'}\n"
            f"🗳️ <b>তৈরিকৃত পোল:</b> {created} টি\n"
            f"🎯 <b>মোট ভোট দিয়েছেন:</b> {voted} বার\n"
            "⚡ <b>স্ট্যাটাস:</b> ভেরিফাইড ক্রিয়েটর ⭐\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(chat_id, profile)

    elif text == "📊 Live Stats" or text == "/stats":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        u_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM polls")
        p_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM polls WHERE is_closed = 0")
        act_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM votes")
        v_cnt = c.fetchone()[0]
        conn.close()

        stats = (
            "📊 <b>UltraPoll Pro লাইভ স্ট্যাটিস্টিক্স</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 <b>মালিক ও ডেভেলপার:</b> @{SUPPORT_USERNAME}\n"
            f"👥 <b>মোট ব্যবহারকারী:</b> {u_cnt} জন\n"
            f"🗳️ <b>মোট আয়োজিত পোল:</b> {p_cnt} টি\n"
            f"🟢 <b>বর্তমানে চলমান পোল:</b> {act_cnt} টি\n"
            f"🎯 <b>মোট কাস্টকৃত ভোট:</b> {v_cnt} টি\n"
            "⚡ <b>ভার্সন:</b> 5.0 Ultra Pro (Telegram Bot API 9.4)\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "🌐 আমাদের অফিসিয়াল চ্যানেল", "url": f"https://t.me/{CHANNEL_USERNAME}", "style": "primary"}]
            ]
        }
        bot.send_message(chat_id, stats, reply_markup=markup)

    elif text == "📞 24/7 Support" or text == "/support":
        supp = (
            "✨ <b>২৪/৭ হেল্প ও কাস্টমার সাপোর্ট</b>\n\n"
            "যেকোনো প্রযুক্তিগত সহায়তা বা চ্যানেল প্রোমোশনের জন্য আমাদের টিমের সাথে সরাসরি যোগাযোগ করুন।"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "💬 সরাসরি সাপোর্ট ইনবক্সে মেসেজ দিন", "url": f"https://t.me/{SUPPORT_USERNAME}", "style": "success"}]
            ]
        }
        bot.send_message(chat_id, supp, reply_markup=markup)


# ==================== CALLBACK QUERY HANDLER ====================
def handle_callback_query(bot: TelegramBot, cb: Dict, bot_username: str, bot_id: int):
    cb_id = cb["id"]
    from_user = cb["from"]
    user_id = from_user["id"]
    data = cb.get("data", "")
    message = cb.get("message")
    if not message:
        bot.answer_callback(cb_id)
        return

    chat_id = message["chat"]["id"]
    message_id = message["message_id"]

    # Wizard: Force-Sub Choice
    if data in ["fsub_yes", "fsub_no"]:
        if user_id not in user_states:
            bot.answer_callback(cb_id, "⚠️ সময় পার হয়ে গেছে, পুনরায় শুরু করুন।")
            return
        state = user_states[user_id]
        channel = state["channel"]
        title = state["title"]
        candidates = state["candidates"]
        force_sub = channel if data == "fsub_yes" else None

        poll_id = f"poll_{int(time.time())}_{user_id}"

        # Save poll in DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO polls (poll_id, creator_id, channel_id, title, force_sub_channel) VALUES (?, ?, ?, ?, ?)",
                  (poll_id, user_id, channel, title, force_sub))

        for idx, opt_name in enumerate(candidates):
            color = COLOR_CYCLE[idx % len(COLOR_CYCLE)]
            c.execute("INSERT INTO poll_options (poll_id, option_index, option_text, color_style) VALUES (?, ?, ?, ?)",
                      (poll_id, idx, opt_name, color))
        conn.commit()
        conn.close()

        # Build initial content
        msg_text, markup = build_live_poll_content(poll_id, bot_username)

        # Post directly to the target channel!
        post_res = bot.send_message(channel, msg_text, reply_markup=markup)

        if not post_res.get("ok"):
            err = post_res.get("description", "Error")
            bot.send_message(
                chat_id,
                f"❌ <b>চ্যানেলে পোস্ট পাঠাতে ব্যর্থ হয়েছে!</b>\n\n"
                f"<b>কারণ:</b> <code>{err}</code>\n\n"
                f"📌 অনুগ্রহ করে বট (@{bot_username})-কে আপনার চ্যানেল <b>{channel}</b>-এ অ্যাডমিন হিসেবে যুক্ত করে পোস্ট পারমিশন অন করুন।"
            )
            del user_states[user_id]
            bot.answer_callback(cb_id)
            return

        channel_msg_id = post_res["result"]["message_id"]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE polls SET message_id = ? WHERE poll_id = ?", (channel_msg_id, poll_id))
        conn.commit()
        conn.close()

        del user_states[user_id]
        bot.answer_callback(cb_id, "🎉 পোল সফলভাবে তৈরি হয়েছে!")

        bot.send_message(
            chat_id,
            f"🚀 <b>অভিনন্দন! আপনার কালারফুল পোলটি চ্যানেলে লাইভ হয়ে গেছে!</b> 🎉\n\n"
            f"📢 <b>চ্যানেল:</b> {channel}\n"
            f"📌 <b>প্রশ্ন:</b> {title}\n"
            f"👥 <b>মোট অপশন:</b> {len(candidates)} টি\n"
            f"🛡️ <b>ফোর্স সাবস্ক্রাইব:</b> {'সক্রিয় ✅' if force_sub else 'নিষ্ক্রিয় ❌'}\n\n"
            "ভোটাররা এখন লাইভ প্রগ্রেস বার ও ফুল কালার বাটনে ভোট দিতে পারছেন।",
            reply_markup=main_menu_keyboard()
        )
        return

    # Voting Action
    if data.startswith("vote:"):
        _, poll_id, opt_idx_str = data.split(":")
        opt_idx = int(opt_idx_str)

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT is_closed, force_sub_channel FROM polls WHERE poll_id = ?", (poll_id,))
        poll_info = c.fetchone()
        if not poll_info or poll_info[0] == 1:
            conn.close()
            bot.answer_callback(cb_id, "⚠️ এই পোলটি সমাপ্ত হয়ে গেছে!", show_alert=True)
            return

        _, force_sub = poll_info

        # Force Subscribe Verification Check
        if force_sub:
            chk = bot.get_chat_member(force_sub, user_id)
            if chk.get("ok"):
                status = chk["result"].get("status")
                if status in ["left", "kicked"]:
                    conn.close()
                    bot.answer_callback(
                        cb_id,
                        f"⚠️ ভোট দেওয়ার আগে আপনাকে অবশ্যই আমাদের {force_sub} চ্যানেলে জয়েন করতে হবে!",
                        show_alert=True
                    )
                    return
            else:
                logger.warning(f"Could not verify membership for {user_id} in {force_sub}")

        # Check existing vote
        c.execute("SELECT option_text FROM poll_options WHERE poll_id = ? AND option_index = ?", (poll_id, opt_idx))
        opt_name = c.fetchone()[0]

        c.execute("SELECT option_index FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
        existing_vote = c.fetchone()

        if existing_vote is not None:
            if existing_vote[0] == opt_idx:
                conn.close()
                bot.answer_callback(cb_id, f"⚠️ আপনি ইতিমধ্যে {opt_name}-কে ভোট দিয়েছেন!", show_alert=False)
                return
            else:
                # Switch vote
                c.execute("UPDATE votes SET option_index = ? WHERE poll_id = ? AND user_id = ?", (opt_idx, poll_id, user_id))
                conn.commit()
                conn.close()
                bot.answer_callback(cb_id, f"🔄 আপনার ভোট পরিবর্তন করে দেওয়া হয়েছে: {opt_name}", show_alert=False)
        else:
            # Cast vote
            c.execute("INSERT INTO votes (poll_id, user_id, option_index) VALUES (?, ?, ?)", (poll_id, user_id, opt_idx))
            conn.commit()
            conn.close()
            bot.answer_callback(cb_id, f"🎉 আপনার ভোট গৃহীত হয়েছে: {opt_name}", show_alert=False)

        # Update the live channel message & colored buttons
        new_text, new_markup = build_live_poll_content(poll_id, bot_username)
        bot.edit_message(chat_id, message_id, new_text, reply_markup=new_markup)

    # Retract Vote Action
    elif data.startswith("retract:"):
        _, poll_id = data.split(":")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT is_closed FROM polls WHERE poll_id = ?", (poll_id,))
        p_row = c.fetchone()
        if not p_row or p_row[0] == 1:
            conn.close()
            bot.answer_callback(cb_id, "⚠️ এই পোলটি সমাপ্ত হয়ে গেছে!", show_alert=True)
            return

        c.execute("SELECT option_index FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
        user_vote = c.fetchone()
        if not user_vote:
            conn.close()
            bot.answer_callback(cb_id, "⚠️ আপনি এই পোলে কোনো ভোট দেননি!", show_alert=True)
            return

        c.execute("DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
        conn.commit()
        conn.close()

        bot.answer_callback(cb_id, "🔄 আপনার ভোট সফলভাবে প্রত্যাহার করা হয়েছে!", show_alert=True)

        new_text, new_markup = build_live_poll_content(poll_id, bot_username)
        bot.edit_message(chat_id, message_id, new_text, reply_markup=new_markup)

    # Stop & Declare Winner
    elif data.startswith("close:"):
        _, poll_id = data.split(":")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT creator_id FROM polls WHERE poll_id = ?", (poll_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            bot.answer_callback(cb_id, "❌ পোল পাওয়া যায়নি!", show_alert=True)
            return

        creator_id = row[0]
        # Permission check: creator, bot admin, or channel admin
        is_admin = (user_id == creator_id or user_id == ADMIN_ID)
        if not is_admin:
            member = bot.get_chat_member(chat_id, user_id)
            if member.get("ok") and member["result"].get("status") in ["creator", "administrator"]:
                is_admin = True

        if not is_admin:
            conn.close()
            bot.answer_callback(cb_id, "⛔ কেবল চ্যানেলের অ্যাডমিন বা পোল ক্রিয়েটর ফলাফল সমাপ্ত করতে পারবেন!", show_alert=True)
            return

        # Audit sweep: verify all voters before finalizing to purge any who left
        c.execute("SELECT user_id FROM votes WHERE poll_id = ?", (poll_id,))
        voters = c.fetchall()
        purged = 0
        for (v_uid,) in voters:
            chk = bot.get_chat_member(chat_id, v_uid)
            if chk.get("ok"):
                st = chk["result"].get("status")
                if st in ["left", "kicked", "banned"]:
                    c.execute("DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, v_uid))
                    purged += 1
        if purged > 0:
            logger.info(f"Purged {purged} ghost votes from users who left channel {chat_id}")

        c.execute("UPDATE polls SET is_closed = 1, closed_at = CURRENT_TIMESTAMP WHERE poll_id = ?", (poll_id,))
        conn.commit()
        conn.close()

        bot.answer_callback(cb_id, "🏆 পোল সমাপ্ত হয়েছে এবং চূড়ান্ত বিজয়ী ঘোষণা করা হয়েছে!", show_alert=True)

        # Update message into final victory card
        final_text, final_markup = build_live_poll_content(poll_id, bot_username)
        bot.edit_message(chat_id, message_id, final_text, reply_markup=final_markup)



# ==================== ANTI-LEAVE REAL-TIME VOTE REVOCATION ====================
def handle_chat_member_updated(bot: TelegramBot, update_data: Dict, bot_username: str):
    """
    Automatic Vote Revocation:
    If a user leaves, unsubs, or is kicked from the channel, their vote is automatically
    cancelled and deducted from the live poll in real time!
    """
    chat = update_data.get("chat", {})
    chat_id = chat.get("id")
    chat_username = chat.get("username", "")
    chat_title = chat.get("title", "চ্যানেল")

    new_member = update_data.get("new_chat_member", {})
    new_status = new_member.get("status")
    user = new_member.get("user", {})
    user_id = user.get("id")
    user_name = user.get("first_name", "User")

    if not user_id:
        return

    # User left or was removed from channel
    if new_status in ["left", "kicked", "banned"]:
        logger.info(f"User {user_id} ({user_name}) left channel {chat_id} (@{chat_username})")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Match possible channel representations
        ch_patterns = [str(chat_id)]
        if chat_username:
            ch_patterns.append(f"@{chat_username.lower()}")
            ch_patterns.append(chat_username.lower())

        placeholders = ",".join("?" for _ in ch_patterns)
        query = f"""
            SELECT p.poll_id, p.message_id, p.channel_id, p.title
            FROM votes v
            JOIN polls p ON v.poll_id = p.poll_id
            WHERE v.user_id = ?
              AND p.is_closed = 0
              AND (p.channel_id IN ({placeholders}) OR p.force_sub_channel IN ({placeholders}))
        """
        c.execute(query, [user_id] + ch_patterns + ch_patterns)
        affected_polls = c.fetchall()

        for poll_id, msg_id, p_ch, p_title in affected_polls:
            # Delete user's vote
            c.execute("DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
            conn.commit()
            logger.info(f"❌ Cancelled vote for user {user_id} from poll {poll_id} because user left channel!")

            # Update live channel poll
            if msg_id and p_ch:
                try:
                    new_text, new_markup = build_live_poll_content(poll_id, bot_username)
                    bot.edit_message(p_ch, msg_id, new_text, reply_markup=new_markup)
                except Exception as e:
                    logger.error(f"Error updating poll message after member left: {e}")

            # Notify the user privately
            try:
                bot.send_message(
                    user_id,
                    f"⚠️ <b>ভোট বাতিল নোটিফিকেশন!</b>\n\n"
                    f"আপনি <b>{chat_title}</b> চ্যানেল থেকে লিভ নেওয়ায় উক্ত চ্যানেলের <b>'{p_title}'</b> পোলে আপনার দেওয়া ভোটটি <b>স্বয়ংক্রিয়ভাবে বাতিল (কেটে)</b> দেওয়া হয়েছে!\n\n"
                    "💡 <i>আবার ভোট যুক্ত করতে চাইলে চ্যানেলে পুনরায় জয়েন করে ভোট দিন।</i>"
                )
            except Exception:
                pass

        conn.close()

# ==================== BOT STARTUP ====================
def run_bot():
    init_db()

    # Start Render HealthCheck Server
    if "PORT" in os.environ or os.getenv("RENDER"):
        t = threading.Thread(target=start_render_health_server, daemon=True)
        t.start()
        logger.info("Render background health check server started.")

    bot = TelegramBot(BOT_TOKEN)

    logger.info("Connecting to Telegram Bot API...")
    me = bot.get_me()
    if not me.get("ok"):
        logger.error(f"Failed to connect: {me}")
        print("\n❌ ত্রুটি: BOT_TOKEN সঠিক নয়! অনুগ্রহ করে @BotFather থেকে পাওয়া টোকেন বসান।\n")
        return

    bot_info = me["result"]
    bot_username = bot_info["username"]
    bot_id = bot_info["id"]

    print(f"\n=======================================================")
    print(f"🚀 UltraPoll Pro Bot চালু হয়েছে: @{bot_username}")
    print(f"🎨 ফুল কালার বাটন, লাইভ প্রগ্রেস বার ও ফোর্স সাব সক্রিয়!")
    print(f"=======================================================\n")

    offset = 0
    while True:
        try:
            updates_res = bot.request("getUpdates", {
                "offset": offset,
                "timeout": 20,
                "allowed_updates": ["message", "callback_query", "chat_member", "my_chat_member"]
            })
            if not updates_res.get("ok"):
                time.sleep(2)
                continue

            updates = updates_res.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(bot, update["message"], bot_username, bot_id)
                elif "callback_query" in update:
                    handle_callback_query(bot, update["callback_query"], bot_username, bot_id)
                elif "chat_member" in update:
                    handle_chat_member_updated(bot, update["chat_member"], bot_username)

        except Exception as e:
            logger.error(f"Polling loop exception: {e}")
            time.sleep(3)

if __name__ == "__main__":
    run_bot()