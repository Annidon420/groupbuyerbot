import json
import asyncio
import nest_asyncio
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import config
import languages
import checker
from datetime import datetime

nest_asyncio.apply()

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

@app.route('/api/stats')
def api_stats():
    total_users = len(data)
    active_users = sum(1 for u in data.values() if u['points'] > 0)
    total_points = sum(u['points'] for u in data.values())
    avg_points = total_points / total_users if total_users > 0 else 0
    return jsonify({
        'total_users': total_users,
        'active_users': active_users,
        'total_points': total_points,
        'avg_points': round(avg_points, 2)
    })

@app.route('/api/leaderboard')
def api_leaderboard():
    sorted_users = sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)[:10]
    leaderboard = []
    for i, (uid, udata) in enumerate(sorted_users, 1):
        curr = udata.get('currency', 'usd')
        converted_pts = config.convert_points(udata['points'], curr)
        leaderboard.append({
            'rank': i,
            'user_id': uid,
            'points': converted_pts,
            'currency': languages.CURRENCY_NAMES[curr]
        })
    return jsonify(leaderboard)

@app.route('/api/logs')
def api_logs():
    logs = load_logs()
    return jsonify(logs[-100:])  # Last 100 logs

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Load data
def load_data():
    try:
        with open('data.json', 'r') as f:
            data = json.load(f)
            if 'total_withdrawn' not in data:
                data['total_withdrawn'] = 0
            return data
    except FileNotFoundError:
        return {'total_withdrawn': 0}

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)

# Load logs
def load_logs():
    try:
        with open('logs.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_logs(logs):
    with open('logs.json', 'w') as f:
        json.dump(logs, f, indent=4)

def log_interaction(user_id, action, details=""):
    logs = load_logs()
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,
        'action': action,
        'details': details
    }
    logs.append(log_entry)
    # Keep only last 1000 logs
    if len(logs) > 1000:
        logs = logs[-1000:]
    save_logs(logs)

data = load_data()

async def start(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'start')
    if user_id not in data:
        data[user_id] = {'language': None, 'currency': None, 'points': 0, 'groups': [], 'awaiting_withdraw': False}
        save_data(data)

    keyboard = [
        [InlineKeyboardButton(languages.LANGUAGE_NAMES['en'], callback_data='lang_en')],
        [InlineKeyboardButton(languages.LANGUAGE_NAMES['ru'], callback_data='lang_ru')],
        [InlineKeyboardButton(languages.LANGUAGE_NAMES['hi'], callback_data='lang_hi')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🌟 Welcome to Group Buyer Bot! 🌟\n\nSelect your language:', reply_markup=reply_markup)

async def language_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = query.data.split('_')[1]
    data[user_id]['language'] = lang
    save_data(data)
    keyboard = [
        [InlineKeyboardButton(languages.CURRENCY_NAMES['usd'], callback_data='curr_usd')],
        [InlineKeyboardButton(languages.CURRENCY_NAMES['gbp'], callback_data='curr_gbp')],
        [InlineKeyboardButton(languages.CURRENCY_NAMES['rub'], callback_data='curr_rub')],
        [InlineKeyboardButton(languages.CURRENCY_NAMES['inr'], callback_data='curr_inr')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(languages.LANGUAGES[lang]['select_currency'], reply_markup=reply_markup)

async def submit(update: Update, context):
    user_id = str(update.effective_user.id)
    if user_id not in data or data[user_id]['language'] is None:
        await update.message.reply_text('Please select a language first with /start.')
        return

    lang = data[user_id]['language']
    text = update.message.text

    # Check if it's a group link first, process it regardless of withdrawal state
    if 't.me/' in text:
        # Process as group link
        pass  # Continue to the rest of the function
    elif data[user_id].get('awaiting_withdraw'):
        try:
            amount, upi = text.split(' ', 1)
            amount = float(amount)
            if amount < 10:
                await update.message.reply_text("❌ Minimum withdrawal is 10 USD.")
                return
            # Convert USD to INR and deduct
            usd_to_inr = config.CURRENCY_RATES['usd']
            deduct_inr = amount * usd_to_inr
            if data[user_id]['points'] < deduct_inr:
                await update.message.reply_text("❌ Insufficient points after conversion.")
                return
            data[user_id]['points'] -= deduct_inr
            data['total_withdrawn'] += deduct_inr
            # Process withdrawal (for now, just acknowledge)
            await update.message.reply_text(languages.LANGUAGES[lang]['withdraw_success'])
            data[user_id]['awaiting_withdraw'] = False
            save_data(data)
        except ValueError:
            await update.message.reply_text(languages.LANGUAGES[lang]['withdraw_invalid'])
        return
    else:
        await update.message.reply_text(languages.LANGUAGES[lang]['invalid_link'])
        return

    if text in data[user_id]['groups']:
        await update.message.reply_text(languages.LANGUAGES[lang]['already_submitted'])
        return

    data[user_id]['current_link'] = text
    save_data(data)

    await update.message.reply_text(languages.LANGUAGES[lang]['checking'])

    # Get current dialogs before joining
    dialogs_before = await checker.client.get_dialogs()
    chat_ids_before = {d.entity.id for d in dialogs_before if d.is_channel or d.is_group}

    # Join group and get year
    joined, join_error = await checker.join_group(text)
    if not joined:
        if join_error == "not_joinable":
            await update.message.reply_text(languages.LANGUAGES[lang]['public_not_joinable'])
        else:
            await update.message.reply_text(languages.LANGUAGES[lang]['join_failed'])
        return

    # Get chat entity after joining
    if 'joinchat' in text:
        # For private groups, find the newly joined chat
        dialogs_after = await checker.client.get_dialogs()
        for dialog in dialogs_after:
            if (dialog.is_channel or dialog.is_group) and dialog.entity.id not in chat_ids_before:
                chat = dialog.entity
                chat_id = chat.id
                break
        else:
            await update.message.reply_text(languages.LANGUAGES[lang]['error'])
            return
    elif 'c/' in text:
        # For private channels, parse the channel ID
        channel_id_str = text.split('/')[-1]
        try:
            chat = await checker.client.get_entity(int(channel_id_str))
            chat_id = chat.id
        except Exception as e:
            print(f"Error getting private channel entity: {e}")
            await update.message.reply_text(languages.LANGUAGES[lang]['error'])
            return
    else:
        # For public groups/channels
        username = text.split('/')[-1]
        try:
            chat = await checker.client.get_entity(username)
            chat_id = chat.id
        except Exception as e:
            print(f"Error getting public entity: {e}")
            await update.message.reply_text(languages.LANGUAGES[lang]['error'])
            return

    year = await checker.get_creation_year(chat_id)
    if year is None:
        await update.message.reply_text(languages.LANGUAGES[lang]['error'])
        await checker.leave_group(chat_id)
        return

    if year >= 2022:
        if year <= 2024:
            points = config.POINTS_REWARDS.get(year, config.POINTS_REWARDS['older'])
        else:
            points = config.POINTS_REWARDS['older']  # for year > 2024, use older points
        text_msg = languages.LANGUAGES[lang]['eligible'].format(year=year, owner=config.OWNER_USERNAME, points=points)
        keyboard = [[InlineKeyboardButton('✅ Done Ownership', callback_data=f'done_{chat_id}_{year}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text_msg, reply_markup=reply_markup)
    else:
        # For year < 2022, award older points
        points = config.POINTS_REWARDS['older']
        text_msg = languages.LANGUAGES[lang]['eligible'].format(year=year, owner=config.OWNER_USERNAME, points=points)
        keyboard = [[InlineKeyboardButton('✅ Done Ownership', callback_data=f'done_{chat_id}_{year}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text_msg, reply_markup=reply_markup)

async def currency_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    curr = query.data.split('_')[1]
    data[user_id]['currency'] = curr
    save_data(data)
    lang = data[user_id]['language']
    text = languages.LANGUAGES[lang]['currency_selected'].format(currency=languages.CURRENCY_NAMES[curr]) + '\n' + languages.LANGUAGES[lang]['submit_prompt']
    await query.edit_message_text(text)

async def done_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = data[user_id]['language']
    _, chat_id, year = query.data.split('_')
    chat_id = int(chat_id)
    year = int(year)

    owned = await checker.check_ownership(chat_id)
    if owned:
        points = config.POINTS_REWARDS.get(year, config.POINTS_REWARDS['older'])
        data[user_id]['points'] += points
        data[user_id]['groups'].append(data[user_id]['current_link'])  # Store the submitted link
        save_data(data)
        await query.edit_message_text(languages.LANGUAGES[lang]['ownership_done'].format(points=points))
    else:
        await query.edit_message_text(languages.LANGUAGES[lang]['ownership_failed'])

    await checker.leave_group(chat_id)

async def points(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'points')
    lang = data[user_id]['language']
    curr = data[user_id].get('currency', 'usd')
    pts = data[user_id]['points']
    converted_pts = config.convert_points(pts, curr)
    await update.message.reply_text(languages.LANGUAGES[lang]['points_balance'].format(points=converted_pts, currency=languages.CURRENCY_NAMES[curr]))

async def withdraw(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'withdraw')
    lang = data[user_id]['language']
    pts = data[user_id]['points']
    if pts < 700:
        await update.message.reply_text(languages.LANGUAGES[lang]['withdraw_insufficient'].format(min_points=700))
        return
    await update.message.reply_text(languages.LANGUAGES[lang]['withdraw_prompt'])
    # Set state for withdrawal
    data[user_id]['awaiting_withdraw'] = True
    save_data(data)

async def portfolio(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'portfolio')
    lang = data[user_id]['language']
    curr = data[user_id].get('currency', 'usd')
    pts = data[user_id]['points']
    converted_pts = config.convert_points(pts, curr)
    await update.message.reply_text(languages.LANGUAGES[lang]['portfolio'].format(points=converted_pts, currency=languages.CURRENCY_NAMES[curr]))

async def mygroups(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'mygroups')
    lang = data[user_id]['language']
    groups = data[user_id]['groups']
    if groups:
        group_list = '\n'.join(groups)
        await update.message.reply_text(f"📋 **Your Submitted Groups:**\n{group_list}")
    else:
        await update.message.reply_text("❌ No groups submitted yet.")

async def stats(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'stats')
    lang = data[user_id]['language']
    total_users = len(data) - 1  # Subtract 1 for 'total_withdrawn' key
    active_users = sum(1 for u in data.values() if isinstance(u, dict) and u['points'] > 0)
    total_points = sum(u['points'] for u in data.values() if isinstance(u, dict))
    avg_points = total_points / total_users if total_users > 0 else 0
    total_withdrawn = data.get('total_withdrawn', 0)
    await update.message.reply_text(languages.LANGUAGES[lang]['stats'].format(
        total_users=total_users,
        active_users=active_users,
        total_points=total_points,
        avg_points=round(avg_points, 2),
        total_withdrawn=total_withdrawn
    ))

async def leaderboard(update: Update, context):
    user_id = str(update.effective_user.id)
    log_interaction(user_id, 'leaderboard')
    lang = data[user_id]['language']
    sorted_users = sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)[:10]
    leaderboard_text = ""
    for i, (uid, udata) in enumerate(sorted_users, 1):
        curr = udata.get('currency', 'usd')
        converted_pts = config.convert_points(udata['points'], curr)
        leaderboard_text += f"{i}. {uid} - {converted_pts} {languages.CURRENCY_NAMES[curr]}\n"
    await update.message.reply_text(languages.LANGUAGES[lang]['leaderboard'].format(leaderboard_text=leaderboard_text))

async def viewlogs(update: Update, context):
    user_id = str(update.effective_user.id)
    if user_id != config.ADMIN_USER_ID:
        await update.message.reply_text(languages.LANGUAGES.get(data[user_id]['language'], languages.LANGUAGES['en'])['admin_only'])
        return
    logs = load_logs()
    if not logs:
        await update.message.reply_text(languages.LANGUAGES.get(data[user_id]['language'], languages.LANGUAGES['en'])['no_logs'])
        return
    logs_text = ""
    for log in logs[-10:]:  # Last 10 logs
        logs_text += f"{log['timestamp'][:19]} - {log['user_id']} - {log['action']}\n"
    await update.message.reply_text(languages.LANGUAGES.get(data[user_id]['language'], languages.LANGUAGES['en'])['logs'].format(logs_text=logs_text))

async def main():
    while True:
        try:
            # Start Telethon client with reconnection
            await checker.client.start(phone=config.PHONE)

            application = Application.builder().token(config.BOT_TOKEN).build()

            application.add_handler(CommandHandler('start', start))
            application.add_handler(CallbackQueryHandler(language_callback, pattern='^lang_'))
            application.add_handler(CallbackQueryHandler(currency_callback, pattern='^curr_'))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, submit))
            application.add_handler(CallbackQueryHandler(done_callback, pattern='^done_'))
            application.add_handler(CommandHandler('points', points))
            application.add_handler(CommandHandler('withdraw', withdraw))
            application.add_handler(CommandHandler('portfolio', portfolio))
            application.add_handler(CommandHandler('mygroups', mygroups))
            application.add_handler(CommandHandler('stats', stats))
            application.add_handler(CommandHandler('leaderboard', leaderboard))
            application.add_handler(CommandHandler('viewlogs', viewlogs))

            # Run polling in the same event loop
            await application.run_polling()
        except Exception as e:
            print(f"Bot error: {e}. Reconnecting in 10 seconds...")
            await asyncio.sleep(10)
            await checker.client.disconnect()
            continue

if __name__ == '__main__':
    import threading
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    asyncio.run(main())
