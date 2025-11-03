from aip.core import Inputs, Strategy, Cohorte, ejecutar_modelo
def test_end2end_min():
    ins = Inputs(
        nombre_caso="t",
        horizonte=2,
        poblacion_objetivo=[100,100],
        cohortes=[Cohorte("General",1.0)],
        estrategias=[Strategy("Comp",800,100,0), Strategy("Interv",1000,100,0)],
        shares_actual={"Comp":[1.0,1.0],"Interv":[0.0,0.0]},
        shares_nuevo={"Comp":[0.0,0.0],"Interv":[1.0,1.0]},
        cobertura_actual=[1.0,1.0],
        cobertura_nuevo=[1.0,1.0],
        saldo_inicial=0.0,
        presupuesto_anual=[0.0,0.0],
        otros_gastos_anuales=[0.0,0.0]
    )
    res = ejecutar_modelo("Modelo 1", ins)
    assert res["tabla"]["Costo agregado (Actual)"][0] == 900*100
    assert res["tabla"]["Costo agregado (Nuevo)"][0] == 1100*100
