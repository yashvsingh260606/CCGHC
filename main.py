import os
from pymongo import MongoClient

client = MongoClient(os.environ["MONGO_URL"])
db = client["your_db_name"]
