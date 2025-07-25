import time
import certifi
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import logging

def connect_mongo(uri, max_retries=5):
    for attempt in range(1, max_retries+1):
        try:
            client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
            )
            client.server_info()
            logging.info("✅ اتصال به MongoDB برقرار شد.")
            return client
        except ServerSelectionTimeoutError as e:
            logging.error(f"❌ خطا در اتصال به MongoDB (تلاش {attempt} از {max_retries}): {e}")
            if attempt == max_retries:
                logging.error("اتصال به دیتابیس برقرار نشد، برنامه متوقف شد.")
                raise
            else:
                logging.info("در حال تلاش مجدد اتصال به MongoDB...")
                time.sleep(5)  # اینجا اصلاح شده

# استفاده:
mongo_client = connect_mongo(MONGO_URI)
