import json
import random
import time
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
)

TOKEN = "YOUR_BOT_TOKEN"
ADMIN_IDS = [123456789]  # Replace with actual admin user IDs

USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def load_matches():
    try:
        with open(MATCHES_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_matches(matches):
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f)

def register_user(user_id, name):
    users = load_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            "name": name, "coins": 1000, "wins": 0, "last_daily": 0
        }
        save_users(users)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id, update.effective_user.first_name)
    await update.message.reply_text(
        f"Welcome to Hand Cricket Bot! 🏏\nUse /register to get started.\n\nAvailable commands:\n"
        "/pm <bet> - Start PvP match\n"
        "/profile - Show your stats\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - Top users\n"
        "/help - Command list\n"
        "/add <id> <coins> - Admin only"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Welcome message\n"
        "/register - Get 1000 coins\n"
        "/pm <bet> - Start match\n"
        "/profile - Your stats\n"
        "/daily - Daily coins\n"
        "/leaderboard - Rankings\n"
        "/add <user_id> <coins> - Admin only"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id, update.effective_user.first_name)
    await update.message.reply_text("You are registered and got 1000 coins! 🪙")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        user = users[uid]
        await update.message.reply_text(
            f"👤 {user['name']}'s Profile\nCoins: {user['coins']} 🪙\nWins: {user['wins']}"
        )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    users = load_users()
    if uid not in users:
        await update.message.reply_text("Please use /register first.")
        return
    now = int(time.time())
    if now - users[uid]["last_daily"] >= 86400:
        users[uid]["coins"] += 250
        users[uid]["last_daily"] = now
        save_users(users)
        await update.message.reply_text("You received 250 daily coins! 🪙")
    else:
        remaining = 86400 - (now - users[uid]["last_daily"])
        hours = remaining // 3600
        mins = (remaining % 3600) // 60
        await update.message.reply_text(f"Please wait {hours}h {mins}m for next claim.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    top = sorted(users.items(), key=lambda x: x[1]['coins'], reverse=True)[:10]
    text = "🏆 Top 10 by Coins:\n"
    for i, (uid, data) in enumerate(top, 1):
        text += f"{i}. {data['name']} - {data['coins']} 🪙\n"
    await update.message.reply_text(text)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    uid, coins = context.args
    users = load_users()
    if uid in users:
        users[uid]["coins"] += int(coins)
        save_users(users)
        await update.message.reply_text("Coins added!")
    else:
        await update.message.reply_text("User not found.")
def build_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)]
    ])

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    users = load_users()
    register_user(user.id, user.first_name)

    bet = int(context.args[0]) if context.args else 0
    if users[uid]["coins"] < bet:
        await update.message.reply_text("Not enough coins.")
        return

    matches = load_matches()
    matches[uid] = {
        "player1": uid,
        "p1name": user.first_name,
        "bet": bet,
        "stage": "waiting"
    }
    save_matches(matches)

    join_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Match", callback_data=f"join_{uid}")]
    ])
    await update.message.reply_text(
        f"{user.first_name} started a match! 🏏\nBet: {bet} 🪙\nClick below to join!",
        reply_markup=join_btn
    )

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    data = query.data
    matches = load_matches()
    users = load_users()

    if data.startswith("join_"):
        host_id = data.split("_")[1]
        if host_id not in matches or matches[host_id]["stage"] != "waiting":
            await query.message.edit_text("Match no longer available.")
            return
        match = matches[host_id]
        match["player2"] = uid
        match["p2name"] = query.from_user.first_name
        match["stage"] = "toss"
        match["msg_id"] = query.message.message_id
        save_matches(matches)

        toss_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data="toss_H"),
             InlineKeyboardButton("Tails", callback_data="toss_T")]
        ])
        await query.message.edit_text(
            f"{match['p1name']} vs {match['p2name']}\n\n{match['p1name']}, choose Heads or Tails!",
            reply_markup=toss_btns
        )
        return

    if data.startswith("toss_"):
        for match in matches.values():
            if match.get("stage") == "toss" and match["player1"] == uid:
                player_choice = data.split("_")[1]
                bot_choice = random.choice(["H", "T"])
                toss_winner = match["player1"] if player_choice == bot_choice else match["player2"]
                match["batting"] = toss_winner
                match["bowling"] = match["player2"] if toss_winner == match["player1"] else match["player1"]
                match["stage"] = "playing"
                match["score"] = 0
                match["innings"] = 1
                match["target"] = None
                match["inputs"] = {}
                save_matches(matches)
                await query.message.edit_text(
                    f"{match['p1name']} vs {match['p2name']}\n"
                    f"Toss: You chose {player_choice}, bot chose {bot_choice}.\n"
                    f"{users[match['batting']]['name']} will bat first!\n\n"
                    f"{users[match['batting']]['name']}, choose a number:",
                    reply_markup=build_buttons()
                )
                return

    if data.startswith("num_"):
        num = int(data.split("_")[1])
        for match in matches.values():
            if match.get("stage") == "playing" and uid in [match["batting"], match["bowling"]]:
                match["inputs"][uid] = num
                if len(match["inputs"]) == 1:
                    other = match["bowling"] if uid == match["batting"] else match["batting"]
                    await query.message.edit_text(
                        f"{users[uid]['name']} chose a number.\nNow it's {users[other]['name']}'s turn.",
                        reply_markup=build_buttons()
                    )
                else:
                    bat_num = match["inputs"][match["batting"]]
                    bowl_num = match["inputs"][match["bowling"]]
                    msg = f"Over {match['innings']}\n{users[match['batting']]['name']}: {bat_num} vs {users[match['bowling']]['name']}: {bowl_num}\n"
                    if bat_num == bowl_num:
                        msg += "❌ WICKET!\n"
                        if match["innings"] == 2:
                            winner = match["bowling"] if match["score"] < match["target"] else match["batting"]
                            loser = match["batting"] if winner == match["bowling"] else match["bowling"]
                            msg += f"{users[winner]['name']} won the match! 🏆"
                            bet = match["bet"]
                            users[winner]["coins"] += bet
                            users[loser]["coins"] -= bet
                            users[winner]["wins"] += 1
                            save_users(users)
                            del matches[match["player1"]]
                            save_matches(matches)
                            await query.message.edit_text(msg)
                            return
                        else:
                            match["innings"] = 2
                            match["target"] = match["score"] + 1
                            match["score"] = 0
                            match["batting"], match["bowling"] = match["bowling"], match["batting"]
                            match["inputs"] = {}
                            msg += f"Now {users[match['batting']]['name']} needs {match['target']} to win!\nChoose a number:"
                            save_matches(matches)
                            await query.message.edit_text(msg, reply_markup=build_buttons())
                            return
                    else:
                        match["score"] += bat_num
                        if match["innings"] == 2 and match["score"] >= match["target"]:
                            msg += f"{users[match['batting']]['name']} scored {match['score']} and won! 🏆"
                            winner = match["batting"]
                            loser = match["bowling"]
                            bet = match["bet"]
                            users[winner]["coins"] += bet
                            users[loser]["coins"] -= bet
                            users[winner]["wins"] += 1
                            save_users(users)
                            del matches[match["player1"]]
                            save_matches(matches)
                            await query.message.edit_text(msg)
                            return
                        else:
                            msg += f"{users[match['batting']]['name']}'s Score: {match['score']}\nContinue batting:"
                            match["inputs"] = {}
                            save_matches(matches)
                            await query.message.edit_text(msg, reply_markup=build_buttons())
                            return

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("pm", pm))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CallbackQueryHandler(callback))

    app.bot.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("register", "Register for coins"),
        BotCommand("pm", "Start PvP match"),
        BotCommand("profile", "Show your profile"),
        BotCommand("daily", "Claim daily coins"),
        BotCommand("leaderboard", "Show leaderboard"),
        BotCommand("help", "List all commands")
    ])

    print("Bot is running...")
    app.run_polling()
