
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Literal, Optional
import numpy as np
import pandas as pd

ModelType = Literal["Modelo 1","Modelo 2","Modelo 3","Modelo 4"]

@dataclass
class Strategy:
    nombre: str
    costo_ts: float
    costo_procedimientos: float = 0.0
    costo_eventos: float = 0.0
    multiplicador_cohortes: Optional[Dict[str,float]] = None

    def costo_paciente_base(self) -> float:
        return float(self.costo_ts + self.costo_procedimientos + self.costo_eventos)

    def costo_paciente_para_cohorte(self, cohorte:str) -> float:
        base = self.costo_paciente_base()
        if self.multiplicador_cohortes and cohorte in self.multiplicador_cohortes:
            return base * float(self.multiplicador_cohortes[cohorte])
        return base

@dataclass
class Cohorte:
    nombre: str
    peso: float  # suma = 1.0

@dataclass
class Inputs:
    nombre_caso: str
    horizonte: int
    poblacion_objetivo: List[float]
    cohortes: List[Cohorte]
    estrategias: List[Strategy]
    shares_actual: Dict[str, List[float]]
    shares_nuevo: Dict[str, List[float]]
    cobertura_actual: List[float]
    cobertura_nuevo: List[float]
    saldo_inicial: float
    presupuesto_anual: List[float]
    otros_gastos_anuales: List[float]

    def validate(self)->None:
        T = self.horizonte
        assert len(self.poblacion_objetivo)==T
        assert len(self.cobertura_actual)==T and len(self.cobertura_nuevo)==T
        assert len(self.presupuesto_anual)==T and len(self.otros_gastos_anuales)==T
        for year in range(T):
            sA = sum(self.shares_actual[e][year] for e in self.shares_actual)
            sN = sum(self.shares_nuevo[e][year] for e in self.shares_nuevo)
            if not np.isclose(sA,1.0, atol=1e-3): raise ValueError(f"shares_actual no suman 1 en año {year+1}")
            if not np.isclose(sN,1.0, atol=1e-3): raise ValueError(f"shares_nuevo no suman 1 en año {year+1}")
        sw = sum(c.peso for c in self.cohortes)
        if not np.isclose(sw,1.0, atol=1e-6): raise ValueError("La suma de pesos de cohortes debe ser 1.0")

def _costo_promedio_por_escenario(ins: Inputs, shares: Dict[str,List[float]], cobertura: List[float]) -> np.ndarray:
    T = ins.horizonte
    estrategias_map = {e.nombre: e for e in ins.estrategias}
    vals = []
    for t in range(T):
        total = 0.0
        for coh in ins.cohortes:
            costo_coh = 0.0
            for estr, sh in shares.items():
                e = estrategias_map[estr]
                costo_coh += sh[t] * e.costo_paciente_para_cohorte(coh.nombre)
            total += coh.peso * costo_coh
        vals.append(total * cobertura[t])
    return np.array(vals)

def costos_agregados(modelo: ModelType, ins: Inputs):
    ins.validate()
    N = np.array(ins.poblacion_objetivo, dtype=float)
    costo_pp_actual = _costo_promedio_por_escenario(ins, ins.shares_actual, ins.cobertura_actual)
    costo_pp_nuevo  = _costo_promedio_por_escenario(ins, ins.shares_nuevo,  ins.cobertura_nuevo)
    CA = (costo_pp_actual * N).tolist()
    CN = (costo_pp_nuevo  * N).tolist()
    return CA, CN, costo_pp_actual, costo_pp_nuevo

def ejecutar_modelo(modelo: ModelType, ins: Inputs):
    CA, CN, cpa, cpn = costos_agregados(modelo, ins)
    AIP = (np.array(CN) - np.array(CA)).tolist()
    SPF = []
    sp = float(ins.saldo_inicial)
    for t in range(ins.horizonte):
        sp = sp + ins.presupuesto_anual[t] - ins.otros_gastos_anuales[t] - CN[t]
        SPF.append(sp)
    df = pd.DataFrame({
        "Año": np.arange(1, ins.horizonte+1),
        "N_t": ins.poblacion_objetivo,
        "Cobertura_actual": ins.cobertura_actual,
        "Cobertura_nuevo": ins.cobertura_nuevo,
        "Costo pp (Actual)": cpa,
        "Costo pp (Nuevo)": cpn,
        "Costo agregado (Actual)": CA,
        "Costo agregado (Nuevo)": CN,
        "Impacto Incremental (AIP)": AIP,
        "SPF": SPF
    })
    return {"tabla": df, "AIP_total": float(np.sum(AIP)), "SPF_final": float(SPF[-1])}
