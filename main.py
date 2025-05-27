import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = [7361215114]  # Replace with your Telegram user ID(s)

matches = {}
users = {}

def get_today():
    return datetime.utcnow().date().isoformat()

def get_buttons():
    # Two rows: 1-3 and 4-6
    return [
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
    ]

def format_profile(user_data):
    name = user_data.get("name", "N/A")
    uid = user_data.get("id", "N/A")
    bal = user_data.get("balance", 0)
    wins = user_data.get("wins", 0)
    losses = user_data.get("losses", 0)
    profile_text = (
        f"**Name:** {name}\n"
        f"**ID:** {uid}\n"
        f"**Balance:** {bal} 💰\n"
        f"**Wins:** {wins}\n"
        f"**Losses:** {losses}"
    )
    return profile_text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in users:
        users[user.id] = {
            "id": user.id,
            "name": user.first_name,
            "balance": 0,
            "wins": 0,
            "losses": 0,
            "last_daily": None,
            "registered": False,
        }
    await update.message.reply_text(
        "Welcome to the Hand Cricket PvP Bot!\n"
        "Use /register to register and get 4000 coins.\n"
        "Use /daily to claim daily 3000 coins.\n"
        "Use /profile to check your stats.\n"
        "Use /start_pvp to begin a new match."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = users.get(user.id)
    if not u:
        users[user.id] = {
            "id": user.id,
            "name": user.first_name,
            "balance": 0,
            "wins": 0,
            "losses": 0,
            "last_daily": None,
            "registered": False,
        }
        u = users[user.id]
    if u["registered"]:
        await update.message.reply_text("You are already registered.")
        return
    u["registered"] = True
    u["balance"] += 4000
    await update.message.reply_text("Registration successful! You got 4000 coins.")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = users.get(user.id)
    if not u or not u.get("registered"):
        await update.message.reply_text("Please register first using /register.")
        return
    today = get_today()
    if u["last_daily"] == today:
        await update.message.reply_text("You already claimed your daily coins today. Come back tomorrow!")
        return
    u["last_daily"] = today
    u["balance"] += 3000
    await update.message.reply_text("Daily claimed! You received 3000 coins.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = users.get(user.id)
    if not u:
        await update.message.reply_text("You have no profile yet. Use /register to start.")
        return
    text = format_profile(u)
    await update.message.reply_text(text, parse_mode="Markdown")

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
        f"Toss result: *{toss_result.capitalize()}*\n"
        f"{match['toss_winner'].first_name} won the toss.\n"
        f"{match['toss_winner'].first_name}, choose to *Bat* or *Bowl*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
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

    keyboard = get_buttons()

    await query.edit_message_text(
        f"*Game started!*\n\n"
        f"🏏 *Batsman:* {match['batsman'].first_name}\n"
        f"🎳 *Bowler:* {match['bowler'].first_name}\n\n"
        f"{match['batsman'].first_name}, play your shot (1-6):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    await query.answer()
async def shot_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user = query.from_user
    match = matches.get(chat_id)

    if not match or match["state"] != "playing":
        await query.answer("No game is currently active.")
        return

    waiting_for = match["waiting_for"]
    batsman = match["batsman"]
    bowler = match["bowler"]

    shot = int(query.data.split("_")[1])

    # Batsman turn
    if waiting_for == "batsman":
        if user.id != batsman.id:
            await query.answer("It's the batsman's turn!")
            return
        match["batsman_choice"] = shot
        match["waiting_for"] = "bowler"
        await query.edit_message_text(
            f"Over : {match['balls']//6}.{match['balls']%6 + 1}\n\n"
            f"🏏 Batsman: *{batsman.first_name}*\n"
            f"🎳 Bowler: *{bowler.first_name}*\n\n"
            f"*{batsman.first_name}* chose: {shot}\n\n"
            f"{bowler.first_name}, play your bowl (1-6):",
            reply_markup=InlineKeyboardMarkup(get_buttons()),
            parse_mode="Markdown",
        )
        await query.answer()
        return

    # Bowler turn
    if waiting_for == "bowler":
        if user.id != bowler.id:
            await query.answer("It's the bowler's turn!")
            return
        match["bowler_choice"] = shot
        batsman_choice = match["batsman_choice"]
        bowler_choice = match["bowler_choice"]
        match["balls"] += 1

        if batsman_choice == bowler_choice:
            # Out!
            text = (
                f"Over : {match['balls']//6}.{(match['balls']-1)%6 + 1}\n\n"
                f"🏏 Batsman: *{batsman.first_name}*\n"
                f"🎳 Bowler: *{bowler.first_name}*\n\n"
                f"*{batsman.first_name}* chose: {batsman_choice}\n"
                f"*{bowler.first_name}* bowled: {bowler_choice}\n\n"
                f"**OUT!**\n"
            )
            # Handle innings change or match end
            if match["innings"] == 1:
                # Switch innings
                match["innings"] = 2
                match["target"] = match["score"] + 1
                # Swap roles
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                match["score"] = 0
                match["balls"] = 0
                match["waiting_for"] = "batsman"
                match["batsman_choice"] = None
                match["bowler_choice"] = None

                text += (
                    f"Innings over! Target for {match['batsman'].first_name} is {match['target']} runs.\n\n"
                    f"🏏 *Now {match['batsman'].first_name} will bat.*\n"
                    f"🎳 *{match['bowler'].first_name} will bowl.*\n\n"
                    f"{match['batsman'].first_name}, play your shot (1-6):"
                )

                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(get_buttons()),
                    parse_mode="Markdown",
                )
                await query.answer()
                return
            else:
                # Match ends
                # Decide winner
                if match["score"] >= match["target"]:
                    winner = match["batsman"]
                    loser = match["bowler"]
                else:
                    winner = match["bowler"]
                    loser = match["batsman"]

                # Update stats
                users[winner.id]["wins"] += 1
                users[loser.id]["losses"] += 1
                users[winner.id]["balance"] += 1000  # winner reward

                text += (
                    f"Match Over!\n\n"
                    f"🏆 Winner: *{winner.first_name}*\n"
                    f"🎉 Awarded 1000 coins!\n\n"
                    f"Use /profile to check your stats.\n"
                    f"Start a new game with /start_pvp"
                )
                match["state"] = "ended"
                await query.edit_message_text(text, parse_mode="Markdown")
                # Remove match
                del matches[chat_id]
                await query.answer()
                return
        else:
            # Runs scored
            runs = batsman_choice
            match["score"] += runs
            match["waiting_for"] = "batsman"
            match["batsman_choice"] = None
            match["bowler_choice"] = None

            text = (
                f"Over : {match['balls']//6}.{(match['balls']-1)%6 + 1}\n\n"
                f"🏏 Batsman: *{batsman.first_name}*\n"
                f"🎳 Bowler: *{bowler.first_name}*\n\n"
                f"*{batsman.first_name}* chose: {batsman_choice}\n"
                f"*{bowler.first_name}* bowled: {bowler_choice}\n\n"
                f"🟢 Runs scored: {runs}\n"
                f"Total Score: {match['score']}\n\n"
            )

            if match["innings"] == 2 and match["score"] >= match["target"]:
                # Chasing team won
                users[batsman.id]["wins"] += 1
                users[bowler.id]["losses"] += 1
                users[batsman.id]["balance"] += 1000  # reward

                text += (
                    f"🏆 *{batsman.first_name}* has reached the target!\n"
                    f"🎉 You won!\n"
                    f"Use /profile to check your stats.\n"
                    f"Start a new game with /start_pvp"
                )
                match["state"] = "ended"
                await query.edit_message_text(text, parse_mode="Markdown")
                del matches[chat_id]
                await query.answer()
                return

            text += f"__Next Move:__\n\n" \
                    f"**{batsman.first_name}**, play your shot (1-6):"

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(get_buttons()),
                parse_mode="MarkdownV2",
            )
            await query.answer()

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("Usage: /add <user_id> <amount>")
            return
        target_id = int(args[0])
        amount = int(args[1])
    except:
        await update.message.reply_text("Invalid arguments. Use /add <user_id> <amount>")
        return
    if target_id not in users:
        await update.message.reply_text("User ID not found.")
        return
    users[target_id]["balance"] += amount
    await update.message.reply_text(f"Added {amount} coins to user {target_id}.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CommandHandler("add", add_coins))

    app.add_handler(CallbackQueryHandler(join_match, pattern="join_match"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="toss_.*"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="choose_.*"))
    app.add_handler(CallbackQueryHandler(shot_chosen, pattern="shot_.*"))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
