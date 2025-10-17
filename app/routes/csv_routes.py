import os
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.session_data import session_data


router = APIRouter()

UPLOAD_DIR = "app/static/csv"
os.makedirs(UPLOAD_DIR, exist_ok=True)
@router.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1].lower()
    if ext not in ["csv"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only CSV files allowed."
        )

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    try:
        df = pd.read_csv(file_path)
        columns = list(df.columns)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error reading CSV file: {str(e)}"
        )

    # ✅ Save to session_data
    session_data["csv_file"] = file.filename

    return JSONResponse({
        "message": "CSV uploaded successfully",
        "fileName": file.filename,
        "columns": columns
    })
