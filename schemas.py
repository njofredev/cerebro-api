from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class DetalleBase(BaseModel):
    codigo_examen: str
    nombre_examen: str
    valor_copago: int

class CotizacionBase(BaseModel):
    folio: str
    documento_id: str
    nombre_paciente: str
    fecha_cotizacion: datetime
    total_copago: int
    detalles: Optional[List[DetalleBase]] = []

    class Config:
        from_attributes = True