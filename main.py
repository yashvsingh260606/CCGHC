import logging
from datetime import datetime, timedelta
import random
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --- Configuration ---
# Replace 'YOUR_BOT_TOKEN' with your actual bot token
BOT_TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'
# Replace [ADMIN_ID_1, ADMIN_ID_2] with your Telegram user IDs as integers
ADMIN_IDS = [123456789] # e.g., [123456789, 987654321]

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- In-Memory Database (for demonstration purposes) ---
# This data will be lost when the bot restarts.

# User data: {user_id: {'name': '...', 'coins': ..., 'wins': ..., 'losses': ..., 'last_daily': datetime_obj, 'username': '...'}}
# 'username' is less critical now, but still useful for `/profile`
user_data = defaultdict(lambda: {'name': 'Player', 'coins': 0, 'wins': 0, 'losses': 0, 'last_daily': None, 'username': None})

# Active games: {game_id: {'chat_id': ..., 'player1_id': ..., 'player2_id': ..., 'bet_amount': ..., 'status': '...', 'toss_winner': ..., 'batting_player': ..., 'bowling_player': ..., 'current_batsman_score': ..., 'target': ..., 'overs_played': ..., 'innings': 1/2, 'player1_choice': None, 'player2_choice': None, 'message_id': None}}
# Reverted to a single 'message_id' for the game message in the specific chat where it's played.
# 'chat_id' will now be the group chat ID or the user's DM chat ID.
active_games = {}


# --- Helper Functions ---
def get_user_name(user_id: int) -> str:
    """Gets the user's name from user_data or provides a default."""
    return user_data[user_id].get('name', f"Player {user_id}")

def get_coins_emoji():
    return "🪙"

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the command /start is issued and stores user info."""
    user = update.effective_user
    user_data[user.id]['name'] = user.full_name # Update user's name on start
    user_data[user.id]['username'] = user.username # Store username (still useful for future features or debugging)
    await update.message.reply_html(
        f"Hello {user.mention_html()}! 👋\n\n"
        f"Welcome to **CCG HandCricket**! 🏏\n"
        f"I'm your friendly bot for playing Hand Cricket with your friends.\n\n"
        f"Use /register to get your starter coins and start playing!\n"
        f"Type /help to see all available commands."
    )

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registers a user, gives them initial coins, and stores user info."""
    user = update.effective_user
    # Ensure name and username are always updated
    user_data[user.id]['name'] = user.full_name
    user_data[user.id]['username'] = user.username

    if user_data[user.id]['coins'] == 0:
        initial_coins = 4000
        user_data[user.id]['coins'] = initial_coins
        await update.message.reply_text(
            f"🎉 Congratulations, {user.full_name}! 🎉\n"
            f"You have successfully registered for CCG HandCricket!\n"
            f"You received {initial_coins} {get_coins_emoji()} as a welcome bonus!"
        )
    else:
        await update.message.reply_text(
            f"You are already registered, {user.full_name}!\n"
            f"Your current balance is {user_data[user.id]['coins']} {get_coins_emoji()}."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows information on how to use the bot."""
    help_text = (
        "Here are the commands you can use in CCG HandCricket:\n\n"
        "🏏 `/start` - Get a welcome message from the bot.\n"
        "💰 `/register` - Register and receive a welcome bonus of 4000 coins.\n"
        "🤝 `/pm [bet_amount]` - Start a Hand Cricket match. Another player can join.\n"
        "👤 `/profile` - View your personal profile, including your coins, wins, and losses.\n"
        "☀️ `/daily` - Claim your daily bonus of 2000 coins (once every 24 hours).\n"
        "🏆 `/leaderboard` - See the top players by coins or wins.\n"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
# --- Game State Constants (from previous parts, ensure these are present) ---
GAME_STATUS_PENDING = "pending"
GAME_STATUS_IN_PROGRESS = "in_progress"
GAME_STATUS_TOSS = "toss"
GAME_STATUS_BAT_BOWL_CHOICE = "bat_bowl_choice"
GAME_STATUS_PLAYER1_CHOICE = "player1_choice"
GAME_STATUS_PLAYER2_CHOICE = "player2_choice"
GAME_STATUS_OVER = "over" # For displaying inning summary after each ball
GAME_STATUS_INNINGS_CHANGE = "innings_change"
GAME_STATUS_GAME_OVER = "game_over"

# --- Callback Data Prefixes (from previous parts, ensure these are present) ---
CALLBACK_PM_JOIN = "pm_join_"
CALLBACK_TOSS_CHOICE = "toss_choice_" # toss_choice_heads / toss_choice_tails
CALLBACK_BAT_BOWL_CHOICE = "bat_bowl_choice_" # bat_bowl_choice_bat / bat_bowl_choice_bowl
CALLBACK_GAME_CHOICE = "game_choice_" # game_choice_1 / game_choice_2 ... game_choice_6


async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a Hand Cricket match in the current chat."""
    chat_id = update.effective_chat.id
    player1_id = update.effective_user.id
    player1_name = get_user_name(player1_id)
    
    bet_amount = 0
    if context.args:
        try:
            bet_amount = int(context.args[0])
            if bet_amount <= 0:
                await update.message.reply_text("Bet amount must be a positive number.")
                return
        except ValueError:
            await update.message.reply_text("Usage: `/pm [bet_amount]`\nExample: `/pm 1000`", parse_mode='Markdown')
            return

    # Check if player1 has enough coins for the bet
    if bet_amount > 0 and user_data[player1_id]['coins'] < bet_amount:
        await update.message.reply_text(f"You don't have enough coins for a {bet_amount} {get_coins_emoji()} bet. Your current balance: {user_data[player1_id]['coins']} {get_coins_emoji()}.")
        return

    # Generate a unique game ID using chat_id and player1_id
    game_id = f"game_{chat_id}_{player1_id}_{random.randint(1000, 9999)}" 
    
    # Check if a game is already active in this chat (to prevent multiple games)
    for gid, game_data in active_games.items():
        if game_data['chat_id'] == chat_id and game_data['status'] not in [GAME_STATUS_GAME_OVER, GAME_STATUS_PENDING]:
            await update.message.reply_text("A game is already in progress in this chat. Please wait for it to finish.")
            return
        # If there's a pending game by this player, cancel it to start a new one
        if game_data['chat_id'] == chat_id and game_data['player1_id'] == player1_id and game_data['status'] == GAME_STATUS_PENDING:
            await context.bot.edit_message_text(
                chat_id=game_data['chat_id'],
                message_id=game_data['message_id'],
                text="Previous game invitation timed out or was replaced."
            )
            del active_games[gid]


    # Initialize game state
    active_games[game_id] = {
        'chat_id': chat_id, # Store the chat ID where the game is played
        'player1_id': player1_id,
        'player2_id': None, # Player 2 is not yet joined
        'bet_amount': bet_amount,
        'status': GAME_STATUS_PENDING,
        'toss_winner': None,
        'batting_player': None,
        'bowling_player': None,
        'current_batsman_score': 0,
        'target': None,
        'overs_played': 0,
        'innings': 1,
        'player1_choice': None,
        'player2_choice': None,
        'message_id': None, # Message ID of the game status message
    }

    # Message for game initiation
    keyboard = [[
        InlineKeyboardButton("Join Game 👋", callback_data=f"{CALLBACK_PM_JOIN}{game_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = f"**{player1_name}** has started a Hand Cricket match!\n"
    if bet_amount > 0:
        message_text += f"💰 Bet Amount: {bet_amount} {get_coins_emoji()}\n"
    message_text += "\nClick 'Join Game' below to accept the challenge!"

    sent_message = await update.message.reply_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    active_games[game_id]['message_id'] = sent_message.message_id


async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Join' button press for a match."""
    query = update.callback_query
    await query.answer()

    game_id = query.data.replace(CALLBACK_PM_JOIN, '')
    player2_id = query.from_user.id
    player2_name = get_user_name(player2_id)
    chat_id = query.message.chat_id

    game = active_games.get(game_id)

    if not game or game['chat_id'] != chat_id:
        await query.edit_message_text("This game request is no longer valid or has expired.")
        return

    player1_id = game['player1_id']
    player1_name = get_user_name(player1_id)

    if player2_id == player1_id:
        await query.answer("You cannot join your own game!", show_alert=True)
        return

    if game['status'] != GAME_STATUS_PENDING:
        await query.edit_message_text("This game has already started or been cancelled.")
        return

    # Check player2's coins for bet
    if game['bet_amount'] > 0 and user_data[player2_id]['coins'] < game['bet_amount']:
        await query.edit_message_text(f"Sorry, {player2_name}! You don't have enough coins ({game['bet_amount']} {get_coins_emoji()}) to join this bet. Your current balance: {user_data[player2_id]['coins']} {get_coins_emoji()}.")
        return

    # Player 2 successfully joined
    game['player2_id'] = player2_id
    game['status'] = GAME_STATUS_TOSS # Move to toss phase

    # Generate toss message and keyboard
    toss_message_text = (
        f"🏏 Game between **{player1_name}** and **{player2_name}** has started!\n\n"
        f"It's time for the toss! **{player1_name}**, please choose Heads or Tails."
    )
    if game['bet_amount'] > 0:
        toss_message_text += f"\n💰 Bet Amount: {game['bet_amount']} {get_coins_emoji()}"

    keyboard = [[
        InlineKeyboardButton("Heads 🪙", callback_data=f"{CALLBACK_TOSS_CHOICE}heads_{game_id}"),
        InlineKeyboardButton("Tails 🌕", callback_data=f"{CALLBACK_TOSS_CHOICE}tails_{game_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit the message in the current chat
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['message_id'],
            text=toss_message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message in join_game: {e}")
        await query.message.reply_text("Something went wrong with starting the toss. Please try again.")
        del active_games[game_id] # Clean up game if error occurs
# --- Important: Ensure these constants are defined from previous parts ---
# GAME_STATUS_TOSS
# GAME_STATUS_BAT_BOWL_CHOICE
# CALLBACK_TOSS_CHOICE
# CALLBACK_BAT_BOWL_CHOICE
# CALLBACK_GAME_CHOICE (used in handle_bat_bowl_choice to set up next turn)

async def handle_toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the toss choice (Heads/Tails) made by Player 1, updating the single game message."""
    query = update.callback_query
    await query.answer()

    # Extract choice (heads/tails) and game_id from callback_data
    parts = query.data.split('_')
    player_choice = parts[2] # "heads" or "tails"
    game_id = parts[3]

    game = active_games.get(game_id)
    if not game:
        await query.edit_message_text("This game is no longer active.")
        return

    chat_id = game['chat_id']
    player1_id = game['player1_id']
    player2_id = game['player2_id'] # Player 2 should be set by now
    player1_name = get_user_name(player1_id)
    player2_name = get_user_name(player2_id)

    # Ensure only Player 1 (the game initiator) can make the toss choice
    if query.from_user.id != player1_id:
        await query.answer("Only the game initiator can choose for the toss.", show_alert=True)
        return

    if game['status'] != GAME_STATUS_TOSS:
        await query.edit_message_text("The toss has already been decided or the game state is invalid.")
        return

    # Bot's random choice for the coin
    bot_choice = random.choice(['heads', 'tails'])

    toss_result_text = f"**{player1_name}** chose **{player_choice.capitalize()}**.\n"
    toss_result_text += f"The coin landed on **{bot_choice.capitalize()}**.\n\n"

    if player_choice == bot_choice:
        toss_winner_id = player1_id
        toss_winner_name = player1_name
        toss_result_text += f"🎉 **{player1_name}** won the toss!"
    else:
        toss_winner_id = player2_id
        toss_winner_name = player2_name
        toss_result_text += f"🎉 **{player2_name}** won the toss!"

    game['toss_winner'] = toss_winner_id
    game['status'] = GAME_STATUS_BAT_BOWL_CHOICE # Move to next phase

    # Offer Bat/Bowl choice to the winner
    keyboard_bat_bowl = [[
        InlineKeyboardButton("Bat 🏏", callback_data=f"{CALLBACK_BAT_BOWL_CHOICE}bat_{game_id}"),
        InlineKeyboardButton("Bowl ⚾", callback_data=f"{CALLBACK_BAT_BOWL_CHOICE}bowl_{game_id}")
    ]]
    
    # We now only have one message to edit in the current chat
    # The buttons will be shown to everyone in the chat, but only the toss winner's click will be processed.
    reply_markup = InlineKeyboardMarkup(keyboard_bat_bowl)

    toss_result_text += f"\n\n**{toss_winner_name}**, please choose whether to Bat or Bowl."

    # Edit the single game message in the chat
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['message_id'],
            text=toss_result_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message after toss in chat {chat_id}: {e}")
        await context.message.reply_text("Something went wrong updating the game after the toss. Game cancelled.")
        if game_id in active_games: del active_games[game_id]
        return


async def handle_bat_bowl_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the choice to Bat or Bowl after winning the toss, updating the single game message."""
    query = update.callback_query
    await query.answer()

    # Extract choice (bat/bowl) and game_id
    parts = query.data.split('_')
    winner_choice = parts[3] # "bat" or "bowl"
    game_id = parts[4]

    game = active_games.get(game_id)
    if not game:
        await query.edit_message_text("This game is no longer active.")
        return

    chat_id = game['chat_id']
    toss_winner_id = game['toss_winner']
    toss_winner_name = get_user_name(toss_winner_id)
    player1_id = game['player1_id']
    player2_id = game['player2_id']
    player1_name = get_user_name(player1_id)
    player2_name = get_user_name(player2_id)


    # Ensure only the toss winner can make this choice
    if query.from_user.id != toss_winner_id:
        await query.answer("Only the toss winner can make this choice.", show_alert=True)
        return

    if game['status'] != GAME_STATUS_BAT_BOWL_CHOICE:
        await query.edit_message_text("The bat/bowl choice has already been made or the game state is invalid.")
        return

    if winner_choice == 'bat':
        game['batting_player'] = toss_winner_id
        game['bowling_player'] = player2_id if toss_winner_id == player1_id else player1_id
    else: # winner_choice == 'bowl'
        game['bowling_player'] = toss_winner_id
        game['batting_player'] = player2_id if toss_winner_id == player1_id else player1_id

    # Deduct bet amounts if applicable, before the game starts
    if game['bet_amount'] > 0:
        # Re-check coins, as balances might have changed
        if user_data[player1_id]['coins'] < game['bet_amount'] or user_data[player2_id]['coins'] < game['bet_amount']:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['message_id'],
                text=f"One of the players no longer has enough coins for the bet ({game['bet_amount']} {get_coins_emoji()}). Game cancelled.",
                parse_mode='Markdown'
            )
            if game_id in active_games: del active_games[game_id]
            return
        user_data[player1_id]['coins'] -= game['bet_amount']
        user_data[player2_id]['coins'] -= game['bet_amount']
        logger.info(f"Deducted {game['bet_amount']} from {player1_name} and {player2_name} for bet in game {game_id}")


    game['status'] = GAME_STATUS_PLAYER1_CHOICE # Ready for the first player (batsman) to choose a number

    batsman_id = game['batting_player']
    bowler_id = game['bowling_player']
    batsman_name = get_user_name(batsman_id)
    bowler_name = get_user_name(bowler_id)

    game_start_text = (
        f"**{toss_winner_name}** chose to **{winner_choice}** first!\n\n"
        f"🏏 **{batsman_name}** will now Bat and ⚾ **{bowler_name}** will now Bowl!\n\n"
        f"**{batsman_name}**, please choose a number (1-6) to bat."
    )

    # Buttons for number choices (1-6)
    keyboard_numbers = [
        [InlineKeyboardButton("1", callback_data=f"{CALLBACK_GAME_CHOICE}1_{game_id}"),
         InlineKeyboardButton("2", callback_data=f"{CALLBACK_GAME_CHOICE}2_{game_id}"),
         InlineKeyboardButton("3", callback_data=f"{CALLBACK_GAME_CHOICE}3_{game_id}")],
        [InlineKeyboardButton("4", callback_data=f"{CALLBACK_GAME_CHOICE}4_{game_id}"),
         InlineKeyboardButton("5", callback_data=f"{CALLBACK_GAME_CHOICE}5_{game_id}"),
         InlineKeyboardButton("6", callback_data=f"{CALLBACK_GAME_CHOICE}6_{game_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard_numbers) # Buttons are always present for the active player

    # Edit the single game message in the chat
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['message_id'],
            text=game_start_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message after bat/bowl choice in chat {chat_id}: {e}")
        await context.bot.send_message(chat_id, "Error updating the game after bat/bowl choice. Game cancelled.")
        if game_id in active_games: del active_games[game_id]
# --- Important: Ensure these constants are defined from previous parts ---
# GAME_STATUS_PLAYER1_CHOICE
# GAME_STATUS_PLAYER2_CHOICE
# GAME_STATUS_OVER
# GAME_STATUS_INNINGS_CHANGE
# GAME_STATUS_GAME_OVER
# CALLBACK_GAME_CHOICE

async def handle_game_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles number choices made by players during the game, updating the single game message."""
    query = update.callback_query
    await query.answer()

    # Extract chosen number and game_id
    parts = query.data.split('_')
    chosen_number = int(parts[2])
    game_id = parts[3]

    game = active_games.get(game_id)
    if not game:
        await query.edit_message_text("This game is no longer active.")
        return

    chat_id = game['chat_id']
    player1_id = game['player1_id']
    player2_id = game['player2_id']
    batting_player_id = game['batting_player']
    bowling_player_id = game['bowling_player']

    current_player_id = query.from_user.id
    current_player_name = get_user_name(current_player_id)

    # Keyboard for number choices (1-6) - always present, but only active player's click matters
    keyboard_numbers = [
        [InlineKeyboardButton("1", callback_data=f"{CALLBACK_GAME_CHOICE}1_{game_id}"),
         InlineKeyboardButton("2", callback_data=f"{CALLBACK_GAME_CHOICE}2_{game_id}"),
         InlineKeyboardButton("3", callback_data=f"{CALLBACK_GAME_CHOICE}3_{game_id}")],
        [InlineKeyboardButton("4", callback_data=f"{CALLBACK_GAME_CHOICE}4_{game_id}"),
         InlineKeyboardButton("5", callback_data=f"{CALLBACK_GAME_CHOICE}5_{game_id}"),
         InlineKeyboardButton("6", callback_data=f"{CALLBACK_GAME_CHOICE}6_{game_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard_numbers) # Default to showing buttons

    # --- Player 1's Choice (Batsman's Turn) ---
    if game['status'] == GAME_STATUS_PLAYER1_CHOICE:
        if current_player_id != batting_player_id:
            await query.answer(f"It's {get_user_name(batting_player_id)}'s turn to choose a number.", show_alert=True)
            return
        game['player1_choice'] = chosen_number # This is the batsman's choice
        game['status'] = GAME_STATUS_PLAYER2_CHOICE # Switch to bowler's turn

        message_text = (
            f"🏏 Batter: **{get_user_name(batting_player_id)}**\n"
            f"⚾ Bowler: **{get_user_name(bowling_player_id)}**\n\n"
            f"**{get_user_name(batting_player_id)}** has chosen their number. Now it's **{get_user_name(bowling_player_id)}'s** turn to choose a number (1-6) to bowl!"
        )

        # Edit the single message in the chat
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['message_id'],
                text=message_text,
                reply_markup=reply_markup, # Buttons are still shown for the next player (bowler)
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing message for bowler's turn in chat {chat_id}: {e}")
            await context.bot.send_message(chat_id, "Something went wrong. Game stopped.")
            if game_id in active_games: del active_games[game_id]
        return

    # --- Player 2's Choice (Bowler's Turn) ---
    elif game['status'] == GAME_STATUS_PLAYER2_CHOICE:
        if current_player_id != bowling_player_id:
            await query.answer(f"It's {get_user_name(bowling_player_id)}'s turn to choose a number.", show_alert=True)
            return
        game['player2_choice'] = chosen_number # This is the bowler's choice
        game['status'] = GAME_STATUS_OVER # Process the ball

        batsman_choice = game['player1_choice']
        bowler_choice = game['player2_choice']

        game_summary_text = (
            f"🏏 Batter: **{get_user_name(batting_player_id)}**\n"
            f"⚾ Bowler: **{get_user_name(bowling_player_id)}**\n\n"
        )
        game_summary_text += f"**{get_user_name(batting_player_id)}** Bat: {batsman_choice}\n"
        game_summary_text += f"**{get_user_name(bowling_player_id)}** Bowl: {bowler_choice}\n\n"

        # --- Game Logic: Check for Wicket or Runs ---
        if batsman_choice == bowler_choice:
            # Wicket!
            wicket_message = "💥 **OUT!** 💥"
            game_summary_text += f"{wicket_message}\n\n"
            game_summary_text += f"Total Score: {game['current_batsman_score']} Runs\n\n"

            if game['innings'] == 1:
                # End of First Innings
                game['target'] = game['current_batsman_score'] + 1 # Target for 2nd innings
                game_summary_text += f"**{get_user_name(bowling_player_id)}** Sets a target of **{game['target']}** runs!\n\n"
                game_summary_text += f"It's time for the second innings!\n"
                
                # Swap batting and bowling players for the second innings
                game['innings'] = 2
                game['current_batsman_score'] = 0 # Reset score for new innings
                game['overs_played'] = 0 # Reset overs/balls
                game['batting_player'], game['bowling_player'] = game['bowling_player'], game['batting_player']
                game['status'] = GAME_STATUS_PLAYER1_CHOICE # Ready for new batsman's turn

                game_summary_text += f"🏏 **{get_user_name(game['batting_player'])}** will now Bat and ⚾ **{get_user_name(game['bowling_player'])}** will now Bowl!\n"
                game_summary_text += f"\n**{get_user_name(game['batting_player'])}**, please choose a number (1-6) to bat."
                
                # Buttons remain for the new batsman
                reply_markup = InlineKeyboardMarkup(keyboard_numbers)

            elif game['innings'] == 2:
                # Second innings, wicket means game over
                game_summary_text += f"**{get_user_name(batting_player_id)}** failed to reach the target of {game['target'] - 1} runs.\n"
                game_summary_text += f"Total Score: {game['current_batsman_score']}\n"
                
                # Determine winner and loser based on target and current score
                winner_id = bowling_player_id # Bowler wins if batsman gets out before target
                loser_id = batting_player_id
                
                game_summary_text += f"**{get_user_name(winner_id)}** wins the match by {game['target'] - 1 - game['current_batsman_score']} runs!"
                game_summary_text += "\n\n**Match Over!**"
                game['status'] = GAME_STATUS_GAME_OVER
                reply_markup = None # No more buttons

                # Update user stats and distribute coins
                user_data[winner_id]['wins'] += 1
                user_data[loser_id]['losses'] += 1
                if game['bet_amount'] > 0:
                    user_data[winner_id]['coins'] += (game['bet_amount'] * 2) # Winner gets double the bet
                    logger.info(f"{get_user_name(winner_id)} won {game['bet_amount']*2} coins in game {game_id}")
                    game_summary_text += f"\n\n**{get_user_name(winner_id)}** received {game['bet_amount']*2} {get_coins_emoji()}!"
                
                # Clean up game
                if game_id in active_games: del active_games[game_id]

        else:
            # Not out, add runs
            runs_scored = batsman_choice
            game['current_batsman_score'] += runs_scored
            game_summary_text += f"**{get_user_name(batting_player_id)}** scored {runs_scored} run(s).\n\n"
            game_summary_text += f"Total Score: {game['current_batsman_score']} Runs\n\n"

            # Check for win condition in second innings
            if game['innings'] == 2 and game['current_batsman_score'] >= game['target']:
                # Batsman chased target, they win
                winner_id = batting_player_id
                loser_id = bowling_player_id

                game_summary_text += f"**{get_user_name(winner_id)}** successfully chased the target of {game['target'] - 1} runs!\n"
                game_summary_text += f"**{get_user_name(winner_id)}** wins the match!"
                game_summary_text += "\n\n**Match Over!**"
                game['status'] = GAME_STATUS_GAME_OVER
                reply_markup = None # No more buttons

                # Update user stats and distribute coins
                user_data[winner_id]['wins'] += 1
                user_data[loser_id]['losses'] += 1
                if game['bet_amount'] > 0:
                    user_data[winner_id]['coins'] += (game['bet_amount'] * 2) # Winner gets double the bet
                    logger.info(f"{get_user_name(winner_id)} won {game['bet_amount']*2} coins in game {game_id}")
                    game_summary_text += f"\n\n**{get_user_name(winner_id)}** received {game['bet_amount']*2} {get_coins_emoji()}!"
                
                # Clean up game
                if game_id in active_games: del active_games[game_id]

            else:
                # Continue game
                game['status'] = GAME_STATUS_PLAYER1_CHOICE # Switch turns for next ball (batsman next)
                game['player1_choice'] = None # Reset choices
                game['player2_choice'] = None

                game_summary_text += f"Next Move:\n"
                game_summary_text += f"**{get_user_name(batting_player_id)}** Continue your Bat!\n\n"
                game_summary_text += f"**{get_user_name(batting_player_id)}**, please choose a number (1-6) to bat."
                
                # Buttons remain for the batsman
                reply_markup = InlineKeyboardMarkup(keyboard_numbers)

        # --- Update the single game message with current game state and appropriate buttons ---
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['message_id'],
                text=game_summary_text,
                reply_markup=reply_markup, # Can be None if game over
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing message during game turn in chat {chat_id}: {e}")
            await context.bot.send_message(chat_id, "Something went wrong during the game. Game stopped.")
            if game_id in active_games: del active_games[game_id]
# --- Additional Command Handlers (from previous parts) ---

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's profile."""
    user = update.effective_user
    user_id = user.id
    
    # Ensure user data is initialized, especially for new users who might skip /start then directly /profile
    # Also ensure username is stored for future challenges (if you ever re-implement direct challenges)
    if user_id not in user_data or user_data[user_id].get('name') == 'Player':
        user_data[user_id]['name'] = user.full_name
        user_data[user.id]['username'] = user.username # Store username
    
    profile_info = user_data[user_id] # Re-fetch after potential update

    profile_text = (
        f"**{user.full_name}'s Profile** -\n\n"
        f"Name : {profile_info.get('name', 'N/A')}\n"
        f"ID : `{user_id}`\n"
        f"Purse : {profile_info.get('coins', 0)} {get_coins_emoji()}\n\n"
        f"**Performance History** :\n"
        f"Wins : {profile_info.get('wins', 0)}\n"
        f"Loss : {profile_info.get('losses', 0)}"
    )
    await update.message.reply_text(profile_text, parse_mode='Markdown')


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gives daily coins to the user."""
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    current_time = datetime.now()

    # Ensure user data is initialized for daily claim
    if user_id not in user_data:
        user_data[user_id]['name'] = user_name
        user_data[user_id]['username'] = update.effective_user.username
        user_data[user_id]['coins'] = 0
        user_data[user_id]['wins'] = 0
        user_data[user_id]['losses'] = 0
        user_data[user_id]['last_daily'] = None # Initialize to None

    last_daily_claim = user_data[user_id]['last_daily']

    if last_daily_claim:
        time_since_last_claim = current_time - last_daily_claim
        if time_since_last_claim < timedelta(hours=24):
            remaining_time = timedelta(hours=24) - time_since_last_claim
            hours, remainder = divmod(remaining_time.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            await update.message.reply_text(
                f"You have already claimed your daily bonus for today, {user_name}!\n"
                f"Please try again in {hours} hours and {minutes} minutes."
            )
            return

    daily_bonus = 2000
    user_data[user_id]['coins'] += daily_bonus
    user_data[user_id]['last_daily'] = current_time
    # Ensure name and username are always updated for current interaction
    user_data[user_id]['name'] = user_name
    user_data[user_id]['username'] = update.effective_user.username

    await update.message.reply_text(
        f"🎉 Congratulations, {user_name}! 🎉\n"
        f"You received your daily bonus of {daily_bonus} {get_coins_emoji()}!\n"
        f"Your new balance is {user_data[user_id]['coins']} {get_coins_emoji()}."
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the leaderboard of top players by coins or wins."""
    # Default to coins leaderboard type
    context.user_data['leaderboard_type'] = context.user_data.get('leaderboard_type', 'coins')
    await send_leaderboard_message(update, context, context.user_data['leaderboard_type'])

async def send_leaderboard_message(update: Update, context: ContextTypes.DEFAULT_TYPE, leaderboard_type: str):
    """Helper function to send or edit the leaderboard message."""
    
    sorted_players = []
    if leaderboard_type == 'coins':
        # Filter out users with 0 coins if desired, or sort all
        sorted_players = sorted(user_data.items(), key=lambda item: item[1]['coins'], reverse=True)
        title = "🏆 Top 10 Richest Players (Coins) 🏆"
    elif leaderboard_type == 'wins':
        # Filter out users with 0 wins if desired, or sort all
        sorted_players = sorted(user_data.items(), key=lambda item: item[1]['wins'], reverse=True)
        title = "🏅 Top 10 Players (Wins) 🏅"
    
    leaderboard_text = f"**{title}**\n\n"
    if not sorted_players:
        leaderboard_text += "No players on the leaderboard yet!"
    else:
        for i, (user_id, data) in enumerate(sorted_players[:10]): # Display top 10
            # Use stored name or a default if not found
            name = data.get('name', f"Player {user_id}")
            if leaderboard_type == 'coins':
                value = data.get('coins', 0)
                leaderboard_text += f"{i+1}. {name}: {value} {get_coins_emoji()}\n"
            elif leaderboard_type == 'wins':
                value = data.get('wins', 0)
                leaderboard_text += f"{i+1}. {name}: {value} Wins\n"

    keyboard = [
        [
            InlineKeyboardButton("Show Coins 🪙", callback_data="leaderboard_coins"),
            InlineKeyboardButton("Show Wins 🏆", callback_data="leaderboard_wins")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if update.callback_query:
            # Edit the existing message if it's a callback query
            await update.callback_query.edit_message_text(
                text=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # Send a new message if it's a command
            await update.message.reply_text(
                text=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error sending/editing leaderboard message: {e}")
        # If the message can't be edited (e.g., too old), send a new one
        if update.callback_query:
             await update.callback_query.message.reply_text(
                text=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries for leaderboard pagination."""
    query = update.callback_query
    await query.answer() # Always answer the callback query

    if query.data == "leaderboard_coins":
        context.user_data['leaderboard_type'] = 'coins'
        await send_leaderboard_message(update, context, 'coins')
    elif query.data == "leaderboard_wins":
        context.user_data['leaderboard_type'] = 'wins'
        await send_leaderboard_message(update, context, 'wins')


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to add coins to a user."""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/add <user_id> <amount>`", parse_mode='Markdown')
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("Amount must be a positive number.")
            return

        # Ensure target user data is initialized, especially if adding coins to a very new user
        if target_user_id not in user_data:
            user_data[target_user_id]['name'] = f"User {target_user_id}" # Default name
            user_data[target_user_id]['coins'] = 0 # Initialize coins
            user_data[target_user_id]['wins'] = 0
            user_data[target_user_id]['losses'] = 0
            user_data[target_user_id]['last_daily'] = None
            user_data[target_user_id]['username'] = None

        user_data[target_user_id]['coins'] += amount
        target_user_name = get_user_name(target_user_id) # Get the name after potential initialization

        await update.message.reply_text(
            f"Successfully added {amount} {get_coins_emoji()} to {target_user_name} (ID: `{target_user_id}`).\n"
            f"New balance: {user_data[target_user_id]['coins']} {get_coins_emoji()}."
            , parse_mode='Markdown'
        )
        # Optionally, try to notify the target user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"An admin has added {amount} {get_coins_emoji()} to your purse! Your new balance is {user_data[target_user_id]['coins']} {get_coins_emoji()}."
            )
        except Exception as e:
            logger.warning(f"Could not notify user {target_user_id} of /add command: {e}")


# --- Main Function ---

def main() -> None:
    """Starts the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("pm", pm_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("daily", daily_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("add", add_command)) # Admin command
    application.add_handler(CommandHandler("help", help_command))

    # Callback Query Handlers (for inline keyboard buttons)
    application.add_handler(CallbackQueryHandler(join_game, pattern=f"^{CALLBACK_PM_JOIN}"))
    application.add_handler(CallbackQueryHandler(handle_toss_choice, pattern=f"^{CALLBACK_TOSS_CHOICE}"))
    application.add_handler(CallbackQueryHandler(handle_bat_bowl_choice, pattern=f"^{CALLBACK_BAT_BOWL_CHOICE}"))
    application.add_handler(CallbackQueryHandler(handle_game_choice, pattern=f"^{CALLBACK_GAME_CHOICE}"))
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^leaderboard_"))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started! Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

# --- IMPORTANT NOTE ON PERSISTENCE ---
# This bot uses in-memory dictionaries (user_data, active_games) to store data.
# This means all user balances, game states, and profiles will be LOST when the bot restarts.
# For a production-ready bot, you MUST integrate a persistent database
# (e.g., PostgreSQL, MongoDB, SQLite) to store this information.
# You would need to load data from the database on startup and save it after every relevant change.
