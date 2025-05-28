import os
import random
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    Filters,
)

# Configuration - Replace these values
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = [123456789]  # Replace with your admin user IDs
DATABASE_NAME = "handcricket.db"

# Constants
REGISTER_REWARD = 4000
DAILY_REWARD = 2000
EMOJI_COIN = "🪙"
EMOJI_BAT = "🏏"
EMOJI_BALL = "⚾"

# Database setup
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            coins INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            last_daily TEXT,
            registered_at TEXT
        )
    ''')
    
    # Matches table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            initiator_id INTEGER,
            opponent_id INTEGER,
            bet_amount INTEGER DEFAULT 0,
            toss_winner INTEGER,
            batting_first INTEGER,
            innings1_score INTEGER DEFAULT 0,
            innings2_score INTEGER DEFAULT 0,
            current_batsman_id INTEGER,
            current_bowler_id INTEGER,
            game_state TEXT,
            message_id INTEGER,
            chat_id INTEGER,
            created_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# User management functions
def register_user(user_id: int, username: str, first_name: str, last_name: str):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users 
        (user_id, username, first_name, last_name, coins, registered_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, REGISTER_REWARD, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2],
            'last_name': row[3],
            'coins': row[4],
            'wins': row[5],
            'losses': row[6],
            'last_daily': row[7],
            'registered_at': row[8]
        }
    return None

def update_user_coins(user_id: int, amount: int):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('UPDATE users SET coins = coins + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def update_user_stats(user_id: int, won: bool):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    if won:
        cursor.execute('UPDATE users SET wins = wins + 1 WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('UPDATE users SET losses = losses + 1 WHERE user_id = ?', (user_id,))
    
    conn.commit()
    conn.close()

# Command handlers
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    welcome_message = (
        f"👋 Welcome to CCG HandCricket, {user.first_name}!\n\n"
        "Play hand cricket with your friends and compete for coins!\n\n"
        "Available commands:\n"
        "/register - Register to get bonus coins\n"
        "/pm - Start a new match\n"
        "/profile - View your profile\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - View top players\n"
        "/help - Show all commands"
    )
    
    update.message.reply_text(welcome_message)

def register(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = get_user(user.id)
    
    if user_data:
        update.message.reply_text(f"You're already registered! Check your /profile")
        return
    
    register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    update.message.reply_text(
        f"🎉 Registration successful! You received {REGISTER_REWARD}{EMOJI_COIN}\n"
        f"Check your /profile"
    )

def profile(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("You need to /register first!")
        return
    
    profile_message = (
        f"👤 {user_data['first_name']}'s Profile:\n\n"
        f"Name: {user_data['first_name']} {user_data.get('last_name', '')}\n"
        f"ID: {user_data['user_id']}\n"
        f"Purse: {user_data['coins']}{EMOJI_COIN}\n\n"
        "Performance History:\n"
        f"Wins: {user_data['wins']}\n"
        f"Losses: {user_data['losses']}"
    )
    
    update.message.reply_text(profile_message)

def daily(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("You need to /register first!")
        return
    
    now = datetime.now()
    last_daily = datetime.fromisoformat(user_data['last_daily']) if user_data['last_daily'] else None
    
    if last_daily and (now - last_daily) < timedelta(hours=24):
        next_claim = last_daily + timedelta(hours=24)
        remaining = next_claim - now
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        update.message.reply_text(
            f"⏳ You've already claimed your daily reward today!\n"
            f"Next claim available in {hours}h {minutes}m"
        )
        return
    
    update_user_coins(user.id, DAILY_REWARD)
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET last_daily = ? WHERE user_id = ?',
        (now.isoformat(), user.id)
    )
    conn.commit()
    conn.close()
    
    update.message.reply_text(
        f"🎉 You claimed your daily reward of {DAILY_REWARD}{EMOJI_COIN}!\n"
        f"Your new balance: {user_data['coins'] + DAILY_REWARD}{EMOJI_COIN}"
    )
# Match management functions
def create_match(initiator_id: int, bet_amount: int = 0) -> int:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO matches 
        (initiator_id, bet_amount, game_state, created_at)
        VALUES (?, ?, ?, ?)
    ''', (initiator_id, bet_amount, 'waiting', datetime.now().isoformat()))
    
    match_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return match_id

def get_match(match_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM matches WHERE match_id = ?', (match_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'match_id': row[0],
            'initiator_id': row[1],
            'opponent_id': row[2],
            'bet_amount': row[3],
            'toss_winner': row[4],
            'batting_first': row[5],
            'innings1_score': row[6],
            'innings2_score': row[7],
            'current_batsman_id': row[8],
            'current_bowler_id': row[9],
            'game_state': row[10],
            'message_id': row[11],
            'chat_id': row[12],
            'created_at': row[13]
        }
    return None

def update_match(match_id: int, updates: dict):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    set_clause = ', '.join(f"{key} = ?" for key in updates.keys())
    values = list(updates.values())
    values.append(match_id)
    
    cursor.execute(f'UPDATE matches SET {set_clause} WHERE match_id = ?', values)
    conn.commit()
    conn.close()

def delete_match(match_id: int):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM matches WHERE match_id = ?', (match_id,))
    conn.commit()
    conn.close()

# Game flow functions
def start_match(update: Update, context: CallbackContext, bet_amount: int = 0):
    user = update.effective_user
    user_data = get_user(user.id)
    
    if not user_data:
        update.message.reply_text("You need to /register first!")
        return
    
    if bet_amount > 0 and user_data['coins'] < bet_amount:
        update.message.reply_text(f"You don't have enough coins! Your balance: {user_data['coins']}{EMOJI_COIN}")
        return
    
    match_id = create_match(user.id, bet_amount)
    
    initiator_name = user_data['first_name']
    if bet_amount > 0:
        message_text = f"🎮 Cricket game with bet of {bet_amount}{EMOJI_COIN} has started!\nPress Join below to play with {initiator_name}"
    else:
        message_text = f"🎮 Cricket game has started!\nPress Join below to play with {initiator_name}"
    
    keyboard = [
        [InlineKeyboardButton("Join Game", callback_data=f"join_{match_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = update.message.reply_text(
        message_text,
        reply_markup=reply_markup
    )
    
    update_match(match_id, {
        'message_id': message.message_id,
        'chat_id': message.chat_id
    })

def join_match(update: Update, context: CallbackContext, match_id: int):
    query = update.callback_query
    user = update.effective_user
    user_data = get_user(user.id)
    
    if not user_data:
        query.answer("You need to /register first!", show_alert=True)
        return
    
    match_data = get_match(match_id)
    if not match_data:
        query.answer("Match not found!", show_alert=True)
        return
    
    if match_data['initiator_id'] == user.id:
        query.answer("You can't join your own match!", show_alert=True)
        return
    
    if match_data['opponent_id'] is not None:
        query.answer("Someone already joined this match!", show_alert=True)
        return
    
    if match_data['bet_amount'] > 0 and user_data['coins'] < match_data['bet_amount']:
        query.answer(f"You don't have enough coins to join this match! Needed: {match_data['bet_amount']}{EMOJI_COIN}", show_alert=True)
        return
    
    # Deduct bet amount from both players
    if match_data['bet_amount'] > 0:
        update_user_coins(match_data['initiator_id'], -match_data['bet_amount'])
        update_user_coins(user.id, -match_data['bet_amount'])
    
    update_match(match_id, {
        'opponent_id': user.id,
        'game_state': 'toss'
    })
    
    initiator_data = get_user(match_data['initiator_id'])
    opponent_name = user_data['first_name']
    
    keyboard = [
        [
            InlineKeyboardButton("Heads", callback_data=f"toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"toss_tails_{match_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        f"🎮 Game: {initiator_data['first_name']} vs {opponent_name}\n"
        f"💰 Bet: {match_data['bet_amount']}{EMOJI_COIN}\n\n"
        f"{initiator_data['first_name']}, choose Heads or Tails for the toss:",
        reply_markup=reply_markup
    )
    query.answer()

def process_toss(update: Update, context: CallbackContext, match_id: int, choice: str):
    query = update.callback_query
    match_data = get_match(match_id)
    
    if not match_data or match_data['game_state'] != 'toss':
        query.answer("Match not in toss state!", show_alert=True)
        return
    
    toss_result = random.choice(['heads', 'tails'])
    initiator_won = (choice == toss_result)
    toss_winner_id = match_data['initiator_id'] if initiator_won else match_data['opponent_id']
    
    update_match(match_id, {
        'toss_winner': toss_winner_id,
        'game_state': 'bat_bowl_choice'
    })
    
    winner_data = get_user(toss_winner_id)
    loser_id = match_data['opponent_id'] if initiator_won else match_data['initiator_id']
    loser_data = get_user(loser_id)
    
    keyboard = [
        [
            InlineKeyboardButton(f"Bat {EMOJI_BAT}", callback_data=f"choose_bat_{match_id}"),
            InlineKeyboardButton(f"Bowl {EMOJI_BALL}", callback_data=f"choose_bowl_{match_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        f"🎯 Toss Result: {toss_result.capitalize()}\n"
        f"{winner_data['first_name']} won the toss!\n\n"
        f"{winner_data['first_name']}, choose to Bat or Bowl:",
        reply_markup=reply_markup
    )
    query.answer()
def choose_bat_or_bowl(update: Update, context: CallbackContext, match_id: int, choice: str):
    query = update.callback_query
    match_data = get_match(match_id)
    
    if not match_data or match_data['game_state'] != 'bat_bowl_choice':
        query.answer("Invalid game state!", show_alert=True)
        return
    
    toss_winner_id = match_data['toss_winner']
    opponent_id = match_data['opponent_id'] if match_data['initiator_id'] == toss_winner_id else match_data['initiator_id']
    
    if choice == 'bat':
        batting_first_id = toss_winner_id
        bowling_first_id = opponent_id
        innings_text = f"{get_user(toss_winner_id)['first_name']} chose to bat first!"
    else:
        batting_first_id = opponent_id
        bowling_first_id = toss_winner_id
        innings_text = f"{get_user(toss_winner_id)['first_name']} chose to bowl first!"
    
    update_match(match_id, {
        'batting_first': batting_first_id,
        'current_batsman_id': batting_first_id,
        'current_bowler_id': bowling_first_id,
        'game_state': 'innings1'
    })
    
    # Create number selection keyboard
    keyboard = [
        [
            InlineKeyboardButton("1", callback_data=f"num_1_{match_id}"),
            InlineKeyboardButton("2", callback_data=f"num_2_{match_id}"),
            InlineKeyboardButton("3", callback_data=f"num_3_{match_id}")
        ],
        [
            InlineKeyboardButton("4", callback_data=f"num_4_{match_id}"),
            InlineKeyboardButton("5", callback_data=f"num_5_{match_id}"),
            InlineKeyboardButton("6", callback_data=f"num_6_{match_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    batsman_data = get_user(batting_first_id)
    bowler_data = get_user(bowling_first_id)
    
    query.edit_message_text(
        f"{innings_text}\n\n"
        f"🏏 Batter: {batsman_data['first_name']}\n"
        f"⚾ Bowler: {bowler_data['first_name']}\n\n"
        f"{batsman_data['first_name']}, choose your number (1-6):",
        reply_markup=reply_markup
    )
    query.answer()

def process_number_selection(update: Update, context: CallbackContext, match_id: int, number: int):
    query = update.callback_query
    user = update.effective_user
    match_data = get_match(match_id)
    
    if not match_data:
        query.answer("Match not found!", show_alert=True)
        return
    
    # Determine whose turn it is
    if match_data['game_state'] == 'innings1':
        expected_player = match_data['current_batsman_id']
        role = "batsman"
    elif match_data['game_state'] == 'innings2':
        expected_player = match_data['current_batsman_id']
        role = "batsman"
    else:
        query.answer("Not your turn yet!", show_alert=True)
        return
    
    if user.id != expected_player:
        query.answer(f"Wait for {get_user(expected_player)['first_name']}'s turn!", show_alert=True)
        return
    
    # Store the player's choice in context
    if 'player_choices' not in context.chat_data:
        context.chat_data['player_choices'] = {}
    
    context.chat_data['player_choices'][f"{match_id}_{user.id}"] = number
    
    # Check if both players have made their choices
    if match_data['game_state'] == 'innings1':
        opponent_id = match_data['current_bowler_id']
        opponent_choice = context.chat_data['player_choices'].get(f"{match_id}_{opponent_id}")
        
        if opponent_choice is not None:
            # Both players have chosen, process the outcome
            process_innings_ball(match_id, context, number, opponent_choice)
        else:
            # Wait for opponent's choice
            bowler_data = get_user(match_data['current_bowler_id'])
            query.edit_message_text(
                f"🏏 Batter: {get_user(match_data['current_batsman_id'])['first_name']} chose their number\n"
                f"⚾ Now {bowler_data['first_name']}, choose your number (1-6):",
                reply_markup=query.message.reply_markup
            )
            query.answer(f"You chose {number}. Waiting for bowler's choice...")
    elif match_data['game_state'] == 'innings2':
        opponent_id = match_data['current_bowler_id']
        opponent_choice = context.chat_data['player_choices'].get(f"{match_id}_{opponent_id}")
        
        if opponent_choice is not None:
            # Both players have chosen, process the outcome
            process_innings_ball(match_id, context, number, opponent_choice)
        else:
            # Wait for opponent's choice
            bowler_data = get_user(match_data['current_bowler_id'])
            query.edit_message_text(
                f"🏏 Batter: {get_user(match_data['current_batsman_id'])['first_name']} chose their number\n"
                f"⚾ Now {bowler_data['first_name']}, choose your number (1-6):",
                reply_markup=query.message.reply_markup
            )
            query.answer(f"You chose {number}. Waiting for bowler's choice...")

def process_innings_ball(match_id: int, context: CallbackContext, batsman_num: int, bowler_num: int):
    match_data = get_match(match_id)
    if not match_data:
        return
    
    # Clear the choices
    if 'player_choices' in context.chat_data:
        context.chat_data['player_choices'].pop(f"{match_id}_{match_data['current_batsman_id']}", None)
        context.chat_data['player_choices'].pop(f"{match_id}_{match_data['current_bowler_id']}", None)
    
    # Get player names
    batsman_data = get_user(match_data['current_batsman_id'])
    bowler_data = get_user(match_data['current_bowler_id'])
    
    # Process the ball outcome
    if batsman_num == bowler_num:
        # Batsman is out
        if match_data['game_state'] == 'innings1':
            # First innings ends
            target = match_data['innings1_score'] + 1
            update_match(match_id, {
                'game_state': 'innings2',
                'current_batsman_id': match_data['current_bowler_id'],
                'current_bowler_id': match_data['current_batsman_id']
            })
            
            # Create number selection keyboard for next innings
            keyboard = [
                [
                    InlineKeyboardButton("1", callback_data=f"num_1_{match_id}"),
                    InlineKeyboardButton("2", callback_data=f"num_2_{match_id}"),
                    InlineKeyboardButton("3", callback_data=f"num_3_{match_id}")
                ],
                [
                    InlineKeyboardButton("4", callback_data=f"num_4_{match_id}"),
                    InlineKeyboardButton("5", callback_data=f"num_5_{match_id}"),
                    InlineKeyboardButton("6", callback_data=f"num_6_{match_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            new_batsman_data = get_user(match_data['current_bowler_id'])
            new_bowler_data = get_user(match_data['current_batsman_id'])
            
            message_text = (
                f"Over: {match_data['innings1_score'] // 6}.{match_data['innings1_score'] % 6}\n\n"
                f"🏏 Batter: {batsman_data['first_name']}\n"
                f"⚾ Bowler: {bowler_data['first_name']}\n\n"
                f"{batsman_data['first_name']} Bat {batsman_num}\n"
                f"{bowler_data['first_name']} Bowl {bowler_num}\n\n"
                f"Total Score:\n"
                f"{batsman_data['first_name']} sets a target of {target}\n\n"
                f"{new_batsman_data['first_name']} will now Bat and {new_bowler_data['first_name']} will now Bowl!\n\n"
                f"{new_batsman_data['first_name']}, choose your number (1-6):"
            )
            
            # Update the message
            context.bot.edit_message_text(
                text=message_text,
                chat_id=match_data['chat_id'],
                message_id=match_data['message_id'],
                reply_markup=reply_markup
            )
        else:
            # Second innings ends - bowler's team wins
            update_match(match_id, {
                'innings2_score': match_data['innings2_score'],
                'game_state': 'completed'
            })
            
            # Determine winner and loser
            winner_id = match_data['current_bowler_id']
            loser_id = match_data['current_batsman_id']
            
            # Update stats
            update_user_stats(winner_id, True)
            update_user_stats(loser_id, False)
            
            # Handle bet amount if any
            if match_data['bet_amount'] > 0:
                update_user_coins(winner_id, 2 * match_data['bet_amount'])
            
            winner_data = get_user(winner_id)
            loser_data = get_user(loser_id)
            
            message_text = (
                f"Over: {match_data['innings2_score'] // 6}.{match_data['innings2_score'] % 6}\n\n"
                f"🏏 Batter: {batsman_data['first_name']}\n"
                f"⚾ Bowler: {bowler_data['first_name']}\n\n"
                f"{batsman_data['first_name']} Bat {batsman_num}\n"
                f"{bowler_data['first_name']} Bowl {bowler_num}\n\n"
                f"Final Score:\n"
                f"{batsman_data['first_name']}: {match_data['innings2_score']}\n"
                f"{bowler_data['first_name']}'s target: {match_data['innings1_score'] + 1}\n\n"
                f"🎉 {winner_data['first_name']} wins by {match_data['innings1_score'] - match_data['innings2_score']} runs!"
            )
            
            if match_data['bet_amount'] > 0:
                message_text += f"\n\n💰 {winner_data['first_name']} wins {2 * match_data['bet_amount']}{EMOJI_COIN}!"
            
            # Remove the reply markup
            context.bot.edit_message_text(
                text=message_text,
                chat_id=match_data['chat_id'],
                message_id=match_data['message_id'],
                reply_markup=None
            )
            
            # Delete the match record
            delete_match(match_id)
    else:
        # Batsman scores runs
        runs = batsman_num
        if match_data['game_state'] == 'innings1':
            new_score = match_data['innings1_score'] + runs
            update_match(match_id, {
                'innings1_score': new_score
            })
        else:
            new_score = match_data['innings2_score'] + runs
            update_match(match_id, {
                'innings2_score': new_score
            })
            
            # Check if batting team has won
            if new_score > match_data['innings1_score']:
                # Batting team wins
                update_match(match_id, {
                    'game_state': 'completed'
                })
                
                # Determine winner and loser
                winner_id = match_data['current_batsman_id']
                loser_id = match_data['current_bowler_id']
                
                # Update stats
                update_user_stats(winner_id, True)
                update_user_stats(loser_id, False)
                
                # Handle bet amount if any
                if match_data['bet_amount'] > 0:
                    update_user_coins(winner_id, 2 * match_data['bet_amount'])
                
                winner_data = get_user(winner_id)
                loser_data = get_user(loser_id)
                
                message_text = (
                    f"Over: {new_score // 6}.{new_score % 6}\n\n"
                    f"🏏 Batter: {batsman_data['first_name']}\n"
                    f"⚾ Bowler: {bowler_data['first_name']}\n\n"
                    f"{batsman_data['first_name']} Bat {batsman_num}\n"
                    f"{bowler_data['first_name']} Bowl {bowler_num}\n\n"
                    f"Final Score:\n"
                    f"{batsman_data['first_name']}: {new_score}\n"
                    f"{bowler_data['first_name']}'s target: {match_data['innings1_score'] + 1}\n\n"
                    f"🎉 {winner_data['first_name']} wins by {match_data['innings1_score'] + 1 - new_score} wickets!"
                )
                
                if match_data['bet_amount'] > 0:
                    message_text += f"\n\n💰 {winner_data['first_name']} wins {2 * match_data['bet_amount']}{EMOJI_COIN}!"
                
                # Remove the reply markup
                context.bot.edit_message_text(
                    text=message_text,
                    chat_id=match_data['chat_id'],
                    message_id=match_data['message_id'],
                    reply_markup=None
                )
                
                # Delete the match record
                delete_match(match_id)
                return
        
        # Create number selection keyboard for next ball
        keyboard = [
            [
                InlineKeyboardButton("1", callback_data=f"num_1_{match_id}"),
                InlineKeyboardButton("2", callback_data=f"num_2_{match_id}"),
                InlineKeyboardButton("3", callback_data=f"num_3_{match_id}")
            ],
            [
                InlineKeyboardButton("4", callback_data=f"num_4_{match_id}"),
                InlineKeyboardButton("5", callback_data=f"num_5_{match_id}"),
                InlineKeyboardButton("6", callback_data=f"num_6_{match_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"Over: {new_score // 6}.{new_score % 6}\n\n"
            f"🏏 Batter: {batsman_data['first_name']}\n"
            f"⚾ Bowler: {bowler_data['first_name']}\n\n"
            f"{batsman_data['first_name']} Bat {batsman_num}\n"
            f"{bowler_data['first_name']} Bowl {bowler_num}\n\n"
            f"Total Score:\n"
            f"{batsman_data['first_name']} scored {runs} runs\n"
            f"Current total: {new_score}\n\n"
            f"{batsman_data['first_name']}, continue your batting!"
        )
        
        # Update the message
        context.bot.edit_message_text(
            text=message_text,
            chat_id=match_data['chat_id'],
            message_id=match_data['message_id'],
            reply_markup=reply_markup
        )

# Leaderboard functions
def get_leaderboard(sort_by: str = 'coins', limit: int = 10) -> list:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    if sort_by == 'coins':
        cursor.execute('''
            SELECT user_id, first_name, coins 
            FROM users 
            ORDER BY coins DESC 
            LIMIT ?
        ''', (limit,))
    elif sort_by == 'wins':
        cursor.execute('''
            SELECT user_id, first_name, wins 
            FROM users 
            ORDER BY wins DESC 
            LIMIT ?
        ''', (limit,))
    
    leaderboard = []
    for row in cursor.fetchall():
        leaderboard.append({
            'user_id': row[0],
            'first_name': row[1],
            'value': row[2]
        })
    
    conn.close()
    return leaderboard

def show_leaderboard(update: Update, context: CallbackContext, sort_by: str = 'coins'):
    leaderboard = get_leaderboard(sort_by)
    
    if not leaderboard:
        update.message.reply_text("No players found!")
        return
    
    emoji = EMOJI_COIN if sort_by == 'coins' else '🏆'
    title = "Top 10 Richest Players" if sort_by == 'coins' else "Top 10 Players by Wins"
    
    leaderboard_text = f"🏅 {title}:\n\n"
    for i, player in enumerate(leaderboard, 1):
        leaderboard_text += f"{i}. {player['first_name']} - {player['value']}{emoji}\n"
    
    keyboard = []
    if sort_by == 'coins':
        keyboard.append([InlineKeyboardButton("Show by Wins", callback_data="leaderboard_wins")])
    else:
        keyboard.append([InlineKeyboardButton("Show by Coins", callback_data="leaderboard_coins")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        leaderboard_text,
        reply_markup=reply_markup
    )

def leaderboard_button(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    
    if data == "leaderboard_coins":
        show_leaderboard(update, context, 'coins')
    elif data == "leaderboard_wins":
        show_leaderboard(update, context, 'wins')
    
    query.answer()
# Admin commands
def add_coins(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        update.message.reply_text("🚫 This command is only for admins!")
        return
    
    if len(context.args) < 2:
        update.message.reply_text("Usage: /add <user_id> <amount>")
        return
    
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        update.message.reply_text("Invalid user ID or amount. Both must be numbers.")
        return
    
    target_user = get_user(target_id)
    if not target_user:
        update.message.reply_text("User not found!")
        return
    
    update_user_coins(target_id, amount)
    update.message.reply_text(
        f"✅ Added {amount}{EMOJI_COIN} to {target_user['first_name']}\n"
        f"New balance: {target_user['coins'] + amount}{EMOJI_COIN}"
    )

# Help command
def help_command(update: Update, context: CallbackContext):
    help_text = (
        "🛠️ CCG HandCricket Bot Commands:\n\n"
        "/start - Welcome message and bot introduction\n"
        "/register - Register to get your starting bonus (4000🪙)\n"
        "/pm - Start a new hand cricket match\n"
        "/pm <amount> - Start a match with a bet amount\n"
        "/profile - View your player profile and stats\n"
        "/daily - Claim your daily 2000🪙 reward\n"
        "/leaderboard - View the top players by coins or wins\n"
        "\n"
        "⚙️ How to Play:\n"
        "1. Start a match with /pm\n"
        "2. Opponent joins by clicking the button\n"
        "3. Toss happens, winner chooses to bat or bowl\n"
        "4. Players take turns selecting numbers (1-6)\n"
        "5. If numbers match, batsman is out!\n"
        "6. Try to score more runs than your opponent!"
    )
    
    update.message.reply_text(help_text)

# Command handlers setup
def setup_handlers(dispatcher):
    # Basic commands
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("register", register))
    dispatcher.add_handler(CommandHandler("profile", profile))
    dispatcher.add_handler(CommandHandler("daily", daily))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("leaderboard", 
        lambda u, c: show_leaderboard(u, c, 'coins')))
    
    # Match commands
    dispatcher.add_handler(CommandHandler("pm", 
        lambda u, c: start_match(u, c, bet_amount=0)))
    dispatcher.add_handler(MessageHandler(
        Filters.regex(r'^/pm\s+\d+$'),
        lambda u, c: start_match(u, c, bet_amount=int(u.message.text.split()[1])))
    
    # Admin commands
    dispatcher.add_handler(CommandHandler("add", add_coins))
    
    # Callback handlers
    dispatcher.add_handler(CallbackQueryHandler(
        lambda u, c: join_match(u, c, int(u.callback_query.data.split('_')[1])),
        pattern=r'^join_\d+$'))
    dispatcher.add_handler(CallbackQueryHandler(
        lambda u, c: process_toss(u, c, int(u.callback_query.data.split('_')[2]), u.callback_query.data.split('_')[1])),
        pattern=r'^toss_(heads|tails)_\d+$'))
    dispatcher.add_handler(CallbackQueryHandler(
        lambda u, c: choose_bat_or_bowl(u, c, int(u.callback_query.data.split('_')[2]), u.callback_query.data.split('_')[1])),
        pattern=r'^choose_(bat|bowl)_\d+$'))
    dispatcher.add_handler(CallbackQueryHandler(
        lambda u, c: process_number_selection(u, c, int(u.callback_query.data.split('_')[2]), int(u.callback_query.data.split('_')[1])),
        pattern=r'^num_[1-6]_\d+$'))
    dispatcher.add_handler(CallbackQueryHandler(leaderboard_button,
        pattern=r'^leaderboard_(coins|wins)$'))

# Main function
def main():
    # Initialize database
    init_db()
    
    # Create the Updater and pass it your bot's token
    updater = Updater(BOT_TOKEN, use_context=True)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    # Set up command and callback handlers
    setup_handlers(dispatcher)
    
    # Start the Bot
    updater.start_polling()
    
    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()

if __name__ == '__main__':
    print("Starting CCG HandCricket Bot...")
    main()
