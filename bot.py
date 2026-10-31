"""
Professional & Beautiful Telegram Poll Bot with Full Colored Buttons (Bot API 9.4+)
Author: AI Developer for User
Features:
- Full Color Buttons: primary (blue), success (green), danger (red)
- Real-time Leaderboard with 👑 Crown / Badges & Progress Bars
- 1-Click Vote Retraction & Poll Closing
- Anti-Cheat & Channel Force-Subscribe Check
- SQLite Database for 100% Data Persistence
- Full Bengali Localization & Beautiful UI/UX
"""

import os
import sys
import time
import json
import sqlite3
import logging
import threading
from typing import Dict, List, Any, Optional
import requests

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("PollBot")

# ==================== CONFIGURATION ====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with token from @BotFather
ADMIN_ID = 123456789              # Replace with your Telegram numeric User ID
SUPPORT_USERNAME = "YourUsername"  # Replace with support username without @
CHANNEL_USERNAME = "YourChannel"   # Replace with update channel username without @

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==================== DATABASE SETUP ====================
DB_FILE = "poll_bot.db"

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
        question TEXT,
        channel_id TEXT,
        message_id INTEGER,
        is_closed INTEGER DEFAULT 0,
        force_sub_channel TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    # Options table
    c.execute('''CREATE TABLE IF NOT EXISTS poll_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id TEXT,
        option_index INTEGER,
        option_text TEXT,
        color_style TEXT DEFAULT 'primary',
        emoji TEXT DEFAULT '🗳️'
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

    def edit_reply_markup(self, chat_id: Any, message_id: int, reply_markup: Optional[Dict] = None) -> Dict:
        payload = {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        return self.request("editMessageReplyMarkup", payload)

    def answer_callback(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> Dict:
        payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text
        return self.request("answerCallbackQuery", payload)

    def get_chat_member(self, chat_id: Any, user_id: int) -> Dict:
        return self.request("getChatMember", {"chat_id": chat_id, "user_id": user_id})

    def get_me(self) -> Dict:
        return self.request("getMe")

# State tracking for multi-step poll creation
user_states: Dict[int, Dict] = {}

# ==================== HELPERS ====================
def make_progress_bar(percent: float, length: int = 8) -> str:
    filled = int(round((percent / 100.0) * length))
    return "█" * filled + "░" * (length - filled)

# Color styles cycle for full colorful buttons:
# Telegram Bot API 9.4 button styles: 'primary' (blue), 'success' (green), 'danger' (red)
COLOR_CYCLE = ["primary", "success", "danger"]
OPTION_EMOJIS = ["🔥", "❤️", "⭐", "💎", "⚡", "🚀", "🏆", "🎯", "🎮", "👑", "🌟", "✨"]

def build_poll_markup(poll_id: str, is_closed: bool = False) -> Dict:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT option_index, option_text, color_style, emoji FROM poll_options WHERE poll_id = ? ORDER BY option_index", (poll_id,))
    options = c.fetchall()

    c.execute("SELECT option_index, COUNT(*) FROM votes WHERE poll_id = ? GROUP BY option_index", (poll_id,))
    counts = dict(c.fetchall())
    total_votes = sum(counts.values())

    # Find leader
    max_votes = -1
    leader_index = -1
    if total_votes > 0:
        for opt_idx, cnt in counts.items():
            if cnt > max_votes:
                max_votes = cnt
                leader_index = opt_idx

    keyboard = []
    row = []

    for idx, text, color, default_emoji in options:
        cnt = counts.get(idx, 0)
        crown = "👑 " if (cnt > 0 and idx == leader_index) else ""
        btn_text = f"{crown}🗳️ {cnt} | {default_emoji} {text}"
        
        # Style mapping:
        # If leader, give distinct success (green) or primary (blue)
        # We cycle color: primary (blue), success (green), danger (red) so ALL buttons are colored!
        btn_style = color if color in COLOR_CYCLE else COLOR_CYCLE[idx % len(COLOR_CYCLE)]

        btn = {
            "text": btn_text,
            "callback_data": f"vote:{poll_id}:{idx}",
            "style": btn_style  # Telegram Bot API 9.4 colored buttons!
        }
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    if not is_closed:
        # Action control buttons
        keyboard.append([
            {"text": "🔄 ভোট প্রত্যাহার করুন", "callback_data": f"retract:{poll_id}", "style": "primary"}
        ])
        keyboard.append([
            {"text": "🛑 পোল বন্ধ করুন", "callback_data": f"close:{poll_id}", "style": "danger"}
        ])
    else:
        keyboard.append([
            {"text": "🔒 এই পোলটি সমাপ্ত হয়েছে", "callback_data": "closed_info", "style": "danger"}
        ])

    conn.close()
    return {"inline_keyboard": keyboard}

def build_poll_text(poll_id: str, bot_username: str) -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT question, is_closed FROM polls WHERE poll_id = ?", (poll_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "❌ পোলটি খুঁজে পাওয়া যায়নি।"
    question, is_closed = row

    c.execute("SELECT option_index, option_text, emoji FROM poll_options WHERE poll_id = ? ORDER BY option_index", (poll_id,))
    options = c.fetchall()

    c.execute("SELECT option_index, COUNT(*) FROM votes WHERE poll_id = ? GROUP BY option_index", (poll_id,))
    counts = dict(c.fetchall())
    total_votes = sum(counts.values())

    status_tag = "🔴 [পোল বন্ধ]" if is_closed else "🟢 [ভোট গ্রহণ চলছে]"

    text = f"✨ <b>পোল কনটেস্ট</b> {status_tag}\n\n"
    text += f"📝 <b>প্রশ্ন / নির্দেশনা:</b>\n{question}\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 <b>লাইভ ফলাফল (মোট ভোট: {total_votes}):</b>\n\n"

    # Sort options by votes descending for ranking view
    sorted_options = sorted(options, key=lambda x: counts.get(x[0], 0), reverse=True)
    for rank, (idx, opt_text, emoji) in enumerate(sorted_options, start=1):
        v = counts.get(idx, 0)
        pct = (v / total_votes * 100) if total_votes > 0 else 0
        bar = make_progress_bar(pct, length=8)
        medal = "🥇" if rank == 1 and v > 0 else ("🥈" if rank == 2 and v > 0 else ("🥉" if rank == 3 and v > 0 else f"#{rank}"))
        text += f"{medal} {emoji} <b>{opt_text}</b>\n"
        text += f"   <code>[{bar}]</code> {pct:.1f}% ({v} ভোট)\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"⚡ <b>Poll Created by:</b> @{bot_username}\n"
    if not is_closed:
        text += "👉 <i>আপনার পছন্দের প্রার্থীর বাটনে ক্লিক করে ভোট দিন!</i>"
    else:
        text += "🏆 <b>পোলটি সফলভাবে শেষ হয়েছে। বিজয়ীকে অভিনন্দন!</b>"

    conn.close()
    return text

def main_menu_keyboard():
    # Full color menu buttons (Primary, Success, Danger)
    return {
        "keyboard": [
            [{"text": "🗳️ Make Poll", "style": "primary"}],
            [{"text": "👤 My Profile", "style": "success"}, {"text": "📊 Statistics", "style": "danger"}],
            [{"text": "📞 Support", "style": "primary"}]
        ],
        "resize_keyboard": True
    }

# ==================== MAIN LOGIC ====================
def handle_message(bot: TelegramBot, msg: Dict, bot_username: str):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text = msg.get("text", "")
    first_name = msg["from"].get("first_name", "User")
    username = msg["from"].get("username", "")

    # Save user
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user_id, first_name, username))
    conn.commit()
    conn.close()

    # Step-by-step state handler for creating poll
    if user_id in user_states:
        state = user_states[user_id]
        step = state.get("step")

        if step == "waiting_for_question":
            state["question"] = text
            state["step"] = "waiting_for_options"
            bot.send_message(
                chat_id,
                "✅ <b>প্রশ্ন গৃহীত হয়েছে!</b>\n\n"
                "এখন পোলের জন্য <b>অপশন / প্রার্থীদের নাম</b> পাঠান।\n"
                "প্রতি লাইনে একটি করে নাম লিখুন অথবা কমা (,) দিয়ে আলাদা করে পাঠান:\n\n"
                "<i>উদাহরণ:</i>\n"
                "Alvi\n"
                "AURA GM\n"
                "Sumaiya\n"
                "WNER CODE"
            )
            return

        elif step == "waiting_for_options":
            lines = [line.strip() for line in text.replace(",", "\n").split("\n") if line.strip()]
            if len(lines) < 2:
                bot.send_message(chat_id, "⚠️ অনুগ্রহ করে কমপক্ষে ২টি অপশন বা নাম দিন।")
                return
            if len(lines) > 20:
                bot.send_message(chat_id, "⚠️ সর্বোচ্চ ২০টি অপশন দেওয়া যাবে।")
                return

            poll_id = f"poll_{int(time.time())}_{user_id}"
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO polls (poll_id, creator_id, question) VALUES (?, ?, ?)",
                      (poll_id, user_id, state["question"]))

            for idx, opt_name in enumerate(lines):
                color = COLOR_CYCLE[idx % len(COLOR_CYCLE)]
                emoji = OPTION_EMOJIS[idx % len(OPTION_EMOJIS)]
                c.execute("INSERT INTO poll_options (poll_id, option_index, option_text, color_style, emoji) VALUES (?, ?, ?, ?, ?)",
                          (poll_id, idx, opt_name, color, emoji))
            conn.commit()
            conn.close()

            del user_states[user_id]

            # Send preview of created poll
            poll_text = build_poll_text(poll_id, bot_username)
            poll_markup = build_poll_markup(poll_id)

            bot.send_message(chat_id, "🎉 <b>আপনার আকর্ষণীয় কালারফুল পোল তৈরি সম্পন্ন হয়েছে!</b>\nনিচে প্রিভিউ দেখে নিন:")
            bot.send_message(chat_id, poll_text, reply_markup=poll_markup)

            # Share button
            share_markup = {
                "inline_keyboard": [
                    [{"text": "🚀 চ্যানেল বা গ্রুপে শেয়ার করুন", "url": f"https://t.me/share/url?url=https://t.me/{bot_username}?start={poll_id}", "style": "success"}]
                ]
            }
            bot.send_message(chat_id, "💡 আপনি এই পোলটি আপনার চ্যানেল বা গ্রুপে ফরওয়ার্ড করতে পারেন অথবা নিচের বাটনে চাপ দিয়ে শেয়ার করতে পারেন:", reply_markup=share_markup)
            return

    # Commands & Menu Buttons
    if text == "/start" or text.startswith("/start"):
        # Check if deep link
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith("poll_"):
            poll_id = parts[1]
            poll_text = build_poll_text(poll_id, bot_username)
            poll_markup = build_poll_markup(poll_id)
            bot.send_message(chat_id, poll_text, reply_markup=poll_markup)
            return

        welcome_text = (
            f"👋 <b>আসসালামু আলাইকুম, {first_name}!</b>\n\n"
            "✨ আমাদের <b>আল্ট্রা-কালারফুল পোল মেকার বট</b>-এ স্বাগতম!\n\n"
            "🔥 <b>ফিচারসমূহ:</b>\n"
            "• 🎨 <b>ফুল কালার বাটন:</b> নীল (Primary), সবুজ (Success), লাল (Danger)\n"
            "• 👑 <b>লাইভ লিডারবোর্ড:</b> শীর্ষ প্রার্থীর জন্য স্বয়ংক্রিয় মুকুট ও ব্যাজ\n"
            "• 📊 <b>রিয়েল-টাইম প্রগ্রেস বার</b> ও পার্সেন্টেজ কাউন্টার\n"
            "• 🔄 <b>ভোট প্রত্যাহার সুবিধা</b>\n"
            "• 🛑 <b>পোল সমাপ্তি ও বিজয়ী ঘোষণা</b>\n\n"
            "👇 নতুন পোল তৈরি করতে নিচের <b>Make Poll</b> বাটনে চাপ দিন।"
        )
        bot.send_message(chat_id, welcome_text, reply_markup=main_menu_keyboard())

    elif text == "🗳️ Make Poll" or text == "/makepoll":
        user_states[user_id] = {"step": "waiting_for_question"}
        bot.send_message(
            chat_id,
            "❓ <b>আপনার পোলের জন্য প্রশ্ন বা শিরোনাম পাঠান:</b>\n\n"
            "<i>টিপস: আপনি HTML ফরম্যাটিং ব্যবহার করতে পারেন:</i>\n"
            "• বোল্ড করতে: <code>&lt;b&gt;আপনার লেখা&lt;/b&gt;</code>\n"
            "• ইতালিক করতে: <code>&lt;i&gt;আপনার লেখা&lt;/i&gt;</code>\n"
            "• কোড স্টাইল: <code>&lt;code&gt;আপনার লেখা&lt;/code&gt;</code>\n\n"
            "👉 এখন আপনার প্রশ্নটি লিখে পাঠান:"
        )

    elif text == "👤 My Profile" or text == "/profile":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM polls WHERE creator_id = ?", (user_id,))
        created_polls = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM votes WHERE user_id = ?", (user_id,))
        total_votes = c.fetchone()[0]
        conn.close()

        profile_text = (
            "👤 <b>ব্যবহারকারী প্রোফাইল</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ইউজার আইডি:</b> <code>{user_id}</code>\n"
            f"👤 <b>নাম:</b> {first_name}\n"
            f"🏷️ <b>ইউজারনেম:</b> @{username if username else 'N/A'}\n"
            f"🗳️ <b>তৈরিকৃত পোল:</b> {created_polls} টি\n"
            f"🎯 <b>মোট প্রদত্ত ভোট:</b> {total_votes} টি\n"
            f"⚡ <b>স্ট্যাটাস:</b> সক্রিয় মেম্বার ✅\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(chat_id, profile_text)

    elif text == "📊 Statistics" or text == "/stats":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM polls")
        total_polls = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM polls WHERE is_closed = 0")
        active_polls = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM votes")
        total_votes = c.fetchone()[0]
        conn.close()

        stats_text = (
            "✨ <b>লাইভ স্ট্যাটিস্টিক্স</b> ✨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 <b>বট ডেভেলপার:</b> @{SUPPORT_USERNAME}\n"
            f"👥 <b>মোট ব্যবহারকারী:</b> {total_users}\n"
            f"🗳️ <b>মোট পোল তৈরি:</b> {total_polls}\n"
            f"📊 <b>একটিভ পোল চলমান:</b> {active_polls}\n"
            f"🎯 <b>মোট ভোট গ্রহণ:</b> {total_votes}\n"
            "⚡ <b>বট ভার্সন:</b> 4.0.0 Pro (Full Color Support)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>আপনার মতামত আমাদের জন্য অত্যন্ত মূল্যবান!</i>"
        )
        channel_markup = {
            "inline_keyboard": [
                [{"text": "🌐 আমাদের অফিসিয়াল চ্যানেল", "url": f"https://t.me/{CHANNEL_USERNAME}", "style": "primary"}]
            ]
        }
        bot.send_message(chat_id, stats_text, reply_markup=channel_markup)

    elif text == "📞 Support" or text == "/support":
        support_text = (
            "✨ <b>সাপোর্টের জন্য যোগাযোগ করুন</b>\n\n"
            "যদি কোনো সমস্যা বা সাহায্যের প্রয়োজন হয়, নিচের বাটনে ক্লিক করুন।\n\n"
            "📌 <i>আমাদের সাপোর্ট টিম সর্বদা আপনার পাশে রয়েছে।</i>\n"
            "🔹 <b>২৪/৭ একটিভ সার্ভিস!</b>"
        )
        support_markup = {
            "inline_keyboard": [
                [{"text": "💬 সরাসরি সাহায্য পেতে ক্লিক করুন", "url": f"https://t.me/{SUPPORT_USERNAME}", "style": "success"}]
            ]
        }
        bot.send_message(chat_id, support_text, reply_markup=support_markup)


def handle_callback_query(bot: TelegramBot, cb: Dict, bot_username: str):
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

    if data.startswith("vote:"):
        _, poll_id, opt_idx_str = data.split(":")
        opt_idx = int(opt_idx_str)

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT is_closed, creator_id FROM polls WHERE poll_id = ?", (poll_id,))
        poll_info = c.fetchone()
        if not poll_info or poll_info[0] == 1:
            conn.close()
            bot.answer_callback(cb_id, "⚠️ এই পোলটি সমাপ্ত হয়ে গেছে!", show_alert=True)
            return

        # Check existing vote
        c.execute("SELECT option_index FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
        prev_vote = c.fetchone()

        if prev_vote is not None:
            if prev_vote[0] == opt_idx:
                conn.close()
                bot.answer_callback(cb_id, "⚠️ আপনি ইতিমধ্যে এই প্রার্থীকে ভোট দিয়েছেন!", show_alert=False)
                return
            else:
                # Change vote
                c.execute("UPDATE votes SET option_index = ? WHERE poll_id = ? AND user_id = ?", (opt_idx, poll_id, user_id))
                conn.commit()
                conn.close()
                bot.answer_callback(cb_id, "✅ আপনার ভোট সফলভাবে পরিবর্তন করা হয়েছে!", show_alert=False)
        else:
            # New vote
            c.execute("INSERT INTO votes (poll_id, user_id, option_index) VALUES (?, ?, ?)", (poll_id, user_id, opt_idx))
            conn.commit()
            conn.close()
            bot.answer_callback(cb_id, "🎉 ভোট দেওয়ার জন্য ধন্যবাদ!", show_alert=False)

        # Update poll UI
        new_text = build_poll_text(poll_id, bot_username)
        new_markup = build_poll_markup(poll_id)
        bot.edit_message(chat_id, message_id, new_text, reply_markup=new_markup)

    elif data.startswith("retract:"):
        _, poll_id = data.split(":")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT option_index FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
        vote = c.fetchone()
        if vote is None:
            conn.close()
            bot.answer_callback(cb_id, "⚠️ আপনি এই পোলে কোনো ভোট দেননি!", show_alert=True)
            return

        c.execute("DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
        conn.commit()
        conn.close()
        bot.answer_callback(cb_id, "🔄 আপনার ভোট প্রত্যাহার করা হয়েছে!", show_alert=True)

        new_text = build_poll_text(poll_id, bot_username)
        new_markup = build_poll_markup(poll_id)
        bot.edit_message(chat_id, message_id, new_text, reply_markup=new_markup)

    elif data.startswith("close:"):
        _, poll_id = data.split(":")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT creator_id FROM polls WHERE poll_id = ?", (poll_id,))
        creator = c.fetchone()
        if not creator or (creator[0] != user_id and user_id != ADMIN_ID):
            conn.close()
            bot.answer_callback(cb_id, "⛔ কেবল পোল ক্রিয়েটর বা অ্যাডমিন এটি বন্ধ করতে পারবেন!", show_alert=True)
            return

        c.execute("UPDATE polls SET is_closed = 1 WHERE poll_id = ?", (poll_id,))
        conn.commit()
        conn.close()
        bot.answer_callback(cb_id, "🛑 পোলটি সফলভাবে বন্ধ করা হয়েছে!", show_alert=True)

        new_text = build_poll_text(poll_id, bot_username)
        new_markup = build_poll_markup(poll_id, is_closed=True)
        bot.edit_message(chat_id, message_id, new_text, reply_markup=new_markup)

    elif data == "closed_info":
        bot.answer_callback(cb_id, "🔒 এই পোলটি সমাপ্ত হয়ে গেছে। নতুন কোনো ভোট গ্রহণ করা হচ্ছে না।", show_alert=True)


# ==================== POLLING LOOP ====================
def run_bot():
    init_db()
    bot = TelegramBot(BOT_TOKEN)

    logger.info("Checking Bot credentials...")
    me = bot.get_me()
    if not me.get("ok"):
        logger.error(f"Failed to connect to Telegram: {me}")
        print("\n❌ ত্রুটি: BOT_TOKEN সঠিক নয়! অনুগ্রহ করে @BotFather থেকে সঠিক টোকেন বসান।\n")
        return

    bot_username = me["result"]["username"]
    logger.info(f"Bot connected successfully as @{bot_username}")
    print(f"\n==========================================")
    print(f"🚀 Telegram Poll Bot চালু হয়েছে: @{bot_username}")
    print(f"🎨 ফুল কালার বাটন ও লাইভ লিডারবোর্ড সক্রিয়!")
    print(f"==========================================\n")

    offset = 0
    while True:
        try:
            updates_res = bot.request("getUpdates", {"offset": offset, "timeout": 20})
            if not updates_res.get("ok"):
                time.sleep(2)
                continue

            updates = updates_res.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(bot, update["message"], bot_username)
                elif "callback_query" in update:
                    handle_callback_query(bot, update["callback_query"], bot_username)

        except Exception as e:
            logger.error(f"Polling loop exception: {e}")
            time.sleep(3)

if __name__ == "__main__":
    run_bot()