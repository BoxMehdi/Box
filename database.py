from pymongo import MongoClient
import config

mongo_client = MongoClient(config.MONGO_URI)
db = mongo_client["boxoffice"]

files_collection = db["files"]
users_collection = db["users"]

def save_file(file_doc: dict):
    result = files_collection.insert_one(file_doc)
    return result.inserted_id

def get_files_by_film_id(film_id: str):
    files = list(files_collection.find({"film_id": film_id}))
    return files

def save_or_update_user(user_doc: dict):
    users_collection.update_one(
        {"user_id": user_doc["user_id"]},
        {"$set": user_doc},
        upsert=True
    )
