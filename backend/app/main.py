import hashlib
import io
import os
import secrets
import warnings
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy import event, func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import defer
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from .models import Card, Company, Department, Grant, LoginSession, Person, User, utcnow
from .schemas import CardCreate, Credentials, GrantCreate, NewUser

ROOT = Path(__file__).resolve().parents[2]
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
TEXT_FIELDS = ("name", "company_name", "department", "title", "email", "phone", "address", "website")
TARGET_MODELS = {"company": Company, "department": Department, "person": Person}


@dataclass
class Settings:
    admin_email: str = ""
    admin_password: str = ""
    allowed_origins: tuple[str, ...] | list[str] = ("http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5173", "http://localhost:5173")
    secure_cookie: bool = False
    session_ttl_seconds: int = 28800

    @classmethod
    def from_env(cls):
        defaults = cls()
        origins = os.getenv("ALLOWED_ORIGINS", "")
        return cls(
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "28800")),
            admin_email=os.getenv("ADMIN_EMAIL", ""),
            admin_password=os.getenv("ADMIN_PASSWORD", ""),
            allowed_origins=tuple(o.strip() for o in origins.split(",") if o.strip()) if origins else defaults.allowed_origins,
            secure_cookie=os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes"),
        )


def fail(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


def user_json(user):
    return {"id": user.id, "email": user.email, "role": user.role}


def visible_cards(user):
    if user.role == "admin":
        return True
    return or_(
        Card.created_by == user.id,
        Card.company_id.in_(select(Grant.company_id).where(Grant.user_id == user.id, Grant.scope == "company")),
        Card.department_id.in_(select(Grant.department_id).where(Grant.user_id == user.id, Grant.scope == "department")),
        Card.person_id.in_(select(Grant.person_id).where(Grant.user_id == user.id, Grant.scope == "person")),
    )


def card_json(card, db):
    creator = db.get(User, card.created_by)
    return {**{key: getattr(card, key) for key in TEXT_FIELDS},
            "id": card.id, "company_id": card.company_id, "department_id": card.department_id,
            "person_id": card.person_id, "created_by": card.created_by,
            "created_by_email": creator.email, "created_at": card.created_at.isoformat() + "Z"}


def target_label(scope, target, db, user=None):
    if scope == "company":
        return f"{target.name} / #{target.id}"
    if scope == "department":
        company = db.get(Company, target.company_id)
        return f"{company.name} / {target.name} / #{target.id}"
    statement = select(Card).where(Card.person_id == target.id).options(defer(Card.image_bytes)).order_by(Card.id.desc())
    if user is not None:
        statement = statement.where(visible_cards(user))
    card = db.exec(statement.limit(1)).first()
    if card:
        return f"{card.name} / {card.company_name or '-'} / {card.department or '-'} / #{target.id}"
    return f"{target.name} / #{target.id}"


def grant_json(grant, db):
    target_id = getattr(grant, grant.scope + "_id")
    target = db.get(TARGET_MODELS[grant.scope], target_id)
    return {"id": grant.id, "scope": grant.scope, "target_id": target_id,
            "label": target_label(grant.scope, target, db)}


async def validated_image(upload):
    blob = await upload.read(MAX_IMAGE_BYTES + 1)
    if len(blob) > MAX_IMAGE_BYTES:
        fail(413, "image_too_large", "画像は5MiB以下にしてください。")
    if not blob:
        fail(422, "invalid_image", "JPEGまたはPNG画像を選択してください。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(blob)) as img:
                if img.format not in ("JPEG", "PNG"):
                    fail(422, "invalid_image", "JPEGとPNGの画像に対応しています。")
                if img.width * img.height > MAX_IMAGE_PIXELS:
                    fail(422, "invalid_image", "画像の画素数は2,000万画素以下にしてください。")
                mime = "image/jpeg" if img.format == "JPEG" else "image/png"
                img.verify()
            with Image.open(io.BytesIO(blob)) as img:
                img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail(422, "invalid_image", "画像が破損しているか、形式・画素数が対応範囲外です。")
    return blob, mime


def create_app(database_path=None, settings=None):
    config = Settings.from_env() if settings is None else (Settings(**settings) if isinstance(settings, dict) else settings)
    if config.session_ttl_seconds < 1:
        raise ValueError("SESSION_TTL_SECONDS must be positive")
    db_path = str(database_path or os.getenv("DATABASE_PATH", "data/app.sqlite3"))
    engine_options = {"connect_args": {"check_same_thread": False, "timeout": 15}}
    if db_path == ":memory:":
        url = "sqlite://"
        engine_options["poolclass"] = StaticPool
    else:
        path = Path(db_path)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        url = "sqlite:///" + str(path)
    engine = create_engine(url, **engine_options)

    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")

    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        if db.exec(select(func.count()).select_from(User)).one() == 0 and (config.admin_email or config.admin_password):
            try:
                bootstrap = NewUser(email=config.admin_email, password=config.admin_password)
            except ValidationError:
                raise ValueError("Initial administrator configuration is invalid. Check ADMIN_EMAIL and a password of at least 12 characters.") from None
            db.add(User(email=bootstrap.email, password_hash=PASSWORD_HASHER.hash(bootstrap.password), role="admin"))
            db.commit()

    app = FastAPI(title="Business Card Manager", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.settings = config

    @app.middleware("http")
    async def response_security(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            detail = {"code": exc.detail["code"], "message": exc.detail["message"]}
        else:
            detail = {"code": "request_failed", "message": 'リクエストを処理できませんでした。入力内容と操作を確認してください。'}
        return JSONResponse(detail, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        return JSONResponse({"code": "invalid_input", "message": "必須項目と入力形式を確認してください。"}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({"code": "storage_error", "message": "データの処理に失敗しました。もう一度お試しください。"}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse({"code": "server_error", "message": "処理に失敗しました。もう一度お試しください。"}, status_code=500)

    def database():
        with Session(engine) as db:
            yield db

    def check_origin(request):
        origin = request.headers.get("origin")
        if not origin or origin not in config.allowed_origins:
            fail(403, "invalid_origin", "このアクセス元からの操作は許可されていません。")

    def authenticate(request: Request, db: Session = Depends(database)):
        token = request.cookies.get("session")
        if not token:
            fail(401, "authentication_required", "ログインしてください。")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        login_session = db.get(LoginSession, token_hash)
        if not login_session or login_session.expires_at <= utcnow():
            fail(401, "authentication_required", "セッションの有効期限が切れました。もう一度ログインしてください。")
        user = db.get(User, login_session.user_id)
        if not user:
            fail(401, "authentication_required", "ログインしてください。")
        request.state.login_session = login_session
        return user

    def mutation(request: Request, user: User = Depends(authenticate)):
        check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(csrf.encode(), request.state.login_session.csrf_token.encode()):
            fail(403, "invalid_csrf", "セッションを確認できません。画面を更新してお試しください。")
        return user

    def admin(user: User = Depends(authenticate)):
        if user.role != "admin":
            fail(403, "forbidden", "管理者権限が必要です。")
        return user

    def admin_mutation(user: User = Depends(mutation)):
        if user.role != "admin":
            fail(403, "forbidden", "管理者権限が必要です。")
        return user

    def find_card(card_id, user, db, include_image=False):
        statement = select(Card).where(Card.id == card_id, visible_cards(user))
        if not include_image:
            statement = statement.options(defer(Card.image_bytes))
        card = db.exec(statement).first()
        if not card:
            fail(404, "not_found", "名刺が見つかりません。")
        return card

    def find_user(user_id, db):
        user = db.get(User, user_id)
        if not user:
            fail(404, "not_found", "利用者が見つかりません。")
        return user

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(payload: Credentials, request: Request, response: Response, db: Session = Depends(database)):
        check_origin(request)
        user = db.exec(select(User).where(User.email == payload.email)).first()
        try:
            PASSWORD_HASHER.verify(user.password_hash if user else DUMMY_PASSWORD_HASH, payload.password)
        except (VerificationError, InvalidHashError):
            fail(401, "invalid_credentials", "メールアドレスまたはパスワードが正しくありません。")
        if not user:
            fail(401, "invalid_credentials", "メールアドレスまたはパスワードが正しくありません。")
        old_token = request.cookies.get("session")
        if old_token:
            old = db.get(LoginSession, hashlib.sha256(old_token.encode()).hexdigest())
            if old:
                db.delete(old)
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                            csrf_token=csrf, expires_at=utcnow() + timedelta(seconds=config.session_ttl_seconds)))
        db.commit()
        response.set_cookie("session", token, max_age=config.session_ttl_seconds, httponly=True,
                            secure=config.secure_cookie, samesite="lax", path="/")
        return {"user": user_json(user), "csrf_token": csrf}

    @app.get("/api/auth/me")
    def me(request: Request, user: User = Depends(authenticate)):
        return {"user": user_json(user), "csrf_token": request.state.login_session.csrf_token}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response, user: User = Depends(mutation), db: Session = Depends(database)):
        db.delete(request.state.login_session)
        db.commit()
        response.delete_cookie("session", path="/", secure=config.secure_cookie, httponly=True, samesite="lax")
        response.status_code = 204

    @app.post("/api/extract")
    async def extract(image: UploadFile = File(...), user: User = Depends(mutation)):
        from . import ai
        blob, mime = await validated_image(image)
        fields = await ai.extract_fields(blob, mime)
        return {"fields": fields}

    @app.post("/api/cards", status_code=201)
    async def save_card(image: UploadFile = File(...), data: str = Form(...), user: User = Depends(mutation), db: Session = Depends(database)):
        try:
            payload = CardCreate.model_validate_json(data)
        except (ValidationError, ValueError):
            fail(422, "invalid_input", "氏名は必須です。登録項目の長さや形式を確認してください。")
        blob, mime = await validated_image(image)
        request_id = str(payload.request_id)
        request_hash = hashlib.sha256(payload.model_dump_json().encode() + b"\0" + blob).hexdigest()
        prior = db.exec(select(Card).where(Card.created_by == user.id, Card.request_id == request_id)).first()
        if prior:
            if prior.request_hash != request_hash:
                fail(409, "request_conflict", "同じ登録IDで異なる内容が送信されました。新しい登録としてお試しください。")
            return card_json(prior, db)
        if payload.person_id is not None:
            visible_person = db.exec(select(Card.id).where(Card.person_id == payload.person_id, visible_cards(user)).limit(1)).first()
            if visible_person is None:
                fail(404, "not_found", "人物が見つかりません。")
            person_id = payload.person_id
        else:
            person = Person(name=payload.name)
            db.add(person)
            db.flush()
            person_id = person.id
        company_id = department_id = None
        if payload.company_name:
            company = db.exec(select(Company).where(Company.name == payload.company_name)).first()
            if not company:
                company = Company(name=payload.company_name)
                db.add(company)
                db.flush()
            company_id = company.id
            if payload.department:
                department = db.exec(select(Department).where(Department.company_id == company_id, Department.name == payload.department)).first()
                if not department:
                    department = Department(company_id=company_id, name=payload.department)
                    db.add(department)
                    db.flush()
                department_id = department.id
        card = Card(**payload.model_dump(exclude={"request_id", "person_id"}), person_id=person_id,
                    company_id=company_id, department_id=department_id, created_by=user.id,
                    image_bytes=blob, image_mime=mime, request_id=request_id, request_hash=request_hash)
        db.add(card)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            prior = db.exec(select(Card).where(Card.created_by == user.id, Card.request_id == request_id)).first()
            if prior and prior.request_hash == request_hash:
                return card_json(prior, db)
            fail(409, "save_conflict", "保存中にデータが変更されました。もう一度お試しください。")
        db.refresh(card)
        return card_json(card, db)

    @app.get("/api/cards")
    def list_cards(q: str = Query(default="", max_length=1000), limit: int = Query(default=50, ge=1, le=100),
                   offset: int = Query(default=0, ge=0), user: User = Depends(authenticate), db: Session = Depends(database)):
        conditions = [visible_cards(user)]
        if q.strip():
            conditions.append(or_(Card.name.contains(q.strip(), autoescape=True), Card.company_name.contains(q.strip(), autoescape=True)))
        total = db.exec(select(func.count()).select_from(Card).where(*conditions)).one()
        cards = db.exec(select(Card).where(*conditions).options(defer(Card.image_bytes)).order_by(Card.id.desc()).offset(offset).limit(limit)).all()
        return {"items": [card_json(card, db) for card in cards], "total": total, "limit": limit, "offset": offset}

    @app.get("/api/cards/{card_id}/image")
    def card_image(card_id: int, user: User = Depends(authenticate), db: Session = Depends(database)):
        card = find_card(card_id, user, db, include_image=True)
        return Response(card.image_bytes, media_type=card.image_mime, headers={"Cache-Control": "private, no-store"})

    @app.get("/api/cards/{card_id}")
    def card_detail(card_id: int, user: User = Depends(authenticate), db: Session = Depends(database)):
        return card_json(find_card(card_id, user, db), db)

    @app.get("/api/people/options")
    def people_options(user: User = Depends(authenticate), db: Session = Depends(database)):
        people = db.exec(select(Person).where(Person.id.in_(select(Card.person_id).where(visible_cards(user)))).order_by(Person.id)).all()
        return {"items": [{"id": person.id, "label": target_label("person", person, db, user)} for person in people]}

    @app.get("/api/admin/users")
    def users(user: User = Depends(admin), db: Session = Depends(database)):
        return {"items": [user_json(item) for item in db.exec(select(User).order_by(User.id)).all()]}

    @app.post("/api/admin/users", status_code=201)
    def add_user(payload: NewUser, user: User = Depends(admin_mutation), db: Session = Depends(database)):
        new_user = User(email=payload.email, password_hash=PASSWORD_HASHER.hash(payload.password), role="user")
        db.add(new_user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            fail(409, "duplicate_email", "このメールアドレスは登録済みです。")
        db.refresh(new_user)
        return user_json(new_user)

    @app.get("/api/admin/grant-targets")
    def grant_targets(scope: Literal["company", "department", "person"], user: User = Depends(admin), db: Session = Depends(database)):
        model = TARGET_MODELS[scope]
        targets = db.exec(select(model).order_by(model.id)).all()
        return {"items": [{"id": target.id, "label": target_label(scope, target, db)} for target in targets]}

    @app.get("/api/admin/users/{user_id}/grants")
    def grants(user_id: int, user: User = Depends(admin), db: Session = Depends(database)):
        find_user(user_id, db)
        items = db.exec(select(Grant).where(Grant.user_id == user_id).order_by(Grant.id)).all()
        return {"items": [grant_json(item, db) for item in items]}

    @app.post("/api/admin/users/{user_id}/grants", status_code=201)
    def add_grant(user_id: int, payload: GrantCreate, user: User = Depends(admin_mutation), db: Session = Depends(database)):
        find_user(user_id, db)
        target = db.get(TARGET_MODELS[payload.scope], payload.target_id)
        if not target:
            fail(404, "not_found", "閲覧許可の対象が見つかりません。")
        target_column = getattr(Grant, payload.scope + "_id")
        statement = select(Grant).where(Grant.user_id == user_id, Grant.scope == payload.scope, target_column == payload.target_id)
        existing = db.exec(statement).first()
        if existing:
            return grant_json(existing, db)
        grant = Grant(user_id=user_id, scope=payload.scope, **{payload.scope + "_id": payload.target_id})
        db.add(grant)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.exec(statement).first()
            if existing:
                return grant_json(existing, db)
            raise
        db.refresh(grant)
        return grant_json(grant, db)

    @app.delete("/api/admin/users/{user_id}/grants/{grant_id}", status_code=204)
    def remove_grant(user_id: int, grant_id: int, user: User = Depends(admin_mutation), db: Session = Depends(database)):
        find_user(user_id, db)
        grant = db.exec(select(Grant).where(Grant.id == grant_id, Grant.user_id == user_id)).first()
        if not grant:
            fail(404, "not_found", "閲覧許可が見つかりません。")
        db.delete(grant)
        db.commit()
        return Response(status_code=204)

    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                fail(404, "not_found", "指定されたAPIが見つかりません。")
            candidate = (dist / path).resolve()
            if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
