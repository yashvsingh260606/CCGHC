import json
import os
import random
from datetime import datetime
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

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

DATA_FILE = "users.json"
matches = {}
users = {}
admins = {7361215114}  # Replace with your Telegram user ID(s)

# Load user data from file
def load_users():
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            users = json.load(f)

# Save user data to file
def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

# Get current UTC date as string
def current_date():
    return datetime.utcnow().date().isoformat()

# Register command
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id in users:
        await update.message.reply_text(
            "You are already registered!\nUse /profile to check your stats."
        )
        return
    users[user_id] = {
        "name": user.first_name,
        "balance": 4000,
        "wins": 0,
        "losses": 0,
        "last_daily": None,
    }
    save_users()
    await update.message.reply_text(
        f"Welcome {user.first_name}! You have been awarded 4000 CCG coins."
    )

# Daily command
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in users:
        await update.message.reply_text(
            "You are not registered yet. Use /register first."
        )
        return
    today = current_date()
    if users[user_id]["last_daily"] == today:
        await update.message.reply_text(
            "You already claimed your daily coins today. Come back tomorrow!"
        )
        return
    users[user_id]["balance"] += 3000
    users[user_id]["last_daily"] = today
    save_users()
    await update.message.reply_text(
        "You received 3000 CCG coins as daily bonus!"
    )

# Profile command
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in users:
        await update.message.reply_text(
            "You are not registered yet. Use /register first."
        )
        return
    data = users[user_id]
    text = (
        f"👤 **Profile** 👤\n\n"
        f"**Name:** {data['name']}\n"
        f"**ID:** {user_id}\n"
        f"**Balance:** {data['balance']} CCG\n"
        f"**Wins:** {data['wins']}\n"
        f"**Losses:** {data['losses']}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# Add coins command for admin
async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in admins:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text(
                "Usage: /add <user_id> <amount>"
            )
            return
        target_id = args[0]
        amount = int(args[1])
        if target_id not in users:
            await update.message.reply_text("Target user not found.")
            return
        users[target_id]["balance"] += amount
        save_users()
        await update.message.reply_text(
            f"Added {amount} CCG coins to user {target_id}."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# Utility: create shot buttons in two rows (1-3, 4-6)
def shot_buttons():
    row1 = [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)]
    return [row1, row2]

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Hand Cricket PvP Bot!\n"
        "Use /start_pvp to begin a match.\n"
        "Use /register to create your profile.\n"
        "Use /daily to claim daily coins.\n"
        "Use /profile to view your stats."
    )

# Start PvP match command
async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id in matches:
        await update.message.reply_text("A match is already running in this chat!")
        return

    matches[chat_id] = {
        "players": [user],
        "state": "waiting_for_opponent",
        "message_id": None,
    }
    keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]]
    sent = await update.message.reply_text(
        f"{user.first_name} started a new match. Waiting for opponent...",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    matches[chat_id]["message_id"] = sent.message_id

# Join match callback
async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user = query.from_user

    match = matches.get(chat_id)
    if not match or match["state"] != "waiting_for_opponent":
        await query.answer("No open match to join.")
        return

    if user.id == match["players"][0].id:
        await query.answer("You already started the match!")
        return

    match["players"].append(user)
    match["state"] = "toss"

    keyboard = [
        [
            InlineKeyboardButton("Heads", callback_data="toss_heads"),
            InlineKeyboardButton("Tails", callback_data="toss_tails"),
        ]
    ]

    await query.edit_message_text(
        f"{user.first_name} joined the match!\n\n"
        f"{match['players'][0].first_name}, choose Heads or Tails for the toss:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await query.answer()

# Toss choice callback
async def toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "toss":
        await query.answer("No toss to choose.")
        return

    user = query.from_user
    if user.id != match["players"][0].id:
        await query.answer("Only the first player can choose toss.")
        return

    choice = query.data.split("_")[1]
    toss_result = random.choice(["heads", "tails"])
    match["toss_choice"] = choice
    match["toss_result"] = toss_result

    if choice == toss_result:
        match["toss_winner"] = match["players"][0]
        match["toss_loser"] = match["players"][1]
    else:
        match["toss_winner"] = match["players"][1]
        match["toss_loser"] = match["players"][0]

    match["state"] = "choose_play"

    keyboard = [
        [
            InlineKeyboardButton("Bat", callback_data="choose_bat"),
            InlineKeyboardButton("Bowl", callback_data="choose_bowl"),
        ]
    ]

    await query.edit_message_text(
        f"Toss result: {toss_result.capitalize()}\n"
        f"{match['toss_winner'].first_name} won the toss.\n"
        f"{match['toss_winner'].first_name}, choose to Bat or Bowl:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await query.answer()
# Bat/Bowl choice callback
async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "choose_play":
        await query.answer("Invalid state.")
        return

    user = query.from_user
    if user.id != match["toss_winner"].id:
        await query.answer("Only toss winner can choose.")
        return

    choice = query.data.split("_")[1]
    match["state"] = "playing"
    match["scores"] = {str(p.id): 0 for p in match["players"]}
    match["innings"] = 1
    match["turn"] = 0  # 0: batsman, 1: bowler
    match["batting"] = match["toss_winner"] if choice == "bat" else match["toss_loser"]
    match["bowling"] = match["toss_loser"] if choice == "bat" else match["toss_winner"]
    match["waiting"] = {}

    await query.edit_message_text(
        f"First Innings Begins!\n\n"
        f"{match['batting'].first_name} is Batting\n"
        f"{match['bowling'].first_name} is Bowling\n"
        "Both players, choose your numbers:"
    )

    kb = InlineKeyboardMarkup(shot_buttons())
    await context.bot.send_message(match["batting"].id, "You are Batting. Choose:", reply_markup=kb)
    await context.bot.send_message(match["bowling"].id, "You are Bowling. Choose:", reply_markup=kb)

# Shot callback
async def play_shot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id

    # find match the user is in
    for cid, m in matches.items():
        if m.get("batting") and user.id in [m["batting"].id, m["bowling"].id]:
            match = m
            chat_id = cid
            break
    else:
        await query.answer("No match found.")
        return

    shot = int(query.data.split("_")[1])
    match["waiting"][str(user.id)] = shot
    await query.answer("Move locked!")

    if len(match["waiting"]) < 2:
        return

    bat_shot = match["waiting"].get(str(match["batting"].id))
    bowl_shot = match["waiting"].get(str(match["bowling"].id))

    del match["waiting"]

    if bat_shot == bowl_shot:
        result = f"OUT!\n{match['batting'].first_name} chose {bat_shot}, {match['bowling'].first_name} chose {bowl_shot}."
        if match["innings"] == 1:
            match["innings"] = 2
            match["target"] = match["scores"][str(match["batting"].id)] + 1
            match["batting"], match["bowling"] = match["bowling"], match["batting"]
            match["waiting"] = {}
            result += f"\n\nSecond Innings Begins!\nTarget: {match['target']}"
            kb = InlineKeyboardMarkup(shot_buttons())
            await context.bot.send_message(match["batting"].id, "You are Batting. Choose:", reply_markup=kb)
            await context.bot.send_message(match["bowling"].id, "You are Bowling. Choose:", reply_markup=kb)
        else:
            p1 = match["players"][0]
            p2 = match["players"][1]
            score1 = match["scores"][str(p1.id)]
            score2 = match["scores"][str(p2.id)]
            if score1 == score2:
                result += "\n\nMatch Drawn!"
            elif score1 > score2:
                winner, loser = p1, p2
            else:
                winner, loser = p2, p1
            if score1 != score2:
                result += f"\n\n{winner.first_name} wins!"
                users[str(winner.id)]["balance"] += 1000
                users[str(loser.id)]["balance"] -= 500
                users[str(winner.id)]["wins"] += 1
                users[str(loser.id)]["losses"] += 1
            save_users()
            del matches[chat_id]
        await context.bot.send_message(chat_id, result)
    else:
        match["scores"][str(match["batting"].id)] += bat_shot
        score = match["scores"][str(match["batting"].id)]
        msg = (
            f"{match['batting'].first_name} played {bat_shot}, "
            f"{match['bowling'].first_name} played {bowl_shot}.\n"
            f"Total Score: {score}"
        )
        await context.bot.send_message(chat_id, msg)

        if match["innings"] == 2 and score >= match["target"]:
            result = f"{match['batting'].first_name} chased the target!\n\n{match['batting'].first_name} wins!"
            users[str(match["batting"].id)]["balance"] += 1000
            users[str(match["bowling"].id)]["balance"] -= 500
            users[str(match["batting"].id)]["wins"] += 1
            users[str(match["bowling"].id)]["losses"] += 1
            save_users()
            await context.bot.send_message(chat_id, result)
            del matches[chat_id]
            return

        kb = InlineKeyboardMarkup(shot_buttons())
        await context.bot.send_message(match["batting"].id, "You are Batting. Choose:", reply_markup=kb)
        await context.bot.send_message(match["bowling"].id, "You are Bowling. Choose:", reply_markup=kb)

# Leaderboard
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
    text = "**🏆 Leaderboard 🏆**\n\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        text += f"{i}. {data['name']} - {data['balance']} CCG\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# Set bot command list
async def set_commands(application):
    commands = [
        BotCommand("start", "Bot info"),
        BotCommand("register", "Register your profile"),
        BotCommand("daily", "Claim daily coins"),
        BotCommand("profile", "View your profile"),
        BotCommand("start_pvp", "Start a PvP hand cricket match"),
        BotCommand("leaderboard", "Show top 10 players"),
        BotCommand("add", "Admin: Add coins to a user")
    ]
    await application.bot.set_my_commands(commands)

# Main bot setup
if __name__ == "__main__":
    load_users()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^choose_"))
    app.add_handler(CallbackQueryHandler(play_shot, pattern="^shot_"))

    app.run_polling(close_loop=False)
    app.create_task(set_commands(app))
