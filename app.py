
import streamlit as st, pandas as pd, numpy as np, plotly.express as px
from aip.core import Inputs, Strategy, Cohorte, ejecutar_modelo
from aip.sensitivity import dsa_univariado, psa_monte_carlo
from aip.report import export_docx, export_pdf

st.set_page_config(page_title="AIP-MINSA v2.1", page_icon="💸", layout="wide")
st.title("AIP – Metodología MINSA (v2.1: formularios + PSA + subgrupos)")

# Estado de sesión
if "estrategias" not in st.session_state:
    st.session_state.estrategias = [Strategy("Comparador", 0.0, 0.0, 0.0), Strategy("Intervención", 0.0, 0.0, 0.0)]
if "cohortes" not in st.session_state:
    st.session_state.cohortes = [Cohorte("General", 1.0)]
if "shares_actual" not in st.session_state or "shares_nuevo" not in st.session_state:
    st.session_state.shares_actual = {}
    st.session_state.shares_nuevo = {}
if "tabla" not in st.session_state:
    st.session_state.tabla = None
if "fig_paths" not in st.session_state:
    st.session_state.fig_paths = {}

# ---- Ejemplo precargado (Modelo 2, 3 estrategias, 2 cohortes) ----
st.sidebar.divider()
if st.sidebar.button("📦 Cargar ejemplo (coexistencia, 3 estrategias, 2 cohortes)"):
    st.session_state["cohortes"] = [
        Cohorte("Adultos (18-64)", 0.7),
        Cohorte("Adultos mayores (65+)", 0.3)
    ]
    st.session_state["estrategias"] = [
        Strategy("Comparador A", 850.0, 120.0, 30.0, {"Adultos (18-64)": 1.0, "Adultos mayores (65+)": 1.15}),
        Strategy("Comparador B", 900.0, 130.0, 35.0, {"Adultos (18-64)": 1.0, "Adultos mayores (65+)": 1.1}),
        Strategy("Intervención", 1100.0, 140.0, 40.0, {"Adultos (18-64)": 1.0, "Adultos mayores (65+)": 1.05}),
    ]
    # Horizonte 5, población y coberturas
    for k,v in {"N_1":5000.0,"N_2":5200.0,"N_3":5400.0,"N_4":5600.0,"N_5":5800.0}.items(): st.session_state[k]=v
    for k in ["covA_","covN_"]:
        for t in range(1,6): st.session_state[f"{k}{t}"]=1.0
    for t in range(1,6):
        st.session_state[f"pres_{t}"]=0.0
        st.session_state[f"gasto_{t}"]=0.0
    st.session_state["modelo_idx"]=1  # Modelo 2
    # Shares por año (suman 1): desplazamiento gradual a Intervención
    for t in range(5):
        st.session_state[f"A_{t}_Comparador A"]=max(0.0, 0.6 - 0.1*t)
        st.session_state[f"A_{t}_Comparador B"]=0.3
        st.session_state[f"A_{t}_Intervención"]=min(1.0, 0.1 + 0.1*t)
        st.session_state[f"N_{t}_Comparador A"]=max(0.0, 0.3 - 0.05*t)
        st.session_state[f"N_{t}_Comparador B"]=max(0.0, 0.2 - 0.02*t)
        st.session_state[f"N_{t}_Intervención"]=min(1.0, 0.5 + 0.07*t)
    st.success("Ejemplo cargado. Revisa cada sección y pulsa 'Calcular AIP'.")
# ---- fin ejemplo ----

with st.sidebar:
    st.header("Parámetros generales")
    nombre_caso = st.text_input("Nombre del caso", value="Caso AIP v2.1")
    horizonte = st.slider("Horizonte (años)", 1, 5, 5)
    N_t = []
    st.markdown("**Población objetivo (N_t)**")
    for t in range(horizonte):
        key=f"N_{t+1}"
        N_t.append(st.number_input(f"N_{t+1}", min_value=0.0, value=float(st.session_state.get(key,0.0)), step=100.0, key=key))
    st.markdown("**Cobertura** (fracción atendida)")
    cobertura_actual = []
    cobertura_nuevo = []
    for t in range(horizonte):
        keyA=f"covA_{t+1}"; keyN=f"covN_{t+1}"
        cobertura_actual.append(st.number_input(f"Cobertura actual año {t+1}", min_value=0.0, max_value=1.0, value=float(st.session_state.get(keyA,1.0)), step=0.05, key=keyA))
        cobertura_nuevo.append(st.number_input(f"Cobertura nuevo año {t+1}", min_value=0.0, max_value=1.0, value=float(st.session_state.get(keyN,1.0)), step=0.05, key=keyN))
    st.markdown("**Presupuesto**")
    saldo0 = st.number_input("Saldo inicial", value=0.0, step=1000.0)
    presu = []; otros = []
    for t in range(horizonte):
        pres_key=f"pres_{t+1}"; gas_key=f"gasto_{t+1}"
        presu.append(st.number_input(f"Ingreso presupuestal año {t+1}", value=float(st.session_state.get(pres_key,0.0)), step=1000.0, key=pres_key))
        otros.append(st.number_input(f"Otros gastos año {t+1}", value=float(st.session_state.get(gas_key,0.0)), step=1000.0, key=gas_key))
    modelo = st.selectbox("Modelo", ["Modelo 1","Modelo 2","Modelo 3","Modelo 4"], index=int(st.session_state.get("modelo_idx",1)), key="modelo_idx")

st.subheader("1) Cohortes / Subgrupos (pesos)")
n_coh = st.number_input("Número de cohortes", min_value=1, max_value=10, value=len(st.session_state.cohortes), step=1)
cohortes = []
for i in range(n_coh):
    c1, c2 = st.columns([2,1])
    nombre = c1.text_input(f"Nombre cohorte {i+1}", value=st.session_state.cohortes[i].nombre if i<len(st.session_state.cohortes) else f"Cohorte {i+1}", key=f"coh_nom_{i}")
    peso   = c2.number_input(f"Peso cohorte {i+1}", min_value=0.0, max_value=1.0, value=st.session_state.cohortes[i].peso if i<len(st.session_state.cohortes) else 0.0, step=0.05, key=f"coh_peso_{i}")
    cohortes.append(Cohorte(nombre, float(peso)))
st.session_state.cohortes = cohortes
st.caption("La suma de pesos debe ser 1.0")

st.subheader("2) Estrategias (comparadores, intervención, secuencias)")
n_est = st.number_input("Número de estrategias", min_value=2, max_value=8, value=len(st.session_state.estrategias), step=1)
estrategias = []
for i in range(n_est):
    with st.expander(f"Estrategia {i+1}"):
        default = st.session_state.estrategias[i] if i<len(st.session_state.estrategias) else None
        nombre = st.text_input("Nombre", value=(default.nombre if default else f"Estrategia {i+1}"), key=f"est_nom_{i}")
        costo_ts = st.number_input("Costo TS por paciente/año", value=(default.costo_ts if default else 0.0), step=100.0, key=f"est_cts_{i}")
        costo_proc = st.number_input("Costo procedimientos por paciente/año", value=(default.costo_procedimientos if default else 0.0), step=50.0, key=f"est_cpr_{i}")
        costo_ea = st.number_input("Costo eventos adversos por paciente/año", value=(default.costo_eventos if default else 0.0), step=50.0, key=f"est_cea_{i}")
        mult = {}
        st.markdown("**Multiplicadores de costo por cohorte (opcional)**")
        for coh in cohortes:
            mult[coh.nombre] = st.number_input(f"× {coh.nombre}", value=1.0, min_value=0.0, step=0.05, key=f"mult_{i}_{coh.nombre}")
        estrategias.append(Strategy(nombre, float(costo_ts), float(costo_proc), float(costo_ea), mult))
st.session_state.estrategias = estrategias

st.subheader("3) Participaciones de mercado por año")
shares_actual = {e.nombre:[0.0]*len(N_t) for e in estrategias}
shares_nuevo  = {e.nombre:[0.0]*len(N_t) for e in estrategias}
for t in range(len(N_t)):
    st.markdown(f"**Año {t+1}**")
    cols = st.columns(len(estrategias))
    sumaA = 0.0; sumaN = 0.0
    for i,e in enumerate(estrategias):
        with cols[i]:
            keyA=f"A_{t}_{e.nombre}"; keyN=f"N_{t}_{e.nombre}"
            shares_actual[e.nombre][t] = st.number_input(f"{e.nombre} (actual)", min_value=0.0, max_value=1.0, value=float(st.session_state.get(keyA,0.0)), step=0.05, key=keyA)
            shares_nuevo[e.nombre][t]  = st.number_input(f"{e.nombre} (nuevo)",  min_value=0.0, max_value=1.0, value=float(st.session_state.get(keyN,0.0)), step=0.05, key=keyN)
            sumaA += shares_actual[e.nombre][t]
            sumaN += shares_nuevo[e.nombre][t]
    st.caption(f"Suma actual={sumaA:.2f} | Suma nuevo={sumaN:.2f} (deben ser 1.00)")

st.session_state.shares_actual = shares_actual
st.session_state.shares_nuevo = shares_nuevo

st.subheader("4) Ejecutar modelo")
if st.button("Calcular AIP"):
    ins = Inputs(
        nombre_caso=nombre_caso,
        horizonte=len(N_t),
        poblacion_objetivo=N_t,
        cohortes=cohortes,
        estrategias=estrategias,
        shares_actual=shares_actual,
        shares_nuevo=shares_nuevo,
        cobertura_actual=cobertura_actual,
        cobertura_nuevo=cobertura_nuevo,
        saldo_inicial=saldo0,
        presupuesto_anual=presu,
        otros_gastos_anuales=otros
    )
    try:
        res = ejecutar_modelo(modelo, ins)
        st.session_state.tabla = res["tabla"]
        st.success(f"AIP acumulado: S/ {res['AIP_total']:.0f} | SPF final: S/ {res['SPF_final']:.0f}")
        st.dataframe(res["tabla"], use_container_width=True)
        df = res["tabla"]
        fig1 = px.line(df, x="Año", y=["Costo agregado (Actual)","Costo agregado (Nuevo)"], title="Costos agregados por escenario", markers=True)
        st.plotly_chart(fig1, use_container_width=True)
        fig2 = px.bar(df, x="Año", y="Impacto Incremental (AIP)", title="Impacto Presupuestal Incremental")
        st.plotly_chart(fig2, use_container_width=True)
        fig3 = px.line(df, x="Año", y="SPF", title="Saldo Presupuestal Final (SPF)", markers=True)
        st.plotly_chart(fig3, use_container_width=True)
        # Guardar imágenes
        import os
        os.makedirs("reports", exist_ok=True)
        fig_paths = {}
        for name,fig in {"Costos":fig1,"AIP":fig2,"SPF":fig3}.items():
            p = f"reports/{name}.png"
            fig.write_image(p, format="png")
            fig_paths[name]=p
        st.session_state.fig_paths = fig_paths
    except Exception as e:
        st.error(str(e))

st.subheader("5) Sensibilidad determinística (DSA)")
with st.expander("Configurar y ejecutar"):
    variaciones = {}
    for e in estrategias:
        vmin = st.number_input(f"{e.nombre}: costo_ts min", value=0.9*e.costo_ts if e.costo_ts>0 else 0.0, step=10.0, key=f"dsa_min_{e.nombre}")
        vmax = st.number_input(f"{e.nombre}: costo_ts max", value=1.1*e.costo_ts if e.costo_ts>0 else 0.0, step=10.0, key=f"dsa_max_{e.nombre}")
        variaciones[f"estrategia:{e.nombre}:costo_ts"] = (float(vmin), float(vmax))
    if st.button("Ejecutar DSA"):
        ins = Inputs(
            nombre_caso=nombre_caso,
            horizonte=len(N_t),
            poblacion_objetivo=N_t,
            cohortes=cohortes,
            estrategias=estrategias,
            shares_actual=shares_actual,
            shares_nuevo=shares_nuevo,
            cobertura_actual=cobertura_actual,
            cobertura_nuevo=cobertura_nuevo,
            saldo_inicial=saldo0,
            presupuesto_anual=presu,
            otros_gastos_anuales=otros
        )
        df_dsa = dsa_univariado(modelo, ins, variaciones)
        st.dataframe(df_dsa, use_container_width=True)
        figt = px.bar(df_dsa, x="Delta", y="Parámetro", orientation="h", title="Diagrama Tornado (AIP total)")
        st.plotly_chart(figt, use_container_width=True)

st.subheader("6) Sensibilidad probabilística (PSA)")
with st.expander("Configurar y ejecutar PSA"):
    nsims = st.number_input("Número de simulaciones", min_value=100, max_value=20000, value=2000, step=100)
    st.markdown("**Gamma (k, θ) para costos por paciente**")
    gamma_params = {}
    for e in estrategias:
        k = st.number_input(f"{e.nombre} k", value=50.0, step=1.0, key=f"gk_{e.nombre}")
        th_cts = st.number_input(f"{e.nombre} θ costo_ts", value=(e.costo_ts/50.0 if e.costo_ts>0 else 1.0), step=1.0, key=f"gth_cts_{e.nombre}")
        th_cpr = st.number_input(f"{e.nombre} θ costo_proc", value=(e.costo_procedimientos/50.0 if e.costo_procedimientos>0 else 1.0), step=1.0, key=f"gth_cpr_{e.nombre}")
        th_cea = st.number_input(f"{e.nombre} θ costo_EA", value=(e.costo_eventos/50.0 if e.costo_eventos>0 else 1.0), step=1.0, key=f"gth_cea_{e.nombre}")
        gamma_params[f"estrategia:{e.nombre}:costo_ts"] = (float(k), float(th_cts))
        gamma_params[f"estrategia:{e.nombre}:costo_procedimientos"] = (float(k), float(th_cpr))
        gamma_params[f"estrategia:{e.nombre}:costo_eventos"] = (float(k), float(th_cea))
    st.markdown("**Dirichlet (α) por año y escenario para shares**")
    dirA = []; dirN = []
    for t in range(len(N_t)):
        with st.expander(f"Alphas año {t+1}"):
            rowA = {}; rowN = {}
            for e in estrategias:
                rowA[e.nombre] = st.number_input(f"α Actual {e.nombre} año {t+1}", value=10.0, step=1.0, key=f"alphaA_{t}_{e.nombre}")
                rowN[e.nombre] = st.number_input(f"α Nuevo {e.nombre} año {t+1}", value=10.0, step=1.0, key=f"alphaN_{t}_{e.nombre}")
            dirA.append(rowA); dirN.append(rowN)
    use_rr = st.checkbox("Incluir RR lognormal (aplicar sobre costos o población)")
    rr_target = st.selectbox("Aplicar RR a:", ["costos","poblacion"]) if use_rr else "costos"
    mu = st.number_input("mu (log)", value=0.0) if use_rr else 0.0
    sigma = st.number_input("sigma (log)", value=0.1) if use_rr else 0.0
    if st.button("Ejecutar PSA"):
        ins = Inputs(
            nombre_caso=nombre_caso,
            horizonte=len(N_t),
            poblacion_objetivo=N_t,
            cohortes=cohortes,
            estrategias=estrategias,
            shares_actual=shares_actual,
            shares_nuevo=shares_nuevo,
            cobertura_actual=cobertura_actual,
            cobertura_nuevo=cobertura_nuevo,
            saldo_inicial=saldo0,
            presupuesto_anual=presu,
            otros_gastos_anuales=otros
        )
        df_psa = psa_monte_carlo(modelo, ins, int(nsims), gamma_params, dirA, dirN,
                                 lognorm_rr={"costos":(mu,sigma),"poblacion":(mu,sigma)} if use_rr else None,
                                 aplicar_rr_en=rr_target)
        desc = df_psa.describe(percentiles=[0.025,0.5,0.975]).T
        st.dataframe(desc, use_container_width=True)
        figh = px.histogram(df_psa, x="AIP_total", nbins=50, title="Distribución AIP_total (PSA)", histnorm="probability")
        st.plotly_chart(figh, use_container_width=True)
        q = df_psa["AIP_total"].quantile([0.025,0.5,0.975]).to_frame().T
        st.write("Percentiles AIP_total (P2.5, P50, P97.5)")
        st.dataframe(q, use_container_width=True)

st.subheader("7) Exportar informe (DOCX/PDF)")
titulo = st.text_input("Título del informe", value="Informe AIP – Metodología MINSA")
resumen = st.text_area("Resumen ejecutivo", value="Resumen breve del caso, supuestos, horizonte, resultados y conclusiones.")
colA, colB = st.columns(2)
with colA:
    if st.button("Exportar DOCX"):
        if st.session_state.tabla is None: st.error("Ejecuta el modelo primero.")
        else:
            meta = {"titulo":titulo, "resumen":resumen}
            df = st.session_state.tabla
            meta["AIP_total"] = f"S/ {float(df['Impacto Incremental (AIP)'].sum()):,.0f}"
            meta["SPF_final"] = f"S/ {float(df['SPF'].iloc[-1]):,.0f}"
            fp = "reports/informe_aip.docx"
            export_docx(fp, meta, df, st.session_state.fig_paths)
            with open(fp, "rb") as f:
                st.download_button("Descargar DOCX", f, file_name="informe_aip.docx")
with colB:
    if st.button("Exportar PDF (simple)"):
        if st.session_state.tabla is None: st.error("Ejecuta el modelo primero.")
        else:
            meta = {"titulo":titulo, "resumen":resumen}
            df = st.session_state.tabla
            meta["AIP_total"] = f"S/ {float(df['Impacto Incremental (AIP)'].sum()):,.0f}"
            meta["SPF_final"] = f"S/ {float(df['SPF'].iloc[-1]):,.0f}"
            fp = "reports/informe_aip.pdf"
            export_pdf(fp, meta)
            with open(fp, "rb") as f:
                st.download_button("Descargar PDF", f, file_name="informe_aip.pdf")
