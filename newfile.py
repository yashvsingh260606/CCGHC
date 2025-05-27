import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import random

logging.basicConfig(level=logging.INFO)

# Store ongoing matches by chat_id (match_id)
matches = {}

# Helper to create number buttons 1-6
def number_buttons():
    return [[InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1,7)]]

async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    match_id = str(update.effective_chat.id)

    if match_id in matches:
        await update.message.reply_text("A match is already ongoing here.")
        return

    matches[match_id] = {
        "players": [user],
        "state": "waiting",  # waiting for opponent
        "message_id": None,
    }

    keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]]
    sent = await update.message.reply_text(
        f"{user.first_name} started a match. Waiting for opponent...",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    matches[match_id]["message_id"] = sent.message_id

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    match_id = str(query.message.chat.id)
    match = matches.get(match_id)

    if not match or len(match["players"]) >= 2:
        await query.edit_message_text("Match full or not found.")
        return

    user = query.from_user
    if user in match["players"]:
        await query.answer("You already joined!")
        return

    match["players"].append(user)
    match["state"] = "toss"

    keyboard = [
        [InlineKeyboardButton("Heads", callback_data="toss_heads"),
         InlineKeyboardButton("Tails", callback_data="toss_tails")]
    ]

    await query.edit_message_text(
        f"{match['players'][0].first_name} and {match['players'][1].first_name} joined.\n"
        "Toss time! Choose Heads or Tails (first to click gets priority).",
        reply_markup=InlineKeyboardMarkup(keyboard)
    ) 
async def toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data.split("_")[1]  # heads or tails
    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if "toss_choices" not in match:
        match["toss_choices"] = {}

    if user.id in match["toss_choices"]:
        await query.answer("You already chose.")
        return

    match["toss_choices"][user.id] = choice

    # Wait until both players choose
    if len(match["toss_choices"]) < 2:
        await query.edit_message_text(
            f"{user.first_name} chose {choice}. Waiting for opponent to choose."
        )
        return

    # Toss result (random)
    toss_result = random.choice(["heads", "tails"])
    match["toss_result"] = toss_result

    p1, p2 = match["players"]
    p1_choice = match["toss_choices"].get(p1.id)
    p2_choice = match["toss_choices"].get(p2.id)

    if p1_choice == toss_result:
        toss_winner = p1
    else:
        toss_winner = p2

    match["toss_winner"] = toss_winner
    match["state"] = "choose_play"

    keyboard = [
        [InlineKeyboardButton("Bat", callback_data="bat"),
         InlineKeyboardButton("Bowl", callback_data="bowl")]
    ]

    await query.edit_message_text(
        f"Toss result: {toss_result.capitalize()}\n"
        f"{toss_winner.first_name} won the toss and will choose to bat or bowl.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data  # bat or bowl
    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if user != match["toss_winner"]:
        await query.answer("You are not the toss winner.")
        return

    if choice == "bat":
        match["batsman"] = user
        match["bowler"] = [p for p in match["players"] if p != user][0]
    else:
        match["bowler"] = user
        match["batsman"] = [p for p in match["players"] if p != user][0]

    match["state"] = "play_turn"
    match["batsman_score"] = 0
    match["balls"] = 0
    match["super_ball"] = False

    await query.edit_message_text(
        f"{user.first_name} chose to {choice} first.\n"
        f"{match['batsman'].first_name} is batting.\n"
        f"{match['bowler'].first_name} is bowling.\n\n"
        f"{match['batsman'].first_name} to play first.\n"
        f"Choose your number:",
        reply_markup=InlineKeyboardMarkup(number_buttons())
    )

async def play_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if match["state"] != "play_turn":
        await query.answer("Game not in play state.")
        return

    num = int(query.data.split("_")[1])
    batsman = match["batsman"]
    bowler = match["bowler"]

    if user not in [batsman, bowler]:
        await query.answer("You are not playing now.")
        return

    # Track choices temporarily
    if "choices" not in match:
        match["choices"] = {}

    match["choices"][user.id] = num

    # Wait for both batsman and bowler choices
    if len(match["choices"]) < 2:
        await query.edit_message_text(
            f"{user.first_name} chose {num}. Waiting for opponent..."
        )
        return

    batsman_num = match["choices"][batsman.id]
    bowler_num = match["choices"][bowler.id]

    # Clear choices for next ball
    match["choices"] = {}

    text = f"{batsman.first_name} chose {batsman_num}. {bowler.first_name} chose {bowler_num}.\n"

    if batsman_num == bowler_num:
        # OUT
        text += f"OUT! {batsman.first_name} is out.\n"
        if not match.get("super_ball"):
            # Start super ball
            match["super_ball"] = True
            match["state"] = "super_ball"
            match["super_runs"] = 0
            # Swap roles for super ball
            match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
            text += (f"Super Ball! {match['batsman'].first_name} will bat now.\n"
                     f"Choose your number:")
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(number_buttons()))
            return
        else:
            # Super ball out, game over
            text += f"Super Ball OUT! Game over."
            match["state"] = "finished"
            matches.pop(match_id, None)
            await query.edit_message_text(text)
            return
    else:
        if not match.get("super_ball"):
            # Normal run
            match["batsman_score"] += batsman_num
            match["balls"] += 1
            text += (f"{batsman.first_name} scored {batsman_num} runs.\n"
                     f"Total score: {match['batsman_score']} runs in {match['balls']} balls.\n"
                     f"{batsman.first_name} choose your next number:")
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(number_buttons()))
            return
        else:
            # Super ball scoring, bowler needs to beat this to win
            match["super_runs"] = batsman_num
            text += f"{batsman.first_name} scored {batsman_num} runs in Super Ball.\n"

            # Swap roles again for super ball response
            match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
            match["state"] = "super_ball_response"
            text += f"{match['batsman'].first_name} needs {batsman_num + 1} runs to win.\nChoose your number:"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(number_buttons()))
            return

async def super_ball_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if match["state"] != "super_ball_response":
        await query.answer("Not in super
