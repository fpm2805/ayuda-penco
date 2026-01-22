import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import pytz
import time

# --- CONFIGURACIÓN INICIAL COMPACTA ---
st.set_page_config(page_title="Ayuda Penco", layout="wide", page_icon="🇨🇱")
chile_time = pytz.timezone('America/Santiago')

# Estilos CSS para achicar espacios y letras gigantes
st.markdown("""
    <style>
        .block-container {padding-top: 3rem; padding-bottom: 0rem;}
        h1 {font-size: 1.5rem !important;}
        h3 {font-size: 1.2rem !important; margin-bottom: 0px;}
        .stAlert {padding: 0.5rem !important;}
        div[data-testid="stMetricValue"] {font-size: 1.2rem !important;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A BASE DE DATOS ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Error de conexión: Revisa el archivo secrets.toml. Detalle: {e}")
        st.stop()

supabase = init_connection()

# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    centro_actual = st.text_input("Centro de Acopio", value="Liceo Pencopolitano")
    # CAMBIO: Ahora dice Funcionario
    usuario_actual = st.text_input("Funcionario Responsable", value="Funcionario Turno 1")
    st.divider()
    st.caption(f"🕒 Hora Sistema: {datetime.now(chile_time).strftime('%H:%M')}")
    st.success("🟢 Conectado")

st.title("I. Municipalidad de Penco - Gestión de Ayudas")

# --- BUSCADOR COMPACTO ---
col_input, col_btn = st.columns([5, 1])
with col_input:
    rut_input_raw = st.text_input("Buscador", placeholder="Ingrese RUT aquí...", label_visibility="collapsed")
with col_btn:
    btn_buscar = st.button("BUSCAR", type="primary", use_container_width=True)

# Función de limpieza
def limpiar_rut(rut):
    return rut.replace(".", "").replace("-", "").strip().upper()

# --- LÓGICA PRINCIPAL ---
if rut_input_raw:
    rut_limpio = limpiar_rut(rut_input_raw)
    
    # 1. BUSCAR DATOS
    try:
        response = supabase.table("beneficiarios").select("*").eq("rut", rut_limpio).execute()
        datos_persona = response.data
    except Exception as e:
        st.error("Error de conexión.")
        st.stop()

    if len(datos_persona) > 0:
        p = datos_persona[0]
        
        # --- NUEVA VISTA COMPACTA DE DATOS ---
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.5, 3, 2, 1])
            c1.markdown(f"**RUT:** {p['rut']}")
            c2.markdown(f"**Nombre:** {p['nombre']}")
            c3.markdown(f"**Dirección:** {p['direccion']}")
            c4.markdown(f"**Fam:** {p['cant_familia']}")
            
            if not p['afectado']:
                st.warning("⚠️ RUT NO FIGURA EN LISTA FIBE/OFICIAL")

        # --- VALIDACIÓN CRUZADA DE DIRECCIÓN (NUEVO) ---
        # Buscamos quién más vive en esa dirección
        try:
            vecinos = supabase.table("beneficiarios").select("rut, nombre").eq("direccion", p['direccion']).execute()
            lista_ruts_casa = [v['rut'] for v in vecinos.data]
            
            # Buscamos entregas HOY para CUALQUIERA de esos ruts
            if lista_ruts_casa:
                entregas_casa = supabase.table("entregas").select("*").in_("rut_beneficiario", lista_ruts_casa).execute()
                df_casa = pd.DataFrame(entregas_casa.data)
                
                if not df_casa.empty:
                    df_casa['fecha_entrega'] = pd.to_datetime(df_casa['fecha_entrega']).dt.tz_convert(chile_time)
                    hoy = datetime.now(chile_time).date()
                    # Filtramos entregas de hoy en esa casa
                    entregas_hoy_casa = df_casa[df_casa['fecha_entrega'].dt.date == hoy]
                    
                    if not entregas_hoy_casa.empty:
                        # Alerta Roja: Alguien en esta casa ya recibió algo
                        st.error(f"🛑 ALERTA DE DIRECCIÓN: En '{p['direccion']}' ya se entregó ayuda HOY.")
                        st.dataframe(
                            entregas_hoy_casa[['rut_beneficiario', 'item', 'centro_acopio', 'fecha_entrega']],
                            hide_index=True,
                            column_config={
                                "rut_beneficiario": "RUT que retiró",
                                "fecha_entrega": st.column_config.DatetimeColumn("Hora", format="HH:mm")
                            }
                        )

        except Exception as e:
            pass # Si falla la validación cruzada, no bloqueamos el sistema

    else:
        # --- REGISTRO DE NUEVO (Formulario Compacto) ---
        st.warning(f"RUT {rut_limpio} no encontrado.")
        with st.form("form_nuevo"):
            st.markdown("**Registrar Nueva Ficha**")
            c1, c2 = st.columns(2)
            new_nombre = c1.text_input("Nombre")
            new_rut = c2.text_input("RUT", value=rut_limpio, disabled=True)
            c3, c4, c5 = st.columns([2, 2, 1])
            new_direccion = c3.text_input("Dirección")
            new_sector = c4.text_input("Sector")
            new_fam = c5.number_input("Familia", 1, 15, 1)
            
            if st.form_submit_button("💾 Guardar", type="primary"):
                if new_nombre and new_direccion:
                    datos = {
                        "rut": rut_limpio, "nombre": new_nombre, 
                        "direccion": new_direccion, "sector": new_sector,
                        "cant_familia": new_fam, "afectado": True,
                        "fecha_registro": datetime.now(chile_time).isoformat()
                    }
                    supabase.table("beneficiarios").insert(datos).execute()
                    st.rerun()

    # --- HISTORIAL Y ENTREGA ---
    if len(datos_persona) > 0:
        
        # Cargar historial
        historial = supabase.table("entregas").select("*").eq("rut_beneficiario", rut_limpio).order("fecha_entrega", desc=True).execute()
        df = pd.DataFrame(historial.data)

        st.markdown("---")
        c_historial, c_form = st.columns([3, 2]) # Dividimos pantalla: Izq Historial, Der Formulario

        with c_historial:
            st.write("📋 **Historial Personal**")
            if not df.empty:
                df['fecha_entrega'] = pd.to_datetime(df['fecha_entrega']).dt.tz_convert(chile_time)
                
                # Tabla profesional con fecha formateada y funcionario
                st.dataframe(
                    df[['fecha_entrega', 'item', 'cantidad', 'centro_acopio', 'usuario_responsable']],
                    use_container_width=True,
                    hide_index=True,
                    height=250,
                    column_config={
                        "fecha_entrega": st.column_config.DatetimeColumn("Fecha/Hora", format="DD-MM HH:mm"),
                        "item": "Ayuda",
                        "cantidad": st.column_config.NumberColumn("Cant", width="small"),
                        "centro_acopio": "Centro",
                        "usuario_responsable": "Funcionario"
                    }
                )
            else:
                st.info("Sin retiros anteriores.")

        with c_form:
            st.write("📦 **Entregar Ayuda**")
            with st.container(border=True):
                # Cargar items
                items_db = supabase.table("catalogo_ayuda").select("nombre_item").execute()
                lista = [i['nombre_item'] for i in items_db.data] + ["➕ OTRO..."]
                
                sel_item = st.selectbox("Item", lista, label_visibility="collapsed")
                nuevo_txt = ""
                if sel_item == "➕ OTRO...":
                    nuevo_txt = st.text_input("Nombre nuevo prod.")
                
                c_cant, c_btn = st.columns([1, 2])
                cant = c_cant.number_input("Cant", 1, 10, 1, label_visibility="collapsed")
                
                if c_btn.button("CONFIRMAR ENTREGA", type="primary", use_container_width=True):
                    final_item = nuevo_txt.strip().title() if sel_item.startswith("➕") else sel_item
                    
                    if sel_item.startswith("➕") and not final_item:
                        st.error("Escriba nombre.")
                    else:
                        if sel_item.startswith("➕"):
                            try: supabase.table("catalogo_ayuda").insert({"nombre_item": final_item}).execute()
                            except: pass

                        datos_entrega = {
                            "rut_beneficiario": rut_limpio,
                            "item": final_item,
                            "cantidad": cant,
                            "centro_acopio": centro_actual,
                            "usuario_responsable": usuario_actual, # Guarda el funcionario
                            "fecha_entrega": datetime.now(chile_time).isoformat()
                        }
                        supabase.table("entregas").insert(datos_entrega).execute()
                        st.toast(f"✅ Entregado: {final_item}")
                        time.sleep(1)
                        st.rerun()


# --- SECCIÓN DE ESTADÍSTICAS (SOLO ADMINISTRADORES) ---
st.markdown("---")
with st.expander("📊 Ver Estadísticas y Reportes (Solo Jefes)"):
    clave_admin = st.text_input("Ingrese clave de administrador", type="password")
    
    # Define aquí una clave sencilla, ej: "penco2026"
    if clave_admin == "penco2026": 
        st.success("Acceso concedido")
        
        # 1. Cargar TODOS los datos de entregas
        # OJO: Si son miles de datos, esto se puede optimizar después, 
        # pero para la emergencia funciona bien.
        datos_globales = supabase.table("entregas").select("*").execute()
        df_global = pd.DataFrame(datos_globales.data)
        
        if not df_global.empty:
            # Convertir fecha
            df_global['fecha_entrega'] = pd.to_datetime(df_global['fecha_entrega']).dt.tz_convert(chile_time)
            
            # A. TOTAL POR CENTRO DE ACOPIO
            st.subheader("📍 Entregas por Centro de Acopio")
            conteo_centros = df_global['centro_acopio'].value_counts()
            st.bar_chart(conteo_centros)
            
            # B. RANKING DE FAMILIAS CON MÁS AYUDA
            st.subheader("🏆 Familias con mayor cantidad de retiros")
            # Agrupamos por RUT y contamos cuántas veces aparece
            top_familias = df_global['rut_beneficiario'].value_counts().head(10)
            st.table(top_familias.rename("Cantidad de Retiros"))
            
            # C. TOTAL DE INSUMOS ENTREGADOS
            st.subheader("📦 Total de Insumos Entregados (Global)")
            total_items = df_global.groupby('item')['cantidad'].sum().sort_values(ascending=False)
            st.dataframe(total_items, use_container_width=True)
            
            # D. DESCARGAR REPORTE EXCEL
            # Convertir el DataFrame a CSV para descargar
            csv = df_global.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Descargar Reporte Completo (CSV)",
                data=csv,
                file_name="reporte_entregas_penco.csv",
                mime="text/csv"
            )
            
        else:
            st.info("Aún no hay datos de entregas para generar reportes.")
    elif clave_admin:
        st.error("Clave incorrecta")                     