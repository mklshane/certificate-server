from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from app.routes import template_routes

app = FastAPI()

# Allow frontend access
# Allow frontend (Next.js) access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change later in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(template_routes.router, prefix="/api")

@app.get("/")
def root():
    return{"message": "Certify Backend Running!"}
