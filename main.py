from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    await update.message.reply_text(
        "Welcome to CCG HandCricket Bot"
    )

async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    match_id = str(query.message.chat.id)

    if match_id in matches:
        # If a match already exists, prevent starting another
        await query.answer("A match is already running in this chat.", show_alert=True)
        return

    matches[match_id] = {
        "players": [user],
        "state": "waiting_for_opponent",
        "message_id": None,
    }

    keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]]
    sent = await query.message.reply_text(
        f"{user.first_name} started a match. Waiting for opponent to join...",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    matches[match_id]["message_id"] = sent.message_id

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = str(query.message.chat.id)
    match = matches.get(match_id)

    if not match:
        await query.answer("No match found. Start a new one first.", show_alert=True)
        return

    if len(match["players"]) >= 2:
        await query.answer("Match already has two players.", show_alert=True)
        return

    user = query.from_user
    if user in match["players"]:
        await query.answer("You already joined this match.", show_alert=True)
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
        f"{user.first_name} joined the match.\n\n"
        "Choose Heads or Tails for the toss:",
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
        await query.answer("Toss already chosen.", show_alert=True)
        return

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
        await query.answer("Play choice already made.", show_alert=True)
        return

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
    match.pop("awaiting_bowler", None)
    match.pop("last_batsman_num", None)

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
    num = int(query.data.split("_")[1])
    match_id = str(query.message.chat.id)
    match = matches.get(match_id)
    user = query.from_user

    if not match or match["state"] != "playing":
        await query.answer("No active game right now.", show_alert=True)
        return

    # Batsman turn to choose number
    if user == match["batsman"] and not match.get("awaiting_bowler"):
        batsman_num = num
        # Save batsman choice and ask bowler to choose
        match["last_batsman_num"] = batsman_num
        match["awaiting_bowler"] = True

        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
        ]
        await query.edit_message_text(
            f"{match['bowler'].first_name}, now choose your number (1-6):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Bowler turn to choose number
    if user == match["bowler"] and match.get("awaiting_bowler"):
        bowler_num = num
        batsman_num = match["last_batsman_num"]

        if bowler_num == batsman_num:
            # OUT
            text = (
                f"Bowler chose {bowler_num}.\n"
                f"{match['batsman'].first_name} is OUT!\n"
                f"Runs scored: {match['batsman_score']}\n"
                f"Balls played: {match['balls_played'] + 1}\n"
            )
            if match["innings"] == 1:
                match["target"] = match["batsman_score"] + 1
                match["innings"] = 2
                # Swap batsman and bowler
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                match["batsman_score"] = 0
                match["balls_played"] = 0
                match.pop("awaiting_bowler", None)
                match.pop("last_batsman_num", None)

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
                # Match over, decide winner
                if match["batsman_score"] >= match["target"]:
                    winner = match["batsman"]
                else:
                    winner = match["bowler"]
                text += f"\nMatch over! Winner: {winner.first_name}"
                await query.edit_message_text(text)
                del matches[match_id]
                return
        else:
            match["batsman_score"] += batsman_num
            match["balls_played"] += 1
            match.pop("awaiting_bowler", None)
            match.pop("last_batsman_num", None)

            # Check if chasing and reached target
            if match["innings"] == 2 and match["batsman_score"] >= match["target"]:
                text = (
                    f"{match['batsman'].first_name} scored {match['batsman_score']} runs and won the match!\n"
                )
                await query.edit_message_text(text)
                del matches[match_id]
                return

            keyboard = [
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
            ]
            await query.edit_message_text(
                f"{match['batsman'].first_name}, play your shot (1-6):",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

    # If user presses out of turn
    await query.answer("Wait for your turn!", show_alert=True)


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_pvp, pattern="^start_pvp$"))
    app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^(bat|bowl)$"))
    app.add_handler(CallbackQueryHandler(play_turn, pattern="^num_"))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
