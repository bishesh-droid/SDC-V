"""Structural engineering knowledge base: curated reference entries served to the Knowledge base tab.

This is reference material, not calculator input. Numbers are summaries of IS 456:2000, IS 875, IS 1893,
IS 800 and standard mechanics; always confirm against the printed code before relying on them.
Entries with impl=True describe something the SDC-V calculator actually implements.
"""
from __future__ import annotations

import re

TOPICS = [
    ("materials", "Materials"),
    ("limit-state", "Limit state design"),
    ("flexure", "Flexure"),
    ("shear", "Shear and torsion"),
    ("serviceability", "Serviceability"),
    ("detailing", "Detailing"),
    ("slabs", "Slabs"),
    ("columns", "Columns"),
    ("foundations", "Foundations and earth retaining"),
    ("loads", "Loads"),
    ("seismic", "Seismic and wind"),
    ("steel", "Steel structures"),
    ("analysis", "Structural analysis"),
    ("durability", "Durability and quality"),
    ("construction", "Construction practice"),
    ("units", "Units and conversions"),
    ("standards", "Codes and standards"),
    ("glossary", "Glossary"),
    ("ai", "AI methods (CE F417)"),
]

ENTRIES: list[dict] = []


def _e(topic: str, title: str, summary: str, points=(), formulas=(), clause: str = "", tags: str = "", impl: bool = False):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    ENTRIES.append({"id": f"{topic}-{slug}"[:80], "topic": topic, "title": title, "summary": summary,
                    "points": list(points), "formulas": list(formulas), "clause": clause,
                    "tags": [t.strip() for t in tags.split(",") if t.strip()], "implemented": impl})


# ------------------------------------------------------------------ materials
_e("materials", "Concrete grades", "Concrete is designated M<n>, where n is the characteristic cube strength fck in N/mm2 at 28 days (5% of results may fall below it).",
   ["Ordinary grades M10-M20, standard M25-M55, high strength M60-M80 (IS 456 Table 2).",
    "M20 is the minimum for reinforced concrete in mild exposure; exposure raises the minimum grade (Table 5).",
    "The calculator supports M20, M25, M30, M35 and M40."],
   clause="IS456 Cl. 6.1; Table 2", tags="fck, cube strength, grade, M25", impl=True)
_e("materials", "Elastic modulus and tensile strength of concrete", "Short-term modulus and flexural tensile strength are derived from fck.",
   ["M25 gives Ec = 25 000 N/mm2.", "Creep and shrinkage make the long-term modulus lower than the short-term value.",
    "Reinforced concrete unit weight is taken as 25 kN/m3, plain concrete 24 kN/m3."],
   ["Ec = 5000 sqrt(fck)  N/mm2", "fcr = 0.7 sqrt(fck)  N/mm2 (flexural tensile strength)"], "IS456 Cl. 6.2.2; 6.2.3.1", "modulus, Ec, flexural strength, cracking")
_e("materials", "Reinforcing steel grades", "High-yield-strength deformed (HYSD) bars to IS 1786 are standard; mild steel is now rare.",
   ["Fe250 (mild), Fe415, Fe500, Fe550 and Fe600 are the common yield grades; D-suffixed bars (Fe500D) have higher ductility.",
    "Modulus of elasticity Es = 2 x 10^5 N/mm2.",
    "The calculator supports Fe250, Fe415 and Fe500."],
   ["Design yield strain (Fe415 and above) = 0.87 fy / Es + 0.002", "Fe415: 0.0038;  Fe500: 0.00418"], "IS456 Cl. 5.6; 26.5; Fig. 23", "steel, rebar, TMT, HYSD, Fe500, yield", impl=True)
_e("materials", "Partial safety factors for materials", "Design strengths are characteristic strengths divided by a material factor.",
   ["Concrete gamma_m = 1.5; steel gamma_m = 1.15.", "Design compressive stress in concrete in bending = 0.446 fck (0.67 fck / 1.5); design steel stress = 0.87 fy."],
   ["fcd = 0.67 fck / 1.5 = 0.446 fck", "fyd = fy / 1.15 = 0.87 fy"], "IS456 Cl. 36.4.2", "gamma, safety factor, design strength", impl=True)
_e("materials", "Cement types", "Cement choice affects strength gain, heat of hydration and durability.",
   ["OPC 33, 43 and 53 grade (IS 269): the number is 28-day mortar strength in N/mm2.",
    "PPC (fly ash, IS 1489) and PSC (slag, IS 455) gain strength more slowly but resist sulphates and chlorides better.",
    "Sulphate-resisting cement (IS 12330) for sulphate soils."],
   clause="IS 269; IS 455; IS 1489; IS 12330", tags="OPC, PPC, PSC, cement")
_e("materials", "Aggregates", "Aggregates make up about 70-75% of concrete volume.",
   ["Nominal maximum size is usually 20 mm for beams and slabs, 10-12.5 mm in congested sections.",
    "Maximum size should not exceed one quarter of the smallest member dimension, nor about 5 mm less than the minimum clear cover or bar spacing.",
    "Grading, shape, cleanliness and water absorption are controlled by IS 383."],
   clause="IS456 Cl. 5.3; IS 383", tags="aggregate, grading, coarse, fine, sand")
_e("materials", "Water-cement ratio and cement content", "Durability limits for reinforced concrete by exposure.",
   ["Mild: w/c 0.55 max, cement 300 kg/m3 min.", "Moderate: 0.50, 300.", "Severe: 0.45, 320.", "Very severe: 0.45, 340.", "Extreme: 0.40, 360."],
   clause="IS456 Table 5", tags="w/c, water cement ratio, cement content, exposure")
_e("materials", "Concrete mix design", "Mix proportions for a target strength are found by IS 10262.",
   ["Target mean strength f'ck = fck + 1.65 s, where s is the standard deviation (Table 1 of IS 10262).",
    "Steps: target strength, w/c ratio, water content (from slump and aggregate size), cement content, aggregate proportions, trial mixes.",
    "Nominal mixes (M5-M20) are allowed only for small works; M25 and above need design mixes."],
   ["f'ck = fck + 1.65 s"], "IS 10262:2019; IS456 Cl. 9", "mix design, proportioning, target strength")
_e("materials", "Workability", "Workability is how easily concrete can be placed and compacted without segregation.",
   ["Measured by slump, compaction factor or Vebe time.", "Heavily reinforced sections need higher slump than mass concrete.", "Add plasticisers or superplasticisers rather than extra water."],
   clause="IS456 Cl. 7; IS 1199", tags="slump, workability, admixture, plasticiser")

# ---------------------------------------------------------------- limit state
_e("limit-state", "Limit state philosophy", "A structure must be safe against collapse (ultimate limit states) and fit for use (serviceability limit states) over its life.",
   ["Ultimate: flexure, shear, torsion, compression, stability, overturning, fatigue.", "Serviceability: deflection, cracking, vibration.",
    "Characteristic loads are multiplied by partial load factors; characteristic strengths are divided by material factors."],
   clause="IS456 Cl. 18, 35, 36", tags="limit state, ultimate, serviceability", impl=True)
_e("limit-state", "Load combinations and load factors", "Design loads are factored combinations of dead, imposed, wind and earthquake loads.",
   ["Dead + imposed: 1.5 (DL + LL).", "Dead + wind or earthquake: 1.5 (DL + WL) or 1.5 (DL + EL); 0.9 DL + 1.5 WL when stability is critical.",
    "Dead + imposed + wind or earthquake: 1.2 (DL + LL + WL) or 1.2 (DL + LL + EL).",
    "The calculator applies 1.5 (DL + LL) and adds self-weight itself."],
   ["wu = 1.5 (DL + LL + self-weight)"], "IS456 Table 18", "load factor, combination, 1.5, wu", impl=True)
_e("limit-state", "Design stress block in flexure", "At the ultimate limit state the compressive stress in concrete is idealised as a rectangle-parabola; IS 456 gives an equivalent rectangle.",
   ["Maximum concrete strain in bending is 0.0035.", "Resultant compression acts at 0.416 xu from the compression edge (0.42 xu is used for design).",
    "Tension in concrete is ignored."],
   ["C = 0.36 fck b xu", "lever arm z = d - 0.42 xu"], "IS456 Cl. 38.1; Annex G", "stress block, 0.36, 0.42, neutral axis", impl=True)
_e("limit-state", "Limiting neutral axis depth and Mu,lim", "Beams must be under-reinforced so that steel yields before concrete crushes.",
   ["xu,max / d = 0.53 (Fe250), 0.48 (Fe415), 0.46 (Fe500).", "If Mu exceeds Mu,lim the section needs compression steel or a larger section."],
   ["Mu,lim = 0.36 fck b xu,max (d - 0.42 xu,max)", "Mu,lim / (fck b d2) = 0.148 (Fe250), 0.138 (Fe415), 0.133 (Fe500)"], "IS456 Cl. 38.1; Annex G-1.1", "balanced, under-reinforced, over-reinforced, Mu,lim", impl=True)
_e("limit-state", "Working stress method", "The older elastic method is still used for some serviceability and liquid-retaining checks.",
   ["Stresses are limited to permissible values (sigma_cbc, sigma_st) under unfactored loads.", "Modular ratio m = 280 / (3 sigma_cbc)."],
   ["m = 280 / (3 sigma_cbc)"], "IS456 Annex B", "WSM, working stress, modular ratio")

# -------------------------------------------------------------------- flexure
_e("flexure", "Singly reinforced rectangular beam", "Required tension steel for a given design moment.",
   ["Valid when Mu <= Mu,lim. Provide at least the minimum steel and at most 4% of gross area.",
    "Check xu / d <= xu,max / d for the provided steel."],
   ["Mu = 0.87 fy Ast d (1 - Ast fy / (b d fck))", "Ast = 0.5 (fck / fy) [1 - sqrt(1 - 4.6 Mu / (fck b d2))] b d", "xu = 0.87 fy Ast / (0.36 fck b)"],
   "IS456 Annex G-1.1(b)", "Ast, tension steel, moment of resistance, rectangular beam", impl=True)
_e("flexure", "Minimum and maximum tension steel", "Limits on beam tension reinforcement.",
   ["Minimum As / (b d) = 0.85 / fy prevents brittle failure at cracking.", "Maximum 0.04 b D keeps the section placeable and compactable."],
   ["As,min = 0.85 b d / fy", "As,max = 0.04 b D"], "IS456 Cl. 26.5.1.1", "minimum steel, maximum steel, 0.85/fy", impl=True)
_e("flexure", "Doubly reinforced beam", "Compression steel is added when the moment exceeds Mu,lim and the section cannot be enlarged. (Not supported by the calculator.)",
   ["Stress fsc in compression steel depends on strain at depth d' (IS 456 SP 16 Table F).", "Tension steel Ast = Ast1 + Ast2, where Ast2 balances the compression steel."],
   ["Mu = Mu,lim + fsc Asc (d - d')", "Ast2 = fsc Asc / (0.87 fy)"], "IS456 Annex G-1.2", "doubly reinforced, compression steel, Asc")
_e("flexure", "Flanged (T and L) beams", "Slab and beam act together. (Not supported by the calculator.)",
   ["Effective flange width is the least of the formula below and the actual width available.",
    "If xu <= Df the section behaves as a rectangle of width bf.", "Otherwise add the flange overhang: Mu = 0.36 (xu/d)(1 - 0.42 xu/d) fck bw d2 + 0.45 fck (bf - bw) Df (d - Df/2), for Df/d <= 0.2."],
   ["T-beam: bf = lo/6 + bw + 6 Df", "L-beam: bf = lo/12 + bw + 3 Df", "lo = distance between points of zero moment"], "IS456 Cl. 23.1.2; Annex G-2", "T-beam, L-beam, flange, bf")
_e("flexure", "Continuous beam moment coefficients", "Simplified coefficients for continuous beams of three or more spans.",
   ["Applies to approximately equal spans (differing by at most 15%), uniformly distributed loads, live load not more than 3/4 of dead load.",
    "Dead + imposed (fixed): span +1/12 (end span), +1/16 (interior); support -1/10 (next to end), -1/12 (others).",
    "Moments are w L2 times the coefficient."],
   clause="IS456 Cl. 22.5; Table 12", tags="continuous beam, coefficients")
_e("flexure", "Effective span", "The span used in analysis and deflection checks.",
   ["Simply supported: the lesser of centre-to-centre of supports or clear span + d.", "Cantilever: length to the face of the support + d/2.", "The calculator takes the span exactly as the user supplies it."],
   clause="IS456 Cl. 22.2", tags="effective span, clear span", impl=True)

# ------------------------------------------------------------- shear / torsion
_e("shear", "Nominal shear stress and concrete shear strength", "Shear is checked against the concrete strength, which depends on tension steel and grade.",
   ["tau_v = Vu / (b d).", "tau_c increases with pt = 100 Ast / (b d) and fck (Table 19, range 0.15% to 3%).",
    "tau_v must never exceed tau_c,max; if it does, enlarge the section.",
    "tau_c,max (N/mm2): M20 2.8, M25 3.1, M30 3.5, M35 3.7, M40 4.0."],
   ["tau_v = Vu / (b d)"], "IS456 Cl. 40.1; Tables 19, 20", "tau_c, tau_v, shear stress, Table 19", impl=True)
_e("shear", "Vertical stirrup design", "When tau_v exceeds tau_c, stirrups carry the excess shear.",
   ["Vus = Vu - tau_c b d.", "Maximum spacing: 0.75 d or 300 mm, whichever is less.", "Minimum shear steel applies even if tau_v < tau_c.",
    "Stirrups closer than about 75 mm are hard to place."],
   ["sv = 0.87 fy Asv d / Vus", "Asv / (b sv) >= 0.4 / (0.87 fy)"], "IS456 Cl. 40.4; 26.5.1.5; 26.5.1.6", "stirrup, shear reinforcement, sv, Asv", impl=True)
_e("shear", "Critical section for shear", "Where Vu is taken. The calculator is deliberately conservative.",
   ["For members loaded on top and supported on compression faces, shear within distance d of the support may be ignored; design shear is taken at d from the face.",
    "The calculator uses the shear at the support, which is conservative."],
   clause="IS456 Cl. 22.6.2; 40.5", tags="critical section, support shear", impl=True)
_e("shear", "Torsion", "Torsion is designed by converting it into equivalent shear and moment. (Not supported by the calculator.)",
   ["Equivalent shear Ve = Vu + 1.6 Tu / b.", "Equivalent moment Me1 = Mu + Mt, where Mt = Tu (1 + D/b) / 1.7.", "Closed stirrups and longitudinal steel are provided on both."],
   ["Ve = Vu + 1.6 Tu / b", "Mt = Tu (1 + D/b) / 1.7"], "IS456 Cl. 41", "torsion, equivalent shear")
_e("shear", "Punching shear", "Slabs and footings are checked at a perimeter d/2 from the column face.",
   ["Shear strength = ks tau_c with ks = 0.5 + beta_c (not more than 1), beta_c = short side / long side of column.", "tau_c = 0.25 sqrt(fck) for punching."],
   ["tau_c' = ks (0.25 sqrt(fck))"], "IS456 Cl. 31.6", "punching, two-way shear, flat slab, footing")

# -------------------------------------------------------------- serviceability
_e("serviceability", "Deflection control by span to depth ratio", "Deflection limits are met indirectly by limiting L/d.",
   ["Basic L/d: 20 for simply supported, 7 for cantilever, 26 for continuous beams.", "For simply supported spans over 10 m multiply the basic ratio by 10 / span (not for cantilevers).",
    "The ratio is increased by a modification factor kt that depends on the tension steel stress and pt (Fig. 4).",
    "Compression steel and flanges give additional modification factors.",
    "The calculator uses an analytic fit of Fig. 4, capped at 2.0."],
   ["fs = 0.58 fy (Ast,req / Ast,prov)", "L/d <= basic L/d x kt"], "IS456 Cl. 23.2.1; Fig. 4", "deflection, span depth, L/d, kt", impl=True)
_e("serviceability", "Deflection limits", "Absolute limits on final deflection.",
   ["Total deflection (including creep, shrinkage and temperature) should not exceed span / 250.", "Deflection after partitions and finishes should not exceed span / 350 or 20 mm, whichever is less."],
   clause="IS456 Cl. 23.2", tags="deflection limit, span/250, span/350")
_e("serviceability", "Cracking", "Crack width is controlled by bar spacing, cover and steel stress.",
   ["Surface crack width is limited to about 0.3 mm in normal conditions and 0.2 mm in aggressive environments.", "Clear bar spacing is limited (Table 15) when a section has little tension steel.",
    "Side-face reinforcement of 0.1% of web area, half on each face, is needed when D exceeds 750 mm."],
   clause="IS456 Cl. 35.3.2; 26.3.3; 26.5.1.3", tags="crack width, side face, Table 15", impl=True)
_e("serviceability", "Lateral stability of beams", "Slender beams can buckle sideways.",
   ["Simply supported or continuous: clear distance between lateral restraints not more than 60 b or 250 b2 / d, whichever is less.", "Cantilever: 25 b or 100 b2 / d, whichever is less."],
   clause="IS456 Cl. 23.3", tags="lateral buckling, slenderness limit beam")

# ------------------------------------------------------------------- detailing
_e("detailing", "Nominal cover", "Cover protects steel from corrosion and fire.",
   ["Mild 20 mm, moderate 30 mm, severe 45 mm, very severe 50 mm, extreme 75 mm (reinforced concrete).", "Cover is not less than the bar diameter.",
    "Fire resistance may require more cover (Table 16A).", "The calculator measures cover to the stirrup."],
   clause="IS456 Cl. 26.4; Table 16", tags="cover, exposure, fire", impl=True)
_e("detailing", "Bar spacing", "Spacing rules allow concrete to flow and limit cracking.",
   ["Minimum horizontal clear spacing: the largest of bar diameter, aggregate size + 5 mm.", "Minimum vertical spacing between layers: 15 mm, 2/3 of aggregate size or bar diameter.",
    "Maximum clear spacing of tension bars (Table 15): 300 mm Fe250, 180 mm Fe415, 150 mm Fe500 (no redistribution)."],
   clause="IS456 Cl. 26.3; Table 15", tags="spacing, clear distance, layers", impl=True)
_e("detailing", "Development length", "Length of bar needed to develop its design stress by bond.",
   ["Design bond stress tau_bd for plain bars in tension (N/mm2): M20 1.2, M25 1.4, M30 1.5, M35 1.7, M40 1.9.", "Increase by 60% for deformed bars; increase by 25% for bars in compression.",
    "Hooks and bends add anchorage value: 16 phi for a 180 degree hook, 8 phi for a 90 degree bend (standard radii)."],
   ["Ld = phi sigma_s / (4 tau_bd)", "sigma_s = 0.87 fy at full stress"], "IS456 Cl. 26.2.1", "development length, bond, anchorage, Ld")
_e("detailing", "Lap splices", "Splicing bars by overlap.",
   ["Flexural tension lap: not less than Ld or 30 phi, whichever is greater.", "Compression lap: not less than Ld in compression or 24 phi.",
    "Avoid lapping more than half the bars at a section; stagger laps.", "Do not lap bars larger than 36 mm (use welding or couplers)."],
   clause="IS456 Cl. 26.2.5", tags="lap, splice, overlap")
_e("detailing", "Curtailment and anchorage at supports", "Where bars may stop.",
   ["Extend bars beyond the theoretical cut-off by the larger of d or 12 phi.", "At a simple support, at least one third of the maximum positive-moment steel should continue into the support.",
    "Check anchorage: Ld <= 1.3 M1 / V + L0."],
   ["Ld <= 1.3 M1 / V + L0"], "IS456 Cl. 26.2.3", "curtailment, cut-off, support anchorage")
_e("detailing", "Stirrup detailing", "Shear links must be closed and well anchored.",
   ["Use closed stirrups with 135 degree hooks and an extension of about 6 phi (not less than 65 mm).", "Space them closely near supports.", "Stirrup diameter is commonly 8 mm; the calculator assumes two-legged 8 mm stirrups."],
   clause="IS456 Cl. 26.2.2.2; SP 34", tags="stirrup, links, hook", impl=True)
_e("detailing", "Side-face reinforcement", "Required in deep beams to control cracking in the web.",
   ["Where D exceeds 750 mm provide 0.1% of web area on each face in total (half per face), at not more than 300 mm or web thickness spacing.", "The calculator reports a warning but does not design it."],
   clause="IS456 Cl. 26.5.1.3", tags="side face, skin reinforcement, deep web", impl=True)

# ----------------------------------------------------------------------- slabs
_e("slabs", "One-way and two-way slabs", "Slabs span in one or two directions depending on the aspect ratio and supports.",
   ["Treat as one-way if the long span / short span exceeds 2.", "Two-way slabs use moment coefficients (Table 26) for the edge conditions, or the yield line method."],
   clause="IS456 Cl. 24; Annex D", tags="one way, two way, slab")
_e("slabs", "Slab reinforcement rules", "Minimum steel and spacing in slabs.",
   ["Minimum steel 0.12% of gross area for Fe415 and Fe500, 0.15% for Fe250.", "Main bar spacing not more than 3 d or 300 mm; distribution bar spacing not more than 5 d or 450 mm.",
    "Bar diameter should not exceed one eighth of the slab thickness."],
   clause="IS456 Cl. 26.5.2", tags="slab steel, spacing, distribution")
_e("slabs", "Slab thickness from deflection", "Initial depth is found from the span to depth ratio.",
   ["Use the same basic ratios as beams (20 simply supported, 26 continuous, 7 cantilever) with the modification factor.", "For two-way slabs use the shorter span; the ratios are as above for spans up to 3.5 m."],
   clause="IS456 Cl. 24.1", tags="slab depth, thickness")
_e("slabs", "Flat slabs", "Slabs supported directly on columns, with drop panels or capitals.",
   ["Designed with column strips and middle strips.", "Punching shear at the column usually governs the thickness.", "Drop panel and column capital sizes are set by Cl. 31."],
   clause="IS456 Cl. 31", tags="flat slab, drop panel, column strip")

# --------------------------------------------------------------------- columns
_e("columns", "Short axially loaded column", "Capacity of a short column with minimum eccentricity.",
   ["A column is short if effective length / least lateral dimension is less than 12.", "Minimum eccentricity: L/500 + D/30, not less than 20 mm.",
    "Helical reinforcement gives a 5% increase."],
   ["Pu = 0.4 fck Ac + 0.67 fy Asc", "emin = L/500 + D/30 >= 20 mm"], "IS456 Cl. 25.4; 39.3", "column, axial load, Pu, minimum eccentricity")
_e("columns", "Column reinforcement rules", "Longitudinal bars and ties.",
   ["Longitudinal steel between 0.8% and 6% of gross area (4% in practice at laps).", "At least 4 bars in rectangular and 6 in circular columns; minimum diameter 12 mm.",
    "Ties: diameter at least a quarter of the largest bar and not less than 6 mm; pitch not more than the least lateral dimension, 16 times the smallest bar, or 300 mm."],
   clause="IS456 Cl. 26.5.3", tags="longitudinal steel, ties, lateral reinforcement")
_e("columns", "Effective length and slenderness", "Effective length depends on end restraint.",
   ["Effective length factors (idealised): both ends fixed 0.5, fixed-hinged 0.7, both hinged 1.0, fixed-free 2.0; Code recommends 0.65, 0.80, 1.0 and 2.0 respectively.",
    "Slender columns (leff / D above 12) carry an additional moment."],
   ["Ma = Pu D / 2000 (leff / D)2"], "IS456 Cl. 25.2; 39.7; Annex E", "effective length, slender column, Euler")
_e("columns", "Interaction diagrams", "Combined axial load and bending is checked with interaction curves (SP 16 charts) or a strain compatibility analysis.",
   ["Biaxial bending uses the Bresler-type expression in Cl. 39.6."],
   ["(Mux/Mux1)^alpha_n + (Muy/Muy1)^alpha_n <= 1"], "IS456 Cl. 39.5, 39.6; SP 16", "interaction, biaxial, P-M")

# ----------------------------------------------------------------- foundations
_e("foundations", "Isolated footing design", "Steps for a column footing.",
   ["Size the plan area from the safe bearing capacity using service loads, including self-weight.", "Design for the net upward pressure from factored loads.",
    "Check bending at the column face, one-way shear at d from the face, punching at d/2, and development length.", "Minimum edge thickness on soil is 150 mm (300 mm on piles)."],
   clause="IS456 Cl. 34", tags="footing, isolated footing, bearing pressure")
_e("foundations", "Bearing capacity", "Soil capacity is estimated by Terzaghi's equation or from field tests.",
   ["Factor of safety is usually 2.5 to 3 on net ultimate capacity.", "Settlement often governs in clays and for large footings.", "Plate load and standard penetration tests give field data (IS 6403, IS 2131)."],
   ["qu = c Nc + q Nq + 0.5 gamma B Ngamma  (strip footing)", "qsafe = qnu / FoS + gamma Df"], "IS 6403", "Terzaghi, SBC, settlement")
_e("foundations", "Pile foundations", "Piles transfer load through weak soil to a firm stratum.",
   ["End bearing plus skin friction; group action reduces capacity of closely spaced piles.", "Minimum spacing about 3 times the pile diameter.", "Load tests confirm the design (IS 2911)."],
   clause="IS 2911", tags="pile, skin friction, end bearing, group")
_e("foundations", "Retaining walls", "Earth pressure and stability checks.",
   ["Rankine active coefficient Ka = (1 - sin phi) / (1 + sin phi) for level backfill.", "Check overturning, sliding, bearing pressure and the wall stem as a cantilever.", "Factors of safety of about 1.5 are common for overturning and sliding.",
    "Provide drainage behind the wall."],
   ["Pa = 0.5 Ka gamma H2", "Ka = (1 - sin phi) / (1 + sin phi)"], "IS 14458; IS456 Cl. 20", "retaining wall, earth pressure, Rankine, Coulomb")

# ----------------------------------------------------------------------- loads
_e("loads", "Dead loads (IS 875 Part 1)", "Self-weight of structure and permanent fixtures.",
   ["Reinforced concrete 25 kN/m3, plain concrete 24 kN/m3, structural steel 78.5 kN/m3, water 9.81 kN/m3.", "Brick masonry is about 19-20 kN/m3; add plaster and finishes.",
    "The calculator adds beam self-weight at 25 kN/m3; superimposed dead load is the user's input."],
   clause="IS 875 (Part 1):1987", tags="dead load, unit weight, density", impl=True)
_e("loads", "Imposed loads (IS 875 Part 2)", "Live loads depend on occupancy. Indicative floor values:",
   ["Residential rooms 2.0 kN/m2, offices 2.5 kN/m2, balconies 3.0 kN/m2, assembly areas 4-5 kN/m2, storage 5 kN/m2 and above.", "Live load reductions are allowed for tributary area on columns and walls.",
    "Roof loads depend on slope and access."],
   clause="IS 875 (Part 2):1987", tags="live load, imposed load, occupancy")
_e("loads", "Wind load (IS 875 Part 3)", "Wind pressure from the design wind speed.",
   ["Vz = Vb k1 k2 k3 k4: basic speed with risk, terrain/height, topography and importance factors.", "Pressure pz = 0.6 Vz2 (N/m2 with Vz in m/s).", "Design force = pressure x area x pressure coefficient (Cpe - Cpi)."],
   ["pz = 0.6 Vz2"], "IS 875 (Part 3):2015", "wind, Vz, pressure coefficient")
_e("loads", "Load path and tributary area", "Loads flow from slab to beam to column to foundation.",
   ["Two-way slab loads reach beams as triangles and trapezoids; for design they are converted to equivalent UDLs.", "Loads from one-way slabs reach the supporting beams as a UDL over half the slab span on each side."],
   tags="tributary area, load transfer, equivalent UDL")
_e("loads", "Load combinations for stability", "Factors of safety against overturning.",
   ["Take the restoring moment with 0.9 DL and the disturbing moment with 1.5 (wind or earthquake).", "Check that the foundation does not lift or slide."],
   clause="IS456 Cl. 20; Table 18", tags="overturning, stability, uplift")

# ---------------------------------------------------------------------- seismic
_e("seismic", "Seismic design force (IS 1893 Part 1)", "Design horizontal acceleration coefficient and base shear.",
   ["Zone factor Z: Zone II 0.10, III 0.16, IV 0.24, V 0.36.", "Importance factor I is 1.0 for ordinary and 1.2-1.5 for important or critical buildings.",
    "Response reduction factor R: 3 for ordinary moment resisting frames, 5 for special moment resisting frames."],
   ["Ah = (Z / 2)(I / R)(Sa / g)", "VB = Ah W", "Qi = VB Wi hi2 / sum(Wj hj2)"], "IS 1893 (Part 1):2016", "earthquake, base shear, zone factor, Ah")
_e("seismic", "Fundamental time period", "Empirical period of a building for the equivalent static method.",
   ["RC moment frame without infill: Ta = 0.075 h^0.75.", "Steel moment frame without infill: Ta = 0.085 h^0.75.", "With masonry infill: Ta = 0.09 h / sqrt(d)."],
   ["Ta = 0.075 h^0.75  (RC frame)"], "IS 1893 (Part 1):2016 Cl. 7.6", "time period, Ta, natural period")
_e("seismic", "Ductile detailing (IS 13920)", "Detailing that gives frames toughness in earthquakes.",
   ["Strong column, weak beam: column moment capacities exceed beam moments at a joint.", "Closely spaced closed ties with 135 degree hooks in confining zones near joints.", "Minimum Fe415/500 with tight limits on tension steel ratio; no lap splices in plastic hinge zones."],
   clause="IS 13920:2016", tags="ductile, earthquake, hinge, confinement")

# ----------------------------------------------------------------------- steel
_e("steel", "Structural steel properties", "Properties for IS 2062 structural steel.",
   ["E250 grade has yield strength 250 N/mm2; E350 has 350 N/mm2.", "Modulus of elasticity 2 x 10^5 N/mm2, density 78.5 kN/m3.", "Partial safety factors in IS 800:2007: gamma_m0 = 1.10 (yielding), gamma_m1 = 1.25 (ultimate)."],
   clause="IS 800:2007; IS 2062", tags="steel, E250, yield, IS 800")
_e("steel", "Section classification", "Local buckling limits the moment capacity of steel sections.",
   ["Plastic, compact, semi-compact and slender classes by width-to-thickness ratios.", "Plastic sections can reach plastic moment Zp fy; semi-compact reach elastic moment Ze fy."],
   clause="IS 800:2007 Table 2", tags="plastic, compact, slender, local buckling")
_e("steel", "Design strengths of steel members", "Basic capacity formulas for hot-rolled members.",
   ["Tension (yielding of gross section): Tdg = Ag fy / gamma_m0.", "Bending (laterally supported): Md = beta_b Zp fy / gamma_m0, limited to 1.2 Ze fy / gamma_m0.", "Shear: Vd = Av fyw / (sqrt(3) gamma_m0)."],
   ["Tdg = Ag fy / 1.10", "Md = beta_b Zp fy / 1.10"], "IS 800:2007 Cl. 6, 8, 9", "tension member, bending, shear, steel beam")
_e("steel", "Bolted and welded connections", "Joint design.",
   ["Bolt shear capacity depends on bolt grade, shear planes and thread location; bearing and block shear also govern.", "Fillet weld strength = throat thickness x length x fu / (sqrt(3) gamma_mw)."],
   clause="IS 800:2007 Cl. 10", tags="bolt, weld, connection")

# -------------------------------------------------------------------- analysis
_e("analysis", "Standard beam formulas", "Maximum moment, shear and deflection for common cases (EI constant).",
   ["Simply supported, UDL: M = wL2/8, V = wL/2, delta = 5wL4/(384EI).", "Simply supported, central point load: M = PL/4, delta = PL3/(48EI).",
    "Cantilever, UDL: M = wL2/2, V = wL, delta = wL4/(8EI).", "Cantilever, end point load: M = PL, delta = PL3/(3EI).", "Fixed both ends, UDL: end M = wL2/12, midspan wL2/24, delta = wL4/(384EI)."],
   ["M = wL2/8 (SS UDL)", "delta = 5 w L4 / (384 E I)"], tags="bending moment, deflection, UDL, point load, cantilever", impl=True)
_e("analysis", "Fixed-end moments", "Moments at the ends of a fully restrained member.",
   ["UDL: wL2/12.", "Central point load: PL/8.", "Point load at distance a from A: P a b2 / L2 at A and P a2 b / L2 at B."],
   ["FEM = wL2/12", "FEM = P a b2 / L2"], tags="FEM, slope deflection, moment distribution")
_e("analysis", "Slope deflection and moment distribution", "Hand methods for indeterminate beams and frames.",
   ["Slope deflection: end moments from rotations and sway.", "Moment distribution (Hardy Cross): distribute unbalanced moments by stiffness, carry over half."],
   ["MAB = FEMAB + (2EI/L)(2thetaA + thetaB - 3psi)"], tags="Hardy Cross, stiffness, carry over")
_e("analysis", "Degree of static indeterminacy", "Counting redundants.",
   ["Plane truss: m + r - 2j.", "Plane frame: 3m + r - 3j - releases.", "A structure is stable only if its reactions and members prevent rigid-body motion."],
   ["Ds = m + r - 2j (truss)", "Ds = 3m + r - 3j (frame)"], tags="determinate, indeterminate, truss, redundant")
_e("analysis", "Energy methods", "Deflections from work and energy.",
   ["Unit load method: delta = integral(M m / EI) dx.", "Castigliano: displacement = dU / dP.", "Maxwell-Betti reciprocal theorem: delta_ij = delta_ji."],
   ["delta = integral M m / (E I) dx"], tags="virtual work, Castigliano, unit load")
_e("analysis", "Influence lines", "Effect of a moving unit load.",
   ["Muller-Breslau: the influence line of a response has the shape of the deflected structure when that response is released.", "Used for bridge and crane girders."],
   tags="influence line, moving load, Muller-Breslau")
_e("analysis", "Section properties and stresses", "Basic mechanics of materials.",
   ["Rectangle: I = b h3 / 12, Z = b h2 / 6.", "Flexure: sigma = M y / I.", "Shear: tau = V Q / (I b); rectangle maximum is 1.5 times the average.", "Principal stresses from Mohr's circle."],
   ["I = b h3 / 12", "sigma = M y / I", "sigma1,2 = (sx + sy)/2 +/- sqrt(((sx - sy)/2)2 + txy2)"], tags="moment of inertia, section modulus, Mohr")
_e("analysis", "Euler buckling", "Elastic buckling load of a slender column.",
   ["Effective length factors: pinned-pinned 1.0, fixed-fixed 0.5, fixed-free 2.0, fixed-pinned 0.7.", "Slenderness ratio = effective length / radius of gyration."],
   ["Pcr = pi2 E I / Le2"], tags="buckling, slenderness, radius of gyration")
_e("analysis", "Truss analysis", "Axial forces in pin-jointed trusses.",
   ["Method of joints (two equilibrium equations per joint) and method of sections (cut through three members).", "Zero-force members can be identified at unloaded joints with two non-collinear members."],
   tags="truss, method of joints, method of sections")

# ------------------------------------------------------------------ durability
_e("durability", "Exposure conditions", "IS 456 classes by severity.",
   ["Mild: protected interior. Moderate: sheltered from rain, buried in non-aggressive soil, fresh water.", "Severe: rain-exposed, alternate wetting and drying, coastal.",
    "Very severe: sea spray, aggressive chemicals. Extreme: tidal zone, direct sea water contact."],
   clause="IS456 Cl. 8.2; Table 3", tags="exposure, mild, moderate, severe, marine", impl=True)
_e("durability", "Corrosion of reinforcement", "Main durability failure of reinforced concrete.",
   ["Carbonation lowers the pH around steel; chlorides break down the passive film.", "Rust occupies more volume than steel and cracks the cover.", "Prevention: low w/c, adequate cover, good compaction and curing, coatings, cathodic protection."],
   tags="corrosion, carbonation, chloride, rust")
_e("durability", "Acceptance of concrete", "Cube test criteria.",
   ["Each sample is three 150 mm cubes tested at 28 days; take the mean.", "Mean of any group of four consecutive samples must be at least fck + 0.825 s (and not less than fck + 3 N/mm2 where s is small).",
    "No individual sample should be below fck - 3 N/mm2."],
   clause="IS456 Cl. 16; Table 11", tags="cube test, acceptance, compressive strength")
_e("durability", "Non-destructive testing", "Assessing strength in existing structures.",
   ["Rebound hammer (surface hardness), ultrasonic pulse velocity (quality and voids), cover meter, half-cell potential (corrosion).", "Cores give the most direct strength estimate (IS 516 Part 5)."],
   clause="IS 13311; IS 516", tags="NDT, rebound hammer, UPV, core")

# ---------------------------------------------------------------- construction
_e("construction", "Curing", "Keeping concrete moist for hydration.",
   ["Cure at least 7 days for OPC and 10 days for concretes with mineral admixtures or in hot, dry weather.", "Methods: ponding, wet hessian, curing compounds, steam for precast."],
   clause="IS456 Cl. 13.5", tags="curing, hydration")
_e("construction", "Formwork stripping times", "Minimum periods before removal (OPC, normal temperatures).",
   ["Vertical formwork to columns, walls and beams: 16-24 hours.", "Slab soffit with props left under: 3 days.", "Beam soffit with props left under: 7 days.",
    "Props to slabs spanning up to 4.5 m: 7 days; over 4.5 m: 14 days.", "Props to beams spanning up to 6 m: 14 days; over 6 m: 21 days."],
   clause="IS456 Cl. 11.3", tags="formwork, shuttering, stripping")
_e("construction", "Placing and compaction", "Good concreting practice.",
   ["Limit free fall to about 1.5 m to avoid segregation.", "Compact with needle vibrators; avoid over-vibration.", "Plan construction joints at low-shear locations, roughen and clean before the next pour."],
   clause="IS456 Cl. 13", tags="placing, compaction, vibrator, cold joint")

# ----------------------------------------------------------------------- units
_e("units", "Force, stress and length conversions", "Common conversions used in design.",
   ["1 N/mm2 = 1 MPa = 1000 kN/m2.", "1 kgf = 9.80665 N; 1 tonne-force = 9.80665 kN.", "1 kip = 4.448 kN; 1 ksi = 6.895 MPa; 1 psi = 6.895 kPa.", "1 ft = 304.8 mm; 1 in = 25.4 mm.",
    "The calculator converts mm, cm, m, in, ft for lengths and kN/m, N/m, t/m, kgf/m, kip/ft and similar for line loads."],
   tags="units, MPa, kN, kip, tonne, conversion", impl=True)
_e("units", "Moment, area and section conversions", "Quick checks of orders of magnitude.",
   ["1 kN.m = 10^6 N.mm.", "Bar area = pi d2 / 4: 12 mm 113 mm2, 16 mm 201 mm2, 20 mm 314 mm2, 25 mm 491 mm2, 32 mm 804 mm2.", "Steel weight per metre = d2 / 162 kg."],
   ["w = d2 / 162  kg/m (d in mm)"], tags="bar area, weight of steel, kg per metre", impl=True)

# -------------------------------------------------------------------- standards
_e("standards", "Indian standards for concrete structures", "Main references for reinforced concrete design.",
   ["IS 456:2000 plain and reinforced concrete; SP 16 design aids; SP 34 detailing handbook.", "IS 1786 reinforcement bars; IS 383 aggregates; IS 269 / 1489 / 455 cement; IS 10262 mix design.",
    "IS 3370 liquid-retaining structures; IS 1343 prestressed concrete; IS 2911 pile foundations; IS 6403 bearing capacity."],
   clause="IS 456:2000", tags="IS 456, SP 16, SP 34, IS 1786, standards list")
_e("standards", "Indian standards for loads and steel", "Loading and steel design codes.",
   ["IS 875 Parts 1-5 loads; IS 1893 Part 1 earthquake; IS 13920 ductile detailing; IS 4326 earthquake-resistant construction.", "IS 800:2007 general construction in steel; IS 2062 structural steel; IS 801 / 811 cold-formed steel."],
   clause="IS 875; IS 1893; IS 800", tags="IS 875, IS 1893, IS 800")
_e("standards", "International codes", "Common non-Indian equivalents (not supported by this tool).",
   ["Eurocode 2 (EN 1992) for concrete, Eurocode 3 for steel, Eurocode 8 for seismic.", "ACI 318 for concrete, AISC 360 for steel, ASCE 7 for loads.", "BS 8110 is withdrawn in favour of Eurocodes."],
   tags="Eurocode, ACI, AISC, BS 8110")

# --------------------------------------------------------------------- glossary
for _t, _d in [
    ("Characteristic strength", "The value below which not more than 5% of test results are expected to fall."),
    ("Effective depth", "Distance from the extreme compression fibre to the centroid of the tension steel (d)."),
    ("Nominal cover", "Concrete thickness between the surface and the nearest reinforcement, including stirrups."),
    ("Neutral axis", "The line in a section where bending stress is zero; xu is its depth from the compression edge."),
    ("Under-reinforced section", "A section where tension steel yields before the concrete crushes, giving ductile failure."),
    ("Over-reinforced section", "A section where concrete crushes first; brittle and not allowed in design."),
    ("Balanced section", "A section where steel yields and concrete reaches its limiting strain at the same time."),
    ("Development length", "Embedded length needed to anchor a bar so it can reach its design stress."),
    ("Stirrup", "A closed link around the main bars that resists shear and confines concrete."),
    ("Hanger bar", "A small bar at the compression face that holds stirrups in position; not counted in flexure."),
    ("Creep", "Time-dependent increase of strain in concrete under sustained load."),
    ("Shrinkage", "Contraction of concrete as it dries, which can crack restrained members."),
    ("Modular ratio", "Ratio of the moduli of steel and concrete used in elastic analysis."),
    ("Lever arm", "Distance between the compressive and tensile resultants in a section (z)."),
    ("Camber", "An upward curvature built into a member to offset expected deflection."),
    ("Curtailment", "Stopping bars at the points where they are no longer required for flexure."),
    ("Bond", "Adhesion and friction between concrete and steel that transfer force between them."),
    ("Tributary area", "The area of floor whose load is carried by a given beam or column."),
]:
    _e("glossary", _t, _d, tags=_t.lower())

# ----------------------------------------------------------------------- ai
_e("ai", "Artificial neural networks", "Layers of weighted units trained by back-propagation to map inputs to outputs.",
   ["Supervised learning from examples; used to predict concrete strength, estimate damage and forecast cost.", "Course reference: Rajasekaran and Pai, chapters on supervised learning and back-propagation."],
   tags="ANN, backpropagation, neural network, strength prediction")
_e("ai", "Fuzzy logic", "Reasoning with degrees of truth instead of crisp true/false.",
   ["Membership functions, IF-THEN rules and defuzzification handle vague terms like 'high risk'.", "Used in condition assessment, risk ranking and decision support."],
   tags="fuzzy, membership, defuzzification, risk")
_e("ai", "Genetic algorithms", "Search by selection, crossover and mutation over a population of candidate designs.",
   ["Used for optimum section sizing, reinforcement layout and construction scheduling.", "The SDC-V explorer does a deterministic grid scan rather than a genetic search."],
   tags="GA, optimisation, crossover, mutation, population")
_e("ai", "Knowledge-based and expert systems", "Facts, rules and an inference engine hold expertise explicitly.",
   ["Forward chaining derives new facts from known ones; backward chaining works from a goal.", "Meta-rules control which rules apply and in what order.", "SDC-V is a rule-based system: see the Expert system tab for its facts, rules and meta-rules."],
   tags="KBS, expert system, inference, forward chaining, meta rules")
_e("ai", "Support vector machines", "Classifiers that find the maximum-margin boundary between classes.",
   ["Applied to crack classification and structural health monitoring.", "Kernels let SVMs separate non-linear data."],
   tags="SVM, classification, kernel")
_e("ai", "Guardrails for LLMs in engineering", "Constraining a language model so that it cannot introduce unverified numbers.",
   ["Extract with the model, compute with code, verify with rules, and reject narrative numbers not found in the result.", "Refuse approval, certification and safety-margin reductions; stamp every output as a draft."],
   tags="LLM, guardrail, hallucination, number trace", impl=True)


def kb_payload() -> dict:
    counts = {t: 0 for t, _ in TOPICS}
    for e in ENTRIES:
        counts[e["topic"]] += 1
    return {"topics": [{"id": t, "label": label, "count": counts[t]} for t, label in TOPICS],
            "entries": ENTRIES, "count": len(ENTRIES),
            "note": "Reference summaries of IS 456:2000, IS 875, IS 1893, IS 800 and standard mechanics. Verify against the printed code. Not a design approval."}
