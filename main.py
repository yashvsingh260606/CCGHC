import logging
import asyncio
import random  # For toss and random choices
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, ConversationHandler,
)
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Constants & Globals ===
BOT_TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'  # <-- Put your bot token here

admins = {123456789}  # Replace with actual admin Telegram user IDs

CHOOSING_BATSMAN, CHOOSING_BOWLER = range(2)

# Player data store for registration & coins
user_data_store = {}

# In-memory matches info, key: chat_id
matches = {}

# Command descriptions for slash suggestions
commands_list = [
    ('start', 'Start the bot'),
    ('profile', 'Show your profile and coins'),
    ('register', 'Register yourself to play'),
    ('myteam', 'View your team'),
    ('buy', 'Buy a player'),
    ('play', 'Start a match'),
    ('add', 'Add coins to a user (admin only)'),
    ('help', 'Show help message'),
]

# Button layout (2 rows)
bat_bowl_buttons = [
    [
        InlineKeyboardButton("1", callback_data='1'),
        InlineKeyboardButton("2", callback_data='2'),
        InlineKeyboardButton("3", callback_data='3'),
    ],
    [
        InlineKeyboardButton("4", callback_data='4'),
        InlineKeyboardButton("5", callback_data='5'),
        InlineKeyboardButton("6", callback_data='6'),
    ],
]

# === Helper functions ===

def get_user_data(user_id):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            'coins': 1000,
            'registered': False,
            'team': [],
        }
    return user_data_store[user_id]

def format_score_message(match):
    # Format the current match status message, fitting mobile screen width
    over = f"Over : {match['ball_count']//6}.{match['ball_count']%6}"
    batsman = match['batsman_name']
    bowler = match['bowler_name']
    score = match['score']

    msg = f"{over}\n\n🏏 Batter : {batsman}\n⚾ Bowler : {bowler}\n\n"

    if match['last_wicket']:
        msg += f"{bowler} Bat {match['bowler_last_bat']}\n{batsman} Bowl {match['batsman_last_bowl']}\n\n"
        msg += f"{bowler} Sets a target of {score}\n\n"
        msg += f"{batsman} will now Bat and {bowler} will now Bowl!"
    else:
        msg += f"{batsman} Bat {match['batsman_last_bat']}\n{bowler} Bowl {match['bowler_last_bowl']}\n\n"
        msg += f"Total Score :\n{batsman} Scored total of {score} Runs\n\n"
        msg += f"Next Move :\n{batsman} Continue your Bat!"

    return msg

def create_choice_keyboard():
    return InlineKeyboardMarkup(bat_bowl_buttons)

def is_admin(user_id):
    return user_id in admins

# === Command handlers ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_data(user.id)

    commands_text = "\n".join([f"/{cmd} - {desc}" for cmd, desc in commands_list])

    welcome_text = (
        f"Hello {user.first_name}!\n"
        "Welcome to Hand Cricket Bot.\n\n"
        "Available Commands:\n"
        f"{commands_text}\n\n"
        "Use /register to register yourself and start playing!"
    )

    await update.message.reply_text(welcome_text)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_data(user.id)
    if user_data['registered']:
        await update.message.reply_text("You are already registered!")
    else:
        user_data['registered'] = True
        await update.message.reply_text(
            "You are now registered! You start with 1000 coins."
        )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_data(user.id)
    if not user_data['registered']:
        await update.message.reply_text("You need to register first using /register")
        return

    text = (
        f"User: {user.first_name}\n"
        f"Coins: {user_data['coins']}\n"
        f"Team Size: {len(user_data['team'])} players"
    )
    await update.message.reply_text(text)

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return

    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments. Use numbers for user_id and amount.")
        return

    target_data = get_user_data(target_id)
    target_data['coins'] += amount

    await update.message.reply_text(f"Added {amount} coins to user {target_id}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands_text = "\n".join([f"/{cmd} - {desc}" for cmd, desc in commands_list])
    await update.message.reply_text(f"Available Commands:\n{commands_text}")

# === Play / Match handlers ===

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_data(user.id)

    if not user_data['registered']:
        await update.message.reply_text("Please register first using /register.")
        return

    chat_id = update.effective_chat.id

    if chat_id in matches:
        await update.message.reply_text("A match is already ongoing here!")
        return

    # Toss
    toss_winner = random.choice(['user', 'bot'])
    user_choice = random.choice(['bat', 'bowl']) if toss_winner == 'bot' else None

    # Initialize match data
    matches[chat_id] = {
        'player_id': user.id,
        'batting': None,  # 'user' or 'bot'
        'bowling': None,
        'ball_count': 0,
        'score': 0,
        'last_wicket': False,
        'batsman_name': user.first_name,
        'bowler_name': "Bot",
        'batsman_last_bat': 0,
        'bowler_last_bowl': 0,
        'batsman_choice': None,
        'bowler_choice': None,
        'message_id': None,
        'state': CHOOSING_BATSMAN,
    }

    # Toss message
    if toss_winner == 'user':
        msg = (
            f"Toss Result: You won!\n"
            "Choose to Bat or Bowl first.\n"
            "Send /bat or /bowl"
        )
    else:
        # Bot chooses randomly
        if user_choice == 'bat':
            msg = (
                "Toss Result: Bot won!\n"
                "Bot chose to Bat first.\n"
                "You will Bowl first.\n\n"
                "Starting match..."
            )
            matches[chat_id]['batting'] = 'bot'
            matches[chat_id]['bowling'] = 'user'
        else:
            msg = (
                "Toss Result: Bot won!\n"
                "Bot chose to Bowl first.\n"
                "You will Bat first.\n\n"
                "Starting match..."
            )
            matches[chat_id]['batting'] = 'user'
            matches[chat_id]['bowling'] = 'bot'

    sent_msg = await update.message.reply_text(msg)

    matches[chat_id]['message_id'] = sent_msg.message_id

    if toss_winner == 'bot':
        # Start game directly
        await prompt_batsman_choice(update, context, chat_id)

async def bat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in matches:
        await update.message.reply_text("No match ongoing here. Use /play to start.")
        return

    match = matches[chat_id]

    if match['batting'] or match['bowling']:
        await update.message.reply_text("Toss already done.")
        return

    if match['player_id'] != user.id:
        await update.message.reply_text("You are not the player of this match.")
        return

    match['batting'] = 'user'
    match['bowling'] = 'bot'

    await update.message.reply_text("You chose to Bat first. Starting match...")

    await prompt_batsman_choice(update, context, chat_id)

async def bowl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in matches:
        await update.message.reply_text("No match ongoing here. Use /play to start.")
        return

    match = matches[chat_id]

    if match['batting'] or match['bowling']:
        await update.message.reply_text("Toss already done.")
        return

    if match['player_id'] != user.id:
        await update.message.reply_text("You are not the player of this match.")
        return

    match['batting'] = 'bot'
    match['bowling'] = 'user'

    await update.message.reply_text("You chose to Bowl first. Starting match...")

    await prompt_batsman_choice(update, context, chat_id)

async def prompt_batsman_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id):
    match = matches[chat_id]
    chat = update.effective_chat

    if match['batting'] == 'user':
        # Prompt user batsman to choose number
        text = f"Your turn to Bat! Choose a number:"
        if match['message_id']:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=match['message_id'],
                text=text,
                reply_markup=create_choice_keyboard(),
            )
        else:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=create_choice_keyboard())
            match['message_id'] = msg.message_id
    else:
        # Bot batsman plays randomly
        await bot_batsman_play(update, context, chat_id)

async def bot_batsman_play(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id):
    match = matches[chat_id]

    bot_choice = random.randint(1, 6)
    match['batsman_choice'] = bot_choice

    # Now user bowls
    text = f"Bot chose its number. Now you Bowl! Choose a number:"
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=match['message_id'],
        text=text,
        reply_markup=create_choice_keyboard(),
    )

    match['state'] = CHOOSING_BOWLER

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    data = query.data

    if chat_id not in matches:
        await query.answer("No ongoing match.")
        return

    match = matches[chat_id]

    if user.id != match['player_id']:
        await query.answer("You are not playing this match.")
        return

    chosen_num = int(data)

    # State handling
    if match['state'] == CHOOSING_BATSMAN:
        # User batsman chooses number
        match['batsman_choice'] = chosen_num
        match['state'] = CHOOSING_BOWLER

        batsman = match['batsman_name']
        bowler = match['bowler_name']

        text = f"{batsman} chose a number.\nNow it's {bowler}'s turn to bowl."
        await query.edit_message_text(text, reply_markup=create_choice_keyboard())
        await query.answer()

    elif match['state'] == CHOOSING_BOWLER:
        # User bowler chooses number
        match['bowler_choice'] = chosen_num

        batsman = match['batsman_name']
        bowler = match['bowler_name']

        # Reveal both numbers and process run or wicket
        bat_num = match['batsman_choice']
        bowl_num = match['bowler_choice']

        # Update last bat/bowl for display
        match['batsman_last_bat'] = bat_num
        match['bowler_last_bowl'] = bowl_num

        # Process runs or wicket
        if bat_num == bowl_num:
            # Wicket
            match['last_wicket'] = True
            # For simplicity end match here, real logic can be more complex
            text = (
                f"Over : {match['ball_count']//6}.{match['ball_count']%6}\n\n"
                f"🏏 Batter : {batsman}\n⚾ Bowler : {bowler}\n\n"
                f"{bowler} Bat {bat_num}\n"
                f"{batsman} Bowl {bowl_num}\n\n"
                f"{bowler} Sets a target of {match['score']}\n\n"
                f"{batsman} will now Bat and {bowler} will now Bowl!"
            )
        else:
            # Runs scored = bat_num * 5 (example)
            runs = bat_num * 5
            match['score'] += runs
            match['ball_count'] += 1
            match['last_wicket'] = False

            text = (
                f"Over : {match['ball_count']//6}.{match['ball_count']%6}\n\n"
                f"🏏 Batter : {batsman}\n⚾ Bowler : {bowler}\n\n"
                f"{batsman} Bat {bat_num}\n"
                f"{bowler} Bowl {bowl_num}\n\n"
                f"Total Score :\n"
                f"{batsman} Scored total of {match['score']} Runs\n\n"
                f"Next Move :\n"
                f"{batsman} Continue your Bat!"
            )

        # Reset choices
        match['batsman_choice'] = None
        match['bowler_choice'] = None
        match['state'] = CHOOSING_BATSMAN

        await query.edit_message_text(text, reply_markup=create_choice_keyboard())
        await query.answer()

async def myteam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_data(user.id)
    if not user_data['registered']:
        await update.message.reply_text("You need to register first using /register.")
        return
    team = user_data.get('team', [])
    if not team:
        await update.message.reply_text("Your team is empty.")
    else:
        await update.message.reply_text("Your team players:\n" + "\n".join(team))

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Placeholder buy command
    user = update.effective_user
    user_data = get_user_data(user.id)
    if not user_data['registered']:
        await update.message.reply_text("Register first using /register.")
        return
    await update.message.reply_text("Buy command not implemented yet.")

# === Main function and app run ===

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Set bot commands for slash suggestions
    bot_commands = [BotCommand(cmd, desc) for cmd, desc in commands_list]
    application.bot.set_my_commands(bot_commands)

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("add", add_coins))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("bat", bat_command))
    application.add_handler(CommandHandler("bowl", bowl_command))
    application.add_handler(CommandHandler("myteam", myteam))
    application.add_handler(CommandHandler("buy", buy))

    # CallbackQuery handler for button presses
    application.add_handler(CallbackQueryHandler(handle_button))

    application.run_polling()

if __name__ == '__main__':
    main()

# === Additional Helper Functions ===

def switch_innings(match):
    # Switch batting and bowling sides for second innings
    if match['batting'] == 'user':
        match['batting'] = 'bot'
        match['bowling'] = 'user'
        match['batsman_name'] = "Bot"
        match['bowler_name'] = match['player_name']
    else:
        match['batting'] = 'user'
        match['bowling'] = 'bot'
        match['batsman_name'] = match['player_name']
        match['bowler_name'] = "Bot"

    match['ball_count'] = 0
    match['score'] = 0
    match['last_wicket'] = False
    match['batsman_last_bat'] = 0
    match['bowler_last_bowl'] = 0
    match['state'] = CHOOSING_BATSMAN
    match['innings'] = 2

async def update_match_message(context, chat_id, match):
    text = format_score_message(match)
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=match['message_id'],
            text=text,
            reply_markup=create_choice_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"Failed to update message: {e}")

async def end_match(context, chat_id, match):
    winner = None
    # Basic logic: higher score wins
    if match['batting'] == 'user':
        # match ended on user's batting innings, check scores
        # (Expand as needed for real two innings logic)
        winner = "You" if match['score'] > match.get('target', 0) else "Bot"
    else:
        winner = "Bot" if match['score'] > match.get('target', 0) else "You"

    final_text = (
        f"Match ended!\n"
        f"Final Score: {match['score']}\n"
        f"Winner: {winner}"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=match['message_id'],
            text=final_text,
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Failed to send final message: {e}")

    # Remove match from memory
    del matches[chat_id]

# Extend handle_button for innings & match logic

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    data = query.data

    if chat_id not in matches:
        await query.answer("No ongoing match.")
        return

    match = matches[chat_id]

    if user.id != match['player_id']:
        await query.answer("You are not playing this match.")
        return

    chosen_num = int(data)

    # State handling & innings logic
    if match['state'] == CHOOSING_BATSMAN:
        # User batsman chooses number or bot batsman handled elsewhere
        if match['batting'] == 'user':
            match['batsman_choice'] = chosen_num
            match['state'] = CHOOSING_BOWLER
            batsman = match['batsman_name']
            bowler = match['bowler_name']
            text = f"{batsman} chose a number.\nNow it's {bowler}'s turn to bowl."
            await query.edit_message_text(text, reply_markup=create_choice_keyboard())
            await query.answer()
        else:
            await query.answer("Wait for your turn.")
    elif match['state'] == CHOOSING_BOWLER:
        if match['bowling'] == 'user':
            match['bowler_choice'] = chosen_num

            # Reveal both numbers and process run or wicket
            bat_num = match['batsman_choice']
            bowl_num = match['bowler_choice']

            match['batsman_last_bat'] = bat_num
            match['bowler_last_bowl'] = bowl_num

            if bat_num == bowl_num:
                # Wicket
                match['last_wicket'] = True
                match['ball_count'] += 1

                # Check innings and switch or end match
                if match.get('innings', 1) == 1:
                    # Set target and switch innings
                    match['target'] = match['score']
                    await query.edit_message_text(
                        f"Wicket! Innings over.\nTarget set: {match['target']}\nSwitching innings...",
                        reply_markup=None,
                    )
                    await asyncio.sleep(3)
                    switch_innings(match)
                    await update_match_message(context, chat_id, match)
                else:
                    # Match end
                    await end_match(context, chat_id, match)
            else:
                runs = bat_num * 5
                match['score'] += runs
                match['ball_count'] += 1
                match['last_wicket'] = False

                # Check if target reached (2nd innings)
                if match.get('innings', 1) == 2 and match['score'] > match.get('target', 0):
                    await end_match(context, chat_id, match)
                else:
                    await update_match_message(context, chat_id, match)

                match['state'] = CHOOSING_BATSMAN
                match['batsman_choice'] = None
                match['bowler_choice'] = None

            await query.answer()
        else:
            await query.answer("Wait for your turn.")

# Extend play command for player_name and set default innings

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_data(user.id)

    if not user_data['registered']:
        await update.message.reply_text("Please register first using /register.")
        return

    chat_id = update.effective_chat.id

    if chat_id in matches:
        await update.message.reply_text("A match is already ongoing here!")
        return

    toss_winner = random.choice(['user', 'bot'])
    match = {
        'player_id': user.id,
        'player_name': user.first_name,
        'batting': None,
        'bowling': None,
        'ball_count': 0,
        'score': 0,
        'last_wicket': False,
        'batsman_name': user.first_name,
        'bowler_name': "Bot",
        'batsman_last_bat': 0,
        'bowler_last_bowl': 0,
        'batsman_choice': None,
        'bowler_choice': None,
        'message_id': None,
        'state': CHOOSING_BATSMAN,
        'innings': 1,
        'target': 0,
    }

    if toss_winner == 'user':
        msg = (
            f"Toss Result: You won!\n"
            "Choose to Bat or Bowl first.\n"
            "Send /bat or /bowl"
        )
    else:
        bot_choice = random.choice(['bat', 'bowl'])
        if bot_choice == 'bat':
            match['batting'] = 'bot'
            match['bowling'] = 'user'
            match['batsman_name'] = "Bot"
            match['bowler_name'] = user.first_name
            msg = (
                "Toss Result: Bot won!\n"
                "Bot chose to Bat first.\n"
                "You will Bowl first.\n\n"
                "Starting match..."
            )
        else:
            match['batting'] = 'user'
            match['bowling'] = 'bot'
            match['batsman_name'] = user.first_name
            match['bowler_name'] = "Bot"
            msg = (
                "Toss Result: Bot won!\n"
                "Bot chose to Bowl first.\n"
                "You will Bat first.\n\n"
                "Starting match..."
            )

    matches[chat_id] = match

    sent_msg = await update.message.reply_text(msg)
    match['message_id'] = sent_msg.message_id

    # If toss winner is bot, start play automatically
    if toss_winner == 'bot':
        if match['batting'] == 'user':
            await prompt_batsman_choice(update, context, chat_id)
        else:
            # Bot batsman turn
            bot_choice = random.randint(1, 6)
            match['batsman_choice'] = bot_choice
            text = f"Bot chose its number. Now you Bowl! Choose a number:"
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=match['message_id'],
                text=text,
                reply_markup=create_choice_keyboard(),
            )
            match['state'] = CHOOSING_BOWLER

# You can add more detailed team, buy, leaderboard functions here...

# === Main function same as Part 1 ===
# Just add 'main()' function from Part 1 to run the bot.
