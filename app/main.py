from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
def root():
    return{"message": "Certify Backend Running!"}
