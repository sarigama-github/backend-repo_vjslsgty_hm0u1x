import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Forge Peptides API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Utility
# -----------------------------
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


# -----------------------------
# Schemas
# -----------------------------
class ProductModel(BaseModel):
    name: str = Field(..., description="Product name")
    sequence: str = Field(..., description="Amino acid sequence")
    purity: float = Field(..., ge=0, le=100, description="Purity percentage")
    description: Optional[str] = Field(None, description="Concise one-line description")
    category: str = Field(..., description="Product category")
    length: int = Field(..., ge=1, description="Peptide length")
    datasheet_url: Optional[str] = Field(None, description="URL to PDF datasheet")
    image: Optional[str] = Field(None, description="Image URL or icon ref")


class ProductOut(ProductModel):
    id: str


class InquiryModel(BaseModel):
    name: str
    email: EmailStr
    organization: Optional[str] = None
    subject: str
    message: str
    type: str = Field("contact", description="contact or quote")
    product_id: Optional[str] = Field(None, description="Related product ID for quote requests")


# -----------------------------
# Startup seed
# -----------------------------
@app.on_event("startup")
async def seed_products():
    if db is None:
        return
    try:
        count = db["product"].count_documents({})
        if count == 0:
            sample_products = [
                {
                    "name": "BPC-157",
                    "sequence": "Gly-Glu-Pro-Pro-Pro-Gly-Lys-Pro-Ala-Asp-Asp-Ala-Gly-Leu-Val",
                    "purity": 98.5,
                    "description": ">98% purity, research-grade peptide",
                    "category": "Bioactive Peptides",
                    "length": 15,
                    "datasheet_url": "https://example.com/datasheets/bpc-157.pdf",
                    "image": "/vial.png",
                },
                {
                    "name": "GHRP-6",
                    "sequence": "His-DTrp-Ala-Trp-DPhe-Lys-NH2",
                    "purity": 99.2,
                    "description": "HPLC purified, MS verified",
                    "category": "Bioactive Peptides",
                    "length": 6,
                    "datasheet_url": "https://example.com/datasheets/ghrp6.pdf",
                    "image": "/vial.png",
                },
                {
                    "name": "Magainin II",
                    "sequence": "GIGKFLHSAKKFGKAFVGEIMNS",
                    "purity": 98.0,
                    "description": "Antibacterial peptide, >98%",
                    "category": "Antibacterial",
                    "length": 23,
                    "datasheet_url": "https://example.com/datasheets/magainin2.pdf",
                    "image": "/vial.png",
                },
                {
                    "name": "Palmitoyl Tripeptide-1",
                    "sequence": "Palmitoyl-Gly-His-Lys",
                    "purity": 98.7,
                    "description": "Cosmetic grade, MS/HPLC documented",
                    "category": "Cosmetic",
                    "length": 3,
                    "datasheet_url": "https://example.com/datasheets/pal-ghk.pdf",
                    "image": "/vial.png",
                },
            ]
            for p in sample_products:
                p["created_at"] = p["updated_at"] = None  # create_document sets these
                create_document("product", p)
    except Exception:
        # Ignore seeding errors in preview environments
        pass


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return {"message": "Forge Peptides API running"}


@app.get("/api/products", response_model=List[ProductOut])
def list_products(
    category: Optional[str] = None,
    length_min: Optional[int] = None,
    length_max: Optional[int] = None,
    purity_min: Optional[float] = None,
):
    if db is None:
        return []
    query: dict = {}
    if category:
        query["category"] = category
    if length_min is not None or length_max is not None:
        rng = {}
        if length_min is not None:
            rng["$gte"] = length_min
        if length_max is not None:
            rng["$lte"] = length_max
        query["length"] = rng
    if purity_min is not None:
        query["purity"] = {"$gte": purity_min}

    docs = get_documents("product", query)
    result: List[ProductOut] = []
    for d in docs:
        d_id = str(d.get("_id")) if d.get("_id") else ""
        result.append(ProductOut(id=d_id, **{k: d.get(k) for k in ProductModel.model_fields.keys()}))
    return result


@app.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: str):
    if db is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        doc = db["product"].find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return ProductOut(id=str(doc["_id"]), **{k: doc.get(k) for k in ProductModel.model_fields.keys()})


@app.get("/api/categories", response_model=List[str])
def categories():
    if db is None:
        return []
    return sorted(db["product"].distinct("category"))


@app.post("/api/inquiry")
def submit_inquiry(payload: InquiryModel):
    data = payload.model_dump()
    # Basic transform: attach product name if provided
    if payload.product_id and db is not None:
        try:
            doc = db["product"].find_one({"_id": ObjectId(payload.product_id)})
            if doc:
                data["product_name"] = doc.get("name")
        except Exception:
            pass
    try:
        doc_id = create_document("inquiry", data)
        return {"status": "ok", "id": doc_id}
    except Exception as e:
        # If database not configured, still return success for demo purposes
        return {"status": "ok", "id": None, "note": "Database not configured in this preview"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
