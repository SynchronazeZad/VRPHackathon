# CVRP Logistics Fleet Optimizer — Submission Package

โปรเจกต์สำหรับแก้ปัญหา **Capacitated Vehicle Routing Problem (CVRP)** โดยใช้ OR-Tools และแสดงผลผ่าน Streamlit

> **Submission note:** ZIP นี้ตั้งใจให้กรรมการสามารถแตกไฟล์แล้วติดตั้ง dependencies และรันได้โดยไม่ต้องส่ง `.venv`, `node_modules` หรือข้อมูลลับใด ๆ

---

## 1. Environment / Library Versions

### Recommended environment
- **Python:** 3.11.x (Python 3.10–3.12 expected)
- **OS:** Windows 10/11, macOS หรือ Linux
- Internet connection: ใช้เฉพาะครั้งแรกสำหรับติดตั้ง Python packages

### Python libraries
Dependencies ถูก pin version ใน `requirements.txt` เพื่อให้ environment reproducible:

| Library | Version |
|---|---:|
| `ortools` | `9.10.4067` |
| `matplotlib` | `3.8.4` |
| `streamlit` | `1.39.0` |

ติดตั้งด้วย:

```bash
python -m pip install -r requirements.txt
```

> `.venv` ไม่ได้รวมอยู่ใน ZIP โดยตั้งใจ ให้สร้างใหม่บนเครื่องกรรมการเพื่อป้องกันปัญหา virtual environment ที่ผูกกับเครื่องเดิม

---

## 2. Project Structure

```text
VRPHackathon/
├── src/
│   ├── CVRP.py                    # CVRP solver + exact optimality check + visualization
│   └── app.py                     # Streamlit web application
├── data/
│   ├── A-n32-k5.vrp
│   ├── B-n31-k5.vrp
│   ├── P-n40-k5.vrp
│   ├── QC-Sample-Pickup-n13-k3.vrp
│   └── Lab-Specimen-Pickup-n21-k4.vrp
├── results/
│   ├── A-n32-k5_solution.png
│   ├── B-n31-k5_solution.png
│   ├── P-n40-k5_solution.png
│   ├── QC-Sample-Pickup-n13-k3_solution.png
│   └── Lab-Specimen-Pickup-n21-k4_solution.png
├── cache/
│   └── optimal_cache.json          # ค่า optimal ที่พิสูจน์แล้วสำหรับ benchmark ที่แนบมา
├── requirements.txt
├── setup_env.bat                   # Windows: สร้าง .venv และติดตั้ง packages
├── run_app.bat                     # Windows: เปิด Streamlit
├── run_benchmark.bat               # Windows: รัน benchmark ทั้งหมด
├── run.sh                           # macOS/Linux
├── Hackathon.code-workspace
├── .gitignore
└── README.md
```

---

## 3. วิธีรัน

### Windows — วิธีง่ายที่สุด

ดับเบิลคลิก:

```text
run_app.bat
```

จากนั้นเปิด:

```text
http://localhost:8501
```

สำหรับรัน benchmark ทั้งหมดโดยไม่เปิดหน้าเว็บ:

```text
run_benchmark.bat
```

ไฟล์ `.bat` จะเรียก `setup_env.bat` เพื่อสร้าง `.venv` และติดตั้ง dependencies ให้อัตโนมัติ

### macOS / Linux

```bash
chmod +x run.sh
./run.sh
```

เปิด benchmark ทั้งหมด:

```bash
./run.sh benchmark
```

### Command line โดยตรง

เปิดเว็บ:

```bash
python -m streamlit run src/app.py
```

รัน benchmark:

```bash
python src/CVRP.py
```

กำหนดเวลาสูงสุดสำหรับการพิสูจน์ optimal ต่อ instance:

```bash
python src/CVRP.py 120
```

---

## 4. Routes / Solver Parameters

### Main heuristic solver

ใช้ OR-Tools Routing Solver โดยกำหนด:

| Parameter | Value |
|---|---|
| First solution strategy | `PATH_CHEAPEST_ARC` |
| Local search metaheuristic | `GUIDED_LOCAL_SEARCH` |
| Default heuristic time limit | **5 seconds / instance** |
| Distance metric | `EUC_2D` |
| Distance calculation | Euclidean distance แล้วปัดเป็น integer ด้วย `round()` |
| Depot | Node `1` |
| Vehicle capacity | อ่านจาก `.vrp` |
| Number of vehicles | อ่านจาก `No of trucks: N` หรือ `-kN` จากชื่อไฟล์ |

### Exact optimality check

หลังจากหา heuristic solution โปรแกรมใช้ OR-Tools CP-SAT เพื่อพยายามพิสูจน์ค่า optimal:

| Parameter | Value |
|---|---|
| Method | OR-Tools CP-SAT |
| Default exact time limit | **120 seconds / instance** |
| CP-SAT workers | `max(8, os.cpu_count())` |
| Heuristic solution | ใช้เป็น CP-SAT hint เมื่อมี |
| Cache | เปิดใช้งาน |
| Cache key | SHA-1 ของไฟล์ `.vrp` หลัง normalize line endings |

ถ้าพิสูจน์ได้ โปรแกรมแสดง `OPTIMAL`; ถ้าเวลาหมดก่อนพิสูจน์ จะรายงานค่า solution และ lower bound แทน

---

## 5. Random Seed

**โปรเจกต์นี้ไม่ได้กำหนดหรือใช้ random seed แบบ explicit** (`random.seed()` / `numpy.random.seed()` ไม่มีในโค้ด)

ดังนั้น:

```text
Random seed: N/A — no explicit random seed is used.
```

สำหรับ benchmark ที่แนบมา `cache/optimal_cache.json` เก็บผล optimal ที่พิสูจน์แล้วไว้แล้ว จึงสามารถแสดงผลเดิมได้โดยไม่ต้องคำนวณ exact model ซ้ำ

> หมายเหตุ: หากลบ cache แล้วรัน solver ใหม่บนเครื่อง/จำนวน CPU ต่างกัน ลำดับ route ที่ heuristic หรือ CP-SAT หาได้อาจแตกต่างกันได้ แม้ objective/optimal cost จะเท่ากัน

---

## 6. Routes และผลรันที่ใช้เป็นหลักฐาน

ผลด้านล่างตรงกับ benchmark results ที่แนบไว้ใน `results/`

### A-n32-k5

- Vehicles: 5
- Capacity: 100
- **Total Cost: 784**
- **Optimal: 784**
- **Gap: 0.00%**
- Status: FEASIBLE

Routes:

```text
Vehicle 1: 1 -> 15 -> 29 -> 12 -> 5 -> 24 -> 4 -> 3 -> 7 -> 1
Vehicle 2: 1 -> 21 -> 6 -> 26 -> 11 -> 16 -> 23 -> 10 -> 9 -> 19 -> 30 -> 1
Vehicle 3: 1 -> 27 -> 8 -> 14 -> 18 -> 20 -> 32 -> 22 -> 1
Vehicle 4: 1 -> 28 -> 25 -> 1
Vehicle 5: 1 -> 31 -> 17 -> 2 -> 13 -> 1
```

Route loads:

```text
V1 = 98 / 100
V2 = 98 / 100
V3 = 98 / 100
V4 = 44 / 100
V5 = 72 / 100
```

Evidence:

```text
results/A-n32-k5_solution.png
```

---

### B-n31-k5

- Vehicles: 5
- Capacity: 100
- **Total Cost: 672**
- **Optimal: 672**
- **Gap: 0.00%**
- Status: FEASIBLE

Routes:

```text
Vehicle 1: 1 -> 4 -> 2 -> 20 -> 25 -> 12 -> 16 -> 15 -> 1
Vehicle 2: 1 -> 21 -> 28 -> 11 -> 3 -> 1
Vehicle 3: 1 -> 22 -> 17 -> 19 -> 26 -> 6 -> 5 -> 30 -> 1
Vehicle 4: 1 -> 23 -> 7 -> 10 -> 18 -> 14 -> 8 -> 1
Vehicle 5: 1 -> 27 -> 29 -> 13 -> 9 -> 24 -> 31 -> 1
```

Route loads:

```text
V1 = 95 / 100
V2 = 38 / 100
V3 = 86 / 100
V4 = 96 / 100
V5 = 97 / 100
```

Evidence:

```text
results/B-n31-k5_solution.png
```

---

### P-n40-k5

- Vehicles: 5
- Capacity: 140
- **Total Cost: 458**
- **Optimal: 458**
- **Gap: 0.00%**
- Status: FEASIBLE

Routes:

```text
Vehicle 1: 1 -> 6 -> 11 -> 40 -> 34 -> 16 -> 38 -> 18 -> 13 -> 1
Vehicle 2: 1 -> 7 -> 25 -> 24 -> 8 -> 27 -> 32 -> 9 -> 28 -> 1
Vehicle 3: 1 -> 12 -> 17 -> 30 -> 22 -> 35 -> 31 -> 10 -> 39 -> 1
Vehicle 4: 1 -> 19 -> 5 -> 20 -> 14 -> 26 -> 15 -> 1
Vehicle 5: 1 -> 33 -> 3 -> 21 -> 36 -> 37 -> 4 -> 29 -> 23 -> 2 -> 1
```

Route loads:

```text
V1 = 114 / 140
V2 = 116 / 140
V3 = 119 / 140
V4 = 131 / 140
V5 = 138 / 140
```

Evidence:

```text
results/P-n40-k5_solution.png
```

---

### QC-Sample-Pickup-n13-k3

- Vehicles: 3
- Capacity: 40
- **Total Cost: 254**
- **Optimal: 254**
- **Gap: 0.00%**
- Status: FEASIBLE

Routes:

```text
Vehicle 1: 1 -> 2 -> 3 -> 4 -> 5 -> 1
Vehicle 2: 1 -> 6 -> 7 -> 8 -> 1
Vehicle 3: 1 -> 9 -> 10 -> 11 -> 12 -> 13 -> 1
```

Route loads:

```text
V1 = 35 / 40
V2 = 27 / 40
V3 = 38 / 40
```

Evidence:

```text
results/QC-Sample-Pickup-n13-k3_solution.png
```

---

### Lab-Specimen-Pickup-n21-k4

- Vehicles: 4
- Capacity: 40
- **Total Cost: 408**
- **Optimal: 408**
- **Gap: 0.00%**
- Status: FEASIBLE

Routes:

```text
Vehicle 1: 1 -> 5 -> 21 -> 6 -> 8 -> 7 -> 1
Vehicle 2: 1 -> 9 -> 10 -> 11 -> 12 -> 20 -> 1
Vehicle 3: 1 -> 13 -> 14 -> 15 -> 16 -> 19 -> 1
Vehicle 4: 1 -> 17 -> 18 -> 4 -> 3 -> 2 -> 1
```

Route loads:

```text
V1 = 39 / 40
V2 = 38 / 40
V3 = 29 / 40
V4 = 39 / 40
```

Evidence:

```text
results/Lab-Specimen-Pickup-n21-k4_solution.png
```

---

## 7. Benchmark Summary

| Instance | Vehicles | Capacity | Total Cost | Optimal | Gap |
|---|---:|---:|---:|---:|---:|
| A-n32-k5 | 5 | 100 | **784** | **784** | **0.00%** |
| B-n31-k5 | 5 | 100 | **672** | **672** | **0.00%** |
| P-n40-k5 | 5 | 140 | **458** | **458** | **0.00%** |
| QC-Sample-Pickup-n13-k3 | 3 | 40 | **254** | **254** | **0.00%** |
| Lab-Specimen-Pickup-n21-k4 | 4 | 40 | **408** | **408** | **0.00%** |

---

## 8. Input `.vrp` Format

แต่ละไฟล์ต้องมี:

```text
DIMENSION
CAPACITY
NODE_COORD_SECTION
DEMAND_SECTION
DEPOT_SECTION
EOF
```

จุด `1` คือ depot และจำนวนรถสามารถระบุใน `COMMENT` เช่น:

```text
COMMENT : No of trucks: 5
```

หรือใช้ `-k5` ในชื่อไฟล์

ตัวอย่าง:

```text
A-n32-k5.vrp
```

---

## 9. สิ่งที่ไม่รวมใน ZIP

เพื่อให้ package สะอาดและ reproducible ZIP นี้ **ไม่รวม**:

- `.venv/`
- `node_modules/`
- API keys
- passwords
- tokens
- `.env` / secret configuration
- cache ของ package manager หรือไฟล์ที่ผูกกับเครื่องผู้พัฒนา

ผู้ตรวจสามารถสร้าง environment ใหม่ได้จาก `requirements.txt`

---

## 10. Quick Start

### Windows

```text
1. แตก ZIP
2. ดับเบิลคลิก run_app.bat
3. เปิด http://localhost:8501
4. เลือก benchmark ใน sidebar
5. กด Run Solver Optimization
```

### macOS / Linux

```bash
cd VRPHackathon
chmod +x run.sh
./run.sh
```

สำหรับ benchmark:

```bash
./run.sh benchmark
```

