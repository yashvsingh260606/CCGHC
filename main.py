import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

matches = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the Hand Cricket PvP Bot!\nUse /start_pvp to begin a new match.")

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

async def play_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)
    if not match or match["state"] != "playing":
        await query.answer("Game not in progress.")
        return

    user = query.from_user
    data = query.data

    if not data.startswith("shot_"):
        await query.answer()
        return

    shot_value = int(data.split("_")[1])

    if match["waiting_for"] == "batsman" and user.id != match["batsman"].id:
        await query.answer("Wait for your turn to play as batsman.", show_alert=True)
        return
    if match["waiting_for"] == "bowler" and user.id != match["bowler"].id:
        await query.answer("Wait for your turn to play as bowler.", show_alert=True)
        return

    if match["waiting_for"] == "batsman":
        match["batsman_choice"] = shot_value
        match["waiting_for"] = "bowler"
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
        ]
        await query.edit_message_text(
            f"{match['batsman'].first_name} chose their shot.\n"
            f"{match['bowler'].first_name}, bowl your number (1-6):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        match["bowler_choice"] = shot_value
        b = match["batsman_choice"]
        w = match["bowler_choice"]

        if b == w:
            text = (
                f"Batsman chose: {b}\n"
                f"Bowler chose: {w}\n\n"
                f"{match['batsman'].first_name} is OUT!\n"
                f"Total Score: {match['score']}"
            )
            if match["innings"] == 1:
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
                text += (
                    f"\n\nInnings 2 begins.\n"
                    f"{match['batsman'].first_name} needs {match['target']} runs to win.\n"
                    f"{match['batsman'].first_name}, play your shot (1-6):"
                )
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                if match["score"] >= match["target"]:
                    winner = match["batsman"]
                else:
                    winner = match["bowler"]
                text += f"\n\nMatch Over! Winner: {winner.first_name}"
                await query.edit_message_text(text)
                del matches[chat_id]
            await query.answer()
            return
        else:
            match["score"] += b
            match["balls"] += 1
            if match["innings"] == 2 and match["score"] >= match["target"]:
                text = (
                    f"Batsman chose: {b}\n"
                    f"Bowler chose: {w}\n\n"
                    f"{match['batsman'].first_name} scored {match['score']} runs and won the match!"
                )
                await query.edit_message_text(text)
                del matches[chat_id]
                await query.answer()
                return

            match["waiting_for"] = "batsman"
            keyboard = [
                [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(1, 4)],
                [InlineKeyboardButton(str(i), callback_data=f"shot_{i}") for i in range(4, 7)],
            ]
            await query.edit_message_text(
                f"Batsman chose: {b}\n"
                f"Bowler chose: {w}\n"
                f"Total Score: {match['score']}\n\n"
                f"{match['batsman'].first_name}, play your next shot (1-6):",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        await query.answer()

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_(heads|tails)$"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^choose_(bat|bowl)$"))
    app.add_handler(CallbackQueryHandler(play_turn, pattern="^shot_[1-6]$"))
    print("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
