from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler
)
import random
import json
import os

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

registered_users = {}  # key: user_id, value: {'name': str, 'coins': int}
matches = {}  # key: chat_id, value: match dict

data_file = "registered_users.json"

def load_data():
    global registered_users
    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            registered_users = json.load(f)

def save_data():
    with open(data_file, "w") as f:
        json.dump(registered_users, f)

def shot_buttons():
    buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)]
    ]
    return buttons

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id not in registered_users:
        registered_users[user_id] = {"name": user.first_name, "coins": 1000}
        save_data()
        await update.message.reply_text(f"Welcome {user.first_name}! You've been registered.")
    else:
        await update.message.reply_text("You're already registered!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if user_id in registered_users:
        data = registered_users[user_id]
        await update.message.reply_text(
            f"**Profile**\nName: {data['name']}\nCoins: ₹{data['coins']}"
        )
    else:
        await update.message.reply_text("Please use /start to register first.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(
        registered_users.items(),
        key=lambda x: x[1]["coins"],
        reverse=True
    )[:10]
    text = "**Leaderboard (Top 10)**\n"
    for i, (uid, info) in enumerate(sorted_users, 1):
        text += f"{i}. {info['name']} — ₹{info['coins']}\n"
    await update.message.reply_text(text)

async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /match <opponent_id>")
        return

    opponent_id = int(context.args[0])
    if opponent_id == user.id:
        await update.message.reply_text("You can't play with yourself!")
        return

    opponent = await context.bot.get_chat(opponent_id)
    if not opponent:
        await update.message.reply_text("User not found.")
        return

    matches[chat_id] = {
        "players": [user, opponent],
        "state": "waiting_toss",
        "waiting": {},
        "chat_id": chat_id,
        "scores": {},
    }

    buttons = [
        [
            InlineKeyboardButton("Heads", callback_data="toss_heads"),
            InlineKeyboardButton("Tails", callback_data="toss_tails")
        ]
    ]
    await update.message.reply_text(
        f"{user.first_name} vs {opponent.first_name}\n\n{user.first_name}, choose Heads or Tails!",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data.split("_")[1]
    chat_id = query.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "waiting_toss":
        await query.answer("Invalid match state.")
        return

    match["state"] = "toss"
    result = random.choice(["heads", "tails"])
    user_choice = data
    user_won = (result == user_choice)

    if user_won:
        toss_winner = user
        toss_loser = match["players"][1] if match["players"][0].id == user.id else match["players"][0]
    else:
        toss_winner = match["players"][1] if match["players"][0].id == user.id else match["players"][0]
        toss_loser = user

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser

    buttons = [
        [
            InlineKeyboardButton("Bat", callback_data="choose_bat"),
            InlineKeyboardButton("Bowl", callback_data="choose_bowl")
        ]
    ]

    await query.edit_message_text(
        f"Toss result: {result.title()}!\n{toss_winner.first_name} won the toss and will choose to bat or bowl.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    choice = query.data.split("_")[1]

    for cid, m in matches.items():
        if m.get("toss_winner") and user.id == m["toss_winner"].id:
            chat_id = cid
            match = m
            break
    else:
        await query.answer("Match not found.")
        return

    if match["state"] != "toss":
        await query.answer("Invalid state.")
        return

    match["state"] = "playing"
    match["scores"] = {str(p.id): 0 for p in match["players"]}
    match["innings"] = 1
    match["turn"] = 0
    match["batting"] = match["toss_winner"] if choice == "bat" else match["toss_loser"]
    match["bowling"] = match["toss_loser"] if choice == "bat" else match["toss_winner"]
    match["waiting"] = {}

    await query.edit_message_text(
        f"**1st Innings Starts!**\n\n"
        f"{match['batting'].first_name} is Batting\n"
        f"{match['bowling'].first_name} is Bowling\n"
        f"Both players: Choose your number."
    )

    kb = InlineKeyboardMarkup(shot_buttons())
    await context.bot.send_message(match["batting"].id, "You're Batting. Choose:", reply_markup=kb)
    await context.bot.send_message(match["bowling"].id, "You're Bowling. Choose:", reply_markup=kb)
    async def handle_shot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    data = query.data

    match = matches.get(chat_id)
    if not match or match["state"] != "playing":
        await query.answer("No active match or not playing state.")
        return

    player_id = str(user.id)
    if player_id not in [str(p.id) for p in match["players"]]:
        await query.answer("You're not part of this match.")
        return

    if player_id in match["waiting"]:
        await query.answer("Already chosen. Waiting for opponent.")
        return

    if not data.startswith("shot_"):
        await query.answer()
        return

    chosen_num = int(data.split("_")[1])
    match["waiting"][player_id] = chosen_num
    await query.answer(f"You chose {chosen_num}")

    if len(match["waiting"]) < 2:
        # Waiting for other player
        await query.edit_message_text(
            f"{user.first_name} chose, waiting for opponent..."
        )
        return

    # Both players have chosen, evaluate
    batting_id = str(match["batting"].id)
    bowling_id = str(match["bowling"].id)

    bat_num = match["waiting"][batting_id]
    bowl_num = match["waiting"][bowling_id]

    score_text = f"{match['batting'].first_name} (Batting): {bat_num}\n" \
                 f"{match['bowling'].first_name} (Bowling): {bowl_num}\n"

    if bat_num == bowl_num:
        # Wicket
        match["scores"][batting_id] -= 1  # Using negative to indicate wicket count
        wicket_count = -match["scores"][batting_id]
        score_text += f"WICKET! Total wickets: {wicket_count}\n"
        # Check if innings over
        if wicket_count >= 1:
            # End innings
            await end_innings(update, context, match)
            return
    else:
        # Runs scored
        match["scores"][batting_id] += bat_num
        score_text += f"Runs scored this ball: {bat_num}\n"

    # Show score summary
    total_runs = match["scores"][batting_id]
    if total_runs < 0:
        total_runs = 0
    score_text += f"Total Runs: {total_runs}\n"

    # Clear waiting for next ball
    match["waiting"] = {}

    # Next ball message with buttons for both players
    kb = InlineKeyboardMarkup(shot_buttons())
    text = f"**Innings {match['innings']}**\n{score_text}" \
           f"{match['batting'].first_name} to Bat, {match['bowling'].first_name} to Bowl.\nChoose your number."

    # Edit the existing message with updated score and buttons
    try:
        await query.edit_message_text(text, reply_markup=kb)
    except:
        # In case edit fails (e.g. message deleted), send fresh message
        await context.bot.send_message(chat_id, text, reply_markup=kb)

async def end_innings(update: Update, context: ContextTypes.DEFAULT_TYPE, match):
    chat_id = match["chat_id"]
    batting_id = str(match["batting"].id)
    batting_runs = match["scores"][batting_id]
    if batting_runs < 0:
        batting_runs = 0

    if match["innings"] == 1:
        # Switch innings
        match["innings"] = 2
        match["batting"], match["bowling"] = match["bowling"], match["batting"]
        match["waiting"] = {}
        match["scores"][str(match["batting"].id)] = 0
        match["scores"][str(match["bowling"].id)] = 0
        match["state"] = "playing"

        text = (
            f"End of 1st innings!\n"
            f"{match['batting'].first_name} will bat now.\n"
            f"Target: {batting_runs + 1}\n\n"
            "Choose your number to start 2nd innings."
        )
        kb = InlineKeyboardMarkup(shot_buttons())
        await context.bot.send_message(chat_id, text, reply_markup=kb)

    else:
        # Match over, declare winner
        second_batting_id = str(match["batting"].id)
        second_batting_runs = match["scores"][second_batting_id]
        if second_batting_runs < 0:
            second_batting_runs = 0

        if second_batting_runs > batting_runs:
            winner = match["batting"]
        elif second_batting_runs < batting_runs:
            winner = match["bowling"]
        else:
            winner = None  # Draw

        if winner:
            result_text = f"Match over!\nWinner: {winner.first_name}\n" \
                          f"Scores:\n" \
                          f"{match['players'][0].first_name}: {match['scores'][str(match['players'][0].id)]}\n" \
                          f"{match['players'][1].first_name}: {match['scores'][str(match['players'][1].id)]}"
        else:
            result_text = "Match over! It's a draw."

        await context.bot.send_message(chat_id, result_text)
        del matches[chat_id]

def main():
    load_data()
    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers with descriptions for slash autocomplete
    app.add_handler(CommandHandler("start", start, description="Register yourself"))
    app.add_handler(CommandHandler("profile", profile, description="Show your profile"))
    app.add_handler(CommandHandler("leaderboard", leaderboard, description="Show leaderboard"))
    app.add_handler(CommandHandler("match", match, description="Start a match with opponent ID"))

    app.add_handler(CallbackQueryHandler(toss, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^choose_"))
    app.add_handler(CallbackQueryHandler(handle_shot, pattern="^shot_"))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
