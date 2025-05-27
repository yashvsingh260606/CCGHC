import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
import logging

logging.basicConfig(level=logging.INFO)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = {7361215114}  # Replace with your Telegram user ID(s)

# Data storage for users and matches (use persistent DB for production)
users = {}
matches = {}

# Utility functions

def get_buttons():
    return [
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
    ]

def format_profile(user_data):
    return (
        f"*Name*      : _{user_data['name']}_\n"
        f"*ID*        : _{user_data['id']}_\n"
        f"*Balance*   : _{user_data['balance']} CCG_\n"
        f"*Wins*      : _{user_data['wins']}_\n"
        f"*Losses*    : _{user_data['losses']}_"
    )

def ensure_user(user):
    if user.id not in users:
        users[user.id] = {
            "name": user.first_name,
            "id": user.id,
            "balance": 0,
            "wins": 0,
            "losses": 0,
            "last_daily": None,
            "registered": False,
        }

# Command Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.message.reply_text(
        "Welcome to Hand Cricket PvP Bot!\n"
        "Use /register to register and get 4000 CCG coins.\n"
        "Use /daily to get 3000 CCG daily bonus.\n"
        "Use /start_pvp to start a match."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    if users[user.id]["registered"]:
        await update.message.reply_text("You have already registered.")
        return
    users[user.id]["registered"] = True
    users[user.id]["balance"] += 4000
    await update.message.reply_text("Registration successful! You got 4000 CCG coins.")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    today = datetime.utcnow().date()
    last_daily = users[user.id]["last_daily"]
    if last_daily == today:
        await update.message.reply_text("You already claimed your daily reward today.")
        return
    users[user.id]["balance"] += 3000
    users[user.id]["last_daily"] = today
    await update.message.reply_text("Daily bonus claimed! You got 3000 CCG coins.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    user_data = users[user.id]
    text = format_profile(user_data)
    await update.message.reply_text(text, parse_mode="Markdown")

# Admin command to add coins

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return
    if target_id not in users:
        await update.message.reply_text("User ID not found.")
        return
    users[target_id]["balance"] += amount
    await update.message.reply_text(
        f"Added {amount} CCG to user {users[target_id]['name']} (ID: {target_id})."
    )

# PvP Match commands and logic

async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    ensure_user(user)
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
    ensure_user(user)

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
    match["batsman_choice"] = None
    match["bowler_choice"] = None

    await query.edit_message_text(
        f"Game started!\n\n"
        f"🏏 *Batsman*: {match['batsman'].first_name}\n"
        f"🎳 *Bowler*: {match['bowler'].first_name}\n\n"
        # continuing from part 1...

        # prompt batsman to play
        f"{match['batsman'].first_name}, play your shot!",
        reply_markup=InlineKeyboardMarkup(get_buttons()),
        parse_mode="Markdown",
    )
    await query.answer()

async def shot_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user = query.from_user
    match = matches.get(chat_id)

    if not match or match["state"] != "playing":
        await query.answer("No ongoing game here.")
        return

    if match["waiting_for"] == "batsman":
        if user.id != match["batsman"].id:
            await query.answer("It's not your turn to bat.")
            return
        batsman_number = int(query.data.split("_")[1])
        match["batsman_choice"] = batsman_number
        match["waiting_for"] = "bowler"

        # Inform that batsman chose their number, now bowler can choose
        await query.edit_message_text(
            f"🏏 *Batsman* chose their number.\n"
            f"Now *{match['bowler'].first_name}* can bowl!\n\n"
            f"Over : {match['balls']//6}.{match['balls']%6}\n\n"
            f"🏏 Batter : *{match['batsman'].first_name}*\n"
            f"⚾ Bowler : *{match['bowler'].first_name}*\n\n"
            f"Next Move:\n"
            f"__{match['bowler'].first_name}, play your next bowl!__",
            reply_markup=InlineKeyboardMarkup(get_buttons()),
            parse_mode="Markdown",
        )
        await query.answer()

    elif match["waiting_for"] == "bowler":
        if user.id != match["bowler"].id:
            await query.answer("It's not your turn to bowl.")
            return
        bowler_number = int(query.data.split("_")[1])
        match["bowler_choice"] = bowler_number

        batsman = match["batsman"]
        bowler = match["bowler"]

        balls = match["balls"]
        score = match["score"]

        batsman_number = match["batsman_choice"]
        bowler_number = match["bowler_choice"]

        # Process ball
        balls += 1
        match["balls"] = balls

        # If numbers match, batsman is out
        if batsman_number == bowler_number:
            # End innings or match accordingly
            text = (
                f"Over : {balls//6}.{balls%6}\n\n"
                f"🏏 Batter : *{batsman.first_name}*\n"
                f"⚾ Bowler : *{bowler.first_name}*\n\n"
                f"{batsman.first_name} is *OUT*!\n"
                f"Final Score: *{score}* Runs\n\n"
            )
            # If first innings, switch innings
            if match["innings"] == 1:
                match["innings"] = 2
                match["target"] = score + 1
                match["score"] = 0
                match["balls"] = 0
                match["waiting_for"] = "batsman"
                # Swap batsman and bowler
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                text += (
                    f"Switching innings.\n"
                    f"Target for {match['batsman'].first_name}: {match['target']} runs.\n\n"
                    f"{match['batsman'].first_name}, play your shot!"
                )
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(get_buttons()),
                    parse_mode="Markdown",
                )
                await query.answer()
                return
            else:
                # Match ends, bowler team wins
                winner = match["bowler"]
                loser = match["batsman"]
                users[winner.id]["wins"] += 1
                users[loser.id]["losses"] += 1
                # Reward winner
                users[winner.id]["balance"] += 5000

                text += (
                    f"Match over!\n"
                    f"🏆 Winner: {winner.first_name}\n"
                    f"Better luck next time, {loser.first_name}."
                )
                await query.edit_message_text(text, parse_mode="Markdown")
                del matches[chat_id]
                await query.answer()
                return
        else:
            # Runs scored
            score += batsman_number
            match["score"] = score
            match["waiting_for"] = "batsman"
            # Check if second innings and target achieved
            if match["innings"] == 2 and score >= match["target"]:
                winner = match["batsman"]
                loser = match["bowler"]
                users[winner.id]["wins"] += 1
                users[loser.id]["losses"] += 1
                users[winner.id]["balance"] += 5000
                text = (
                    f"Over : {balls//6}.{balls%6}\n\n"
                    f"🏏 Batter : *{batsman.first_name}*\n"
                    f"⚾ Bowler : *{bowler.first_name}*\n\n"
                    f"{batsman.first_name} scored *{batsman_number}* runs.\n"
                    f"Total Score: *{score}* / {balls} balls\n\n"
                    f"🏆 {batsman.first_name} reached the target!\n"
                    f"Match over! Congratulations!"
                )
                await query.edit_message_text(text, parse_mode="Markdown")
                del matches[chat_id]
                await query.answer()
                return
            else:
                # Continue innings
                text = (
                    f"Over : {balls//6}.{balls%6}\n\n"
                    f"🏏 Batter : *{batsman.first_name}*\n"
                    f"⚾ Bowler : *{bowler.first_name}*\n\n"
                    f"{batsman.first_name} scored *{batsman_number}* runs.\n"
                    f"Total Score: *{score}* / {balls} balls\n\n"
                    f"{match['batsman'].first_name}, play your next shot!"
                )
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(get_buttons()),
                    parse_mode="Markdown",
                )
                await query.answer()
    else:
        await query.answer("Unexpected state.")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("add", add_coins))
    application.add_handler(CommandHandler("start_pvp", start_pvp))

    application.add_handler(CallbackQueryHandler(join_match, pattern="join_match"))
    application.add_handler(CallbackQueryHandler(toss_choice, pattern="toss_"))
    application.add_handler(CallbackQueryHandler(choose_play, pattern="choose_"))
    application.add_handler(CallbackQueryHandler(shot_choice, pattern="shot_"))

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
    
