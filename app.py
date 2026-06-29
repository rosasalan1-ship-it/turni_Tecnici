import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
 
# =========================
# CONFIG
# =========================
TECHS = ["Tiziana", "Rosario", "Ragusa", "Cunsolo"]
DAYS = 30
WORK_SHIFTS = ["M", "P", "N"]
REP_SHIFTS = ["REPN", "REPD"]
ALL_SHIFTS = WORK_SHIFTS + REP_SHIFTS
 
MAX_REP_MONTH = 7          # REP totali (REPN+REPD) al mese, per tutti
TIZIANA_MAX_NOTTI = 6      # N + REPN per Tiziana
 
st.set_page_config(page_title="Gestione Turni", layout="wide")
st.title("📅 Pianificazione Turni - Tecnici")
 
# CSS globale: bordi su tutte le tabelle/data_editor dell'app
st.markdown(
    """
    <style>
    div[data-testid="stDataFrame"] table,
    div[data-testid="stDataFrame"] th,
    div[data-testid="stDataFrame"] td,
    div[data-testid="stDataEditor"] table,
    div[data-testid="stDataEditor"] th,
    div[data-testid="stDataEditor"] td {
        border: 1px solid #444 !important;
        border-collapse: collapse !important;
    }
    div[data-testid="stDataFrame"] [role="grid"],
    div[data-testid="stDataEditor"] [role="grid"] {
        border: 1px solid #444 !important;
    }
    div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataEditor"] [role="gridcell"],
    div[data-testid="stDataEditor"] [role="columnheader"] {
        border: 1px solid #444 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
 
st.markdown(
    """
**Codici disponibili per ogni giorno:**
`F` · `MAL` · `RC` · `CS` · `RR` · `IM` · `IP` · `IN` · `IREPN` · `IREPD` · `DM` · `DP` · `DN` · `DREPN` · `DREPD` · `M` · `P` · `N` · `REPN` · `REPD`
"""
)
 
# =========================
# INPUT - TABELLA EDITABILE
# =========================
COL_NAMES = [str(i) for i in range(1, DAYS + 1)]
 
if "inp" not in st.session_state:
    st.session_state.inp = pd.DataFrame("", index=TECHS, columns=COL_NAMES)
 
if "festivo_giorni" not in st.session_state:
    st.session_state.festivo_giorni = ""
 
st.subheader("Inserisci disponibilità / vincoli")
 
data_inizio = st.date_input("Data di inizio del periodo (giorno 1)", value=None)
 
GIORNI_SETT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
 
if data_inizio is not None:
    import datetime
    col_labels = []
    for i in range(DAYS):
        giorno = data_inizio + datetime.timedelta(days=i)
        col_labels.append(f"{i+1} {GIORNI_SETT[giorno.weekday()]}")
else:
    st.info("Seleziona la data di inizio per vedere i giorni della settimana nella tabella.")
    col_labels = COL_NAMES
 
# Bottone Pulisci: cancella anche la cache interna del widget (non solo il dataframe)
col_clear, _ = st.columns([1, 5])
with col_clear:
    if st.button("🧹 Pulisci griglia"):
        st.session_state.inp = pd.DataFrame("", index=TECHS, columns=COL_NAMES)
        st.session_state.festivo_giorni = ""
        if "editor_input" in st.session_state:
            del st.session_state["editor_input"]
        st.rerun()
 
# La griglia è dentro un FORM: le modifiche si fissano solo al click di "Salva",
# evitando che Streamlit "perda" un'edit perché ricarica la pagina troppo presto
# mentre stai ancora scrivendo nelle celle.
with st.form("form_input", border=False):
    festivo_input = st.text_input(
        "Giorni festivi (numeri separati da virgola, es: 5,12,25) — si comportano come domenica:",
        value=st.session_state.festivo_giorni,
    )
 
    display_df = st.session_state.inp.copy()
    display_df.columns = col_labels
 
    # colonne strette (max 4 lettere nei codici): si vede tutto il mese senza scroll
    col_config_input = {
        col: st.column_config.TextColumn(label=col, width=46)
        for col in display_df.columns
    }
 
    edited_display = st.data_editor(
        display_df,
        use_container_width=False,
        num_rows="fixed",
        key="editor_input",
        column_config=col_config_input,
    )
 
    salva = st.form_submit_button("💾 Salva tabella", type="secondary")
 
if salva:
    edited = edited_display.copy()
    edited.columns = COL_NAMES
    st.session_state.inp = edited
    st.session_state.festivo_giorni = festivo_input
    st.success("Tabella salvata.")
 
 
inp = st.session_state.inp
 
# parsing dei giorni festivi inseriti come testo (es. "5,12,25")
_festivi_set = set()
for _tok in st.session_state.festivo_giorni.replace(" ", "").split(","):
    if _tok.isdigit():
        _festivi_set.add(int(_tok))
 
st.divider()
 
 
# =========================
# BOTTONE SOLVE
# =========================
if st.button("🚀 Genera turni", type="primary"):
 
    model = cp_model.CpModel()
 
    # giorno della settimana basato sulla data di inizio scelta dall'utente
    import datetime as _dt
 
    def weekday_of(d):
        if data_inizio is None:
            return d % 7  # fallback: assume giorno1 = lunedi
        return (data_inizio + _dt.timedelta(days=d)).weekday()
 
    def is_saturday(d):
        return weekday_of(d) == 5
 
    def is_sunday(d):
        return weekday_of(d) == 6
 
    def is_friday(d):
        return weekday_of(d) == 4
 
    def is_festivo(d):
        return (d + 1) in _festivi_set
 
    def is_giorno_speciale(d):
        # domenica O giorno segnato FESTIVO: si comporta come domenica (solo REPD/REPN)
        return is_sunday(d) or is_festivo(d)
 
    # =========================
    # VARIABILI
    # =========================
    x = {}
    for t in TECHS:
        for d in range(DAYS):
            for s in ALL_SHIFTS:
                if is_giorno_speciale(d):
                    if s not in ("REPN", "REPD"):
                        continue  # domenica/festivo: solo REPD (diurna) e REPN (notturna), niente M/P/N
                else:
                    if s == "REPD":
                        continue  # REPD esiste solo la domenica/festivo
                x[(t, d, s)] = model.NewBoolVar(f"x_{t}_{d}_{s}")
 
    def var(t, d, s):
        return x.get((t, d, s))
 
    # =========================
    # FUNZIONI INPUT
    # =========================
    def is_absent(v):
        v = str(v).upper()
        return any(code in v for code in ["F", "MAL", "RC", "CS", "RR"])
 
    def is_blocked(v, s):
        return f"I{s}" in str(v)
 
    def is_preferred(v, s):
        return f"D{s}" in str(v)
 
    def is_forced(v, s):
        # se la cella contiene ESATTAMENTE il codice del turno (es. "M", "REPN")
        # senza prefisso D/I, è un'assegnazione OBBLIGATA
        return str(v).strip() == s
 
    # =========================
    # 1. MUTUAL EXCLUSION GIORNALIERA
    # =========================
    for t in TECHS:
        for d in range(DAYS):
            mpn = [var(t, d, s) for s in ["M", "P", "N"] if var(t, d, s) is not None]
            if mpn:
                model.Add(sum(mpn) <= 1)
 
            repn = var(t, d, "REPN")
            n_ = var(t, d, "N")
            if repn is not None and n_ is not None:
                model.Add(repn + n_ <= 1)
 
            repd = var(t, d, "REPD")
            if repd is not None:
                for s in ["M", "P", "N"]:
                    v_ = var(t, d, s)
                    if v_ is not None:
                        model.Add(repd + v_ <= 1)
 
    # =========================
    # 2. FERIE / MALATTIA -> HARD BLOCK su tutto
    # =========================
    for t in TECHS:
        for d in range(DAYS):
            if is_absent(inp.loc[t, str(d + 1)]):
                for s in ALL_SHIFTS:
                    v_ = var(t, d, s)
                    if v_ is not None:
                        model.Add(v_ == 0)
 
    # =========================
    # 3. INDISPONIBILITÀ TURNO (I*) -> HARD BLOCK
    # =========================
    for t in TECHS:
        for d in range(DAYS):
            v = inp.loc[t, str(d + 1)]
            for s in ALL_SHIFTS:
                if is_blocked(v, s):
                    v_ = var(t, d, s)
                    if v_ is not None:
                        model.Add(v_ == 0)
 
    # =========================
    # 3b. ASSEGNAZIONE FORZATA (cella = codice turno puro, es. "M", "REPN")
    # =========================
    for t in TECHS:
        for d in range(DAYS):
            v = inp.loc[t, str(d + 1)]
            for s in ALL_SHIFTS:
                if is_forced(v, s):
                    v_ = var(t, d, s)
                    if v_ is not None:
                        model.Add(v_ == 1)
 
    # =========================
    # 4. MAX 6 UNITA' SETTIMANALI (M=1, P=1, N=2). REP NON CONTA.
    #    Tutti i lavoratori NON in ferie devono tendere a 6 unita'/settimana
    #    (vincolo HARD <=6, spinta forte verso 6 nell'obiettivo piu' sotto)
    # =========================
    weekly_unit_vars = []  # (somma_unita_var) per dare un bonus quando si avvicina a 6
    for t in TECHS:
        for w in range(DAYS // 7):
            days_in_week = range(w * 7, min((w + 1) * 7, DAYS))
            terms = []
            for d in days_in_week:
                if var(t, d, "M") is not None:
                    terms.append(var(t, d, "M"))
                if var(t, d, "P") is not None:
                    terms.append(var(t, d, "P"))
                n_ = var(t, d, "N")
                if n_ is not None:
                    terms.append(2 * n_)
            if terms:
                model.Add(sum(terms) <= 6)
                weekly_unit_vars.append(sum(terms))
 
    # =========================
    # 5. MAX 7 REP AL MESE (REPN + REPD) PER TUTTI
    # =========================
    rep_total = {}
    for t in TECHS:
        terms = []
        for d in range(DAYS):
            for s in REP_SHIFTS:
                v_ = var(t, d, s)
                if v_ is not None:
                    terms.append(v_)
        rep_total[t] = sum(terms)
        model.Add(rep_total[t] <= MAX_REP_MONTH)
 
    # =========================
    # 6. TIZIANA: MAX 6 NOTTI (N + REPN) AL MESE
    # =========================
    tiz_notti = []
    for d in range(DAYS):
        n_ = var("Tiziana", d, "N")
        if n_ is not None:
            tiz_notti.append(n_)
        repn_ = var("Tiziana", d, "REPN")
        if repn_ is not None:
            tiz_notti.append(repn_)
    model.Add(sum(tiz_notti) <= TIZIANA_MAX_NOTTI)
 
    # =========================
    # 7. RIPOSO DOPO N: STOP COMPLETO IL GIORNO DOPO (nessun turno/REP)
    #    Il rientro avviene il giorno successivo ancora, in REP o M/P
    # =========================
    for t in TECHS:
        for d in range(DAYS - 1):
            n_ = var(t, d, "N")
            if n_ is None:
                continue
            for s in ALL_SHIFTS:
                v_next = var(t, d + 1, s)
                if v_next is not None:
                    model.Add(v_next == 0).OnlyEnforceIf(n_)
 
    # =========================
    # 7b. DOPO LA REP NOTTURNA NON SI FA LA MATTINA, BENSI' IL POMERIGGIO
    # =========================
    for t in TECHS:
        for d in range(DAYS - 1):
            repn_ = var(t, d, "REPN")
            m_next = var(t, d + 1, "M")
            if repn_ is not None and m_next is not None:
                model.Add(m_next == 0).OnlyEnforceIf(repn_)
 
    # NOTA: la REP di per se' non prevede un giorno di riposo completo
    # (solo dopo la N c'e' lo stop totale); dopo la REPN si esclude solo la M.
 
    # =========================
    # 9. COPERTURA M E P: SEMPRE ALMENO 1 PERSONA (HARD), MAX 2 IN M
    # =========================
    for d in range(DAYS):
        m_vars = [var(t, d, "M") for t in TECHS if var(t, d, "M") is not None]
        p_vars = [var(t, d, "P") for t in TECHS if var(t, d, "P") is not None]
        if m_vars:
            model.Add(sum(m_vars) >= 1)
            # nessun tetto rigido: se avanzano operatori senza altro turno,
            # vengono messi in M (gestito come bonus nell'obiettivo)
        if p_vars:
            model.Add(sum(p_vars) >= 1)
 
    # =========================
    # 10. COPERTURA NOTTE: ESATTAMENTE 1 OPERATORE (REPN o N, mai più di uno)
    #     COPERTURA REPD DOMENICA: ESATTAMENTE 1 OPERATORE
    #     (la copertura minima è SOFT: si accetta scopertura solo se causata
    #      da troppe F/MAL; ma se qualcuno la copre, deve essere uno solo - HARD)
    # =========================
    night_uncovered = {}
    sunday_repd_uncovered = {}
 
    for d in range(DAYS):
        # copertura REPD diurna (domenica o giorno festivo)
        if is_giorno_speciale(d):
            repd_vars = [var(t, d, "REPD") for t in TECHS if var(t, d, "REPD") is not None]
            if repd_vars:
                model.Add(sum(repd_vars) <= 1)  # un solo operatore in REPD
                slack_d = model.NewBoolVar(f"repd_uncovered_{d}")
                model.Add(sum(repd_vars) + slack_d >= 1)
                sunday_repd_uncovered[d] = slack_d
 
        # copertura notte (REPN o N) - tutti i giorni, incluse le domeniche (solo REPN)
        coverage_vars = []
        for t in TECHS:
            n_ = var(t, d, "N")
            if n_ is not None:
                coverage_vars.append(n_)
            repn_ = var(t, d, "REPN")
            if repn_ is not None:
                coverage_vars.append(repn_)
        if coverage_vars:
            model.Add(sum(coverage_vars) <= 1)  # un solo operatore copre la notte
            slack = model.NewBoolVar(f"night_uncovered_{d}")
            model.Add(sum(coverage_vars) + slack >= 1)
            night_uncovered[d] = slack
 
    # =========================
    # 11. CONTINUITA' WEEKEND (SOFT) + REPD A OPERATORE DIVERSO (HARD)
    #     chi fa REPN sabato è preferito per la REPN di domenica (stessa persona)
    #     la REPD di domenica deve invece andare a un altro operatore
    # =========================
    weekend_bonus_vars = []
    for t in TECHS:
        for d in range(DAYS - 1):
            if is_saturday(d):
                sat_repn = var(t, d, "REPN")
                sun_repn = var(t, d + 1, "REPN")
                sun_repd = var(t, d + 1, "REPD")
 
                # bonus soft: stessa persona REPN sabato e REPN domenica
                if sat_repn is not None and sun_repn is not None:
                    both = model.NewBoolVar(f"weekend_cont_{t}_{d}")
                    model.AddMultiplicationEquality(both, [sat_repn, sun_repn])
                    weekend_bonus_vars.append(both)
 
                # hard: chi fa REPN sabato NON può fare la REPD di domenica
                if sat_repn is not None and sun_repd is not None:
                    model.Add(sat_repn + sun_repd <= 1)
 
    # =========================
    # 11c. CHI FA VENERDI' NOTTE FA SABATO POMERIGGIO E DOMENICA REPD
    #      (rotazione: un weekend impegnato, uno libero)
    # =========================
    for t in TECHS:
        for d in range(DAYS - 2):
            if is_friday(d):
                fri_n = var(t, d, "N")
                sat_p = var(t, d + 1, "P")
                sun_repd = var(t, d + 2, "REPD")
                if fri_n is not None and sat_p is not None:
                    model.Add(sat_p == 1).OnlyEnforceIf(fri_n)
                if fri_n is not None and sun_repd is not None:
                    model.Add(sun_repd == 1).OnlyEnforceIf(fri_n)
 
    # =========================
    # 11d. NOTTI/REP NON CONSECUTIVE (SOFT): penalita' se la stessa persona
    #      fa notte (N o REPN) due giorni di seguito
    # =========================
    consecutive_night_vars = []
    for t in TECHS:
        for d in range(DAYS - 1):
            today_terms = [v for v in [var(t, d, "N"), var(t, d, "REPN")] if v is not None]
            tomorrow_terms = [v for v in [var(t, d + 1, "N"), var(t, d + 1, "REPN")] if v is not None]
            if not today_terms or not tomorrow_terms:
                continue
            today_night = model.NewBoolVar(f"night_today_{t}_{d}")
            model.AddMaxEquality(today_night, today_terms)
            tomorrow_night = model.NewBoolVar(f"night_tomorrow_{t}_{d}")
            model.AddMaxEquality(tomorrow_night, tomorrow_terms)
            both = model.NewBoolVar(f"consec_night_{t}_{d}")
            model.AddMultiplicationEquality(both, [today_night, tomorrow_night])
            consecutive_night_vars.append(both)
    # =========================
    # 11e. DOMENICA/FESTIVO: REPN e REPD NON POSSONO ESSERE DELLO STESSO OPERATORE
    # =========================
    for t in TECHS:
        for d in range(DAYS):
            if is_giorno_speciale(d):
                repn_ = var(t, d, "REPN")
                repd_ = var(t, d, "REPD")
                if repn_ is not None and repd_ is not None:
                    model.Add(repn_ + repd_ <= 1)
 
    # =========================
    # 11b. DISTRIBUZIONE EQUA DI REPN, REPD, N TRA GLI OPERATORI
    #      minimizziamo lo squilibrio (max - min) per ciascun tipo di turno
    # =========================
    def fairness_penalty(shift_name, label):
        """Crea variabili max/min sul totale di 'shift_name' per tecnico
        e ritorna una lista di termini obiettivo che penalizzano lo squilibrio."""
        totals = []
        for t in TECHS:
            terms = [var(t, d, shift_name) for d in range(DAYS) if var(t, d, shift_name) is not None]
            if not terms:
                continue
            tot = model.NewIntVar(0, DAYS, f"tot_{label}_{t}")
            model.Add(tot == sum(terms))
            totals.append(tot)
        if len(totals) < 2:
            return []
        max_v = model.NewIntVar(0, DAYS, f"max_{label}")
        min_v = model.NewIntVar(0, DAYS, f"min_{label}")
        model.AddMaxEquality(max_v, totals)
        model.AddMinEquality(min_v, totals)
        spread = model.NewIntVar(0, DAYS, f"spread_{label}")
        model.Add(spread == max_v - min_v)
        return [spread]
 
    fairness_terms = []
    fairness_terms += fairness_penalty("REPN", "repn")
    fairness_terms += fairness_penalty("REPD", "repd")
    fairness_terms += fairness_penalty("N", "n")
 
    # =========================
    # 12. OBIETTIVO
    # =========================
    objective = []
 
    for t in TECHS:
        for d in range(DAYS):
            v = inp.loc[t, str(d + 1)]
            for s in ALL_SHIFTS:
                if is_preferred(v, s):
                    v_ = var(t, d, s)
                    if v_ is not None:
                        objective.append(5 * v_)
 
    for t in TECHS:
        for d in range(DAYS):
            repn_ = var(t, d, "REPN")
            if repn_ is not None:
                objective.append(3 * repn_)
            repd_ = var(t, d, "REPD")
            if repd_ is not None:
                objective.append(3 * repd_)
            n_ = var(t, d, "N")
            if n_ is not None:
                objective.append(1 * n_)
 
    objective += [2 * v for v in weekend_bonus_vars]
 
    # spinta forte verso 6 unita'/settimana per ogni operatore (evita i "buchi")
    objective += [4 * v for v in weekly_unit_vars]
 
    # bonus generale di riempimento: qualsiasi M/P assegnato è meglio di un buco
    # (i blank non coperti da F/MAL/I*/D* vengono preferibilmente messi in M)
    for d in range(DAYS):
        m_vars = [var(t, d, "M") for t in TECHS if var(t, d, "M") is not None]
        p_vars = [var(t, d, "P") for t in TECHS if var(t, d, "P") is not None]
        objective += [2 * v for v in m_vars]
        objective += [1 * v for v in p_vars]  # leggera preferenza per M rispetto a P sui "buchi"
 
    # bonus: dopo la REP notturna, preferiamo il pomeriggio (non obbligatorio, ma incentivato)
    for t in TECHS:
        for d in range(DAYS - 1):
            repn_ = var(t, d, "REPN")
            p_next = var(t, d + 1, "P")
            if repn_ is not None and p_next is not None:
                both = model.NewBoolVar(f"repn_then_p_{t}_{d}")
                model.AddMultiplicationEquality(both, [repn_, p_next])
                objective.append(2 * both)
 
    objective += [-50 * s for s in night_uncovered.values()]
    objective += [-50 * s for s in sunday_repd_uncovered.values()]
 
    # penalita' forte sullo squilibrio tra operatori (equita')
    objective += [-4 * s for s in fairness_terms]
 
    # penalita' per notti/REP consecutive (preferiamo distribuirle nel mese)
    objective += [-3 * s for s in consecutive_night_vars]
 
    model.Maximize(sum(objective))
 
    # =========================
    # SOLVER
    # =========================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
 
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        out = pd.DataFrame("", index=TECHS, columns=[str(i) for i in range(1, DAYS + 1)])
        for t in TECHS:
            for d in range(DAYS):
                cella_input = str(inp.loc[t, str(d + 1)])
                if is_absent(cella_input):
                    codice_assenza = next(
                        (c for c in ["F", "MAL", "RC", "CS", "RR"] if c in cella_input.upper()),
                        "F",
                    )
                    out.loc[t, str(d + 1)] = codice_assenza
                    continue
                assigned = []
                for s in ALL_SHIFTS:
                    v_ = var(t, d, s)
                    if v_ is not None and solver.Value(v_) == 1:
                        assigned.append(s)
                out.loc[t, str(d + 1)] = "+".join(assigned)
 
        # giorni scoperti -> riga speciale "SCOPERTO" sotto la tabella
        giorni_scoperti_notte = [d + 1 for d, s in night_uncovered.items() if solver.Value(s) == 1]
        giorni_scoperti_repd = [d + 1 for d, s in sunday_repd_uncovered.items() if solver.Value(s) == 1]
 
        # riga aggiuntiva nella tabella che segnala "SCOPERTO" sul giorno
        out.loc["⚠️ SCOPERTO NOTTE"] = ""
        for gd in giorni_scoperti_notte:
            out.loc["⚠️ SCOPERTO NOTTE", str(gd)] = "SCOPERTO"
        out.loc["⚠️ SCOPERTO REP DOMENICA"] = ""
        for gd in giorni_scoperti_repd:
            out.loc["⚠️ SCOPERTO REP DOMENICA", str(gd)] = "SCOPERTO"
 
        st.success(
            "Soluzione "
            + ("ottimale" if status == cp_model.OPTIMAL else "trovata (non ottimale)")
            + " ✅"
        )
 
        if giorni_scoperti_notte:
            st.warning(f"⚠️ Notti scoperte nei giorni: {', '.join(map(str, giorni_scoperti_notte))}")
        if giorni_scoperti_repd:
            st.warning(f"⚠️ REP diurna domenicale scoperta nei giorni: {', '.join(map(str, giorni_scoperti_repd))}")
 
        BORDER = "border: 1px solid #444;"
 
        def color_shift(val):
            if val == "SCOPERTO":
                return BORDER + "background-color: #f8d7da; color: #842029; font-weight: bold"
            if val in ("F", "MAL"):
                return BORDER + "background-color: #e2e3e5; color: #6c757d; font-style: italic"
            if "REPD" in val:
                return BORDER + "background-color: #d4edda"
            if "REPN" in val:
                return BORDER + "background-color: #ffe5b4"
            if "N" in val:
                return BORDER + "background-color: #d6d8d9"
            if "M" in val:
                return BORDER + "background-color: #cce5ff"
            if "P" in val:
                return BORDER + "background-color: #fff3cd"
            return BORDER
 
        # intestazioni con i giorni della settimana
        col_labels_out = []
        for i in range(DAYS):
            if data_inizio is not None:
                giorno = data_inizio + _dt.timedelta(days=i)
                col_labels_out.append(f"{i+1} ({GIORNI_SETT[giorno.weekday()]})")
            else:
                col_labels_out.append(str(i + 1))
 
        out_display = out.copy()
        out_display.columns = col_labels_out
 
        col_config_out = {
            col: st.column_config.TextColumn(label=col, width=46)
            for col in out_display.columns
        }
 
        st.subheader("Turni generati")
        st.dataframe(
            out_display.style.map(color_shift).set_properties(**{"text-align": "center"}),
            use_container_width=False,
            column_config=col_config_out,
        )
 
        st.subheader("Riepilogo per tecnico")
        ABSENCE_CODES = ["F", "MAL", "RC", "CS", "RR"]
        RIEPILOGO_COLS = ALL_SHIFTS + ABSENCE_CODES
        summary = pd.DataFrame(index=TECHS, columns=RIEPILOGO_COLS).fillna(0)
        for t in TECHS:
            for s in ALL_SHIFTS:
                summary.loc[t, s] = sum(
                    1 for d in range(DAYS) if s in str(out.loc[t, str(d + 1)]).split("+")
                )
            for s in ABSENCE_CODES:
                summary.loc[t, s] = sum(
                    1 for d in range(DAYS) if str(out.loc[t, str(d + 1)]) == s
                )
        st.dataframe(
            summary.style.set_properties(**{"border": "1px solid #444", "text-align": "center"}),
            use_container_width=False,
        )
 
        # =========================
        # EXPORT CSV ED EXCEL
        # =========================
        csv = out_display.to_csv().encode("utf-8")
        st.download_button(
            "⬇️ Scarica turni in CSV",
            data=csv,
            file_name="turni_generati.csv",
            mime="text/csv",
        )
 
        import io
        from openpyxl.styles import Border, Side
        from openpyxl.worksheet.page import PageMargins
 
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            out_display.to_excel(writer, sheet_name="Turni")
            summary.to_excel(writer, sheet_name="Riepilogo")
 
            thin = Side(border_style="thin", color="444444")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)
 
            for sheet_name in ["Turni", "Riepilogo"]:
                ws = writer.sheets[sheet_name]
 
                # bordi su tutte le celle con dati (incluse intestazioni)
                for row in ws.iter_rows(
                    min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column
                ):
                    for cell in row:
                        cell.border = border
 
                # impostazioni di stampa: orizzontale, tutte le colonne su una pagina
                ws.page_setup.orientation = "landscape"
                ws.page_setup.fitToWidth = 1
                ws.page_setup.fitToHeight = 0  # 0 = altezza libera (più pagine in verticale se serve)
                ws.sheet_properties.pageSetUpPr.fitToPage = True
                ws.page_margins = PageMargins(
                    left=0.3, right=0.3, top=0.4, bottom=0.4, header=0.2, footer=0.2
                )
        buffer.seek(0)
 
        st.download_button(
            "⬇️ Scarica turni in Excel (.xlsx)",
            data=buffer,
            file_name="turni_generati.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
 
    else:
        st.error("❌ Nessuna soluzione trovata. Controlla i vincoli inseriti (troppe ferie/indisponibilità rigide?).")