
from __future__ import annotations
import numpy as np, pandas as pd
from typing import Dict, Tuple
from .core import ejecutar_modelo, Inputs

def dsa_univariado(modelo, ins: Inputs, variaciones: Dict[str, Tuple[float,float]])->pd.DataFrame:
    import copy
    base = ejecutar_modelo(modelo, ins)["AIP_total"]
    filas = []
    for campo,(vmin,vmax) in variaciones.items():
        ins_min = _apply_change(copy.deepcopy(ins), campo, vmin)
        ins_max = _apply_change(copy.deepcopy(ins), campo, vmax)
        aip_min = ejecutar_modelo(modelo, ins_min)["AIP_total"]
        aip_max = ejecutar_modelo(modelo, ins_max)["AIP_total"]
        filas.append({"Parámetro":campo,"Base":base,"AIP_min":aip_min,"AIP_max":aip_max,"Delta":abs(aip_max-aip_min)})
    return pd.DataFrame(filas).sort_values("Delta", ascending=True)

def _apply_change(ins: Inputs, campo: str, valor: float)->Inputs:
    parts = campo.split(":")
    if parts[0]=="estrategia":
        nombre = parts[1]; atributo = parts[2]
        for e in ins.estrategias:
            if e.nombre==nombre:
                setattr(e, atributo, float(valor)); break
    elif parts[0]=="inputs":
        atributo = parts[1]
        if atributo in ["saldo_inicial"]:
            setattr(ins, atributo, float(valor))
        elif atributo in ["presupuesto_anual","otros_gastos_anuales","cobertura_actual","cobertura_nuevo"]:
            idx = int(parts[2]); getattr(ins, atributo)[idx] = float(valor)
        else:
            raise ValueError("Atributo no soportado")
    else:
        raise ValueError("Campo no soportado")
    return ins

def psa_monte_carlo(modelo, ins: Inputs, nsims:int,
                    gamma_k_theta: Dict[str, tuple],
                    dirichlet_alpha_actual, dirichlet_alpha_nuevo,
                    lognorm_rr=None, aplicar_rr_en="costos")->pd.DataFrame:
    import copy
    estrategias = [e.nombre for e in ins.estrategias]
    T = ins.horizonte
    resultados = []
    for s in range(nsims):
        draw = copy.deepcopy(ins)
        # Gamma para costos
        for e in draw.estrategias:
            for key,(k,theta) in gamma_k_theta.items():
                etq, nombre, campo = key.split(":")
                if etq=="estrategia" and nombre==e.nombre:
                    val = np.random.gamma(shape=float(k), scale=float(theta))
                    setattr(e, campo, float(val))
        # Dirichlet para shares por año
        for t in range(T):
            alphasA = [dirichlet_alpha_actual[t][e] for e in estrategias]
            vecA = np.random.dirichlet(alpha=np.array(alphasA, dtype=float))
            for i,estr in enumerate(estrategias):
                draw.shares_actual[estr][t] = float(vecA[i])
            alphasN = [dirichlet_alpha_nuevo[t][e] for e in estrategias]
            vecN = np.random.dirichlet(alpha=np.array(alphasN, dtype=float))
            for i,estr in enumerate(estrategias):
                draw.shares_nuevo[estr][t] = float(vecN[i])
        # Lognormal RR
        if lognorm_rr:
            mu, sigma = lognorm_rr.get(aplicar_rr_en, (0.0,0.0))
            if sigma>0:
                rr = float(np.random.lognormal(mean=float(mu), sigma=float(sigma)))
                if aplicar_rr_en=="costos":
                    for e in draw.estrategias:
                        e.costo_ts *= rr
                        e.costo_procedimientos *= rr
                        e.costo_eventos *= rr
                elif aplicar_rr_en=="poblacion":
                    draw.poblacion_objetivo = [n*rr for n in draw.poblacion_objetivo]
        res = ejecutar_modelo(modelo, draw)
        resultados.append({"sim":s, "AIP_total": res["AIP_total"], "SPF_final": res["SPF_final"]})
    return pd.DataFrame(resultados)
