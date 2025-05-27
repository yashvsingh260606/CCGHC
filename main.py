import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

matches = {}
users = {}

# Helper emoji
COIN_EMOJI = "🪙"  # Use coin emoji or replace if unsupported

def get_today():
    return datetime.utcnow().date().isoformat()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Hand Cricket PvP Bot!\n"
        "Use /register to create your profile and get 4000 CCG.\n"
        "Use /daily to claim daily 3000 CCG.\n"
        "Use /start_pvp to start a match.\n"
        "Use /profile to view your stats."
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
        "last_daily": None,
    }
    await update.message.reply_text(
        f"Registered successfully! You received 4000 {COIN_EMOJI}."
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in users:
        await update.message.reply_text("Please /register first.")
        return
    today = get_today()
    last_daily = users[user.id]["last_daily"]
    if last_daily == today:
        await update.message.reply_text("You have already claimed your daily reward today.")
        return
    users[user.id]["balance"] += 3000
    users[user.id]["last_daily"] = today
    await update.message.reply_text(
        f"Daily claimed! You got 3000 {COIN_EMOJI}."
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in users:
        await update.message.reply_text("Please /register first.")
        return
    u = users[user.id]
    text = (
        f"*Name*    : {u['name']}\n"
        f"*ID*      : {u['id']}\n"
        f"*Balance* : {u['balance']} {COIN_EMOJI}\n"
        f"*Wins*    : {u['wins']}\n"
        f"*Losses*  : {u['losses']}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# -------- PvP Game Commands --------

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

async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)
    if not match or match["state"] != "choose_play":
        await query.answer("Not the right time to choose play.")
        return

    user = query.from_user
    if user.id != match["toss_winner"].id:
        await query.answer("Only toss winner can choose to bat or bowl.")
        return

    choice = query.data.split("_")[1]

    if choice == "bat":
        match["batsman"] = match["toss_winner"]
        match["bowler"] = match["toss_loser"]
    else:
        match["bowler"] = match["toss_winner"]
        match["batsman"] = match["toss_loser"]

    match["state"] = "playing"
    match["innings"] = 1
    match["score"] = 0
    match["balls"] = 0
    match["waiting_for"] = "batsman"
    match["target"] = None

    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
    ]

    await query.edit_message_text(
        f"Game started!\n\n"
        f"Batsman: {match['batsman'].first_name}\n"
        f"Bowler: {match['bowler'].first_name}\n\n"
        f"{match['batsman'].first_name}, play your shot (1-6):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await query.answer()
async def play_shot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)
    if not match or match["state"] != "playing":
        await query.answer("No game in progress.")
        return

    user = query.from_user
    if match["waiting_for"] != "batsman" or user.id != match["batsman"].id:
        await query.answer("Wait for your turn to bat.")
        return

    batsman_choice = int(query.data.split("_")[1])

    # Now ask bowler for their choice
    match["last_batsman_choice"] = batsman_choice
    match["waiting_for"] = "bowler"

    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"bowl_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"bowl_{i}") for i in range(4, 7)],
    ]

    await query.edit_message_text(
        f"{match['bowler'].first_name}, choose your bowl (1-6):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await query.answer()

async def bowl_shot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)
    if not match or match["state"] != "playing":
        await query.answer("No game in progress.")
        return

    user = query.from_user
    if match["waiting_for"] != "bowler" or user.id != match["bowler"].id:
        await query.answer("Wait for your turn to bowl.")
        return

    bowler_choice = int(query.data.split("_")[1])
    batsman_choice = match["last_batsman_choice"]

    # Update balls and score logic
    match["balls"] += 1

    if batsman_choice == bowler_choice:
        # Out!
        if match["innings"] == 1:
            # First innings over, switch innings
            match["target"] = match["score"] + 1
            match["innings"] = 2
            match["score"] = 0
            match["balls"] = 0
            match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
            match["waiting_for"] = "batsman"
            keyboard = [
                [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
                [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
            ]
            text = (
                f"Out! {match['bowler'].first_name} took the wicket.\n"
                f"Innings 2 started!\n\n"
                f"Target: {match['target']} runs\n"
                f"Batsman: {match['batsman'].first_name}\n"
                f"Bowler: {match['bowler'].first_name}\n\n"
                f"{match['batsman'].first_name}, play your shot (1-6):"
            )
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            await query.answer()
            return
        else:
            # Match over, second innings ended with wicket
            # Check if target reached or lost
            if match["score"] >= match["target"]:
                winner = match["batsman"]
            else:
                winner = match["bowler"]
            await end_match(chat_id, winner, query)
            return
    else:
        # Runs scored
        match["score"] += batsman_choice

        if match["innings"] == 2 and match["score"] >= match["target"]:
            # Chase won
            winner = match["batsman"]
            await end_match(chat_id, winner, query)
            return

        # Continue playing
        match["waiting_for"] = "batsman"
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
        ]

        text = (
            f"Batsman chose: {batsman_choice}\n"
            f"Bowler chose: {bowler_choice}\n"
            f"Runs scored this ball: {batsman_choice if batsman_choice != bowler_choice else 0}\n"
            f"Total score: {match['score']}\n"
            f"Balls played: {match['balls']}\n\n"
            f"{match['batsman'].first_name}, play your next shot (1-6):"
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await query.answer()

async def end_match(chat_id, winner, query):
    match = matches.get(chat_id)
    loser = None
    if winner == match["players"][0]:
        loser = match["players"][1]
    else:
        loser = match["players"][0]

    # Update user stats
    if winner.id in users:
        users[winner.id]["wins"] += 1
        users[winner.id]["balance"] += 5000  # Reward for winning
    if loser.id in users:
        users[loser.id]["losses"] += 1

    text = (
        f"Match over!\n\n"
        f"Winner: {winner.first_name}\n"
        f"Loser: {loser.first_name}\n"
        f"Final Score: {match['score']}\n"
        f"{winner.first_name} wins 5000 {COIN_EMOJI}!"
    )
    await query.edit_message_text(text)
    matches.pop(chat_id, None)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^choose_"))
    app.add_handler(CallbackQueryHandler(play_shot, pattern="^shot_"))
    app.add_handler(CallbackQueryHandler(bowl_shot, pattern="^bowl_"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
