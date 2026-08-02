#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "ihd.sqlite3"
HOST = os.getenv("IHD_HOST", "127.0.0.1")
PORT = int(os.getenv("IHD_PORT", "8787"))
MAX_UPLOAD = int(os.getenv("IHD_MAX_UPLOAD_MB", "250")) * 1024 * 1024
SESSION_SECONDS = int(os.getenv("IHD_SESSION_HOURS", "168")) * 3600
COOKIE_NAME = "ihd_session"
PBKDF2_ITERS = 310_000

DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)

SCHEMA = r'''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'creator',
  verified INTEGER NOT NULL DEFAULT 0,
  suspended INTEGER NOT NULL DEFAULT 0,
  password_hash TEXT NOT NULL,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  target TEXT,
  details TEXT,
  ip TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  original_name TEXT NOT NULL,
  storage_name TEXT NOT NULL,
  mime TEXT,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_assets (
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  label TEXT,
  PRIMARY KEY(project_id, asset_id)
);
CREATE TABLE IF NOT EXISTS beats (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  bpm INTEGER,
  musical_key TEXT,
  license_text TEXT NOT NULL,
  asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
  public INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plugin_presets (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  chain_json TEXT NOT NULL,
  public INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
  id TEXT PRIMARY KEY,
  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  primary_artist TEXT NOT NULL,
  audio_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
  artwork_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
  composition_splits TEXT NOT NULL DEFAULT '[]',
  master_splits TEXT NOT NULL DEFAULT '[]',
  credits TEXT NOT NULL DEFAULT '[]',
  rights_attested INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  share_slug TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS epk_profiles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  artist_name TEXT,
  bio TEXT,
  market TEXT,
  business_email TEXT,
  links_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  host_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  locked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS room_members (
  room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission TEXT NOT NULL DEFAULT 'guest',
  joined_at TEXT NOT NULL,
  last_seen INTEGER NOT NULL,
  PRIMARY KEY(room_id, user_id)
);
CREATE TABLE IF NOT EXISTS room_invites (
  id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  inviter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invitee_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS room_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
  from_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  to_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  signal_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_owner ON assets(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_messages_room ON room_messages(room_id,id);
CREATE INDEX IF NOT EXISTS idx_signals_to ON signals(room_id,to_user_id,id);
'''


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with db() as con:
        con.executescript(SCHEMA)
        row = con.execute("SELECT id FROM users WHERE role='super_admin' LIMIT 1").fetchone()
        if not row:
            email = os.getenv("IHD_MASTER_EMAIL", "owner@ithitdifferent.local").strip().lower()
            password = os.getenv("IHD_MASTER_PASSWORD") or secrets.token_urlsafe(15)
            name = os.getenv("IHD_MASTER_NAME", "IT HIT DIFFERENT Owner")
            con.execute(
                "INSERT INTO users(email,display_name,role,verified,suspended,password_hash,must_change_password,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (email, name, "super_admin", 1, 0, hash_password(password), 0, now_iso()),
            )
            con.commit()
            print("\n" + "="*68)
            print(" IT HIT DIFFERENT LLC — MASTER ACCOUNT CREATED")
            print(f" Email:    {email}")
            print(f" Password: {password}")
            print(" Save this password now. It is not written to a plaintext file.")
            print("="*68 + "\n")


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERS)
    return f"pbkdf2_sha256${PBKDF2_ITERS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password, encoded):
    try:
        alg, iters, salt64, digest64 = encoded.split("$", 3)
        if alg != "pbkdf2_sha256": return False
        salt = base64.urlsafe_b64decode(salt64.encode())
        expected = base64.urlsafe_b64decode(digest64.encode())
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def safe_name(name):
    name = Path(name).name[:180]
    clean = "".join(c if c.isalnum() or c in " ._()-[]" else "_" for c in name).strip()
    return clean or "upload.bin"


def generate_room_code(length=6):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def public_user(row):
    return {
        "id": row["id"], "email": row["email"], "display_name": row["display_name"],
        "role": row["role"], "verified": bool(row["verified"]), "suspended": bool(row["suspended"]),
        "must_change_password": bool(row["must_change_password"]), "created_at": row["created_at"]
    }


def audit(con, actor, action, target="", details=None, ip=""):
    con.execute("INSERT INTO audit_events(actor_user_id,action,target,details,ip,created_at) VALUES(?,?,?,?,?,?)",
                (actor, action, target, json.dumps(details or {}, separators=(",",":")), ip, now_iso()))


class Handler(BaseHTTPRequestHandler):
    server_version = "IHDPrivateGate/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s - %s\n" % (self.log_date_time_string(), self.address_string(), fmt % args))

    @property
    def path_only(self):
        return urllib.parse.urlsplit(self.path).path

    @property
    def query(self):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

    def client_ip(self):
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def json_body(self, limit=2*1024*1024):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > limit:
            raise ValueError("body_too_large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload, status=200, headers=None):
        data = json.dumps(payload, separators=(",",":"), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.security_headers()
        if headers:
            for k,v in headers.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)

    def error_json(self, status, code, message):
        self.send_json({"ok":False,"error":code,"message":message}, status)

    def security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(self), microphone=(self), display-capture=(self), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; style-src 'self'; script-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

    def session_user(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get(COOKIE_NAME)
        if not morsel: return None, None
        th = token_hash(morsel.value)
        with db() as con:
            row = con.execute("""SELECT s.csrf,s.expires_at,u.* FROM sessions s JOIN users u ON u.id=s.user_id
                               WHERE s.token_hash=?""", (th,)).fetchone()
            if not row: return None, None
            if row["expires_at"] < int(time.time()) or row["suspended"]:
                con.execute("DELETE FROM sessions WHERE token_hash=?", (th,)); con.commit(); return None, None
            return row, row["csrf"]

    def require_auth(self, csrf=False, roles=None):
        user, csrf_token = self.session_user()
        if not user:
            self.error_json(401,"unauthorized","Sign in through the private gate."); return None
        if csrf and not hmac.compare_digest(self.headers.get("X-IHD-CSRF", ""), csrf_token or ""):
            self.error_json(403,"csrf","Security token mismatch. Refresh and try again."); return None
        if roles and user["role"] not in roles:
            self.error_json(403,"forbidden","Your account does not have permission for this action."); return None
        return user

    def do_HEAD(self):
        p=self.path_only
        if p in ("/","/index.html"): target=STATIC/"index.html"
        else:
            rel=p.lstrip("/"); target=(STATIC/rel).resolve()
            if STATIC.resolve() not in target.parents and target!=STATIC.resolve():
                self.send_response(403); self.security_headers(); self.end_headers(); return
            if not target.exists() or not target.is_file(): target=STATIC/"index.html"
        mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",mime + ("; charset=utf-8" if mime.startswith("text/") or mime in ("application/javascript","application/json") else "")); self.send_header("Content-Length",str(target.stat().st_size)); self.security_headers(); self.end_headers()

    def do_GET(self):
        try:
            p = self.path_only
            if p == "/api/health": return self.send_json({"ok":True,"service":"IT HIT DIFFERENT LLC","time":now_iso()})
            if p == "/api/me": return self.api_me()
            if p == "/api/dashboard": return self.api_dashboard()
            if p == "/api/webrtc-config": return self.api_webrtc_config()
            if p == "/api/projects": return self.api_projects_get()
            if p == "/api/beats": return self.api_beats_get()
            if p == "/api/plugins": return self.api_plugins_get()
            if p == "/api/releases": return self.api_releases_get()
            if p == "/api/epk": return self.api_epk_get()
            if p == "/api/users/directory": return self.api_directory()
            if p == "/api/rooms": return self.api_rooms_get()
            if p == "/api/room-invites": return self.api_invites_get()
            if p.startswith("/api/rooms/") and p.endswith("/members"): return self.api_room_members(p.split("/")[3])
            if p.startswith("/api/rooms/") and p.endswith("/chat"): return self.api_chat_get(p.split("/")[3])
            if p.startswith("/api/rooms/") and p.endswith("/signals"): return self.api_signals_get(p.split("/")[3])
            if p == "/api/admin/users": return self.api_admin_users()
            if p == "/api/admin/audit": return self.api_admin_audit()
            if p.startswith("/media/"): return self.serve_media(p.split("/")[2])
            if p.startswith("/share/"): return self.serve_share(p.split("/")[2])
            if p.startswith("/invite/"): return self.serve_invite(p.split("/")[2])
            return self.serve_static(p)
        except Exception as e:
            self.log_error("GET error: %r", e)
            if not self.wfile.closed:
                try: self.error_json(500,"server_error","The server could not complete that request.")
                except Exception: pass

    def do_POST(self):
        try:
            p=self.path_only
            if p == "/api/login": return self.api_login()
            if p == "/api/logout": return self.api_logout()
            if p == "/api/account/password": return self.api_change_password()
            if p.startswith("/api/upload/"): return self.api_upload(p.split("/")[3])
            if p == "/api/projects": return self.api_projects_post()
            if p == "/api/beats": return self.api_beats_post()
            if p == "/api/plugins": return self.api_plugins_post()
            if p == "/api/releases": return self.api_releases_post()
            if p == "/api/rooms": return self.api_rooms_post()
            if p == "/api/rooms/join": return self.api_rooms_join()
            if p.startswith("/api/rooms/") and p.endswith("/chat"): return self.api_chat_post(p.split("/")[3])
            if p.startswith("/api/rooms/") and p.endswith("/signal"): return self.api_signal_post(p.split("/")[3])
            if p.startswith("/api/rooms/") and p.endswith("/invite"): return self.api_invite_post(p.split("/")[3])
            if p.startswith("/api/room-invites/") and p.endswith("/respond"): return self.api_invite_respond(p.split("/")[3])
            if p == "/api/admin/users": return self.api_admin_create_user()
            if p.startswith("/api/admin/users/") and p.endswith("/status"): return self.api_admin_user_status(int(p.split("/")[4]))
            return self.error_json(404,"not_found","Endpoint not found.")
        except ValueError as e:
            return self.error_json(400,"bad_request",str(e))
        except Exception as e:
            self.log_error("POST error: %r", e)
            return self.error_json(500,"server_error","The server could not complete that request.")

    def do_PUT(self):
        try:
            if self.path_only == "/api/epk": return self.api_epk_put()
            return self.error_json(404,"not_found","Endpoint not found.")
        except Exception as e:
            self.log_error("PUT error: %r", e); return self.error_json(500,"server_error","The server could not complete that request.")

    def api_login(self):
        body=self.json_body(); email=str(body.get("email","")).strip().lower(); password=str(body.get("password", ""))
        if not email or not password: return self.error_json(400,"missing_credentials","Email and password are required.")
        with db() as con:
            u=con.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE",(email,)).fetchone()
            if not u or not verify_password(password,u["password_hash"]):
                audit(con, u["id"] if u else None, "login_failed", email, ip=self.client_ip()); con.commit()
                time.sleep(.25); return self.error_json(401,"invalid_credentials","Invalid email or password.")
            if u["suspended"]: return self.error_json(403,"suspended","This account is suspended.")
            token=secrets.token_urlsafe(36); csrf=secrets.token_urlsafe(24)
            con.execute("DELETE FROM sessions WHERE expires_at < ?",(int(time.time()),))
            con.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at,created_at) VALUES(?,?,?,?,?)",
                        (token_hash(token),u["id"],csrf,int(time.time())+SESSION_SECONDS,now_iso()))
            audit(con,u["id"],"login","private_gate",ip=self.client_ip()); con.commit()
        secure = os.getenv("IHD_SECURE_COOKIE", "0") == "1"
        cookie=f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}" + ("; Secure" if secure else "")
        return self.send_json({"ok":True,"csrf":csrf,"user":public_user(u)},headers={"Set-Cookie":cookie,"Cache-Control":"no-store"})

    def api_logout(self):
        user=self.require_auth(csrf=True)
        if not user: return
        cookie=SimpleCookie(self.headers.get("Cookie")); morsel=cookie.get(COOKIE_NAME)
        if morsel:
            with db() as con:
                con.execute("DELETE FROM sessions WHERE token_hash=?",(token_hash(morsel.value),)); audit(con,user["id"],"logout","session",ip=self.client_ip()); con.commit()
        return self.send_json({"ok":True},headers={"Set-Cookie":f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

    def api_me(self):
        user,csrf=self.session_user()
        if not user: return self.error_json(401,"unauthorized","Sign in through the private gate.")
        return self.send_json({"ok":True,"user":public_user(user),"csrf":csrf},{ } if False else 200, headers={"Cache-Control":"no-store"})

    def api_change_password(self):
        user=self.require_auth(csrf=True)
        if not user:return
        b=self.json_body(); current=str(b.get("current_password","")); new=str(b.get("new_password",""))
        if len(new)<12:return self.error_json(400,"weak_password","Use at least 12 characters.")
        with db() as con:
            fresh=con.execute("SELECT * FROM users WHERE id=?",(user["id"],)).fetchone()
            if not verify_password(current,fresh["password_hash"]): return self.error_json(403,"wrong_password","Current password is incorrect.")
            con.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?",(hash_password(new),user["id"]))
            audit(con,user["id"],"password_changed",str(user["id"]),ip=self.client_ip()); con.commit()
        return self.send_json({"ok":True})

    def api_webrtc_config(self):
        user=self.require_auth()
        if not user:return
        servers=[]
        stun=os.getenv("IHD_STUN_URL", "").strip()
        turn=os.getenv("IHD_TURN_URL", "").strip()
        if stun: servers.append({"urls":stun})
        if turn:
            item={"urls":turn}
            if os.getenv("IHD_TURN_USERNAME"): item["username"]=os.getenv("IHD_TURN_USERNAME")
            if os.getenv("IHD_TURN_PASSWORD"): item["credential"]=os.getenv("IHD_TURN_PASSWORD")
            servers.append(item)
        return self.send_json({"ok":True,"iceServers":servers})

    def api_dashboard(self):
        user=self.require_auth();
        if not user:return
        with db() as con:
            uid=user["id"]
            counts={
              "projects":con.execute("SELECT count(*) n FROM projects WHERE owner_user_id=?",(uid,)).fetchone()["n"],
              "beats":con.execute("SELECT count(*) n FROM beats WHERE owner_user_id=?",(uid,)).fetchone()["n"],
              "releases":con.execute("SELECT count(*) n FROM releases WHERE owner_user_id=?",(uid,)).fetchone()["n"],
              "rooms":con.execute("SELECT count(*) n FROM room_members WHERE user_id=?",(uid,)).fetchone()["n"]
            }
            if user["role"] in ("super_admin","admin"):
                counts["users"]=con.execute("SELECT count(*) n FROM users").fetchone()["n"]
        return self.send_json({"ok":True,"counts":counts})

    def api_upload(self, kind):
        user=self.require_auth(csrf=True)
        if not user:return
        allowed={"take","beat","release","artwork","agreement","epk"}
        if kind not in allowed:return self.error_json(400,"upload_kind","Unsupported upload type.")
        if kind=="beat" and user["role"] not in ("super_admin","admin","verified_producer"):
            return self.error_json(403,"producer_required","Verified producer access is required to publish beats.")
        length=int(self.headers.get("Content-Length","0") or 0)
        if length<=0:return self.error_json(400,"empty_upload","No file data received.")
        if length>MAX_UPLOAD:return self.error_json(413,"too_large",f"File exceeds {MAX_UPLOAD//1024//1024} MB upload limit.")
        original=safe_name(urllib.parse.unquote(self.headers.get("X-IHD-Filename","upload.bin")))
        mime=self.headers.get("Content-Type","application/octet-stream").split(";")[0].strip().lower()
        if kind in ("take","beat","release") and not (mime.startswith("audio/") or mime in ("application/octet-stream",)):
            return self.error_json(415,"audio_required","This upload must be an audio file.")
        if kind=="artwork" and not mime.startswith("image/"):
            return self.error_json(415,"image_required","Artwork must be an image.")
        aid=secrets.token_hex(16); ext=Path(original).suffix[:10].lower(); storage=f"{aid}{ext}"
        folder=UPLOADS/kind/str(user["id"]); folder.mkdir(parents=True,exist_ok=True); path=folder/storage
        remaining=length
        with open(path,"wb") as f:
            while remaining:
                chunk=self.rfile.read(min(1024*1024,remaining))
                if not chunk: break
                f.write(chunk); remaining-=len(chunk)
        actual=path.stat().st_size
        if actual!=length:
            path.unlink(missing_ok=True); return self.error_json(400,"short_upload","Upload ended before all bytes were received.")
        with db() as con:
            con.execute("INSERT INTO assets(id,owner_user_id,kind,original_name,storage_name,mime,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (aid,user["id"],kind,original,storage,mime,actual,now_iso()))
            audit(con,user["id"],"asset_uploaded",aid,{"kind":kind,"name":original,"bytes":actual},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"asset":{"id":aid,"kind":kind,"name":original,"mime":mime,"size":actual,"url":f"/media/{aid}"}},201)

    def serve_media(self, aid):
        user=self.require_auth()
        if not user:return
        with db() as con:
            a=con.execute("SELECT * FROM assets WHERE id=?",(aid,)).fetchone()
            if not a:return self.error_json(404,"asset_missing","File not found.")
            public_ok=False
            if a["kind"]=="beat": public_ok=bool(user["verified"] and con.execute("SELECT 1 FROM beats WHERE asset_id=? AND public=1",(aid,)).fetchone())
            if a["kind"] in ("release","artwork"): public_ok=bool(user["verified"] and con.execute("SELECT 1 FROM releases WHERE (audio_asset_id=? OR artwork_asset_id=?) AND status='published'",(aid,aid)).fetchone())
            if a["owner_user_id"]!=user["id"] and not public_ok and user["role"] not in ("super_admin","admin"):
                return self.error_json(403,"asset_forbidden","You do not have access to this private file.")
            path=UPLOADS/a["kind"]/str(a["owner_user_id"])/a["storage_name"]
        if not path.exists():return self.error_json(404,"asset_missing","Stored file not found.")
        data=path.read_bytes(); self.send_response(200); self.send_header("Content-Type",a["mime"] or "application/octet-stream"); self.send_header("Content-Length",str(len(data))); self.send_header("Content-Disposition",f'inline; filename="{safe_name(a["original_name"])}"'); self.security_headers(); self.end_headers(); self.wfile.write(data)

    def api_projects_get(self):
        user=self.require_auth();
        if not user:return
        with db() as con:
            rows=con.execute("SELECT * FROM projects WHERE owner_user_id=? ORDER BY updated_at DESC LIMIT 100",(user["id"],)).fetchall()
        return self.send_json({"ok":True,"projects":[dict(r) | {"metadata":json.loads(r["metadata"])} for r in rows]})

    def api_projects_post(self):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); name=str(b.get("name","Untitled Session")).strip()[:120] or "Untitled Session"; metadata=b.get("metadata",{}); pid=str(b.get("id") or secrets.token_hex(12)); assets=b.get("asset_ids",[])
        with db() as con:
            existing=con.execute("SELECT owner_user_id FROM projects WHERE id=?",(pid,)).fetchone()
            if existing and existing["owner_user_id"]!=user["id"]: return self.error_json(403,"project_forbidden","Project belongs to another user.")
            ts=now_iso()
            if existing: con.execute("UPDATE projects SET name=?,metadata=?,updated_at=? WHERE id=?",(name,json.dumps(metadata),ts,pid))
            else: con.execute("INSERT INTO projects(id,owner_user_id,name,metadata,created_at,updated_at) VALUES(?,?,?,?,?,?)",(pid,user["id"],name,json.dumps(metadata),ts,ts))
            for aid in assets:
                own=con.execute("SELECT 1 FROM assets WHERE id=? AND owner_user_id=?",(aid,user["id"])).fetchone()
                if own: con.execute("INSERT OR IGNORE INTO project_assets(project_id,asset_id,label) VALUES(?,?,?)",(pid,aid,"take"))
            audit(con,user["id"],"project_saved",pid,{"name":name},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"project":{"id":pid,"name":name}},201 if not existing else 200)

    def api_beats_get(self):
        user=self.require_auth();
        if not user:return
        with db() as con:
            rows=con.execute("""SELECT b.*,u.display_name producer FROM beats b JOIN users u ON u.id=b.owner_user_id
                                WHERE b.public=1 OR b.owner_user_id=? ORDER BY b.created_at DESC LIMIT 200""",(user["id"],)).fetchall()
        beats=[dict(r) | {"audio_url":f"/media/{r['asset_id']}" if r["asset_id"] else None} for r in rows]
        return self.send_json({"ok":True,"beats":beats})

    def api_beats_post(self):
        user=self.require_auth(csrf=True,roles=("super_admin","admin","verified_producer"));
        if not user:return
        b=self.json_body(); title=str(b.get("title","")).strip()[:140]; license_text=str(b.get("license_text","")).strip()[:4000]; aid=b.get("asset_id")
        if not title or not license_text:return self.error_json(400,"missing_fields","Beat title and licensing terms are required.")
        if aid:
            with db() as con:
                if not con.execute("SELECT 1 FROM assets WHERE id=? AND owner_user_id=? AND kind='beat'",(aid,user["id"])).fetchone(): return self.error_json(400,"invalid_asset","Beat audio asset is invalid.")
        bid=secrets.token_hex(12)
        with db() as con:
            con.execute("INSERT INTO beats(id,owner_user_id,title,bpm,musical_key,license_text,asset_id,public,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (bid,user["id"],title,int(b.get("bpm") or 0) or None,str(b.get("musical_key","")).strip()[:30],license_text,aid,1 if b.get("public",True) else 0,now_iso()))
            audit(con,user["id"],"beat_published",bid,{"title":title},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"id":bid},201)

    def api_plugins_get(self):
        user=self.require_auth();
        if not user:return
        builtins=[
          {"id":"ihd-eq","name":"IHD Parametric EQ","category":"EQ","builtin":True},
          {"id":"ihd-compressor","name":"IHD Vocal Glue","category":"Dynamics","builtin":True},
          {"id":"ihd-delay","name":"IHD Pocket Delay","category":"Delay","builtin":True},
          {"id":"ihd-saturator","name":"IHD Heat","category":"Saturation","builtin":True},
          {"id":"ihd-space","name":"IHD Space","category":"Reverb","builtin":True}
        ]
        with db() as con:
            rows=con.execute("SELECT p.*,u.display_name producer FROM plugin_presets p JOIN users u ON u.id=p.owner_user_id WHERE p.public=1 OR p.owner_user_id=? ORDER BY created_at DESC",(user["id"],)).fetchall()
        return self.send_json({"ok":True,"builtins":builtins,"presets":[dict(r)|{"chain":json.loads(r["chain_json"])} for r in rows]})

    def api_plugins_post(self):
        user=self.require_auth(csrf=True,roles=("super_admin","admin","verified_producer"));
        if not user:return
        b=self.json_body(); name=str(b.get("name","")).strip()[:100]; category=str(b.get("category","Producer Chain")).strip()[:80]; chain=b.get("chain",[])
        if not name or not isinstance(chain,list) or len(chain)>24:return self.error_json(400,"invalid_plugin","Provide a name and a chain of up to 24 approved processors.")
        approved={"eq","compressor","delay","saturator","reverb","gain","highpass","lowpass"}
        for item in chain:
            if not isinstance(item,dict) or item.get("type") not in approved:return self.error_json(400,"unapproved_processor","Plugin presets may only use approved browser processors.")
        pid=secrets.token_hex(12)
        with db() as con:
            con.execute("INSERT INTO plugin_presets(id,owner_user_id,name,category,chain_json,public,created_at) VALUES(?,?,?,?,?,?,?)",(pid,user["id"],name,category,json.dumps(chain),1 if b.get("public",True) else 0,now_iso())); audit(con,user["id"],"plugin_preset_published",pid,{"name":name},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"id":pid},201)

    def api_releases_get(self):
        user=self.require_auth();
        if not user:return
        with db() as con:
            rows=con.execute("SELECT * FROM releases WHERE owner_user_id=? OR status='published' ORDER BY updated_at DESC",(user["id"],)).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["composition_splits"]=json.loads(d["composition_splits"]); d["master_splits"]=json.loads(d["master_splits"]); d["credits"]=json.loads(d["credits"]); d["share_url"]="/share/"+d["share_slug"]; out.append(d)
        return self.send_json({"ok":True,"releases":out})

    def api_releases_post(self):
        user=self.require_auth(csrf=True);
        if not user:return
        if not user["verified"]:return self.error_json(403,"verification_required","Only verified users may submit releases.")
        b=self.json_body(); title=str(b.get("title","")).strip()[:160]; artist=str(b.get("primary_artist","")).strip()[:160]
        if not title or not artist or not b.get("rights_attested"):return self.error_json(400,"release_requirements","Title, primary artist, and rights attestation are required.")
        comp=b.get("composition_splits",[]); master=b.get("master_splits",[]); credits=b.get("credits",[])
        def split_total(x):
            try:return round(sum(float(i.get("percent",0)) for i in x),4)
            except:return -1
        if comp and abs(split_total(comp)-100)>0.01:return self.error_json(400,"composition_split","Composition splits must total 100%.")
        if master and abs(split_total(master)-100)>0.01:return self.error_json(400,"master_split","Master splits must total 100%.")
        audio=b.get("audio_asset_id"); artwork=b.get("artwork_asset_id")
        with db() as con:
            for aid,kind in ((audio,"release"),(artwork,"artwork")):
                if aid and not con.execute("SELECT 1 FROM assets WHERE id=? AND owner_user_id=? AND kind=?",(aid,user["id"],kind)).fetchone():return self.error_json(400,"invalid_asset",f"Invalid {kind} asset.")
            rid=secrets.token_hex(12); slug=("".join(c.lower() if c.isalnum() else "-" for c in f"{artist}-{title}").strip("-")[:60] or "release")+"-"+rid[:6]; ts=now_iso(); status="published" if b.get("publish") else "draft"
            con.execute("""INSERT INTO releases(id,owner_user_id,title,primary_artist,audio_asset_id,artwork_asset_id,composition_splits,master_splits,credits,rights_attested,status,share_slug,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(rid,user["id"],title,artist,audio,artwork,json.dumps(comp),json.dumps(master),json.dumps(credits),1,status,slug,ts,ts)); audit(con,user["id"],"release_saved",rid,{"title":title,"status":status},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"id":rid,"share_url":"/share/"+slug},201)

    def serve_share(self, slug):
        with db() as con:
            r=con.execute("SELECT r.*,u.display_name FROM releases r JOIN users u ON u.id=r.owner_user_id WHERE r.share_slug=? AND r.status='published'",(slug,)).fetchone()
        if not r:return self.serve_static("/")
        title=self.html_escape(r["title"]); artist=self.html_escape(r["primary_artist"])
        body=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} — {artist} | IT HIT DIFFERENT LLC</title><meta property="og:title" content="{title} — {artist}"><meta property="og:description" content="Official IT HIT DIFFERENT LLC release page"><link rel="stylesheet" href="/app.css"></head><body class="share-page"><main class="share-card"><div class="logo-orb">IHD</div><p class="eyebrow">OFFICIAL RELEASE</p><h1>{title}</h1><h2>{artist}</h2><p class="muted">Published through the IT HIT DIFFERENT LLC Creator Network.</p><a class="btn primary" href="/">Enter Private Network</a></main></body></html>'''.encode()
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.security_headers(); self.end_headers(); self.wfile.write(body)

    def serve_invite(self, code):
        code=str(code or "").strip().upper()
        if not code:
            return self.serve_static("/")
        location=f"/?room={urllib.parse.quote(code)}"
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.security_headers()
        self.end_headers()
        self.wfile.write(f"<html><head><meta http-equiv=refresh content='0;url={location}'></head><body>If you are not redirected, <a href=\"{location}\">click here</a>.</body></html>".encode())

    def api_epk_get(self):
        user=self.require_auth();
        if not user:return
        with db() as con:r=con.execute("SELECT * FROM epk_profiles WHERE user_id=?",(user["id"],)).fetchone()
        d=dict(r) if r else {"artist_name":"","bio":"","market":"","business_email":"","links_json":"[]"}; d["links"]=json.loads(d.pop("links_json","[]")); return self.send_json({"ok":True,"epk":d})

    def api_epk_put(self):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); vals=(str(b.get("artist_name","")).strip()[:160],str(b.get("bio","")).strip()[:5000],str(b.get("market","")).strip()[:160],str(b.get("business_email","")).strip()[:200],json.dumps(b.get("links",[])[:20]),now_iso(),user["id"])
        with db() as con:
            con.execute("""INSERT INTO epk_profiles(artist_name,bio,market,business_email,links_json,updated_at,user_id) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET artist_name=excluded.artist_name,bio=excluded.bio,market=excluded.market,business_email=excluded.business_email,links_json=excluded.links_json,updated_at=excluded.updated_at""",vals); audit(con,user["id"],"epk_saved",str(user["id"]),ip=self.client_ip()); con.commit()
        return self.send_json({"ok":True})

    def api_directory(self):
        user=self.require_auth();
        if not user:return
        with db() as con:rows=con.execute("SELECT id,display_name,role,verified FROM users WHERE suspended=0 AND verified=1 AND id<>? ORDER BY display_name",(user["id"],)).fetchall()
        return self.send_json({"ok":True,"users":[dict(r)|{"verified":bool(r["verified"])} for r in rows]})

    def ensure_room_member(self, con, room_id, uid):
        row=con.execute("SELECT * FROM room_members WHERE room_id=? AND user_id=?",(room_id,uid)).fetchone()
        if row: con.execute("UPDATE room_members SET last_seen=? WHERE room_id=? AND user_id=?",(int(time.time()),room_id,uid))
        return row

    def api_rooms_get(self):
        user=self.require_auth();
        if not user:return
        with db() as con:
            rows=con.execute("""SELECT r.*,rm.permission,u.display_name host_name FROM room_members rm JOIN rooms r ON r.id=rm.room_id JOIN users u ON u.id=r.host_user_id WHERE rm.user_id=? ORDER BY r.created_at DESC""",(user["id"],)).fetchall()
        return self.send_json({"ok":True,"rooms":[dict(r) for r in rows]})

    def api_rooms_post(self):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); name=str(b.get("name","New Collaboration")).strip()[:120] or "New Collaboration"; rid=secrets.token_hex(12); ts=now_iso()
        code=None
        with db() as con:
            for _ in range(8):
                code=generate_room_code()
                try:
                    con.execute("INSERT INTO rooms(id,code,host_user_id,name,created_at) VALUES(?,?,?,?,?)",(rid,code,user["id"],name,ts))
                    break
                except sqlite3.IntegrityError:
                    code=None
            if not code:
                return self.error_json(500,"room_creation_failed","Could not generate a unique room code. Try again.")
            con.execute("INSERT INTO room_members(room_id,user_id,permission,joined_at,last_seen) VALUES(?,?,?,?,?)",(rid,user["id"],"host",ts,int(time.time())));
            audit(con,user["id"],"room_created",rid,{"name":name},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"room":{"id":rid,"code":code,"name":name,"share_url":f"/invite/{code}"}},201)

    def api_rooms_join(self):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); code=str(b.get("code","")).strip().upper()
        with db() as con:
            r=con.execute("SELECT * FROM rooms WHERE code=?",(code,)).fetchone()
            if not r:return self.error_json(404,"room_missing","Room code not found.")
            con.execute("INSERT OR IGNORE INTO room_members(room_id,user_id,permission,joined_at,last_seen) VALUES(?,?,?,?,?)",(r["id"],user["id"],"guest",now_iso(),int(time.time()))); audit(con,user["id"],"room_joined",r["id"],ip=self.client_ip()); con.commit()
        return self.send_json({"ok":True,"room":dict(r)})

    def api_room_members(self, rid):
        user=self.require_auth();
        if not user:return
        with db() as con:
            if not self.ensure_room_member(con,rid,user["id"]):return self.error_json(403,"room_forbidden","Join this room first.")
            rows=con.execute("""SELECT u.id,u.display_name,u.role,rm.permission,rm.last_seen FROM room_members rm JOIN users u ON u.id=rm.user_id WHERE rm.room_id=? AND u.suspended=0""",(rid,)).fetchall(); con.commit()
        now=int(time.time()); return self.send_json({"ok":True,"members":[dict(r)|{"online":now-r["last_seen"]<20} for r in rows]})

    def api_chat_get(self,rid):
        user=self.require_auth();
        if not user:return
        after=int((self.query.get("after") or [0])[0])
        with db() as con:
            if not self.ensure_room_member(con,rid,user["id"]):return self.error_json(403,"room_forbidden","Join this room first.")
            rows=con.execute("""SELECT m.id,m.body,m.created_at,u.id user_id,u.display_name FROM room_messages m JOIN users u ON u.id=m.user_id WHERE m.room_id=? AND m.id>? ORDER BY m.id LIMIT 100""",(rid,after)).fetchall(); con.commit()
        return self.send_json({"ok":True,"messages":[dict(r) for r in rows]})

    def api_chat_post(self,rid):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); body=str(b.get("body","")).strip()[:2000]
        if not body:return self.error_json(400,"empty_message","Message cannot be empty.")
        with db() as con:
            if not self.ensure_room_member(con,rid,user["id"]):return self.error_json(403,"room_forbidden","Join this room first.")
            cur=con.execute("INSERT INTO room_messages(room_id,user_id,body,created_at) VALUES(?,?,?,?)",(rid,user["id"],body,now_iso())); con.commit(); mid=cur.lastrowid
        return self.send_json({"ok":True,"id":mid},201)

    def api_signal_post(self,rid):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); to=int(b.get("to") or 0); st=str(b.get("type","")).strip(); payload=b.get("payload",{})
        if st not in ("offer","answer","ice","hangup"):return self.error_json(400,"signal_type","Unsupported signaling message.")
        with db() as con:
            if not self.ensure_room_member(con,rid,user["id"]):return self.error_json(403,"room_forbidden","Join this room first.")
            if not con.execute("SELECT 1 FROM room_members WHERE room_id=? AND user_id=?",(rid,to)).fetchone():return self.error_json(400,"peer_missing","Peer is not in this room.")
            con.execute("INSERT INTO signals(room_id,from_user_id,to_user_id,signal_type,payload,created_at) VALUES(?,?,?,?,?,?)",(rid,user["id"],to,st,json.dumps(payload),int(time.time()))); con.commit()
        return self.send_json({"ok":True},201)

    def api_signals_get(self,rid):
        user=self.require_auth();
        if not user:return
        after=int((self.query.get("after") or [0])[0])
        with db() as con:
            if not self.ensure_room_member(con,rid,user["id"]):return self.error_json(403,"room_forbidden","Join this room first.")
            rows=con.execute("SELECT * FROM signals WHERE room_id=? AND to_user_id=? AND id>? ORDER BY id LIMIT 200",(rid,user["id"],after)).fetchall(); con.commit()
        return self.send_json({"ok":True,"signals":[dict(r)|{"payload":json.loads(r["payload"])} for r in rows]})

    def api_invite_post(self,rid):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); invitee=int(b.get("user_id") or 0)
        with db() as con:
            room=con.execute("SELECT * FROM rooms WHERE id=?",(rid,)).fetchone(); member=con.execute("SELECT permission FROM room_members WHERE room_id=? AND user_id=?",(rid,user["id"])).fetchone()
            if not room or not member or member["permission"] not in ("host","cohost"):return self.error_json(403,"invite_forbidden","Only room hosts can invite collaborators.")
            if not con.execute("SELECT 1 FROM users WHERE id=? AND verified=1 AND suspended=0",(invitee,)).fetchone():return self.error_json(400,"invitee_missing","Verified collaborator not found.")
            iid=secrets.token_hex(12); con.execute("INSERT INTO room_invites(id,room_id,inviter_user_id,invitee_user_id,status,created_at) VALUES(?,?,?,?,?,?)",(iid,rid,user["id"],invitee,"pending",now_iso())); audit(con,user["id"],"room_invite",iid,{"room":rid,"invitee":invitee},self.client_ip()); con.commit()
        return self.send_json({"ok":True,"id":iid},201)

    def api_invites_get(self):
        user=self.require_auth();
        if not user:return
        with db() as con:
            rows=con.execute("""SELECT i.*,r.name room_name,r.code,u.display_name inviter_name FROM room_invites i JOIN rooms r ON r.id=i.room_id JOIN users u ON u.id=i.inviter_user_id WHERE i.invitee_user_id=? AND i.status='pending' ORDER BY i.created_at DESC""",(user["id"],)).fetchall()
        return self.send_json({"ok":True,"invites":[dict(r) for r in rows]})

    def api_invite_respond(self,iid):
        user=self.require_auth(csrf=True);
        if not user:return
        b=self.json_body(); status=str(b.get("status","")).lower()
        if status not in ("accepted","declined"):return self.error_json(400,"invite_status","Choose accepted or declined.")
        with db() as con:
            inv=con.execute("SELECT * FROM room_invites WHERE id=? AND invitee_user_id=? AND status='pending'",(iid,user["id"])).fetchone()
            if not inv:return self.error_json(404,"invite_missing","Invitation is no longer pending.")
            con.execute("UPDATE room_invites SET status=? WHERE id=?",(status,iid))
            if status=="accepted":con.execute("INSERT OR IGNORE INTO room_members(room_id,user_id,permission,joined_at,last_seen) VALUES(?,?,?,?,?)",(inv["room_id"],user["id"],"guest",now_iso(),int(time.time())))
            audit(con,user["id"],"room_invite_responded",iid,{"status":status},self.client_ip()); con.commit()
        return self.send_json({"ok":True})

    def api_admin_users(self):
        user=self.require_auth(roles=("super_admin","admin"));
        if not user:return
        with db() as con:rows=con.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return self.send_json({"ok":True,"users":[public_user(r) for r in rows]})

    def api_admin_create_user(self):
        user=self.require_auth(csrf=True,roles=("super_admin","admin"));
        if not user:return
        b=self.json_body(); email=str(b.get("email","")).strip().lower(); name=str(b.get("display_name","")).strip()[:120]; role=str(b.get("role","creator"))
        roles={"creator","verified_artist","verified_producer","admin"}
        if not email or "@" not in email or not name or role not in roles:return self.error_json(400,"user_fields","Valid email, display name and role are required.")
        if role=="admin" and user["role"]!="super_admin":return self.error_json(403,"owner_required","Only the master owner can create administrators.")
        temp=secrets.token_urlsafe(12)
        try:
            with db() as con:
                cur=con.execute("INSERT INTO users(email,display_name,role,verified,suspended,password_hash,must_change_password,created_at) VALUES(?,?,?,?,?,?,?,?)",(email,name,role,1 if role.startswith("verified_") or role=="admin" else 0,0,hash_password(temp),1,now_iso())); uid=cur.lastrowid; audit(con,user["id"],"user_created",str(uid),{"email":email,"role":role},self.client_ip()); con.commit()
        except sqlite3.IntegrityError:return self.error_json(409,"email_exists","An account with that email already exists.")
        return self.send_json({"ok":True,"user_id":uid,"temporary_password":temp,"message":"Temporary password is returned once. Send it to the user securely."},201)

    def api_admin_user_status(self,uid):
        user=self.require_auth(csrf=True,roles=("super_admin","admin"));
        if not user:return
        if uid==user["id"]:return self.error_json(400,"self_lockout","You cannot change your own status from this control.")
        b=self.json_body(); verified=b.get("verified"); suspended=b.get("suspended"); role=b.get("role")
        with db() as con:
            target=con.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
            if not target:return self.error_json(404,"user_missing","User not found.")
            if target["role"]=="super_admin":return self.error_json(403,"master_protected","The master owner cannot be modified here.")
            if user["role"]!="super_admin" and target["role"]=="admin":return self.error_json(403,"owner_required","Only the master owner can modify administrators.")
            if role is not None:
                allowed={"creator","verified_artist","verified_producer","admin"}
                if role not in allowed:return self.error_json(400,"role_invalid","Unsupported role.")
                if role=="admin" and user["role"]!="super_admin":return self.error_json(403,"owner_required","Only master can grant admin.")
                con.execute("UPDATE users SET role=? WHERE id=?",(role,uid))
            if verified is not None:con.execute("UPDATE users SET verified=? WHERE id=?",(1 if verified else 0,uid))
            if suspended is not None:
                con.execute("UPDATE users SET suspended=? WHERE id=?",(1 if suspended else 0,uid))
                if suspended:con.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
            audit(con,user["id"],"user_status_changed",str(uid),{"verified":verified,"suspended":suspended,"role":role},self.client_ip()); con.commit()
        return self.send_json({"ok":True})

    def api_admin_audit(self):
        user=self.require_auth(roles=("super_admin","admin"));
        if not user:return
        with db() as con:
            rows=con.execute("""SELECT a.*,u.display_name actor FROM audit_events a LEFT JOIN users u ON u.id=a.actor_user_id ORDER BY a.id DESC LIMIT 300""").fetchall()
        return self.send_json({"ok":True,"events":[dict(r)|{"details":json.loads(r["details"] or "{}") } for r in rows]})

    def serve_static(self,p):
        if p in ("/","/index.html"): target=STATIC/"index.html"
        else:
            rel=p.lstrip("/"); target=(STATIC/rel).resolve()
            if STATIC.resolve() not in target.parents and target!=STATIC.resolve():return self.error_json(403,"forbidden","Invalid path.")
            if not target.exists() or not target.is_file():target=STATIC/"index.html"
        data=target.read_bytes(); mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",mime + ("; charset=utf-8" if mime.startswith("text/") or mime in ("application/javascript","application/json") else "")); self.send_header("Content-Length",str(len(data))); self.security_headers(); self.send_header("Cache-Control","no-store" if target.name=="index.html" else "public, max-age=300"); self.end_headers(); self.wfile.write(data)

    @staticmethod
    def html_escape(s):
        return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#39;")


def main():
    init_db()
    srv=ThreadingHTTPServer((HOST,PORT),Handler)
    print(f"IT HIT DIFFERENT LLC Creator Network running at http://{HOST}:{PORT}")
    print("For LAN testing, set IHD_HOST=0.0.0.0. Put HTTPS/reverse proxy in front for production.")
    try:srv.serve_forever()
    except KeyboardInterrupt:print("\nShutting down.")
    finally:srv.server_close()

if __name__=="__main__":main()
