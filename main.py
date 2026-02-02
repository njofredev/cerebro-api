from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List
import uvicorn
import json
from datetime import datetime

app = FastAPI(title="Cerebro API - Policlínico Tabancura")

# --- MODELOS DE DATOS (SCHEMAS) ---

class DetalleBase(BaseModel):
    codigo_examen: str
    nombre_examen: str
    valor_copago: int

class OrdenMedicaIn(BaseModel):
    folio: str
    rut: str

class ItemActualizacion(BaseModel):
    # Mapeo directo de las columnas del data_editor de Streamlit
    codigo_ingreso: str
    nombre_prestacion: str
    copago: int

class ActualizarCotizacionIn(BaseModel):
    folio: str
    items: List[dict]

class AuditoriaOrdenIn(BaseModel):
    rut_paciente: str
    nombre_paciente: str
    folio_origen: str
    cantidad_examenes: int
    codigos: List[str]

# --- LÓGICA DE CONEXIÓN ---

def conectar_db():
    host = os.getenv("POSTGRES_HOST")
    if host:
        database = os.getenv("POSTGRES_DATABASE")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        port = os.getenv("POSTGRES_PORT")
        try:
            conn = psycopg2.connect(
                host=host,
                database=database,
                user=user,
                password=password,
                port=port,
                sslmode="disable"
            )
            return conn
        except Exception as e:
            print(f"Error de conexión: {e}")
            return None
    return None

# --- ENDPOINTS ---

@app.get("/cotizaciones/buscar/{rut}")
def buscar_cotizaciones_por_rut(rut: str):
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = "SELECT * FROM cotizaciones WHERE documento_id = %s ORDER BY fecha_cotizacion DESC"
        cur.execute(query, (rut,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows: raise HTTPException(status_code=404, detail="No se encontraron cotizaciones")
        return rows
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cotizaciones/detalle/{folio}", response_model=List[DetalleBase])
def obtener_detalle_cotizacion(folio: str):
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Sincronizado con nombres de columnas de imagen_02a7c0.png
        query = "SELECT codigo_examen, nombre_examen, valor_copago FROM detalle_cotizaciones WHERE folio_cotizacion = %s"
        cur.execute(query, (folio,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cotizaciones/actualizar")
def actualizar_cotizacion(data: ActualizarCotizacionIn):
    """Actualiza los exámenes de una cotización tras ser editados en el portal"""
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor()
        # 1. Eliminar detalle previo según folio_cotizacion
        cur.execute("DELETE FROM detalle_cotizaciones WHERE folio_cotizacion = %s", (data.folio,))
        
        # 2. Insertar nuevos items editados
        for item in data.items:
            cur.execute("""
                INSERT INTO detalle_cotizaciones (folio_cotizacion, codigo_examen, nombre_examen, valor_copago)
                VALUES (%s, %s, %s, %s)
            """, (
                data.folio, 
                str(item.get('Codigo Ingreso', '')), 
                item.get('Nombre prestación en Fonasa o Particular', ''),
                int(item.get('Copago', 0))
            ))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Detalle del folio {data.folio} actualizado"}
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auditoria/ordenes")
def registrar_auditoria(audit: AuditoriaOrdenIn):
    """Registra auditoría detallada de la generación de órdenes"""
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor()
        # Insertar en la tabla de auditoría (debe ser creada previamente)
        query = """
            INSERT INTO auditoria_examenes 
            (rut_paciente, nombre_paciente, folio_origen, cantidad_examenes, codigos_json)
            VALUES (%s, %s, %s, %s, %s)
        """
        cur.execute(query, (
            audit.rut_paciente,
            audit.nombre_paciente,
            audit.folio_origen,
            audit.cantidad_examenes,
            json.dumps(audit.codigos)
        ))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Auditoría registrada"}
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ordenes/generar")
def generar_orden_medica(orden: OrdenMedicaIn):
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor()
        query = "INSERT INTO ordenes_medicas (folio_cotizacion, rut_paciente) VALUES (%s, %s)"
        cur.execute(query, (orden.folio, orden.rut))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Orden vinculada al folio {orden.folio}"}
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/auditoria/historial")
def obtener_historial_auditoria():
    """Consulta todos los registros de la tabla de auditoría"""
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Ordenamos por los más recientes primero
        query = "SELECT * FROM auditoria_examenes ORDER BY fecha_emision DESC"
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)