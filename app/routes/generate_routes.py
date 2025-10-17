import os
import fitz  # PyMuPDF
import pandas as pd
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .mapping_routes import session_data

router = APIRouter()

OUTPUT_DIR = "app/static/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PLACEHOLDER_RE = re.compile(r"<<(.*?)>>")

def replace_placeholders_in_pdf(input_path: str, output_path: str, mappings: dict, row: pd.Series):
    """
    Replace placeholders in a PDF template by redacting them and inserting replacement text.

    Args:
        input_path: Path to the template PDF.
        output_path: Path to save the filled PDF.
        mappings: Dictionary mapping placeholder keys to CSV column names.
        row: Pandas Series containing data for one participant.
    """
    doc = fitz.open(input_path)

    for page in doc:
        # First pass: find all placeholders and their positions
        placeholder_data = []
        text_instances = page.get_text("dict")

        for block in text_instances.get("blocks", []):
            if block["type"] != 0:  # Only text blocks
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    span_rect = fitz.Rect(span["bbox"])

                    for match in PLACEHOLDER_RE.finditer(span_text):
                        placeholder_key = match.group(1).strip()
                        if placeholder_key not in mappings:
                            print(f"Warning: Placeholder '{placeholder_key}' not found in mappings")
                            continue

                        csv_col = mappings[placeholder_key]
                        replacement_text = str(row.get(csv_col, "")).strip()
                        if not replacement_text:
                            print(f"Warning: No value for column '{csv_col}' in row")
                            continue

                        # Calculate the exact position of the placeholder
                        start_pos, end_pos = match.span()
                        total_chars = max(len(span_text), 1)
                        char_width = span_rect.width / total_chars
                        x0 = span_rect.x0 + (char_width * start_pos)
                        x1 = span_rect.x0 + (char_width * end_pos)
                        placeholder_rect = fitz.Rect(x0, span_rect.y0, x1, span_rect.y1)

                        # Expand rectangle for text insertion
                        adjusted_rect = fitz.Rect(
                            x0 - 2,
                            span_rect.y0 - 2,
                            x1 + (char_width * len(replacement_text) * 1.5),  # Adjust width for text length
                            span_rect.y1 + 2
                        )

                        placeholder_data.append({
                            "rect": placeholder_rect,
                            "insert_rect": adjusted_rect,
                            "text": replacement_text,
                            "fontsize": span.get("size", 12),
                            "fontname": span.get("font", "helv"),  # Try to use detected font
                            "color": (0, 0, 0)  # Default to black
                        })
                        print(f"Replacing '{match.group(0)}' with '{replacement_text}' at rect {adjusted_rect}")

        # Second pass: redact placeholders
        for data in placeholder_data:
            page.add_redact_annot(data["rect"], fill=None)  # Transparent redaction

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        print(f"Applied {len(placeholder_data)} redactions on page {page.number}")

        # Third pass: insert replacement text
        for data in placeholder_data:
            try:
                page.insert_textbox(
                    data["insert_rect"],
                    data["text"],
                    fontsize=data["fontsize"],
                    fontname=data["fontname"],
                    color=data["color"],
                    align=0  # Left-align
                )
                print(f"Inserted text '{data['text']}' at rect {data['insert_rect']}")
            except Exception as e:
                print(f"Text insertion failed for '{data['text']}' at {data['insert_rect']}: {e}")
                # Fallback with simpler insertion
                try:
                    page.insert_text(
                        data["insert_rect"].tl + (0, data["fontsize"] * 1),
                        data["text"],
                        fontsize=data["fontsize"],
                        fontname="helv", 
                        color=(0, 0, 0)
                    )
                    print(f"Fallback inserted text '{data['text']}' at {data['insert_rect'].tl}")
                except Exception as e2:
                    print(f"Fallback insertion failed: {e2}")

    doc.save(output_path, garbage=4, deflate=True)  # Optimize PDF
    doc.close()
    print(f"Saved filled PDF to {output_path}")

def debug_pdf_text(input_path: str):
    """
    Debug function to see what text is detectable in the PDF.
    """
    doc = fitz.open(input_path)
    print(f"\n=== DEBUG PDF TEXT ===")
    print(f"Pages: {len(doc)}")

    for page_num, page in enumerate(doc):
        text = page.get_text()
        print(f"\nPage {page_num + 1} text: '{text}'")

        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block["type"] == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        print(f"  Span: '{span.get('text', '')}' at {span.get('bbox')}, "
                              f"size: {span.get('size')}, font: {span.get('font')}")

    doc.close()

@router.get("/generate-preview")
def generate_preview():
    """
    Generate a preview PDF by replacing placeholders in the template with data from the first row of the CSV.
    """
    template_file = session_data.get("template_file")
    csv_file = session_data.get("csv_file")
    mappings = session_data.get("mappings")

    if not template_file or not csv_file or not mappings:
        raise HTTPException(status_code=400, detail="Missing template, CSV, or mappings")

    template_path = f"app/static/templates/{template_file}"
    csv_path = f"app/static/csv/{csv_file}"

    if not os.path.exists(template_path):
        raise HTTPException(status_code=400, detail="Template file not found")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=400, detail="CSV file not found")

    # Debug: Check what's in the PDF
    print("=== DEBUGGING PDF ===")
    debug_pdf_text(template_path)

    df = pd.read_csv(csv_path)
    if df.empty:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    row = df.iloc[0]
    print(f"=== USING DATA ===")
    print(f"Mappings: {mappings}")
    print(f"Row data: {dict(row)}")

    # Generate replacement values
    for key, csv_col in mappings.items():
        replacement_text = str(row.get(csv_col, ""))
        print(f"Replacing <<{key}>> with '{replacement_text}' (from column '{csv_col}')")

    output_path = os.path.join(OUTPUT_DIR, "preview.pdf")

    try:
        replace_placeholders_in_pdf(template_path, output_path, mappings, row)
        print("=== PREVIEW GENERATED ===")
        debug_pdf_text(output_path)
    except Exception as e:
        print(f"Error generating preview: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")

    if not os.path.exists(output_path):
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

    return FileResponse(output_path, media_type="application/pdf", filename="preview.pdf")