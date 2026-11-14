"""包装节拍对照实验：异方差 Welch t 与按工位配对 t 分析。"""
import math
import random
import numpy as np
from scipy import stats

STATION_KEY = "station"
STATION_LABEL = "工位"
MODE_WELCH = "welch"
MODE_PAIRED = "paired"
SHIFTS = ("早班", "晚班")
CONFIDENCE_LEVELS = (.9, .95, .99)
_PROBLEM_LIMIT = 10


def metadata():
    return {"name": "包装线节拍对照实验", "short": "pack-welch", "tagline": "把工艺调整的节拍差，放进可复查的实验区间。", "client": "榆川包装 · 52 人食品外包装车间，工艺组比较两种封装动作", "workflow": "工艺员用秒表登记每段节拍，把两列平均值截图交给生产经理。", "pains": ["忽略两组方差差异", "只报改善秒数没有不确定区间", "班次混杂未单独观察", "同一工位两动作的配对关系被当作独立样本丢掉"], "upstream": "随机分配试运行片段 YC_pack_trial.csv", "downstream": "工艺经理决定是否继续扩大试验",
            "entities": ["实验片段", "节拍比较", "工艺评审简报"], "dataset_name": "A 原动作 / B 改动作 · 160 段观测",
            "columns": [{"key": "run", "label": "片段", "type": "string"}, {"key": "arm", "label": "实验组", "type": "string"}, {"key": "shift", "label": "班次", "type": "string"}, {"key": "seconds", "label": "单件节拍/秒", "type": "number"}, {"key": STATION_KEY, "label": STATION_LABEL, "type": "string", "optional": True}],
            "parameters": [{"key": "confidence", "label": "区间置信度", "type": "select", "default": "0.95", "options": [{"value": str(v), "label": f"{v*100:g}%"} for v in CONFIDENCE_LEVELS]}, {"key": "shift", "label": "实验班次", "type": "select", "default": "全部", "options": [{"value": n, "label": n} for n in ("全部",) + SHIFTS]}, {"key": "analysis", "label": "分析口径", "type": "select", "default": MODE_WELCH, "options": [{"value": MODE_WELCH, "label": "独立样本 Welch 比较"}, {"value": MODE_PAIRED, "label": "按工位配对比较"}]}],
            "workbench_title": "节拍效果核验", "action_label": "执行节拍比较", "unit": "秒", "accent": "oklch(58% 0.16 69)", "style": "industrial",
            "seed_story": ["08:20 工艺员导入 YC_pack_trial.csv，A/B 各 80 段。", "08:30 核查片段按班次交错随机分配。", "08:40 分析员选择 95% 置信度和全部班次。", "08:45 执行 Welch 检验，查看 A−B 改善秒数。", "09:00 检查置信区间是否跨 0。", "09:20 改为晚班重算，查看异方差影响。", "09:45 导出工艺评审简报，交经理安排扩大试验。"],
            "method": "独立样本：改善量=均值(A)−均值(B)；SE=√(sA²/nA+sB²/nB)；Welch–Satterthwaite 自由度；双侧 t 检验和 t 分布置信区间；Cohen d 用合并标准差。配对样本：同一工位同班次取 A/B 各一段，差值 d=A−B；对差值做配对 t 检验，SE=sd/√n，t 分布置信区间；配对不完整则整次拒绝。", "limitations": ["假定观测片段近似独立", "未校正多个班次的探索性比较", "显著节拍差不能证明成品质检合格", "配对比较要求每个工位在所选班次内两动作各一段，缺对、同组重复或跨班配对均拒绝出结果"]}


def seed_records():
    rng = random.Random(1004)
    rows = []
    for arm, mu, sigma in [("A", 19.5, 1.4), ("B", 18.2, 2.1)]:
        for i in range(80):
            shift = "早班" if i % 2 == 0 else "晚班"
            rows.append({"run": f"YC-{arm}{i+1:03}", "arm": arm, "shift": shift, STATION_KEY: f"W{(i // 2) % 40 + 1:02d}", "seconds": round(max(1, rng.gauss(mu + (.8 if shift == "晚班" else 0), sigma)), 3)})
    return rows


def _parse_params(params):
    try:
        confidence = float(params.get("confidence", .95))
    except (TypeError, ValueError):
        raise ValueError("置信度只接受 0.90/0.95/0.99")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError("置信度只接受 0.90/0.95/0.99")
    shift = str(params.get("shift", "全部"))
    if shift not in ("全部",) + SHIFTS:
        raise ValueError("未知班次")
    analysis = str(params.get("analysis", MODE_WELCH))
    if analysis not in (MODE_WELCH, MODE_PAIRED):
        raise ValueError("分析口径只接受独立样本 Welch 或按工位配对")
    return confidence, shift, analysis


def _format_stations(names):
    names = sorted(set(names))
    head = "、".join(names[:_PROBLEM_LIMIT])
    if len(names) > _PROBLEM_LIMIT:
        return head + f" 等 {len(names)} 个"
    return head


def analyze(records, params):
    confidence, shift, analysis = _parse_params(params)
    if analysis == MODE_PAIRED:
        return _analyze_paired(records, confidence, shift)
    return _analyze_welch(records, confidence, shift)


def _analyze_welch(records, confidence, shift):
    groups = {"A": [], "B": []}
    seen = set()
    for r in records:
        try:
            arm, run = str(r["arm"]), str(r["run"])
            seconds = float(r["seconds"])
            if arm not in groups or not math.isfinite(seconds) or seconds <= 0 or run in seen:
                raise ValueError()
            seen.add(run)
            if shift == "全部" or r["shift"] == shift:
                groups[arm].append(seconds)
        except (KeyError, TypeError, ValueError):
            raise ValueError("片段号须唯一，组别为 A/B，节拍必须为正有限数")
    if min(map(len, groups.values())) < 3:
        raise ValueError("每组至少需要 3 个独立实验片段")
    a, b = np.array(groups["A"]), np.array(groups["B"])
    na, nb = len(a), len(b)
    ma, mb, va, vb = float(a.mean()), float(b.mean()), float(a.var(ddof=1)), float(b.var(ddof=1))
    se2 = va / na + vb / nb
    if se2 <= 1e-15:
        raise ValueError("两组均无变异，Welch 检验无法估计误差")
    df = se2 * se2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    diff, se = ma - mb, math.sqrt(se2)
    statistic = diff / se
    p = float(2 * stats.t.sf(abs(statistic), df))
    margin = float(stats.t.ppf((1 + confidence) / 2, df)) * se
    low, high = diff - margin, diff + margin
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    effect = diff / pooled
    rows = [{"arm": k, "n": len(groups[k]), "mean": round(float(np.mean(groups[k])), 4), "sd": round(float(np.std(groups[k], ddof=1)), 4)} for k in ("A", "B")]
    return {"summary": f"B 相对 A 平均节拍缩短 {diff:.3f} 秒；{confidence*100:g}% 区间为 [{low:.3f}, {high:.3f}] 秒。",
            "metrics": [{"label": "改善量 A−B", "value": round(diff, 5), "unit": "秒"}, {"label": "双侧 p 值", "value": float(f"{p:.6g}")}, {"label": "Cohen d", "value": round(effect, 5)}, {"label": "Welch 自由度", "value": round(df, 3)}],
            "table": {"columns": [{"key": "arm", "label": "实验组"}, {"key": "n", "label": "片段数"}, {"key": "mean", "label": "均值/秒"}, {"key": "sd", "label": "样本标准差/秒"}], "rows": rows},
            "chart": {"type": "bar", "labels": ["A 原动作", "B 改动作"], "series": [{"name": "平均单件节拍/秒", "values": [round(ma, 4), round(mb, 4)]}]},
            "findings": [f"区间下界 {low:.4f} 秒，上界 {high:.4f} 秒；{'区间未跨 0' if low > 0 or high < 0 else '区间跨 0'}。", f"t={statistic:.4f}，自由度={df:.3f}；分析班次：{shift}。", "仅在分组随机、片段独立的前提下支持实验推断；扩大试验仍须核查质检指标。"], "method": "改善量=均值(A)−均值(B)；SE=√(sA²/nA+sB²/nB)；Welch–Satterthwaite 自由度；双侧 t 检验和 t 分布置信区间；Cohen d 用合并标准差。", "warnings": ["班次子组比较为探索性分析，未调整多重检验。"]}


def _analyze_paired(records, confidence, shift):
    """按工位配对：每个工位在所选班次内必须 A/B 各恰好一段，否则整次拒绝。"""
    if not any(isinstance(r, dict) and r.get(STATION_KEY) not in (None, "") for r in records):
        raise ValueError("该批次缺少工位字段，无法按工位配对；请改用独立样本 Welch 比较")

    # station -> shift -> arm -> list[value]
    buckets = {}
    all_stations = set()
    missing_station = []
    seen_runs = set()
    for r in records:
        try:
            arm, run = str(r["arm"]), str(r["run"])
            record_shift = str(r["shift"])
            seconds = float(r["seconds"])
            if arm not in ("A", "B") or not math.isfinite(seconds) or seconds <= 0 or not run or run in seen_runs:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ValueError("片段号须唯一，组别为 A/B，节拍必须为正有限数")
        seen_runs.add(run)
        station = r.get(STATION_KEY)
        if station is None or str(station).strip() == "":
            missing_station.append(run)
            continue
        station = str(station).strip()
        all_stations.add(station)
        if shift != "全部" and record_shift != shift:
            continue
        buckets.setdefault(station, {}).setdefault(record_shift, {}).setdefault(arm, []).append(seconds)

    duplicates, incomplete, cross_shift, absent = [], [], [], []
    pairs = []
    target_shifts = list(SHIFTS) if shift == "全部" else [shift]
    for station, shift_map in buckets.items():
        station_bad = False
        station_pairs = []
        for record_shift in target_shifts:
            arms = shift_map.get(record_shift)
            if arms is None:
                continue  # 该班次无观测，交由完整性检查判定
            a_vals, b_vals = arms.get("A", []), arms.get("B", [])
            if len(a_vals) > 1 or len(b_vals) > 1:
                duplicates.append(station)
                station_bad = True
                continue
            if len(a_vals) == 1 and len(b_vals) == 1:
                station_pairs.append((record_shift, a_vals[0], b_vals[0]))
            elif a_vals or b_vals:
                # 同班次只有一个动作有数据：缺对
                incomplete.append(station)
                station_bad = True
        if station_bad:
            continue
        observed_shifts = set(shift_map)
        if shift == "全部":
            # 全部班次：A/B 出现在不同班次即构成跨班配对，必须每班各自成对
            per_shift_complete = all(len(shift_map.get(s, {}).get("A", [])) == 1 and len(shift_map.get(s, {}).get("B", [])) == 1 for s in observed_shifts)
            if observed_shifts - set(target_shifts) or not per_shift_complete or len(station_pairs) != len(observed_shifts):
                cross_shift.append(station)
                continue
        elif observed_shifts != set(target_shifts) or len(station_pairs) != 1:
            incomplete.append(station)
            continue
        for record_shift, a_val, b_val in station_pairs:
            pairs.append((station, record_shift, a_val, b_val))

    # 选定班次后核对配对完整性：整批中出现但该班次无任何记录的工位也算缺对，不能静默丢弃
    if shift != "全部":
        absent = sorted(all_stations - set(buckets))

    problems = []
    if missing_station:
        problems.append(f"存在 {len(missing_station)} 条缺少工位字段的记录（片段：{_format_stations(missing_station)}），旧批次请改用独立样本 Welch 比较")
    if absent:
        problems.append(f"所选班次无观测的工位（该班次缺对）：{_format_stations(absent)}")
    if duplicates:
        problems.append(f"同组重复工位（同班次同动作多于一段）：{_format_stations(duplicates)}")
    if incomplete:
        problems.append(f"缺对工位（所选班次内两动作未各齐一段）：{_format_stations(incomplete)}")
    if cross_shift:
        problems.append(f"跨班配对工位（A/B 未在同一班次内成对）：{_format_stations(cross_shift)}")
    if problems:
        raise ValueError("配对完整性校验未通过，整次拒绝，不能只拿好对计算；" + "；".join(problems))
    if len(pairs) < 3:
        raise ValueError("配对比较至少需要 3 个完整工位配对")

    pairs.sort(key=lambda item: (item[0], item[1]))
    stations = [item[0] for item in pairs]
    pair_shifts = [item[1] for item in pairs]
    a_vals = np.array([item[2] for item in pairs], dtype=float)
    b_vals = np.array([item[3] for item in pairs], dtype=float)
    diffs = a_vals - b_vals
    n = len(diffs)
    mean_diff = float(diffs.mean())
    sd_diff = float(diffs.std(ddof=1))
    if sd_diff <= 1e-15:
        raise ValueError("各工位差值无变异，配对 t 检验无法估计误差")
    se = sd_diff / math.sqrt(n)
    df = n - 1
    statistic = mean_diff / se
    p = float(2 * stats.t.sf(abs(statistic), df))
    margin = float(stats.t.ppf((1 + confidence) / 2, df)) * se
    low, high = mean_diff - margin, mean_diff + margin
    rows = [{"station": station, "shift": pair_shift, "a_seconds": round(float(a_val), 4), "b_seconds": round(float(b_val), 4), "diff": round(float(a_val - b_val), 4)}
            for station, pair_shift, a_val, b_val in pairs]
    station_count = len(set(stations))
    return {"summary": f"{station_count} 个工位共 {n} 对配对，B 相对 A 平均节拍缩短 {mean_diff:.3f} 秒；{confidence*100:g}% 配对区间为 [{low:.3f}, {high:.3f}] 秒。",
            "metrics": [{"label": "配对数", "value": n, "unit": "对"}, {"label": "覆盖工位", "value": station_count, "unit": "个"}, {"label": "平均改善量 A−B", "value": round(mean_diff, 5), "unit": "秒"}, {"label": "区间下界", "value": round(low, 5), "unit": "秒"}, {"label": "区间上界", "value": round(high, 5), "unit": "秒"}, {"label": "双侧 p 值", "value": float(f"{p:.6g}")}, {"label": "配对 t 自由度", "value": df}],
            "table": {"columns": [{"key": "station", "label": STATION_LABEL}, {"key": "shift", "label": "班次"}, {"key": "a_seconds", "label": "A 原动作/秒"}, {"key": "b_seconds", "label": "B 改动作/秒"}, {"key": "diff", "label": "逐对差值 A−B/秒"}], "rows": rows},
            "chart": {"type": "bar", "labels": [f"{s}·{x}" for s, x in zip(stations, pair_shifts)], "series": [{"name": "逐对差值 A−B/秒", "values": [round(float(v), 4) for v in diffs]}]},
            "findings": [f"配对差值区间下界 {low:.4f} 秒，上界 {high:.4f} 秒；{'区间未跨 0' if low > 0 or high < 0 else '区间跨 0'}。", f"配对 t={statistic:.4f}，自由度={df}，差值标准差={sd_diff:.4f} 秒；分析班次：{shift}。", f"共 {n} 对、覆盖 {station_count} 个工位；配对要求同工位同班次两动作各一段，跨班配对已拒绝。", "配对比较利用同工位相关性降低方差；扩大试验仍须核查质检指标。"],
            "method": "按工位配对：同一工位同班次取 A/B 各一段，逐对差值 d=A−B；平均改善量=均值(d)；SE=sd(d)/√n；双侧配对 t 检验，自由度 n−1，t 分布置信区间。",
            "warnings": ["配对不完整（缺对、同组重复、跨班配对）时整次拒绝，不会只取好对计算。", "班次子组比较为探索性分析，未调整多重检验。"]}
