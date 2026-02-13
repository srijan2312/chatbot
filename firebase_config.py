import json
import os

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_CONFIGURED = False
FIREBASE_CONFIG_ERROR = ""


def _load_firebase_service_account():
    if "firebase_service_account" in st.secrets:
        return dict(st.secrets["firebase_service_account"])
    env_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            return json.loads(env_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid FIREBASE_SERVICE_ACCOUNT_JSON value.") from exc
    return None


try:
    firebase_secrets = _load_firebase_service_account()
    if not firebase_secrets:
        raise RuntimeError(
            "Firebase service account not configured. Set Streamlit secrets "
            "[firebase_service_account] or FIREBASE_SERVICE_ACCOUNT_JSON."
        )

    cred = credentials.Certificate(firebase_secrets)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    FIREBASE_CONFIGURED = True
except Exception as exc:
    db = None
    FIREBASE_CONFIGURED = False
    FIREBASE_CONFIG_ERROR = str(exc)


