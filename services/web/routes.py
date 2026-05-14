from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi import Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi import Cookie
from fastapi import Query
from typing import Optional
import os
import sqlalchemy
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import random

# Define the router before using it
router = APIRouter()
templates = Jinja2Templates(directory="templates")

#connecting to database?
_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:pass@pg_normalized_batch:5432/postgres")
_engine = sqlalchemy.create_engine(_DATABASE_URL) if _DATABASE_URL else None

connection = _engine.connect()

_PAGE_SIZE = 20

def _fix_tz(ts: str) -> str:
    """Fix timestamps where the tz offset is separated by a space instead of +."""
    return re.sub(r' (\d{2}:\d{2})$', r'+\1', ts)


def build_timeline_page(
    before_created_at: Optional[str] = None,
    before_id: Optional[int] = None,
    after_created_at: Optional[str] = None,
    after_id: Optional[int] = None,
) -> tuple[list, Optional[dict]]:
    """Keyset pagination ordered by recency. Fast on large tables."""
    if before_created_at:
        before_created_at = _fix_tz(before_created_at)
    if after_created_at:
        after_created_at = _fix_tz(after_created_at)

    with connection.begin():
        if before_created_at and before_id:
            # Going to newer page
            sql = sqlalchemy.sql.text('''
                SELECT id_tweets, text, tweets.created_at, screen_name
                FROM tweets
                JOIN users USING (id_users)
                WHERE (tweets.created_at, id_tweets) > (:created_at, :id_tweets)
                ORDER BY tweets.created_at ASC, id_tweets ASC
                LIMIT :limit
            ''')
            res = connection.execute(sql, {'created_at': before_created_at, 'id_tweets': before_id, 'limit': _PAGE_SIZE + 1})
            rows = list(reversed(res.mappings().fetchall()))

        elif after_created_at and after_id:
            # Going to older page
            sql = sqlalchemy.sql.text('''
                SELECT id_tweets, text, tweets.created_at, screen_name
                FROM tweets
                JOIN users USING (id_users)
                WHERE (tweets.created_at, id_tweets) < (:created_at, :id_tweets)
                ORDER BY tweets.created_at DESC, id_tweets DESC
                LIMIT :limit
            ''')
            res = connection.execute(sql, {'created_at': after_created_at, 'id_tweets': after_id, 'limit': _PAGE_SIZE + 1})
            rows = res.mappings().fetchall()

        else:
            # First page
            sql = sqlalchemy.sql.text('''
                SELECT id_tweets, text, tweets.created_at, screen_name
                FROM tweets
                JOIN users USING (id_users)
                ORDER BY created_at DESC, id_tweets DESC
                LIMIT :limit
            ''')
            res = connection.execute(sql, {'limit': _PAGE_SIZE + 1})
            rows = res.mappings().fetchall()

        has_more = len(rows) > _PAGE_SIZE
        page_rows = rows[:_PAGE_SIZE]

        if not page_rows:
            return [], None

        first = page_rows[0]
        last = page_rows[-1]

     # Are there newer tweets than the first tweet on this page?
        newer_sql = sqlalchemy.sql.text('''
            SELECT 1
            FROM tweets
            WHERE (created_at, id_tweets) > (:created_at, :id_tweets)
            LIMIT 1
        ''')

        newer_res = connection.execute(
            newer_sql,
            {
                'created_at': first['created_at'],
                'id_tweets': first['id_tweets']
            }
        )

        has_newer = newer_res.fetchone() is not None

    # Are there older tweets than the last tweet on this page?
        older_sql = sqlalchemy.sql.text('''
            SELECT 1
            FROM tweets
            WHERE (created_at, id_tweets) < (:created_at, :id_tweets)
            LIMIT 1
        ''')

        older_res = connection.execute(
            older_sql,
            {
                'created_at': last['created_at'],
                'id_tweets': last['id_tweets']
            }
        )

        has_older = older_res.fetchone() is not None

    pager = {
        "has_newer": has_newer,
        "has_older": has_older,
        "newer_href": f"/?before_created_at={first['created_at']}&before_id={first['id_tweets']}",
        "older_href": f"/?after_created_at={last['created_at']}&after_id={last['id_tweets']}",
    }

    return page_rows, pager

def create_account(username: str, password: str, confirm_password: str):
    random_id = random.randint(1, 9223372036854775807) 
    if password != confirm_password:
        return "Passwords do not match"

    with connection.begin():
        sql = sqlalchemy.sql.text('''
            SELECT username FROM credentials
            WHERE username = :username
        ''')
        res = connection.execute(sql, {
            'username': username
            })
        row = res.fetchone()

        if row is not None:
            return "Username already in use, please choose a new username"
        
        sql = sqlalchemy.sql.text('''
                INSERT INTO users (
                    id_users,
                    created_at,
                    screen_name,
                    name
                )
                VALUES (
                    :id_users,
                    :created_at,
                    :screen_name,
                    :name
                )
            ''')
        now = datetime.now(ZoneInfo("America/Los_Angeles"))

        res = connection.execute(sql, {
            'id_users': random_id,
            'created_at': now,
            'screen_name': username,
            'name': username
            })

        sql = sqlalchemy.sql.text('''
            INSERT INTO credentials (username, password) VALUES (:username, :password)
            ''')
        res = connection.execute(sql, {'username': username, 'password': password })
        return True

def check_credentials(username: str, password: str) -> str:
    """
    Checks if the provided username and password are valid.

    Args:
    - username (str): The username to check.
    - password (str): The password to check.

    Returns:
    - str: The username if the credentials are valid, otherwise None.
    """
    with connection.begin():

        sql = sqlalchemy.sql.text('''
            SELECT password FROM credentials
            WHERE username = :username
            ''')
        res = connection.execute(sql, {'username': username})
        row = res.fetchone()
        if row is None:
            return "Username does not exist"
        stored_password = row.password

    if password == stored_password:
        return True
    else:
        return "Incorrect Password"

def logged_in_user(request: Request) -> str:
    """
    Checks if the user is logged in by checking the cookies.

    Args:
    - request (Request): The current request.

    Returns:
    - str: The username if the user is logged in, otherwise None.
    """
    username = request.cookies.get("username")
    password = request.cookies.get("password")
    if username is not None and password is not None:
        valid_username = check_credentials(username, password)
        if valid_username is True:
            return username
    return None

def create_message(username, tweet_text):
    random_id = random.randint(1, 9223372036854775807)
    
    with connection.begin():

        sql = sqlalchemy.sql.text('''
                SELECT id_users FROM users 
                WHERE screen_name = :screen_name
            ''')
        res = connection.execute(sql, {
            'screen_name': username,
        })
        row = res.fetchone()

        if row is None:
            return None

        id_user = row.id_users
                
        
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        sql = sqlalchemy.sql.text('''
                INSERT INTO tweets (
                    id_tweets,
                    id_users,
                    created_at,
                    text
                )
                VALUES (
                    :id_tweets,
                    :id_users,
                    :created_at,
                    :text
                )
            ''')
        
        res = connection.execute(sql, {
            'id_tweets': random_id,
            'id_users': id_user,
            'created_at': now,
            'text': tweet_text
        })
        return True

def search_tweets(query, offset):
    stmt = sqlalchemy.text(
        """
        SELECT
            t.id_tweets,
            t.created_at,
            u.screen_name,
            ts_headline('english', t.text, q,
                'StartSel=<b>, StopSel=</b>,
                MaxFragments=10,
                MinWords=5, MaxWords=10') AS text,
            to_tsvector('english'::regconfig, t.text) <=> q  AS rank
        FROM tweets AS t
        JOIN users AS u USING (id_users),
        plainto_tsquery('english', :query) AS q
        WHERE to_tsvector('english'::regconfig, t.text) @@ q
        ORDER BY rank ASC
        LIMIT :limit
        OFFSET :offset
        """
    )
    with connection.begin():
        return connection.execute(
            stmt,
            {
                "query": query,
                "limit": _PAGE_SIZE + 1,
                "offset": offset,
            },
        ).mappings().all()


@router.get("/")
async def read_root(
    request: Request,
    before_created_at: Optional[str] = Query(None),
    before_id: Optional[int] = Query(None),
    after_created_at: Optional[str] = Query(None),
    after_id: Optional[int] = Query(None),
):
    username = logged_in_user(request)
    tweets, pager = build_timeline_page(
        before_created_at=before_created_at,
        before_id=before_id,
        after_created_at=after_created_at,
        after_id=after_id,
    )
    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": username,
        "tweets": tweets,
        "pager": pager,
        "active_page": "home"
    })

@router.get("/login")
def read_login(request: Request):
    """Returns the HTML content for the login page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("login.html", {"request": request, "username": username, "active_page": "login"})

@router.post("/login")
def post_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Returns the HTML content after a login attempt"""

    print(f"Username: {username}, Password: {password}")

    valid_login = check_credentials(username, password)

    if valid_login is not True:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "username": None,
                "error": valid_login
            }
        )

    # Successful login
    response = templates.TemplateResponse(
        "login_successful.html",
        {
            "request": request,
            "username": username
        }
    )

    response.set_cookie("username", username)
    response.set_cookie("password", password)

    return response


@router.get("/logout")
def read_logout(request: Request):
    """Returns the HTML content for the logout page and deletes cookies"""
    response = templates.TemplateResponse("logout.html", {"request": request, "username": None})
    response.delete_cookie("username")
    response.delete_cookie("password")
    return response

@router.get("/create_account")
def read_create_account(request: Request):
    """Returns the HTML content for the create account page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("create_account.html", {"request": request, "username": username, "active_page": "create_account"})

@router.post("/create_account")
def post_create_account(request: Request, username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    """Returns the HTML content after a successful account creation"""
    created_account = create_account(username, password, confirm_password)
    print(created_account)
    username = logged_in_user(request)
    if created_account is not True:
        print("makes it to error part of page conditional")
        return templates.TemplateResponse("create_account.html", {"request": request, "username": username, "error": created_account})
    else:
        print("makes it to continuing part of page conditional")
        return templates.TemplateResponse("account_created.html", {"request": request, "username": username})

@router.get("/create_message")
def read_create_message(request: Request):
    """Returns the HTML content for the create message page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("create_message.html", {"request": request, "username": username, "active_page": "create_message"})

@router.post("/create_message")
def post_create_message(request: Request, message: str = Form(...)):
    """Returns the HTML content after a successful message creation"""
    username = logged_in_user(request)
    create_message(username, message)
    return templates.TemplateResponse("message_posted.html", {"request": request, "username": username})

@router.get("/search")
def read_search(request: Request):
    """Returns the HTML content for the search page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("search.html", {"request": request, "username": username})

@router.post("/search")
def post_search(request: Request, query: str = Form(...), offset: int = Form(0)):
    username = logged_in_user(request)
    rows = search_tweets(query, offset)
    has_more = len(rows) > _PAGE_SIZE
    tweets = rows[:_PAGE_SIZE]
    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "username": username,
        "tweets": tweets,
        "query": query,
        "offset": offset,
        "prev_offset": max(0, offset - _PAGE_SIZE),
        "next_offset": offset + _PAGE_SIZE,
        "has_more": has_more,
    })
