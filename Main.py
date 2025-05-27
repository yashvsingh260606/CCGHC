from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update
import os

TOKEN = os.getenv("TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Received /start from {update.effective_user.first_name}")
    await update.message.reply_text("Hello, bot is working!")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
