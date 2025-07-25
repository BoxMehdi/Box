from pymongo import MongoClient

uri = "mongodb+srv://BoxOfficeRobot:WIqhkOQ974s6xkpe@boxofficerobot.9jlszia.mongodb.net/?retryWrites=true&w=majority&tls=false"

try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    print(client.server_info())
    print("اتصال موفقیت‌آمیز بود")
except Exception as e:
    print("خطا در اتصال:", e)
