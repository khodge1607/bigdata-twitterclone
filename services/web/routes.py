from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi import Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi import Cookie
import os
import sqlalchemy

# Define the router before using it
router = APIRouter()
templates = Jinja2Templates(directory="templates")

#connecting to database?
_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:pass@pg_normalized_batch:5432/postgres")
_engine = sqlalchemy.create_engine(_DATABASE_URL) if _DATABASE_URL else None

connection = _engine.connect()


def create_account(username: str, password: str, confirm_password: str):
    
    if password != confirm_password:
        return "Password doesn't match"

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
            return "Username already in use, please chose a new username"

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
    # FIXME: Add database code to check credentials
    # For now, this is a mock with hardcoded valid credentials
    with connection.begin():

        sql = sqlalchemy.sql.text('''
            SELECT password FROM credentials
            WHERE username = :username
            ''')
        res = connection.execute(sql, {'username': username})
        row = res.fetchone()
        if row is None:
            return None
        stored_password = row.password

    if password == stored_password:
        return username
    else:
        return None

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
        if valid_username is not None:
            return valid_username
    return None

@router.get("/")
async def read_root(request: Request):
    """Returns the HTML content for the home page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("index.html", {"request": request, "username": username})

@router.get("/login")
def read_login(request: Request):
    """Returns the HTML content for the login page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("login.html", {"request": request, "username": username})

@router.post("/login")
def post_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Returns the HTML content after a login attempt"""
    # Print the username and password to the logs
    print(f"Username: {username}, Password: {password}")
    # Check the credentials
    valid_username = check_credentials(username, password)
    if valid_username is not None:
        # Credentials are valid, set cookies and return the success page
        response = templates.TemplateResponse("login_successful.html", {"request": request, "username": valid_username})
        response.set_cookie("username", username)
        response.set_cookie("password", password)
        return response
    else:
        # Credentials are invalid, return an error page
        return templates.TemplateResponse("login.html", {"request": request, "username": None, "error": "Invalid username or password"})

@router.get("/logout")
def read_logout(request: Request):
    """Returns the HTML content for the logout page and deletes cookies"""
    username = logged_in_user(request)
    response = templates.TemplateResponse("logout.html", {"request": request, "username": None})
    response.set_cookie("username", "")
    response.set_cookie("password", "")
    response.set_cookie("username", "", expires=0)
    response.set_cookie("password", "", expires=0)
    return response

@router.get("/create_account")
def read_create_account(request: Request):
    """Returns the HTML content for the create account page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("create_account.html", {"request": request, "username": username})

@router.post("/create_account")
def post_create_account(request: Request, username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    """Returns the HTML content after a successful account creation"""
    created_account = create_account(username, password, confirm_password)
    username = logged_in_user(request)
    if created_account == "Unexpected Error" or created_account == "Username already exists" or created_account=="Passwords do not match":
        return templates.TemplateResponse(request, "create_account.html", {"request": request, "username": username, "error": created_account})
    else:
        return templates.TemplateResponse(request, "account_created.html", {"request": request, "username": username})

@router.get("/create_message")
def read_create_message(request: Request):
    """Returns the HTML content for the create message page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("create_message.html", {"request": request, "username": username})

@router.post("/create_message")
def post_create_message(request: Request, message: str = Form(...)):
    """Returns the HTML content after a successful message creation"""
    username = logged_in_user(request)
    return templates.TemplateResponse("message_posted.html", {"request": request, "username": username})

@router.get("/search")
def read_search(request: Request):
    """Returns the HTML content for the search page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("search.html", {"request": request, "username": username})

@router.post("/search")
def post_search(request: Request, query: str = Form(...)):
    """Returns the HTML content for the search results page"""
    username = logged_in_user(request)
    return templates.TemplateResponse("search_results.html", {"request": request, "username": username})
