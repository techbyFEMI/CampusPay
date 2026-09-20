
import firebase_admin
from firebase_admin import auth
from firebase_admin import credentials
from app.core.config import settings
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import json
import base64
import tempfile

bearer_schema=HTTPBearer()


creds_dict = json.loads(settings.FIREBASE_CREDENTIALS)
firebase_creds = credentials.Certificate(creds_dict)

default_app = firebase_admin.initialize_app(firebase_creds)


import jwt

def verify_firebase_token(token: str) -> dict:
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_firebase_user(creds: HTTPAuthorizationCredentials = Depends(bearer_schema)) -> dict:
    token = creds.credentials
    return verify_firebase_token(token)
 


