#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p4_analysis.py — 统计判定与交叉线估计（P4 产物）
=================================================
输入：.tmp/linear-models/results/*.json（由 lda_log_lab.py 产出，schema 已冻结）
输出：.tmp/linear-models/results/p4_summary.json（P5 报告的唯一数据源）

运行：python experiment/p4_analysis.py   （在所有实验 stage 跑完之后）
依赖：仅 numpy + 标准库。

方法（与 research-plan.md §6 冻结一致）：
  - 配对检验：对每个格点的逐 rep 差值数组（paired.d_auc / d_brier / d_logloss）做
    Wilcoxon 符号秩（正态近似 + 结校正 + 连续性校正），双侧。
  - 多重比较：每 stage 内 {metric × point} 全部 p 值做 Holm 校正（族 = 单 stage 单 metric）。
  - 交叉点：win = ΔAUC>0（恰为 0 记 0.5），对 log10(n)（E1）/ d（E2）/ λ（E3a）拟合
    分组二项 logistic（IRLS），解 P(win)=0.5 的轴值；拟合失败返回 None 并记录原因。
  - 有效性：逐点记录 lda/logit 相对贝叶斯天花板的差（paired.lda_rel_bayes 等）。
"""
import json
import math
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, ".tmp", "linear-models", "results")
STAGES = ["e1", "e2", "e3a", "e3b", "e5"]
METRICS = ("auc", "brier", "logloss")
ANCHOR_METRICS = ("auc", "brier")


# ---------------- 统计基元 ----------------
def wilcoxon_p(diff):
    """双侧 Wilcoxon 符号秩，正态近似，结校正+连续性校正。返回 (p, W, n_eff)。"""
    d = np.asarray([x for x in diff if np.isfinite(x) and abs(x) > 1e-12], dtype=float)
    n = len(d)
    if n < 6:
        return float("nan"), float("nan"), n
    absd = np.abs(d)
    order = np.argsort(absd, kind="mergesort")
    ranks = np.empty(n)
    i = 0
    tie_groups = []
    s = absd[order]
    while i < n:
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        avg = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        if j > i:
            tie_groups.append(j - i + 1)
        i = j + 1
    w_pos = float(ranks[d > 0].sum())
    w_stat = min(w_pos, float(ranks.sum()) - w_pos)
    mu = n * (n + 1) / 4.0
    sig2 = n * (n + 1) * (2 * n + 1) / 24.0
    for t in tie_groups:
        sig2 -= t * (t - 1) * (t + 1) * (2 * t + 1) / 48.0
    sig = math.sqrt(max(sig2, 1e-12))
    z = (abs(w_stat - mu) + 0.5) / sig
    p = math.erfc(z / math.sqrt(2.0))
    return float(min(1.0, max(p, 0.0))), w_stat, n


def holm(ps):
    """Holm 校正。ps: list[(key, p_or_nan)] → dict[key, p_holm]。"""
    items = [(k, p) for k, p in ps if np.isfinite(p)]
    nan_keys = [k for k, p in ps if not np.isfinite(p)]
    items.sort(key=lambda x: x[1])
    m = len(items)
    out = {}
    running = 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)          # 单调性
        out[k] = running
    for k in nan_keys:
        out[k] = None
    return out


def fit_win_rate(diff):
    d = np.asarray([x for x in diff if np.isfinite(x)], dtype=float)
    if len(d) == 0:
        return 0.5, 0, 0
    wins = float(np.sum(d > 0)) + 0.5 * float(np.sum(d == 0))
    return wins / len(d), wins, len(d)


def grouped_logit(x, k, ntot):
    """二项分组 logistic：P=σ(a+b·x)。返回 (a,b,ok)。"""
    x = np.asarray(x, dtype=float)
    k = np.asarray(k, dtype=float)
    nn = np.asarray(ntot, dtype=float)
    ok = nn > 0
    x, k, nn = x[ok], k[ok], nn[ok]
    if len(x) < 3 or np.all(k <= 1e-9) or np.all(k >= nn - 1e-9):
        return None, None, False
    y = k / nn
    B = np.array([[1.0, xx] for xx in x])
    beta = np.array([math.log(max(0.5 * (np.sum(k) + 0.5) / (np.sum(nn) - np.sum(k) + 0.5), 1e-6)), 0.0])
    for _ in range(60):
        z = B @ beta
        p = 1.0 / (1.0 + np.exp(-z))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        w = nn * p * (1 - p)
        w = np.clip(w, 1e-12, None)
        g = B.T @ (k - nn * p)
        H = B.T @ (B * w[:, None])
        try:
            step = np.linalg.solve(H + 1e-9 * np.eye(2), g)
        except np.linalg.LinAlgError:
            return None, None, False
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return float(beta[0]), float(beta[1]), True


def crossover_from_fit(a, b):
    """P=0.5 ⇒ a+b·x=0。"""
    if b == 0.0:
        return None
    return -a / b


# ---------------- 合成阶段 ----------------
def analyze_synth(stage, pts):
    rows = []
    for pt in pts:
        cfg = pt["config"]
        paired = pt["paired"]
        row = {
            "n": cfg["n"], "d": cfg["d"], "lam": cfg["lam"], "gamma": cfg["gamma"],
            "tag": "n%d_d%d_lam%g_g%g" % (cfg["n"], cfg["d"], cfg["lam"], cfg["gamma"]),
            "n_rep": pt["n_rep"], "bayes_auc": pt["bayes_auc"],
            "auc_lda": pt["stats"]["lda"]["auc"], "auc_logit": pt["stats"]["logit"]["auc"],
            "d_auc_mean": paired["d_auc_mean"], "d_auc_ci": paired["d_auc_ci"],
            "d_brier_mean": paired["d_brier_mean"], "d_logloss_mean": paired["d_logloss_mean"],
            "lda_rel_bayes": paired["lda_rel_bayes"], "logit_rel_bayes": paired["logit_rel_bayes"],
            "win_rate_auc": fit_win_rate(paired["d_auc"])[0],
            "wins_auc": fit_win_rate(paired["d_auc"])[1], "trials_auc": fit_win_rate(paired["d_auc"])[2],
            "dir": pt.get("dir", {}),
        }
        for w in (1, 5, 20):
            row["cost_w%d_lda_tau05" % w] = pt["stats"]["lda"]["cost_w%g_tau05" % w]
            row["cost_w%d_logit_tau05" % w] = pt["stats"]["logit"]["cost_w%g_tau05" % w]
            row["cost_w%d_lda_tstar" % w] = pt["stats"]["lda"]["cost_w%g_tstar" % w]
            row["cost_w%d_logit_tstar" % w] = pt["stats"]["logit"]["cost_w%g_tstar" % w]
        if "qda" in pt:
            row["qda"] = pt["qda"]
        if "lda_by_factor" in pt:
            row["by_factor"] = pt["lda_by_factor"]
        rows.append(row)
    tests = {}
    for metric in METRICS:
        key = "d_%s" % ("auc" if metric == "auc" else ("brier" if metric == "brier" else "logloss"))
        ps = []
        for r in rows:
            pval, W, ne = wilcoxon_p(r.get("_diff_" + metric, []))
            ps.append((r["tag"], pval))
        tests[metric] = holm(ps)
    return {"points": rows, "wilcoxon_raw_note": "逐 rep 数组见 points[*].d_auc 原始留存", "holm_by_metric_stage": tests}


def analyze_stage_file(sname):
    path = os.path.join(RES, "%s.json" % sname)
    if not os.path.exists(path):
        return {"stage": sname, "error": "missing %s" % path}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    rows = []
    for pt in data["points"]:
        if "error" in pt:
            continue
        cfg = pt["config"]
        paired = pt["paired"]
        wr, wins, trials = fit_win_rate(paired["d_auc"])
        row = {
            "n": cfg["n"], "d": cfg["d"], "lam": cfg["lam"], "gamma": cfg["gamma"],
            "tag": "n%d_d%d_lam%g_g%g" % (cfg["n"], cfg["d"], cfg["lam"], cfg["gamma"]),
            "n_rep": pt["n_rep"], "bayes_auc": pt["bayes_auc"],
            "auc_lda": pt["stats"]["lda"]["auc"], "auc_logit": pt["stats"]["logit"]["auc"],
            "d_auc_mean": paired["d_auc_mean"], "d_auc_ci": paired["d_auc_ci"],
            "d_brier_mean": paired["d_brier_mean"], "d_brier_ci": paired["d_brier_ci"],
            "d_logloss_mean": paired["d_logloss_mean"],
            "lda_rel_bayes": paired["lda_rel_bayes"], "logit_rel_bayes": paired["logit_rel_bayes"],
            "win_rate_auc": wr, "wins_auc": wins, "trials_auc": trials,
            "dir": {k: pt.get("dir", {}).get(k) for k in ("cos_mean", "cos_lo", "cos_hi", "lda_ang_sd_mean", "logit_ang_sd_mean")},
            "n_irls_nonconv": pt["stats"]["logit"]["n_irls_nonconv"],
            "n_lda_pinv": pt["stats"]["lda"]["n_lda_pinv"],
        }
        for w in (1, 5, 20):
            row["cost_w%d_lda_tau05" % w] = pt["stats"]["lda"]["cost_w%g_tau05" % w]
            row["cost_w%d_logit_tau05" % w] = pt["stats"]["logit"]["cost_w%g_tau05" % w]
            row["cost_w%d_lda_tstar" % w] = pt["stats"]["lda"]["cost_w%g_tstar" % w]
            row["cost_w%d_logit_tstar" % w] = pt["stats"]["logit"]["cost_w%g_tstar" % w]
        if "qda" in pt:
            row["qda"] = pt["qda"]
        if "lda_by_factor" in pt:
            row["by_factor"] = pt["lda_by_factor"]
        # 逐 rep 数组留存（Wilcoxon/复核用）
        row["per_rep_d_auc"] = paired["d_auc"]
        row["per_rep_d_brier"] = paired["d_brier"]
        row["per_rep_d_logloss"] = paired["d_logloss"]
        rows.append(row)
    tests = {}
    ARR = {"auc": "per_rep_d_auc", "brier": "per_rep_d_brier", "logloss": "per_rep_d_logloss"}
    for metric in METRICS:
        ps = []
        for r in rows:
            pval, _, _ = wilcoxon_p(r[ARR[metric]])
            ps.append((r["tag"], pval))
        tests[metric] = holm(ps)
    # 交叉线拟合（按轴分组）
    crossovers = {}
    def axis_fit(rows_sub, xfun, name):
        xs = [xfun(r) for r in rows_sub]
        ks = [r["wins_auc"] for r in rows_sub]
        ns = [r["trials_auc"] for r in rows_sub]
        a, b, ok = grouped_logit(xs, ks, ns)
        if ok:
            cx = crossover_from_fit(a, b)
            crossovers[name] = {"a": a, "b": b, "crossover_x": cx,
                                "n_pts": len(rows_sub)}
        else:
            crossovers[name] = {"ok": False, "n_pts": len(rows_sub)}
    lam0 = [r for r in rows if r["lam"] == 0.0 and r["gamma"] == 1.0]
    if sname == "e1":
        for dd in sorted({r["d"] for r in lam0}):
            sub = [r for r in lam0 if r["d"] == dd]
            axis_fit(sub, lambda r: math.log10(r["n"]), "e1_d%d_log10n" % dd)
    if sname == "e2":
        axis_fit(lam0, lambda r: r["d"], "e2_n300_d")
    if sname == "e3a":
        axis_fit([r for r in rows if r["gamma"] == 1.0], lambda r: r["lam"], "e3a_lambda")
    return {"stage": sname, "points": rows, "holm_by_metric": tests, "crossovers": crossovers}


# ---------------- 锚点阶段 ----------------
def analyze_anchors():
    path = os.path.join(RES, "e6.json")
    if not os.path.exists(path):
        return {"stage": "e6", "error": "missing %s" % path}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    out = {"stage": "e6", "anchors": []}
    ps_auc, ps_brier = [], []
    for a in data["points"]:
        cfg = a["config"]
        p_auc = a["paired"]
        row = {
            "anchor": cfg["anchor"], "n": cfg["n"], "d": cfg["d"], "pos_rate": cfg["pos_rate"],
            "auc_lda": a["lda"]["auc"], "auc_logit": a["logit"]["auc"],
            "brier_lda": a["lda"]["brier"], "brier_logit": a["logit"]["brier"],
            "logloss_lda": a["lda"]["logloss"], "logloss_logit": a["logit"]["logloss"],
            "d_auc_mean": p_auc["d_auc_mean"], "d_auc_ci": p_auc["d_auc_ci"],
            "d_brier_mean": p_auc["d_brier_mean"], "d_brier_ci": p_auc["d_brier_ci"],
            "win_rate_auc": fit_win_rate(p_auc["per_rep_d_auc"])[0],
            "per_rep_d_auc": p_auc["per_rep_d_auc"],
            "lda_lw": a.get("lda_lw"), "dir": a.get("dir"),
            "alpha_hist": a.get("alpha_hist"), "fail": a.get("fail"),
        }
        pa, _, na = wilcoxon_p(p_auc["per_rep_d_auc"])
        pb, _, _ = wilcoxon_p(p_auc["per_rep_d_brier"] if "per_rep_d_brier" in p_auc else [])
        row["wilcoxon_auc_raw"], row["wilcoxon_auc_n"] = pa, na
        ps_auc.append((cfg["anchor"], pa))
        ps_brier.append((cfg["anchor"], pb))
        out["anchors"].append(row)
    out["holm_auc"] = holm(ps_auc)
    out["holm_brier"] = holm(ps_brier)
    return out


# ---------------- 汇总 ----------------
def main():
    summary = {"generator": "p4_analysis.py v1", "stages": {}, "anchors": None,
               "regime_table": [], "notes": []}
    for s in STAGES:
        r = analyze_stage_file(s)
        summary["stages"][s] = r
        for pt in r.get("points", []):
            summary["regime_table"].append({
                "n": pt["n"], "d": pt["d"], "lam": pt["lam"], "gamma": pt["gamma"],
                "winner_auc": ("lda" if pt["d_auc_mean"] > 0 else "logit" if pt["d_auc_mean"] < 0 else "tie"),
                "win_rate_auc": round(pt["win_rate_auc"], 4),
                "d_auc_mean": round(pt["d_auc_mean"], 5),
                "p_holm_auc": pt_holm(r, pt),
            })
    summary["anchors"] = analyze_anchors()
    # 快速结论行（供报告摘要直接引用；判定阈值也预注册：p_holm<0.05 且 |d_auc_mean|>0.005 才算优势）
    concl = []
    for s, r in summary["stages"].items():
        if "error" in r:
            continue
        for pt in r["points"]:
            ph = pt_holm(r, pt)
            sig = ph is not None and ph < 0.05 and abs(pt["d_auc_mean"]) > 0.005
            concl.append({"stage": s, "tag": pt["tag"],
                          "call": ("LDA" if pt["d_auc_mean"] > 0 else "logit") if sig else "undecided",
                          "d_auc": round(pt["d_auc_mean"], 5), "p_holm": ph})
    summary["calls"] = concl
    out_path = os.path.join(RES, "p4_summary.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("wrote", out_path)
    print("regime points:", len(summary["regime_table"]))
    for s in STAGES:
        r = summary["stages"][s]
        print(" %-4s %s" % (s, "ERROR " + r["error"] if "error" in r else
                            "%d pts, crossovers: %s" % (len(r["points"]),
                            {k: (round(v["crossover_x"], 3) if v.get("crossover_x") is not None else None)
                             for k, v in r["crossovers"].items()} if r["crossovers"] else "-")))
    a = summary["anchors"]
    if "error" in a:
        print(" e6   ERROR", a["error"])
    else:
        for row in a["anchors"]:
            print(" e6/%-12s ΔAUC=%+.4f p_holm=%s win=%.2f" % (
                row["anchor"], row["d_auc_mean"], a["holm_auc"].get(row["anchor"]),
                row["win_rate_auc"]))


def pt_holm(stage_result, pt):
    try:
        return stage_result["holm_by_metric"]["auc"].get(pt["tag"])
    except Exception:
        return None


if __name__ == "__main__":
    main()
