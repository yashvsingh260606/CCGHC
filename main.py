import json
import os
import random
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
DATA_FILE = "users.json"
MATCH_FILE = "matches.json"
ADMINS = [123456789]  # Replace with your Telegram user ID(s)

def load_data(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

users = load_data(DATA_FILE)
matches = load_data(MATCH_FILE)

def save_all():
    save_data(DATA_FILE, users)
    save_data(MATCH_FILE, matches)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 *Welcome to Hand Cricket Bot!*\n\n"
        "Use /register to start your journey!\n"
        "Type /help to see available commands.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Available Commands:*\n"
        "/start - Welcome message\n"
        "/register - Get free starting coins\n"
        "/profile - View your stats\n"
        "/daily - Claim daily bonus\n"
        "/leaderboard - Top players\n"
        "/pm <bet> - Start/join a match\n"
        "/add <user_id> <coins> - Admin only\n"
        "/help - List all commands",
        parse_mode="Markdown"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    uid = str(user.id)
    if uid not in users:
        users[uid] = {
            "name": user.first_name,
            "coins": 500,
            "wins": 0,
            "losses": 0,
            "last_daily": 0
        }
        save_all()
        await update.message.reply_text("✅ Registered successfully! You got 500 coins.")
    else:
        await update.message.reply_text("⚠️ You are already registered.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid in users:
        u = users[uid]
        await update.message.reply_text(
            f"*👤 Profile:*\n"
            f"Name: {u['name']}\n"
            f"ID: {uid}\n"
            f"💰 Coins: {u['coins']}\n"
            f"📊 Wins: {u['wins']} | Losses: {u['losses']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ You are not registered. Use /register.")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    now = time.time()
    if uid in users:
        if now - users[uid]["last_daily"] >= 86400:
            users[uid]["coins"] += 200
            users[uid]["last_daily"] = now
            save_all()
            await update.message.reply_text("✅ You claimed 200 daily coins!")
        else:
            remaining = int(86400 - (now - users[uid]["last_daily"]))
            hrs, mins = divmod(remaining // 60, 60)
            await update.message.reply_text(f"⏳ Come back in {hrs}h {mins}m for your next daily reward.")
    else:
        await update.message.reply_text("❌ You are not registered. Use /register.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(users.items(), key=lambda x: x[1]["coins"], reverse=True)[:10]
    msg = "*🏆 Leaderboard (by Coins):*\n"
    for i, (uid, u) in enumerate(top, 1):
        msg += f"{i}. {u['name']} - {u['coins']} coins\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid not in map(str, ADMINS):
        return await update.message.reply_text("❌ You are not an admin.")
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
        if target_id in users:
            users[target_id]["coins"] += amount
            save_all()
            await update.message.reply_text(f"✅ Added {amount} coins to {users[target_id]['name']}.")
        else:
            await update.message.reply_text("❌ User not found.")
    except:
        await update.message.reply_text("Usage: /add <user_id> <coins>")

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid not in users:
        return await update.message.reply_text("❌ Use /register first.")
    bet = int(context.args[0]) if context.args else 0
    if users[uid]["coins"] < bet:
        return await update.message.reply_text("❌ Not enough coins.")
    match_id = str(update.message.chat_id)
    if match_id in matches:
        return await update.message.reply_text("⚠️ Match already active.")
    matches[match_id] = {
        "p1": uid,
        "p2": None,
        "bet": bet,
        "state": "waiting"
    }
    save_all()
    btn = [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    await update.message.reply_text(
        f"🎮 {users[uid]['name']} started a match!\n💰 Bet: {bet} coins\n\nWaiting for opponent...",
        reply_markup=InlineKeyboardMarkup(btn)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("join_"):
        match_id = data.split("_")[1]
        if match_id in matches:
            match = matches[match_id]
            if match["state"] != "waiting":
                return await query.edit_message_text("❌ Match already started.")
            uid = str(query.from_user.id)
            if uid == match["p1"]:
                return await query.edit_message_text("⚠️ You can't join your own match.")
            if uid not in users or users[uid]["coins"] < match["bet"]:
                return await query.edit_message_text("❌ Not enough coins or not registered.")
            match["p2"] = uid
            match["turn"] = "toss"
            save_all()
            await query.edit_message_text("🪙 Toss time! Heads or Tails?")
            btns = [[InlineKeyboardButton("Heads", callback_data=f"toss_heads_{match_id}"),
                     InlineKeyboardButton("Tails", callback_data=f"toss_tails_{match_id}")]]
            await query.message.edit_text(
                f"{users[match['p1']]['name']} vs {users[uid]['name']}\n\n{users[match['p1']]['name']}, choose Heads or Tails!",
                reply_markup=InlineKeyboardMarkup(btns)
            )
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = str(query.from_user.id)

    if data.startswith("join_"):
        match_id = data.split("_")[1]
        if match_id not in matches:
            return
        match = matches[match_id]
        if match["state"] != "waiting":
            return
        if uid == match["p1"] or uid == match["p2"]:
            return
        if uid not in users or users[uid]["coins"] < match["bet"]:
            return await query.edit_message_text("❌ Not enough coins or not registered.")
        match["p2"] = uid
        match["state"] = "toss"
        match["message_id"] = query.message.message_id
        save_all()
        btns = [[InlineKeyboardButton("Heads", callback_data=f"toss_heads_{match_id}"),
                 InlineKeyboardButton("Tails", callback_data=f"toss_tails_{match_id}")]]
        await query.message.edit_text(
            f"🪙 Toss Time!\n{users[match['p1']]['name']} vs {users[uid]['name']}\n\n"
            f"{users[match['p1']]['name']}, choose Heads or Tails!",
            reply_markup=InlineKeyboardMarkup(btns)
        )
        return

    if data.startswith("toss_"):
        call, choice, match_id = data.split("_")
        match = matches.get(match_id)
        if not match or match["state"] != "toss":
            return
        toss_winner = match["p1"]
        toss_loser = match["p2"]
        coin = random.choice(["heads", "tails"])
        won_toss = (choice == coin)
        match["bat_first"] = toss_winner if won_toss else toss_loser
        match["bat"] = match["bat_first"]
        match["bowl"] = match["p2"] if match["bat"] == match["p1"] else match["p1"]
        match["innings"] = 1
        match["scores"] = {match["p1"]: 0, match["p2"]: 0}
        match["turns"] = {}
        match["state"] = "playing"
        save_all()
        await query.message.edit_text(
            f"🪙 Coin: {coin.title()}!\n"
            f"{users[match['bat']]['name']} bats first!\n\n"
            f"{users[match['bat']]['name']}, choose a number:",
            reply_markup=number_buttons()
        )
        return

    if data.startswith("num_"):
        _, num, match_id = data.split("_")
        num = int(num)
        match = matches.get(match_id)
        if not match or match["state"] != "playing":
            return
        if uid != match["bat"] and uid != match["bowl"]:
            return
        match["turns"][uid] = num
        if len(match["turns"]) < 2:
            next_user = match["bowl"] if uid == match["bat"] else match["bat"]
            await query.message.edit_text(
                f"{users[uid]['name']} chose a number.\n"
                f"Now it's {users[next_user]['name']}'s turn!",
                reply_markup=number_buttons()
            )
            save_all()
            return
        # Both chosen
        bnum = match["turns"][match["bat"]]
        bwnum = match["turns"][match["bowl"]]
        text = (f"⚔️ {users[match['bat']]['name']} vs {users[match['bowl']]['name']}\n"
                f"Bat: {bnum}, Bowl: {bwnum}\n")

        if bnum == bwnum:
            text += f"❌ OUT! {users[match['bat']]['name']} is out!\n"
            if match["innings"] == 1:
                match["innings"] = 2
                match["bat"], match["bowl"] = match["bowl"], match["bat"]
                match["bat_first"] = match["bat"]
                match["turns"] = {}
                save_all()
                await query.message.edit_text(
                    text + f"Now {users[match['bat']]['name']} will bat.\nChoose a number:",
                    reply_markup=number_buttons()
                )
                return
            else:
                await end_match(query, match_id)
                return
        else:
            match["scores"][match["bat"]] += bnum
            match["turns"] = {}
            if match["innings"] == 2:
                target = match["scores"][match["bowl"]] + 1
                if match["scores"][match["bat"]] >= target:
                    await end_match(query, match_id)
                    return
            save_all()
            await query.message.edit_text(
                text + f"{users[match['bat']]['name']} continues...\n"
                f"Score: {match['scores'][match['bat']]}\n\nChoose a number:",
                reply_markup=number_buttons()
            )
            return

def number_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_match") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_match") for i in range(4, 7)]
    ])

async def end_match(query, match_id):
    match = matches[match_id]
    p1, p2 = match["p1"], match["p2"]
    score1, score2 = match["scores"][p1], match["scores"][p2]
    bet = match["bet"]
    winner, loser = (p1, p2) if score1 > score2 else (p2, p1)
    if score1 == score2:
        msg = f"🤝 Match tied!\n{users[p1]['name']}: {score1}\n{users[p2]['name']}: {score2}"
    else:
        msg = (f"🏆 {users[winner]['name']} won the match!\n"
               f"{users[p1]['name']}: {score1}\n"
               f"{users[p2]['name']}: {score2}")
        users[winner]["wins"] += 1
        users[loser]["losses"] += 1
        if bet > 0:
            users[winner]["coins"] += bet
            users[loser]["coins"] -= bet
    save_all()
    await query.message.edit_text(msg)
    del matches[match_id]
    save_all()

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("pm", pm))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running...")
    app.run_polling()
