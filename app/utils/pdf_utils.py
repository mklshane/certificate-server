# app/utils/pdf_utils.py
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import fitz  # PyMuPDF

def replace_placeholders_in_pdf(template_path: str, output_path: str, mapping: dict, row_data):
    """Replace placeholders in PDF template with actual data from CSV row"""
    try:
        # Open the template PDF
        doc = fitz.open(template_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Search for placeholders and replace them
            for placeholder, column_name in mapping.items():
                if not column_name:  # Skip empty mappings
                    continue
                    
                # Get the value from the row data
                value = str(row_data.get(column_name, "")).strip()
                if not value:
                    continue
                
                # Search for the placeholder pattern
                placeholder_text = f"<<{placeholder}>>"
                
                # Search for text instances
                text_instances = page.search_for(placeholder_text)
                
                for inst in text_instances:
                    # Replace the placeholder with actual value
                    page.add_redact_annot(inst, value, fill=(1, 1, 1))
            
            # Apply the redactions (replacements)
            page.apply_redactions()
        
        # Save the modified PDF
        doc.save(output_path)
        doc.close()
        
        print(f"PDF generated successfully: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        if 'doc' in locals():
            doc.close()
        raise e