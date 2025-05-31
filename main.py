# --- PART 1 ---

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
import logging
import random
import datetime
import asyncio
from pymongo import MongoClient

# === CONFIG ===
BOT_TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'
MONGO_URL = 'mongodb://mongo:GhpHMiZizYnvJfKIQKxoDbRyzBCpqEyC@mainline.proxy.rlwy.net:54853'

# === Logging ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === MongoDB ===
client = MongoClient(MONGO_URL)
db = client['handcricket']
users_col = db['users']
matches_col = db['matches']

BUTTONS = [
    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)]
]

ADMIN_IDS = [123456789]  # Replace with actual admin Telegram IDs
# --- PART 2 ---

def get_user(uid):
    return users_col.find_one({"_id": uid})

def update_user(uid, data):
    users_col.update_one({"_id": uid}, {"$set": data}, upsert=True)

def inc_user(uid, field, amount):
    users_col.update_one({"_id": uid}, {"$inc": {field: amount}}, upsert=True)

def format_profile(user):
    return (
        f"👤 Name: {user.get('name', 'Unknown')}\n"
        f"🆔 ID: {user['_id']}\n"
        f"💰 Coins: ₹{user.get('coins', 0)}\n"
        f"🏏 Matches: {user.get('wins', 0)} Wins / {user.get('losses', 0)} Losses"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 Welcome to CCG HandCricket Bot!\n\n"
        "Use /register to get started.\n"
        "Commands:\n"
        "/pm <bet> – Start PvP match\n"
        "/profile – Your stats\n"
        "/daily – Claim daily coins\n"
        "/leaderboard – Top players\n"
        "/add <user_id> <coins> – Admin only"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if get_user(user.id):
        await update.message.reply_text("✅ You're already registered.")
    else:
        users_col.insert_one({
            "_id": user.id,
            "name": user.first_name,
            "coins": 1000,
            "wins": 0,
            "losses": 0,
            "last_daily": None
        })
        await update.message.reply_text("🎉 Registered! You got ₹1000 to start!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("❗ Use /register first.")
        return
    await update.message.reply_text(format_profile(user))

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user:
        await update.message.reply_text("❗ Use /register first.")
        return
    now = datetime.datetime.utcnow()
    last = user.get("last_daily")
    if last and (now - last).total_seconds() < 86400:
        left = 86400 - (now - last).total_seconds()
        await update.message.reply_text(
            f"⏳ Come back in {int(left//3600)}h {int((left%3600)//60)}m."
        )
        return
    inc_user(uid, "coins", 500)
    update_user(uid, {"last_daily": now})
    await update.message.reply_text("💸 You received ₹500 daily bonus!")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Unauthorized.")
        return
    try:
        uid = int(context.args[0])
        coins = int(context.args[1])
        inc_user(uid, "coins", coins)
        await update.message.reply_text(f"✅ Added ₹{coins} to user {uid}.")
    except:
        await update.message.reply_text("❗ Usage: /add <user_id> <coins>")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = users_col.find().sort("coins", -1).limit(10)
    text = "🏆 Leaderboard:\n\n"
    for i, u in enumerate(top, 1):
        text += f"{i}. {u['name']} – ₹{u.get('coins', 0)}\n"
    await update.message.reply_text(text)
# --- PART 3 ---

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    bet = int(context.args[0]) if context.args else 0

    udata = get_user(uid)
    if not udata or udata.get("coins", 0) < bet:
        await update.message.reply_text("❗ Not enough coins or not registered.")
        return

    match_id = f"{update.effective_chat.id}_{update.message.message_id}"
    match = {
        "_id": match_id,
        "players": [uid],
        "names": [user.first_name],
        "bets": bet,
        "scores": {uid: 0},
        "wickets": {uid: 0},
        "choices": {},
        "state": "waiting",
        "turn": None,
        "target": None,
        "innings": 1
    }
    matches_col.insert_one(match)

    join_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Join Match", callback_data=f"join_{match_id}")]
    ])
    await update.message.reply_text(
        f"🕹️ {user.first_name} started a match!\nBet: ₹{bet}\nWaiting for opponent...",
        reply_markup=join_btn
    )
# --- PART 4 ---

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data.startswith("join_"):
        match_id = data[5:]
        match = matches_col.find_one({"_id": match_id})
        if not match or len(match["players"]) == 2:
            await query.edit_message_text("❗ Match already started or invalid.")
            return
        match["players"].append(uid)
        match["names"].append(query.from_user.first_name)
        match["scores"][uid] = 0
        match["wickets"][uid] = 0
        match["state"] = "ongoing"
        match["turn"] = match["players"][0]
        matches_col.replace_one({"_id": match_id}, match)

        for pid in match["players"]:
            inc_user(pid, "coins", -match["bets"])

        await query.edit_message_text(
            f"🎮 Match started!\n"
            f"{match['names'][0]} vs {match['names'][1]}\n"
            f"{match['names'][0]} is batting first.",
            reply_markup=InlineKeyboardMarkup(BUTTONS)
        )
        return

    if data.startswith("num_"):
        num = int(data.split("_")[1])
        match_id = f"{query.message.chat.id}_{query.message.message_id}"
        match = matches_col.find_one({"_id": match_id})
        if not match or uid not in match["players"]:
            return

        match["choices"][str(uid)] = num
        matches_col.replace_one({"_id": match_id}, match)

        if len(match["choices"]) < 2:
            other = [p for p in match["players"] if p != uid][0]
            await query.edit_message_text(
                f"{query.from_user.first_name} chose a number.\n"
                f"Waiting for {match['names'][match['players'].index(other)]}...",
                reply_markup=InlineKeyboardMarkup(BUTTONS)
            )
            return

        p1, p2 = match["players"]
        b1 = match["choices"].get(str(p1))
        b2 = match["choices"].get(str(p2))
        bat = match["turn"]
        bowl = p2 if bat == p1 else p1

        if b1 == b2:
            match["wickets"][bat] += 1
            out = True
        else:
            match["scores"][bat] += b1 if bat == p1 else b2
            out = False

        text = (
            f"🔢 {match['names'][p1 == bat]}: {b1} | "
            f"{match['names'][p2 == bat]}: {b2}\n"
        )

        if out:
            text += f"💥 WICKET! {match['names'][match['players'].index(bat)]} is OUT!\n"
            if match["wickets"][bat] >= 2:
                if match["innings"] == 1:
                    match["innings"] = 2
                    match["target"] = match["scores"][bat] + 1
                    match["turn"] = bowl
                    match["choices"] = {}
                    matches_col.replace_one({"_id": match_id}, match)
                    await query.edit_message_text(
                        f"{text}\nInnings Over. Target: {match['target']}\n"
                        f"{match['names'][match['players'].index(bowl)]} batting now.",
                        reply_markup=InlineKeyboardMarkup(BUTTONS)
                    )
                    return
                else:
                    win1 = match["scores"][p1]
                    win2 = match["scores"][p2]
                    if win1 == win2:
                        result = "🤝 It's a TIE!"
                    elif win1 > win2:
                        winner = match["names"][0]
                        result = f"🏆 {winner} wins!"
                        inc_user(p1, "wins", 1)
                        inc_user(p2, "losses", 1)
                        inc_user(p1, "coins", match["bets"] * 2)
                    else:
                        winner = match["names"][1]
                        result = f"🏆 {winner} wins!"
                        inc_user(p2, "wins", 1)
                        inc_user(p1, "losses", 1)
                        inc_user(p2, "coins", match["bets"] * 2)
                    matches_col.delete_one({"_id": match_id})
                    await query.edit_message_text(f"{text}\n{result}")
                    return

        match["choices"] = {}
        matches_col.replace_one({"_id": match_id}, match)
        await query.edit_message_text(
            f"{text}\n"
            f"{match['names'][match['players'].index(match['turn'])]} is batting.",
            reply_markup=InlineKeyboardMarkup(BUTTONS)
        )

# === MAIN ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("pm", pm))
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling()

if __name__ == "__main__":
    main()
