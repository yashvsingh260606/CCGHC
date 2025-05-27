# === IMPORTS ===
import json
import os
import random
import time
from datetime import datetime, timedelta
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# === CONFIGURATION ===
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace with your actual bot token
ADMIN_IDS = [123456789]  # Replace with your admin Telegram user IDs

# === FILES ===
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

# === LOADING AND SAVING ===
def load_data(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

users = load_data(USERS_FILE)
matches = load_data(MATCHES_FILE)

def save_all():
    save_data(USERS_FILE, users)
    save_data(MATCHES_FILE, matches)

# === UTILITY FUNCTIONS ===
def get_user(user_id):
    if str(user_id) not in users:
        users[str(user_id)] = {
            "name": "",
            "coins": 1000,
            "wins": 0,
            "losses": 0,
            "last_daily": "1970-01-01",
        }
    return users[str(user_id)]

def is_admin(user_id):
    return user_id in ADMIN_IDS
# === COMMAND HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    user["name"] = update.effective_user.first_name
    save_all()

    commands = [
        "/register - Register and get 1000 coins",
        "/pm <bet> - Start or join a PvP hand cricket match",
        "/profile - View your profile",
        "/daily - Claim your daily coin reward",
        "/leaderboard - View top players",
        "/help - Show help info",
    ]
    if is_admin(update.effective_user.id):
        commands.append("/add <user_id> <coins> - Add coins to a user (admin only)")

    text = (
        f"Welcome *{user['name']}* to Hand Cricket Bot!\n\n"
        "Available Commands:\n" + "\n".join(commands)
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user["coins"] > 0:
        await update.message.reply_text("You're already registered.")
    else:
        user["name"] = update.effective_user.first_name
        user["coins"] = 1000
        save_all()
        await update.message.reply_text("You have been registered and received 1000 coins!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    text = (
        f"👤 *{user['name']}*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Coins: {user['coins']}\n"
        f"🏏 Wins: {user['wins']} | ❌ Losses: {user['losses']}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")

    if user["last_daily"] == today:
        await update.message.reply_text("You've already claimed your daily coins today!")
    else:
        user["coins"] += 500
        user["last_daily"] = today
        save_all()
        await update.message.reply_text("✅ You've received 500 daily coins!")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = sorted(users.items(), key=lambda x: x[1].get("coins", 0), reverse=True)[:10]
    text = "*🏆 Leaderboard (Top 10 by Coins)*\n\n"

    for i, (uid, data) in enumerate(top_users, start=1):
        text += f"{i}. {data['name']} - {data['coins']} coins\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return

    try:
        user_id = int(context.args[0])
        coins = int(context.args[1])
        user = get_user(user_id)
        user["coins"] += coins
        save_all()
        await update.message.reply_text(f"Added {coins} coins to {user['name']} ({user_id}).")
    except:
        await update.message.reply_text("Invalid input. Usage: /add <user_id> <coins>")
# === MATCH SYSTEM ===

def end_match(chat_id):
    if chat_id in matches:
        del matches[chat_id]
        save_all()

def get_turn_text(state):
    if state["waiting_for"] == "batsman":
        return f"🎯 {state['batsman_name']} chose a number, now it's {state['bowler_name']}'s turn."
    return "Waiting for next input..."

def reveal_turn_result(state):
    batter = state["batsman_num"]
    bowler = state["bowler_num"]
    batter_name = state["batsman_name"]
    bowler_name = state["bowler_name"]

    if batter == bowler:
        text = (
            f"🏏 {batter_name} chose {batter}, {bowler_name} chose {bowler}\n"
            f"❌ WICKET! {batter_name} is out!\n"
        )
        state["wickets"] += 1
        if state["wickets"] == 1:
            # Change innings
            state["innings"] += 1
            state["batsman"], state["bowler"] = state["bowler"], state["batsman"]
            state["batsman_name"], state["bowler_name"] = state["bowler_name"], state["batsman_name"]
            state["score"] = 0
            state["wickets"] = 0
            state["target"] = state["score"]
            state["waiting_for"] = "batsman"
            text += "\n🔁 Innings Over! Switching roles.\n"
            text += f"{state['batsman_name']} now batting."
        else:
            state["waiting_for"] = "batsman"
            text += f"\nNext ball: {state['batsman_name']}'s turn."
    else:
        state["score"] += batter
        text = (
            f"🏏 {batter_name} chose {batter}, {bowler_name} chose {bowler}\n"
            f"➕ {batter_name} scores {batter} runs!\n"
            f"Current Score: {state['score']} / {state['wickets']}\n"
        )
        if state["innings"] == 2 and state["score"] > state["target"]:
            text += f"\n🏆 {state['batsman_name']} wins the match!"
            winner = state["batsman"]
            loser = state["bowler"]
            users[str(winner)]["wins"] += 1
            users[str(loser)]["losses"] += 1
            save_all()
            end_match(state["chat_id"])
            return text
        state["waiting_for"] = "batsman"
    return text

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if chat_id not in matches:
        return

    state = matches[chat_id]

    if user_id == state["batsman"]:
        state["batsman_num"] = int(query.data)
        state["waiting_for"] = "bowler"
        await query.edit_message_text(get_turn_text(state), reply_markup=get_number_buttons())
    elif user_id == state["bowler"] and state["waiting_for"] == "bowler":
        state["bowler_num"] = int(query.data)
        result = reveal_turn_result(state)
        await query.edit_message_text(result, reply_markup=get_number_buttons())
        save_all()

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    bet = int(context.args[0]) if context.args else 0
    chat_id = update.message.chat_id

    if user["coins"] < bet:
        await update.message.reply_text("Not enough coins to place the bet.")
        return

    for state in matches.values():
        if state["status"] == "waiting" and state["creator"] != user_id:
            creator_id = state["creator"]
            if user["coins"] < state["bet"]:
                await update.message.reply_text("You don't have enough coins to join this match.")
                return

            user["coins"] -= state["bet"]
            users[str(creator_id)]["coins"] -= state["bet"]

            matches[chat_id] = {
                "chat_id": chat_id,
                "batsman": creator_id,
                "bowler": user_id,
                "batsman_name": users[str(creator_id)]["name"],
                "bowler_name": user["name"],
                "score": 0,
                "wickets": 0,
                "innings": 1,
                "target": 0,
                "waiting_for": "batsman",
                "status": "playing",
                "bet": state["bet"]
            }

            del matches[state["chat_id"]]
            save_all()

            await update.message.reply_text(
                f"🎮 Match started!\n"
                f"{matches[chat_id]['batsman_name']} vs {matches[chat_id]['bowler_name']}\n"
                f"Batting: {matches[chat_id]['batsman_name']}",
                reply_markup=get_number_buttons()
            )
            return

    matches[chat_id] = {
        "chat_id": chat_id,
        "creator": user_id,
        "bet": bet,
        "status": "waiting"
    }
    await update.message.reply_text("Waiting for opponent to join...")

def get_number_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 7)],
    ])

# === MAIN FUNCTION ===

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("pm", pm))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
