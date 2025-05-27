from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
import random
import os

TOKEN = os.getenv("TOKEN")
matches = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Start PvP Match", callback_data="start_pvp")]]
    await update.message.reply_text(
        "Welcome to CCG HandCricket Bot",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Welcome message\n"
        "/start_pvp - Start a Player vs Player match\n"
        "/help - Show this help message"
    )

async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle both command and callback query
    if update.message:
        user = update.message.from_user
        chat_id = update.message.chat.id
        send_func = update.message.reply_text
    else:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        chat_id = query.message.chat.id
        send_func = query.message.edit_text

    match_id = str(chat_id)
    if match_id in matches:
        await send_func("A match is already running in this chat.")
        return

    matches[match_id] = {
        "players": [user],
        "state": "waiting_for_opponent",
        "message_id": None,
    }
    keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]]
    sent = await context.bot.send_message(
        chat_id,
        f"{user.first_name} started a match. Waiting for opponent to join...",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    matches[match_id]["message_id"] = sent.message_id

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = str(query.message.chat.id)
    match = matches.get(match_id)

    if not match or len(match["players"]) >= 2:
        return await query.edit_message_text("Match full or not found.")

    user = query.from_user
    if user in match["players"]:
        return await query.answer("You already joined this match.", show_alert=True)

    match["players"].append(user)
    match["state"] = "toss"
    keyboard = [
        [
            InlineKeyboardButton("Heads", callback_data="toss_heads"),
            InlineKeyboardButton("Tails", callback_data="toss_tails"),
        ]
    ]
    await query.edit_message_text(
        f"{user.first_name} joined the match.\n\nChoose Heads or Tails for the toss:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]
    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if match.get("toss_choice"):
        return await query.answer("Toss already chosen.", show_alert=True)

    match["toss_choice"] = choice
    toss_result = random.choice(["heads", "tails"])
    match["toss_result"] = toss_result

    if choice == toss_result:
        match["toss_winner"] = user
    else:
        other_player = next(p for p in match["players"] if p != user)
        match["toss_winner"] = other_player

    keyboard = [
        [
            InlineKeyboardButton("Bat", callback_data="bat"),
            InlineKeyboardButton("Bowl", callback_data="bowl"),
        ]
    ]

    await query.edit_message_text(
        f"Toss result: {toss_result.capitalize()}\n"
        f"{match['toss_winner'].first_name} won the toss.\n\n"
        f"{match['toss_winner'].first_name}, choose to Bat or Bowl:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data  # 'bat' or 'bowl'
    match_id = str(query.message.chat.id)
    match = matches[match_id]

    if match.get("play_choice"):
        return await query.answer("Play choice already made.", show_alert=True)

    match["play_choice"] = choice
    p1, p2 = match["players"]
    toss_winner = match["toss_winner"]
    opponent = p2 if toss_winner == p1 else p1

    if choice == "bat":
        match["batsman"] = toss_winner
        match["bowler"] = opponent
    else:
        match["bowler"] = toss_winner
        match["batsman"] = opponent

    match["state"] = "playing"
    match["batsman_score"] = 0
    match["balls_played"] = 0
    match["innings"] = 1
    match["target"] = None
    match["waiting_for"] = "batsman"

    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
    ]

    await query.edit_message_text(
        f"Game started!\n\n"
        f"Batsman: {match['batsman'].first_name}\n"
        f"Bowler: {match['bowler'].first_name}\n\n"
        f"{match['batsman'].first_name}, play your shot (1-6):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def play_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if match["state"] != "playing":
        return await query.answer("Game not in playing state.", show_alert=True)

    # We expect alternation: batsman chooses, then bowler chooses
    if match["waiting_for"] == "batsman" and user != match["batsman"]:
        return await query.answer("Wait for your turn! Batsman is playing.", show_alert=True)
    if match["waiting_for"] == "bowler" and user != match["bowler"]:
        return await query.answer("Wait for your turn! Bowler is playing.", show_alert=True)

    if not data.startswith("num_"):
        return

    num = int(data.split("_")[1])

    if match["waiting_for"] == "batsman":
        match["batsman_num"] = num
        match["waiting_for"] = "bowler"
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
        ]
        await query.edit_message_text(
            f"{match['batsman'].first_name} chose {num}. Now {match['bowler'].first_name} can choose.\n"
            f"{match['bowler'].first_name}, select your number (1-6):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        match["bowler_num"] = num
        batsman_num = match["batsman_num"]
        bowler_num = num

        if batsman_num == bowler_num:
            # Wicket
            text = (
                f"{match['batsman'].first_name} got OUT!\n"
                f"Runs scored: {match['batsman_score']}\n"
            )
            if match["innings"] == 1:
                match["target"] = match["batsman_score"] + 1
                match["innings"] = 2
                match["batsman_score"] = 0
                match["balls_played"] = 0
                match["state"] = "playing"
                # Swap roles for second innings
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                match["waiting_for"] = "batsman"
                keyboard = [
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
                ]
                text += (
                    f"\nInnings 2 started.\n"
                    f"{match['batsman'].first_name} needs {match['target']} runs to win.\n"
                    f"{match['batsman'].first_name}, play your shot (1-6):"
                )
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return
            else:
                # Match over
                if match["batsman_score"] >= match["target"]:
                    winner = match["batsman"]
                else:
                    winner = match["bowler"]
                text += f"\nMatch over! Winner: {winner.first_name}"
                await query.edit_message_text(text)
                del matches[match_id]
                return
        else:
            # Add runs
            match["batsman_score"] += batsman_num
            match["balls_played"] += 1

            if match["innings"] == 2 and match["batsman_score"] >= match["target"]:
                # Batsman won
                text = (
                    f"{match['batsman'].first_name} scored {match['batsman_score']} runs and won the match!\n"
                )
                await query.edit_message_text(text)
                del matches[match_id]
                return

            match["waiting_for"] = "batsman"
            keyboard = [
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
            ]
            await query.edit_message_text(
                f"{match['batsman'].first_name} scored {batsman_num}.\n"
                f"Now {match['batsman'].first_name}, play your shot (1-6):",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

def set_commands(app):
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("start_pvp", "Start a Player vs Player match"),
        BotCommand("help", "Show help commands"),
    ]
    app.bot.set_my_commands(commands)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CallbackQueryHandler(start_pvp, pattern="^start_pvp$"))
    app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^(bat|bowl)$"))
    app.add_handler(CallbackQueryHandler(play_turn, pattern="^num_"))

    app.run_polling(close_loop=False)
    set_commands(app)  # Set bot commands for "/" menu

if __name__ == "__main__":
    main()
