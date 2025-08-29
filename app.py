
import streamlit as st, pandas as pd, numpy as np, matplotlib.pyplot as plt
st.set_page_config(page_title="Qrauts – Portfolio Finanzmodell", layout="wide")
st.title("Qrauts – Finanzmodell (Sensitivitäten)")

@st.cache_data
def load_data():
    return pd.read_csv("portfolio_data.csv")
df = load_data()

st.sidebar.header("Annahmen")
yield_kwh_kwp = st.sidebar.number_input("Spez. Ertrag (kWh/kWp·a)", 700.0, 1200.0, 930.0, 10.0)
sc = st.sidebar.slider("Self-Consumption-Quote", 0.0, 0.95, 0.55, 0.01)
p_mieter = st.sidebar.number_input("Mieterstrompreis (€/kWh)", 0.10, 0.60, 0.28, 0.01)
p_grid = st.sidebar.number_input("Einspeisepreis (€/kWh)", 0.00, 0.30, 0.08, 0.01)
fee_ab = st.sidebar.number_input("Abrechnungsfee (€/kWh)", 0.00, 0.10, 0.02, 0.005)
capex_kwp = st.sidebar.number_input("CAPEX (€/kWp)", 400.0, 2000.0, 1000.0, 10.0)
opex_kwp = st.sidebar.number_input("OPEX (€/kWp·a)", 0.0, 80.0, 20.0, 1.0)
pacht_kwp = st.sidebar.number_input("Dachpacht (€/kWp·a)", 0.0, 50.0, 10.0, 1.0)
degr = st.sidebar.slider("Degradation (%/a)", 0.0, 2.0, 0.5, 0.1)/100.0
infl = st.sidebar.slider("Inflation (%/a)", 0.0, 5.0, 2.0, 0.1)/100.0
years = st.sidebar.number_input("Analysejahre", 5, 30, 20, 1)
eq = st.sidebar.slider("Equity-Quote", 0.0, 1.0, 0.30, 0.05)
i_debt = st.sidebar.number_input("FK-Zins (p.a.)", 0.00, 0.15, 0.05, 0.005)
n_debt = st.sidebar.number_input("FK-Laufzeit (Jahre)", 1, 25, 15, 1)

objects = st.multiselect("Objekte auswählen (leer = alle)", df["Objekt"].tolist())
dff = df[df["Objekt"].isin(objects)].copy() if objects else df.copy()

dff["kWp"] = dff["Vorschlag_kWp"].fillna(0)
dff["gen_y1"] = dff["kWp"] * yield_kwh_kwp
dff["sc_kWh"] = np.minimum(dff["gen_y1"] * sc, dff["Verbrauch_kWh"])
dff["exp_kWh"] = dff["gen_y1"] - dff["sc_kWh"]
dff["rev_mieter"] = dff["sc_kWh"] * p_mieter
dff["rev_grid"] = dff["exp_kWh"] * p_grid
dff["opex"] = dff["kWp"] * opex_kwp
dff["pacht"] = dff["kWp"] * pacht_kwp
dff["fee"] = dff["sc_kWh"] * fee_ab
dff["ebitda"] = dff["rev_mieter"] + dff["rev_grid"] - dff["opex"] - dff["pacht"] - dff["fee"]

st.subheader("Portfolio – Year 1 (Base-Case)")
st.dataframe(dff[["Objekt","kWp","Verbrauch_kWh","gen_y1","sc_kWh","exp_kWh","rev_mieter","rev_grid","opex","pacht","fee","ebitda"]])

fig = plt.figure(figsize=(8,5))
plt.bar(["SC_kWh","Export_KWh"], [dff["sc_kWh"].sum()/1000.0, dff["exp_kWh"].sum()/1000.0])
plt.ylabel("MWh/a")
plt.title("Eigenverbrauch vs. Einspeisung – Portfolio (Y1)")
st.pyplot(fig)

kWp_total = dff["kWp"].sum()
cons_total = dff["Verbrauch_kWh"].sum()
capex = kWp_total * capex_kwp

def annuity(P, i, n):
    if n <= 0: return 0.0
    if i == 0: return P / n
    return P * (i*(1+i)**n)/((1+i)**n - 1)

debt = capex * (1-eq)
equity = capex * eq
debt_service = annuity(debt, i_debt, int(n_debt))

years_list = list(range(0, int(years)+1))
cf_equity, cfads, debt_serv_list, ebitda_list = [], [], [], []
for y in years_list:
    if y == 0:
        cf_equity.append(-equity); cfads.append(0.0); debt_serv_list.append(0.0); ebitda_list.append(0.0)
    else:
        gen = kWp_total * yield_kwh_kwp * ((1-degr)**(y-1))
        sc_k = min(cons_total, gen*sc)
        exp_k = gen - sc_k
        rev = sc_k * (p_mieter*((1+infl)**(y-1))) + exp_k * (p_grid*((1+infl)**(y-1)))
        opex_y = kWp_total * opex_kwp * ((1+infl)**(y-1))
        pacht_y = kWp_total * pacht_kwp * ((1+infl)**(y-1))
        fee_y = sc_k * (fee_ab*((1+infl)**(y-1)))
        ebitda = rev - opex_y - pacht_y - fee_y
        ds = debt_service if y <= n_debt else 0.0
        cf = ebitda  # Steuern = 0%
        cf_equity.append(cf - ds); cfads.append(cf); debt_serv_list.append(ds); ebitda_list.append(ebitda)

def irr(cashflows, guess=0.1, tol=1e-6, maxiter=100):
    rate = guess
    for _ in range(maxiter):
        npv = 0.0; d = 0.0
        for t, c in enumerate(cashflows):
            npv += c / ((1+rate)**t)
            if t > 0: d += -t * c / ((1+rate)**(t+1))
        if abs(npv) < tol: return rate
        rate -= npv/d if d != 0 else 0.0
    return float("nan")

irr_equity = irr(cf_equity)
irr_unlev = irr([-capex] + ebitda_list[1:])
dscr_vals = [cfads[y] / debt_serv_list[y] if debt_serv_list[y] > 0 else float("nan") for y in range(len(years_list))]
dscr_min = np.nanmin(dscr_vals[1:]) if np.any(~np.isnan(dscr_vals[1:])) else float("nan")
dscr_avg = np.nanmean([v for v in dscr_vals[1:] if not np.isnan(v)]) if np.any(~np.isnan(dscr_vals[1:])) else float("nan")

st.subheader("KPIs – Portfolio")
st.write(f"**CAPEX:** {capex:,.0f} €".format(capex=capex))
st.write(f"**Unlevered IRR:** {irr:.2%}".format(irr=irr_unlev) if not np.isnan(irr_unlev) else "Unlevered IRR: n/a")
st.write(f"**Equity IRR:** {irr:.2%}".format(irr=irr_equity) if not np.isnan(irr_equity) else "Equity IRR: n/a")
st.write(f"**DSCR (min / Ø):** {a:.2f} / {b:.2f}".format(a=dscr_min, b=dscr_avg) if not np.isnan(dscr_min) else "DSCR: n/a")

res = pd.DataFrame({
    "Year": years_list,
    "EBITDA": ebitda_list,
    "DebtService": debt_serv_list,
    "CFADS": cfads,
    "EquityCF": cf_equity,
    "DSCR": dscr_vals
})
st.download_button("Cashflows (CSV)", res.to_csv(index=False).encode("utf-8"), "cashflows_portfolio.csv", "text/csv")

st.caption("Hinweis: Vereinfachtes Modell ohne Steuern; Parameter in der Sidebar anpassbar.")
