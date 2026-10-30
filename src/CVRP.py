import glob
import hashlib
import json
import math
import os
import re
import sys
import time
import matplotlib
matplotlib.use("Agg")  # วาดรูปแบบไม่ต้องเปิดหน้าต่าง ใช้ได้ทุกเครื่อง (รวมถึงตอนรันใน Streamlit)
import matplotlib.pyplot as plt
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from ortools.sat.python import cp_model

# ค่า Optimal จากเอกสารอ้างอิง (literature) ใช้ตรวจเทียบกับค่าที่คำนวณเองเท่านั้น
BENCHMARK_OPTIMAL = {
    "A-n32-k5": 784,
    "B-n31-k5": 672,
    "P-n40-k5": 458
}

# โครงสร้างโฟลเดอร์ (อ้างอิงจากตำแหน่งไฟล์นี้ ย้ายไปเครื่องไหนก็ใช้ได้)
#   <โปรเจกต์>/src/      โค้ด (ไฟล์นี้อยู่ที่นี่)
#   <โปรเจกต์>/data/     ไฟล์โจทย์ .vrp
#   <โปรเจกต์>/results/  รูปเส้นทาง *_solution.png
#   <โปรเจกต์>/cache/    optimal_cache.json
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
for _folder in (DATA_DIR, RESULTS_DIR, CACHE_DIR):
    os.makedirs(_folder, exist_ok=True)

ALGORITHM_NAME = "OR-Tools (Path Cheapest Arc + Guided Local Search)"
EXACT_METHOD_NAME = "OR-Tools CP-SAT (exact model, proves optimality)"

# เก็บค่า Optimal ที่พิสูจน์แล้ว จะได้ไม่ต้องคำนวณซ้ำ (ผูกกับเนื้อหาไฟล์ ถ้าแก้ไฟล์จะคำนวณใหม่)
CACHE_FILE = os.path.join(CACHE_DIR, "optimal_cache.json")
DEFAULT_EXACT_TIME_LIMIT = 120  # วินาที


# =====================================================================
# 1) อ่านและตรวจไฟล์ .vrp
# =====================================================================
def _resolve(file_path):
    # ชื่อไฟล์เฉย ๆ -> หาในโฟลเดอร์ data ก่อน แล้วค่อยหาในโฟลเดอร์โปรเจกต์
    if not os.path.isabs(file_path) and not os.path.exists(file_path):
        for folder in (DATA_DIR, BASE_DIR):
            candidate = os.path.join(folder, file_path)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(DATA_DIR, file_path)
    return file_path


def parse_vrp_file(file_path):
    file_path = _resolve(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"ไม่พบไฟล์: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = [line.strip() for line in content.strip().split('\n') if line.strip()]

    capacity = 0
    dimension = 0
    num_vehicles = 5
    coords = {}
    demands = {}
    mode = None

    truck_match = re.search(r"No of trucks:\s*(\d+)", content, re.IGNORECASE)
    if truck_match:
        num_vehicles = int(truck_match.group(1))
    else:
        k_match = re.search(r"-k(\d+)", os.path.basename(file_path), re.IGNORECASE)
        if k_match:
            num_vehicles = int(k_match.group(1))

    for line in lines:
        if line.startswith("CAPACITY"):
            capacity = int(line.split(":")[1].strip())
        elif line.startswith("DIMENSION"):
            dimension = int(line.split(":")[1].strip())
        elif line.startswith("NODE_COORD_SECTION"):
            mode = "COORD"
            continue
        elif line.startswith("DEMAND_SECTION"):
            mode = "DEMAND"
            continue
        elif line.startswith("DEPOT_SECTION"):
            mode = "DEPOT"
            continue
        elif line.startswith("EOF"):
            break

        if mode == "COORD":
            parts = line.split()
            node_id = int(parts[0]) - 1
            coords[node_id] = (float(parts[1]), float(parts[2]))
        elif mode == "DEMAND":
            parts = line.split()
            node_id = int(parts[0]) - 1
            demands[node_id] = int(parts[1])

    return dimension, capacity, num_vehicles, coords, demands


def read_optimal_from_file(file_path):
    """อ่านค่า 'Optimal value: N' จากบรรทัด COMMENT (ถ้ามีและมากกว่า 0) ใช้เป็นค่าอ้างอิงเทียบ"""
    try:
        with open(_resolve(file_path), 'r', encoding='utf-8') as f:
            m = re.search(r"Optimal value:\s*([\d.]+)", f.read(), re.IGNORECASE)
        if m and float(m.group(1)) > 0:
            v = float(m.group(1))
            return int(v) if v.is_integer() else v
    except (OSError, ValueError):
        pass
    return None


def validate_vrp_file(file_path):
    """ตรวจ 'รูปแบบ' ไฟล์ .vrp คืนค่าเป็นรายการปัญหา (ว่าง = อ่านได้)
    หมายเหตุ: ความจุรถไม่พอ ไม่ถือว่ารูปแบบผิด แต่จะรายงานเป็น INFEASIBLE ตอนคำนวณ"""
    try:
        dimension, capacity, num_vehicles, coords, demands = parse_vrp_file(file_path)
    except Exception as e:
        return [f"อ่านไฟล์ไม่ได้: {e}"]
    problems = []
    if dimension <= 1:
        problems.append("ไม่พบ DIMENSION หรือจำนวนจุดน้อยเกินไป")
    if capacity <= 0:
        problems.append("ไม่พบ CAPACITY")
    if num_vehicles <= 0:
        problems.append("จำนวนรถต้องมากกว่า 0")
    expected = set(range(dimension))
    if set(coords) != expected:
        problems.append(f"NODE_COORD_SECTION ต้องมีจุด 1 ถึง {dimension} ครบ (พบ {len(coords)} จุด)")
    if set(demands) != expected:
        problems.append(f"DEMAND_SECTION ต้องมีจุด 1 ถึง {dimension} ครบ (พบ {len(demands)} จุด)")
    return problems


def check_capacity(dimension, capacity, num_vehicles, demands):
    """ตรวจเบื้องต้นว่าความจุรถพอหรือไม่ คืนข้อความเหตุผลถ้าไม่พอ (None = ผ่าน)"""
    too_big = [i + 1 for i in range(1, dimension) if demands[i] > capacity]
    if too_big:
        return f"จุด {too_big} มี demand มากกว่าความจุรถ ({capacity}) ส่งด้วยรถคันเดียวไม่ได้"
    total = sum(demands[i] for i in range(1, dimension))
    if total > capacity * num_vehicles:
        return (f"demand รวม {total} เกินความจุรถทั้งหมด {num_vehicles} คัน x {capacity} = "
                f"{capacity * num_vehicles}")
    return None


def build_distance_matrix(dimension, coords):
    # EUC_2D มาตรฐาน TSPLIB: ปัดระยะทางเป็นจำนวนเต็มที่ใกล้ที่สุด
    return [[int(round(math.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])))
             for j in range(dimension)] for i in range(dimension)]


def build_route_details(route_node_lists, dist, demands, capacity):
    """แปลงรายการเส้นทาง (เลขจุดแบบเริ่ม 1 มีคลังหัวท้าย) เป็นรายละเอียดสำหรับแสดงผล"""
    details = []
    for v, nodes in enumerate(route_node_lists, start=1):
        d = sum(dist[nodes[k] - 1][nodes[k + 1] - 1] for k in range(len(nodes) - 1))
        load = sum(demands[n - 1] for n in nodes[1:-1])
        details.append({
            "vehicle": v,
            "nodes": nodes,
            "path": " -> ".join(map(str, nodes)),
            "load": load,
            "capacity": capacity,
            "distance": d
        })
    return details


# =====================================================================
# 2) คำนวณค่า Optimal จริงด้วย CP-SAT (exact) + cache
# =====================================================================
def _file_hash(file_path):
    with open(_resolve(file_path), 'rb') as f:
        return hashlib.sha1(f.read().replace(b"\r\n", b"\n")).hexdigest()


def _load_cache():
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def compute_optimal(file_path, time_limit_sec=DEFAULT_EXACT_TIME_LIMIT, hint_routes=None, use_cache=True):
    """หาค่า Optimal ที่พิสูจน์ได้ทางคณิตศาสตร์ด้วย CP-SAT
    คืนค่า dict: status = OPTIMAL | FEASIBLE (หมดเวลาก่อนพิสูจน์ได้) | INFEASIBLE | UNKNOWN
                 value, bound (ขอบล่าง), routes, seconds, cached"""
    dimension, capacity, num_vehicles, coords, demands = parse_vrp_file(file_path)
    key = None
    if use_cache:
        key = _file_hash(file_path)
        hit = _load_cache().get(key)
        if hit:
            hit = dict(hit)
            hit["cached"] = True
            return hit

    reason = check_capacity(dimension, capacity, num_vehicles, demands)
    if reason:
        result = {"status": "INFEASIBLE", "value": None, "bound": None, "routes": [],
                  "seconds": 0.0, "reason": reason}
    else:
        dist = build_distance_matrix(dimension, coords)
        model = cp_model.CpModel()
        x = {}
        arcs = []
        for i in range(dimension):
            for j in range(dimension):
                if i == j:
                    continue
                if i and j and demands[i] + demands[j] > capacity:
                    continue  # สองจุดนี้อยู่รถคันเดียวกันไม่ได้อยู่แล้ว
                x[i, j] = model.NewBoolVar(f"x_{i}_{j}")
                arcs.append((i, j, x[i, j]))

        # ทุกลูกค้าถูกเยี่ยม 1 ครั้ง, ทุกเส้นทางเริ่ม-จบที่คลัง (node 0)
        model.AddMultipleCircuit(arcs)
        # ใช้รถได้ไม่เกินจำนวนที่กำหนด
        model.Add(sum(x[0, j] for j in range(1, dimension) if (0, j) in x) <= num_vehicles)
        # น้ำหนักสะสมบนรถ (กันไม่ให้เกินความจุ และกันวงย่อยที่ไม่ผ่านคลัง)
        load = [model.NewIntVar(demands[i] if i else 0, capacity if i else 0, f"u_{i}")
                for i in range(dimension)]
        for (i, j), var in x.items():
            if j:
                model.Add(load[j] >= load[i] + demands[j]).OnlyEnforceIf(var)
        model.Minimize(sum(dist[i][j] * var for (i, j), var in x.items()))

        # ใช้คำตอบจาก heuristic เป็นจุดเริ่มต้น ช่วยให้เร็วขึ้น
        if hint_routes:
            used = set()
            for nodes in hint_routes:
                for a, b in zip(nodes[:-1], nodes[1:]):
                    used.add((a - 1, b - 1))
            for (i, j), var in x.items():
                model.AddHint(var, 1 if (i, j) in used else 0)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_sec)
        solver.parameters.num_workers = max(8, os.cpu_count() or 8)
        t0 = time.time()
        status = solver.Solve(model)
        seconds = round(time.time() - t0, 1)

        routes = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            succ = {i: j for (i, j), var in x.items() if i and solver.Value(var)}
            for j in range(1, dimension):
                if (0, j) in x and solver.Value(x[0, j]):
                    nodes = [1, j + 1]
                    cur = j
                    while cur in succ and succ[cur] != 0:
                        cur = succ[cur]
                        nodes.append(cur + 1)
                    nodes.append(1)
                    routes.append(nodes)

        name = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
                cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")
        result = {
            "status": name,
            "value": int(solver.ObjectiveValue()) if routes else None,
            "bound": int(math.ceil(solver.BestObjectiveBound() - 1e-6)) if name != "INFEASIBLE" else None,
            "routes": routes,
            "seconds": seconds,
            "reason": "ไม่มีวิธีจัดของลงรถให้ครบภายในความจุและจำนวนรถที่กำหนด" if name == "INFEASIBLE" else None
        }

    # เก็บเฉพาะผลที่ 'สรุปได้แน่นอน' ลง cache
    if use_cache and key and result["status"] in ("OPTIMAL", "INFEASIBLE"):
        cache = _load_cache()
        cache[key] = dict(result, file=os.path.basename(file_path))
        _save_cache(cache)
    result["cached"] = False
    return result


# =====================================================================
# 3) วาดรูป
# =====================================================================
def plot_routes(instance_name, coords, routes, total_cost, optimal_cost, gap_text):
    """ฟังก์ชันวาดกราฟเส้นทางแยกสีตามคันรถและเซฟรูปไฟล์ PNG"""
    plt.figure(figsize=(10, 8))
    colors = ['#E63946', '#1D3557', '#2A9D8F', '#F4A261', '#9C89B8', '#457B9D', '#E76F51', '#A8DADC']

    # 1. พลอตตำแหน่ง Nodes ทั้งหมด
    all_x = [coords[i][0] for i in sorted(coords)]
    all_y = [coords[i][1] for i in sorted(coords)]
    plt.scatter(all_x[1:], all_y[1:], c='skyblue', s=120, edgecolors='black', zorder=3, label='Customers')

    for node_id, (x, y) in coords.items():
        if node_id != 0:
            plt.annotate(str(node_id + 1), (x, y), fontsize=9, ha='center', va='center', fontweight='bold', zorder=4)

    # 2. พลอต Depot (Node 1)
    depot_x, depot_y = coords[0]
    plt.scatter(depot_x, depot_y, c='red', s=250, marker='*', edgecolors='black', zorder=5, label='Depot (Node 1)')

    # 3. พลอตเส้นทางของรถแต่ละคัน
    for idx, r in enumerate(routes):
        color = colors[idx % len(colors)]
        node_seq = r['nodes']
        x_seq = [coords[n - 1][0] for n in node_seq]
        y_seq = [coords[n - 1][1] for n in node_seq]

        plt.plot(x_seq, y_seq, color=color, linewidth=2, linestyle='-', marker='o', markersize=4,
                 label=f"Vehicle {r['vehicle']} (Load: {r['load']}/{r['capacity']})", zorder=2)

    # 4. ตกแต่งกราฟ
    plt.title(f"CVRP Route Solution: {instance_name}\nTotal Cost: {total_cost} | "
              f"Optimal: {optimal_cost if optimal_cost is not None else 'N/A'} | Gap: {gap_text}",
              fontsize=12, fontweight='bold', pad=15)
    plt.xlabel("X Coordinate")
    plt.ylabel("Y Coordinate")
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=9)
    plt.grid(True, linestyle='--', alpha=0.5)

    output_filename = os.path.join(RESULTS_DIR, f"{instance_name}_solution.png")
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    plt.close()
    print(f" Saved route plot to: {output_filename}")


# =====================================================================
# 4) Solver หลัก (heuristic) + เทียบกับค่า Optimal
# =====================================================================
def _run_heuristic(dimension, capacity, num_vehicles, demands, dist, time_limit_sec):
    manager = pywrapcp.RoutingIndexManager(dimension, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return dist[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def demand_callback(from_index):
        return demands[manager.IndexToNode(from_index)]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, [capacity] * num_vehicles, True, 'Capacity')

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = int(time_limit_sec)

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return None
    routes = []
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        nodes = []
        while not routing.IsEnd(index):
            nodes.append(manager.IndexToNode(index) + 1)
            index = solution.Value(routing.NextVar(index))
        nodes.append(manager.IndexToNode(index) + 1)
        if len(nodes) > 2:
            routes.append(nodes)
    return routes


def format_gap(res):
    if res.get("gap") is None:
        return "N/A"
    return ("<= " if res.get("gap_is_upper_bound") else "") + f"{res['gap']:.2f}%"


def solve_single_vrp(file_path, time_limit_sec=5, exact_time_limit_sec=DEFAULT_EXACT_TIME_LIMIT,
                     compute_exact=True):
    file_path = _resolve(file_path)
    dimension, capacity, num_vehicles, coords, demands = parse_vrp_file(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    literature = BENCHMARK_OPTIMAL.get(base_name) or read_optimal_from_file(file_path)
    dist = build_distance_matrix(dimension, coords)

    res = {
        "instance_name": base_name,
        "file_name": os.path.basename(file_path),
        "num_vehicles": num_vehicles,
        "capacity": capacity,
        "total_cost": None,
        "routes": [],
        "solution_source": ALGORITHM_NAME,
        "optimal_cost": None,
        "optimal_status": None,
        "optimal_source": None,
        "lower_bound": None,
        "optimal_routes": [],
        "exact_seconds": None,
        "exact_cached": False,
        "literature_optimal": literature,
        "gap": None,
        "gap_is_upper_bound": False,
        "feasible": False,
        "infeasible_reason": None,
        "image_path": os.path.join(RESULTS_DIR, f"{base_name}_solution.png"),
    }

    # --- 0) ความจุรถไม่พอแน่นอน -> INFEASIBLE ทันที ---
    reason = check_capacity(dimension, capacity, num_vehicles, demands)
    if reason:
        res.update(optimal_status="INFEASIBLE", infeasible_reason=reason)
        return res

    # --- 1) Solver หลัก (heuristic) ---
    heur_routes = _run_heuristic(dimension, capacity, num_vehicles, demands, dist, time_limit_sec)

    # --- 2) ค่า Optimal ที่พิสูจน์ได้ (exact) ---
    exact = None
    if compute_exact:
        exact = compute_optimal(file_path, exact_time_limit_sec, hint_routes=heur_routes)
        res["exact_seconds"] = exact["seconds"]
        res["exact_cached"] = exact.get("cached", False)
        res["optimal_status"] = exact["status"]
        res["lower_bound"] = exact["bound"]
        res["optimal_routes"] = build_route_details(exact["routes"], dist, demands, capacity)

        if exact["status"] == "INFEASIBLE":
            res["infeasible_reason"] = exact.get("reason")
            return res
        if exact["status"] == "OPTIMAL":
            res["optimal_cost"] = exact["value"]
            res["optimal_source"] = "Proven optimal (CP-SAT)"

    if res["optimal_cost"] is None and literature:
        res["optimal_cost"] = literature
        res["optimal_source"] = "Literature / COMMENT"

    # --- 3) ถ้า heuristic หาไม่ได้ ใช้คำตอบจาก exact แทน ---
    if heur_routes is None and exact and exact["routes"]:
        heur_routes = exact["routes"]
        res["solution_source"] = EXACT_METHOD_NAME
    if heur_routes is None:
        res["infeasible_reason"] = "หาเส้นทางไม่ได้ภายในเวลาที่กำหนด ลองเพิ่ม Time Limit"
        return res

    routes_detail = build_route_details(heur_routes, dist, demands, capacity)
    total = sum(r["distance"] for r in routes_detail)
    visited = {n for r in routes_detail for n in r["nodes"][1:-1]}
    res.update(
        routes=routes_detail,
        total_cost=total,
        feasible=(len(visited) == dimension - 1) and all(r["load"] <= capacity for r in routes_detail),
    )

    # --- 4) Gap ---
    if res["optimal_cost"]:
        res["gap"] = (total - res["optimal_cost"]) / res["optimal_cost"] * 100
    elif res["lower_bound"]:
        res["gap"] = (total - res["lower_bound"]) / res["lower_bound"] * 100
        res["gap_is_upper_bound"] = True

    plot_routes(base_name, coords, routes_detail, total,
                res["optimal_cost"] if res["optimal_cost"] else res["lower_bound"] and f">= {res['lower_bound']}",
                format_gap(res))
    return res


# =====================================================================
# 5) รันทุกไฟล์ในโฟลเดอร์ (python CVRP.py [เวลาพิสูจน์ Optimal วินาที])
# =====================================================================
def describe_optimal(res):
    st = res["optimal_status"]
    if st == "INFEASIBLE":
        return f"INFEASIBLE - {res['infeasible_reason']}"
    if res["optimal_cost"]:
        extra = ""
        if res["optimal_source"].startswith("Proven"):
            extra = " (cached)" if res["exact_cached"] else f" ({res['exact_seconds']}s)"
            lit = res["literature_optimal"]
            if lit and lit != res["optimal_cost"]:
                extra += f"  [!] ต่างจากค่าอ้างอิง {lit}"
        return f"{res['optimal_cost']}  [{res['optimal_source']}{extra}]"
    if res["lower_bound"]:
        return f">= {res['lower_bound']}  [พิสูจน์ไม่ทันเวลา ได้แค่ขอบล่าง]"
    return "N/A"


def print_result_card(res):
    print("\n" + "=" * 70)
    print(f" RESULT CARD : {res['instance_name']} ({res['file_name']})")
    print("=" * 70)
    print(f" 1. Benchmark / Instance : {res['instance_name']}")
    print(f" 2. Algorithm / Approach  : {res['solution_source']}")
    print(" 3. Route Solution        :")
    for r in res['routes']:
        print(f"    - Route {r['vehicle']}: {r['path']}")
        print(f"      [Load: {r['load']}/{r['capacity']} | Distance: {r['distance']}]")
    print(f" 4. Total Distance / Cost : {res['total_cost'] if res['total_cost'] is not None else 'N/A'}")
    print(f" 5. Optimal Value         : {describe_optimal(res)}")
    print(f" 6. Gap from Optimal      : {format_gap(res)}")
    print(f" 7. Feasibility Status    : {'YES (FEASIBLE)' if res['feasible'] else 'NO (INFEASIBLE)'}")
    if res["infeasible_reason"]:
        print(f"    เหตุผล: {res['infeasible_reason']}")
    print("=" * 70)


def main():
    exact_limit = DEFAULT_EXACT_TIME_LIMIT
    if len(sys.argv) > 1:
        try:
            exact_limit = float(sys.argv[1])
        except ValueError:
            pass

    # รันทุกไฟล์ .vrp ในโฟลเดอร์ data อัตโนมัติ (เพิ่มไฟล์ใหม่ก็รันให้เลย)
    files_to_solve = sorted(glob.glob(os.path.join(DATA_DIR, "*.vrp")))
    if not files_to_solve:
        print(f"ไม่พบไฟล์ .vrp ในโฟลเดอร์ {DATA_DIR}")
        return
    print(f"พบ {len(files_to_solve)} ไฟล์ | คำนวณค่า Optimal ด้วย CP-SAT (สูงสุด {exact_limit:g} วินาที/ไฟล์, "
          f"ไฟล์ที่เคยพิสูจน์แล้วจะดึงจาก cache)")

    summary_results = []
    for file_path in files_to_solve:
        problems = validate_vrp_file(file_path)
        if problems:
            print(f"\n[SKIP] {os.path.basename(file_path)} รูปแบบไฟล์ไม่ถูกต้อง:")
            for p in problems:
                print(f"   - {p}")
            continue
        try:
            print(f"\n... กำลังคำนวณ {os.path.basename(file_path)}", flush=True)
            res = solve_single_vrp(file_path, exact_time_limit_sec=exact_limit)
            print_result_card(res)
            summary_results.append(res)
        except Exception as e:
            print(f"\n[ERROR] ไม่สามารถประมวลผลไฟล์ {file_path}: {e}")

    if summary_results:
        print("\n" + "█" * 78)
        print(f" OVERALL BENCHMARK COMPARISON SUMMARY ({len(summary_results)} INSTANCES)")
        print("█" * 78)
        print(f"{'Instance':<26} | {'Cost':<7} | {'Optimal':<9} | {'Gap (%)':<10} | {'Feasible'}")
        print("-" * 78)

        gaps = []
        for s in summary_results:
            status = "YES" if s["feasible"] else "NO"
            cost = s['total_cost'] if s['total_cost'] is not None else 'N/A'
            if s["optimal_status"] == "INFEASIBLE":
                opt = "INFEAS."
            elif s["optimal_cost"]:
                opt = s["optimal_cost"]
            elif s["lower_bound"]:
                opt = f">={s['lower_bound']}"
            else:
                opt = "N/A"
            print(f"{s['instance_name']:<26} | {cost:<7} | {opt:<9} | {format_gap(s):<10} | {status}")
            if s["gap"] is not None and not s["gap_is_upper_bound"]:
                gaps.append(s["gap"])

        print("-" * 78)
        if gaps:
            print(f"Average Optimality Gap: {sum(gaps) / len(gaps):.2f}%  (จาก {len(gaps)} ไฟล์ที่ทราบค่า Optimal)\n")


if __name__ == '__main__':
    main()
