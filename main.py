# Part 1: Setup, Core Bot Logic, and Database Integration (Minor Log Refinement)

import logging
import sqlite3
import json
import random
from datetime import datetime, timedelta
import uuid # For generating unique game IDs

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler

# --- Configuration ---
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo" # Replace with your actual bot token
ADMIN_IDS = [684829863928] # Replace with your Telegram User ID(s) as integers, e.g., [123456789]
DB_NAME = "handcricket_bot.db"
DAILY_REWARD = 2000
REGISTER_REWARD = 4000
COIN_EMOJI = "🪙"

# --- Logging Setup ---
# Set logging level to INFO for production, DEBUG for development to see all details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO # Change to logging.DEBUG for more verbose output
)
logger = logging.getLogger(__name__)

# --- Database Initialization ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            purse INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            last_daily_claim TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_games (
            game_id TEXT PRIMARY KEY,
            initiator_id INTEGER,
            opponent_id INTEGER,
            bet_amount INTEGER DEFAULT 0,
            game_state TEXT, -- JSON string for game details
            message_id INTEGER,
            chat_id INTEGER,
            last_update_time TEXT -- To manage game timeouts (though not fully implemented yet)
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

# --- Helper Functions (Database Interaction) ---
def get_user_data(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data

def update_user_purse(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET purse = purse + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_user_stats(user_id, win=False, loss=False):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if win:
        cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
    if loss:
        cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def register_user(user_id, username, full_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (user_id, username, full_name, purse) VALUES (?, ?, ?, ?)",
                       (user_id, username, full_name, REGISTER_REWARD))
        conn.commit()
        logger.info(f"User {user_id} registered with initial reward.")
        return True
    except sqlite3.IntegrityError:
        logger.info(f"User {user_id} already registered.")
        return False
    finally:
        conn.close()

def get_game_data(game_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Explicitly select columns to ensure order and avoid issues with future table changes
    cursor.execute("SELECT game_id, initiator_id, opponent_id, bet_amount, game_state, message_id, chat_id, last_update_time FROM active_games WHERE game_id = ?", (game_id,))
    game_data = cursor.fetchone()
    conn.close()
    if game_data:
        game_data_list = list(game_data)
        try:
            game_state_json_str = game_data_list[4]
            game_data_list[4] = json.loads(game_state_json_str) # Load game_state JSON
            logger.debug(f"Successfully loaded game_state for {game_id}.")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode game_state JSON for game_id: {game_id}. Error: {e}. Raw data: {game_state_json_str}", exc_info=True)
            return None
        return tuple(game_data_list)
    logger.debug(f"No game data found for game_id: {game_id}.")
    return None

def save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state_dict, message_id, chat_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        game_state_json = json.dumps(game_state_dict)
        cursor.execute('''
            INSERT OR REPLACE INTO active_games
            (game_id, initiator_id, opponent_id, bet_amount, game_state, message_id, chat_id, last_update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, initiator_id, opponent_id, bet_amount, game_state_json,
              message_id, chat_id, datetime.now().isoformat()))
        conn.commit()
        logger.debug(f"Game {game_id} state successfully saved/updated in DB. message_id: {message_id}, chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Critical Error saving game state for {game_id}: {e}", exc_info=True)
    finally:
        conn.close()

def delete_game_state(game_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_games WHERE game_id = ?", (game_id,))
    conn.commit()
    conn.close()
    logger.info(f"Game {game_id} deleted from DB.")

# --- Command Handlers (Part 1) ---
async def start_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    full_name = update.effective_user.full_name

    await update.message.reply_text(
        f"👋 Welcome to CCG HandCricket, {full_name}!\n\n"
        "I'm your bot for exciting hand cricket matches. "
        "Use /help to see all available commands and get started!"
    )

async def register_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    full_name = update.effective_user.full_name

    if register_user(user_id, username, full_name):
        await update.message.reply_text(
            f"🎉 Congratulations, {full_name}! You've been registered "
            f"and received {REGISTER_REWARD}{COIN_EMOJI} as a welcome bonus!\n\n"
            "You can now use other commands like /profile, /daily, and /pm."
        )
    else:
        user_data = get_user_data(user_id)
        if user_data:
            await update.message.reply_text(
                f"You're already registered, {full_name}! "
                f"You have {user_data[3]}{COIN_EMOJI} in your purse."
            )
        else:
            await update.message.reply_text("An unexpected error occurred during registration check.")


async def profile_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text(
            "You are not registered yet! Use /register to join the game."
        )
        return

    _, username, full_name, purse, wins, losses, _ = user_data

    profile_text = (
        f"*{full_name}'s Profile* -\n\n"
        f"Name : {full_name}\n"
        f"ID : `{user_id}`\n"
        f"Purse : {purse}{COIN_EMOJI}\n\n"
        f"*Performance History* :\n"
        f"Wins : {wins}\n"
        f"Loss : {losses}"
    )
    await update.message.reply_text(profile_text, parse_mode='Markdown')

async def daily_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text(
            "You are not registered yet! Use /register to join the game."
        )
        return

    last_daily_claim_str = user_data[6]
    current_time = datetime.now()

    if last_daily_claim_str:
        last_claim_time = datetime.fromisoformat(last_daily_claim_str)
        if current_time - last_claim_time < timedelta(hours=24):
            time_left = timedelta(hours=24) - (current_time - last_claim_time)
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await update.message.reply_text(
                f"You have already claimed your daily reward. "
                f"Please wait {hours}h {minutes}m before claiming again."
            )
            return

    update_user_purse(user_id, DAILY_REWARD)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_daily_claim = ? WHERE user_id = ?",
                   (current_time.isoformat(), user_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🎁 You've claimed your daily reward of {DAILY_REWARD}{COIN_EMOJI}!\n"
        f"Your new balance is {get_user_data(user_id)[3]}{COIN_EMOJI}."
    )

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Here are the commands you can use:\n\n"
        "📚 `/start` - Get a welcome message from the bot.\n"
        "✍️ `/register` - Register yourself to start playing and get a welcome bonus.\n"
        "👤 `/profile` - View your game statistics and coin balance.\n"
        "💰 `/daily` - Claim your daily coin reward (once every 24 hours).\n"
        "⚔️ `/pm` - Start a private hand cricket match. Use `/pm <bet_amount>` to play with a bet.\n"
        "🏆 `/leaderboard` - See the top players by coins and wins.\n"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
# Part 2: Private Messaging Game Initiation and Toss Logic (Focused Logging)

# (Requires imports and helper functions from Part 1)
# Make sure Part 1's code is above this in your final script.

# --- Global Game State Management (relying on DB only) ---
# Removed ACTIVE_GAMES_CACHE to ensure all game state is fetched/saved from/to the DB.
# This makes the bot stateless regarding active games between requests.

async def pm_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    full_name = update.effective_user.full_name
    chat_id = update.effective_chat.id # This is the chat ID where the /pm command was sent

    logger.info(f"pm_command initiated by user {user_id} ({full_name}) in chat {chat_id}")

    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text(
            "You are not registered yet! Use /register to join the game."
        )
        logger.info(f"User {user_id} not registered, /pm failed.")
        return

    bet_amount = 0
    if context.args:
        try:
            bet_amount = int(context.args[0])
            if bet_amount <= 0:
                await update.message.reply_text("Bet amount must be a positive number.")
                return
            if user_data[3] < bet_amount:
                await update.message.reply_text(
                    f"You don't have enough {COIN_EMOJI} for this bet. "
                    f"Your purse: {user_data[3]}{COIN_EMOJI}, required: {bet_amount}{COIN_EMOJI}."
                )
                return
        except ValueError:
            await update.message.reply_text(
                "Invalid bet amount. Please use `/pm <number>` or just `/pm` to start a casual match."
            )
            return
    
    game_id = str(uuid.uuid4()) # Generate a unique game ID for each match
    logger.info(f"Generated new game ID: {game_id}")

    keyboard = [[InlineKeyboardButton("Join 👋", callback_data=f"join_game_{game_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        f"🏏 Cricket game has been started by *{full_name}*!\n\n"
        f"Game ID: `{game_id[:8]}...`\n" # Added game ID for clarity in multi-game scenarios
        f"Press Join below to play with {full_name}."
    )
    if bet_amount > 0:
        message_text += f"\n\n🚨 Bet Amount: {bet_amount}{COIN_EMOJI} (Winner gets double!)"

    try:
        sent_message = await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"Initial game message sent. Message ID: {sent_message.message_id}, Chat ID: {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send initial game message in chat {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Failed to start game. Please try again.")
        return

    game_state = {
        'initiator_id': user_id,
        'opponent_id': None, # Will be set when opponent joins
        'bet_amount': bet_amount,
        'state': 'waiting_for_join',
        'message_id': sent_message.message_id, # Store the specific message ID for this game
        'chat_id': chat_id, # Store the chat ID where the message was sent
        'initiator_username': update.effective_user.username or full_name, # Use full_name if username not available
        'initiator_full_name': full_name,
        'opponent_username': None,
        'opponent_full_name': None,
        'toss_winner_id': None,
        'current_batter_id': None,
        'current_bowler_id': None,
        'first_innings_score': 0,
        'first_innings_wickets': 0,
        'second_innings_score': 0,
        'second_innings_wickets': 0,
        'first_innings_runs': [],
        'second_innings_runs': [],
        'last_player_choice': None, # Stores the last number chosen by a player
        'target': None
    }
    
    save_game_state(game_id, user_id, None, bet_amount, game_state, sent_message.message_id, chat_id)
    logger.info(f"Game {game_id} state for initiator {user_id} saved to DB. Initial state: {game_state['state']}")

async def handle_join_game_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    game_id = query.data.split('_')[2]
    opponent_id = query.effective_user.id
    opponent_full_name = query.effective_user.full_name
    opponent_username = query.effective_user.username

    logger.info(f"handle_join_game_callback received for Game ID: {game_id} by user {opponent_id} ({opponent_full_name})")
    logger.debug(f"Query data: {query.data}")
    logger.debug(f"Query message ID: {query.message.message_id}, Query chat ID: {query.message.chat_id}")


    game_data = get_game_data(game_id)
    if not game_data:
        # This is the most common failure point. Check your logs for "No game data found for game_id" from get_game_data
        logger.warning(f"Attempted to join non-existent game {game_id} by user {opponent_id}. Game data not found in DB.")
        await query.edit_message_text(
            f"This game (`{game_id[:8]}...`) has expired, was cancelled, or the bot restarted.",
            reply_markup=None # Remove buttons if game is gone
        )
        return

    # Unpack game_data tuple.
    # Note: game_state (index 4) is already loaded as a dict by get_game_data
    _, initiator_id, existing_opponent_id, bet_amount, game_state, stored_msg_id, stored_chat_id, _ = game_data

    logger.debug(f"Retrieved game {game_id} from DB. Initiator: {initiator_id}, Opponent: {existing_opponent_id}, Stored Msg ID: {stored_msg_id}, Stored Chat ID: {stored_chat_id}, Current state: {game_state['state']}")

    # Critical check: Ensure the callback is for the correct message if multiple are in a chat
    if query.message.message_id != stored_msg_id or query.message.chat_id != stored_chat_id:
        logger.warning(f"Join callback message_id/chat_id mismatch for game {game_id}. Query msg ID: {query.message.message_id}, Stored msg ID: {stored_msg_id}. Query chat ID: {query.message.chat_id}, Stored chat ID: {stored_chat_id}")
        # Optionally, you could try to find the correct message and edit it, but for now, we warn.
        # Or, just reply to the user that this message is outdated/wrong.
        await query.edit_message_text(query.message.text + "\n\nThis game message might be outdated. Please click 'Join' on the latest game message.", reply_markup=None)
        return


    if opponent_id == initiator_id:
        logger.info(f"User {opponent_id} tried to join their own game {game_id}.")
        await query.edit_message_text(query.message.text + "\n\nYou cannot join your own game!", reply_markup=query.message.reply_markup)
        return

    if existing_opponent_id and existing_opponent_id != opponent_id:
        logger.info(f"Game {game_id} already has an opponent ({existing_opponent_id}). User {opponent_id} tried to join.")
        await query.edit_message_text(query.message.text + "\n\nThis game already has an opponent!", reply_markup=query.message.reply_markup)
        return
    
    if existing_opponent_id == opponent_id:
        logger.info(f"User {opponent_id} re-clicked join for game {game_id}.")
        await query.edit_message_text(query.message.text + "\n\nYou have already joined this game!", reply_markup=query.message.reply_markup)
        return

    # Removed: Check if opponent is already in another game (allows multiple games per user)

    opponent_user_data = get_user_data(opponent_id)
    if not opponent_user_data:
        logger.info(f"Opponent user {opponent_id} not registered for game {game_id}.")
        await query.edit_message_text(query.message.text + "\n\nYou are not registered yet! Use /register to join the game.", reply_markup=query.message.reply_markup)
        return
    
    if bet_amount > 0 and opponent_user_data[3] < bet_amount:
        logger.info(f"Opponent {opponent_id} has insufficient funds ({opponent_user_data[3]}) for bet {bet_amount} in game {game_id}.")
        await query.edit_message_text(
            query.message.text +
            f"\n\n❌ You don't have enough {COIN_EMOJI} for this bet. "
            f"Your purse: {opponent_user_data[3]}{COIN_EMOJI}, required: {bet_amount}{COIN_EMOJI}.",
            reply_markup=query.message.reply_markup
        )
        return

    # All checks passed, proceed to join
    game_state['opponent_id'] = opponent_id
    game_state['opponent_full_name'] = opponent_full_name
    game_state['opponent_username'] = opponent_username
    game_state['state'] = 'toss_heads_tails'
    
    save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, stored_msg_id, stored_chat_id)
    logger.info(f"Game {game_id} state updated to toss_heads_tails. Opponent {opponent_id} joined. Saved to DB.")

    initiator_full_name = game_state['initiator_full_name']

    # Deduct bet amount if applicable
    if bet_amount > 0:
        update_user_purse(initiator_id, -bet_amount)
        update_user_purse(opponent_id, -bet_amount)
        try:
            await context.bot.send_message(chat_id=initiator_id, text=f"Your {bet_amount}{COIN_EMOJI} bet has been placed for the match against {opponent_full_name} (Game ID: `{game_id[:8]}...`).")
            await context.bot.send_message(chat_id=opponent_id, text=f"Your {bet_amount}{COIN_EMOJI} bet has been placed for the match against {initiator_full_name} (Game ID: `{game_id[:8]}...`).")
        except Exception as e:
            logger.warning(f"Could not send private bet messages for game {game_id}: {e}", exc_info=True)

    keyboard = [
        [InlineKeyboardButton("Heads", callback_data=f"toss_heads_{game_id}")],
        [InlineKeyboardButton("Tails", callback_data=f"toss_tails_{game_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.edit_message_text( # Crucial: Use stored_chat_id and stored_msg_id
            chat_id=stored_chat_id,
            message_id=stored_msg_id,
            text=f"*{initiator_full_name}* vs *{opponent_full_name}*\n\n"
            f"Game ID: `{game_id[:8]}...`\n" # Added game ID for clarity
            f"Game has started! {initiator_full_name}, please choose Heads or Tails for the toss.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"Game {game_id} toss message updated. Message ID: {stored_msg_id}")
    except Exception as e:
        logger.error(f"Failed to edit message {stored_msg_id} in chat {stored_chat_id} after join for game {game_id}: {e}", exc_info=True)
        # Fallback: Send a new message if editing fails (e.g., message was deleted)
        await context.bot.send_message(
            chat_id=stored_chat_id,
            text=f"*{initiator_full_name}* vs *{opponent_full_name}*\n\n"
                 f"Game ID: `{game_id[:8]}...`\n"
                 f"Game has started! {initiator_full_name}, please choose Heads or Tails for the toss.\n"
                 f"_The previous game message might have been deleted. Continuing here._",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        # If a new message was sent, update the message_id in the game state for future interactions
        new_msg = await context.bot.send_message(chat_id=stored_chat_id, text="...") # Dummy to get new ID
        game_state['message_id'] = new_msg.message_id
        save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, game_state['message_id'], stored_chat_id)
        await new_msg.delete() # Delete dummy message

async def handle_toss_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    choice_type, choice_value, game_id = query.data.split('_')
    
    logger.info(f"Toss callback for Game ID: {game_id}, Choice: {choice_value} by user {query.effective_user.id}")

    game_data_tuple = get_game_data(game_id)
    if not game_data_tuple:
        logger.warning(f"Toss callback for non-existent game {game_id}.")
        await query.edit_message_text(f"This game (`{game_id[:8]}...`) has expired or was cancelled.", reply_markup=None)
        return
    
    _, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id, _ = game_data_tuple

    # Crucial check: Ensure the callback is for the correct message if multiple are in a chat
    if query.message.message_id != msg_id or query.message.chat_id != chat_id:
        logger.warning(f"Toss callback message_id/chat_id mismatch for game {game_id}. Query msg ID: {query.message.message_id}, Stored msg ID: {msg_id}. Query chat ID: {query.message.chat_id}, Stored chat ID: {chat_id}")
        await query.edit_message_text(query.message.text + "\n\nThis game message might be outdated. Please use the latest game message.", reply_markup=None)
        return

    current_player_id = query.effective_user.id
    
    if game_state['state'] == 'toss_heads_tails':
        if current_player_id != initiator_id:
            logger.info(f"User {current_player_id} tried to make toss choice for game {game_id}, but not initiator.")
            await query.edit_message_text(query.message.text + "\n\nOnly the initiator can choose Heads or Tails!", reply_markup=query.message.reply_markup)
            return

        toss_result = random.choice(["heads", "tails"])
        
        message_text = f"*{game_state['initiator_full_name']}* vs *{game_state['opponent_full_name']}*\n\n"
        message_text += f"Game ID: `{game_id[:8]}...`\n"
        message_text += f"{game_state['initiator_full_name']} chose: *{choice_value.capitalize()}*\n"
        message_text += f"The coin landed on: *{toss_result.capitalize()}*\n\n"

        if choice_value == toss_result:
            game_state['toss_winner_id'] = initiator_id
            toss_winner_name = game_state['initiator_full_name']
            message_text += f"*{toss_winner_name}* won the toss!"
        else:
            game_state['toss_winner_id'] = opponent_id
            toss_winner_name = game_state['opponent_full_name']
            message_text += f"*{toss_winner_name}* won the toss!"

        game_state['state'] = 'toss_bat_bowl'
        save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id)
        logger.info(f"Game {game_id} toss decided. Winner: {toss_winner_name}. State: {game_state['state']}")

        keyboard = [
            [InlineKeyboardButton("Bat 🏏", callback_data=f"choice_bat_{game_id}")],
            [InlineKeyboardButton("Bowl ⚾", callback_data=f"choice_bowl_{game_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.edit_message_text( # Use stored chat_id and message_id
                chat_id=chat_id,
                message_id=msg_id,
                text=message_text + f"\n\n*{toss_winner_name}*, what do you choose?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to edit message {msg_id} in chat {chat_id} for game {game_id} after toss: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_text + f"\n\n*{toss_winner_name}*, what do you choose? (Previous message may be deleted.)",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            # Update message_id if new message sent
            new_msg = await context.bot.send_message(chat_id=chat_id, text="...")
            game_state['message_id'] = new_msg.message_id
            save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, game_state['message_id'], chat_id)
            await new_msg.delete()


    elif game_state['state'] == 'toss_bat_bowl':
        if current_player_id != game_state['toss_winner_id']:
            logger.info(f"User {current_player_id} tried to make bat/bowl choice for game {game_id}, but not toss winner.")
            await query.edit_message_text(query.message.text + "\n\nOnly the toss winner can choose Bat or Bowl!", reply_markup=query.message.reply_markup)
            return
        
        toss_winner_name = get_user_data(game_state['toss_winner_id'])[2] # Full name
        
        if choice_value == 'bat':
            game_state['current_batter_id'] = game_state['toss_winner_id']
            game_state['current_bowler_id'] = initiator_id if game_state['toss_winner_id'] == opponent_id else opponent_id
            start_message = f"*{toss_winner_name}* elected to *Bat* first!"
        else: # choice_value == 'bowl'
            game_state['current_bowler_id'] = game_state['toss_winner_id']
            game_state['current_batter_id'] = initiator_id if game_state['toss_winner_id'] == opponent_id else opponent_id
            start_message = f"*{toss_winner_name}* elected to *Bowl* first!"
        
        game_state['state'] = 'batting_1st_innings'
        save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id)
        logger.info(f"Game {game_id} starting 1st innings. Batter: {get_user_data(game_state['current_batter_id'])[2]}, Bowler: {get_user_data(game_state['current_bowler_id'])[2]}. State: {game_state['state']}")

        # Prepare for the first innings - send updated message with options
        await send_batting_bowling_options(context, game_id, chat_id, msg_id)
    else:
        logger.warning(f"Toss callback received in unexpected state {game_state['state']} for game {game_id}.")
        await query.edit_message_text(query.message.text + "\n\nThis action is not allowed at this stage of the game.", reply_markup=query.message.reply_markup)
# Part 3: In-Game Logic (Batting and Bowling) (Consistent ID Usage)

# (Requires imports and helper functions from Part 1 & 2)
# Make sure Part 1 and Part 2's code is above this in your final script.

async def send_batting_bowling_options(context: CallbackContext, game_id: str, chat_id: int, message_id: int):
    # Retrieve the latest game data from the DB for accuracy
    game_data_tuple = get_game_data(game_id)
    if not game_data_tuple:
        logger.warning(f"Attempted to send options for non-existent game {game_id}.")
        return # Game expired or already finished

    _, initiator_id, opponent_id, bet_amount, game_state, stored_msg_id, stored_chat_id, _ = game_data_tuple

    # Ensure we use the correct message_id and chat_id from the stored game state for editing
    # This is CRUCIAL for multi-game scenarios and handling bot restarts.
    # If the provided message_id/chat_id don't match stored, it's a potential inconsistency, prefer stored.
    # We log this, but proceed with stored values for editing.
    if stored_msg_id != message_id or stored_chat_id != chat_id:
        logger.warning(f"send_batting_bowling_options: Mismatch in provided message_id/chat_id for game {game_id}. Using stored. Provided: msg={message_id}, chat={chat_id} | Stored: msg={stored_msg_id}, chat={stored_chat_id}")
        # Update current function's variables to use stored ones
        message_id = stored_msg_id
        chat_id = stored_chat_id

    batter_name = get_user_data(game_state['current_batter_id'])[2]
    bowler_name = get_user_data(game_state['current_bowler_id'])[2]

    keyboard = [
        [InlineKeyboardButton("1", callback_data=f"play_1_{game_id}"),
         InlineKeyboardButton("2", callback_data=f"play_2_{game_id}"),
         InlineKeyboardButton("3", callback_data=f"play_3_{game_id}")],
        [InlineKeyboardButton("4", callback_data=f"play_4_{game_id}"),
         InlineKeyboardButton("5", callback_data=f"play_5_{game_id}"),
         InlineKeyboardButton("6", callback_data=f"play_6_{game_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    innings_status = ""
    if game_state['state'] == 'batting_1st_innings':
        innings_status = f"🏏 Batter: *{batter_name}*\n⚾ Bowler: *{bowler_name}*\n\n"
        innings_status += f"Score: {game_state['first_innings_score']}/{game_state['first_innings_wickets']}"
    elif game_state['state'] == 'batting_2nd_innings':
        innings_status = f"🏏 Batter: *{batter_name}*\n⚾ Bowler: *{bowler_name}*\n\n"
        innings_status += f"Target: {game_state['target']}\n"
        innings_status += f"Score: {game_state['second_innings_score']}/{game_state['second_innings_wickets']}"

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, # Use the determined chat_id
            message_id=message_id, # Use the determined message_id
            text=f"*{game_state['initiator_full_name']}* vs *{game_state['opponent_full_name']}*\n\n"
                 f"Game ID: `{game_id[:8]}...`\n" # Added game ID for clarity
                 f"{innings_status}\n\n"
                 f"*{batter_name}*, choose your batting number. *{bowler_name}*, choose your bowling number.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.debug(f"Successfully edited message {message_id} in chat {chat_id} for game {game_id}.")
    except Exception as e:
        logger.error(f"Failed to edit message {message_id} in chat {chat_id} for game {game_id}: {e}", exc_info=True)
        # Fallback: Send a new message if editing fails (e.g., original message deleted by user or Telegram issue)
        sent_new_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"*{game_state['initiator_full_name']}* vs *{game_state['opponent_full_name']}*\n\n"
                 f"Game ID: `{game_id[:8]}...`\n"
                 f"{innings_status}\n\n"
                 f"*{batter_name}*, choose your batting number. *{bowler_name}*, choose your bowling number.\n"
                 f"_The previous game message might have been deleted. Continuing here._",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        # Update message_id in DB to the new message's ID for future interactions
        game_state['message_id'] = sent_new_message.message_id
        save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, game_state['message_id'], chat_id)
        logger.info(f"Sent new message for game {game_id} due to edit failure. New message ID: {sent_new_message.message_id}")


async def handle_play_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    _, player_choice_str, game_id = query.data.split('_')
    player_choice = int(player_choice_str)
    current_player_id = query.effective_user.id

    logger.info(f"Play callback for Game ID: {game_id}, Choice: {player_choice} by user {current_player_id}")

    game_data_tuple = get_game_data(game_id)
    if not game_data_tuple:
        logger.warning(f"Play callback for non-existent game {game_id}.")
        await query.edit_message_text(f"This game (`{game_id[:8]}...`) has expired or was cancelled.", reply_markup=None)
        return

    _, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id, _ = game_data_tuple # msg_id and chat_id are from stored game state

    # Crucial check: Ensure the callback is for the correct message if multiple are in a chat
    if query.message.message_id != msg_id or query.message.chat_id != chat_id:
        logger.warning(f"Play callback message_id/chat_id mismatch for game {game_id}. Query msg ID: {query.message.message_id}, Stored msg ID: {msg_id}. Query chat ID: {query.message.chat_id}, Stored chat ID: {chat_id}")
        await query.edit_message_text(query.message.text + "\n\nThis game message might be outdated. Please use the latest game message.", reply_markup=None)
        return

    # Ensure correct player is making the move
    if current_player_id not in [game_state['current_batter_id'], game_state['current_bowler_id']]:
        logger.info(f"User {current_player_id} tried to play in game {game_id}, but not current batter/bowler.")
        await query.edit_message_text(query.message.text + "\n\nIt's not your turn or you are not part of this game!", reply_markup=query.message.reply_markup)
        return

    # Check if a choice was already made for this 'turn' by the current player
    if game_state['last_player_choice'] and current_player_id == game_state['last_player_choice']['player_id']:
        logger.info(f"User {current_player_id} re-chose number {player_choice} for game {game_id}.")
        await context.bot.edit_message_text(
            chat_id=chat_id, # Use stored chat_id
            message_id=msg_id, # Use stored message_id
            text=query.message.text + "\n\nYou have already chosen a number for this turn. Waiting for opponent.",
            parse_mode='Markdown',
            reply_markup=query.message.reply_markup # Keep buttons for other player
        )
        return

    # Store the choice
    if not game_state['last_player_choice']:
        game_state['last_player_choice'] = {'player_id': current_player_id, 'choice': player_choice}
        
        # Notify the player their choice is recorded, waiting for opponent
        player_name = get_user_data(current_player_id)[2]
        # Determine opponent's name for the current turn based on roles
        if current_player_id == game_state['current_batter_id']: # current player is batter, waiting for bowler
            opponent_name = get_user_data(game_state['current_bowler_id'])[2]
        else: # current player is bowler, waiting for batter
            opponent_name = get_user_data(game_state['current_batter_id'])[2]
        
        try:
            await context.bot.edit_message_text( # Use stored chat_id and message_id
                chat_id=chat_id,
                message_id=msg_id,
                text=query.message.text + f"\n\n*{player_name}* has chosen a number. Waiting for *{opponent_name}* to choose.",
                parse_mode='Markdown',
                reply_markup=query.message.reply_markup # Keep buttons for other player
            )
            logger.debug(f"Player {current_player_id} chose {player_choice} for game {game_id}. Waiting for opponent.")
        except Exception as e:
            logger.error(f"Failed to edit message {msg_id} in chat {chat_id} after first player choice in game {game_id}: {e}", exc_info=True)
            # Fallback to sending new message if edit fails
            await context.bot.send_message(
                chat_id=chat_id,
                text=query.message.text + f"\n\n*{player_name}* has chosen a number. Waiting for *{opponent_name}* to choose.\n_Previous message might be deleted._",
                parse_mode='Markdown',
                reply_markup=query.message.reply_markup
            )
            # Update message_id if new message sent
            new_msg = await context.bot.send_message(chat_id=chat_id, text="...")
            game_state['message_id'] = new_msg.message_id
            await new_msg.delete()

        save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id) # Save updated state with choice
        return
    else:
        # Both players have chosen
        first_player_choice_info = game_state['last_player_choice']
        
        # Determine who chose what
        batter_choice = 0
        bowler_choice = 0
        
        if first_player_choice_info['player_id'] == game_state['current_batter_id']:
            batter_choice = first_player_choice_info['choice']
            bowler_choice = player_choice
        else:
            bowler_choice = first_player_choice_info['choice']
            batter_choice = player_choice

        batter_name = get_user_data(game_state['current_batter_id'])[2]
        bowler_name = get_user_data(game_state['current_bowler_id'])[2]

        game_summary_text = (
            f"*{game_state['initiator_full_name']}* vs *{game_state['opponent_full_name']}*\n"
            f"Game ID: `{game_id[:8]}...`\n\n" # Added game ID for clarity
            f"🏏 Batter : *{batter_name}*\n"
            f"⚾ Bowler : *{bowler_name}*\n\n"
            f"*{batter_name}* Bat {batter_choice}\n"
            f"*{bowler_name}* Bowl {bowler_choice}\n\n"
        )

        game_state['last_player_choice'] = None # Reset for next turn

        if batter_choice == bowler_choice:
            # OUT!
            if game_state['state'] == 'batting_1st_innings':
                game_state['first_innings_wickets'] += 1
                game_state['first_innings_runs'].append(f"{batter_choice} (OUT!)")
            else: # 2nd innings
                game_state['second_innings_wickets'] += 1
                game_state['second_innings_runs'].append(f"{batter_choice} (OUT!)")

            game_summary_text += "Total Score -\n\n"
            
            if game_state['state'] == 'batting_1st_innings':
                game_summary_text += f"*{bowler_name}* takes a wicket!\n"
                game_summary_text += f"First Innings Score: {game_state['first_innings_score']}/{game_state['first_innings_wickets']}\n\n"

                # Switch innings
                game_state['target'] = game_state['first_innings_score'] + 1
                game_state['state'] = 'batting_2nd_innings'
                
                # Swap batter and bowler
                temp_batter = game_state['current_batter_id']
                game_state['current_batter_id'] = game_state['current_bowler_id']
                game_state['current_bowler_id'] = temp_batter
                
                new_batter_name = get_user_data(game_state['current_batter_id'])[2]
                new_bowler_name = get_user_data(game_state['current_bowler_id'])[2]
                
                game_summary_text += f"*{new_bowler_name}* Sets a target of {game_state['target']}!\n\n"
                game_summary_text += f"*{new_batter_name}* will now Bat and *{new_bowler_name}* will now Bowl!"

                save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id)
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=game_summary_text, parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Failed to edit message {msg_id} for innings switch in game {game_id}: {e}", exc_info=True)
                await send_batting_bowling_options(context, game_id, chat_id, msg_id)

            else: # 2nd innings
                game_summary_text += f"*{bowler_name}* takes a wicket!\n"
                game_summary_text += f"Second Innings Score: {game_state['second_innings_score']}/{game_state['second_innings_wickets']} (Target: {game_state['target']})\n\n"

                # Game over in 2nd innings after an out
                winner_id = game_state['current_bowler_id']
                loser_id = game_state['current_batter_id']
                winner_name = get_user_data(winner_id)[2]
                
                game_summary_text += f"*{winner_name}* wins the match by defending the target!\n\n"
                game_state['state'] = 'finished'
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=game_summary_text, parse_mode='Markdown', reply_markup=None)
                except Exception as e:
                    logger.error(f"Failed to edit message {msg_id} for game end (out) in game {game_id}: {e}", exc_info=True)
                await end_game(context, game_id, winner_id, loser_id, bet_amount)

        else:
            # Not an out, add runs
            if game_state['state'] == 'batting_1st_innings':
                game_state['first_innings_score'] += batter_choice
                game_state['first_innings_runs'].append(str(batter_choice))
                current_score = game_state['first_innings_score']
                current_innings_runs = ", ".join(game_state['first_innings_runs'])
                game_summary_text += f"Total Score: {current_score}\n"
                game_summary_text += f"Run progression: [{current_innings_runs}]\n\n"
                game_summary_text += f"*{batter_name}* Scored total of {current_score} Runs!\n\n"
                game_summary_text += f"Next Move:\n*{batter_name}* Continue your Bat!"

                save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id)
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=game_summary_text, parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Failed to edit message {msg_id} for 1st innings run update in game {game_id}: {e}", exc_info=True)
                await send_batting_bowling_options(context, game_id, chat_id, msg_id)

            else: # 2nd innings
                game_state['second_innings_score'] += batter_choice
                game_state['second_innings_runs'].append(str(batter_choice))
                current_score = game_state['second_innings_score']
                current_innings_runs = ", ".join(game_state['second_innings_runs'])
                game_summary_text += f"Total Score: {current_score} (Target: {game_state['target']})\n"
                game_summary_text += f"Run progression: [{current_innings_runs}]\n\n"

                if current_score >= game_state['target']:
                    # Target achieved, batter wins
                    winner_id = game_state['current_batter_id']
                    loser_id = game_state['current_bowler_id']
                    winner_name = get_user_data(winner_id)[2]
                    
                    game_summary_text += f"*{winner_name}* Scored total of {current_score} Runs!\n\n"
                    game_summary_text += f"*{winner_name}* wins the match by chasing the target!\n\n"
                    game_state['state'] = 'finished'
                    try:
                        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=game_summary_text, parse_mode='Markdown', reply_markup=None)
                    except Exception as e:
                        logger.error(f"Failed to edit message {msg_id} for game end (target met) in game {game_id}: {e}", exc_info=True)
                    await end_game(context, game_id, winner_id, loser_id, bet_amount)
                else:
                    game_summary_text += f"*{batter_name}* Scored total of {current_score} Runs!\n\n"
                    game_summary_text += f"Next Move:\n*{batter_name}* Continue your Bat!"
                    
                    save_game_state(game_id, initiator_id, opponent_id, bet_amount, game_state, msg_id, chat_id)
                    try:
                        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=game_summary_text, parse_mode='Markdown')
                    except Exception as e:
                        logger.error(f"Failed to edit message {msg_id} for 2nd innings run update in game {game_id}: {e}", exc_info=True)
                    await send_batting_bowling_options(context, game_id, chat_id, msg_id)

async def end_game(context: CallbackContext, game_id: str, winner_id: int, loser_id: int, bet_amount: int):
    # Update user stats
    update_user_stats(winner_id, win=True)
    update_user_stats(loser_id, loss=True)

    # Handle bet amounts
    if bet_amount > 0:
        update_user_purse(winner_id, bet_amount * 2) # Winner gets double the bet back
        # Loser already had their bet deducted at the start

        winner_name = get_user_data(winner_id)[2]
        loser_name = get_user_data(loser_id)[2]
        try:
            await context.bot.send_message(chat_id=winner_id, text=f"🎉 You won {bet_amount*2}{COIN_EMOJI} from the match against {loser_name} (Game ID: `{game_id[:8]}...`)!")
            await context.bot.send_message(chat_id=loser_id, text=f"😔 You lost {bet_amount}{COIN_EMOJI} in the match against {winner_name} (Game ID: `{game_id[:8]}...`)!")
        except Exception as e:
            logger.warning(f"Could not send private game end message for game {game_id} to user {winner_id} or {loser_id}: {e}")

    # Clean up game state
    delete_game_state(game_id)
    logger.info(f"Game {game_id} finished. Winner: {winner_id}, Loser: {loser_id}. Bet: {bet_amount}. State deleted from DB.")
# Part 4: Leaderboard, Admin Commands, and Main Function (Minor Log Refinement)

# (Requires imports and helper functions from Part 1, 2 & 3)
# Make sure Part 1, 2 and 3's code is above this in your final script.

# --- Leaderboard ---
async def leaderboard_command(update: Update, context: CallbackContext) -> None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Default to coins leaderboard
    cursor.execute("SELECT full_name, purse FROM users ORDER BY purse DESC LIMIT 10")
    top_by_coins = cursor.fetchall()
    
    conn.close()

    message_text = "*🏆 Top 10 Richest Players (by Coins) 🏆*\n\n"
    if not top_by_coins:
        message_text += "No players registered yet!"
    else:
        for i, (name, purse) in enumerate(top_by_coins):
            message_text += f"{i+1}. {name}: {purse}{COIN_EMOJI}\n"

    keyboard = [
        [InlineKeyboardButton("Leaderboard by Wins ▶️", callback_data="leaderboard_wins_0")] # 0 is placeholder for page
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_leaderboard_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    _, lb_type, page = query.data.split('_') # page is unused for now, but good for future expansion
    page = int(page) # Convert to int

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    message_text = ""
    keyboard_buttons = []

    if lb_type == 'wins':
        cursor.execute("SELECT full_name, wins FROM users ORDER BY wins DESC LIMIT 10")
        top_by_wins = cursor.fetchall()
        message_text = "*🏆 Top 10 Players (by Wins) 🏆*\n\n"
        if not top_by_wins:
            message_text += "No players with wins yet!"
        else:
            for i, (name, wins) in enumerate(top_by_wins):
                message_text += f"{i+1}. {name}: {wins} Wins\n"
        keyboard_buttons.append(InlineKeyboardButton("◀️ Leaderboard by Coins", callback_data="leaderboard_coins_0"))
    else: # lb_type == 'coins'
        cursor.execute("SELECT full_name, purse FROM users ORDER BY purse DESC LIMIT 10")
        top_by_coins = cursor.fetchall()
        message_text = "*🏆 Top 10 Richest Players (by Coins) 🏆*\n\n"
        if not top_by_coins:
            message_text += "No players registered yet!"
        else:
            for i, (name, purse) in enumerate(top_by_coins):
                message_text += f"{i+1}. {name}: {purse}{COIN_EMOJI}\n"
        keyboard_buttons.append(InlineKeyboardButton("Leaderboard by Wins ▶️", callback_data="leaderboard_wins_0"))
    
    conn.close()

    reply_markup = InlineKeyboardMarkup([keyboard_buttons])

    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- Admin Command ---
async def add_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/add <user_id> <amount>`", parse_mode='Markdown')
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])

        target_user_data = get_user_data(target_user_id)
        if not target_user_data:
            await update.message.reply_text(f"User with ID `{target_user_id}` not found.", parse_mode='Markdown')
            return

        update_user_purse(target_user_id, amount)
        target_user_name = target_user_data[2]
        await update.message.reply_text(
            f"Successfully added {amount}{COIN_EMOJI} to *{target_user_name}* (ID: `{target_user_id}`).\n"
            f"New balance: {get_user_data(target_user_id)[3]}{COIN_EMOJI}.",
            parse_mode='Markdown'
        )
        # Notify the user if possible
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"💰 An admin has added {amount}{COIN_EMOJI} to your purse! Your new balance is {get_user_data(target_user_id)[3]}{COIN_EMOJI}.")
        except Exception as e:
            logger.warning(f"Could not notify user {target_user_id} about added coins: {e}")

    except ValueError:
        await update.message.reply_text("Invalid user ID or amount. Please use numbers only.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

# --- Error Handler (Optional but Recommended) ---
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update.callback_query:
        # Try to answer the callback query to remove the "loading" spinner on the button
        try:
            await update.callback_query.answer("An error occurred. Please try again or contact support.")
        except Exception as e:
            logger.warning(f"Failed to answer callback query in error_handler: {e}")
    elif update.message:
        await update.message.reply_text("Oops! Something went wrong. Please try again.")

# --- Main Function ---
def main() -> None:
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("daily", daily_command))
    application.add_handler(CommandHandler("pm", pm_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("add", add_command)) # Admin command
    application.add_handler(CommandHandler("help", help_command))

    # --- Callback Query Handlers ---
    application.add_handler(CallbackQueryHandler(handle_join_game_callback, pattern=r"^join_game_"))
    application.add_handler(CallbackQueryHandler(handle_toss_callback, pattern=r"^(toss_|choice_)"))
    application.add_handler(CallbackQueryHandler(handle_play_callback, pattern=r"^play_"))
    application.add_handler(CallbackQueryHandler(handle_leaderboard_callback, pattern=r"^leaderboard_"))

    # --- Error Handler ---
    application.add_error_handler(error_handler)

    logger.info("Bot started polling.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
