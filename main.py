import logging
import json
import os
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # !! REPLACE WITH YOUR ACTUAL BOT TOKEN !!
ADMIN_IDS = [123456789, 987654321]  # !! REPLACE WITH YOUR TELEGRAM USER ID(s) for admin access !!
DATA_FILE = "user_data.json" # File to store user coin/win/loss data

# --- Game Constants ---
REGISTER_REWARD = 4000
DAILY_REWARD = 2000
DAILY_COOLDOWN = 24 * 60 * 60  # 24 hours in seconds
MAX_LEADERBOARD_ENTRIES = 10

# --- Global Data Stores ---
# Stores user data: {user_id: {"name": str, "coins": int, "wins": int, "losses": int, "last_daily_claim": float}}
users = {}
# Stores ongoing match data: {message_id: {match_state_dict}}
# message_id is used as key because all game interactions for a match happen on one message.
active_matches = {}

# --- Utility Functions ---
def load_data():
    """Loads user data from a JSON file."""
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                data = json.load(f)
                users = {int(k): v for k, v in data.items()}  # Ensure keys are int
                logger.info("User data loaded successfully.")
            except json.JSONDecodeError:
                logger.warning("Error decoding JSON from data file. Starting with empty data.")
                users = {}
    else:
        logger.info("Data file not found. Starting with empty data.")

def save_data():
    """Saves user data to a JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=4)
    logger.info("User data saved successfully.")

def get_user_data(user_id: int, user_name: str) -> dict:
    """Retrieves or creates user data."""
    if user_id not in users:
        users[user_id] = {
            "name": user_name,
            "coins": 0,
            "wins": 0,
            "losses": 0,
            "last_daily_claim": 0.0, # Unix timestamp of last claim
        }
        save_data()
    return users[user_id]

# --- Inline Keyboard Button Helpers ---
def get_match_buttons() -> InlineKeyboardMarkup:
    """Returns inline keyboard for choosing numbers 1-6."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="play_1"), InlineKeyboardButton("2", callback_data="play_2"), InlineKeyboardButton("3", callback_data="play_3")],
        [InlineKeyboardButton("4", callback_data="play_4"), InlineKeyboardButton("5", callback_data="play_5"), InlineKeyboardButton("6", callback_data="play_6")]
    ])

def get_toss_buttons() -> InlineKeyboardMarkup:
    """Returns inline keyboard for Heads/Tails toss choice."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Heads", callback_data="toss_heads"), InlineKeyboardButton("Tails", callback_data="toss_tails")]
    ])

def get_bat_bowl_buttons() -> InlineKeyboardMarkup:
    """Returns inline keyboard for Bat/Bowl choice."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Bat 🏏", callback_data="choice_bat"), InlineKeyboardButton("Bowl ⚾", callback_data="choice_bowl")]
    ])

def get_join_button(initiator_name: str) -> InlineKeyboardMarkup:
    """Returns inline keyboard for joining a match."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Join below to play with {initiator_name}", callback_data="join_match")]
    ])

async def update_game_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, text: str, reply_markup: InlineKeyboardMarkup = None):
    """Edits an existing Telegram message with new text and/or reply markup."""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown" # Enable Markdown formatting
        )
    except Exception as e:
        logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")
        # If message cannot be edited (e.g., too old or deleted), clear match state
        if message_id in active_matches:
            del active_matches[message_id]
        logger.info(f"Cleared match state for message {message_id} due to edit error.")
# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    get_user_data(user.id, user.full_name) # Ensure user is registered or loaded
    await update.message.reply_text(
        f"👋 Hello, {user.full_name}! Welcome to CCG HandCricket Bot!\n\n"
        "I'm here to help you play thrilling hand cricket matches with your friends.\n\n"
        "Use `/help` to see all available commands."
    )

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registers a user and gives a reward if they haven't received it yet."""
    user = update.effective_user
    user_data = get_user_data(user.id, user.full_name) # Ensures user entry exists

    if user_data["coins"] >= REGISTER_REWARD:
        await update.message.reply_text(
            f"You are already registered, {user.full_name}! You've already received your registration reward."
        )
    else:
        user_data["coins"] += REGISTER_REWARD
        save_data()
        await update.message.reply_text(
            f"🎉 Congratulations, {user.full_name}! You have successfully registered and received {REGISTER_REWARD}🪙 coins!"
        )

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's profile information."""
    user = update.effective_user
    user_data = get_user_data(user.id, user.full_name)

    profile_text = (
        f"*{user_data['name']}'s Profile*\n\n"
        f"Name : {user_data['name']}\n"
        f"ID : `{user.id}`\n" # Use backticks for monospace ID
        f"Purse : {user_data['coins']}🪙\n\n"
        f"*Performance History*\n"
        f"Wins : {user_data['wins']}\n"
        f"Loss : {user_data['losses']}"
    )
    await update.message.reply_text(profile_text, parse_mode="Markdown")

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows users to claim a daily coin bonus with a 24-hour cooldown."""
    user = update.effective_user
    user_data = get_user_data(user.id, user.full_name)
    current_time = time.time()

    if current_time - user_data["last_daily_claim"] >= DAILY_COOLDOWN:
        user_data["coins"] += DAILY_REWARD
        user_data["last_daily_claim"] = current_time
        save_data()
        await update.message.reply_text(
            f"💰 You received your daily bonus of {DAILY_REWARD}🪙 coins! Come back in 24 hours for more."
        )
    else:
        time_left = DAILY_COOLDOWN - (current_time - user_data["last_daily_claim"])
        hours, remainder = divmod(time_left, 3600)
        minutes, seconds = divmod(remainder, 60)
        await update.message.reply_text(
            f"⏳ You can claim your daily bonus again in {int(hours)}h {int(minutes)}m {int(seconds)}s."
        )

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates a private hand cricket match, optionally with a bet."""
    initiator = update.effective_user
    initiator_data = get_user_data(initiator.id, initiator.full_name)
    bet_amount = 0

    if context.args:
        try:
            bet_amount = int(context.args[0])
            if bet_amount <= 0:
                await update.message.reply_text("Bet amount must be a positive number.")
                return
            if initiator_data["coins"] < bet_amount:
                await update.message.reply_text(f"You don't have enough coins for a bet of {bet_amount}🪙. Your current balance: {initiator_data['coins']}🪙.")
                return
        except ValueError:
            await update.message.reply_text("Invalid bet amount. Please provide a number, e.g., `/pm 1000`.")
            return

    # Check if initiator is already in an active game
    for match_id_key, match_state_val in active_matches.items():
        if (match_state_val["initiator_id"] == initiator.id or match_state_val["opponent_id"] == initiator.id) and \
           match_state_val["status"] != "game_over":
            await update.message.reply_text("You are already in an active game. Please finish it before starting a new one.")
            return

    # Create a new match state
    game_message = await update.message.reply_text(
        f"Cricket game has been started!\n\nPress Join below to play with {initiator.full_name}",
        reply_markup=get_join_button(initiator.full_name)
    )

    match_id = game_message.message_id
    active_matches[match_id] = {
        "initiator_id": initiator.id,
        "opponent_id": None,
        "bet_amount": bet_amount,
        "status": "pending_join", # pending_join, toss, bat_bowl_choice, batting, innings_break, game_over
        "message_id": match_id,
        "chat_id": update.effective_chat.id,
        "toss_winner_id": None,
        "toss_choice": None,
        "toss_result": None,
        "chosen_to": None, # "bat" or "bowl"
        "current_batsman_id": None,
        "current_bowler_id": None,
        "batsman_score": 0,
        "current_ball": 0, # Total balls bowled in current innings
        "target": 0, # For second innings
        "innings": 1, # 1 or 2
        "p1_last_choice": None, # Player 1 (batsman's) last chosen number
        "p2_last_choice": None, # Player 2 (bowler's) last chosen number
        "p1_name": initiator.full_name,
        "p2_name": None, # Will be set when opponent joins
    }
    logger.info(f"Match {match_id} initiated by {initiator.full_name} with bet {bet_amount}.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays a list of available commands and their descriptions."""
    help_text = (
        "*CCG HandCricket Bot Commands:*\n\n"
        "🏏 `/start` - Get a welcome message from the bot.\n"
        "📝 `/register` - Register yourself and receive a starting bonus of 4000🪙 coins!\n"
        "🤝 `/pm` - Start a private hand cricket match. The bot will prompt for an opponent to join.\n"
        "🤝 `/pm <amount>` - Start a private hand cricket match with a bet. Winner takes double the bet!\n"
        "📊 `/profile` - View your personal stats, including coins, wins, and losses.\n"
        "💰 `/daily` - Claim your daily coin bonus (available every 24 hours).\n"
        "🏆 `/leaderboard` - See the top players by coins and wins."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- Callback Query Handlers (for Inline Keyboard buttons) ---

async def handle_join_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Join' button press for a match."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press
    opponent = query.from_user
    message_id = query.message.message_id
    match_state = active_matches.get(message_id)

    if not match_state:
        await query.edit_message_text("This game has expired or was cancelled.", reply_markup=None)
        logger.info(f"Join attempt for expired match {message_id} by {opponent.full_name}.")
        return

    if match_state["initiator_id"] == opponent.id:
        await query.answer("You cannot join your own match!", show_alert=True)
        return

    if match_state["opponent_id"] is not None:
        await query.answer("This match already has an opponent!", show_alert=True)
        return

    # Check if opponent has enough coins if there's a bet
    if match_state["bet_amount"] > 0:
        opponent_data = get_user_data(opponent.id, opponent.full_name)
        if opponent_data["coins"] < match_state["bet_amount"]:
            await query.answer(f"You don't have enough coins ({match_state['bet_amount']}🪙) to join this bet match!", show_alert=True)
            return

    match_state["opponent_id"] = opponent.id
    match_state["p2_name"] = opponent.full_name
    match_state["status"] = "toss" # Move to toss phase
    logger.info(f"Opponent {opponent.full_name} joined match {message_id}.")

    initiator_name = users[match_state["initiator_id"]]["name"]
    opponent_name = users[match_state["opponent_id"]]["name"]

    await update_game_message(
        context,
        match_state["chat_id"],
        match_state["message_id"],
        f"🏏 Match between *{initiator_name}* and *{opponent_name}*\n\n"
        f"*{initiator_name}*, please choose Heads or Tails for the toss.",
        reply_markup=get_toss_buttons()
    )


async def handle_toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the Heads/Tails choice during the toss."""
    query = update.callback_query
    await query.answer()
    player_id = query.from_user.id
    message_id = query.message.message_id
    match_state = active_matches.get(message_id)

    if not match_state or match_state["status"] != "toss":
        await query.answer("This action is not available right now.", show_alert=True)
        return

    if player_id != match_state["initiator_id"]:
        await query.answer("Only the match initiator can choose for the toss.", show_alert=True)
        return

    chosen = query.data.split('_')[1] # "heads" or "tails"
    match_state["toss_choice"] = chosen
    toss_result = random.choice(["heads", "tails"])
    match_state["toss_result"] = toss_result

    initiator_name = users[match_state["initiator_id"]]["name"]
    opponent_name = users[match_state["opponent_id"]]["name"]

    if chosen == toss_result:
        match_state["toss_winner_id"] = player_id
        winner_name = initiator_name
        loser_name = opponent_name
        toss_message = f"*{winner_name}* called *{chosen.capitalize()}* and it's *{toss_result.capitalize()}*! *{winner_name}* wins the toss."
    else:
        match_state["toss_winner_id"] = match_state["opponent_id"]
        winner_name = opponent_name
        loser_name = initiator_name
        toss_message = f"*{initiator_name}* called *{chosen.capitalize()}* but it's *{toss_result.capitalize()}*! *{winner_name}* wins the toss."

    match_state["status"] = "bat_bowl_choice" # Move to bat/bowl choice phase
    logger.info(f"Toss in match {message_id}: {winner_name} won.")

    await update_game_message(
        context,
        match_state["chat_id"],
        match_state["message_id"],
        f"🏏 Match between *{initiator_name}* and *{opponent_name}*\n\n"
        f"{toss_message}\n\n"
        f"*{winner_name}*, what do you choose?",
        reply_markup=get_bat_bowl_buttons()
    )


async def handle_bat_bowl_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the Bat/Bowl choice after winning the toss."""
    query = update.callback_query
    await query.answer()
    player_id = query.from_user.id
    message_id = query.message.message_id
    match_state = active_matches.get(message_id)

    if not match_state or match_state["status"] != "bat_bowl_choice":
        await query.answer("This action is not available right now.", show_alert=True)
        return

    if player_id != match_state["toss_winner_id"]:
        await query.answer("Only the toss winner can make this choice.", show_alert=True)
        return

    choice = query.data.split('_')[1] # "bat" or "bowl"
    match_state["chosen_to"] = choice
    match_state["status"] = "batting" # Game starts

    initiator_name = users[match_state["initiator_id"]]["name"]
    opponent_name = users[match_state["opponent_id"]]["name"]

    if choice == "bat":
        match_state["current_batsman_id"] = player_id
        match_state["current_bowler_id"] = match_state["opponent_id"] if player_id == match_state["initiator_id"] else match_state["initiator_id"]
    else: # choice == "bowl"
        match_state["current_bowler_id"] = player_id
        match_state["current_batsman_id"] = match_state["opponent_id"] if player_id == match_state["initiator_id"] else match_state["initiator_id"]

    batsman_name = users[match_state["current_batsman_id"]]["name"]
    bowler_name = users[match_state["current_bowler_id"]]["name"]

    logger.info(f"Match {message_id}: {batsman_name} elected to {choice} first.")

    await update_game_message(
        context,
        match_state["chat_id"],
        match_state["message_id"],
        f"🏏 Match between *{initiator_name}* and *{opponent_name}*\n\n"
        f"*{users[match_state['toss_winner_id']]['name']}* elected to *{choice}* first.\n\n"
        f"*{batsman_name}* is now batting, *{bowler_name}* is bowling.\n\n"
        f"*{batsman_name}*, please choose your number (1-6).",
        reply_markup=get_match_buttons()
    )
async def handle_play_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles number choice during batting/bowling turns."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press
    player_id = query.from_user.id
    message_id = query.message.message_id
    match_state = active_matches.get(message_id)

    if not match_state or match_state["status"] not in ["batting", "innings_break"]:
        await query.answer("This action is not available right now.", show_alert=True)
        return

    chosen_number = int(query.data.split('_')[1])
    
    batsman_id = match_state["current_batsman_id"]
    bowler_id = match_state["current_bowler_id"]
    batsman_name = users[batsman_id]["name"]
    bowler_name = users[bowler_id]["name"]

    # Store the chosen number in the correct player's slot
    if player_id == batsman_id:
        if match_state["p1_last_choice"] is not None: # Player already played their number for this ball
            await query.answer("You already played your number for this turn.", show_alert=True)
            return
        match_state["p1_last_choice"] = chosen_number # Store batsman's choice
        await query.answer("You chose your number. Waiting for opponent...")
    elif player_id == bowler_id:
        if match_state["p2_last_choice"] is not None: # Player already played their number for this ball
            await query.answer("You already played your number for this turn.", show_alert=True)
            return
        match_state["p2_last_choice"] = chosen_number # Store bowler's choice
        await query.answer("You chose your number. Waiting for opponent...")
    else:
        await query.answer("You are not part of this match.", show_alert=True)
        return

    # If both players have made their move, process the ball
    if match_state["p1_last_choice"] is not None and match_state["p2_last_choice"] is not None:
        await process_ball(context, message_id)
    else:
        # One player has chosen, update message to show whose turn it is
        if player_id == batsman_id: # Batsman played, waiting for bowler
            await update_game_message(
                context,
                match_state["chat_id"],
                match_state["message_id"],
                f"🏏 Batter : *{batsman_name}*\n⚾ Bowler : *{bowler_name}*\n\n"
                f"*{batsman_name}* chosen the number, now *{bowler_name}*'s turn.",
                reply_markup=get_match_buttons()
            )
        elif player_id == bowler_id: # Bowler played, waiting for batsman
             await update_game_message(
                context,
                match_state["chat_id"],
                match_state["message_id"],
                f"🏏 Batter : *{batsman_name}*\n⚾ Bowler : *{bowler_name}*\n\n"
                f"*{bowler_name}* chosen the number, now *{batsman_name}*'s turn.",
                reply_markup=get_match_buttons()
            )


async def process_ball(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Processes the outcome of a single ball (after both players choose numbers)."""
    match_state = active_matches[message_id]

    batsman_id = match_state["current_batsman_id"]
    bowler_id = match_state["current_bowler_id"]
    batsman_name = users[batsman_id]["name"]
    bowler_name = users[bowler_id]["name"]

    batsman_choice = match_state["p1_last_choice"]
    bowler_choice = match_state["p2_last_choice"]

    match_state["current_ball"] += 1 # Increment total balls bowled in this innings
    
    # Calculate overs display (e.g., 0.1, 0.2, ..., 0.6, 1.0, 1.1)
    overs_completed = (match_state['current_ball'] - 1) // 6
    balls_in_current_over = (match_state['current_ball'] - 1) % 6 + 1
    over_display = f"{overs_completed}.{balls_in_current_over}"

    game_text = (
        f"Over : {over_display}\n\n"
        f"🏏 Batter : *{batsman_name}*\n"
        f"⚾ Bowler : *{bowler_name}*\n\n"
        f"*{batsman_name}* Bat {batsman_choice}\n"
        f"*{bowler_name}* Bowl {bowler_choice}\n\n"
    )

    is_out = (batsman_choice == bowler_choice)

    if is_out:
        game_text += f"*{batsman_name}* is OUT! 💥\n"
        if match_state["innings"] == 1:
            match_state["target"] = match_state["batsman_score"] + 1 # Target is current score + 1
            game_text += f"Total Score - {match_state['batsman_score']} Runs\n"
            game_text += f"*{bowler_name}* Sets a target of {match_state['target']}!\n\n"
            game_text += f"*{bowler_name}* will now Bat and *{batsman_name}* will now Bowl!"
            
            # Swap roles for second innings
            match_state["current_batsman_id"], match_state["current_bowler_id"] = \
                match_state["current_bowler_id"], match_state["current_batsman_id"]
            match_state["batsman_score"] = 0 # Reset score for second innings
            match_state["current_ball"] = 0 # Reset ball count for second innings
            match_state["innings"] = 2
            match_state["status"] = "batting" # Ready for second innings

            await update_game_message(
                context,
                match_state["chat_id"],
                match_state["message_id"],
                game_text,
                reply_markup=get_match_buttons()
            )

        elif match_state["innings"] == 2:
            # Second innings, check if target was met before getting out
            final_batsman_score = match_state["batsman_score"]
            winner_id = None
            loser_id = None
            
            if final_batsman_score >= match_state["target"]:
                winner_id = batsman_id
                loser_id = bowler_id
                game_text += f"Total Score : {final_batsman_score} Runs\n"
                game_text += f"*{users[winner_id]['name']}* wins by completing the target! 🎉"
            else:
                winner_id = bowler_id
                loser_id = batsman_id
                game_text += f"Total Score : {final_batsman_score} Runs\n"
                game_text += f"*{users[winner_id]['name']}* wins by {match_state['target'] - 1 - final_batsman_score} runs! 🎉"
            
            await finish_match(context, message_id, winner_id, loser_id, match_state["bet_amount"], final_game_text=game_text)
            return # Exit to prevent further game loop

    else: # Not OUT, add runs to batsman's score
        match_state["batsman_score"] += batsman_choice
        game_text += f"Total Score : {match_state['batsman_score']} Runs\n\n"

        if match_state["innings"] == 2 and match_state["batsman_score"] >= match_state["target"]:
            # Batsman wins by reaching target
            winner_id = batsman_id
            loser_id = bowler_id
            game_text += f"*{users[winner_id]['name']}* wins by completing the target! 🎉"
            await finish_match(context, message_id, winner_id, loser_id, match_state["bet_amount"], final_game_text=game_text)
            return # Exit to prevent further game loop

        game_text += f"Next Move:\n*{batsman_name}* Continue your Bat!"
        
        await update_game_message(
            context,
            match_state["chat_id"],
            match_state["message_id"],
            game_text,
            reply_markup=get_match_buttons()
        )
    
    # Reset choices for next ball regardless of outcome (unless game finished)
    match_state["p1_last_choice"] = None
    match_state["p2_last_choice"] = None


async def finish_match(context: ContextTypes.DEFAULT_TYPE, message_id: int, winner_id: int, loser_id: int, bet_amount: int, final_game_text: str = None):
    """Handles updating scores, distributing bets, and ending a match."""
    match_state = active_matches[message_id]
    
    winner_data = get_user_data(winner_id, users.get(winner_id, {}).get('name', 'Unknown'))
    loser_data = get_user_data(loser_id, users.get(loser_id, {}).get('name', 'Unknown'))

    winner_data["wins"] += 1
    loser_data["losses"] += 1

    if bet_amount > 0:
        winner_data["coins"] += bet_amount * 2 # Winner gets double the bet
        loser_data["coins"] -= bet_amount # Loser loses the bet
        # Ensure loser's coins don't go below zero
        if loser_data["coins"] < 0:
            loser_data["coins"] = 0 # Cannot have negative coins

        await context.bot.send_message(
            chat_id=match_state["chat_id"],
            text=f"💸 *Bet Result:*\n*{users[winner_id]['name']}* won {bet_amount*2}🪙!\n*{users[loser_id]['name']}* lost {bet_amount}🪙.",
            parse_mode="Markdown"
        )

    save_data()
    
    # Update the game message to show final score and winner, then remove buttons
    # Use the pre-formatted text if provided (e.g., from an out condition that ends the game)
    # Otherwise, generate a generic final message.
    if not final_game_text:
        final_game_text = (
            f"🏏 Match between *{match_state['p1_name']}* and *{match_state['p2_name']}*\n\n"
            f"Final Score : {match_state['batsman_score']} Runs\n"
            f"Target : {match_state['target'] if match_state['target'] > 0 else 'N/A'}\n\n"
            f"🎉 *{users[winner_id]['name']}* wins the match!\n"
            f"Good game, everyone!"
        )
    
    await update_game_message(
        context,
        match_state["chat_id"],
        message_id,
        final_game_text,
        reply_markup=None # Remove all buttons
    )
    
    match_state["status"] = "game_over" # Mark match as finished


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the leaderboard by coins or wins, with interactive buttons."""
    message = update.message if update.message else update.callback_query.message
    query_data = update.callback_query.data if update.callback_query else None

    # Determine leaderboard type based on callback query data or default
    if query_data == "lb_by_wins":
        lb_type = "wins"
    elif query_data == "lb_by_coins":
        lb_type = "coins"
    else: # Default or initial call
        lb_type = "coins"
    
    sorted_users_list = []
    if lb_type == "coins":
        # Sort by coins in descending order
        sorted_users_list = sorted(users.items(), key=lambda item: item[1]["coins"], reverse=True)
    else: # "wins"
        # Sort by wins in descending order
        sorted_users_list = sorted(users.items(), key=lambda item: item[1]["wins"], reverse=True)

    leaderboard_text = f"*{'💰 Richest Players' if lb_type == 'coins' else '🏆 Most Wins'} Leaderboard*\n\n"
    if not sorted_users_list:
        leaderboard_text += "No players registered yet!"
    else:
        for i, (user_id, data) in enumerate(sorted_users_list[:MAX_LEADERBOARD_ENTRIES]):
            leaderboard_text += f"{i+1}. {data['name']} - {'🪙' + str(data['coins']) if lb_type == 'coins' else '🏆' + str(data['wins'])}\n"

    # Create buttons to switch leaderboard view
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ By Coins" if lb_type == "wins" else "By Coins", callback_data="lb_by_coins"),
         InlineKeyboardButton("By Wins" if lb_type == "coins" else "➡️ By Wins", callback_data="lb_by_wins")]
    ])

    if update.callback_query:
        # If it's a callback, edit the existing message
        await update_game_message(context, message.chat.id, message.message_id, leaderboard_text, reply_markup=keyboard)
    else:
        # If it's a command, send a new message
        await message.reply_text(leaderboard_text, reply_markup=keyboard, parse_mode="Markdown")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only command to add coins to a user."""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/add <user_id> <amount>`")
        return

    try:
        target_user_id = int(context.args[0])
        amount_to_add = int(context.args[1])
        if amount_to_add <= 0:
            await update.message.reply_text("Amount must be positive.")
            return

        if target_user_id not in users:
            await update.message.reply_text(f"User with ID `{target_user_id}` not found in database. They must interact with the bot first (e.g., via /start or /register).")
            return

        users[target_user_id]["coins"] += amount_to_add
        save_data()
        await update.message.reply_text(
            f"Successfully added {amount_to_add}🪙 to user `{target_user_id}` ({users[target_user_id]['name']}). "
            f"New balance: {users[target_user_id]['coins']}🪙."
        )
    except ValueError:
        await update.message.reply_text("Invalid user ID or amount. Please provide numbers.")
    except Exception as e:
        logger.error(f"Error in add_command: {e}")
        await update.message.reply_text(f"An error occurred: {e}")


async def main() -> None:
    """Starts the bot."""
    load_data() # Load user data when the bot starts
    application = Application.builder().token(TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("daily", daily_command))
    application.add_handler(CommandHandler("pm", pm_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("add", add_command)) # Admin-only command

    # Register callback query handlers for inline keyboard button presses
    application.add_handler(CallbackQueryHandler(handle_join_match, pattern="^join_match$"))
    application.add_handler(CallbackQueryHandler(handle_toss_choice, pattern="^toss_"))
    application.add_handler(CallbackQueryHandler(handle_bat_bowl_choice, pattern="^choice_"))
    application.add_handler(CallbackQueryHandler(handle_play_number, pattern="^play_"))
    application.add_handler(CallbackQueryHandler(leaderboard_command, pattern="^lb_")) # For leaderboard buttons

    # Run the bot
    logger.info("CCG HandCricket Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
    
