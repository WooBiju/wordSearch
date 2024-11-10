from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import sqlite3
from passlib.context import CryptContext
import random
import string
from typing import List
from typing import Optional
from datetime import datetime,timedelta,timezone
import jwt

def get_db_connection():
    conn = sqlite3.connect('DB.db')
    conn.row_factory = sqlite3.Row
    return conn

# pw 해싱 객체 생성
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# pw 해싱
def get_password_hash(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

SECRET_KEY = "mysecretkey"  
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 

# JWT 토큰 생성 
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

app = FastAPI()

class User(BaseModel):
    username: str
    email: str

class UserCreate(User):
    password: str
    
class UserInDB(User):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    
class WordCreate(BaseModel):
    word: str
    
# Wordsearch 그리드 생성
class WordSearchRequest(BaseModel):
    size: int = 10
    words: List[str]
    
# 사용자 회원가입
def add_user(username: str, email: str, password: str):
    conn = get_db_connection()
    conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                 (username, email, password))
    conn.commit()
    conn.close() 

@app.post("/register")
def register(user: UserCreate):
    hashed_password = get_password_hash(user.password)
    add_user(user.username, user.email, hashed_password)
    return {"message": "Login Success"}


def create_user(user_create: UserCreate):
    hashed_password = get_password_hash(user_create.password)
    add_user(user_create.username, user_create.email, hashed_password)


def get_user_by_username(username: str):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

# 사용자 로그인
@app.post("/login", response_model=Token)
def login(user: UserCreate):
    user_in_db = get_user_by_username(user.username)
    if not user_in_db or not verify_password(user.password, user_in_db['password']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# 로그인 검증
def authenticate_user(username: str, password: str):
    user = get_user_by_username(username)
    if user and verify_password(password, user['hashed_password']):
        return user
    return None

# JWT 인증 확인
def get_current_user(token: str):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username  
    except jwt.PyJWTError:
        raise credentials_exception
    
# 로그인된 사용자만 접근 가능
@app.get("/users/me")
def read_users_me(current_user: str = Depends(get_current_user)):
    return {"user": current_user}

# 빈 그리드 생성
def create_empty_grid(size=10):
    return [[' ' for _ in range(size)] for _ in range(size)]

# 단어를 그리드에 배치하는 함수
def place_word_in_grid(grid, word):
    size = len(grid)
    word_len = len(word)
    
    # 단어를 배치할 수 있는 위치 찾기
    directions = ['horizontal', 'vertical', 'diagonal']
    direction = random.choice(directions)
    
    if direction == 'horizontal':
        row = random.randint(0, size - 1)
        col = random.randint(0, size - word_len)
        for i in range(word_len):
            grid[row][col + i] = word[i]
    
    elif direction == 'vertical':
        row = random.randint(0, size - word_len)
        col = random.randint(0, size - 1)
        for i in range(word_len):
            grid[row + i][col] = word[i]
    
    elif direction == 'diagonal':
        row = random.randint(0, size - word_len)
        col = random.randint(0, size - word_len)
        for i in range(word_len):
            grid[row + i][col + i] = word[i]
    
    return grid

# 단어 검색 그리드 생성
def create_wordsearch_grid(size=10, words=None):
    if words is None:
        words = []
    
    grid = create_empty_grid(size)
    
    # 단어들을 그리드에 배치
    for word in words:
        grid = place_word_in_grid(grid, word)
    
    # 빈 공간에 무작위 문자 채우기
    for row in range(size):
        for col in range(size):
            if grid[row][col] == ' ':
                grid[row][col] = random.choice(string.ascii_uppercase)
    
    return grid
    
def add_word(word: str):
    conn = get_db_connection()
    conn.execute('INSERT INTO words (word) VALUES (?)', (word,))
    conn.commit()
    conn.close()
    
def get_all_words():
    conn = get_db_connection()
    words = conn.execute('SELECT word FROM words').fetchall()
    conn.close()
    return [word['word'] for word in words]
  
@app.post("/words")
def create_word(word: WordCreate):
    add_word(word.word)
    return {"message": f"Word '{word.word}' added successfully"}  

# 단어 목록 조회
@app.get("/words", response_model=List[str])
def get_words():
    words = get_all_words()
    if not words:
        raise HTTPException(status_code=404, detail="No words found")
    return words
    
@app.post("/generate_grid")
def generate_grid(request: WordSearchRequest):
    grid = create_wordsearch_grid(request.size, request.words)
    return {"grid": grid}

