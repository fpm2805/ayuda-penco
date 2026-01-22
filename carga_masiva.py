import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import pytz

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Importador Masivo - Penco", page_icon="📤", layout="centered")
chile_time = pytz.timezone('America/Santiago')

# --- CONEXIÓN ---
try:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase = create_client(url, key)
except:
    st.error("No se encontraron las claves en .streamlit/secrets.toml")
    st.stop()

# --- SELECTOR DE MODO ---
st.title("📤 Central de Carga Masiva")
modo = st.radio("¿Qué tipo de datos deseas subir hoy?", 
                ["👥 1. Cargar Padrón de Personas (Damnificados)", 
                 "📦 2. Cargar Entregas Históricas (Ayudas pasadas)"])

st.markdown("---")

# ==========================================
# MODO 1: CARGA DE PERSONAS (BENEFICIARIOS)
# ==========================================
if modo == "👥 1. Cargar Padrón de Personas (Damnificados)":
    st.subheader("Carga de Base de Datos de Personas")
    st.info("ℹ️ Sube aquí las fichas FIBE o listados del Servel. Esto crea a las personas en el sistema.")
    
    archivo = st.file_uploader("Sube Excel o CSV de PERSONAS", type=["xlsx", "xls", "csv"], key="file_personas")
    
    if archivo:
        if archivo.name.endswith('csv'): df = pd.read_csv(archivo)
        else: df = pd.read_excel(archivo)
        
        st.write(f"Previsualización ({len(df)} registros):")
        st.dataframe(df.head(3))

        with st.form("form_personas"):
            c1, c2 = st.columns(2)
            c3, c4 = st.columns(2)
            c_rut = c1.selectbox("Columna RUT", df.columns)
            c_nom = c2.selectbox("Columna NOMBRE", df.columns)
            c_dir = c3.selectbox("Columna DIRECCIÓN", df.columns)
            c_fam = c4.selectbox("Columna GRUPO FAMILIAR", df.columns)
            c_sec = st.selectbox("Columna SECTOR (Opcional)", ["Ninguna"] + list(df.columns))
            
            if st.form_submit_button("🚀 SUBIR PERSONAS", type="primary"):
                progreso = st.progress(0)
                status = st.empty()
                exitos, errores = 0, 0
                
                for i, row in df.iterrows():
                    try:
                        rut_limpio = str(row[c_rut]).replace(".", "").replace("-", "").strip().upper()
                        try: fam = int(row[c_fam])
                        except: fam = 1
                        
                        datos = {
                            "rut": rut_limpio,
                            "nombre": str(row[c_nom]).strip(),
                            "direccion": str(row[c_dir]).strip(),
                            "cant_familia": fam,
                            "afectado": True
                        }
                        if c_sec != "Ninguna": datos["sector"] = str(row[c_sec])
                        
                        supabase.table("beneficiarios").upsert(datos).execute()
                        exitos += 1
                    except: errores += 1
                    if i % 10 == 0: progreso.progress((i + 1) / len(df))
                
                progreso.progress(100)
                st.success(f"✅ Personas cargadas: {exitos} | Errores: {errores}")

# ==========================================
# MODO 2: CARGA DE ENTREGAS (HISTORIAL)
# ==========================================
else:
    st.subheader("Carga de Entregas Históricas")
    st.warning("⚠️ IMPORTANTE: Los RUTs de este archivo YA DEBEN EXISTIR en la base de datos de personas. Si el sistema no conoce el RUT, la entrega fallará.")
    
    archivo_ent = st.file_uploader("Sube Excel o CSV de ENTREGAS", type=["xlsx", "xls", "csv"], key="file_entregas")
    
    if archivo_ent:
        if archivo_ent.name.endswith('csv'): df_ent = pd.read_csv(archivo_ent)
        else: df_ent = pd.read_excel(archivo_ent)
        
        st.write(f"Previsualización ({len(df_ent)} entregas):")
        st.dataframe(df_ent.head(3))
        
        with st.form("form_entregas"):
            col1, col2, col3 = st.columns(3)
            c_rut_ent = col1.selectbox("Columna RUT Beneficiario", df_ent.columns)
            c_item_ent = col2.selectbox("Columna QUE SE ENTREGÓ (Item)", df_ent.columns)
            c_cant_ent = col3.selectbox("Columna CANTIDAD", df_ent.columns)
            
            col4, col5 = st.columns(2)
            # Opcion para poner fecha manual o desde columna
            usar_fecha_col = st.checkbox("El Excel trae la fecha", value=True)
            if usar_fecha_col:
                c_fecha_ent = col4.selectbox("Columna FECHA", df_ent.columns)
            else:
                fecha_fija = col4.date_input("Si no hay fecha, usar esta para todos:")
            
            # Centro de acopio puede venir en el excel o ser fijo para toda la carga
            usar_centro_col = st.checkbox("El Excel trae el Centro de Acopio", value=False)
            if usar_centro_col:
                c_centro_ent = col5.selectbox("Columna CENTRO", df_ent.columns)
            else:
                centro_fijo = col5.text_input("Si no trae centro, poner a todos:", "Carga Histórica Municipal")

            st.markdown("**Nota:** El 'Funcionario' quedará registrado como 'Administrador (Carga Masiva)'")
            
            if st.form_submit_button("🚀 SUBIR HISTORIAL DE ENTREGAS", type="primary"):
                progreso = st.progress(0)
                exitos, errores, ruts_no_encontrados = 0, 0, 0
                
                for i, row in df_ent.iterrows():
                    try:
                        rut_limpio = str(row[c_rut_ent]).replace(".", "").replace("-", "").strip().upper()
                        
                        # 1. Resolver Fecha
                        if usar_fecha_col:
                            fecha_str = str(row[c_fecha_ent])
                            # Intentamos convertir fecha excel a formato ISO
                            try:
                                fecha_obj = pd.to_datetime(fecha_str)
                                fecha_final = fecha_obj.isoformat()
                            except:
                                fecha_final = datetime.now().isoformat() # Fallback
                        else:
                            fecha_final = datetime.combine(fecha_fija, datetime.min.time()).isoformat()

                        # 2. Resolver Centro
                        if usar_centro_col:
                            centro_final = str(row[c_centro_ent])
                        else:
                            centro_final = centro_fijo

                        datos_entrega = {
                            "rut_beneficiario": rut_limpio,
                            "item": str(row[c_item_ent]),
                            "cantidad": int(row[c_cant_ent]),
                            "centro_acopio": centro_final,
                            "fecha_entrega": fecha_final,
                            "usuario_responsable": "Admin (Carga Masiva)"
                        }
                        
                        supabase.table("entregas").insert(datos_entrega).execute()
                        exitos += 1
                        
                    except Exception as e:
                        # Si el error es de llave foránea (RUT no existe)
                        if "foreign key constraint" in str(e).lower() or "violates foreign key" in str(e).lower():
                            ruts_no_encontrados += 1
                        else:
                            errores += 1
                            print(e)
                    
                    if i % 10 == 0: progreso.progress((i + 1) / len(df_ent))
                
                progreso.progress(100)
                st.success(f"✅ Proceso terminado: {exitos} entregas subidas.")
                if ruts_no_encontrados > 0:
                    st.error(f"❌ {ruts_no_encontrados} entregas fallaron porque el RUT no estaba registrado en Personas.")
                if errores > 0:
                    st.warning(f"⚠️ {errores} fallaron por otros errores de formato.")