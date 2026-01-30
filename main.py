from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List
import uvicorn

app = FastAPI(title="Cerebro API - Policlínico Tabancura")

# --- MODELOS DE DATOS (SCHEMAS) ---

class DetalleBase(BaseModel):
    codigo_examen: str
    nombre_examen: str
    valor_copago: int

class OrdenMedicaIn(BaseModel):
    folio: str
    rut: str

# --- LÓGICA DE CONEXIÓN (IDÉNTICA A TU COTIZADOR) ---

def conectar_db():
    # Intenta obtener de variables de entorno (Coolify/Docker)
    host = os.getenv("POSTGRES_HOST")
    if host:
        database = os.getenv("POSTGRES_DATABASE")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        port = os.getenv("POSTGRES_PORT")
    else:
        # Nota: FastAPI no accede a st.secrets de Streamlit. 
        # Asegúrate de configurar las Variables de Entorno en Coolify.
        return None

    try:
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port,
            sslmode="disable" # Mantenemos tu config de seguridad
        )
        return conn
    except Exception as e:
        print(f"Error crítico de conexión a DB: {e}")
        return None

# --- ENDPOINTS ---

@app.get("/cotizaciones/buscar/{rut}")
def buscar_cotizaciones_por_rut(rut: str):
    """Busca cotizaciones usando el documento_id del paciente"""
    conn = conectar_db()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a DB")
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Buscamos por documento_id (RUT con puntos y guion)
        query = "SELECT * FROM cotizaciones WHERE documento_id = %s ORDER BY fecha_cotizacion DESC"
        cur.execute(query, (rut,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if not rows:
            raise HTTPException(status_code=404, detail="No se encontraron cotizaciones para este RUT")
        return rows
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cotizaciones/detalle/{folio}", response_model=List[DetalleBase])
def obtener_detalle_cotizacion(folio: str):
    """Trae los exámenes asociados a un folio específico"""
    conn = conectar_db()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a DB")
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = "SELECT codigo_examen, nombre_examen, valor_copago FROM detalle_cotizaciones WHERE folio_cotizacion = %s"
        cur.execute(query, (folio,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ordenes/generar")
def generar_orden_medica(orden: OrdenMedicaIn):
    """Registra la conversión de una cotización en una orden médica"""
    conn = conectar_db()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a DB")
    
    try:
        cur = conn.cursor()
        # Insertamos en la nueva tabla de trazabilidad
        query = """
            INSERT INTO ordenes_medicas (folio_cotizacion, rut_paciente) 
            VALUES (%s, %s)
        """
        cur.execute(query, (orden.folio, orden.rut))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Orden vinculada exitosamente al folio {orden.folio}"}
    except psycopg2.errors.UniqueViolation:
        if conn: conn.close()
        raise HTTPException(status_code=400, detail="Esta cotización ya fue convertida en una orden previamente.")
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)