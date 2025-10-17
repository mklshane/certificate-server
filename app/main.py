from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from app.routes import template_routes, csv_routes, mapping_routes, generate_routes, email_routes

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(template_routes.router, prefix="/api")
app.include_router(csv_routes.router, prefix="/api")
app.include_router(mapping_routes.router, prefix="/api")
app.include_router(generate_routes.router, prefix="/api")
app.include_router(email_routes.router, prefix="/api")

@app.get("/")
def root():
    return{"message": "Certify Backend Running!"}
