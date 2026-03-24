import json
import os
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from urllib.parse import urlparse

from sqlalchemy import event, text

# Import with error handling
try:
    from authlib.integrations.flask_client import OAuth

    _has_authlib = True
except ImportError as e:
    print(f"Warning: authlib not available: {e}")
    _has_authlib = False
    OAuth = None

try:
    from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
    from flask_login import (
        LoginManager,
        UserMixin,
        current_user,
        login_required,
        login_user,
        logout_user,
    )
    from flask_sqlalchemy import SQLAlchemy
    from werkzeug.exceptions import RequestEntityTooLarge
    from werkzeug.security import check_password_hash, generate_password_hash

    _has_flask = True
except ImportError as e:
    print(f"Error: Flask dependencies not available: {e}")
    _has_flask = False
    sys.exit(1)

try:
    from zoneinfo import ZoneInfo  # Python 3.9+

    _has_zoneinfo = True
except Exception:
    _has_zoneinfo = False

# Import with error handling for optional dependencies
try:
    import docx

    _has_docx = True
except ImportError as e:
    print(f"Warning: python-docx not available: {e}")
    _has_docx = False

try:
    import easyocr

    _has_easyocr = True
except ImportError as e:
    print(f"Warning: easyocr not available: {e}")
    _has_easyocr = False

try:
    import google.generativeai as genai

    _has_gemini = True
except ImportError as e:
    print(f"Warning: google-generativeai not available: {e}")
    _has_gemini = False

try:
    import PyPDF2

    _has_pypdf2 = True
except ImportError as e:
    print(f"Warning: PyPDF2 not available: {e}")
    _has_pypdf2 = False

try:
    import requests
    from bs4 import BeautifulSoup
    from duckduckgo_search import DDGS
    from langdetect import detect

    _has_web_deps = True
except ImportError as e:
    print(f"Warning: Web dependencies not available: {e}")
    _has_web_deps = False

try:
    from dotenv import load_dotenv

    _has_dotenv = True
except ImportError as e:
    print(f"Warning: python-dotenv not available: {e}")
    _has_dotenv = False

try:
    from PIL import Image, ImageFile

    _has_pil = True
except ImportError as e:
    print(f"Warning: Pillow not available: {e}")
    _has_pil = False

# Load environment variables
if _has_dotenv:
    load_dotenv()
# Pillow compatibility shim for deprecated resampling constants used by dependencies (e.g., EasyOCR)
if _has_pil:
    try:
        # Pillow >= 10 removed these aliases; map to Resampling equivalents
        if not hasattr(Image, "ANTIALIAS"):
            setattr(Image, "ANTIALIAS", Image.Resampling.LANCZOS)
        if not hasattr(Image, "BILINEAR"):
            setattr(Image, "BILINEAR", Image.Resampling.BILINEAR)
        if not hasattr(Image, "BICUBIC"):
            setattr(Image, "BICUBIC", Image.Resampling.BICUBIC)
    except Exception:
        pass
    try:
        # Allow loading slightly corrupted/truncated images rather than erroring out
        ImageFile.LOAD_TRUNCATED_IMAGES = True
    except Exception:
        pass
try:
    import pytesseract

    _has_tesseract = True
except Exception:
    _has_tesseract = False

import io

try:
    import cv2
    import numpy as np

    _has_cv2 = True
except ImportError as e:
    print(f"Warning: OpenCV not available: {e}")
    _has_cv2 = False

# Encryption helpers removed

# Optional PaddleOCR (GPU) fallback
try:
    from paddleocr import PaddleOCR  # type: ignore

    _has_paddleocr = True
except Exception:
    _has_paddleocr = False

# Initialize Flask app
try:
    app = Flask(__name__)
    print("✓ Flask app initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize Flask app: {e}")
    sys.exit(1)

# Configuration
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "qJBri77yHZvgMoRHmf_VkTzyBT8qRRANtRU0R2JqG5NPX9NSZA-seOBrMeuweL8TG284Wht7YLkSU0KPIdKloA",
)

# Database configuration - use Render's DATABASE_URL if available
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Render provides DATABASE_URL, use it directly
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    print(f"Using production database: {database_url[:50]}...")
    print("Database URL found - ready for production!")
else:
    # Local development fallback
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "postgresql://neethi_user:HariDharaan%402025@localhost/neethi_ai"
    )
    print("Using local development database")
    print("WARNING: DATABASE_URL not found! Make sure to set it in Render environment variables.")
    print("To fix: Link your PostgreSQL database to the web service in Render dashboard")
    print(
        "Environment variables available:",
        [k for k in os.environ.keys() if "DATABASE" in k.upper()],
    )

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Limit uploads to 10 MB to prevent crashes
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))

# Initialize extensions
try:
    # Avoid implicit post-commit refreshes that can trigger RLS-protected reloads.
    db = SQLAlchemy(app, session_options={"expire_on_commit": False})
    login_manager = LoginManager()
    login_manager.init_app(app)
    setattr(login_manager, "login_view", "login")
    setattr(login_manager, "login_message", "Please log in to access this page.")
    print("✓ Database and login manager initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize database/login manager: {e}")
    sys.exit(1)


# Initialize OAuth
def init_oauth():
    if not _has_authlib:
        print("OAuth providers disabled - authlib not available")
        return None, None, None, None

    try:
        if OAuth is None:
            print("OAuth class not available")
            return None, None, None, None
        oauth = OAuth(app)

        # Only register OAuth providers if environment variables are properly set
        google = None
        github = None
        linkedin = None

        # Google OAuth - only if properly configured
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if (
            google_client_id
            and google_client_secret
            and google_client_id != "your-google-client-id"
        ):
            try:
                google = cast(
                    Any,
                    oauth.register(
                        name="google",
                        client_id=google_client_id,
                        client_secret=google_client_secret,
                        server_metadata_url=(
                            "https://accounts.google.com/.well-known/" "openid_configuration"
                        ),
                        client_kwargs={"scope": "openid email profile"},
                    ),
                )
                print("✓ Google OAuth configured")
            except Exception as e:
                print(f"⚠️ Google OAuth configuration failed: {e}")
        else:
            print("⚠️ Google OAuth not configured - missing environment variables")

        # GitHub OAuth - only if properly configured
        github_client_id = os.getenv("GITHUB_CLIENT_ID")
        github_client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        if (
            github_client_id
            and github_client_secret
            and github_client_id != "your-github-client-id"
        ):
            try:
                github = cast(
                    Any,
                    oauth.register(
                        name="github",
                        client_id=github_client_id,
                        client_secret=github_client_secret,
                        access_token_url="https://github.com/login/oauth/access_token",
                        authorize_url="https://github.com/login/oauth/authorize",
                        api_base_url="https://api.github.com/",
                        client_kwargs={"scope": "read:user user:email"},
                    ),
                )
                print("✓ GitHub OAuth configured")
            except Exception as e:
                print(f"⚠️ GitHub OAuth configuration failed: {e}")
        else:
            print("⚠️ GitHub OAuth not configured - missing environment variables")

        # LinkedIn OAuth - only if properly configured
        linkedin_client_id = os.getenv("LINKEDIN_CLIENT_ID")
        linkedin_client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
        if (
            linkedin_client_id
            and linkedin_client_secret
            and linkedin_client_id != "your-linkedin-client-id"
        ):
            try:
                linkedin = cast(
                    Any,
                    oauth.register(
                        name="linkedin",
                        client_id=linkedin_client_id,
                        client_secret=linkedin_client_secret,
                        access_token_url="https://www.linkedin.com/oauth/v2/accessToken",
                        authorize_url="https://www.linkedin.com/oauth/v2/authorization",
                        api_base_url="https://api.linkedin.com/v2/",
                        client_kwargs={
                            "scope": "r_liteprofile r_emailaddress",
                            "token_endpoint_auth_method": "client_secret_post",
                        },
                    ),
                )
                print("✓ LinkedIn OAuth configured")
            except Exception as e:
                print(f"⚠️ LinkedIn OAuth configuration failed: {e}")
        else:
            print("⚠️ LinkedIn OAuth not configured - missing environment variables")

        return oauth, google, github, linkedin

    except Exception as e:
        print(f"⚠️ OAuth initialization failed: {e}")
        return None, None, None, None


oauth, google, github, linkedin = init_oauth()


# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)  # Nullable for OAuth users
    name = db.Column(db.String(100), nullable=False)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    auth_provider = db.Column(db.String(20), default="email")  # 'email' or 'google'

    # Relationship to chats
    chats = db.relationship("Chat", backref="user", lazy=True, cascade="all, delete-orphan")


class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    sources = db.Column(db.Text)  # JSON string of sources
    language = db.Column(db.String(10), default="en")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    feature_used = db.Column(db.String(50))  # Which feature was used
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversation.id"), nullable=True, default=None
    )  # Link to conversation
    is_edited = db.Column(db.Boolean, default=False)  # Track if message was edited
    edited_at = db.Column(db.DateTime)  # When it was edited
    # Encryption metadata
    chat_encrypted = db.Column(db.Boolean, default=False)
    chat_iv = db.Column(db.Text)
    chat_tag = db.Column(db.Text)
    enc_version = db.Column(db.SmallInteger, default=1)
    key_id = db.Column(db.Text)


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)  # For soft deletion
    document_context = db.Column(db.Text, nullable=True)  # Attached doc/notice for follow-ups

    # Relationships
    chats = db.relationship("Chat", backref="conversation", lazy=True, cascade="all, delete-orphan")


class VerificationFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    chat_id = db.Column(db.Integer, db.ForeignKey("chat.id"), nullable=True)
    verification_type = db.Column(
        db.String(50), nullable=False
    )  # 'fake_notice', 'document_analysis', etc.
    original_result = db.Column(db.Text, nullable=False)  # Original analysis result
    user_feedback = db.Column(db.String(20), nullable=False)  # 'correct', 'incorrect', 'partial'
    feedback_details = db.Column(db.Text)  # User's detailed feedback
    admin_response = db.Column(db.Text)  # Admin's response
    status = db.Column(db.String(20), default="pending")  # 'pending', 'reviewed', 'resolved'
    priority = db.Column(db.Integer, default=1)  # 1=low, 2=medium, 3=high
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)


_rls_user_id: ContextVar[str] = ContextVar("_rls_user_id", default="")


def _init_postgres_rls_pool_hooks() -> None:
    """Ensure pooled connections always have correct RLS context."""
    try:
        if db.engine.dialect.name != "postgresql":
            return
        engine = db.engine
        if getattr(engine, "_neethi_rls_hooks_installed", False):
            return

        @event.listens_for(engine, "checkout")
        def _apply_rls_context_on_checkout(dbapi_connection, _connection_record, _connection_proxy):
            uid = _rls_user_id.get()
            cursor = dbapi_connection.cursor()
            try:
                if uid:
                    # Use plain SET for custom GUC; it's reliable across psycopg2 + pooling.
                    cursor.execute("SET app.user_id = %s", (uid,))
                else:
                    cursor.execute("RESET app.user_id")
            finally:
                cursor.close()

        setattr(engine, "_neethi_rls_hooks_installed", True)
    except Exception:
        # If hooks fail, app still runs (RLS may block; logs will show DB errors)
        pass


def _ensure_postgres_rls():
    """Enable RLS and create per-user policies for sensitive tables (Postgres only)."""
    try:
        if db.engine.dialect.name != "postgresql":
            return

        rls_sql = [
            # Chat
            "ALTER TABLE chat ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE chat FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS chat_user_isolation ON chat",
            """
            CREATE POLICY chat_user_isolation ON chat
            USING (user_id = nullif(current_setting('app.user_id', true), '')::int)
            WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::int)
            """,
            # Conversation
            "ALTER TABLE conversation ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE conversation FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS conversation_user_isolation ON conversation",
            """
            CREATE POLICY conversation_user_isolation ON conversation
            USING (user_id = nullif(current_setting('app.user_id', true), '')::int)
            WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::int)
            """,
            # Verification feedback
            "ALTER TABLE verification_feedback ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE verification_feedback FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS verification_feedback_user_isolation ON verification_feedback",
            """
            CREATE POLICY verification_feedback_user_isolation ON verification_feedback
            USING (user_id = nullif(current_setting('app.user_id', true), '')::int)
            WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::int)
            """,
        ]

        for stmt in rls_sql:
            db.session.execute(text(stmt))
        db.session.commit()
        app.logger.info("Postgres RLS policies ensured successfully")
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Failed to ensure Postgres RLS policies: {e}")


@app.before_request
def _set_postgres_rls_context():
    """Set per-request user context used by Postgres RLS policies."""
    try:
        if db.engine.dialect.name != "postgresql":
            return
        _init_postgres_rls_pool_hooks()
        uid = str(current_user.id) if getattr(current_user, "is_authenticated", False) else ""
        _rls_user_id.set(uid)
        # Force checkout now so the connection gets configured for this request.
        # Also explicitly set the variable on the active connection to avoid cases
        # where the checkout hook wasn't applied yet (engine already in use).
        conn = db.session.connection()
        if uid:
            conn.execute(text("SET app.user_id = :uid"), {"uid": uid})
        else:
            conn.execute(text("RESET app.user_id"))
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


@app.teardown_request
def _reset_postgres_rls_context(_exc):
    """Clear RLS context to prevent pooled-connection user_id leakage."""
    try:
        if db.engine.dialect.name != "postgresql":
            return
        _rls_user_id.set("")
    except Exception:
        pass


# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Make config available in templates
@app.context_processor
def inject_config():
    return dict(config=app.config)


# Initialize EasyOCR reader with Tamil support
# EasyOCR reader will be initialized when needed to avoid startup issues
reader = None


# Language Detection and Support
def detect_language(text):
    """Detect if text is in Tamil or English"""
    try:
        lang = detect(text)
        return "ta" if lang == "ta" else "en"
    except Exception:
        return "en"


def get_language_prompt(language):
    """Get language-specific prompts"""
    if language == "ta":
        return {
            "system": (
                "நீங்கள் ஒரு சட்ட AI உதவியாளர். இந்திய குடிமக்களுக்கு "
                "அவர்களின் உரிமைகளை புரிந்துகொள்ள உதவுங்கள்."
            ),
            "response_instruction": ("தமிழில் பதிலளிக்கவும் மற்றும் சட்ட பிரிவுகளை குறிப்பிடவும்."),
        }
    else:
        return {
            "system": "You are a legal AI assistant helping citizens understand their rights.",
            "response_instruction": "Answer in English and mention relevant legal sections.",
        }


# Configure Gemini API
def configure_gemini_api():
    api_key = os.getenv(
        "GEMINI_API_KEY",
        "Key",
    )
    try:
        if not api_key:
            app.logger.error("GEMINI_API_KEY not found in environment variables")
            return None
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        app.logger.info("Gemini API configured successfully")
        return model
    except Exception as e:
        app.logger.error(f"Error configuring Gemini API: {str(e)}")
        return None


# Initialize Gemini model
model = configure_gemini_api()

# Allow loading truncated images safely
ImageFile.LOAD_TRUNCATED_IMAGES = True


# Friendly error for oversized uploads
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({"error": "File too large. Please upload an image under 10 MB."}), 413


# Translation helper
def translate_text(text, target_lang, model):
    try:
        if target_lang not in ["en", "ta"] or not text.strip():
            return text
        lang_label = "English" if target_lang == "en" else "Tamil"
        prompt = (
            f"Translate the following text to {lang_label} preserving legal "
            "meaning and terminology:\n\n"
            "Text:\n"
            f"{text}\n"
        )
        response = model.generate_content(prompt)
        return response.text if response and response.text else text
    except Exception:
        return text


# PDF Parsing
def extract_text_from_pdf(file):
    full_text = ""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        for page in pdf_reader.pages:
            text = page.extract_text() or ""
            full_text += text
        return full_text[:4000]  # Gemini safe limit
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")


# Word Document Parsing
def extract_text_from_docx(file):
    try:
        doc = docx.Document(file)
        full_text = ""
        for para in doc.paragraphs:
            full_text += para.text + "\n"
        return full_text[:4000]  # Gemini safe limit
    except Exception as e:
        raise Exception(f"Error extracting text from Word document: {str(e)}")


# Legal Source Finder with Tamil Nadu Support
def get_legal_sources(query, max_results=3, fast=False):
    # National trusted sites
    national_sites = [
        "site:indiankanoon.org",
        "site:gov.in",
        "site:prsindia.org",
        "site:egazette.nic.in",
        "site:legislative.gov.in",
        "site:india.gov.in",
        "site:legalaffairs.gov.in",
        "site:incometax.gov.in",
        "site:gst.gov.in",
        "site:cbic.gov.in",
    ]

    # Tamil Nadu specific sites
    tn_sites = [
        "site:tn.gov.in",
        "site:law.tn.gov.in",
        "site:ctd.tn.gov.in",
        "site:tnreginet.gov.in",
        "site:tnincometax.gov.in",
        "site:tnpolice.gov.in",
    ]

    all_sites = national_sites + tn_sites
    combined_sites = " OR ".join(all_sites)

    # Strict domain whitelist (hostnames)
    allowed_domains = [
        "indiankanoon.org",
        "gov.in",
        "prsindia.org",
        "egazette.nic.in",
        "legislative.gov.in",
        "india.gov.in",
        "legalaffairs.gov.in",
        "incometax.gov.in",
        "gst.gov.in",
        "cbic.gov.in",
        "tn.gov.in",
        "law.tn.gov.in",
        "ctd.tn.gov.in",
        "tnreginet.gov.in",
        "tnincometax.gov.in",
        "tnpolice.gov.in",
        "nic.in",
    ]
    search_query = f"{query} {combined_sites}"

    try:
        trusted_links: list[str] = []

        # Primary: DuckDuckGo API wrapper
        try:
            with DDGS() as ddgs:
                results = ddgs.text(search_query, max_results=max_results)
                for result in results:
                    href = result.get("href", "")
                    if not href:
                        continue
                    hostname = urlparse(str(href)).hostname or ""
                    if any(hostname.endswith(dom) for dom in allowed_domains):
                        trusted_links.append(href)
        except Exception:
            # Fallback: scrape DuckDuckGo HTML to avoid httpx/proxy incompatibilities
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    )
                }
                resp = requests.get(
                    "https://duckduckgo.com/html/",
                    params={"q": search_query},
                    headers=headers,
                    timeout=4,
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select("a.result__a, a[href]"):
                    href = a.get("href", "")
                    if not isinstance(href, str) or not href or href.startswith("/"):
                        continue
                    hostname = urlparse(str(href)).hostname or ""
                    if any(hostname.endswith(dom) for dom in allowed_domains):
                        trusted_links.append(href)
                    if len(trusted_links) >= max_results:
                        break
            except Exception:
                pass

        # If nothing found, try expanded queries (IPC/section awareness and legal phrasing)
        if not trusted_links:
            expanded_queries: list[str] = []
            # Section targeting
            section_match = re.search(r"(?:section\s*)?(\d{1,4})", query, re.IGNORECASE)
            if section_match:
                sec = section_match.group(1)
                expanded_queries.extend(
                    [
                        f"IPC Section {sec}",
                        f"Indian Penal Code Section {sec}",
                        f"Section {sec} IPC meaning",
                        f"Section {sec} IPC punishment",
                    ]
                )
            # IPC expansion
            if re.search(r"\bipc\b", query, re.IGNORECASE):
                expanded_queries.extend(["Indian Penal Code overview", "What is Indian Penal Code"])
            # General legal phrasing
            expanded_queries.extend([f"{query} Indian law", f"{query} legal definition India"])
            # Try API wrapper first for expanded queries as well
            try:
                with DDGS() as ddgs:
                    results = ddgs.text(" OR ".join(expanded_queries), max_results=max_results)
                    for result in results:
                        href = result.get("href", "")
                        if not href:
                            continue
                        hostname = urlparse(str(href)).hostname or ""
                        if any(hostname.endswith(dom) for dom in allowed_domains):
                            trusted_links.append(href)
            except Exception:
                pass

        # Deduplicate and cap
        deduped = list(dict.fromkeys(trusted_links))
        return deduped[:max_results]
    except Exception as e:
        raise Exception(f"Error fetching legal sources: {str(e)}")


# Web Scraping
def scrape_web_text(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            )
        }
        response = requests.get(url, timeout=10, headers=headers)
        soup = BeautifulSoup(response.content.decode("utf-8"), "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join([para.get_text() for para in paragraphs])
        return text[:4000]
    except Exception:
        return ""


# Summarize Legal Issue
def summarize_legal_issue(document_text, query, urls, model):
    try:
        if not document_text.strip():
            raise Exception("Document is empty.")
        prompt = (
            "You are a legal AI assistant helping citizens understand their rights.\n\n"
            f"User Question: {query}\n\n"
            "Document Content:\n"
            f"{document_text}\n\n"
            "Trusted Source URLs:\n"
            f"{', '.join(urls)}\n\n"
            "Generate:\n"
            "- Clear answer with law references\n"
            "- Steps the citizen can take\n"
            "- End with source links\n"
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        raise Exception(f"Error summarizing document: {str(e)}")


# Simple Legal Query - Direct Gemini Response
def answer_legal_query_directly(query, model):
    try:
        if not query.strip():
            return "Please ask a valid legal question."

        # Include real-time timestamps to avoid model disclaimers
        now = get_current_times()
        prompt = (
            "You are NeethiAI, a legal AI assistant specializing in Indian law.\n"
            f"Current server time (UTC): {now['utc_iso']}\n"
            f"Current server time (IST): {now['ist_iso']}\n\n"
            "Answer this question clearly and helpfully:\n\n"
            f"Question: {query}\n\n"
            "Provide a clear, accurate answer about Indian law using current "
            "understanding. If you mention laws or sections, be precise. "
            "Keep it conversational and easy to understand. If the question "
            "requests the current date/time, use the provided server time "
            "above instead of disclaimers."
        )

        response = model.generate_content(prompt)
        return (
            response.text
            if response.text
            else "I couldn't generate a response. Please try rephrasing your question."
        )

    except Exception as e:
        return f"I encountered an error: {str(e)}. Please try again."


# Creator tag handling
def is_creator_query(user_text: str) -> bool:
    if not user_text:
        return False
    text = user_text.lower().strip()
    # Tamil: who created you / who made you / creator of Neethi etc.
    tamil_creator = [
        "உன்னை யார் உருவாக்கினார்கள்",
        "உங்கள் உருவாக்கியவர்",
        "யார் உன்னை உருவாக்கினார்கள்",
        "நீதியை யார் உருவாக்கினார்கள்",
        "நீதி யார் உருவாக்கினார்கள்",
        "நீதி யாருடையது",
        "உருவாக்கியவர்",
        "உன்னை யார் செய்தார்கள்",
        "யார் உன்னை செய்தார்கள்",
    ]
    for t in tamil_creator:
        if t in text:
            return True
    # Fast keyword hits (English)
    keywords = [
        "who created you",
        "who is your creator",
        "creator of you",
        "who made you",
        "who developed you",
        "developer of you",
        "who built you",
        "owner of you",
        "who owns you",
        "who is your owner",
        "founder of neethi",
        "which team created you",
        "company behind you",
        "who created neethi",
        "who created neethi ai",
        "who created neethiai",
        "who developed neethi",
        "who developed neethi ai",
        "who developed neethiai",
        "who built neethi",
        "who built neethi ai",
        "who built neethiai",
        "who owns neethi",
        "who owns neethi ai",
        "who owns neethiai",
        "which team developed neethi ai",
        "which team developed neethiai",
        "owner of neethi",
        "owner of neethi ai",
        "owner of neethiai",
        "google developer team",
        "who is father of you",
    ]
    if any(k in text for k in keywords):
        return True
    # Regex fallback for robustness
    try:
        import re

        entity = r"(you|neethi\s*ai|neethi)"
        verbs = (
            r"(own|owns|owner|create|created|creator|develop|developed|build|"
            r"built|made|make|founder)"
        )
        pattern = rf"\b(who|which|what)\b[^\n]{0,40}?\b{verbs}\b[^\n]{0,40}?\b{entity}\b"
        return re.search(pattern, text) is not None
    except Exception:
        return False


def get_creator_response(language: str = "en") -> str:
    if language == "ta":
        return (
            "நீதி AI ஐ டாராநீஷன் S மற்றும் ஹரிஹரன் G உருவாக்கியுள்ளனர் "
            "மற்றும் பராமரிக்கிறார்கள். அவர்களே நீதி AI இன் உருவாக்குநர்கள்/உரிமையாளர்கள்."
        )
    return (
        "NeethiAI was created and is maintained by Dharaanishan S and Hariharan G. "
        "They are the developers/owners behind NeethiAI."
    )


# Tax Advisory
def get_tax_advice(user_query, model):
    try:
        if not user_query.strip():
            raise Exception("Query cannot be empty.")
        system_prompt = (
            "You are a certified Indian tax consultant AI assistant. "
            "Answer the user's question in a clear, structured way using the "
            "latest tax laws and budget updates. Include the following "
            "sections:\n\n"
            "1. **User Query**\n"
            "2. **Applicable Tax Regime & Slab**\n"
            "3. **Total Tax Payable (with calculation)**\n"
            "4. **Possible Deductions / Tax Saving Tips**\n"
            "5. **Summary Advice**\n"
            "6. **Trusted Sources** (include official links like "
            "incometax.gov.in, cbic.gov.in, or cleartax.in)\n"
            "Use Markdown formatting for headings and bold text."
        )
        full_prompt = f"{system_prompt}\n\nUser: {user_query}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        raise Exception(f"Error generating tax advice: {str(e)}")


# Fake Notice Detection
def _is_ocr_error_text(s: str) -> bool:
    """Treat known OCR error/placeholder strings as 'no text' so we can try other engines."""
    if not s or not s.strip():
        return True
    lower = s.strip().lower()
    if len(lower) < 20:
        return False
    errors = (
        "ocr processing failed",
        "unable to extract text",
        "unable to extract sufficient",
        "please ensure the image is clear",
        "please try with a clearer",
    )
    return any(e in lower for e in errors)


def preprocess_image(image):
    # Ensure RGB (PIL Image or RGB numpy)
    if hasattr(image, "mode") and image.mode != "RGB":
        image = image.convert("RGB")
    img = np.array(image)
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img
    # Improve contrast
    gray = cv2.equalizeHist(gray)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def extract_text_easyocr(image):
    global reader
    try:
        import os

        model_dir = os.path.join(os.getcwd(), "easyocr_models")
        os.makedirs(model_dir, exist_ok=True)

        # Use English-only to avoid multilingual checkpoint mismatch (143 vs 127 chars).
        # Init once and reuse so we don't re-load models on every image.
        if reader is None:
            gpu_available = False
            try:
                import torch  # type: ignore

                gpu_available = bool(torch.cuda.is_available())
            except Exception:
                gpu_available = False
            try:
                reader = easyocr.Reader(
                    ["en"],
                    gpu=gpu_available,
                    download_enabled=True,
                    model_storage_directory=model_dir,
                )
                app.logger.info("EasyOCR initialized (en only, gpu=%s)", gpu_available)
            except Exception as e:
                app.logger.warning("EasyOCR GPU init failed: %s, using CPU", e)
                reader = easyocr.Reader(
                    ["en"],
                    gpu=False,
                    download_enabled=True,
                    model_storage_directory=model_dir,
                )
                app.logger.info("EasyOCR initialized (en only, CPU)")

        # Ensure image is 3-channel for EasyOCR (BGR or RGB both work)
        if hasattr(image, "shape") and len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        results = reader.readtext(image, detail=0, paragraph=True)
        text = "\n".join([r.strip() for r in results if isinstance(r, str)])
        # Tesseract fallback inside try when we have little text
        if (not text or len(text.strip()) < 6) and _has_tesseract:
            try:
                if isinstance(image, np.ndarray):
                    pil_img = Image.fromarray(image)
                else:
                    pil_img = Image.fromarray(image)
                t_text = pytesseract.image_to_string(pil_img)
                if t_text and len(t_text.strip()) > len((text or "").strip()):
                    text = t_text
            except Exception:
                pass
        return text
    except Exception as e:
        app.logger.error(f"EasyOCR processing failed: {e}")
        return "OCR processing failed. Please try with a clearer image."


def extract_text_paddle(image: np.ndarray) -> str:
    """Optional PaddleOCR fallback. Accepts RGB numpy image."""
    if not _has_paddleocr:
        return ""
    try:
        use_angle_cls = True
        try:
            import torch as _torch  # type: ignore

            use_gpu = bool(_torch.cuda.is_available())
        except Exception:
            use_gpu = False
        ocr = PaddleOCR(use_angle_cls=use_angle_cls, lang="en", use_gpu=use_gpu)
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if len(image.shape) == 3 else image
        result = ocr.ocr(bgr, cls=True)
        lines = []
        if result:
            for block in result:
                for line in block:
                    if len(line) >= 2 and isinstance(line[1], (list, tuple)):
                        lines.append(str(line[1][0]))
        return "\n".join(
            [line_text.strip() for line_text in lines if line_text and isinstance(line_text, str)]
        )
    except Exception:
        return ""


def detect_text_fraud_features(text: str):
    """Analyze extracted text for fraud indicators and return (score, reasons)."""
    if not text:
        return 0, ["No text extracted"]

    # Suspicious keywords and phrases
    suspicious_keywords = [
        "urgent action",
        "pay immediately",
        "legal threat",
        "court summon",
        "non-bailable",
        "case filed",
        "arrest warrant",
        "pay via wallet",
        "pay via upi",
        "qr code payment",
        "immediate payment",
        "urgent payment",
        "threat",
        "immediate action",
        "legal action",
        "court notice",
    ]

    # Suspicious patterns
    suspicious_patterns = [
        r"pay\s+immediately",
        r"urgent\s+action",
        r"legal\s+threat",
        r"case\s+filed",
        r"non-bailable",
        r"arrest\s+warrant",
        r"pay\s+via\s+(wallet|upi)",
        r"qr\s+code\s+payment",
    ]

    # Check for suspicious keywords
    found_keywords = [kw for kw in suspicious_keywords if kw.lower() in text.lower()]

    # Check for suspicious patterns
    found_patterns = []
    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found_patterns.append(pattern)

    # Check for missing official elements
    missing_elements = []
    if not re.search(r"fir\s+no|gn\s+no|reference\s+no", text, re.IGNORECASE):
        missing_elements.append("No FIR/GN/Reference number")

    if not re.search(r"contact|phone|email|address", text, re.IGNORECASE):
        missing_elements.append("No contact information")

    if not re.search(r"government|ministry|department", text, re.IGNORECASE):
        missing_elements.append("No government department mentioned")

    # Calculate fraud score
    fraud_score = 0
    fraud_reasons = []

    if found_keywords:
        fraud_score += len(found_keywords) * 10
        fraud_reasons.append(f"Suspicious keywords: {', '.join(found_keywords)}")

    if found_patterns:
        fraud_score += len(found_patterns) * 15
        fraud_reasons.append(f"Suspicious patterns: {', '.join(found_patterns)}")

    if missing_elements:
        fraud_score += len(missing_elements) * 5
        fraud_reasons.append(f"Missing elements: {', '.join(missing_elements)}")

    # Check for shortened links (suspicious)
    if re.search(r"bit\.ly|tinyurl|goo\.gl|t\.co", text, re.IGNORECASE):
        fraud_score += 20
        fraud_reasons.append("Contains shortened links (suspicious)")

    # Normalize to 0-60 range reserved for text
    return min(int(fraud_score), 60), fraud_reasons


def analyze_layout(image_rgb: np.ndarray):
    """Heuristic layout analysis without templates. Returns (score_0_20, notes)."""
    notes = []
    try:
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2GRAY)
    except Exception:
        gray = (
            image_rgb if len(image_rgb.shape) == 2 else cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        )
    # Binarize and count text-like contours
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    text_boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) > 50]
    density = sum((bw * bh) for (x, y, bw, bh) in text_boxes) / float(h * w + 1)
    margins_ok = True if any(y < h * 0.1 for (_, y, _, _) in text_boxes) is False else False
    # Heuristics
    score = 0
    if density < 0.05 or density > 0.7:
        score += 8
        notes.append(f"Abnormal text density: {density:.2f}")
    if not margins_ok:
        score += 6
        notes.append("Missing top margin (common in poor edits)")
    if len(text_boxes) < 5:
        score += 4
        notes.append("Too few text regions detected")
    return min(score, 20), notes


def analyze_visual_anomalies(image_rgb: np.ndarray):
    """Simple ELA-based anomaly check. Returns (score_0_20, notes)."""
    try:
        pil = Image.fromarray(cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB))
    except Exception:
        pil = Image.fromarray(image_rgb)
    bio = io.BytesIO()
    try:
        pil.save(bio, "JPEG", quality=90)
        bio.seek(0)
        recompressed = Image.open(bio)
        from PIL import ImageChops as _ImageChops

        ela = _ImageChops.difference(pil.convert("RGB"), recompressed.convert("RGB"))
        stat = np.array(ela).astype(np.float32)
        mean_diff = float(stat.mean())
        # Map mean_diff to 0-20
        score = max(0, min(20, int((mean_diff / 25.0) * 20)))
        notes = [f"ELA mean difference: {mean_diff:.2f}"]
        return score, notes
    except Exception:
        return 0, ["ELA check not applicable"]


def verify_signature_placeholder(image_rgb: np.ndarray):
    """
    Enhanced signature/face verification with basic CNN-like analysis.
    Returns (score_0_10, notes).
    """
    try:
        # Convert to grayscale for analysis
        if len(image_rgb.shape) == 3:
            gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_rgb

        # Detect potential signature regions using edge detection
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find signature-like regions (curved, complex contours)
        signature_regions = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 100:  # Filter small noise
                # Calculate contour complexity
                perimeter = cv2.arcLength(contour, True)
                if perimeter > 0:
                    complexity = area / (perimeter * perimeter)
                    if 0.01 < complexity < 0.1:  # Signature-like complexity
                        signature_regions.append(contour)

        # Analyze signature characteristics
        score = 0
        notes = []

        if len(signature_regions) > 0:
            notes.append(f"Found {len(signature_regions)} potential signature regions")

            # Check for signature-like features
            for region in signature_regions:
                # Check for curved lines (signature characteristic)
                hull = cv2.convexHull(region)
                hull_area = cv2.contourArea(hull)
                region_area = cv2.contourArea(region)

                if region_area > 0:
                    solidity = region_area / hull_area
                    if solidity < 0.7:  # Signatures are typically less solid
                        score += 2
                        notes.append("Detected curved signature-like patterns")
                        break

            # Check for consistent stroke width (handwritten characteristic)
            if len(signature_regions) >= 2:
                score += 1
                notes.append("Multiple signature strokes detected")
        else:
            notes.append("No signature regions detected")
            score += 3  # Penalty for missing signature

        # Check for digital manipulation indicators
        # Look for uniform patterns that might indicate copy-paste
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist_peaks = len([i for i, val in enumerate(hist) if val > hist.mean() * 2])

        if hist_peaks < 5:  # Too few intensity variations
            score += 2
            notes.append("Uniform intensity patterns detected (possible digital manipulation)")

        return min(score, 10), notes

    except Exception as e:
        return 0, [f"Signature verification failed: {str(e)}"]


def detect_fake_notice(text: str, image_rgb: np.ndarray | None = None):
    """Risk-scored pipeline combining text, layout, and visual anomaly analysis.

    Returns (analysis_markdown, risk_level, fraud_score, recommendation).
    """
    # Text features (0-60)
    text_score, text_notes = detect_text_fraud_features(text)

    # Visual/layout (0-40 combined)
    layout_score = 0
    layout_notes = []
    visual_score = 0
    visual_notes = []
    sign_score = 0
    sign_notes = []
    if image_rgb is not None:
        try:
            ls, ln = analyze_layout(image_rgb)
            layout_score, layout_notes = ls, ln
        except Exception:
            layout_notes = ["Layout analysis failed"]
        try:
            vs, vn = analyze_visual_anomalies(image_rgb)
            visual_score, visual_notes = vs, vn
        except Exception:
            visual_notes = ["Visual anomaly analysis failed"]
        try:
            ss, sn = verify_signature_placeholder(image_rgb)
            sign_score, sign_notes = ss, sn
        except Exception:
            sign_notes = ["Signature check failed"]

    # Combine scores (cap 100)
    raw_score = text_score + visual_score + layout_score + sign_score
    fraud_score = min(int(raw_score), 100)

    # Risk mapping
    if fraud_score >= 70:
        risk_level = "HIGH RISK"
        recommendation = (
            "🚨 **Likely FAKE**. Do not pay. Report to cybercrime.gov.in and "
            "verify with issuing department."
        )
    elif fraud_score >= 40:
        risk_level = "MEDIUM RISK"
        recommendation = (
            "⚠️ **Caution**. Cross-check with official helplines and websites before action."
        )
    else:
        risk_level = "LOW RISK"
        recommendation = "✅ Appears legitimate, but verify via official channels before acting."

    analysis_lines = []
    if text_notes:
        analysis_lines.append("Text indicators: " + "; ".join(text_notes))
    if layout_notes:
        analysis_lines.append("Layout check: " + "; ".join(layout_notes))
    if visual_notes:
        analysis_lines.append("Visual anomalies: " + "; ".join(visual_notes))
    if sign_notes:
        analysis_lines.append("Signature/face: " + "; ".join(sign_notes))

    result = f"""
## Fraud Detection Analysis

**Risk Level:** {risk_level} (Score: {fraud_score}/100)

**Analysis:**
{chr(10).join(analysis_lines) if analysis_lines else "No suspicious patterns detected"}

**Recommendation:**
{recommendation}

**What to do next:**
1. Cross-verify with official government websites
2. Contact the mentioned department directly via published numbers
3. If suspicious, report to cybercrime.gov.in
4. Never make payments without verification
"""

    return result, risk_level, fraud_score, recommendation


def calculate_feedback_priority(
    user_feedback: str, verification_type: str, fraud_score: int
) -> int:
    """Calculate priority for feedback based on verification history and fraud score."""
    priority = 1  # Default low priority

    # High priority for incorrect high-risk assessments
    if user_feedback == "incorrect" and fraud_score >= 70:
        priority = 3
    # Medium priority for incorrect medium-risk assessments
    elif user_feedback == "incorrect" and fraud_score >= 40:
        priority = 2
    # Medium priority for partial feedback on high-risk cases
    elif user_feedback == "partial" and fraud_score >= 70:
        priority = 2

    return priority


# Voice Chat Support
def create_voice_chat_interface():
    """Create voice chat interface with HTML/JavaScript"""
    voice_html = """
    <div id="voice-chat-container">
        <button id="start-recording" onclick="startRecording()" style="
            background-color: #003087;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        ">🎤 Start Recording</button>

        <button id="stop-recording" onclick="stopRecording()" style="
            background-color: #dc3545;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
            display: none;
        ">⏹️ Stop Recording</button>

        <button id="play-response" onclick="playResponse()" style="
            background-color: #28a745;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
            display: none;
        ">🔊 Play Response</button>

        <div id="transcript"
             style="margin: 10px 0; padding: 10px; "
                   "border: 1px solid #ddd; border-radius: 5px; "
                   "min-height: 50px;">
            <p>Your speech will appear here...</p>
        </div>

        <div id="response-text"
             style="margin: 10px 0; padding: 10px; "
                   "border: 1px solid #ddd; border-radius: 5px; "
                   "min-height: 50px; display: none;">
            <p>AI response will appear here...</p>
        </div>
    </div>

    <script>
        let recognition;
        let isRecording = false;
        let responseText = '';

        // Initialize speech recognition
        if ('webkitSpeechRecognition' in window) {
            recognition = new webkitSpeechRecognition();
        } else if ('SpeechRecognition' in window) {
            recognition = new SpeechRecognition();
        } else {
            document.getElementById('transcript').innerHTML =
              '<p>Speech recognition not supported in this browser.</p>';
        }

        if (recognition) {
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.lang = 'en-US'; // or 'ta-IN' for Tamil

            recognition.onstart = function() {
                isRecording = true;
                document.getElementById('start-recording').style.display = 'none';
                document.getElementById('stop-recording').style.display = 'inline-block';
                document.getElementById('transcript').innerHTML = '<p>Listening... Speak now.</p>';
            };

            recognition.onresult = function(event) {
                let transcript = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    transcript += event.results[i][0].transcript;
                }
                document.getElementById('transcript').innerHTML =
                  '<p><strong>You said:</strong> ' + transcript + '</p>';

                // Send to backend for processing
                if (event.results[i-1].isFinal) {
                    processVoiceInput(transcript);
                }
            };

            recognition.onend = function() {
                isRecording = false;
                document.getElementById('start-recording').style.display = 'inline-block';
                document.getElementById('stop-recording').style.display = 'none';
            };

            recognition.onerror = function(event) {
                console.error('Speech recognition error:', event.error);
                document.getElementById('transcript').innerHTML =
                  '<p>Error: ' + event.error + '</p>';
            };
        }

        function startRecording() {
            if (recognition && !isRecording) {
                recognition.start();
            }
        }

        function stopRecording() {
            if (recognition && isRecording) {
                recognition.stop();
            }
        }

        function processVoiceInput(transcript) {
            // This would typically send the transcript to your backend
            // For now, we'll just display it
            document.getElementById('response-text').innerHTML =
              '<p><strong>Processing:</strong> ' + transcript + '</p>';
            document.getElementById('response-text').style.display = 'block';

            // In a real implementation, you would send this to your Python backend
            // and get the AI response back
        }

        function playResponse() {
            if ('speechSynthesis' in window && responseText) {
                const utterance = new SpeechSynthesisUtterance(responseText);
                utterance.lang = 'en-US'; // Can be changed to 'ta-IN' for Tamil
                speechSynthesis.speak(utterance);
            }
        }

        // Set response text (called from Python)
        function setResponseText(text) {
            responseText = text;
            document.getElementById('response-text').innerHTML =
              '<p><strong>AI Response:</strong> ' + text + '</p>';
            document.getElementById('play-response').style.display = 'inline-block';
        }
    </script>
    """
    return voice_html


# Offline Cached Handbook for Common FAQs
def get_offline_handbook():
    """Offline cached handbook for common legal FAQs"""
    return {
        "FIR": {
            "question": "What is an FIR and how to file it?",
            "answer": """
**FIR (First Information Report) - Complete Guide**

**What is FIR?**
- FIR is the first information about a cognizable offence given to a police officer
- It is mandatory for police to register FIR for cognizable offences
- It can be filed by the victim, witness, or any person having knowledge of the crime

**How to file FIR:**
1. Go to the nearest police station
2. Provide detailed information about the incident
3. Police must register FIR within 24 hours
4. Get a copy of the FIR with FIR number
5. If refused, approach Superintendent of Police or file online

**Important Points:**
- FIR is free of cost
- No lawyer required to file FIR
- Police cannot refuse to register FIR for cognizable offences
- You can file FIR online in many states

**Sources:** indiankanoon.org, tnpolice.gov.in
            """,
            "sources": ["https://indiankanoon.org", "https://tnpolice.gov.in"],
        },
        "RTI": {
            "question": "How to file RTI application?",
            "answer": """
**RTI (Right to Information) - Complete Guide**

**What is RTI?**
- RTI Act 2005 gives citizens right to access information from public authorities
- Any citizen can seek information from government departments
- Information must be provided within 30 days (48 hours for life/liberty matters)

**How to file RTI:**
1. Identify the concerned public authority
2. Write application in English/Hindi/local language
3. Pay fee of Rs. 10 (cash/postal order/demand draft)
4. Submit to PIO (Public Information Officer)
5. Get acknowledgment receipt

**Online RTI:**
- Can be filed online at rti.gov.in
- Payment through online banking
- Track status online

**Appeal Process:**
- First appeal to First Appellate Authority within 30 days
- Second appeal to Information Commission within 90 days

**Sources:** rti.gov.in, indiankanoon.org
            """,
            "sources": ["https://rti.gov.in", "https://indiankanoon.org"],
        },
        "GST": {
            "question": "GST registration and filing process",
            "answer": """
**GST (Goods and Services Tax) - Complete Guide**

**GST Registration:**
- Mandatory if annual turnover exceeds Rs. 20 lakhs (Rs. 10 lakhs for special category states)
- Can register voluntarily even below threshold
- Registration is free and online

**GST Filing Process:**
1. **GSTR-1:** Monthly return of outward supplies (by 11th of next month)
2. **GSTR-3B:** Monthly summary return (by 20th of next month)
3. **GSTR-9:** Annual return (by 31st December of next year)

**GST Rates:**
- 0%: Essential items
- 5%: Basic necessities
- 12%: Processed food items
- 18%: Most goods and services
- 28%: Luxury items

**Penalties:**
- Late filing: Rs. 200 per day
- Non-registration: 100% of tax amount

**Sources:** gst.gov.in, cbic.gov.in
            """,
            "sources": ["https://gst.gov.in", "https://cbic.gov.in"],
        },
        "Income Tax": {
            "question": "Income Tax filing and deductions",
            "answer": """
**Income Tax - Complete Guide**

**Tax Slabs (FY 2023-24):**
- Up to Rs. 3 lakh: 0%
- Rs. 3-6 lakh: 5%
- Rs. 6-9 lakh: 10%
- Rs. 9-12 lakh: 15%
- Rs. 12-15 lakh: 20%
- Above Rs. 15 lakh: 30%

**Key Deductions:**
- Section 80C: Up to Rs. 1.5 lakh (EPF, PPF, ELSS, etc.)
- Section 80D: Health insurance premium
- Section 80E: Education loan interest
- Section 24: Home loan interest up to Rs. 2 lakh

**Filing Process:**
1. Calculate total income
2. Claim deductions
3. Calculate tax liability
4. File ITR online before July 31st
5. Pay any balance tax

**Penalties:**
- Late filing: Rs. 1,000-5,000
- Non-filing: Up to Rs. 10,000

**Sources:** incometax.gov.in, cleartax.in
            """,
            "sources": ["https://incometax.gov.in", "https://cleartax.in"],
        },
    }


def search_offline_handbook(query):
    """Search offline handbook for quick answers"""
    handbook = get_offline_handbook()
    query_lower = query.lower()

    for key, data in handbook.items():
        if any(word in query_lower for word in [key.lower(), data["question"].lower()]):
            return data

    # Search in question content
    for key, data in handbook.items():
        if any(word in query_lower for word in data["question"].lower().split()):
            return data

    return None


# Citation Gatekeeper
def citation_gatekeeper(response_text, sources):
    """Ensure all responses have at least one official source"""
    if not sources or len(sources) == 0:
        return (
            "⚠️ **Unable to provide response without verified sources.** "
            "Please try rephrasing your question or contact a legal "
            "professional directly."
        )

    # Check if response contains source links
    has_links = any(
        domain in response_text.lower()
        for domain in [".gov.in", ".nic.in", "indiankanoon.org", "prsindia.org"]
    )

    if not has_links and sources:
        # Append sources to response
        response_text += "\n\n**📚 Trusted Sources:**\n"
        for i, source in enumerate(sources[:3], 1):
            response_text += f"{i}. [{source}]({source})\n"

    return response_text


def enhanced_legal_query_with_gatekeeper(query, model, force_language=None):
    """Enhanced legal query with citation gatekeeper and offline handbook"""
    try:
        if not query.strip():
            raise Exception("Query cannot be empty.")

        # First check offline handbook
        offline_result = search_offline_handbook(query)
        if offline_result:
            return citation_gatekeeper(offline_result["answer"], offline_result["sources"])

        # If not found in handbook, search online sources
        # If Tamil, translate query to English for better recall
        working_query = query
        if force_language == "ta" or detect_language(query) == "ta":
            working_query = translate_text(query, "en", model)
        urls = get_legal_sources(working_query)
        if not urls:
            return (
                "⚠️ **No verified sources found for your query.** "
                "Please try rephrasing or contact a legal professional directly."
            )

        for url in urls:
            text = scrape_web_text(url)
            if len(text) > 300:
                # Detect or force language
                language = (
                    force_language if force_language in ["ta", "en"] else detect_language(query)
                )
                lang_prompts = get_language_prompt(language)

                prompt = f"""
{lang_prompts['system']}

**User Question:** {query}

**Relevant Legal Content from Trusted Source:**
{text}

**Instructions:**
- {lang_prompts['response_instruction']}
- Provide clear, actionable advice
- Mention relevant legal sections/acts if found
- Keep response concise and citizen-friendly
- Always end with source verification

**Source:** {url}
"""
                response = model.generate_content(
                    contents=[prompt],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.2, max_output_tokens=1024
                    ),
                )

                # Apply citation gatekeeper
                final_response = citation_gatekeeper(response.text, [url])
                # If Tamil forced, ensure output in Tamil (translate if needed)
                if force_language == "ta" and language != "ta":
                    final_response = translate_text(final_response, "ta", model)
                return final_response

        return (
            "⚠️ **Unable to find reliable legal sources for your query.** "
            "Please try rephrasing or contact a legal professional directly."
        )

    except Exception as e:
        raise Exception(f"Error answering query: {str(e)}")


# Flask Routes
@app.route("/")
def index():
    try:
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return render_template("index.html")
    except Exception:
        # Fallback if there are any issues with authentication
        return f"""
        <html>
        <head><title>NeethiAI</title></head>
        <body>
            <h1>NeethiAI - Legal AI Assistant</h1>
            <p>Application is running. If you see this message, the basic server is working.</p>
            <p>Status: {datetime.utcnow().isoformat()}</p>
            <p><a href="/health">Health Check</a></p>
        </body>
        </html>
        """


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        remember = True if request.form.get("remember") else False
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password")
    # Unified auth page; mode via query string (?mode=register)
    mode = request.args.get("mode", "login")
    return render_template("auth.html", mode=mode)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        password_confirm = request.form.get("password_confirm", "")
        if password_confirm and password != password_confirm:
            flash("Passwords do not match")
            return redirect(url_for("login", mode="register"))
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash("Email already registered")
            return redirect(url_for("login", mode="register"))
        # Create new user
        user = User()
        user.name = name
        user.email = email
        user.password_hash = generate_password_hash(password)
        user.auth_provider = "email"
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))
    # GET → unified page in register mode
    return redirect(url_for("login", mode="register"))


# Google OAuth Routes
@app.route("/login/google")
def google_login():
    # Check if OAuth is available
    if not _has_authlib or not google:
        flash("OAuth authentication is not available. Please use email/password login.")
        return redirect(url_for("login"))

    # Check if Google OAuth is properly configured
    if (
        os.getenv("GOOGLE_CLIENT_ID") == "your-google-client-id"
        or os.getenv("GOOGLE_CLIENT_SECRET") == "your-google-client-secret"
        or not os.getenv("GOOGLE_CLIENT_ID")
        or not os.getenv("GOOGLE_CLIENT_SECRET")
    ):
        flash("Google OAuth is not configured. Please contact the administrator.")
        return redirect(url_for("login"))

    try:
        redirect_uri = url_for("google_callback", _external=True)
        return google.authorize_redirect(redirect_uri)
    except Exception as e:
        flash(f"Google OAuth error: {str(e)}")
        return redirect(url_for("login"))


# GitHub OAuth routes
@app.route("/login/github")
def github_login():
    # Check if OAuth is available
    if not _has_authlib or not github:
        flash("OAuth authentication is not available. Please use email/password login.")
        return redirect(url_for("login"))

    if not os.getenv("GITHUB_CLIENT_ID") or not os.getenv("GITHUB_CLIENT_SECRET"):
        flash("GitHub OAuth is not configured. Please contact the administrator.")
        return redirect(url_for("login"))
    redirect_uri = url_for("github_callback", _external=True)
    return github.authorize_redirect(redirect_uri)


@app.route("/callback/github")
def github_callback():
    # Check if OAuth is available
    if not _has_authlib or not github:
        flash("OAuth authentication is not available.")
        return redirect(url_for("login"))

    try:
        github.authorize_access_token()
        user = github.get("user").json()
        emails = github.get("user/emails").json() or []
        primary_email = next((e["email"] for e in emails if e.get("primary")), user.get("email"))
        if not primary_email:
            flash("Failed to retrieve email from GitHub account")
            return redirect(url_for("login"))
        name = user.get("name") or user.get("login") or "GitHub User"
        user_row = User.query.filter_by(email=primary_email).first()
        if not user_row:
            user_row = User()
            user_row.email = primary_email
            user_row.name = name
            user_row.auth_provider = "github"
            db.session.add(user_row)
            db.session.commit()
        login_user(user_row)
        user_row.last_login = datetime.utcnow()
        db.session.commit()
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"GitHub login failed: {str(e)}")
        return redirect(url_for("login"))


# LinkedIn OAuth routes
@app.route("/login/linkedin")
def linkedin_login():
    # Check if OAuth is available
    if not _has_authlib or not linkedin:
        flash("OAuth authentication is not available. Please use email/password login.")
        return redirect(url_for("login"))

    if not os.getenv("LINKEDIN_CLIENT_ID") or not os.getenv("LINKEDIN_CLIENT_SECRET"):
        flash("LinkedIn OAuth is not configured. Please contact the administrator.")
        return redirect(url_for("login"))
    redirect_uri = url_for("linkedin_callback", _external=True)
    return linkedin.authorize_redirect(redirect_uri)


@app.route("/callback/linkedin")
def linkedin_callback():
    # Check if OAuth is available
    if not _has_authlib or not linkedin:
        flash("OAuth authentication is not available.")
        return redirect(url_for("login"))

    try:
        linkedin.authorize_access_token()
        # Fetch profile and email
        profile = linkedin.get("me?projection=(id,localizedFirstName,localizedLastName)").json()
        email_resp = linkedin.get("emailAddress?q=members&projection=(elements*(handle~))").json()
        email_elements = (email_resp or {}).get("elements", [])
        primary_email = None
        for el in email_elements:
            handle = el.get("handle~") or {}
            if handle.get("emailAddress"):
                primary_email = handle.get("emailAddress")
                break
        if not primary_email:
            flash("Failed to retrieve email from LinkedIn account")
            return redirect(url_for("login"))
        name = (
            f"{profile.get('localizedFirstName','')} {profile.get('localizedLastName','')}".strip()
            or "LinkedIn User"
        )
        user_row = User.query.filter_by(email=primary_email).first()
        if not user_row:
            user_row = User()
            user_row.email = primary_email
            user_row.name = name
            user_row.auth_provider = "linkedin"
            db.session.add(user_row)
            db.session.commit()
        login_user(user_row)
        user_row.last_login = datetime.utcnow()
        db.session.commit()
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"LinkedIn login failed: {str(e)}")
        return redirect(url_for("login"))


@app.route("/callback/google")
def google_callback():
    # Check if OAuth is available
    if not _has_authlib or not google:
        flash("OAuth authentication is not available.")
        return redirect(url_for("login"))

    try:
        token = google.authorize_access_token()
        user_info = token.get("userinfo")

        if not user_info:
            flash("Failed to get user information from Google")
            return redirect(url_for("login"))

        email = user_info.get("email")
        name = user_info.get("name")
        google_id = user_info.get("sub")
        profile_picture = user_info.get("picture")

        if not email or not name:
            flash("Incomplete user information from Google")
            return redirect(url_for("login"))

        # Check if user exists
        user = User.query.filter_by(email=email).first()

        if not user:
            # Create new user
            user = User()
            user.email = email
            user.name = name
            user.google_id = google_id
            user.profile_picture = profile_picture
            user.auth_provider = "google"
            db.session.add(user)
            db.session.commit()
        else:
            # Update existing user with Google info
            user.google_id = google_id
            user.profile_picture = profile_picture
            user.auth_provider = "google"
            db.session.commit()

        # Login user
        login_user(user)
        user.last_login = datetime.utcnow()
        db.session.commit()

        return redirect(url_for("dashboard"))
    except Exception as e:
        print(f"Google OAuth error: {str(e)}")  # Log for debugging
        flash("Google login failed. Please try again or contact support.")
        return redirect(url_for("login"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    # Get recent chats
    recent_chats = (
        Chat.query.filter_by(user_id=current_user.id)
        .order_by(Chat.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template("dashboard.html", chats=recent_chats)


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    # Debug: Log the raw request data
    app.logger.info(f"Raw request data: {request.get_data()}")
    app.logger.info(f"Content-Type: {request.content_type}")
    app.logger.info(f"Headers: {dict(request.headers)}")

    data = request.get_json(silent=True) or {}
    app.logger.info(f"Parsed JSON data: {data}")

    # Accept multiple request shapes, including encrypted object with plaintext fallback
    raw_question = (
        data.get("question")
        or data.get("message")
        or data.get("prompt")
        or data.get("q")
        or data.get("text")
        or data.get("content")
        or data.get("input")
        or data.get("query")
        or data.get("promptText")
        or data.get("body")
        or ""
    )
    # No E2EE support; ensure question is string
    app.logger.info(f"Raw question extracted: '{raw_question}'")
    # OpenAI-style messages array: pick last user content
    if (not raw_question) and isinstance(data.get("messages"), list):
        try:
            msgs = data.get("messages")
            msgs = msgs if isinstance(msgs, list) else []
            for item in reversed(msgs):
                role = item.get("role") if isinstance(item, dict) else None
                content = item.get("content") if isinstance(item, dict) else None
                if role == "user" and content:
                    raw_question = content
                    break
        except Exception:
            pass
    # Normalize question to string from various shapes
    if isinstance(raw_question, dict):
        raw_question = (
            raw_question.get("text")
            or raw_question.get("content")
            or raw_question.get("message")
            or raw_question.get("value")
            or ""
        )
    elif isinstance(raw_question, list):
        # Join parts if an array of segments
        try:
            raw_question = " ".join([str(p) for p in raw_question if p])
        except Exception:
            raw_question = str(raw_question)
    question = str(raw_question or "").strip()

    # Fallbacks from form, query params, or raw body if JSON missing
    if not question:
        try:
            form_q = (
                request.form.get("question")
                or request.form.get("message")
                or request.form.get("input")
                or request.form.get("text")
                or request.form.get("content")
                or ""
            )
            question = str(form_q or "").strip()
        except Exception:
            pass
    if not question:
        try:
            arg_q = (
                request.args.get("question")
                or request.args.get("q")
                or request.args.get("input")
                or request.args.get("text")
                or request.args.get("content")
                or ""
            )
            question = str(arg_q or "").strip()
        except Exception:
            pass
    if not question:
        try:
            raw_body = request.get_data(as_text=True) or ""
            # If body is plain text, treat as question; if JSON string, ignore
            if raw_body and not raw_body.strip().startswith("{"):
                question = raw_body.strip()
        except Exception:
            pass

    raw_force_lang = data.get("force_language", "")
    force_language = raw_force_lang.strip().lower() if isinstance(raw_force_lang, str) else None
    conversation_id = data.get("conversation_id", None)  # Get conversation ID from frontend

    # Allow empty question only when user has attached a document (requesting summary)
    doc_in_session = bool(session.get("doc_context", "").strip())
    if not question and doc_in_session:
        question = "Summarize this document and explain the main points."
    app.logger.info(f"Final question after all parsing: '{question}'")
    if not question:
        app.logger.error("Question is empty after all parsing attempts")
        return jsonify({"error": "Question cannot be empty"}), 400

    # Get or create conversation
    if conversation_id:
        conversation = Conversation.query.filter_by(
            id=conversation_id, user_id=current_user.id, is_active=True
        ).first()
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
    else:
        # Create new conversation
        conversation_title = question[:50] + "..." if len(question) > 50 else question
        conversation = Conversation(user_id=current_user.id, title=conversation_title)
        db.session.add(conversation)
        # Use flush to obtain PK without triggering a post-commit refresh.
        # With Postgres RLS + connection pooling, a post-commit refresh may occur on
        # a different connection that doesn't yet have app.user_id set, causing
        # SQLAlchemy to think the row "disappeared".
        # Debug (can be removed later): confirm RLS user id is set on this connection.
        try:
            if db.engine.dialect.name == "postgresql":
                v = db.session.execute(text("SELECT current_setting('app.user_id', true)")).scalar()
                app.logger.info(f"RLS app.user_id at conversation insert: {v!r}")
        except Exception:
            pass

        db.session.flush()
        conversation_id = conversation.id
        db.session.commit()

    # Persist session document into conversation so follow-ups in same chat work
    if session.get("doc_context"):
        conversation.document_context = (session.get("doc_context") or "").strip() or None
        session.pop("doc_context", None)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Short-circuit for creator/owner questions (English or Tamil)
    try:
        if is_creator_query(question):
            lang = force_language or detect_language(question)
            answer = get_creator_response(language=lang if lang in ("ta", "en") else "en")
            sources = []
            feature_used = "about_creator"
            chat = Chat(
                user_id=current_user.id,
                question=question,
                answer=answer,
                sources=json.dumps(sources),
                language=lang if lang in ("ta", "en") else "en",
                feature_used=feature_used,
                conversation_id=conversation_id,
            )
            db.session.add(chat)
            db.session.commit()
            return jsonify(
                {
                    "answer": answer,
                    "sources": sources,
                    "chat_id": chat.id,
                    "conversation_id": conversation_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
    except Exception:
        # If anything goes wrong, fall back to normal flow
        pass

    # Prepare defaults to avoid UnboundLocalError in later branches
    answer = None
    sources = []
    feature_used = "legal_qa"

    def is_pure_datetime_query(q: str) -> bool:
        """Return True only when the user is clearly asking for date/time itself."""
        ql = (q or "").lower()

        # If the question mentions legal/tax or news/trending concepts,
        # don't treat as pure date/time
        negative_markers = [
            # legal / tax / finance
            "gst",
            "tax",
            "budget",
            "legal",
            "law",
            "section",
            "act",
            "ipc",
            "court",
            "fine",
            "penalty",
            "crime",
            "offence",
            "offense",
            "notice",
            "document",
            "contract",
            "agreement",
            "regime",
            "slab",
            "income",
            "deduction",
            "refund",
            "return filing",
            # news / trends
            "news",
            "headline",
            "trending",
            "trend",
            "update",
            "latest",
            "recent",
        ]
        if any(k in ql for k in negative_markers):
            return False

        # If the question contains a year or digits, assume it's not just "what's the time"
        if re.search(r"\d", ql):
            return False

        # Strong positive patterns for "tell me the date/time"
        positive_phrases = [
            "what is the date",
            "what's the date",
            "today's date",
            "today date",
            "current date",
            "today date please",
            "current time",
            "time now",
            "what is the time",
            "what's the time",
            "which day is today",
            "what day is today",
            "day of week",
        ]
        if any(p in ql for p in positive_phrases):
            return True

        # Very short queries with just 'date', 'time', 'day', or 'today'
        tokens = [t for t in re.split(r"\s+", ql.strip()) if t]
        if len(tokens) <= 3 and any(t in ["date", "time", "today", "day", "now"] for t in tokens):
            return True

        return False

    # Handle explicit date/time–only questions
    try:
        if is_pure_datetime_query(question):
            # Get current time information
            times = get_current_times()

            # Get news if requested
            news_items = []
            if any(
                keyword in question.lower() for keyword in ["news", "update", "latest", "recent"]
            ):
                try:
                    news_items = fetch_official_news()
                except Exception as e:
                    app.logger.warning(f"Failed to fetch news: {e}")
                    news_items = []
            # If user also asked about GST/Tax/Budget, include filtered updates
            try:
                ql = question.lower()
                if any(k in ql for k in ["gst", "tax", "budget"]):
                    enriched = fetch_official_news()
                    keys = ["gst", "tax", "budget"]
                    news_items = [
                        it
                        for it in enriched
                        if any(k in (it.get("title", "") or "").lower() for k in keys)
                    ] + news_items
            except Exception as e:
                app.logger.warning(f"Failed to enrich time response with topical news: {e}")

            # Create comprehensive response
            answer = "📅 **Current Date & Time:**\n\n"
            answer += f"**UTC Time:** {times['utc_iso']}\n"
            answer += f"**IST Time:** {times['ist_iso']}\n"
            answer += f"**Epoch (ms):** {times['epoch_ms']}\n\n"

            if news_items:
                answer += "📰 **Latest News Updates:**\n\n"
                for i, item in enumerate(news_items[:5], 1):
                    answer += f"{i}. **{item['title']}**\n"
                    src = item.get("source") or ""
                    if src:
                        answer += f"   Source: {src}\n"
                    answer += f"   Published: {item['published']}\n\n"

            answer += "💡 *This information is updated in real-time from the server.*"

            sources = []
            feature_used = "date_time"

            # Save to database only for date/time questions
            chat = Chat(
                user_id=current_user.id,
                question=question,
                answer=answer,
                sources=json.dumps(sources),
                language="en",
                feature_used=feature_used,
                conversation_id=conversation_id,
            )
            db.session.add(chat)
            db.session.commit()

            return jsonify(
                {
                    "answer": answer,
                    "sources": sources,
                    "chat_id": chat.id,
                    "conversation_id": conversation_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
    except Exception as e:
        app.logger.warning(f"Date/time handling failed: {e}")
        db.session.rollback()
        # Continue to normal flow

    try:
        # Get Gemini model
        model = configure_gemini_api()
        if not model:
            return jsonify({"error": "AI service unavailable"}), 500

        # Determine answer language:
        # 1) Explicit hint in the question ("in tamil"/"in english") wins
        # 2) Otherwise, use force_language if provided
        # 3) Otherwise, auto-detect from the question text
        ql = question.lower()
        hint_language = None
        if " in tamil" in ql or ql.endswith(" in tamil"):
            hint_language = "ta"
        elif " in english" in ql or ql.endswith(" in english"):
            hint_language = "en"

        if hint_language in ["ta", "en"]:
            language = hint_language
        elif force_language in ["ta", "en"]:
            language = force_language
        else:
            language = detect_language(question)
        # Inject current server time so the model can answer "today" correctly
        try:
            _times = get_current_times()
            current_time_note = (
                f"\n\n[Server Time] UTC: {_times['utc_iso']} | "
                f"IST: {_times['ist_iso']} | epoch_ms: {_times['epoch_ms']}\n"
            )
        except Exception:
            current_time_note = "\n\n[Server Time unavailable]\n"
        doc_ctx = (conversation.document_context or session.get("doc_context") or "").strip()
        if doc_ctx:
            try:
                # Prefer summarization when user asks for summary / overview
                ql = question.lower().strip()
                summary_phrases = (
                    "summarize this document",
                    "summarize this",
                    "document summary",
                    "summary of this",
                    "what is this document about",
                    "summarize",
                    "give me a summary",
                    "main points",
                )
                if any(p in ql for p in summary_phrases) or len(ql.split()) <= 4:
                    try:
                        urls = get_legal_sources(question)
                    except Exception:
                        urls = []
                    answer = summarize_legal_issue(doc_ctx, question, urls or [], model)
                    sources = urls or []
                    feature_used = "document_analysis"
                else:
                    prompt = (
                        "You are NeethiAI, a legal AI assistant specializing in "
                        "Indian law.\n\n"
                        f"User question: {question}\n\n"
                        "Relevant document content:\n"
                        f"{doc_ctx[:8000]}\n\n"
                        "Answer clearly and helpfully. If citing laws/sections, "
                        "be precise. Keep it user-friendly.\n"
                        f"{current_time_note}"
                    )
                    resp = model.generate_content(prompt)
                    answer = resp.text if resp and resp.text else "I couldn't generate a response."
                    try:
                        urls = get_legal_sources(question)
                    except Exception:
                        urls = []
                    sources = urls
                    feature_used = "doc_qa"
            except Exception as e:
                app.logger.warning(f"Document QA failed: {e}")
                try:
                    urls = get_legal_sources(question)
                except Exception:
                    urls = []
                if urls:
                    answer = enhanced_legal_query_with_gatekeeper(
                        question + current_time_note, model, force_language=force_language
                    )
                    sources = urls
                else:
                    answer = answer_legal_query_directly(question + current_time_note, model)
                    sources = []
                feature_used = "legal_qa"
        else:
            urls = get_legal_sources(question)
            if urls:
                answer = enhanced_legal_query_with_gatekeeper(
                    question + current_time_note, model, force_language=force_language
                )
                sources = urls
            else:
                answer = answer_legal_query_directly(question + current_time_note, model)
                sources = []
            feature_used = "legal_qa"

        # Save to database (store plaintext for immediate usability)
        chat = Chat(
            user_id=current_user.id,
            question=question,
            answer=answer or "No response generated",
            sources=json.dumps(sources or []),
            language=language,
            feature_used=feature_used,
            conversation_id=conversation_id,
            chat_encrypted=False,
        )
        try:
            db.session.add(chat)
            db.session.commit()

            # Update conversation timestamp
            conversation.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as db_error:
            app.logger.error(f"Database error: {db_error}")
            db.session.rollback()
            # Return error response instead of crashing
            return jsonify({"error": "Database error occurred. Please try again."}), 500

        return jsonify(
            {
                "answer": answer,
                "sources": sources,
                "chat_id": chat.id,
                "conversation_id": conversation_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        app.logger.error(f"Chat API error: {str(e)}")
        app.logger.error(f"Error type: {type(e).__name__}")
        import traceback

        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": "Sorry, I encountered an error. Please try again."}), 500


@app.route("/api/chat/history")
@login_required
def chat_history():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Get conversations instead of individual chats
    conversations = (
        Conversation.query.filter_by(user_id=current_user.id, is_active=True)
        .order_by(Conversation.updated_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    conversation_data = []
    for conv in conversations.items:
        # Get the first chat in the conversation for preview
        first_chat = (
            Chat.query.filter_by(conversation_id=conv.id).order_by(Chat.created_at.asc()).first()
        )
        chat_count = Chat.query.filter_by(conversation_id=conv.id).count()

        conversation_data.append(
            {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "chat_count": chat_count,
                "preview": first_chat.question if first_chat else conv.title,
            }
        )

    return jsonify(
        {
            "conversations": conversation_data,
            "has_next": conversations.has_next,
            "has_prev": conversations.has_prev,
            "page": page,
            "pages": conversations.pages,
        }
    )


@app.route("/api/conversation/<int:conversation_id>/chats")
@login_required
def get_conversation_chats(conversation_id):
    """Get all chats in a specific conversation."""
    conversation = Conversation.query.filter_by(
        id=conversation_id, user_id=current_user.id, is_active=True
    ).first()
    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    chats = (
        Chat.query.filter_by(conversation_id=conversation_id).order_by(Chat.created_at.asc()).all()
    )

    chat_data = []
    for chat in chats:
        q = chat.question or ""
        a = chat.answer or ""
        sources = json.loads(chat.sources) if chat.sources else []
        chat_data.append(
            {
                "id": chat.id,
                "question": q,
                "answer": a,
                "sources": sources,
                "language": chat.language,
                "feature_used": chat.feature_used,
                "created_at": chat.created_at.isoformat(),
                "is_edited": chat.is_edited,
                "edited_at": chat.edited_at.isoformat() if chat.edited_at else None,
            }
        )

    return jsonify(
        {
            "conversation": {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
            },
            "chats": chat_data,
        }
    )


@app.route("/api/chat/<int:chat_id>")
@login_required
def get_chat(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    q = chat.question or ""
    a = chat.answer or ""
    sources = json.loads(chat.sources) if chat.sources else []
    return jsonify(
        {
            "id": chat.id,
            "question": q,
            "answer": a,
            "sources": sources,
            "language": chat.language,
            "feature_used": chat.feature_used,
            "created_at": chat.created_at.isoformat(),
        }
    )


@app.route("/api/chat/<int:chat_id>/delete", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    """Delete a specific chat message."""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    try:
        db.session.delete(chat)
        db.session.commit()
        return jsonify({"success": True, "message": "Chat deleted successfully"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete chat"}), 500


@app.route("/api/conversation/<int:conversation_id>/delete", methods=["DELETE"])
@login_required
def delete_conversation(conversation_id):
    """Delete an entire conversation (soft delete)."""
    conversation = Conversation.query.filter_by(
        id=conversation_id, user_id=current_user.id, is_active=True
    ).first()
    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    try:
        conversation.is_active = False
        db.session.commit()
        return jsonify({"success": True, "message": "Conversation deleted successfully"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete conversation"}), 500


@app.route("/api/chat/<int:chat_id>/edit", methods=["PUT"])
@login_required
def edit_chat(chat_id):
    """Edit a chat message."""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    data = request.get_json()
    if not data or "question" not in data:
        return jsonify({"error": "Question is required"}), 400

    new_question = data.get("question", "").strip()
    if not new_question:
        return jsonify({"error": "Question cannot be empty"}), 400

    try:
        # Update the question
        chat.question = new_question
        chat.chat_encrypted = False
        chat.chat_iv = None
        chat.chat_tag = None
        chat.is_edited = True
        chat.edited_at = datetime.utcnow()

        # Regenerate answer if requested
        if data.get("regenerate_answer", False):
            try:
                model = configure_gemini_api()
                if model:
                    # Use the same logic as the main chat API
                    language = detect_language(new_question)
                    doc_ctx = session.get("doc_context")
                    if not doc_ctx and chat.conversation_id:
                        conv = Conversation.query.get(chat.conversation_id)
                        if conv and conv.document_context:
                            doc_ctx = conv.document_context

                    if doc_ctx:
                        prompt = f"""
You are NeethiAI, a legal AI assistant specializing in Indian law.

User question: {new_question}

Relevant document content:
{doc_ctx[:8000]}

Answer clearly and helpfully. If citing laws/sections, be precise. Keep it user-friendly.
"""
                        resp = model.generate_content(prompt)
                        new_answer = (
                            resp.text if resp and resp.text else "I couldn't generate a response."
                        )
                        chat.answer = new_answer
                        chat.feature_used = "doc_qa"
                    else:
                        urls = get_legal_sources(new_question)
                        if urls:
                            new_answer = enhanced_legal_query_with_gatekeeper(
                                new_question, model, force_language=language
                            )
                            chat.answer = new_answer
                            chat.sources = json.dumps(urls)
                        else:
                            new_answer = answer_legal_query_directly(new_question, model)
                            chat.answer = new_answer
                            chat.sources = json.dumps([])
                        chat.feature_used = "legal_qa"
                else:
                    new_answer = "AI service is currently unavailable. Please try again later."
                    chat.answer = new_answer
                    chat.sources = json.dumps([])
            except Exception as e:
                app.logger.warning(f"Failed to regenerate answer: {e}")
                chat.answer = "Failed to regenerate answer. Please try again."

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Chat updated successfully",
                "chat": {
                    "id": chat.id,
                    "question": chat.question,
                    "answer": chat.answer,
                    "sources": json.loads(chat.sources) if chat.sources else [],
                    "is_edited": chat.is_edited,
                    "edited_at": chat.edited_at.isoformat() if chat.edited_at else None,
                },
            }
        )
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update chat"}), 500


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html")


@app.route("/api/profile/clear-history", methods=["POST"])
@login_required
def clear_history():
    try:
        Chat.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        # Clear any stored doc context
        session.pop("doc_context", None)
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/profile/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json() or {}
    current = data.get("current_password", "")
    new = data.get("new_password", "")
    if not current or not new:
        return jsonify({"error": "Both current and new passwords are required"}), 400
    user = User.query.filter_by(id=current_user.id).first()
    if not user or not user.password_hash:
        return jsonify({"error": "Password change is not available for this account"}), 400
    if not check_password_hash(user.password_hash, current):
        return jsonify({"error": "Current password is incorrect"}), 400
    user.password_hash = generate_password_hash(new)
    db.session.commit()
    return jsonify({"ok": True})


# Forgot password inline flow, reuse unified auth page
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your email")
            return render_template("auth.html", mode="forgot")
        # In production: issue token + send email
        flash("If this email exists, a reset link has been sent.")
        return redirect(url_for("login"))
    return render_template("auth.html", mode="forgot")


@app.route("/api/profile/export", methods=["GET"])
@login_required
def export_chats():
    chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.created_at.asc()).all()
    export = []
    for c in chats:
        export.append(
            {
                "id": c.id,
                "question": c.question,
                "answer": c.answer,
                "sources": json.loads(c.sources) if c.sources else [],
                "language": c.language,
                "feature_used": c.feature_used,
                "created_at": c.created_at.isoformat(),
            }
        )
    return jsonify({"chats": export})


@app.route("/health")
def health_check():
    """Health check endpoint for Render"""
    try:
        # Test database connection
        db_status = "connected"
        try:
            with app.app_context():
                db.session.execute(db.text("SELECT 1"))
        except Exception:
            db_status = "not_connected"

        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "database": db_status,
                "flask": "running",
                "version": "1.0.0",
            }
        )
    except Exception as e:
        return (
            jsonify(
                {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
            ),
            500,
        )


# --- Time utilities & endpoints ---
def get_current_times():
    """Return current timestamps in UTC and IST (Asia/Kolkata)."""
    now_utc = datetime.now(timezone.utc)
    if _has_zoneinfo:
        ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    else:
        # Fallback fixed offset for IST (+05:30)
        ist = now_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
    return {
        "utc_iso": now_utc.isoformat(),
        "ist_iso": ist.isoformat(),
        "epoch_ms": int(now_utc.timestamp() * 1000),
    }


@app.route("/api/time")
def api_time():
    """Return server time in UTC and IST to enable real-time answers on the client."""
    return jsonify(get_current_times())


# OCR benchmark endpoint (basic)
@app.route("/api/bench/ocr", methods=["POST"])
@login_required
def bench_ocr():
    try:
        import time

        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        f = request.files["file"]
        raw = f.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        arr = np.array(img)
        t0 = time.time()
        _ = extract_text_easyocr(arr)
        t1 = time.time()
        paddle_ms = None
        if _has_paddleocr:
            t2 = time.time()
            _ = extract_text_paddle(arr)
            t3 = time.time()
            paddle_ms = int((t3 - t2) * 1000)
        return jsonify({"easyocr_ms": int((t1 - t0) * 1000), "paddleocr_ms": paddle_ms})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Official news (RSS) endpoint ---
def fetch_rss_items(url, max_items=5):
    """Best-effort RSS fetcher using requests + BeautifulSoup (no external feedparser).
    Returns list of {title, link, published}.
    """
    try:
        headers = {"User-Agent": "NeethiAI/1.0 (+https://neethi.ai)"}
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.content.decode("utf-8"), "xml")
        items = []
        for item in soup.find_all("item")[:max_items]:
            title = (item.title.get_text(strip=True) if item.title else "").strip()
            link = (item.link.get_text(strip=True) if item.link else "").strip()
            pub = ""
            if item.pubDate:
                pub = item.pubDate.get_text(strip=True)
            elif item.find("updated"):
                pub = item.find("updated").get_text(strip=True)
            items.append({"title": title, "link": link, "published": pub})
        # Atom fallback (<entry>)
        if not items:
            for entry in soup.find_all("entry")[:max_items]:
                title = (entry.title.get_text(strip=True) if entry.title else "").strip()
                link_tag = entry.find("link")
                href = link_tag.get("href") if link_tag and link_tag.has_attr("href") else ""
                updated = entry.updated.get_text(strip=True) if entry.find("updated") else ""
                items.append({"title": title, "link": href, "published": updated})
        return items
    except Exception:
        return []


@app.route("/api/news")
def api_news():
    """Aggregate headlines from official Indian government and regulator RSS feeds.
    Sources are limited to .gov.in/.nic.in and apex bodies.
    """
    feeds = [
        # Press Information Bureau (PIB)
        "https://pib.gov.in/rssall.aspx",
        # RBI Press Releases
        "https://www.rbi.org.in/Rss/PressReleaseRss.aspx",
        # CBIC (indirect taxes) news
        "https://www.cbic.gov.in/htdocs-cbec/rss.xml",
        # India Portal (news)
        "https://www.india.gov.in/news_feeds?output=rss",
    ]
    aggregated = []
    for f in feeds:
        aggregated.extend(fetch_rss_items(f, max_items=5))
    # De-duplicate by link
    seen = set()
    unique = []
    for it in aggregated:
        key = it.get("link") or it.get("title")
        if key and key not in seen:
            seen.add(key)
            unique.append(it)
    return jsonify({"generated_at": get_current_times(), "count": len(unique), "items": unique})


def fetch_official_news():
    """Helper function to fetch official news items."""
    feeds = [
        "https://pib.gov.in/rssall.aspx",
        "https://www.rbi.org.in/Rss/PressReleaseRss.aspx",
        "https://www.cbic.gov.in/htdocs-cbec/rss.xml",
        "https://www.india.gov.in/news_feeds?output=rss",
    ]
    aggregated = []
    for f in feeds:
        aggregated.extend(fetch_rss_items(f, max_items=5))

    # De-duplicate by link
    seen = set()
    unique = []
    for it in aggregated:
        key = it.get("link") or it.get("title")
        if key and key not in seen:
            seen.add(key)
            unique.append(it)

    return unique[:10]  # Return top 10 items


# Additional API Routes
@app.route("/api/upload/document", methods=["POST"])
@login_required
def upload_document():
    if "file" not in request.files:
        app.logger.error("Upload error: no file part in request")
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        app.logger.error("Upload error: empty filename")
        return jsonify({"error": "No file selected"}), 400

    try:
        # Ensure stream is at start
        try:
            file.stream.seek(0)
        except Exception:
            pass

        if file.filename and file.filename.lower().endswith(".pdf"):
            text = extract_text_from_pdf(file.stream)
        elif file.filename and file.filename.lower().endswith(".docx"):
            text = extract_text_from_docx(file.stream)
        else:
            return jsonify({"error": "Unsupported file type"}), 400

        # Store document context in the session for later chat questions.
        # This lets the user upload first, then press "Send" in chat with their query.
        session["doc_context"] = text or ""

        # Do NOT auto-create a chat message or auto-summarize here.
        # Frontend can choose to call /api/chat with a user question that uses this context.
        return jsonify(
            {
                "ok": True,
                "text": text,
                "length": len(text or ""),
                "message": (
                    "Document uploaded and ready. Ask your question in chat " "when you’re ready."
                ),
            }
        )
    except Exception as e:
        app.logger.exception("Upload document failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/detect/fake-notice", methods=["POST"])
@login_required
def detect_fake_notice_api():
    if "file" not in request.files:
        app.logger.error("Fake-notice upload error: no file part")
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        app.logger.error("Fake-notice upload error: empty filename")
        return jsonify({"error": "No file selected"}), 400

    # Optional: link to current conversation for follow-up questions
    conv_id_raw = request.form.get("conversation_id")
    conversation_id = None
    if conv_id_raw:
        try:
            conversation_id = int(conv_id_raw)
        except (TypeError, ValueError):
            pass

    try:
        # Read raw bytes once for reliability across WSGI servers
        try:
            raw_bytes = file.read()
        except Exception:
            raw_bytes = None
        if not raw_bytes:
            try:
                file.stream.seek(0)
                raw_bytes = file.stream.read()
            except Exception:
                raw_bytes = None
        if not raw_bytes:
            app.logger.error("Fake notice: empty file stream after read")
            return jsonify({"error": "Could not read uploaded image"}), 400

        # Create a fresh BytesIO for PIL
        img_io = io.BytesIO(raw_bytes)

        if file.filename and file.filename.lower().endswith((".jpg", ".jpeg", ".png")):
            image = Image.open(img_io)
            if image is None:
                return jsonify({"error": "Could not open image"}), 400
            try:
                from PIL import ImageOps

                image = ImageOps.exif_transpose(image) or image
            except Exception:
                pass
            if image is None:
                return jsonify({"error": "Could not process image"}), 400
            # Keep higher resolution for documents (e.g. legal letters)
            max_side = 2400
            if max(image.size) > max_side:
                scale = max_side / max(image.size)
                new_size = (int(image.size[0] * scale), int(image.size[1] * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            elif max(image.size) < 400:
                scale = 400.0 / max(image.size)
                new_size = (int(image.size[0] * scale), int(image.size[1] * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            if image.mode != "RGB":
                image = image.convert("RGB")
            np_img = np.array(image)

            def _usable(t):  # noqa: ANN001
                if not t or not isinstance(t, str):
                    return False
                return len(t.strip()) >= 10 and not _is_ocr_error_text(t)

            text = ""
            try:
                t0 = extract_text_easyocr(np_img)
                if _usable(t0):
                    text = t0
            except Exception as e:
                app.logger.error(f"EasyOCR failed: {e}")

            if not _usable(text):
                try:
                    processed = preprocess_image(image)
                    if len(processed.shape) == 2:
                        processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)
                    t1 = extract_text_easyocr(processed)
                    s1 = (t1 or "").strip()
                    if _usable(t1) and len(s1) > len(text or ""):
                        text = t1 or ""
                except Exception as e:
                    app.logger.error(f"Preprocessed OCR failed: {e}")

            if not _usable(text):
                try:
                    gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
                    enhanced = cv2.equalizeHist(gray)
                    enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
                    t2 = extract_text_easyocr(enhanced_rgb)
                    s2 = (t2 or "").strip()
                    if _usable(t2) and len(s2) > len(text or ""):
                        text = t2 or ""
                except Exception as e:
                    app.logger.error(f"Enhanced OCR failed: {e}")

            if not _usable(text) and _has_tesseract:
                try:
                    t3 = pytesseract.image_to_string(image)
                    s3 = (t3 or "").strip()
                    if _usable(t3) and len(s3) > len(text or ""):
                        text = t3 or ""
                except Exception as e:
                    app.logger.error(f"Tesseract failed: {e}")

            if not _usable(text) and _has_paddleocr:
                try:
                    t4 = extract_text_paddle(np_img)
                    s4 = (t4 or "").strip()
                    if _usable(t4) and len(s4) > len(text or ""):
                        text = t4 or ""
                except Exception as e:
                    app.logger.error(f"PaddleOCR failed: {e}")

            if not _usable(text):
                text = ""
        elif file.filename and file.filename.lower().endswith(".pdf"):
            # Reuse the raw bytes for PDF parsing
            text = extract_text_from_pdf(io.BytesIO(raw_bytes))
        elif file.filename and file.filename.lower().endswith(".docx"):
            text = extract_text_from_docx(io.BytesIO(raw_bytes))
        else:
            app.logger.error(f"Unsupported file type: {file.filename}")
            return jsonify({"error": "Unsupported file type"}), 400

        app.logger.info(f"Extracted text length: {len(text) if text else 0}")
        app.logger.info(f'Extracted text preview: {text[:200] if text else "No text"}')

        if not text or len(text.strip()) < 5:
            app.logger.warning("Very little text extracted from image")
            result_text = (
                "⚠️ **Unable to extract sufficient text from the image.**\n\n"
                "**Possible reasons:**\n"
                "- Image quality is too low\n"
                "- Text is too small or blurry\n"
                "- Image format not supported\n"
                "- No text present in image\n\n"
                "**Please try:**\n"
                "- Using a higher quality image\n"
                "- Ensuring text is clearly visible\n"
                "- Using JPG, PNG, or PDF format"
            )
            risk_level = "UNKNOWN"
            fraud_score = 0
            recommendation = "Upload a clearer image for analysis"
            sources = []
        else:
            try:
                result_text, risk_level, fraud_score, recommendation = detect_fake_notice(text)
            except Exception:
                app.logger.exception("detect_fake_notice failed")
                result_text = (
                    "Analysis could not be completed. Please try again with a "
                    "clearer image or document."
                )
                risk_level = "UNKNOWN"
                fraud_score = 0
                recommendation = "Retry with a clearer upload."
            try:
                sources = get_legal_sources("fake legal notice")
            except Exception as e:
                app.logger.warning(f"Failed to get legal sources: {e}")
                sources = []

        # Get or create conversation so follow-ups about this notice work
        conv = None
        if conversation_id:
            conv = Conversation.query.filter_by(
                id=conversation_id, user_id=current_user.id, is_active=True
            ).first()
        if not conv:
            conv = Conversation(
                user_id=current_user.id,
                title="[Fake Notice] " + (file.filename or "Image checked"),
            )
            db.session.add(conv)
            db.session.flush()
        conv.document_context = (text or "").strip() or None
        conv.updated_at = datetime.utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        # Save analysis to chat history (linked to conversation)
        try:
            saved = Chat(
                user_id=current_user.id,
                question="[Fake Notice] " + (file.filename or "Image checked"),
                answer=result_text,
                sources=json.dumps(sources),
                language="en",
                feature_used="fake_notice",
                conversation_id=conv.id,
            )
            db.session.add(saved)
            db.session.commit()
            chat_id = saved.id
            app.logger.info(f"Fake notice analysis saved with chat_id: {chat_id}")
        except Exception as e:
            app.logger.error(f"Failed to save fake notice analysis: {e}")
            chat_id = None

        return jsonify(
            {
                "text": text,
                "result": result_text,
                "risk_level": risk_level,
                "fraud_score": fraud_score,
                "recommendation": recommendation,
                "sources": sources,
                "chat_id": chat_id,
                "conversation_id": conv.id,
            }
        )
    except Exception as e:
        app.logger.exception("Fake notice detection failed")
        err_msg = str(e) if str(e) else "Fake notice detection failed. Please try again."
        return jsonify({"error": err_msg}), 500


@app.route("/api/feedback/verification", methods=["POST"])
@login_required
def submit_verification_feedback():
    """Submit feedback for verification results."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ["chat_id", "verification_type", "user_feedback", "original_result"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Get the original chat record
        chat = Chat.query.filter_by(id=data["chat_id"], user_id=current_user.id).first()
        if not chat:
            return jsonify({"error": "Chat record not found"}), 404

        # Calculate priority based on feedback and fraud score
        fraud_score = data.get("fraud_score", 0)
        priority = calculate_feedback_priority(
            data["user_feedback"], data["verification_type"], fraud_score
        )

        # Create feedback record
        feedback = VerificationFeedback(
            user_id=current_user.id,
            chat_id=data["chat_id"],
            verification_type=data["verification_type"],
            original_result=data["original_result"],
            user_feedback=data["user_feedback"],
            feedback_details=data.get("feedback_details", ""),
            priority=priority,
        )

        db.session.add(feedback)
        db.session.commit()

        app.logger.info(f"Verification feedback submitted: ID={feedback.id}, Priority={priority}")

        return jsonify(
            {
                "success": True,
                "feedback_id": feedback.id,
                "priority": priority,
                "message": (
                    "Feedback submitted successfully. Thank you for helping " "improve our system!"
                ),
            }
        )

    except Exception:
        app.logger.exception("Failed to submit verification feedback")
        return jsonify({"error": "Failed to submit feedback"}), 500


@app.route("/api/feedback/admin", methods=["GET"])
@login_required
def get_admin_feedback():
    """Get feedback for admin review (requires admin privileges)."""
    try:
        # Check if user is admin (you can implement proper admin check)
        if not current_user.email.endswith("@admin.neethiai.com"):  # Simple admin check
            return jsonify({"error": "Admin access required"}), 403

        # Get pending feedback ordered by priority
        feedback_list = (
            VerificationFeedback.query.filter_by(status="pending")
            .order_by(VerificationFeedback.priority.desc(), VerificationFeedback.timestamp.desc())
            .limit(50)
            .all()
        )

        feedback_data = []
        for fb in feedback_list:
            feedback_data.append(
                {
                    "id": fb.id,
                    "user_id": fb.user_id,
                    "chat_id": fb.chat_id,
                    "verification_type": fb.verification_type,
                    "user_feedback": fb.user_feedback,
                    "feedback_details": fb.feedback_details,
                    "priority": fb.priority,
                    "timestamp": fb.timestamp.isoformat(),
                    "original_result": (
                        fb.original_result[:200] + "..."
                        if len(fb.original_result) > 200
                        else fb.original_result
                    ),
                }
            )

        return jsonify(
            {"success": True, "feedback": feedback_data, "total_pending": len(feedback_data)}
        )

    except Exception:
        app.logger.exception("Failed to get admin feedback")
        return jsonify({"error": "Failed to retrieve feedback"}), 500


@app.route("/api/feedback/admin/<int:feedback_id>", methods=["POST"])
@login_required
def respond_to_feedback(feedback_id):
    """Admin response to feedback."""
    try:
        # Check admin privileges
        if not current_user.email.endswith("@admin.neethiai.com"):
            return jsonify({"error": "Admin access required"}), 403

        data = request.get_json()
        if not data or "admin_response" not in data:
            return jsonify({"error": "Admin response required"}), 400

        feedback = VerificationFeedback.query.get(feedback_id)
        if not feedback:
            return jsonify({"error": "Feedback not found"}), 404

        feedback.admin_response = data["admin_response"]
        feedback.status = data.get("status", "reviewed")
        if feedback.status == "resolved":
            feedback.resolved_at = datetime.utcnow()

        db.session.commit()

        app.logger.info(f"Admin responded to feedback ID={feedback_id}")

        return jsonify({"success": True, "message": "Response submitted successfully"})

    except Exception:
        app.logger.exception("Failed to respond to feedback")
        return jsonify({"error": "Failed to submit response"}), 500


@app.route("/api/tax/advice", methods=["POST"])
@login_required
def tax_advice():
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400

    try:
        model = configure_gemini_api()
        if not model:
            return jsonify({"error": "AI service unavailable"}), 500
        advice = get_tax_advice(query, model)
        sources = get_legal_sources("tax advisory", fast=False)
        return jsonify({"advice": advice, "sources": sources})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tax/calc/income", methods=["POST"])
@login_required
def tax_calc_income():
    data = request.get_json() or {}
    try:
        taxable_income = float(data.get("income", 0))
    except Exception:
        return jsonify({"error": "income must be a number"}), 400
    regime = (data.get("regime") or "new").strip().lower()  # 'new' or 'old'
    include_cess = bool(data.get("include_cess", True))

    # Basic slab calculation (FY 2024-25) for individuals; slabs from incometax.gov.in
    def compute_new_regime(amount: float) -> dict:
        slabs = [
            (0, 300000, 0.00),
            (300000, 600000, 0.05),
            (600000, 900000, 0.10),
            (900000, 1200000, 0.15),
            (1200000, 1500000, 0.20),
            (1500000, float("inf"), 0.30),
        ]
        breakdown = []
        tax = 0.0
        for lower, upper, rate in slabs:
            if amount <= lower:
                break
            band = min(amount, upper) - lower
            piece = max(0.0, band) * rate
            tax += max(0.0, piece)
            breakdown.append(
                {
                    "from": lower,
                    "to": upper if upper != float("inf") else None,
                    "rate": rate,
                    "tax": round(max(0.0, piece), 2),
                }
            )
        return {"tax": round(tax, 2), "breakdown": breakdown}

    def compute_old_regime(amount: float) -> dict:
        slabs = [
            (0, 250000, 0.00),
            (250000, 500000, 0.05),
            (500000, 1000000, 0.20),
            (1000000, float("inf"), 0.30),
        ]
        breakdown = []
        tax = 0.0
        for lower, upper, rate in slabs:
            if amount <= lower:
                break
            band = min(amount, upper) - lower
            piece = max(0.0, band) * rate
            tax += max(0.0, piece)
            breakdown.append(
                {
                    "from": lower,
                    "to": upper if upper != float("inf") else None,
                    "rate": rate,
                    "tax": round(max(0.0, piece), 2),
                }
            )
        return {"tax": round(tax, 2), "breakdown": breakdown}

    calc = compute_new_regime if regime == "new" else compute_old_regime
    result = calc(max(0.0, taxable_income))
    cess = round(result["tax"] * 0.04, 2) if include_cess else 0.0
    total = round(result["tax"] + cess, 2)
    sources = get_legal_sources(
        "Income tax slabs site:incometax.gov.in", max_results=3, fast=False
    ) or [
        "https://www.incometax.gov.in/",
    ]
    return jsonify(
        {
            "regime": "new" if regime == "new" else "old",
            "tax_before_cess": result["tax"],
            "health_education_cess_4pct": cess,
            "total_tax": total,
            "breakdown": result["breakdown"],
            "sources": sources,
        }
    )


@app.route("/api/tax/calc/gst", methods=["POST"])
@login_required
def tax_calc_gst():
    data = request.get_json() or {}
    try:
        amount = float(data.get("amount", 0))
    except Exception:
        return jsonify({"error": "amount must be a number"}), 400
    try:
        rate = float(data.get("rate", 18))  # 0,5,12,18,28
    except Exception:
        return jsonify({"error": "rate must be a number"}), 400
    intra_state = bool(data.get("intra_state", True))
    rate = max(0.0, min(rate, 28.0))
    tax_amount = round(amount * (rate / 100.0), 2)
    if intra_state:
        cgst = round(tax_amount / 2.0, 2)
        sgst = round(tax_amount / 2.0, 2)
        payload = {"cgst": cgst, "sgst": sgst, "igst": 0.0}
    else:
        payload = {"cgst": 0.0, "sgst": 0.0, "igst": tax_amount}
    sources = get_legal_sources(
        "GST rates site:cbic.gov.in OR site:gst.gov.in", max_results=3, fast=False
    ) or [
        "https://www.cbic.gov.in/",
        "https://www.gst.gov.in/",
    ]
    return jsonify(
        {
            "amount": amount,
            "rate_percent": rate,
            "tax_components": payload,
            "total_with_tax": round(amount + tax_amount, 2),
            "sources": sources,
        }
    )


@app.route("/api/tax/budget/summary")
def tax_budget_summary():
    # Summarize budget-related items from official feeds only
    feeds = [
        "https://pib.gov.in/rssall.aspx",
        "https://www.cbic.gov.in/htdocs-cbec/rss.xml",
        "https://www.rbi.org.in/Rss/PressReleaseRss.aspx",
        "https://www.india.gov.in/news_feeds?output=rss",
    ]
    items = []
    for f in feeds:
        items.extend(fetch_rss_items(f, max_items=10))
    # Filter for budget/tax content
    keys = ["budget", "finance", "tax", "gst", "income tax", "direct tax", "indirect tax"]
    filtered = []
    for it in items:
        title = (it.get("title") or "").lower()
        if any(k in title for k in keys):
            filtered.append(it)
    # Summarize titles via model (official links only)
    model_local = configure_gemini_api()
    summary = ""
    if model_local and filtered:
        try:
            joined = "\n".join([f"- {it['title']}" for it in filtered if it.get("title")])
            prompt = (
                "Summarize the following official budget/tax updates for "
                "Indian taxpayers in 6-10 concise bullet points, plain "
                f"language:\n\n{joined}\n\n"
                "Keep neutral tone and avoid speculation."
            )
            resp = model_local.generate_content(prompt)
            summary = resp.text if resp and resp.text else ""
        except Exception:
            summary = ""
    return jsonify(
        {
            "generated_at": get_current_times(),
            "count": len(filtered),
            "summary": summary,
            "items": filtered[:20],
        }
    )


@app.route("/api/handbook/search")
@login_required
def search_handbook():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400

    result = search_offline_handbook(query)

    if result:
        return jsonify(
            {
                "found": True,
                "question": result["question"],
                "answer": result["answer"],
                "sources": result["sources"],
            }
        )
    else:
        return jsonify({"found": False, "message": "No matching entry found in the handbook"})


# Initialize database and run app
if __name__ == "__main__":
    try:
        # Get port from environment variable (Render sets this)
        port = int(os.getenv("PORT", 5000))

        # Check if running in production
        is_production = os.getenv("FLASK_ENV") == "production"

        print(
            f"Starting NeethiAI - Environment: {'Production' if is_production else 'Development'}"
        )
        print(f"Port: {port}")

        # Try to create database tables, but don't fail if database is not available
        try:
            with app.app_context():
                db.create_all()
                # Add document_context to conversation if missing (existing DBs)
                try:
                    dialect = db.engine.dialect.name
                    if dialect == "postgresql":
                        sql = (
                            "ALTER TABLE conversation ADD COLUMN IF NOT EXISTS "
                            "document_context TEXT"
                        )
                    elif dialect == "sqlite":
                        sql = "ALTER TABLE conversation ADD COLUMN document_context TEXT"
                    else:
                        sql = None
                    if sql:
                        db.session.execute(text(sql))
                        db.session.commit()
                except Exception as col_err:
                    err_lower = str(col_err).lower()
                    if "duplicate column" in err_lower or "already exists" in err_lower:
                        pass
                    else:
                        app.logger.warning("Optional migration (document_context): %s", col_err)
                    db.session.rollback()
                _init_postgres_rls_pool_hooks()
                _ensure_postgres_rls()
                print("✓ Database tables created successfully")
        except Exception as e:
            print(f"⚠️ Database connection failed: {e}")
            if is_production:
                print("Starting in production mode with limited functionality...")
                print("Database will be available when connection is restored")
            else:
                print("Continuing in development mode without database...")

        # Start the server
        if is_production:
            print("Starting NeethiAI in Production Mode...")
            print(f"Binding to host: 0.0.0.0, port: {port}")
            # Try to use Waitress for production
            try:
                from waitress import serve

                print("✓ Using Waitress production server")
                serve(app, host="0.0.0.0", port=port, threads=4)
            except ImportError:
                print("⚠️ Waitress not available, using Flask development server")
                app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
            except Exception as e:
                print(f"⚠️ Error starting Waitress: {e}")
                print("Falling back to Flask development server...")
                app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
        else:
            print("Starting NeethiAI Flask Application...")
            print(f"Open your browser and go to: http://localhost:{port}")
            # Run without auto-reloader to avoid upload interruptions
            app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)

    except Exception as e:
        print(f"✗ Fatal error starting application: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
