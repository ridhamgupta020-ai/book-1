import json
import logging
import os
from pathlib import Path

from django.conf import settings


logger = logging.getLogger(__name__)
FIREBASE_APP_NAME = "mybookshow-auth"


class FirebaseAuthUnavailable(Exception):
    pass


class InvalidFirebaseToken(Exception):
    pass


class FirebaseAccountConflict(Exception):
    pass


def verify_firebase_id_token(id_token):
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
        from firebase_admin.exceptions import FirebaseError
    except ImportError as exc:
        raise FirebaseAuthUnavailable(
            "Install the firebase-admin package to enable Google sign-in."
        ) from exc

    try:
        app = firebase_admin.get_app(FIREBASE_APP_NAME)
    except ValueError:
        app = _initialize_firebase_app(firebase_admin, credentials)

    try:
        return auth.verify_id_token(id_token, app=app, check_revoked=True)
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError) as exc:
        raise InvalidFirebaseToken from exc
    except FirebaseError as exc:
        logger.exception("Firebase ID token verification failed.")
        raise FirebaseAuthUnavailable from exc


def _initialize_firebase_app(firebase_admin, credentials):
    credential_json = os.getenv("FIREBASE_ADMIN_CREDENTIALS", "").strip()
    credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

    try:
        if credential_json:
            credential_data = json.loads(credential_json)
            credential = credentials.Certificate(credential_data)
        elif credential_path:
            credential = credentials.Certificate(str(Path(credential_path)))
        else:
            raise FirebaseAuthUnavailable(
                "Set FIREBASE_ADMIN_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS."
            )

        project_id = settings.FIREBASE_WEB_CONFIG.get("projectId", "")
        return firebase_admin.initialize_app(
            credential,
            options={"projectId": project_id} if project_id else None,
            name=FIREBASE_APP_NAME,
        )
    except FirebaseAuthUnavailable:
        raise
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        logger.exception("Firebase Admin credentials could not be loaded.")
        raise FirebaseAuthUnavailable from exc
