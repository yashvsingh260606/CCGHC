import json
import time
import threading
from telegram import (
    Bot,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
)
import logging

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== BOT TOKEN HERE =====
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# ===== ADMINS IDS HERE ===== (as strings)
admins = ["123456789", "987654321"]  # replace with your admin user IDs as strings

# ===== FILES FOR DATA PERSISTENCE =====
USERS_FILE = "users_data.json"
MATCHES_FILE = "matches_data.json"

# ===== GLOBAL DATA =====
users = {}   # key = user_id(str), value = dict with coins, wins, last_daily timestamp
matches = {} # key = match_id(str), value = match data dict

# ===== MATCH CONSTANTS =====
MAX_WICKETS = 1
INACTIVITY_LIMIT = 20 * 60  # 20 minutes inactivity timeout in seconds

# ===== UTILS =====

def load_data():
    global users, matches
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}
    try:
        with open(MATCHES_FILE, "r") as f:
            matches = json.load(f)
    except FileNotFoundError:
        matches = {}

def save_data():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f, indent=2)

def is_admin(user_id: str) -> bool:
    return user_id in admins

def format_match_id():
    # Generate simple unique match ID based on timestamp
    return str(int(time.time()*1000))[-6:]

def get_user(uid):
    if uid not in users:
        users[uid] = {"coins": 1000, "wins": 0, "last_daily": 0}
        save_data()
    return users[uid]

def current_time():
    return int(time.time())

# Button keyboard for numbers 1 to 6, two rows
def number_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data='num_1'),
         InlineKeyboardButton("2", callback_data='num_2'),
         InlineKeyboardButton("3", callback_data='num_3')],
        [InlineKeyboardButton("4", callback_data='num_4'),
         InlineKeyboardButton("5", callback_data='num_5'),
         InlineKeyboardButton("6", callback_data='num_6')],
    ])

# Start the bot (loading data)
def init_bot():
    load_data()
    print("Data loaded, bot ready.")

# Call init_bot() once when running this part
init_bot()
# ===== COMMAND HANDLERS =====

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = str(user.id)
    get_user(uid)  # ensure user in users dict
    save_data()

    text = (
        f"Hello {user.first_name}!\n\n"
        "Welcome to Hand Cricket Bot.\n\n"
        "Commands:\n"
        "/pm <bet> - Create a player-vs-player match with optional bet (e.g. /pm 200)\n"
        "/leaderboard - Show leaderboard\n"
        "/daily - Claim your daily coins\n"
        "/profile - Show your profile\n"
        "/help - Show help message"
    )
    update.message.reply_text(text)

def help_command(update: Update, context: CallbackContext):
    text = (
        "Available commands:\n"
        "/pm <bet> - Create or join a PVP match with optional bet\n"
        "/leaderboard - View leaderboard (wins and coins, use arrows)\n"
        "/daily - Claim daily coins bonus\n"
        "/profile - See your stats\n"
        "/help - Show this message"
    )
    update.message.reply_text(text)

def profile(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    text = (
        f"Your Profile:\n"
        f"Coins: {user['coins']}\n"
        f"Wins: {user['wins']}"
    )
    update.message.reply_text(text)

def daily(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    now = current_time()

    if now - user.get("last_daily", 0) < 24 * 3600:
        update.message.reply_text("You already claimed your daily coins. Come back tomorrow!")
        return

    daily_coins = 500
    user["coins"] += daily_coins
    user["last_daily"] = now
    save_data()

    update.message.reply_text(f"Daily claimed! You received {daily_coins} coins.")

# ----- Match Creation Command -----

def pm_command(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = str(user.id)
    get_user(uid)

    args = context.args
    bet = 0
    if args and args[0].isdigit():
        bet = int(args[0])

    # Create match ID
    match_id = format_match_id()

    # Initialize match structure
    matches[match_id] = {
        "players": [uid],
        "bet": bet,
        "state": "waiting",  # waiting for opponent to join
        "created_at": current_time(),
        "last_activity": current_time(),
        "turn": None,
        "innings": 1,
        "scores": {uid: 0},
        "wickets": 0,
        "batting": uid,
        "bowling": None,
        "batsman_num": None,
        "bowler_num": None,
        "msg_id": None,
        "chat_id": update.effective_chat.id,
        "max_wickets": MAX_WICKETS,
        "over": 0.0,
    }
    save_data()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]
    ])

    update.message.reply_text(
        f"{user.first_name} created a match with bet {bet} coins.\nPress Join to join!",
        reply_markup=keyboard
    )

# ----- Join Match Callback -----

def join_match(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    uid = str(user.id)

    data = query.data  # format join_<match_id>
    _, match_id = data.split("_")

    if match_id not in matches:
        query.answer("Match no longer available.")
        return

    match = matches[match_id]

    if uid in match["players"]:
        query.answer("You are already in this match.")
        return

    if len(match["players"]) >= 2:
        query.answer("Match is full.")
        return

    # Check if user has enough coins for bet
    if match["bet"] > 0 and get_user(uid)["coins"] < match["bet"]:
        query.answer("Not enough coins to join this bet match.")
        return

    # Add second player
    match["players"].append(uid)
    match["scores"][uid] = 0
    match["state"] = "playing"
    match["bowling"] = uid
    match["turn"] = match["batting"]
    match["last_activity"] = current_time()

    # Deduct bet coins from both players if bet > 0
    if match["bet"] > 0:
        for player_uid in match["players"]:
            user_data = get_user(player_uid)
            user_data["coins"] -= match["bet"]

    save_data()

    # Show match start message and buttons
    batter_name = context.bot.get_chat_member(match['chat_id'], int(match['batting'])).user.first_name
    bowler_name = context.bot.get_chat_member(match['chat_id'], int(match['bowling'])).user.first_name

    text = (
        f"Match started between:\n"
        f"🏏 Batter: {batter_name}\n"
        f"⚾ Bowler: {bowler_name}\n\n"
        f"Over : 0.0\n"
        f"{batter_name} to bat first.\n\n"
        "Batter, choose your number:"
    )

    # Edit original message with buttons
    query.edit_message_text(text=text, reply_markup=number_buttons())

    save_data()
    query.answer()
# ----- Number Selection Handler -----

def number_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    uid = str(user.id)
    data = query.data  # format num_1..6

    if not data.startswith
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("pm", pm_command))

    # CallbackQuery handlers
    dp.add_handler(CallbackQueryHandler(join_match, pattern=r"^join_\d+$"))
    dp.add_handler(CallbackQueryHandler(number_handler, pattern=r"^num_[1-6]$"))

    # Start polling
    updater.start_polling()
    print("Bot started...")

    updater.idle()

if __name__ == '__main__':
    main()
