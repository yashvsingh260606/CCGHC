import random
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

matches = {}
users = {}
admins = {7361215114}  # Put your Telegram user ID(s) here as admin(s)

# Helper function to get current UTC date string
def current_date():
    return datetime.utcnow().date().isoformat()

# Register command: register user and give 4000 coins once
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
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
    await update.message.reply_text(
        f"Welcome {user.first_name}! You have been awarded 4000 CCG coins."
    )

# Daily command: Give 3000 coins once per day
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
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
    await update.message.reply_text(
        "You received 3000 CCG coins as daily bonus!"
    )

# Profile command: show user profile nicely formatted
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
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
        target_id = int(args[0])
        amount = int(args[1])
        if target_id not in users:
            await update.message.reply_text("Target user not found.")
            return
        users[target_id]["balance"] += amount
        await update.message.reply_text(
            f"Added {amount} CCG coins to user {target_id}."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# Utility: create shot buttons in two rows (1-3, 4-6)
def shot_buttons():
    row1 = [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1,4)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4,7)]
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

# Choose bat or bowl callback
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

    keyboard = shot_buttons()

    await query.edit_message_text(
        f"Game started!\n\n"
        f"🏏 Batter: {match['batsman'].first_name}\n"
        f"⚾ Bowler: {match['bowler'].first_name}\n\n"
        f"{match['batsman'].first_name}, play your shot (1-6):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await query.answer()
# Handle shot selection during play
async def shot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "playing":
        await query.answer("No active game right now.")
        return

    user = query.from_user
    data = query.data

    # Validate shot selection
    if not data.startswith("shot_"):
        await query.answer()
        return

    number = int(data.split("_")[1])

    # Whose turn?
    if match["waiting_for"] == "batsman":
        if user.id != match["batsman"].id:
            await query.answer("Wait for your turn to bat!")
            return
        match["batsman_choice"] = number
        match["waiting_for"] = "bowler"

        await query.edit_message_text(
            f"{match['batsman'].first_name} chose their shot.\n"
            f"Now, {match['bowler'].first_name} can choose the ball."
        )
        await query.answer()

    elif match["waiting_for"] == "bowler":
        if user.id != match["bowler"].id:
            await query.answer("Wait for your turn to bowl!")
            return
        match["bowler_choice"] = number

        # Reveal choices and update score
        b_choice = match["batsman_choice"]
        bow_choice = match["bowler_choice"]

        text = (
            f"Over : {match['balls']//6}.{match['balls']%6 + 1}\n\n"
            f"🏏 Batter : {match['batsman'].first_name}\n"
            f"⚾ Bowler : {match['bowler'].first_name}\n\n"
            f"{match['batsman'].first_name} chose {b_choice}\n"
            f"{match['bowler'].first_name} chose {bow_choice}\n\n"
        )

        if b_choice == bow_choice:
            text += (
                f"💥 {match['batsman'].first_name} is OUT!\n\n"
            )
            # End innings or match logic
            if match["innings"] == 1:
                match["innings"] = 2
                match["target"] = match["score"] + 1
                match["score"] = 0
                match["balls"] = 0
                # Swap batsman and bowler for second innings
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                match["waiting_for"] = "batsman"

                text += (
                    f"Target for {match['batsman'].first_name} is {match['target']} runs.\n\n"
                    f"🏏 Batter: {match['batsman'].first_name}\n"
                    f"⚾ Bowler: {match['bowler'].first_name}\n\n"
                    f"{match['batsman'].first_name}, play your shot:"
                )
                keyboard = shot_buttons()
                await query.edit_message_text(
                    text, reply_markup=InlineKeyboardMarkup(keyboard)
                )
                await query.answer()
                return
            else:
                # Match finished, bowler wins
                match["state"] = "finished"
                match["players"][1 if match["batsman"] == match["players"][0] else 0]["wins"] += 1
                match["players"][0 if match["batsman"] == match["players"][0] else 1]["losses"] += 1

                text += (
                    f"🏆 {match['bowler'].first_name} wins the match!\n\n"
                    f"Use /start_pvp to play again."
                )
                await query.edit_message_text(text)
                matches.pop(chat_id)
                await query.answer()
                return
        else:
            match["score"] += b_choice
            match["balls"] += 1

            # Check chase condition in second innings
            if match["innings"] == 2 and match["score"] >= match["target"]:
                match["state"] = "finished"
                match["players"][0 if match["batsman"] == match["players"][0] else 1]["wins"] += 1
                match["players"][1 if match["batsman"] == match["players"][0] else 0]["losses"] += 1

                text += (
                    f"{match['batsman'].first_name} scored {match['score']} runs.\n"
                    f"🏆 {match['batsman'].first_name} wins the match!\n\n"
                    f"Use /start_pvp to play again."
                )
                await query.edit_message_text(text)
                matches.pop(chat_id)
                await query.answer()
                return

            text += (
                f"{match['batsman'].first_name} scored {b_choice} runs.\n"
                f"Total Score: {match['score']}\n\n"
                f"{match['batsman'].first_name}, play your next shot!"
            )
            match["waiting_for"] = "batsman"
            keyboard = shot_buttons()
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            await query.answer()

# Leaderboard command based on coin balance
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not users:
        await update.message.reply_text("No users registered yet.")
        return
    sorted_users = sorted(users.items(), key=lambda x: x[1]["balance"], reverse=True)
    text = "**🏅 Leaderboard - Top Coin Holders 🏅**\n\n"
    for i, (uid, data) in enumerate(sorted_users[:10], 1):
        text += f"{i}. {data['name']} - {data['balance']} CCG coins\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# Command handlers registration
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))

    app.add_handler(CallbackQueryHandler(join_match, pattern="join_match"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="toss_"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="choose_"))
    app.add_handler(CallbackQueryHandler(shot_handler, pattern="shot_"))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
