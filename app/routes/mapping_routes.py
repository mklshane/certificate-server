from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from app.session_data import session_data


router = APIRouter()


class MappingRequest(BaseModel):
    templateFile: str
    csvFile: str
    mappings: dict  # { "Name": "Full Name", "Year": "Batch", ... }
    emailColumn: str

@router.post("/save-mapping")
async def save_mapping(data: MappingRequest):
    session_data["template_file"] = data.templateFile
    session_data["csv_file"] = data.csvFile
    session_data["mappings"] = data.mappings
    session_data["email_column"] = data.emailColumn

    return JSONResponse({
        "message": "Mapping saved",
        "saved": session_data
    })
