import random
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

matches = {}
users = {}
last_daily_claim = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Hand Cricket PvP Bot!\n"
        "Use /register to join and get 4000 CCG!\n"
        "Then use /start_pvp to play a match."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in users:
        await update.message.reply_text("You are already registered!")
        return
    users[user.id] = {
        "name": user.first_name,
        "id": user.id,
        "balance": 4000,
        "wins": 0,
        "losses": 0,
    }
    await update.message.reply_text("Registered successfully! You got 4000 CCG!")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = int(time.time())
    if user.id not in users:
        await update.message.reply_text("You need to /register first!")
        return
    last_time = last_daily_claim.get(user.id, 0)
    if now - last_time < 86400:
        remaining = 86400 - (now - last_time)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await update.message.reply_text(
            f"You already claimed daily reward!\nCome back in {hours}h {minutes}m."
        )
    else:
        users[user.id]["balance"] += 3000
        last_daily_claim[user.id] = now
        await update.message.reply_text("You received 3000 CCG as daily reward!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in users:
        await update.message.reply_text("You need to /register first!")
        return
    u = users[user.id]
    msg = (
        f"**Profile**\n\n"
        f"**Name    :** {u['name']}\n"
        f"**ID      :** {u['id']}\n"
        f"**Balance :** {u['balance']} CCG\n"
        f"**Wins    :** {u['wins']}\n"
        f"**Losses  :** {u['losses']}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

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
async def join_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    if chat_id not in matches:
        await query.answer("No active match found.")
        return
    match = matches[chat_id]
    if len(match["players"]) >= 2:
        await query.answer("Match already has 2 players.")
        return
    if user in match["players"]:
        await query.answer("You're already in the match.")
        return
    match["players"].append(user)
    match["state"] = "toss"
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=match["message_id"],
        text=f"Match between {match['players'][0].first_name} and {user.first_name}!\nToss time!\n{match['players'][0].first_name}, choose Heads or Tails:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data="toss_heads")],
            [InlineKeyboardButton("Tails", callback_data="toss_tails")],
        ])
    )

async def toss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data.split("_")[1]
    chat_id = query.message.chat.id
    match = matches[chat_id]
    p1, p2 = match["players"]
    result = random.choice(["heads", "tails"])
    winner = p1 if choice == result else p2
    match["toss_winner"] = winner
    match["state"] = "bat_bowl_choice"
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=match["message_id"],
        text=f"Toss result: {result.capitalize()}!\n{winner.first_name} won the toss. Choose to Bat or Bowl:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Bat", callback_data="choose_bat")],
            [InlineKeyboardButton("Bowl", callback_data="choose_bowl")],
        ])
    )

async def bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data.split("_")[1]
    chat_id = query.message.chat.id
    match = matches[chat_id]
    p1, p2 = match["players"]
    toss_winner = match["toss_winner"]
    if choice == "bat":
        match["batting"] = toss_winner
        match["bowling"] = p2 if toss_winner == p1 else p1
    else:
        match["bowling"] = toss_winner
        match["batting"] = p2 if toss_winner == p1 else p1
    match["scores"] = {match["batting"].id: 0}
    match["state"] = "waiting_batsman"
    await send_turn_keyboard(chat_id, context, match)

async def send_turn_keyboard(chat_id, context, match):
    batting = match["batting"]
    bowler = match["bowling"]
    match["state"] = "waiting_batsman"
    keyboard = [[InlineKeyboardButton(str(i), callback_data=f"bat_{i}")] for i in range(1, 7)]
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=match["message_id"],
        text=f"{batting.first_name}, choose your number to bat:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def bat_input_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches[chat_id]
    batting = match["batting"]
    bowler = match["bowling"]
    bat_choice = int(query.data.split("_")[1])
    match["bat_choice"] = bat_choice
    match["state"] = "waiting_bowler"
    keyboard = [[InlineKeyboardButton(str(i), callback_data=f"bowl_{i}")] for i in range(1, 7)]
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=match["message_id"],
        text=f"{bowler.first_name}, choose your number to bowl:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def bowl_input_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches[chat_id]
    batting = match["batting"]
    bowler = match["bowling"]
    bowl_choice = int(query.data.split("_")[1])
    bat_choice = match["bat_choice"]
    score = match["scores"].get(batting.id, 0)
    if bat_choice == bowl_choice:
        match["state"] = "end_innings"
        match["target"] = score
        match["batting"], match["bowling"] = bowler, batting
        match["scores"][match["batting"].id] = 0
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=match["message_id"],
            text=f"OUT!\n{batting.first_name} scored {score}.\n\n{match['batting'].first_name}, your turn to chase {score + 1}!",
        )
        await send_turn_keyboard(chat_id, context, match)
    else:
        score += bat_choice
        match["scores"][batting.id] = score
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=match["message_id"],
            text=f"{batting.first_name} chose - {bat_choice}, {bowler.first_name} chose - {bowl_choice}\nTotal Score: {score}\n\n{batting.first_name}, choose again:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(str(i), callback_data=f"bat_{i}")] for i in range(1, 7)])
        )

async def handle_result(chat_id, context, match):
    p1, p2 = match["players"]
    s1 = match["scores"].get(p1.id, 0)
    s2 = match["scores"].get(p2.id, 0)
    winner = None
    if s1 > s2:
        winner = p1
        users[p1.id]["wins"] += 1
        users[p2.id]["losses"] += 1
    elif s2 > s1:
        winner = p2
        users[p2.id]["wins"] += 1
        users[p1.id]["losses"] += 1
    msg = f"Match Over!\n{p1.first_name}: {s1}\n{p2.first_name}: {s2}\n\nWinner: {winner.first_name if winner else 'Draw!'}"
    await context.bot.edit_message_text(chat_id=chat_id, message_id=match["message_id"], text=msg)
    del matches[chat_id]

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("start_pvp", start_pvp))

    app.add_handler(CallbackQueryHandler(join_match_callback, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_callback, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(bat_bowl_choice_callback, pattern="^choose_"))
    app.add_handler(CallbackQueryHandler(bat_input_callback, pattern="^bat_"))
    app.add_handler(CallbackQueryHandler(bowl_input_callback, pattern="^bowl_"))

    app.run_polling()
