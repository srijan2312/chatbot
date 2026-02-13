import time
import bcrypt
from firebase_config import db, FIREBASE_CONFIGURED, FIREBASE_CONFIG_ERROR

# =========================================================
# 🔖 Firestore Collections
# =========================================================
USERS_COLLECTION = "users"
RATE_LIMITS_COLLECTION = "rate_limits"

# =========================================================
# 👤 Authentication Functions
# =========================================================
def _require_db() -> None:
    if not FIREBASE_CONFIGURED or db is None:
        raise RuntimeError(FIREBASE_CONFIG_ERROR or "Firebase is not configured.")


def register_user(username: str, password: str) -> bool:
    """
    Register a new user with hashed password.
    Returns False if username already exists.
    """
    _require_db()
    doc_ref = db.collection(USERS_COLLECTION).document(username)
    if doc_ref.get().exists:
        return False

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("utf-8", "ignore")
    doc_ref.set({"password": hashed})
    return True


def login_user(username: str, password: str) -> bool:
    _require_db()
    if not username:
        return False
    """
    Validate login credentials.
    Returns True if correct, False otherwise.
    """
    doc = db.collection(USERS_COLLECTION).document(username).get()
    if not doc.exists:
        return False

    stored = doc.to_dict().get("password")
    if not stored:
        return False

    return bcrypt.checkpw(password.encode(), stored.encode())


def check_rate_limit(action: str, key: str, max_attempts: int, window_seconds: int):
    _require_db()
    if not key:
        return True, 0
    now = int(time.time())
    cutoff = now - window_seconds
    doc_id = f"{action}:{key}".lower()
    doc_ref = db.collection(RATE_LIMITS_COLLECTION).document(doc_id)
    doc = doc_ref.get()
    attempts = []
    if doc.exists:
        attempts = doc.to_dict().get("attempts", []) or []
    attempts = [ts for ts in attempts if isinstance(ts, int) and ts >= cutoff]
    if len(attempts) >= max_attempts:
        retry_in = window_seconds - (now - min(attempts))
        return False, max(1, retry_in)
    attempts.append(now)
    doc_ref.set({"attempts": attempts, "updated_at": now, "key": key, "action": action})
    return True, 0


# =========================================================
# 🤖 Bot Management
# =========================================================
def add_bot(username: str, name: str, file_text: str, persona: str = None) -> None:
    """
    Store bot data inside Firestore:
      users/{username}/bots/{bot_name}
    Supports optional 'persona' (personality description).
    """
    _require_db()
    bots_ref = db.collection(USERS_COLLECTION).document(username).collection("bots")
    bot_data = {
        "name": name,
        "file_text": file_text,
    }
    if persona:
        bot_data["persona"] = persona

    bots_ref.document(name.lower()).set(bot_data)


def get_user_bots(username: str):
    """
    Retrieve all bots for a given user.
    Returns a list of dicts [{name, file, persona?}, ...]
    """
    _require_db()
    bots_ref = db.collection(USERS_COLLECTION).document(username).collection("bots").stream()
    bots = []
    for doc in bots_ref:
        data = doc.to_dict()
        bots.append({
            "name": data.get("name"),
            "file": doc.id,
            "persona": data.get("persona", "")
        })
    return bots


def get_bot_file(username: str, bot_name: str):
    """
    Get the bot's full text content and optional persona.
    Returns (file_text, persona)
    """
    _require_db()
    doc_ref = db.collection(USERS_COLLECTION).document(username).collection("bots").document(bot_name.lower()).get()
    if doc_ref.exists:
        data = doc_ref.to_dict()
        return data.get("file_text", ""), data.get("persona", "")
    return "", ""


def update_bot(username: str, old_name: str, new_name: str, new_file_text: str = None):
    """
    Rename a bot or update its file text.
    Creates a new document and deletes the old one.
    """
    _require_db()
    user_ref = db.collection(USERS_COLLECTION).document(username)
    old_ref = user_ref.collection("bots").document(old_name.lower())
    old_doc = old_ref.get()

    if not old_doc.exists:
        return

    data = old_doc.to_dict()
    data["name"] = new_name
    if new_file_text:
        data["file_text"] = new_file_text

    # Create new doc, then delete old
    new_ref = user_ref.collection("bots").document(new_name.lower())
    new_ref.set(data)
    old_ref.delete()


def delete_bot(username: str, bot_name: str):
    """
    Delete a bot and its data from Firestore.
    """
    _require_db()
    db.collection(USERS_COLLECTION).document(username).collection("bots").document(bot_name.lower()).delete()


def update_bot_persona(username: str, bot_name: str, persona_text: str):
    """
    Update only the persona field for a bot.
    """
    _require_db()
    doc_ref = db.collection(USERS_COLLECTION).document(username).collection("bots").document(bot_name.lower())
    if doc_ref.get().exists:
        doc_ref.update({"persona": persona_text})


# =========================================================
# 💬 Chat History (Cloud Stored)
# =========================================================
def save_chat_history_cloud(user: str, bot: str, history: list) -> None:
    """
    Save chat history to Firestore under:
      users/{user}/chats/{bot}
    """
    _require_db()
    db.collection(USERS_COLLECTION).document(user).collection("chats").document(bot.lower()).set({
        "history": history
    })


def load_chat_history_cloud(user: str, bot: str) -> list:
    """
    Load chat history from Firestore.
    Returns an empty list if no history found.
    """
    _require_db()
    doc = db.collection(USERS_COLLECTION).document(user).collection("chats").document(bot.lower()).get()
    if doc.exists:
        return doc.to_dict().get("history", [])
    return []


def delete_user_and_data(username: str) -> None:
    _require_db()
    user_ref = db.collection(USERS_COLLECTION).document(username)
    for subcollection in ["bots", "chats"]:
        docs = user_ref.collection(subcollection).stream()
        for doc in docs:
            doc.reference.delete()
    user_ref.delete()

    rate_docs = db.collection(RATE_LIMITS_COLLECTION).where("key", "==", username).stream()
    for doc in rate_docs:
        doc.reference.delete()
