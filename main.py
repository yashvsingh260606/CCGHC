import json
import time
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
)
import logging

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== BOT TOKEN =====
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# ===== ADMINS (as strings) =====
ADMINS = ["123456789"]  # replace with your Telegram user IDs as strings

# ===== DATA FILES =====
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

# ===== GLOBAL DATA =====
users = {}    # user_id(str) -> {"coins": int, "wins": int, "last_daily": int}
matches = {}  # match_id(str) -> match data dict

# ===== CONSTANTS =====
MAX_WICKETS = 1
INACTIVITY_TIMEOUT = 20 * 60  # 20 minutes

# ===== UTILITIES =====

def load_data():
    global users, matches
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    except:
        users = {}
    try:
        with open(MATCHES_FILE, "r") as f:
            matches = json.load(f)
    except:
        matches = {}

def save_data():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f, indent=2)

def is_admin(user_id: str):
    return user_id in ADMINS

def get_user(uid: str):
    if uid not in users:
        users[uid] = {"coins": 1000, "wins": 0, "last_daily": 0}
        save_data()
    return users[uid]

def current_time():
    return int(time.time())

def format_match_id():
    return str(int(time.time() * 1000))[-6:]

# Number buttons 1-6 in 2 rows
def number_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="num_1"),
         InlineKeyboardButton("2", callback_data="num_2"),
         InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"),
         InlineKeyboardButton("5", callback_data="num_5"),
         InlineKeyboardButton("6", callback_data="num_6")]
    ])

# ===== COMMANDS =====

def start(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    get_user(uid)
    save_data()

    text = (
        f"Hello {update.effective_user.first_name}!\n\n"
        "Welcome to Hand Cricket Bot.\n\n"
        "Commands:\n"
        "/pm <bet> - Create a player-vs-player match with optional bet (e.g. /pm 200)\n"
        "/leaderboard - Show leaderboard\n"
        "/daily - Claim daily coins\n"
        "/profile - Show your profile\n"
        "/help - Show help message"
    )
    update.message.reply_text(text)

def help_command(update: Update, context: CallbackContext):
    text = (
        "Commands:\n"
        "/pm <bet> - Create/join PVP match with optional bet\n"
        "/leaderboard - Show leaderboard\n"
        "/daily - Claim daily coins\n"
        "/profile - View your stats\n"
        "/help - This message"
    )
    update.message.reply_text(text)

def profile(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    text = f"Your Profile:\nCoins: {user['coins']}\nWins: {user['wins']}"
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

# Load data once at start
load_data()
# ----- Create Match Command (/pm) -----

def pm_command(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = str(user.id)
    get_user(uid)

    bet = 0
    if context.args and context.args[0].isdigit():
        bet = int(context.args[0])

    # Check if user has enough coins for bet
    if bet > 0 and get_user(uid)["coins"] < bet:
        update.message.reply_text("You don't have enough coins to place this bet.")
        return

    match_id = format_match_id()
    matches[match_id] = {
        "players": [uid],
        "bet": bet,
        "state": "waiting",
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

# ----- Join Match Handler -----

def join_match(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    uid = str(user.id)
    data = query.data
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

    if match["bet"] > 0 and get_user(uid)["coins"] < match["bet"]:
        query.answer("Not enough coins to join this bet match.")
        return

    match["players"].append(uid)
    match["scores"][uid] = 0
    match["state"] = "playing"
    match["bowling"] = uid
    match["turn"] = match["batting"]
    match["last_activity"] = current_time()

    # Deduct bet from both players
    if match["bet"] > 0:
        for p in match["players"]:
            get_user(p)["coins"] -= match["bet"]

    save_data()

    # Prepare start message
    chat_id = match["chat_id"]
    batting_name = context.bot.get_chat_member(chat_id, int(match["batting"])).user.first_name
    bowling_name = context.bot.get_chat_member(chat_id, int(match["bowling"])).user.first_name

    text = (
        f"Match started!\n"
        f"🏏 Batter: {batting_name}\n"
        f"⚾ Bowler: {bowling_name}\n\n"
        f"Over: 0.0\n"
        f"{batting_name} to bat first.\n\n"
        "Batter, choose your number:"
    )

    # Send new message with buttons
    sent_msg = query.edit_message_text(text=text, reply_markup=number_buttons())
    match["msg_id"] = sent_msg.message_id

    save_data()
    query.answer()

# ----- Number Selection Handler -----

def number_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    uid = str(user.id)
    data = query.data

    if not data.startswith("num_"):
        query.answer()
        return

    chosen_num = int(data.split("_")[1])

    # Find match for this user
    match = None
    for m in matches.values():
        if uid in m["players"] and m["state"] == "playing":
            match = m
            break

    if not match:
        query.answer("You are not currently in a match.")
        return

    if match["turn"] != uid:
        query.answer("It's not your turn.")
        return

    # Logic: If batsman turn -> store batsman number and switch to bowler turn
    # If bowler turn -> store bowler number, compare, update score/wicket, switch turn

    if uid == match["batting"]:
        # Batsman picks number
        match["batsman_num"] = chosen_num
        match["turn"] = match["bowling"]

        # Show message: batsman picked number, now bowler turn (hide number)
        chat_id = match["chat_id"]
        msg_id = match["msg_id"]
        batting_name = context.bot.get_chat_member(chat_id, int(match["batting"])).user.first_name
        bowling_name = context.bot.get_chat_member(chat_id, int(match["bowling"])).user.first_name

        text = (
            f"Over: {match['over']:.1f}\n"
            f"{batting_name} chose a number.\n"
            f"Now it's {bowling_name}'s turn to bowl."
        )
        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=number_buttons()
        )
        save_data()
        query.answer("You chose your batting number.")
        return

    elif uid == match["bowling"]:
        # Bowler picks number
        match["bowler_num"] = chosen_num

        batting_name = context.bot.get_chat_member(match["chat_id"], int(match["batting"])).user.first_name
        bowling_name = context.bot.get_chat_member(match["chat_id"], int(match["bowling"])).user.first_name

        chat_id = match["chat_id"]
        msg_id = match["msg_id"]

        # Compare numbers
        if match["batsman_num"] == match["bowler_num"]:
            # Wicket falls
            match["wickets"] += 1
            text = (
                f"Over: {match['over']:.1f}\n"
                f"{batting_name} chose {match['batsman_num']}, {bowling_name} chose {match['bowler_num']}.\n"
                "Wicket! ⚠️\n\n"
                f"Score: {match['scores'][match['batting']]}\n"
                "Innings over."
            )
            match["state"] = "finished"
            # Update winner coins if bet > 0
            winner_uid = match["bowling"]
            loser_uid = match["batting"]
            if match["bet"] > 0:
                get_user(winner_uid)["coins"] += match["bet"] * 2

            # Update wins count
            get_user(winner_uid]["wins"] += 1

            save_data()

        else:
            # Runs scored equal to batsman number
            runs = match["batsman_num"]
            match["scores"][match["batting"]] += runs
            match["over"] += 0.1
            if match["over"] % 1 >= 0.6:
                match["over"] = int(match["over"]) + 1.0

            text = (
                f"Over: {match['over']:.1f}\n"
                f"{batting_name} chose {match['batsman_num']}, {bowling_name} chose {match['bowler_num']}.\n"
                f"Runs scored: {runs}\n"
                f"Score: {match['scores'][match['batting']]}\n\n"
                f"{batting_name} to bat. Choose your number:"
            )
            match["turn"] = match["batting"]
            # Reset batsman and bowler numbers
            match["batsman_num"] = None
            match["bowler_num"] = None

        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=number_buttons() if match["state"] == "playing" else None,
        )

        save_data()
        query.answer()
        return
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Register commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("pm", pm_command))

    # Callback query handlers
    dp.add_handler(CallbackQueryHandler(join_match, pattern=r"^join_\d+$"))
    dp.add_handler(CallbackQueryHandler(number_handler, pattern=r"^num_[1-6]$"))

    # Start polling
    updater.start_polling()
    print("Bot started and polling...")

    updater.idle()

if __name__ == "__main__":
    main()
