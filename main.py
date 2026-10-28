import json
import os
import xml.etree.ElementTree as ET
import urllib.request
from urllib.parse import urlencode
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import jwt
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

app = FastAPI()

# Load the secret key from environment variable
SECRET_KEY = os.getenv("SECRET_KEY", "lmaopisan") 

# Load the base form url from environment variable
FORM_LINK = os.getenv("FORM_LINK", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

# Open Json
with open ("parsed.json", "r") as file:
    faculty_data = json.load(file)

# Maps readable field names to the Google Form's entry IDs, so callers
# of get_form_link() don't need to know the raw entry.XXXXXXX codes.
FORM_FIELD_ENTRIES = {
    "name": "entry.1254159707",
    "email": "entry.709516174",
    "whatsapp": "entry.2070004909",
    "line_id": "entry.10108758",
    "faculty": "entry.1855554993",
    "major": "entry.1617867247",
    "batch": "entry.1810171063",
}

FACULTY_LABEL_OVERRIDES = {
    "Ilmu Pengetahuan Budaya": "Ilmu Budaya",
    "Matematika dan Ilmu Pengetahuan Alam": "Matematika dan Pengetahuan Alam",
}

def get_faculty_label(faculty: str) -> str:
    if faculty == "Pendidikan Vokasi":
        return "Program Pendidikan Vokasi"
    return f"Fakultas {FACULTY_LABEL_OVERRIDES.get(faculty, faculty)}"

def get_form_link(base_url: str, **fields):
    """Build a pre-filled Google Form link.

    Usage:
        get_form_link(
            FORM_LINK,
            name=name,
            email=email,
            faculty=faculty,
            major=major,
            batch=batch,
        )
    """
    params = {"usp": "pp_url"}

    for field_name, value in fields.items():
        if field_name not in FORM_FIELD_ENTRIES:
            raise ValueError(f"Unknown form field: {field_name}")
        if value is not None:
            params[FORM_FIELD_ENTRIES[field_name]] = value

    return f"{base_url}?{urlencode(params)}"

@app.get("/")
async def index(request: Request):
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"/member{query}")

@app.get("/member")
async def root(request: Request, service="", ticket=""):

    current_url = request.url
    
    if not service and not ticket:
        return RedirectResponse(url=f"https://sso.ui.ac.id/cas2/login?service={current_url}")
    
    current_url = str(current_url).split("?")[0]
    fetch_url = f"https://sso.ui.ac.id/cas2/serviceValidate?service={current_url}&ticket={ticket}"
    
    try:
        print("Fetching URL:", fetch_url)  # Debugging line to check the fetch URL
        with urllib.request.urlopen(fetch_url) as response:
            raw_data = response.read().decode("utf-8")

        print("Raw XML Data:", raw_data)  # Debugging line to check the raw XML data
        
        cleaned_xml = raw_data.strip()
        root = ET.fromstring(cleaned_xml)
        namespace = {'cas': 'http://www.yale.edu/tp/cas'}
        
        user = root.find(".//cas:user", namespace).text
        ldap_cn = root.find(".//cas:ldap_cn", namespace).text
        kd_org = root.find(".//cas:kd_org", namespace).text
        role = root.find(".//cas:peran_user", namespace).text
        name = root.find(".//cas:nama", namespace).text
        npm = root.find(".//cas:npm", namespace).text
        
        # Create a payload for JWT
        payload = {
            "user": user,
            "ldap_cn": ldap_cn,
            "organizational_code": kd_org,
            "role": role,
            "name": name,
            "npm": npm
        }

        print("Parsed User Data:", payload)  # Debugging line to check parsed user data
        
        
        # Get Json Data based on organizational code
        user_faculty_data = [faculty for faculty in faculty_data if faculty["id"] == kd_org][0]
        
        # Encrypt the data with JWT (kept for /validate; the current form
        # has no field to carry it, so it isn't part of the prefill link)
        token = jwt.encode(payload=payload, key=SECRET_KEY, algorithm='HS256')
        print("Generated Token:", token)  # Debugging line so the token can still be retrieved for /validate

        npm_prefix = npm[:2]

        faculty = user_faculty_data["fakultas"]
        major = user_faculty_data["prodi"]

        if (npm_prefix == "24"):
            batch = "2024"
        elif (npm_prefix == "25"):
            batch = "2025"
        elif (npm_prefix == "26"):
            batch = "2026"
        else:
            batch = None

        form_link = get_form_link(
            f"{FORM_LINK}/viewform",
            name=name,
            email=f"{user}@ui.ac.id",
            faculty=get_faculty_label(faculty),
            major=major,
            batch=batch,
        )

        return RedirectResponse(url=form_link)
        
    except ET.ParseError as e:
        print(f"XML Parsing Error: {e}")
        return {"error": "Failed to parse the XML response", "details": str(e)}
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return {"error": "An unexpected error occurred", "details": str(e)}

@app.get("/validate")
async def validate(request: Request, token=""):
    try:
        if not token:
            return {"error": "Token is not valid"}
        
        decoded = jwt.decode(token.strip(), SECRET_KEY, algorithms=["HS256"])
        
        csv = ",".join([f"{value}" for key, value in decoded.items()])
        
        return csv
    except jwt.InvalidTokenError:
        return "Token is Not Valid"
    
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app)