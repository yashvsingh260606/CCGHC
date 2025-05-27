from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update from telegram.ext import ( ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, ) import random import os

TOKEN = os.getenv("TOKEN")  # Make sure this is set in Railway or your environment

matches = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user keyboard = [[InlineKeyboardButton("Start PvP Match", callback_data="start_pvp")]] await update.message.reply_text( f"Welcome to CCG HandCricket Bot!", reply_markup=InlineKeyboardMarkup(keyboard), )

async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user match_id = str(update.effective_chat.id) matches[match_id] = { "players": [user], "state": "waiting", "message_id": None, } keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]] sent = await update.callback_query.message.reply_text( f"{user.first_name} started a match. Waiting for opponent...", reply_markup=InlineKeyboardMarkup(keyboard), ) matches[match_id]["message_id"] = sent.message_id await update.callback_query.answer()

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() match_id = str(query.message.chat.id) match = matches.get(match_id)

if not match or len(match["players"]) >= 2:
    return await query.edit_message_text("Match full or not found.")

user = query.from_user
if user in match["players"]:
    return await query.answer("You already joined this match.", show_alert=True)

match["players"].append(user)
match["state"] = "toss"
match["toss_turn"] = match["players"][0]

keyboard = [
    [
        InlineKeyboardButton("Heads", callback_data="toss_heads"),
        InlineKeyboardButton("Tails", callback_data="toss_tails"),
    ]
]
await query.edit_message_text(
    f"{user.first_name} joined the match.\n\n"
    f"{match['toss_turn'].first_name}, choose Heads or Tails for the toss:",
    reply_markup=InlineKeyboardMarkup(keyboard),
)

async def toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() choice = query.data.split("_")[1] match_id = str(query.message.chat.id) match = matches[match_id] user = query.from_user

if user != match["toss_turn"]:
    return await query.answer("Only toss player can choose.", show_alert=True)

toss_result = random.choice(["heads", "tails"])
match["toss_result"] = toss_result

if choice == toss_result:
    match["toss_winner"] = user
else:
    match["toss_winner"] = next(p for p in match["players"] if p != user)

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

async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() choice = query.data match_id = str(query.message.chat.id) match = matches[match_id]

if match.get("play_choice"):
    return await query.answer("Choice already made.", show_alert=True)

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

keyboard = [
    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
    [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
]
await query.edit_message_text(
    f"Game Started!\n\nBatsman: {match['batsman'].first_name}\nBowler: {match['bowler'].first_name}\n\n"
    f"Batsman, choose your number (1-6):",
    reply_markup=InlineKeyboardMarkup(keyboard),
)

async def play_turn(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() batsman_num = int(query.data.split("_")[1]) match_id = str(query.message.chat.id) match = matches[match_id] user = query.from_user

if match["state"] != "playing" or user != match["batsman"]:
    return await query.answer("Not your turn or invalid state.", show_alert=True)

bowler_num = random.randint(1, 6)

if batsman_num == bowler_num:
    # OUT
    text = (
        f"Batsman chose - {batsman_num}\n"
        f"Bowler chose - {bowler_num}\n"
        f"{match['batsman'].first_name} is OUT!\n"
        f"Score: {match['batsman_score']} in {match['balls_played'] + 1} balls\n"
    )
    if match["innings"] == 1:
        match["target"] = match["batsman_score"] + 1
        match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
        match["batsman_score"] = 0
        match["balls_played"] = 0
        match["innings"] = 2
        text += (
            f"\nInnings 2 begins.\n"
            f"Target: {match['target']}\n"
            f"{match['batsman'].first_name}, choose your number (1-6):"
        )
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        winner = match["bowler"] if match["batsman_score"] < match["target"] else match["batsman"]
        text += f"\nMatch Over! Winner: {winner.first_name}"
        await query.edit_message_text(text)
        del matches[match_id]
else:
    match["batsman_score"] += batsman_num
    match["balls_played"] += 1
    if match["innings"] == 2 and match["batsman_score"] >= match["target"]:
        await query.edit_message_text(
            f"{match['batsman'].first_name} scored {match['batsman_score']} and won the match!"
        )
        del matches[match_id]
    else:
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
        ]
        await query.edit_message_text(
            f"Batsman chose - {batsman_num}\nBowler chose - {bowler_num}\n"
            f"Total Score: {match['batsman_score']}\n"
            f"Batsman, choose your number (1-6):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

def main(): app = ApplicationBuilder().token(TOKEN).build() app.add_handler(CommandHandler("start", start)) app.add_handler(CallbackQueryHandler(start_pvp, pattern="^start_pvp$")) app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$")) app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_")) app.add_handler(CallbackQueryHandler(choose_play, pattern="^(bat|bowl)$")) app.add_handler(CallbackQueryHandler(play_turn, pattern="^num_\d$")) print("Bot started!") app.run_polling()

if name == "main": main()

