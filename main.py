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

users = {}
matches = {}

def get_emoji():
    # Use normal coin emoji as fallback
    return "🪙"

def format_profile(user_id):
    user = users.get(user_id)
    if not user:
        return "No profile found. Please /register first."
    text = (
        f"*Name*       : _{user['name']}_\n"
        f"*ID*         : _{user_id}_\n"
        f"*Balance*    : _{user['balance']} {get_emoji()}_\n"
        f"*Wins*       : _{user['wins']}_\n"
        f"*Losses*     : _{user['losses']}_"
    )
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Hand Cricket PvP Bot!\n"
        "Use /register to create your profile.\n"
        "Use /start_pvp to begin a new match."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id in users:
        await update.message.reply_text("You already have a profile.")
        return
    users[user_id] = {
        "name": user.first_name,
        "balance": 4000,
        "wins": 0,
        "losses": 0,
        "last_daily": None,
    }
    await update.message.reply_text(
        f"Profile created! You received 4000 {get_emoji()}."
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in users:
        await update.message.reply_text("Please /register first.")
        return
    today = datetime.utcnow().date().isoformat()
    last_daily = users[user_id].get("last_daily")
    if last_daily == today:
        await update.message.reply_text("You have already claimed your daily reward today.")
        return
    users[user_id]["balance"] += 3000
    users[user_id]["last_daily"] = today
    await update.message.reply_text(
        f"Daily reward claimed! You received 3000 {get_emoji()}."
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = format_profile(user_id)
    await update.message.reply_text(text, parse_mode="MarkdownV2")

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
    data = query.data
    match = matches.get(chat_id)
    if not match or match["state"] != "toss":
        await query.answer("No toss ongoing.")
        return

    player1 = match["players"][0]
    player2 = match["players"][1]
    toss_winner = None
    toss_loser = None
    player1_choice = "heads" if data == "toss_heads" else "tails"
    coin_result = random.choice(["heads", "tails"])

    if player1_choice == coin_result:
        toss_winner = player1
        toss_loser = player2
    else:
        toss_winner = player2
        toss_loser = player1

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "toss_winner_decide"

    keyboard = [
        [
            InlineKeyboardButton("Bat", callback_data="choose_bat"),
            InlineKeyboardButton("Bowl", callback_data="choose_bowl"),
        ]
    ]

    await query.edit_message_text(
        f"Coin toss result: *{coin_result.capitalize()}*\n"
        f"Toss winner: *{toss_winner.first_name}*\n\n"
        f"{toss_winner.first_name}, choose to Bat or Bowl first:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    await query.answer()

async def toss_winner_decide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data
    match = matches.get(chat_id)

    if not match or match["state"] != "toss_winner_decide":
        await query.answer("Invalid state.")
        return

    choice = data
    toss_winner = match["toss_winner"]
    toss_loser = match["toss_loser"]

    if choice == "choose_bat":
        match["batting"] = toss_winner
        match["bowling"] = toss_loser
    else:
        match["batting"] = toss_loser
        match["bowling"] = toss_winner

    match["state"] = "batting_turn"
    match["over"] = 0
    match["ball_in_over"] = 0
    match["score"] = 0
    match["wickets"] = 0
    match["target"] = None
    match["balls_played"] = 0

    await query.edit_message_text(
        f"{match['batting'].first_name} will bat first.\n\n"
        f"{match['batting'].first_name}, choose your shot (0-6):",
        reply_markup=generate_batting_keyboard(),
    )
    await query.answer()

def generate_batting_keyboard():
    buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"bat_{i}") for i in range(7)]
    ]
    return InlineKeyboardMarkup(buttons)

def generate_bowling_keyboard():
    buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"bowl_{i}") for i in range(7)]
    ]
    return InlineKeyboardMarkup(buttons)

async def batting_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data
    match = matches.get(chat_id)

    if not match or match["state"] not in ["batting_turn", "bowling_turn"]:
        await query.answer("No active batting turn.")
        return

    user = query.from_user
    if user.id != match["batting"].id:
        await query.answer("Wait for your turn to bat.")
        return

    if not data.startswith("bat_"):
        await query.answer("Invalid choice.")
        return

    bat_choice = int(data.split("_")[1])
    match["bat_choice"] = bat_choice

    match["state"] = "bowling_turn"

    await query.edit_message_text(
        f"{match['bowling'].first_name}, bowl your ball (0-6):",
        reply_markup=generate_bowling_keyboard(),
    )
    await query.answer()

async def bowling_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    data = query.data
    match = matches.get(chat_id)

    if not match or match["state"] != "bowling_turn":
        await query.answer("No active bowling turn.")
        return

    user = query.from_user
    if user.id != match["bowling"].id:
        await query.answer("Wait for your turn to bowl.")
        return

    if not data.startswith("bowl_"):
        await query.answer("Invalid choice.")
        return

    bowl_choice = int(data.split("_")[1])
    bat_choice = match.get("bat_choice")
    score = match.get("score", 0)
    over = match.get("over", 0)
    ball_in_over = match.get("ball_in_over", 0)
    balls_played = match.get("balls_played", 0)
    wickets = match.get("wickets", 0)
    target = match.get("target")

    batsman_name = match["batting"].first_name
    bowler_name = match["bowling"].first_name

    if bat_choice == bowl_choice:
        # Out
        wickets += 1
        ball_in_over += 1
        balls_played += 1
        event = "OUT!"
        runs_scored = 0
    else:
        runs_scored = bat_choice
        score += runs_scored
        ball_in_over += 1
        balls_played += 1
        event = f"Scored {runs_scored} run{'s' if runs_scored != 1 else ''}"

    # Check over completion
    if ball_in_over == 6:
        over += 1
        ball_in_over = 0

    match["score"] = score
    match["over"] = over
    match["ball_in_over"] = ball_in_over
    match["balls_played"] = balls_played
    match["wickets"] = wickets

    # Compose message
    msg = (
        f"*Over :* {over}.{ball_in_over}\n\n"
        f"🏏 *Batter:* {batsman_name}\n"
        f"🎯 *Bowler:* {bowler_name}\n\n"
        f"*{batsman_name}* played *{bat_choice}*\n"
        f"*{bowler_name}* bowled *{bowl_choice}*\n\n"
        f"Total Score : *{score} / {wickets}*\n"
        f"{event}\n\n"
    )

    # Check for innings end or target reached
    if wickets >= 1 or (target is not None and score > target):
        # End innings or match
        if target is None:
            # First innings ended, set target
            match["target"] = score
            match["batting"], match["bowling"] = match["bowling"], match["batting"]
            match["state"] = "batting_turn"
            match["over"] = 0
            match["ball_in_over"] = 0
            match["score"] = 0
            match["wickets"] = 0
            match["balls_played"] = 0
            msg += (
                f"🏁 *Innings over!*\n\n"
                f"Target for {match['batting'].first_name}: *{score + 1}*\n\n"
                f"{match['batting'].first_name}, your turn to bat!\n"
                "Choose your shot (0-6):"
            )
            await query.edit_message_text(msg, reply_markup=generate_batting_keyboard(), parse_mode="Markdown")
            await query.answer()
            return
        else:
            # Match over
            match["state"] = "finished"
            winner = None
            if score > target:
                winner = match["batting"]
            elif score == target:
                winner = None  # tie
            else:
                winner = match["bowling"]

            if winner:
                users[winner.id]["wins"] += 1
                loser = match["batting"] if winner == match["bowling"] else match["bowling"]
                users[loser.id]["losses"] += 1
                msg += f"🏆 *{winner.first_name} wins the match!*"
            else:
                msg += "🤝 *Match tied!*"

            await query.edit_message_text(msg, parse_mode="Markdown")
            # Remove match after finishing
            matches.pop(chat_id, None)
            await query.answer()
            return

    # Continue batting turn
    match["state"] = "batting_turn"
    msg += f"➡️ *Next Move:*\n\n_{match['batting'].first_name}, choose your next shot (0-6):_"

    await query.edit_message_text(msg, reply_markup=generate_batting_keyboard(), parse_mode="Markdown")
    await query.answer()

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("start_pvp", start_pvp))

    app.add_handler(CallbackQueryHandler(join_match, pattern="join_match"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="toss_.*"))
    app.add_handler(CallbackQueryHandler(toss_winner_decide, pattern="choose_.*"))
    app.add_handler(CallbackQueryHandler(batting_turn, pattern="bat_.*"))
    app.add_handler(CallbackQueryHandler(bowling_turn, pattern="bowl_.*"))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
