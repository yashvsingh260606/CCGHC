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
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Start PvP Match", callback_data="start_pvp")]
    ]
    await update.message.reply_text(
        f"Hello {user.first_name}! Welcome to Hand Cricket PvP Bot.\n"
        "Press the button below to start a Player vs Player match.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    match_id = str(query.message.chat.id)
    matches[match_id] = {
        "players": [user],
        "state": "waiting",
        "message_id": None,
    }
    keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]]
    sent = await query.message.reply_text(
        f"{user.first_name} started a match. Waiting for opponent...",
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
    match["bowler_score"] = 0
    match["balls_played"] = 0
    match["innings"] = 1
    match["target"] = None

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
    match = matches[match_id]
    user = query.from_user

    if match["state"] != "playing":
        return await query.answer("Game not in playing state.", show_alert=True)

    # Batsman chooses
    if user == match["batsman"]:
        batsman_num = num
        bowler_num = random.randint(1, 6)
        if batsman_num == bowler_num:
            # Wicket
            text = (
                f"{match['batsman'].first_name} chose {batsman_num}.\n"
                f"Bowler chose {bowler_num}.\n"
                f"{match['batsman'].first_name} got OUT!\n"
                f"Runs scored: {match['batsman_score']}\n"
                f"Balls played: {match['balls_played'] + 1}\n"
            )
            if match["innings"] == 1:
                match["target"] = match["batsman_score"] + 1
                match["innings"] = 2
                # Swap roles
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                match["batsman_score"] = 0
                match["balls_played"] = 0
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
            match["batsman_score"] += batsman_num
            match["balls_played"] += 1
            keyboard = [
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
            ]
            text = (
                f"{match['batsman'].first_name} chose {batsman_num}. Now {match['bowler'].first_name} can choose.\n"
                f"Bowler, select your number (1-6):"
            )
            # Save the bowler's turn state
            match["awaiting_bowler"] = True
            match["last_batsman_num"] = batsman_num
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    # Bowler chooses
    elif user == match["bowler"] and match.get("awaiting_bowler"):
        bowler_num = num
        batsman_num = match.get("last_batsman_num")

        if bowler_num == batsman_num:
            # Wicket
            text = (
                f"Bowler chose {bowler_num}.\n"
                f"{match['batsman'].first_name} got OUT!\n"
                f"Runs scored: {match['batsman_score']}\n"
                f"Balls played: {match['balls_played']}\n"
            )
            if match["innings"] == 1:
                match["target"] = match["batsman_score"] + 1
                match["innings"] = 2
                # Swap roles
                match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                match["batsman_score"] = 0
                match["balls_played"] = 0
                keyboard = [
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
                ]
                text += (
                    f"\nInnings 2 started.\n"
                    f"{match['batsman'].first_name} needs {match['target']} runs to win.\n"
                    f"{match['batsman'].first_name}, play your shot (1-6):"
                )
                match.pop("awaiting_bowler", None)
                match.pop("last_batsman_num", None)
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
            match["bowler_score"] += bowler_num
            match.pop("awaiting_bowler", None)
            match.pop("last_batsman_num", None)

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
            text = (
                f"Bowler chose {bowler_num}.\n"
                f"{match['batsman'].first_name}, play your shot (1-6):"
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    else:
        return await query.answer("Wait for your turn!", show_alert=True)

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
