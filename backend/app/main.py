from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine, settings, SessionLocal
from .models import Role
from .routers import auth, crm, finance, expanded, documents

DEFAULT_ROLES = [
    "Super Admin", "Management", "Sales / Business Development",
    "Internship Coordinator", "Training Coordinator", "Finance / Accounts",
    "Marketing Executive", "Project / Team Manager", "Employee / Intern"
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key in {"CHANGE_ME_BEFORE_DEPLOYMENT", "replace-with-a-long-random-secret-before-running"} or len(settings.secret_key) < 32:
        raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters before starting the API.")
    if settings.auto_create_schema:
        # Keep create_all as a local development convenience. Deployed environments
        # use the explicit Alembic migration command before starting the API.
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for name in DEFAULT_ROLES:
            if not db.query(Role).filter(Role.name == name).first(): db.add(Role(name=name))
        db.commit()
    yield

app = FastAPI(title="HRUTA OneCRM API", version="1.0.0", description="Role-based sales, internship, training, partnership, finance, and project CRM API", lifespan=lifespan)
origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
allow_all = "*" in origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else origins,
    allow_origin_regex=None if allow_all else (settings.cors_origin_regex or None),
    allow_credentials=not allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(crm.router, prefix="/api/v1")
app.include_router(finance.router, prefix="/api/v1")
app.include_router(expanded.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")

@app.get("/", tags=["System"])
@app.head("/", tags=["System"])
def root():
    return {
        "status": "online",
        "service": "HRUTA OneCRM API",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0"
    }

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "service": "HRUTA OneCRM API"}

