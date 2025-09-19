import uuid, time, hashlib, secrets
from typing import Optional
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger


# ────────────────────────────── Auth Helpers/Routes ───────────────────────────
def _hash_password(password: str, salt: Optional[str] = None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return {"salt": salt, "hash": dk.hex()}


def _verify_password(password: str, salt: str, expected_hex: str) -> bool:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return secrets.compare_digest(dk.hex(), expected_hex)


@app.post("/auth/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if not email or not password or "@" not in email:
        raise HTTPException(400, detail="Invalid email or password")
    users = rag.db["users"]
    if users.find_one({"email": email}):
        raise HTTPException(409, detail="Email already registered")
    user_id = str(uuid.uuid4())
    hp = _hash_password(password)
    users.insert_one({
        "email": email,
        "user_id": user_id,
        "pw_salt": hp["salt"],
        "pw_hash": hp["hash"],
        "created_at": int(time.time())
    })
    logger.info(f"[AUTH] Created user {email} -> {user_id}")
    return {"email": email, "user_id": user_id}


@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    users = rag.db["users"]
    doc = users.find_one({"email": email})
    if not doc:
        raise HTTPException(401, detail="Invalid credentials")
    if not _verify_password(password, doc.get("pw_salt", ""), doc.get("pw_hash", "")):
        raise HTTPException(401, detail="Invalid credentials")
    logger.info(f"[AUTH] Login {email}")
    return {"email": email, "user_id": doc.get("user_id")}


