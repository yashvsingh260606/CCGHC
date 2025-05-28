import logging
import sqlite3
import asyncio
import uuid
import random
from typing import Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.error import RetryAfter

# --- Configuration ---
TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo' # Replace with your bot token
ADMIN_IDS = [7361215114, 7493429677] # Replace with your Telegram user IDs as integers

# --- Database Setup ---
DB_NAME = 'handcricket_bot.db'

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Database Functions ---

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 4000
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_games (
            game_id TEXT PRIMARY KEY,
            initiator_id INTEGER,
            initiator_username TEXT,
            opponent_id INTEGER,
            opponent_username TEXT,
            initiator_score INTEGER,
            opponent_score INTEGER,
            bet_amount INTEGER,
            current_turn TEXT, -- 'initiator_batting', 'opponent_batting'
            target INTEGER,
            status TEXT, -- 'waiting_for_join', 'toss_pending', 'choice_pending', 'in_progress', 'completed', 'cancelled'
            message_id INTEGER,
            chat_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def get_user_balance(user_id: int) -> Optional[int]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_user_balance(user_id: int, amount: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def register_user(user_id: int, username: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, ?)',
                   (user_id, username, 4000))
    conn.commit()
    conn.close()

def save_game_data(game_data: Dict[str, Any]):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO active_games (
            game_id, initiator_id, initiator_username, opponent_id, opponent_username,
            initiator_score, opponent_score, bet_amount, current_turn, target, status,
            message_id, chat_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        game_data['game_id'], game_data['initiator_id'], game_data['initiator_username'],
        game_data['opponent_id'], game_data['opponent_username'],
        game_data['initiator_score'], game_data['opponent_score'],
        game_data['bet_amount'], game_data['current_turn'], game_data['target'],
        game_data['status'], game_data['message_id'], game_data['chat_id']
    ))
    conn.commit()
    conn.close()
    logger.debug(f"Game {game_data['game_id']} state for initiator {game_data['initiator_id']} saved to DB. Current status: {game_data['status']}")


def get_game_data(game_id: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM active_games WHERE game_id = ?', (game_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, result))
    return None

def delete_game_data(game_id: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM active_games WHERE game_id = ?', (game_id,))
    conn.commit()
    conn.close()
    logger.info(f"Game {game_id} deleted from DB.")

# --- Keyboard Functions ---

def get_game_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Returns the keyboard for joining or cancelling a game."""
    keyboard = [
        [InlineKeyboardButton("🤝 Join Game", callback_data=f"join_game_{game_id}")],
        [InlineKeyboardButton("❌ Cancel Game", callback_data=f"cancel_game_{game_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_toss_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Returns the keyboard for toss (Heads/Tails)."""
    keyboard = [
        [
            InlineKeyboardButton("Heads", callback_data=f"toss_{game_id}_heads"),
            InlineKeyboardButton("Tails", callback_data=f"toss_{game_id}_tails")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_bat_bowl_choice_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Returns the keyboard for choosing bat or bowl."""
    keyboard = [
        [
            InlineKeyboardButton("🏏 Bat", callback_data=f"choice_{game_id}_bat"),
            InlineKeyboardButton("⚾ Bowl", callback_data=f"choice_{game_id}_bowl")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_play_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Returns the keyboard for playing runs."""
    keyboard = [
        [InlineKeyboardButton("1", callback_data=f"play_game_{game_id}_1"),
         InlineKeyboardButton("2", callback_data=f"play_game_{game_id}_2"),
         InlineKeyboardButton("3", callback_data=f"play_game_{game_id}_3")],
        [InlineKeyboardButton("4", callback_data=f"play_game_{game_id}_4"),
         InlineKeyboardButton("5", callback_data=f"play_game_{game_id}_5"),
         InlineKeyboardButton("6", callback_data=f"play_game_{game_id}_6")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Helper Functions ---

def get_game_summary(game_data: Dict[str, Any]) -> str:
    """Generates a summary of the game state."""
    initiator_name = game_data['initiator_username']
    opponent_name = game_data['opponent_username'] if game_data['opponent_username'] else "Waiting for opponent..."
    bet_info = f"Bet: {game_data['bet_amount']}🪙" if game_data['bet_amount'] > 0 else "No Bet Game"

    status_text = {
        'waiting_for_join': f"Game initiated by {initiator_name}. {bet_info}\nStatus: Waiting for an opponent to join.",
        'toss_pending': f"Game between {initiator_name} and {opponent_name}. {bet_info}\nStatus: Toss pending. {initiator_name}, choose Heads or Tails for the toss.",
        'choice_pending': f"Game between {initiator_name} and {opponent_name}. {bet_info}\nStatus: Toss won by {game_data['current_turn']}. {game_data['current_turn']}, choose to Bat or Bowl.",
        'in_progress': (f"Game between {initiator_name} ({game_data['initiator_score']}) "
                        f"and {opponent_name} ({game_data['opponent_score']}). {bet_info}\n"
                        f"Current Turn: "
                        f"{initiator_name if game_data['current_turn'] == 'initiator_batting' else opponent_name} is {'batting' if 'batting' in game_data['current_turn'] else 'bowling'}.\n"
                        f"{f'Target: {game_data['target']}' if game_data['target'] > 0 else 'First Innings'}"
                       ),
        'completed': (f"Game between {initiator_name} ({game_data['initiator_score']}) "
                      f"and {opponent_name} ({game_data['opponent_score']}). {bet_info}\n"
                      "Status: Game Over!\n"
                      f"{'Result: ' + determine_game_result(game_data)}"
                     ),
        'cancelled': f"Game initiated by {initiator_name} ({bet_info}) has been cancelled."
    }
    return status_text.get(game_data['status'], "Unknown game status.")

def determine_game_result(game_data: Dict[str, Any]) -> str:
    """Determines the winner of a completed game."""
    initiator_score = game_data['initiator_score']
    opponent_score = game_data['opponent_score']
    
    if game_data['target'] > 0: # Second innings
        if game_data['current_turn'] == 'opponent_batting': # Opponent was batting in second innings
            if opponent_score >= game_data['target']:
                return f"{game_data['opponent_username']} wins by chasing the target!"
            else:
                return f"{game_data['initiator_username']} wins by defending the target!"
        elif game_data['current_turn'] == 'initiator_batting': # Initiator was batting in second innings
            if initiator_score >= game_data['target']:
                return f"{game_data['initiator_username']} wins by chasing the target!"
            else:
                return f"{game_data['opponent_username']} wins by defending the target!"
    else: # First innings completed, one player is out, other wins by higher score or tie
        if initiator_score > opponent_score:
            return f"{game_data['initiator_username']} wins!"
        elif opponent_score > initiator_score:
            return f"{game_data['opponent_username']} wins!"
    return "It's a tie!" # Should only happen if scores are equal after an out

async def update_game_message(context: ContextTypes.DEFAULT_TYPE, game_data: Dict[str, Any], extra_text: Optional[str] = None):
    """Edits the game message with the latest state, optionally adding extra text."""
    summary = get_game_summary(game_data)
    if extra_text:
        summary += f"\n\n{extra_text}"
    
    reply_markup = None

    if game_data['status'] == 'waiting_for_join':
        reply_markup = get_game_keyboard(game_data['game_id'])
    elif game_data['status'] == 'toss_pending':
        reply_markup = get_toss_keyboard(game_data['game_id'])
    elif game_data['status'] == 'choice_pending':
        reply_markup = get_bat_bowl_choice_keyboard(game_data['game_id'])
    elif game_data['status'] == 'in_progress':
        reply_markup = get_play_keyboard(game_data['game_id'])
    # No reply_markup for 'completed' or 'cancelled'

    try:
        await context.bot.edit_message_text(
            chat_id=game_data['chat_id'],
            message_id=game_data['message_id'],
            text=summary,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"Game {game_data['game_id']} message updated successfully to status {game_data['status']}.")
    except Exception as e:
        logger.error(f"Failed to edit message for game {game_data['game_id']}: {e}. Sending new message instead.")
        # If editing fails (e.g., message too old), send a new one
        new_message: Message = await context.bot.send_message(
            chat_id=game_data['chat_id'],
            text=summary,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        game_data['message_id'] = new_message.message_id
        save_game_data(game_data) # Update DB with new message ID

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    register_user(user_id, username) # Ensure user is registered on start
    await update.message.reply_text(
        f"👋 Welcome to Hand Cricket! I'm your bot.!\n\n"
        f"You can register with /register, view your profile with /profile, "
        f"start a game with /pm <bet_amount> or /pm_nobet, and check rules with /rules."
    )
    logger.info(f"Start command received from user {user_id} ({username})")

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    balance = get_user_balance(user_id)

    if balance is None:
        register_user(user_id, username)
        await update.message.reply_text(
            f"🎉 You've been registered! Your starting balance is 4000🪙.\n"
            f"You can now start a game with /pm <bet_amount> or /pm_nobet."
        )
        logger.info(f"User {user_id} ({username}) registered successfully.")
    else:
        await update.message.reply_text("You are already registered!")
        logger.info(f"User {user_id} ({username}) already registered.")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    balance = get_user_balance(user_id)

    if balance is None:
        await update.message.reply_text("You are not registered. Use /register to join Hand Cricket!")
        logger.info(f"Profile command failed for unregistered user {user_id} ({username}).")
    else:
        await update.message.reply_text(f"👤 **{username}'s Profile**\n💰 Balance: {balance}🪙", parse_mode='Markdown')
        logger.info(f"Profile command successful for user {user_id} ({username}). Balance: {balance}.")

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rules_text = (
        "🏏 **Hand Cricket Rules:**\n\n"
        "1. Two players, a batsman and a bowler.\n"
        "2. Both choose a number from 1 to 6 simultaneously.\n"
        "3. **If numbers match:** Batsman is OUT! Change roles.\n"
        "4. **If numbers don't match:** Batsman scores their chosen runs.\n"
        "5. **Second Innings:** The new batsman tries to beat the target set by the first batsman.\n"
        "6. **Winner:** Player with the higher score wins the bet!\n"
        "7. **Tie:** If scores are equal, bets are returned.\n\n"
        "Good luck and have fun!"
    )
    await update.message.reply_text(rules_text, parse_mode='Markdown')
    logger.info(f"Rules command used by user {update.effective_user.id}.")

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_game(update, context, is_bet_game=True)

async def pm_nobet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_game(update, context, is_bet_game=False)

async def _start_game(update: Update, context: ContextTypes.DEFAULT_TYPE, is_bet_game: bool) -> None:
    initiator_id = update.effective_user.id
    initiator_username = update.effective_user.username or f"user_{initiator_id}"
    chat_id = update.effective_chat.id

    logger.info(f"Game initiated by user {initiator_id} ({initiator_username}) in chat {chat_id}. Bet game: {is_bet_game}")

    # Check if initiator is registered
    if get_user_balance(initiator_id) is None:
        await update.message.reply_text("You need to /register first to start a game!")
        logger.info(f"User {initiator_id} not registered, game initiation failed.")
        return

    bet_amount = 0
    if is_bet_game:
        # Extract bet amount
        try:
            bet_amount = int(context.args[0])
            if bet_amount <= 0:
                raise ValueError
        except (IndexError, ValueError):
            await update.message.reply_text("Please specify a valid positive bet amount. Example: `/pm 100`")
            logger.info(f"Invalid bet amount for /pm by user {initiator_id}.")
            return

        # Check if initiator has enough balance
        if get_user_balance(initiator_id) < bet_amount:
            await update.message.reply_text(f"You don't have enough balance ({get_user_balance(initiator_id)}🪙) to bet {bet_amount}🪙.")
            logger.info(f"User {initiator_id} has insufficient balance for /pm.")
            return

    # Generate unique game ID
    game_id = str(uuid.uuid4())
    logger.info(f"Generated new game ID: {game_id}")

    # Initial game data
    game_data = {
        'game_id': game_id,
        'initiator_id': initiator_id,
        'initiator_username': initiator_username,
        'opponent_id': None,
        'opponent_username': None,
        'initiator_score': 0,
        'opponent_score': 0,
        'bet_amount': bet_amount,
        'current_turn': 'waiting_for_toss', # This will be set to 'toss_pending' when joined
        'target': 0,
        'status': 'waiting_for_join',
        'message_id': None, # To be filled after sending message
        'chat_id': chat_id
    }

    # Send initial game message (Simplified as requested)
    initiator_mention = f"[{initiator_username}](tg://user?id={initiator_id})" # Markdown for user mention
    message_text = f"{initiator_mention} created a Hand Cricket match!\n\nClick the button below to join."
    reply_markup = get_game_keyboard(game_id)
    sent_message: Message = await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"Initial game message sent. Message ID: {sent_message.message_id}, Chat ID: {chat_id}")

    # Update game data with message info and save to DB
    game_data['message_id'] = sent_message.message_id
    save_game_data(game_data)
    logger.info(f"Game {game_id} state for initiator {initiator_id} saved to DB. Initial state: {game_data['status']}")

async def handle_cancel_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback

    user_id = query.from_user.id
    username = query.from_user.username or f"user_{user_id}"
    
    logger.info(f"handle_cancel_game_callback received for Game ID: {query.data} by user {user_id} ({username})")

    try:
        game_id = query.data.split('_', 2)[2] # Extract the UUID part
    except IndexError:
        logger.error(f"Invalid callback data format for cancel: {query.data}")
        await query.edit_message_text("Error: Invalid cancel game data. Please start a new game if needed.")
        return

    game_data = get_game_data(game_id)

    if not game_data:
        await query.edit_message_text("This game no longer exists or has already been completed/cancelled.")
        logger.warning(f"Attempted to cancel non-existent game {game_id} by user {user_id}.")
        return

    if game_data['initiator_id'] != user_id:
        await query.answer("You can only cancel games you initiated.", show_alert=True) # Pop-up message
        logger.warning(f"User {user_id} tried to cancel game {game_id} which they didn't initiate.")
        return

    if game_data['status'] != 'waiting_for_join':
        await query.answer("This game is already in progress or completed and cannot be cancelled.", show_alert=True) # Pop-up
        logger.warning(f"User {user_id} tried to cancel game {game_id} which was already {game_data['status']}.")
        return

    game_data['status'] = 'cancelled'
    save_game_data(game_data) # Update status in DB
    
    # Refund the bet amount if it was a bet game
    if game_data['bet_amount'] > 0:
        update_user_balance(game_data['initiator_id'], game_data['bet_amount'])
        logger.info(f"Bet amount {game_data['bet_amount']} refunded to initiator {game_data['initiator_id']} for cancelled game {game_id}.")

    await update_game_message(context, game_data)
    delete_game_data(game_id) # Remove from active_games table
    logger.info(f"Game {game_id} successfully cancelled by initiator {user_id}.")
# --- Callback Handlers ---

async def handle_join_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback immediately

    opponent_id = query.from_user.id # This is the user who clicked 'Join'
    opponent_username = query.from_user.username or f"user_{opponent_id}"

    logger.info(f"handle_join_game_callback received for Game ID: {query.data} by user {opponent_id} ({opponent_username})")

    # The game ID is embedded in the callback data, e.g., "join_game_some-uuid"
    try:
        game_id = query.data.split('_', 2)[2] # Correctly extract the UUID part
    except IndexError:
        logger.error(f"Invalid callback data format: {query.data}")
        await query.edit_message_text("Error: Invalid game data. Please start a new game.")
        return

    game_data = get_game_data(game_id)

    if not game_data:
        await query.edit_message_text("This game no longer exists or has been cancelled/completed.")
        logger.warning(f"Attempted to join non-existent game {game_id} by user {opponent_id}. Game data not found in DB.")
        return

    # Check if opponent is registered
    if get_user_balance(opponent_id) is None:
        await query.answer("You need to /register first to join a game!", show_alert=True)
        logger.warning(f"User {opponent_id} not registered, cannot join game {game_id}.")
        return

    # Check if opponent has enough balance if it's a bet game
    if game_data['bet_amount'] > 0 and get_user_balance(opponent_id) < game_data['bet_amount']:
        await query.answer(f"You don't have enough balance ({get_user_balance(opponent_id)}🪙) to join this game (bet: {game_data['bet_amount']}🪙).", show_alert=True)
        logger.warning(f"User {opponent_id} has insufficient balance to join game {game_id}.")
        return

    if game_data['status'] != 'waiting_for_join':
        await query.answer("This game is no longer open for joining.", show_alert=True)
        logger.warning(f"Game {game_id} is not in 'waiting_for_join' status. Current: {game_data['status']}.")
        return

    if game_data['initiator_id'] == opponent_id:
        await query.answer("You cannot join your own game!", show_alert=True)
        logger.warning(f"Initiator {opponent_id} attempted to join their own game {game_id}.")
        return

    # Deduct bet from both players (temporarily, will be adjusted on win/loss) if it's a bet game
    if game_data['bet_amount'] > 0:
        update_user_balance(game_data['initiator_id'], -game_data['bet_amount'])
        update_user_balance(opponent_id, -game_data['bet_amount'])
        logger.info(f"Bet {game_data['bet_amount']} deducted from initiator {game_data['initiator_id']} and opponent {opponent_id}.")

    # Update game data for joined game
    game_data['opponent_id'] = opponent_id
    game_data['opponent_username'] = opponent_username
    game_data['status'] = 'toss_pending' # Game is ready for toss
    save_game_data(game_data)
    logger.info(f"Game {game_id} successfully joined by {opponent_id}. Status: {game_data['status']}")

    # Update message to show toss options
    await update_game_message(context, game_data)


async def handle_toss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    player_id = query.from_user.id
    player_username = query.from_user.username or f"user_{player_id}"

    try:
        _, game_id, choice = query.data.split('_', 2) # e.g., "toss_GAMEID_heads"
    except ValueError:
        logger.error(f"Invalid toss callback data: {query.data}")
        await query.edit_message_text("Error: Invalid toss data.")
        return

    game_data = get_game_data(game_id)

    if not game_data or game_data['status'] != 'toss_pending':
        await query.edit_message_text("This game is not in a toss state or does not exist.")
        return

    # --- IMPORTANT: Only initiator can make the toss choice ---
    if player_id != game_data['initiator_id']:
        await query.answer("Only the game initiator can choose Heads or Tails for the toss.", show_alert=True)
        logger.warning(f"User {player_id} (not initiator) tried to make toss choice for game {game_id}.")
        return

    # Simulate toss: 0 for Heads, 1 for Tails
    toss_result_int = random.randint(0, 1)
    toss_result_name = "Heads" if toss_result_int == 0 else "Tails"

    won_toss = False
    if (choice == 'heads' and toss_result_int == 0) or \
       (choice == 'tails' and toss_result_int == 1):
        won_toss = True

    toss_winner_id = game_data['initiator_id'] if won_toss else game_data['opponent_id']
    toss_winner_username = game_data['initiator_username'] if won_toss else game_data['opponent_username']

    game_data['status'] = 'choice_pending'
    game_data['current_turn'] = toss_winner_username # Temporarily store winner's username for choice message
    save_game_data(game_data)
    logger.info(f"Toss for game {game_id}: Initiator chose {choice}, result was {toss_result_name}. Winner: {toss_winner_username}")

    extra_message = f"{toss_winner_username} won the toss ({toss_result_name})."
    await update_game_message(context, game_data, extra_text=extra_message)

async def handle_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    player_id = query.from_user.id
    player_username = query.from_user.username or f"user_{player_id}"

    try:
        _, game_id, choice = query.data.split('_', 2) # e.g., "choice_GAMEID_bat"
    except ValueError:
        logger.error(f"Invalid choice callback data: {query.data}")
        await query.edit_message_text("Error: Invalid choice data.")
        return

    game_data = get_game_data(game_id)

    if not game_data or game_data['status'] != 'choice_pending':
        await query.edit_message_text("This game is not in a choice state or does not exist.")
        return

    # Check if the player making the choice is the toss winner
    toss_winner_id = game_data['initiator_id'] if game_data['current_turn'] == game_data['initiator_username'] else game_data['opponent_id']

    if player_id != toss_winner_id:
        await query.answer("Only the toss winner can choose to bat or bowl.", show_alert=True)
        return

    # Set initial turn based on choice
    if choice == 'bat':
        if player_id == game_data['initiator_id']:
            game_data['current_turn'] = 'initiator_batting'
        else:
            game_data['current_turn'] = 'opponent_batting'
    else: # choice == 'bowl'
        if player_id == game_data['initiator_id']:
            game_data['current_turn'] = 'opponent_batting' # Initiator chose to bowl, so opponent bats
        else:
            game_data['current_turn'] = 'initiator_batting' # Opponent chose to bowl, so initiator bats

    game_data['status'] = 'in_progress'
    save_game_data(game_data)
    logger.info(f"Game {game_id}: {player_username} chose to {choice}. Current turn: {game_data['current_turn']}")

    await update_game_message(context, game_data)
async def handle_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    player_id = query.from_user.id
    player_username = query.from_user.username or f"user_{player_id}"

    try:
        _, game_id, chosen_run_str = query.data.split('_', 2) # e.g., "play_game_GAMEID_3"
        chosen_run = int(chosen_run_str)
    except ValueError:
        logger.error(f"Invalid play callback data: {query.data}")
        await query.edit_message_text("Error: Invalid play data.")
        return

    game_data = get_game_data(game_id)

    if not game_data or game_data['status'] != 'in_progress':
        await query.edit_message_text("This game is not in progress or does not exist.")
        return

    initiator_id = game_data['initiator_id']
    opponent_id = game_data['opponent_id']

    # Determine who is batting and who is bowling
    if game_data['current_turn'] == 'initiator_batting':
        batsman_id = initiator_id
        bowler_id = opponent_id
    elif game_data['current_turn'] == 'opponent_batting':
        batsman_id = opponent_id
        bowler_id = initiator_id
    else:
        # This state should ideally not happen if turns are managed correctly
        logger.error(f"Unexpected current_turn in game {game_id}: {game_data['current_turn']}")
        await query.edit_message_text("An internal error occurred. Please start a new game.")
        return

    # Check if the player clicking the button is the current batsman OR bowler
    # This bot design assumes that both players click a button representing their choice
    # at roughly the same time, or that the bot waits for both.
    # For a simple single-button-click-per-player model, we need to know whose turn it is
    # and whether they are batting or bowling.
    # Here, we need to ensure the correct player is interacting.

    # This part of the logic needs careful consideration. If both players click the same button
    # on the same message, it's difficult to distinguish their roles (batsman vs. bowler choice).
    # A robust solution might involve:
    # 1. Sending separate keyboards/messages to batsman and bowler.
    # 2. Storing 'pending_choice' for each player and processing when both are received.
    #
    # Given the current structure (single 'play_game' callback for both), we will simulate
    # the 'other' player's choice. This is a simplification.

    # If the user clicking is the batsman, their choice is `chosen_run`. Bowler's is random.
    if player_id == batsman_id:
        batsman_choice = chosen_run
        bowler_choice = random.randint(1, 6) # Simulated bowler's choice
        # If the bowler clicks when it's batsman's turn, deny action.
        if player_id == bowler_id:
            await query.answer("It's the batsman's turn to play!", show_alert=True)
            return
    # If the user clicking is the bowler, their choice is `chosen_run`. Batsman's is random.
    elif player_id == bowler_id:
        bowler_choice = chosen_run
        batsman_choice = random.randint(1, 6) # Simulated batsman's choice
        # If the batsman clicks when it's bowler's turn, deny action.
        if player_id == batsman_id:
            await query.answer("It's the bowler's turn to play!", show_alert=True)
            return
    else:
        await query.answer("It's not your turn to play!", show_alert=True)
        return


    logger.debug(f"Game {game_id}: Batsman chose {batsman_choice}, Bowler chose {bowler_choice}.")

    outcome_message = f"Batsman played: {batsman_choice}, Bowler played: {bowler_choice}.\n"

    # Check for Out
    if batsman_choice == bowler_choice:
        outcome_message += "🚨 **OUT!** 🚨\n"
        if game_data['current_turn'] == 'initiator_batting':
            # Initiator is out, opponent starts batting
            game_data['current_turn'] = 'opponent_batting'
            game_data['target'] = game_data['initiator_score'] + 1 # Opponent needs to beat initiator's score
            outcome_message += f"{game_data['initiator_username']} is out! {game_data['opponent_username']} needs {game_data['target']} to win."
        elif game_data['current_turn'] == 'opponent_batting':
            # Opponent is out, end of game
            game_data['status'] = 'completed'
            outcome_message += f"{game_data['opponent_username']} is out!"
        logger.info(f"Game {game_id}: {game_data['current_turn']} out.")
    else:
        # Batsman scores runs
        if game_data['current_turn'] == 'initiator_batting':
            game_data['initiator_score'] += batsman_choice
            outcome_message += f"{game_data['initiator_username']} scored {batsman_choice} runs. Total: {game_data['initiator_score']}."
            # Check if target is reached in 2nd innings
            if game_data['target'] > 0 and game_data['initiator_score'] >= game_data['target']:
                game_data['status'] = 'completed' # Initiator chased target
                outcome_message += f"\n{game_data['initiator_username']} reached the target!"
        elif game_data['current_turn'] == 'opponent_batting':
            game_data['opponent_score'] += batsman_choice
            outcome_message += f"{game_data['opponent_username']} scored {batsman_choice} runs. Total: {game_data['opponent_score']}."
            # Check if target is reached in 2nd innings
            if game_data['target'] > 0 and game_data['opponent_score'] >= game_data['target']:
                game_data['status'] = 'completed' # Opponent chased target
                outcome_message += f"\n{game_data['opponent_username']} reached the target!"
        logger.info(f"Game {game_id}: {game_data['current_turn']} scored {batsman_choice}. Current score: {game_data['initiator_score'] if player_id == initiator_id else game_data['opponent_score']}.")

    # Game completion logic (after potential out or target reached)
    if game_data['status'] == 'completed':
        winner_id = None
        if game_data['bet_amount'] > 0: # Only process payouts for bet games
            if game_data['initiator_score'] > game_data['opponent_score']:
                winner_id = initiator_id
            elif game_data['opponent_score'] > game_data['initiator_score']:
                winner_id = opponent_id

            if winner_id:
                update_user_balance(winner_id, game_data['bet_amount'] * 2) # Winner gets back bet + opponent's bet
                logger.info(f"Game {game_id} completed. Winner: {winner_id}. Awarded {game_data['bet_amount'] * 2} coins.")
            else: # Tie
                update_user_balance(initiator_id, game_data['bet_amount']) # Refund initiator
                update_user_balance(opponent_id, game_data['bet_amount']) # Refund opponent
                logger.info(f"Game {game_id} completed. It's a tie. Bets refunded.")
        else: # No bet game
            logger.info(f"Game {game_id} (no bet) completed. No balance changes.")
        
        # After game completion, delete it from active_games
        delete_game_data(game_id)
        logger.info(f"Game {game_id} deleted from active_games after completion.")

    save_game_data(game_data) # Save updated game state

    # Update the message
    await update_game_message(context, game_data, extra_text=outcome_message)
# --- Error Handling ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update:", exc_info=context.error)

    # Custom error handling for specific issues
    if isinstance(context.error, RetryAfter):
        retry_after = context.error.retry_after
        logger.warning(f"Flood control exceeded. Retrying in {retry_after} seconds.")
        if update and update.effective_chat:
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"Too many requests! Please wait {retry_after} seconds before trying again."
                )
            except Exception as e:
                logger.error(f"Failed to send RetryAfter message: {e}")
        return

    # Try to notify the user in the chat
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "An error occurred while processing your request. Please try again later."
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
    
    # Send a message to admins (optional, but good for debugging)
    for admin_id in ADMIN_IDS:
        try:
            error_message = f"An error occurred: {context.error}\nUpdate: {update}"
            if len(error_message) > 4000: # Telegram message limit
                error_message = error_message[:3990] + "..."
            await context.bot.send_message(chat_id=admin_id, text=error_message)
        except Exception as e:
            logger.error(f"Failed to send error message to admin {admin_id}: {e}")


# --- Main ---

def main() -> None:
    init_db()

    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("pm", pm_command)) # For bet games
    application.add_handler(CommandHandler("pm_nobet", pm_nobet_command)) # For no-bet games

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(handle_join_game_callback, pattern=r"^join_game_"))
    application.add_handler(CallbackQueryHandler(handle_cancel_game_callback, pattern=r"^cancel_game_"))
    application.add_handler(CallbackQueryHandler(handle_toss_callback, pattern=r"^toss_"))
    application.add_handler(CallbackQueryHandler(handle_choice_callback, pattern=r"^choice_"))
    application.add_handler(CallbackQueryHandler(handle_play_callback, pattern=r"^play_game_"))


    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Bot started polling.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
