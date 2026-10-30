import os
import re
import glob
import tempfile
import streamlit as st
from CVRP import solve_single_vrp, validate_vrp_file, format_gap, DEFAULT_EXACT_TIME_LIMIT, DATA_DIR

st.set_page_config(page_title="CVRP Fleet Optimizer", layout="wide")

st.title("🚛 CVRP Logistics Fleet Optimizer")
st.subheader("One-Solver Benchmark Evaluation Dashboard")

# ไฟล์ .vrp อยู่ในโฟลเดอร์ data ข้าง ๆ app.py เสมอ ย้ายไปเครื่องไหนก็หาไฟล์เจอ
folder_path = DATA_DIR

TEMPLATE_VRP = """NAME : my-case
COMMENT : (My case, No of trucks: 3, Optimal value: 0)
TYPE : CVRP
DIMENSION : 6
EDGE_WEIGHT_TYPE : EUC_2D
CAPACITY : 100
NODE_COORD_SECTION
 1 50 50
 2 20 80
 3 70 90
 4 85 30
 5 30 20
 6 60 10
DEMAND_SECTION
 1 0
 2 30
 3 25
 4 40
 5 20
 6 35
DEPOT_SECTION
 1
 -1
EOF
"""

# ---------------------------------------------------------------
# 0. เพิ่มไฟล์ .vrp ใหม่จากหน้าเว็บ
# ---------------------------------------------------------------
with st.sidebar.expander("➕ เพิ่มไฟล์ .vrp ใหม่", expanded=False):
    uploaded = st.file_uploader("อัปโหลดไฟล์ .vrp", type=["vrp"], key="vrp_upload")
    st.caption("จุดที่ 1 = คลังสินค้า (demand 0) · ใส่ 'No of trucks: N' และ "
               "'Optimal value: N' (ถ้ารู้) ในบรรทัด COMMENT")
    st.download_button("⬇️ ดาวน์โหลดไฟล์ตัวอย่าง (template.vrp)", TEMPLATE_VRP,
                       file_name="template.vrp", mime="text/plain")

    if uploaded is not None:
        # ตั้งชื่อไฟล์ให้ปลอดภัย (ตัวอักษรอังกฤษ ตัวเลข . และ - เท่านั้น)
        safe_name = re.sub(r"[^A-Za-z0-9.\-]+", "-", os.path.basename(uploaded.name)).strip("-")
        if not safe_name.lower().endswith(".vrp"):
            safe_name += ".vrp"
        data = uploaded.getvalue()

        # ตรวจไฟล์ก่อนบันทึก
        with tempfile.NamedTemporaryFile("wb", suffix="-" + safe_name, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            problems = validate_vrp_file(tmp_path)
        finally:
            os.remove(tmp_path)

        if problems:
            st.error("ไฟล์ยังใช้ไม่ได้:\n\n" + "\n".join(f"- {p}" for p in problems))
        else:
            dest = os.path.join(folder_path, safe_name)
            with open(dest, "wb") as f:
                f.write(data)
            # เลือกไฟล์ที่เพิ่งอัปโหลดให้อัตโนมัติ (ครั้งเดียวต่อการอัปโหลด)
            if st.session_state.get("last_saved") != (safe_name, len(data)):
                st.session_state["last_saved"] = (safe_name, len(data))
                st.session_state["selected_vrp"] = safe_name
            st.success(f"บันทึก {safe_name} ลงโฟลเดอร์แล้ว")

# ---------------------------------------------------------------
# 1. ดึงรายชื่อไฟล์ .vrp ทั้งหมดที่มีอยู่ในโฟลเดอร์อัตโนมัติ
# ---------------------------------------------------------------
vrp_files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(folder_path, "*.vrp")))

if not vrp_files:
    st.error(f"ไม่พบไฟล์ .vrp ในโฟลเดอร์ {folder_path}")
else:
    if st.session_state.get("selected_vrp") not in vrp_files:
        st.session_state["selected_vrp"] = vrp_files[0]
    selected_file_name = st.sidebar.selectbox("เลือกไฟล์ Benchmark (.vrp)", vrp_files, key="selected_vrp")
    full_file_path = os.path.join(folder_path, selected_file_name)

    time_limit = st.sidebar.slider("Time Limit ของ Solver (วินาที)", 1, 30, 5)
    exact_limit = st.sidebar.slider("เวลาสูงสุดในการพิสูจน์ค่า Optimal (วินาที)", 10, 600,
                                    DEFAULT_EXACT_TIME_LIMIT, step=10,
                                    help="คำนวณค่า Optimal จริงด้วย CP-SAT ไฟล์ที่เคยพิสูจน์แล้วจะดึงผลเดิมทันที")

    if st.sidebar.button("🚀 Run Solver Optimization", type="primary"):
        problems = validate_vrp_file(full_file_path)
        if problems:
            st.error(f"{selected_file_name} รูปแบบไฟล์ไม่ถูกต้อง:\n\n" + "\n".join(f"- {p}" for p in problems))
            st.stop()

        with st.spinner("กำลังคำนวณเส้นทาง และพิสูจน์ค่า Optimal ด้วย CP-SAT (ไฟล์ใหญ่อาจใช้เวลาเป็นนาที)..."):
            res = solve_single_vrp(full_file_path, time_limit_sec=time_limit, exact_time_limit_sec=exact_limit)

        # ค่า Optimal
        if res["optimal_status"] == "INFEASIBLE":
            opt_text, opt_help = "INFEASIBLE", res["infeasible_reason"]
        elif res["optimal_cost"]:
            opt_text = str(res["optimal_cost"])
            if (res["optimal_source"] or "").startswith("Proven"):
                opt_help = "พิสูจน์แล้วด้วย CP-SAT ว่าเป็นค่าที่ดีที่สุด" + (
                    " (ดึงจากผลที่เคยคำนวณไว้)" if res["exact_cached"] else f" ใช้เวลา {res['exact_seconds']} วินาที")
            else:
                opt_help = "ค่าอ้างอิงจาก literature / COMMENT (CP-SAT พิสูจน์ไม่ทันเวลา)"
        elif res["lower_bound"]:
            opt_text = f"≥ {res['lower_bound']}"
            opt_help = "พิสูจน์ไม่ทันเวลา ได้แค่ขอบล่าง เพิ่มเวลาพิสูจน์ค่า Optimal แล้วรันใหม่"
        else:
            opt_text, opt_help = "N/A", "เพิ่มเวลาพิสูจน์ค่า Optimal แล้วรันใหม่"

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Cost / Distance", res["total_cost"] if res["total_cost"] is not None else "N/A")
        col2.metric("Optimal Cost", opt_text, help=opt_help)
        col3.metric("Optimality Gap", format_gap(res).replace("<= ", "≤ "))
        col4.metric("Status", "FEASIBLE" if res["feasible"] else "INFEASIBLE")

        if res["infeasible_reason"]:
            st.error(f"INFEASIBLE: {res['infeasible_reason']}")
        elif res["optimal_cost"] and (res["optimal_source"] or "").startswith("Proven"):
            st.caption(f"✅ {opt_help}")
            lit = res["literature_optimal"]
            if lit and lit != res["optimal_cost"]:
                st.warning(f"ค่าที่พิสูจน์ได้ ({res['optimal_cost']}) ต่างจากค่าอ้างอิงในไฟล์ ({lit})")
        elif opt_text.startswith("≥") or opt_text == "N/A":
            st.warning(opt_help)

        if res["routes"]:
            # แสดงรายละเอียดเส้นทาง
            st.write(f"### 📌 Route Solutions ({len(res['routes'])} / {res['num_vehicles']} vehicles used)")
            if res["solution_source"] != "OR-Tools (Path Cheapest Arc + Guided Local Search)":
                st.caption(f"Solver หลักหาไม่ได้ ใช้เส้นทางจาก {res['solution_source']}")
            for r in res["routes"]:
                st.success(f"**Vehicle {r['vehicle']}** (Load: {r['load']}/{r['capacity']} | Dist: {r['distance']}) : {r['path']}")

            if res["optimal_routes"] and res["gap"] and not res["gap_is_upper_bound"] and res["gap"] > 0:
                with st.expander(f"🏆 ดูเส้นทางที่ดีที่สุด (Optimal = {res['optimal_cost']})"):
                    for r in res["optimal_routes"]:
                        st.info(f"**Vehicle {r['vehicle']}** (Load: {r['load']}/{r['capacity']} | Dist: {r['distance']}) : {r['path']}")

            # แสดงภาพแผนที่
            img_path = res.get("image_path")
            if img_path and os.path.exists(img_path):
                st.write("### 🗺️ Route Visualization Map")
                st.image(img_path)
