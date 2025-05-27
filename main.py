import json
import random
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes,
)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# Load and Save user data
def load_users():
    try:
        with open("users.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_users():
    with open("users.json", "w") as f:
        json.dump(users, f)

matches = {}
users = load_users()
admins = {7361215114}  # Your Telegram ID

def current_date():
    return datetime.utcnow().date().isoformat()

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

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in users:
        await update.message.reply_text("Use /register first.")
        return
    today = current_date()
    if users[user_id]["last_daily"] == today:
        await update.message.reply_text("You already claimed daily coins today.")
        return
    users[user_id]["balance"] += 3000
    users[user_id]["last_daily"] = today
    save_users()
    await update.message.reply_text("You received 3000 CCG coins!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in users:
        await update.message.reply_text("Use /register first.")
        return
    data = users[user_id]
    text = (
        f"👤 *Profile*\n\n"
        f"*Name:* {data['name']}\n"
        f"*ID:* {user_id}\n"
        f"*Balance:* {data['balance']} CCG\n"
        f"*Wins:* {data['wins']}\n"
        f"*Losses:* {data['losses']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if int(user_id) not in admins:
        await update.message.reply_text("Not authorized.")
        return
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("Usage: /add <user_id> <amount>")
            return
        target_id = args[0]
        amount = int(args[1])
        if target_id not in users:
            await update.message.reply_text("User not found.")
            return
        users[target_id]["balance"] += amount
        save_users()
        await update.message.reply_text(f"Added {amount} to {target_id}.")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not users:
        await update.message.reply_text("No users yet.")
        return
    sorted_users = sorted(users.items(), key=lambda x: x[1]["balance"], reverse=True)
    text = "*🏅 Leaderboard - Top 10 🏅*\n\n"
    for i, (uid, data) in enumerate(sorted_users[:10], 1):
        text += f"{i}. {data['name']} - {data['balance']} CCG\n"
    await update.message.reply_text(text, parse_mode="Markdown")
async def start_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in users:
        await update.message.reply_text("Use /register first.")
        return
    if user_id in matches:
        await update.message.reply_text("You're already in a match.")
        return
    keyboard = [
        [InlineKeyboardButton("Create Match", callback_data="create")],
        [InlineKeyboardButton("Join Match", callback_data="join")]
    ]
    await update.message.reply_text("Choose:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = str(user.id)

    if query.data == "create":
        if user_id in matches:
            await query.edit_message_text("You're already in a match.")
            return
        match_id = str(random.randint(1000, 9999))
        matches[user_id] = {
            "host": user_id,
            "players": [user_id],
            "state": "waiting",
            "match_id": match_id
        }
        await query.edit_message_text(
            f"Match created!\nAsk a friend to use /join {match_id}"
        )

    elif query.data.startswith("join"):
        pass  # Handled in /join command

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in users:
        await update.message.reply_text("Use /register first.")
        return
    if user_id in matches:
        await update.message.reply_text("You're already in a match.")
        return
    try:
        match_id = context.args[0]
    except:
        await update.message.reply_text("Usage: /join <match_id>")
        return
    host_id = None
    for uid, match in matches.items():
        if match.get("match_id") == match_id and match["state"] == "waiting":
            host_id = uid
            break
    if not host_id:
        await update.message.reply_text("No such open match found.")
        return

    match = matches[host_id]
    match["players"].append(user_id)
    match["state"] = "toss"
    match["innings"] = 1
    match["batting"] = host_id
    match["bowling"] = user_id
    match["scores"] = {host_id: 0, user_id: 0}
    match["turn"] = 0
    match["choices"] = {}

    matches[user_id] = match
    msg = await update.message.reply_text(
        f"Match found!\nTossing coin...",
    )
    await start_toss(msg, match)

async def start_toss(msg, match):
    toss_winner = random.choice(match["players"])
    toss_loser = [p for p in match["players"] if p != toss_winner][0]
    match["batting"] = toss_winner
    match["bowling"] = toss_loser
    match["state"] = "playing"
    await msg.edit_text(
        f"Toss won by {users[toss_winner]['name']}.\n"
        f"They will bat first!"
    )
    await send_play_prompt(msg, match)

async def send_play_prompt(msg, match):
    keyboard = [[InlineKeyboardButton(str(i), callback_data=f"play_{i}")]
                for i in range(1, 7)]
    for uid in match["players"]:
        try:
            await msg.bot.send_message(
                chat_id=int(uid),
                text="Choose your number (1-6):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
    match["choices"] = {}

async def play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if user_id not in matches:
        await query.edit_message_text("Not in a match.")
        return
    match = matches[user_id]
    if not query.data.startswith("play_"):
        return
    choice = int(query.data.split("_")[1])
    match["choices"][user_id] = choice

    if len(match["choices"]) == 2:
        bat = match["batting"]
        bowl = match["bowling"]
        b_choice = match["choices"][bat]
        w_choice = match["choices"][bowl]

        result_text = (
            f"{users[bat]['name']} (Bat): {b_choice}\n"
            f"{users[bowl]['name']} (Bowl): {w_choice}\n"
        )

        if b_choice == w_choice:
            result_text += "OUT!\n"
            if match["innings"] == 1:
                match["innings"] = 2
                match["batting"], match["bowling"] = bowl, bat
                match["choices"] = {}
                await query.edit_message_text(result_text + "Innings Over! Second innings begins.")
                await send_play_prompt(query, match)
                return
            else:
                result_text += match_result(match)
                await end_match(match, query, result_text)
                return
        else:
            match["scores"][bat] += b_choice
            result_text += f"{users[bat]['name']} scored {b_choice} runs!\n"

        await query.edit_message_text(result_text)
        await send_play_prompt(query, match)

def match_result(match):
    p1, p2 = match["players"]
    s1, s2 = match["scores"][p1], match["scores"][p2]
    if s1 == s2:
        return "Match Drawn!"
    winner = p1 if s1 > s2 else p2
    loser = p2 if winner == p1 else p1
    users[winner]["wins"] += 1
    users[loser]["losses"] += 1
    users[winner]["balance"] += 1000
    users[loser]["balance"] += 250
    save_users()
    return f"{users[winner]['name']} won the match!"

async def end_match(match, query, text):
    for uid in match["players"]:
        try:
            await query.bot.send_message(chat_id=int(uid), text=text)
        except:
            pass
        del matches[uid]

# MAIN FUNCTION
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("startmatch", start_match))
    app.add_handler(CommandHandler("join", join_match))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(create|join)"))
    app.add_handler(CallbackQueryHandler(play_callback, pattern="^play_"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
