from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List, Optional
import uvicorn
import json
from datetime import datetime

app = FastAPI(title="Cerebro API - Policlínico Tabancura")

# --- MODELOS DE DATOS (SCHEMAS) ---

class DetalleBase(BaseModel):
    codigo_examen: str
    nombre_examen: str
    valor_copago: int

class ExamenItem(BaseModel):
    # Mapeo exacto de las claves que envía el data_editor de Streamlit
    codigo_ingreso: str = Optional[str]
    nombre_prestacion: str = Optional[str]

class NuevaOrdenIn(BaseModel):
    folio_cotizacion: str
    rut_paciente: str
    examenes: List[dict] # Recibe la lista de exámenes desde Streamlit

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
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST"),
            database=os.getenv("POSTGRES_DATABASE"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            sslmode="disable"
        )
        return conn
    except Exception as e:
        print(f"Error de conexión: {e}")
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
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión a DB")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM detalle_cotizaciones WHERE folio_cotizacion = %s", (data.folio,))
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
        return {"status": "success"}
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ordenes/nueva", status_code=201)
def crear_nueva_orden_clinica(data: NuevaOrdenIn):
    """Inserta la orden y sus detalles devolviendo el Folio SERIAL generado"""
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión")
    try:
        cur = conn.cursor()
        # 1. Insertar Cabecera y obtener Folio SERIAL
        query_cabecera = """
            INSERT INTO ordenes_clinicas (folio_cotizacion_origen, rut_paciente)
            VALUES (%s, %s) RETURNING folio_orden
        """
        cur.execute(query_cabecera, (data.folio_cotizacion, data.rut_paciente))
        nuevo_folio = cur.fetchone()[0]

        # 2. Insertar Detalles
        query_detalle = """
            INSERT INTO ordenes_detalles (folio_orden, codigo_examen, nombre_examen)
            VALUES (%s, %s, %s)
        """
        for examen in data.examenes:
            cur.execute(query_detalle, (
                nuevo_folio,
                str(examen.get('Codigo Ingreso', '')),
                examen.get('Nombre prestación en Fonasa o Particular', '')
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "folio_orden": nuevo_folio}
    except Exception as e:
        if conn: 
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail=f"Error en transacción: {str(e)}")

@app.post("/auditoria/ordenes")
def registrar_auditoria(audit: AuditoriaOrdenIn):
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión")
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO auditoria_examenes 
            (rut_paciente, nombre_paciente, folio_origen, cantidad_examenes, codigos_json)
            VALUES (%s, %s, %s, %s, %s)
        """
        cur.execute(query, (
            audit.rut_paciente, audit.nombre_paciente, audit.folio_origen,
            audit.cantidad_examenes, json.dumps(audit.codigos)
        ))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auditoria/historial")
def obtener_historial_auditoria():
    conn = conectar_db()
    if not conn: raise HTTPException(status_code=500, detail="Error de conexión")
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM auditoria_examenes ORDER BY fecha_emision DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        if conn: conn.close()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)