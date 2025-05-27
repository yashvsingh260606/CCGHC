from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
import random

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

matches = {}  # Stores ongoing matches by chat_id


async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    match_id = str(update.effective_chat.id)
    matches[match_id] = {
        "players": [user],
        "state": "waiting",
        "message_id": None,
    }
    keyboard = [[InlineKeyboardButton("Join Match", callback_data="join_match")]]
    sent = await update.message.reply_text(
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
        return await query.answer("You already joined!")

    match["players"].append(user)

    text = f"Match started between {match['players'][0].first_name} and {match['players'][1].first_name}!\n\n"
    text += "Toss time! Choose Heads or Tails."

    keyboard = [
        [
            InlineKeyboardButton("Heads", callback_data="toss_heads"),
            InlineKeyboardButton("Tails", callback_data="toss_tails"),
        ]
    ]
    match["state"] = "toss"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]  # 'heads' or 'tails'
    match_id = str(query.message.chat.id)
    match = matches[match_id]
    user = query.from_user

    if "toss_choices" not in match:
        match["toss_choices"] = {}

    if user.id in match["toss_choices"]:
        return await query.answer("You already chose!")

    match["toss_choices"][user.id] = choice

    if len(match["toss_choices"]) < 2:
        await query.edit_message_text(
            f"{user.first_name} chose {choice.capitalize()}. Waiting for opponent..."
        )
        return

    # Both players chose; decide toss winner randomly
    toss_result = random.choice(["heads", "tails"])
    players = match["players"]
    p1_choice = match["toss_choices"][players[0].id]
    p2_choice = match["toss_choices"][players[1].id]

    if p1_choice == toss_result:
        winner = players[0]
    elif p2_choice == toss_result:
        winner = players[1]
    else:
        # Rare case: no one matched toss, redo toss
        match["toss_choices"] = {}
        return await query.edit_message_text(
            "No one guessed correctly. Toss again! Choose Heads or Tails.",
            reply_markup=query.message.reply_markup,
        )

    match["toss_winner"] = winner
    match["state"] = "choose_play"

    text = (
        f"Toss result is {toss_result.capitalize()}!\n"
        f"{winner.first_name} won the toss and can choose to Bat or Bowl first."
    )
    keyboard = [
        [
            InlineKeyboardButton("Bat", callback_data="choose_bat"),
            InlineKeyboardButton("Bowl", callback_data="choose_bowl"),
        ]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]  # 'bat' or 'bowl'
    match_id = str(query.message.chat.id)
    match = matches[match_id]
    winner = match["toss_winner"]
    players = match["players"]

    # Assign roles based on toss winner choice
    if choice == "bat":
        match["batsman"] = winner
        match["bowler"] = players[1] if winner == players[0] else players[0]
    else:
        match["bowler"] = winner
        match["batsman"] = players[1] if winner == players[0] else players[0]

    match["state"] = "batting"
    match["runs"] = 0
    match["wickets"] = 0
    match["balls"] = 0
    match["over"] = 0
    match["target"] = None  # To be set after first innings

    text = (
        f"{match['batsman'].first_name} will bat first.\n"
        f"{match['batsman'].first_name} choose a number between 1 to 6."
    )
   keyboard = [
    [
        InlineKeyboardButton("1", callback_data="num_1"),
        InlineKeyboardButton("2", callback_data="num_2"),
        InlineKeyboardButton("3", callback_data="num_3"),
    ],
    [
        InlineKeyboardButton("4", callback_data="num_4"),
        InlineKeyboardButton("5", callback_data="num_5"),
        InlineKeyboardButton("6", callback_data="num_6"),
    ],
]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    InlineKeyboardButton("6", callback_data="num_6"),
                    ],
                ]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return
            else:
                # Second innings wicket (end game)
                target = match["target"]
                runs = match["runs"]
                if runs >= target:
                    winner = match["batsman"]
                    text = f"{winner.first_name} wins the match by scoring {runs} runs!"
                else:
                    winner = match["bowler"]
                    text = f"{winner.first_name} wins! {match['batsman'].first_name} got out at {runs} runs."
                await query.edit_message_text(text)
                matches.pop(match_id)
                return

        else:
            # Runs scored
            match["runs"] += batsman_num

            # Balls and overs count
            match["balls"] += 1
            if match["balls"] == 6:
                match["over"] += 1
                match["balls"] = 0

            # Check if second innings and target reached
            if match.get("target") is not None:
                if match["runs"] >= match["target"]:
                    text = (f"{match['batsman'].first_name} scored {match['runs']} runs.\n"
                            f"Target {match['target']} reached! {match['batsman'].first_name} wins!")
                    await query.edit_message_text(text)
                    matches.pop(match_id)
                    return

            text = (f"Ball {match['over']}.{match['balls']}:\n"
                    f"{match['batsman'].first_name} scored {batsman_num} runs.\n"
                    f"Total Runs: {match['runs']} | Wickets: {match['wickets']}\n"
                    f"{match['batsman'].first_name} to choose a number for next ball.")

            keyboard = [
                [
                    InlineKeyboardButton("1", callback_data="num_1"),
                    InlineKeyboardButton("2", callback_data="num_2"),
                    InlineKeyboardButton("3", callback_data="num_3"),
                ],
                [
                    InlineKeyboardButton("4", callback_data="num_4"),
                    InlineKeyboardButton("5", callback_data="num_5"),
                    InlineKeyboardButton("6", callback_data="num_6"),
                ],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # If wrong user pressed or invalid state
    await query.answer("Wait for your turn.")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CallbackQueryHandler(join_match, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_(heads|tails)$"))
    app.add_handler(CallbackQueryHandler(choose_play, pattern="^choose_(bat|bowl)$|^choose_bat$|^choose_bowl$"))
    app.add_handler(CallbackQueryHandler(play_turn, pattern="^num_[1-6]$"))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()