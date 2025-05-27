import json
import time
import logging
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace this with your bot token

USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

ADMINS = []  # Your Telegram user IDs as strings if needed for admin commands

# Load and save data functions with error handling
def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

users = load_json(USERS_FILE)
matches = load_json(MATCHES_FILE)

def save_all():
    save_json(USERS_FILE, users)
    save_json(MATCHES_FILE, matches)

def get_user(uid):
    if uid not in users:
        users[uid] = {"coins": 1000, "wins": 0, "last_daily": 0}
        save_all()
    return users[uid]

def current_time():
    return int(time.time())

def format_match_id():
    return str(int(time.time() * 1000))[-6:]

def number_buttons():
    keyboard = [
        [InlineKeyboardButton(str(n), callback_data=f"num_{n}") for n in [1, 2, 3]],
        [InlineKeyboardButton(str(n), callback_data=f"num_{n}") for n in [4, 5, 6]],
    ]
    return InlineKeyboardMarkup(keyboard)

def is_admin(uid):
    return str(uid) in ADMINS

# === Command Handlers ===

def start(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    get_user(uid)
    update.message.reply_text(
        f"Hi {update.effective_user.first_name}! Welcome to Hand Cricket.\n"
        "Commands:\n"
        "/pm <bet> - create/join match\n"
        "/profile - show your profile\n"
        "/daily - claim daily coins\n"
        "/help - show commands"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Commands:\n"
        "/pm <bet> - Create or join a PvP match with optional bet\n"
        "/profile - Show your profile\n"
        "/daily - Claim daily coins\n"
        "/help - Show this message"
    )

def profile(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    update.message.reply_text(f"Profile:\nCoins: {user['coins']}\nWins: {user['wins']}")

def daily(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    now = current_time()
    if now - user.get("last_daily", 0) < 24 * 3600:
        update.message.reply_text("Daily already claimed. Try again tomorrow!")
        return
    reward = 500
    user["coins"] += reward
    user["last_daily"] = now
    save_all()
    update.message.reply_text(f"Daily claimed! You got {reward} coins.")

# === Match commands and callbacks ===

def pm_command(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    get_user(uid)
    bet = 0
    if context.args and context.args[0].isdigit():
        bet = int(context.args[0])
    if bet > 0 and users[uid]["coins"] < bet:
        update.message.reply_text("You don't have enough coins to bet that amount.")
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
        "max_wickets": 1,
        "over": 0.0,
    }
    save_all()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]
    ])
    update.message.reply_text(
        f"{update.effective_user.first_name} created a match with bet {bet} coins.\nPress Join to join!",
        reply_markup=keyboard,
    )

def join_match(update: Update, context: CallbackContext):
    query = update.callback_query
    uid = str(query.from_user.id)
    _, match_id = query.data.split("_")
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
    if match["bet"] > 0 and users[uid]["coins"] < match["bet"]:
        query.answer("Not enough coins for this bet.")
        return
    match["players"].append(uid)
    match["scores"][uid] = 0
    match["state"] = "playing"
    match["bowling"] = uid
    match["turn"] = match["batting"]
    match["last_activity"] = current_time()
    if match["bet"] > 0:
        for p in match["players"]:
            users[p]["coins"] -= match["bet"]
    save_all()

    # Use user first names safely
    chat_id = match["chat_id"]
    try:
        batting_name = context.bot.get_chat_member(chat_id, int(match["batting"])).user.first_name
    except:
        batting_name = "Batsman"
    try:
        bowling_name = context.bot.get_chat_member(chat_id, int(match["bowling"])).user.first_name
    except:
        bowling_name = "Bowler"

    text = (
        f"Match started!\n"
        f"🏏 Batter: {batting_name}\n"
        f"⚾ Bowler: {bowling_name}\n\n"
        f"Over: 0.0\n"
        f"{batting_name} to bat first.\n\n"
        "Batter, choose your number:"
    )
    sent = context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=text,
        reply_markup=number_buttons(),
    )
    match["msg_id"] = sent.message_id
    save_all()
    query.answer()

def number_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    uid = str(query.from_user.id)
    if not query.data.startswith("num_"):
        query.answer()
        return
    chosen_num = int(query.data.split("_")[1])

    # Find match for user
    user_match = None
    for m in matches.values():
        if uid in m["players"] and m["state"] == "playing":
            user_match = m
            break
    if not user_match:
        query.answer("You're not in an active match.")
        return
    if user_match["turn"] != uid:
        query.answer("Not your turn yet.")
        return

    chat_id = user_match["chat_id"]
    msg_id = user_match["msg_id"]

    # Get names safely
    try:
        batting_name = context.bot.get_chat_member(chat_id, int(user_match["batting"])).user.first_name
    except:
        batting_name = "Batsman"
    try:
        bowling_name = context.bot.get_chat_member(chat_id, int(user_match["bowling"])).user.first_name
    except:
        bowling_name = "Bowler"

    if uid == user_match["batting"]:
        user_match["batsman_num"] = chosen_num
        user_match["turn"] = user_match["bowling"]
        text = (
            f"Over: {user_match['over']:.1f}\n"
            f"{batting_name} chose a number.\n"
            f"Now it's {bowling_name}'s turn to bowl."
        )
        context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=number_buttons())
        save_all()
        query.answer("Batsman number chosen.")
        return

    elif uid == user_match["bowling"]:
        user_match["bowler_num"] = chosen_num

        if user_match["batsman_num"] == user_match["bowler_num"]:
            # Wicket!
            user_match["wickets"] += 1
            text = (
                f"Over: {user_match['over']:.1f}\n"
                f"{batting_name} chose {user_match['batsman_num']}, {bowling_name} chose {user_match['bowler_num']}.\n"
                "Wicket! ⚠️\n\n"
                f"Score: {user_match['scores'][user_match['batting']]}\n"
                "Innings over."
            )
            user_match["state"] = "finished"
            winner = user_match["bowling"]
            loser = user_match["batting"]
            if user_match["bet"] > 0:
                users[winner]["coins"] += user_match["bet"] * 2
            users[winner]["wins"] += 1
            save_all()
            context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=None)
            query.answer()
            return
        else:
            runs = user_match["batsman_num"]
            user_match["scores"][user_match["batting"]] += runs
            user_match["over"] += 0.1
            if round(user_match["over"] % 1, 1) >= 0.6:
                user_match["over"] = int(user_match["over"]) + 1.0

            text = (
                f"Over: {user_match['over']:.1f}\n"
                f"{batting_name} chose {user_match['batsman_num']}, {bowling_name} chose {user_match['bowler_num']}.\n"
                f"Runs scored: {runs}\n"
                f"Score: {user_match['scores'][user_match['batting']]}\n\n"
                f"{batting_name} to bat. Choose your number:"
            )
            user_match["turn"] = user_match["batting"]
            user_match["batsman_num"] = None
            user_match["bowler_num"] = None
            context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=number_buttons())
            save_all()
            query.answer()
            return
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("pm", pm_command))
    dp.add_handler(CallbackQueryHandler(join_match, pattern=r"^join_"))
    dp.add_handler(CallbackQueryHandler(number_handler, pattern=r"^num_"))

    print("Bot started. Press Ctrl+C to stop.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
