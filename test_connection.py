import requests
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv('BOT_TOKEN')

if not token:
    print("❌ Токен не найден в файле .env")
    exit()

print(f"Проверяем токен: {token[:10]}...")

try:
    # Проверяем подключение к Telegram API
    url = f"https://api.telegram.org/bot{token}/getMe"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        if data['ok']:
            print(f"✅ Бот успешно подключен!")
            print(f"Имя бота: {data['result']['first_name']}")
            print(f"Username: @{data['result']['username']}")
        else:
            print(f"❌ Ошибка API: {data}")
    else:
        print(f"❌ Ошибка HTTP: {response.status_code}")
        
except requests.exceptions.Timeout:
    print("❌ Таймаут подключения. Проверьте интернет и доступ к Telegram")
except requests.exceptions.ConnectionError:
    print("❌ Ошибка подключения. Возможно, Telegram заблокирован")
except Exception as e:
    print(f"❌ Ошибка: {e}")