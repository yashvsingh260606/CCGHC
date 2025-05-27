import json
import random
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

matches = {}
DATA_FILE = "players_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the Hand Cricket PvP Bot!\nUse /register to register and get 4000 CCG.\nUse /daily to claim 3000 CCG daily.\nUse /profile to see your stats.\nUse /start_pvp to begin a PvP match!")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)

    if uid in data:
        await update.message.reply_text("You're already registered!")
    else:
        data[uid] = {
            "name": user.first_name,
            "balance": 4000,
            "wins": 0,
            "losses": 0,
            "last_daily": "",
        }
        save_data(data)
        await update.message.reply_text("Registration complete! You received 4000 CCG!")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime

    user = update.effective_user
    uid = str(user.id)
    data = load_data()
    today = datetime.utcnow().date().isoformat()

    if uid not in data:
        await update.message.reply_text("You're not registered. Use /register first.")
        return

    if data[uid]["last_daily"] == today:
        await update.message.reply_text("You've already claimed your daily CCG today!")
    else:
        data[uid]["balance"] += 3000
        data[uid]["last_daily"] = today
        save_data(data)
        await update.message.reply_text("You've received 3000 CCG for your daily reward!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    data = load_data()

    if uid not in data:
        await update.message.reply_text("You're not registered. Use /register first.")
    else:
        p = data[uid]
        await update.message.reply_text(
            f"**Profile**\n"
            f"Name: {p['name']}\n"
            f"ID: {uid}\n"
            f"Balance: {p['balance']} CCG\n"
            f"Wins: {p['wins']}\n"
            f"Losses: {p['losses']}",
            parse_mode="Markdown"
        )

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
async def handle_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    choice = query.data.split("_")[1]

    match = matches[chat_id]
    p1, p2 = match["players"]
    toss_result = random.choice(["heads", "tails"])

    winner = p1 if toss_result == choice else p2
    match["toss_winner"] = winner
    match["batting_first"] = None
    match["state"] = "choose_bat_bowl"

    keyboard = [
        [
            InlineKeyboardButton("Bat", callback_data="choose_bat"),
            InlineKeyboardButton("Bowl", callback_data="choose_bowl"),
        ]
    ]

    await query.edit_message_text(
        f"Toss result: {toss_result.capitalize()}\n"
        f"{winner.first_name} won the toss! Choose to bat or bowl first:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await query.answer()

async def choose_bat_bowl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data.split("_")[1]
    chat_id = query.message.chat.id
    match = matches[chat_id]

    match["batting_first"] = match["toss_winner"] if choice == "bat" else next(p for p in match["players"] if p != match["toss_winner"])
    match["scores"] = {str(p.id): 0 for p in match["players"]}
    match["innings"] = 1
    match["turn"] = 1
    match["state"] = "playing"

    await send_turn_message(chat_id, context)

async def send_turn_message(chat_id, context):
    match = matches[chat_id]
    batting = match["batting_first"] if match["innings"] == 1 else next(p for p in match["players"] if p != match["batting_first"])
    bowling = next(p for p in match["players"] if p != batting)

    keyboard = [[InlineKeyboardButton(str(i), callback_data=f"play_{i}") for i in range(1, 4)],
                [InlineKeyboardButton(str(i), callback_data=f"play_{i}") for i in range(4, 7)]]

    message = f"**Innings {match['innings']}**\n" \
              f"{batting.first_name}'s turn to bat.\nChoose a number between 1-6:"
    await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def play_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    match = matches[chat_id]
    batting = match["batting_first"] if match["innings"] == 1 else next(p for p in match["players"] if p != match["batting_first"])
    bowling = next(p for p in match["players"] if p != batting)

    if user.id != batting.id:
        await query.answer("Not your turn!")
        return

    bat_choice = int(query.data.split("_")[1])
    bowl_choice = random.randint(1, 6)

    if bat_choice == bowl_choice:
        result = f"{batting.first_name} is OUT!\nThey scored {match['scores'][str(batting.id)]} runs."
        if match["innings"] == 1:
            match["innings"] = 2
            await query.edit_message_text(result + "\n\nNext innings starting...")
            await send_turn_message(chat_id, context)
        else:
            await end_match(chat_id, context)
    else:
        match["scores"][str(batting.id)] += bat_choice
        total = match["scores"][str(batting.id)]
        result = f"{batting.first_name} chose {bat_choice}, {bowling.first_name} chose {bowl_choice}\n" \
                 f"Total: {total}"
        await query.edit_message_text(result)
        await send_turn_message(chat_id, context)
    await query.answer()

async def end_match(chat_id, context):
    match = matches[chat_id]
    p1, p2 = match["players"]
    s1 = match["scores"][str(p1.id)]
    s2 = match["scores"][str(p2.id)]

    if match["batting_first"].id == p1.id:
        first, second = p1, p2
        first_score, second_score = s1, s2
    else:
        first, second = p2, p1
        first_score, second_score = s2, s1

    if first_score > second_score:
        winner, loser = first, second
    elif second_score > first_score:
        winner, loser = second, first
    else:
        winner = loser = None  # Tie

    data = load_data()
    if winner and loser:
        data[str(winner.id)]["balance"] += 1000
        data[str(winner.id)]["wins"] += 1
        data[str(loser.id)]["losses"] += 1
        message = f"**{winner.first_name} wins the match!**\n" \
                  f"{first.first_name}: {first_score}\n{second.first_name}: {second_score}\nWinner gets 1000 CCG."
    else:
        message = f"The match is a tie!\n" \
                  f"{first.first_name}: {first_score}\n{second.first_name}: {second_score}"

    save_data(data)
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    del matches[chat_id]

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("start_pvp", start_pvp))

    app.add_handler(CallbackQueryHandler(join_match, pattern="join_match"))
    app.add_handler(CallbackQueryHandler(handle_toss, pattern="toss_"))
    app.add_handler(CallbackQueryHandler(choose_bat_bowl, pattern="choose_"))
    app.add_handler(CallbackQueryHandler(play_turn, pattern="play_"))

    app.run_polling()

if __name__ == "__main__":
    main()
