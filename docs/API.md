# API contract for implementation

All routes start with /api. JSON uses snake_case. Errors: {"code":"...", "message":"..."}.
Cookie session + X-CSRF-Token for authenticated POST/DELETE. Frontend calls credentials: same-origin.
Login and GET /auth/me return {"user":{"id":1,"email":"...","role":"admin"},"csrf_token":"..."}.
POST /auth/login JSON {email,password}; POST /auth/logout returns 204.
GET /health returns {"status":"ok"}.
GET /cards?q=&limit=50&offset=0 returns {"items":[Card],"total":1,"limit":50,"offset":0}.
Card contains id, name, company_name, department, title, email, phone, address, website,
company_id (nullable), department_id (nullable), person_id, created_by, created_by_email, created_at.
GET /cards/{id} returns Card. GET /cards/{id}/image returns authenticated binary.
POST /extract multipart field image returns {"fields":{the eight text fields}}.
POST /cards multipart image and data. data is JSON containing the eight fields plus
request_id (UUID string), optional person_id (null means new person). Returns Card with status 201.
Only name is required; absent other text fields default to "". Unknown JSON keys rejected.
GET /people/options returns {"items":[{"id":1,"label":"name / company / department / #ID"}]}.
GET /admin/users returns {"items":[User]}. POST /admin/users {email,password} returns User (201).
GET /admin/grant-targets?scope=company|department|person returns {"items":[{"id":1,"label":"..."}]}.
GET /admin/users/{id}/grants returns {"items":[Grant]}.
POST /admin/users/{id}/grants JSON {scope,target_id} returns Grant (201; duplicates are idempotent).
DELETE /admin/users/{id}/grants/{grant_id} returns 204.
Grant = {id,scope,target_id,label}. User = {id,email,role}.
Use label with identifying company/department context and ID, never identify people by name alone.

Backend location: backend/app/. Entrypoint app.asgi:app.
create_app(database_path=None, settings=None) creates an isolated app for tests.
settings accepts admin_email, admin_password, allowed_origins, secure_cookie, session_ttl_seconds.
AI adapter: backend/app/ai.py, async extract_fields(image_bytes: bytes, mime: str) -> dict[str,str].
.env loads from the repository root. Image validation precedes extraction and saving.
Frontend: frontend/. Vite proxies /api to http://127.0.0.1:8000.
Production frontend/dist is served by FastAPI after building.
