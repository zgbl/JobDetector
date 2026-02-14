
from api.db import get_db

def update_benlang_name():
    db = get_db()
    result = db.collections.update_one(
        {'id': 'ben-lang-feb-2024'},
        {'$set': {'name': "Ben Lang's List"}}
    )
    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")

if __name__ == "__main__":
    update_benlang_name()
