# Telegram Bot Token from @BotFather
BOT_TOKEN = '6368745911:AAGeckKpUWqC3Qn_cByeSzN5_1n1A_YHEC4'

# Telethon API credentials from https://my.telegram.org
TELEGRAM_API_ID = 24878110
TELEGRAM_API_HASH = 'b16394a43ec5f74f1455e2ef9bcef2a6'
PHONE = '+918006902002'

# Other configs
OWNER_USERNAME = 'STARK_69_BLACK'  # The username to transfer ownership to
ADMIN_USER_ID = '6313511983'  # Admin user ID for restricted commands
POINTS_REWARDS = {
    2024: 700,
    2023: 1200,
    2022: 1500,
    'older': 2000
}

# Currency rates to INR (approximate)
CURRENCY_RATES = {
    'usd': 83,
    'gbp': 105,
    'rub': 1.15,
    'inr': 1
}

def convert_points(points, currency):
    rate = CURRENCY_RATES.get(currency, 1)
    return points / rate
