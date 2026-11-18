#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lda_log_lab.py — LDA vs Logistic 交叉曲面实验台（P2 产物，v3）
==============================================================
预注册依据：research-plan.md（网格/指标/协议在跑数前冻结，本文头部常量与其一致）。
最终用途：为论文格式 HTML 报告生成 JSON 结果。

依赖：仅 numpy + 标准库（csv/json/math/time/zlib）。**不需要 sklearn/pandas**。
建议 Python ≥3.10。numpy 版本不限（2026-11 实测 2.3.5）。

用法：
    python experiment/lda_log_lab.py --stage selftest      # 必跑自检（~1 分钟）
    python experiment/lda_log_lab.py --stage smoke         # 5 rep 冒烟
    python experiment/lda_log_lab.py --quick --stage all   # 快扫（nrep=40，看趋势）
    python experiment/lda_log_lab.py --stage all           # 全量（nrep=200，预计 30~90 min）
    python experiment/lda_log_lab.py --stage e2,e5 --force # 子集重跑

输出（相对本包根目录）：
    .tmp/linear-models/cache/point_<stage>_<tag>.json   逐格点缓存（存在即跳过，断点续跑）
    .tmp/linear-models/cache/bayes_d*_lam*_g*.json      贝叶斯天花板缓存
    .tmp/linear-models/results/<stage>.json             阶段汇总（P4 分析唯一输入）

协议要点（冻结）：
  - 标准化/one-hot/先验/μ̂/Σ̂/α(L2)/τ* 一律只在训练折内拟合；selftest #6 有泄漏哨兵。
  - 种子：SEED0*1000 + CRC32(config)，再 + 7919×rep；两模型共享同一 train/test 划分。
  - 指标四件套：ROC-AUC / Brier / log-loss / 代价 {1,5,20}×FN:FP @ {τ=0.5, τ*}；
    τ* 在训练折 OOF 概率上按代价最小选取；锚点用池化 OOF（两模型对称，报告注明）。
  - 合成设定：μ0=0, μ1=SEP·e1, Σ0=I, Σ1 前 ⌈d/2⌉ 个分量方差 1→1+3λ, π=0.44。
    SEP=√2·Φ⁻¹(0.85)≈1.4658；二正态等方差 AUC=Φ(d′/√2) ⇒ 共享Σ时天花板≈0.85。
  - 偏态 γ：可逆保号幂变换不改变似然比排序 ⇒ 贝叶斯 AUC 与 γ 无关（天花板 MC 用变换前密度）。
  - 方向稳定性（bootstrap 重拟合）只在 cfg.stability=True 的格点计算（E2/E5），控制运行时间。
  - 已知简化（写进报告局限）：heart 锚点 one-hot 水平集取全数据（列集合已知，统计量折内）。
"""
import argparse
import csv
import json
import math
import os
import time
import zlib

import numpy as np

# ---------------- 冻结常数 ----------------
SEED0 = 2026
NREP_DEFAULT = 200
NREP_QUICK = 40
ANCHOR_REP_DEFAULT = 10
ANCHOR_REP_QUICK = 5
PI = 0.44
SEP = 1.46575          # √2·Φ⁻¹(0.85) ⇒ 贝叶斯 AUC = Φ(SEP/√2) = 0.85
R_MAX = 4.0
TAU_GRID = np.round(np.arange(0.05, 0.9501, 0.01), 4)
COST_W = (1.0, 5.0, 20.0)
ALPHAS_FULL = [100.0, 10.0, 1.0, 0.1, 0.01]     # α = 1/C（L2 罚），降序 warm-start
ALPHAS_QUICK = [10.0, 1.0, 0.1]
CLIP = 1e-15
MC_FULL = 100000
MC_QUICK = 30000
BOOT_B = 20            # 稳定性 bootstrap 次数
STABILITY_EVERY = 1    # 每 K 个 rep 算一次稳定性（默认全算；仅在 stability=True 格点）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEART_PATH = os.path.join(ROOT, "assets", "pbl-linear-models-lda-logistic-regression", "statlog-heart.csv")
BCW_PATH = os.path.join(ROOT, "data", "raw-breast_cancer_sklearn.csv")
PIMA_PATH = os.path.join(ROOT, "data", "raw-pima_diabetes_plotly.csv")


def crc32_of(s):
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF


def point_seed(base, rep):
    return (base + 7919 * rep) % (2 ** 32)


# ---------------- 数值工具 ----------------
def sigmoid(z):
    z = np.asarray(z, dtype=float)
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    e = np.exp(z[~pos])
    out[~pos] = e / (1.0 + e)
    return out


def log1pexp(z):
    z = np.asarray(z, dtype=float)
    out = np.empty_like(z)
    hi = z > 30
    lo = z < -30
    mid = ~(hi | lo)
    out[hi] = z[hi]
    out[lo] = np.exp(z[lo])
    out[mid] = np.log1p(np.exp(z[mid]))
    return out


def logistic_nll(z, y):
    return float(np.sum(log1pexp(z) - y * z))


def auc_score(y, p):
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    idx = np.argsort(p, kind="mergesort")
    ps = p[idx]
    ys = y[idx]
    ranks = np.arange(1.0, len(p) + 1.0)
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        if j > i:
            ranks[i:j + 1] = (i + j + 2) / 2.0
        i = j + 1
    sum_pos = float(ranks[ys == 1].sum())
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier(y, p):
    p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
    return float(np.mean((p - np.asarray(y, dtype=float)) ** 2))


def logloss(y, p):
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)
    yy = np.asarray(y, dtype=float)
    return float(-np.mean(yy * np.log(p) + (1.0 - yy) * np.log(1.0 - p)))


def cost_at_tau(p, y, w, tau):
    p = np.asarray(p, dtype=float)
    y = np.asarray(y).astype(int)
    return float(np.sum(p[y == 0] > tau) + w * np.sum(p[y == 1] <= tau))


def cost_curve(p, y, w):
    """返回 (最小代价, 最优τ, 全网格代价)。τ* = 曲线 argmin，平手取最小 τ（网格顺序）。"""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y).astype(int)
    pneg = np.sort(p[y == 0])
    ppos = np.sort(p[y == 1])
    fp = len(pneg) - np.searchsorted(pneg, TAU_GRID, side="right")
    fn = np.searchsorted(ppos, TAU_GRID, side="right")
    cost = fp + w * fn
    k = int(np.argmin(cost))
    return float(cost[k]), float(TAU_GRID[k]), cost


def boot_ci(vals, B=1000, rng=None):
    v = np.asarray([x for x in vals if np.isfinite(x)], dtype=float)
    if len(v) < 3:
        return [float("nan"), float("nan")]
    rng = rng or np.random.default_rng(SEED0)
    reps = v[rng.integers(0, len(v), size=(B, len(v)))]
    s = reps.mean(axis=1)
    return [float(np.quantile(s, 0.025)), float(np.quantile(s, 0.975))]


# ---------------- 合成数据与贝叶斯天花板 ----------------
def sigma_vec(d, lam):
    k = max(1, math.ceil(d / 2))
    v = np.ones(d)
    v[:k] = 1.0 + (R_MAX - 1.0) * lam
    return v


def gen_sample(n, d, lam, gamma, rng):
    v = sigma_vec(d, lam)
    n1 = int(round(PI * n))
    n0 = n - n1
    x0 = rng.standard_normal((n0, d))
    x1 = rng.standard_normal((n1, d)) * np.sqrt(v)
    x1[:, 0] += SEP
    X = np.vstack([x0, x1])
    y = np.concatenate([np.zeros(n0, dtype=int), np.ones(n1, dtype=int)])
    if gamma != 1.0:
        X = np.sign(X) * (np.abs(X) + 1e-9) ** gamma
    return X, y


def lr_score(X, v):
    """log(p1/p0) 的可加部分：Σ0=I, Σ1=diag(v), μ1=SEP·e1（二次型，λ>0 时非线性可分）。"""
    qcoef = 0.5 * (1.0 - 1.0 / v)
    return (X * X) @ qcoef + (SEP / v[0]) * X[:, 0]


def bayes_auc_mc(d, lam, m=MC_FULL, seed=12345):
    v = sigma_vec(d, lam)
    rng = np.random.default_rng(seed)
    s0 = lr_score(rng.standard_normal((m, d)), v)
    x1 = rng.standard_normal((m, d)) * np.sqrt(v)
    x1[:, 0] += SEP
    s1 = lr_score(x1, v)
    s0s = np.sort(s0)
    lo = np.searchsorted(s0s, s1, side="left")
    hi = np.searchsorted(s0s, s1, side="right")
    return float(np.mean((lo + hi) / 2.0 / m))


def bayes_auc_cached(d, lam, gamma, cache_dir, m):
    """γ 不改变 LR 排序 ⇒ 天花板只依赖 (d, λ)；tag 里带 γ 仅为与格点缓存命名一致。"""
    key = "bayes_d%d_lam%g_g%g_m%d.json" % (d, lam, gamma, m)
    p = os.path.join(cache_dir, key)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)["auc"]
    val = bayes_auc_mc(d, lam, m=m)
    os.makedirs(cache_dir, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"d": d, "lam": lam, "gamma": gamma, "m": m, "auc": val}, fh)
    return val


# ---------------- 折内预处理 ----------------
class Standardizer:
    def fit(self, Xtr):
        self.mu = Xtr.mean(axis=0)
        sd = Xtr.std(axis=0, ddof=1)
        self.sd = np.where(sd > 1e-12, sd, 1.0)
        return self

    def transform(self, X):
        return (X - self.mu) / self.sd


def strat_split(y, frac, rng):
    idx1 = np.where(y == 1)[0]
    idx0 = np.where(y == 0)[0]
    rng.shuffle(idx1)
    rng.shuffle(idx0)
    n1v = max(1, int(round(frac * len(idx1))))
    n0v = max(1, int(round(frac * len(idx0))))
    te = np.concatenate([idx1[:n1v], idx0[:n0v]])
    tr = np.concatenate([idx1[n1v:], idx0[n0v:]])
    return tr, te


def stratified_kfold(y, k, rng):
    folds = [[] for _ in range(k)]
    for cls in (1, 0):
        idx = np.where(y == cls)[0].copy()
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            folds[j % k].append(i)
    return [np.array(sorted(f)) for f in folds]


def design(X):
    return np.hstack([np.ones((len(X), 1)), X])


# ---------------- LDA（+LW 收缩因子） ----------------
def lw_delta(Xc, n):
    d = Xc.shape[1]
    S = Xc.T @ Xc / n
    mu = float(np.trace(S)) / d
    gamma2 = float(np.linalg.norm(S - mu * np.eye(d), "fro") ** 2)
    if gamma2 <= 0:
        return 0.0
    beta2 = 0.0
    for x in Xc:
        beta2 += float(np.linalg.norm(np.outer(x, x) - S, "fro") ** 2)
    beta2 /= (n * n)
    return float(min(beta2, gamma2) / gamma2)


def fit_lda(X, y, factors=(0.0,), ridge=1e-8):
    n, d = X.shape
    i1 = y == 1
    i0 = ~i1
    mu1 = X[i1].mean(0)
    mu0 = X[i0].mean(0)
    n1 = int(i1.sum())
    n0 = int(i0.sum())
    Xc = X.copy()
    Xc[i1] -= mu1
    Xc[i0] -= mu0
    S = Xc.T @ Xc / max(n - 2, 1)
    dlw = lw_delta(Xc, n)
    mu_tr = float(np.trace(S)) / d
    eye = np.eye(d)
    pi1 = max(n1 / n, CLIP)
    pi0 = max(n0 / n, CLIP)
    out = {}
    for f in factors:
        delta = min(max(f * dlw, 0.0), 1.0)
        Sr = (1.0 - delta) * S + delta * mu_tr * eye + ridge * eye
        try:
            sol = np.linalg.solve(Sr, mu1 - mu0)
            pinv = False
        except np.linalg.LinAlgError:
            sol = np.linalg.pinv(Sr) @ (mu1 - mu0)
            pinv = True
        c1 = float(mu1 @ sol)
        c0 = float(mu0 @ sol)
        out[f] = {"beta": sol, "beta0": -0.5 * (c1 - c0) + math.log(pi1 / pi0),
                  "pinv": pinv, "delta": delta}
    return out, dlw


def predict_lda(m, X):
    return sigmoid(m["beta0"] + X @ m["beta"])


def lda_oof(Xtr, ytr, rng, factor=0.0, k=5):
    folds = stratified_kfold(ytr, k, rng)
    oof = np.zeros(len(ytr))
    for f in folds:
        mask = np.ones(len(ytr), dtype=bool)
        mask[f] = False
        st = Standardizer().fit(Xtr[mask])
        lds, _ = fit_lda(st.transform(Xtr[mask]), ytr[mask], factors=(factor,))
        oof[f] = predict_lda(lds[factor], st.transform(Xtr[f]))
    return oof


# ---------------- Logistic（正则路径 + IRLS） ----------------
def irls(Xb, y, beta_start, lam2, maxit=80, tol=1e-11):
    """带 L2（不含截距）牛顿 + 目标单调减半步长。收敛判据：目标增益与步长同时趋零。"""
    pen = np.concatenate([[0.0], np.full(Xb.shape[1] - 1, lam2)])

    def obj(b):
        return logistic_nll(Xb @ b, y) + 0.5 * float(np.sum(pen * b * b))

    beta = np.array(beta_start, dtype=float)
    f_old = obj(beta)
    converged = False
    for _ in range(maxit):
        pr = sigmoid(Xb @ beta)
        W = np.clip(pr * (1.0 - pr), 1e-10, None)
        g = Xb.T @ (y - pr) - pen * beta
        H = Xb.T @ (Xb * W[:, None]) + np.diag(pen)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, g, rcond=None)[0]
        moved = False
        for fr in (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.015625, 0.0078125):
            trial = beta + fr * step
            if obj(trial) <= f_old:
                beta_new = trial
                moved = True
                break
        if not moved:
            converged = True          # 步长预算耗尽 ≈ 数值收敛
            break
        gain = f_old - obj(beta_new)
        move = float(np.linalg.norm(beta_new - beta))
        beta = beta_new
        f_old = obj(beta)
        if gain <= tol * max(1.0, abs(f_old)) and move < 1e-5:
            converged = True
            break
    return beta, converged


def fit_logistic_path(X, y, alphas):
    Xb = design(X)
    p1 = min(max(float(y.mean()), CLIP), 1.0 - CLIP)
    b0 = np.concatenate([[math.log(p1 / (1.0 - p1))], np.zeros(X.shape[1])])
    fits = {}
    prev = b0
    for a in sorted(alphas, reverse=True):
        b, conv = irls(Xb, y, prev, a)
        fits[a] = (b, conv)
        prev = b
    return fits, b0


def select_logistic(Xtr, ytr, alphas, rng):
    """内层分层 5 折：每 α 的 OOF NLL 最小者胜出；全训练段重拟合。返回含 OOF（τ* 用）。"""
    folds = stratified_kfold(ytr, 5, rng)
    oof = {a: np.zeros(len(ytr)) for a in alphas}
    for f in folds:
        mask = np.ones(len(ytr), dtype=bool)
        mask[f] = False
        st = Standardizer().fit(Xtr[mask])
        fits, _ = fit_logistic_path(st.transform(Xtr[mask]), ytr[mask], alphas)
        Xt = design(st.transform(Xtr[f]))
        for a in alphas:
            oof[a][f] = sigmoid(Xt @ fits[a][0])
    best_a, best_nll = alphas[0], float("inf")
    for a in alphas:
        pc = np.clip(oof[a], CLIP, 1.0 - CLIP)
        nll = logistic_nll(np.log(pc / (1.0 - pc)), ytr)
        if nll < best_nll:
            best_nll, best_a = nll, a
    st = Standardizer().fit(Xtr)
    fits, _ = fit_logistic_path(st.transform(Xtr), ytr, alphas)
    beta, conv = fits[best_a]
    return {"alpha": best_a, "beta_std": beta, "conv": conv, "st": st,
            "oof": oof[best_a], "nll": best_nll}


def logistic_prob(sel, X):
    return sigmoid(design(sel["st"].transform(X)) @ sel["beta_std"])


def logit_raw_dir(sel):
    return sel["beta_std"][1:] / sel["st"].sd


# ---------------- 方向稳定性 ----------------
def ang_sd(dirs):
    if len(dirs) < 2:
        return float("nan")
    m = np.mean(dirs, axis=0)
    nm = np.linalg.norm(m)
    if nm < 1e-15:
        return float("nan")
    angs = []
    for dd in dirs:
        nd = np.linalg.norm(dd)
        if nd < 1e-15:
            continue
        cosv = max(-1.0, min(1.0, float(dd @ m) / (nd * nm)))
        angs.append(math.acos(cosv))
    return float(np.std(angs, ddof=1)) if len(angs) > 1 else float("nan")


def stability(Xtr, ytr, alpha_log, rng, B=BOOT_B):
    """bootstrap 重拟合：原始尺度方向散布（角标准差）+ LDA/logit 方向余弦。"""
    n = len(ytr)
    lda_dirs, log_dirs, coslist = [], [], []
    nok = 0
    for _ in range(B):
        idx = rng.integers(0, n, n)
        if len(np.unique(ytr[idx])) < 2:
            continue
        stb = Standardizer().fit(Xtr[idx])
        Xsb = stb.transform(Xtr[idx])
        lds, _ = fit_lda(Xsb, ytr[idx], factors=(0.0,))
        if lds[0.0]["pinv"]:
            continue
        fits, _ = fit_logistic_path(Xsb, ytr[idx], [alpha_log])
        b_std, conv = fits[alpha_log]
        if not conv:
            continue
        w_lda = lds[0.0]["beta"] / stb.sd
        w_log = b_std[1:] / stb.sd
        lda_dirs.append(w_lda)
        log_dirs.append(w_log)
        nok += 1
        nw, nb = np.linalg.norm(w_lda), np.linalg.norm(w_log)
        if nw > 1e-15 and nb > 1e-15:
            coslist.append(float(w_lda @ w_log / (nw * nb)))
    if nok < 5:
        return {"cos_mean": float("nan"), "cos_lo": float("nan"), "cos_hi": float("nan"),
                "lda_ang_sd": float("nan"), "logit_ang_sd": float("nan"), "n_ok": nok}
    return {"cos_mean": float(np.mean(coslist)),
            "cos_lo": boot_ci(coslist)[0], "cos_hi": boot_ci(coslist)[1],
            "lda_ang_sd": ang_sd(lda_dirs), "logit_ang_sd": ang_sd(log_dirs), "n_ok": nok}


# ---------------- QDA 参照（E3a λ=1 点） ----------------
def fit_qda(X, y, ridge=1e-6):
    n, d = X.shape
    out = {}
    for cls in (1, 0):
        mask = y == cls
        mu = X[mask].mean(0)
        Xc = X[mask] - mu
        nk = int(mask.sum())
        S = Xc.T @ Xc / max(nk - 1, 1) + ridge * np.eye(d)
        try:
            L = np.linalg.cholesky(S)
            logdet = 2.0 * float(np.sum(np.log(np.diag(L))))
            Sinv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            Sinv = np.linalg.pinv(S)
            logdet = float(np.sum(np.log(np.maximum(np.linalg.eigvalsh(S), 1e-30))))
        out[cls] = (mu, Sinv, logdet, math.log(max(nk / n, CLIP)))

    def logit_p(Xq):
        g1 = -0.5 * np.einsum("ij,jk,ik->i", Xq - out[1][0], out[1][1], Xq - out[1][0]) - 0.5 * out[1][2] + out[1][3]
        g0 = -0.5 * np.einsum("ij,jk,ik->i", Xq - out[0][0], out[0][1], Xq - out[0][0]) - 0.5 * out[0][2] + out[0][3]
        return g1 - g0
    return logit_p


# ---------------- 代价块 ----------------
def cost_block(p_tr_oof, y_tr, p_te, y_te):
    out = {}
    for w in COST_W:
        tau_star = cost_curve(p_tr_oof, y_tr, w)[1]
        out["%g" % w] = {
            "tau_star": float(tau_star),
            "cost05_test": cost_at_tau(p_te, y_te, w, 0.5),
            "cost_star_test": cost_at_tau(p_te, y_te, w, tau_star),
            "cost_oracle_min_test": cost_curve(p_te, y_te, w)[0],
            "tau_oracle_test": cost_curve(p_te, y_te, w)[1],
        }
    return out


# ---------------- 单 rep（合成） ----------------
def run_rep(cfg, rng_rep, alphas):
    n, d, lam, gamma = cfg["n"], cfg["d"], cfg["lam"], cfg["gamma"]
    factors = tuple(cfg.get("factors", (0.0,)))
    X, y = gen_sample(n, d, lam, gamma, rng_rep)
    tr, te = strat_split(y, 0.2, rng_rep)
    if y[tr].sum() < 1 or y[te].sum() < 1:
        return None
    st = Standardizer().fit(X[tr])
    Xtr, Xte, ytr, yte = st.transform(X[tr]), st.transform(X[te]), y[tr], y[te]
    f0 = factors[0]

    lds, dlw = fit_lda(Xtr, ytr, factors=factors)
    lda = {"delta_lw": float(dlw)}
    best = lds[f0]
    p_lda_te = predict_lda(best, Xte)
    p_lda_oof = lda_oof(Xtr, ytr, rng_rep, factor=f0)
    lda.update({"auc": auc_score(yte, p_lda_te), "brier": brier(yte, p_lda_te),
                "logloss": logloss(yte, p_lda_te),
                "cost": cost_block(p_lda_oof, ytr, p_lda_te, yte)})
    if len(factors) > 1:
        lda["by_factor"] = {"%g" % f: {"auc": auc_score(yte, predict_lda(lds[f], Xte)),
                                       "brier": brier(yte, predict_lda(lds[f], Xte)),
                                       "logloss": logloss(yte, predict_lda(lds[f], Xte)),
                                       "delta": float(lds[f]["delta"])}
                            for f in factors}
    fail = {"irls_nonconv": 0, "lda_pinv": int(best["pinv"])}

    sel = select_logistic(Xtr, ytr, alphas, rng_rep)
    if not sel["conv"]:
        fail["irls_nonconv"] = 1
    p_log_te = logistic_prob(sel, Xte)
    logit = {"alpha": float(sel["alpha"]),
             "auc": auc_score(yte, p_log_te), "brier": brier(yte, p_log_te),
             "logloss": logloss(yte, p_log_te),
             "cost": cost_block(sel["oof"], ytr, p_log_te, yte)}

    rec = {"lda": lda, "logit": logit, "fail": fail}
    if cfg.get("stability") and (int(rng_rep.integers(10 ** 9)) % STABILITY_EVERY == 0):
        rec["dir"] = stability(Xtr, ytr, sel["alpha"], rng_rep)
    else:
        rec["dir"] = None
    if cfg.get("plot2d") and Xte.shape[1] == 2:   # plot 采集器仅支持 d=2（F1 散点）
        rec["plot"] = {"n": int(n),
                       "pts": [[[round(float(a), 4), round(float(b), 4)], int(v)] for (a, b), v in zip(Xte, yte)],
                       "lda_beta": [float(v) for v in best["beta"]], "lda_beta0": float(best["beta0"]),
                       "log_beta": [float(v) for v in sel["beta_std"][1:]], "log_beta0": float(sel["beta_std"][0])}
    if cfg.get("qda"):
        zq = fit_qda(Xtr, ytr)
        z = zq(Xte)
        rec["qda"] = {"auc": auc_score(yte, sigmoid(z)), "brier": brier(yte, sigmoid(z)),
                      "logloss": logloss(yte, sigmoid(z))}
    return rec


def aggregate(cfg, reps, bayes, runtime):
    rng_b = np.random.default_rng(SEED0)

    def arr(model, key):
        return np.array([float(r[model].get(key, float("nan"))) for r in reps], dtype=float)

    agg = {"config": cfg, "bayes_auc": float(bayes), "n_rep": len(reps),
           "runtime_s": round(float(runtime), 1), "numpy_version": np.__version__}
    stats = {}
    for model in ("lda", "logit"):
        m = {"n_irls_nonconv": int(sum(r["fail"]["irls_nonconv"] for r in reps)),
             "n_lda_pinv": int(sum(r["fail"]["lda_pinv"] for r in reps))}
        for k in ("auc", "brier", "logloss"):
            v = arr(model, k)
            m[k] = float(np.nanmean(v))
            m[k + "_ci"] = boot_ci(v.tolist(), rng=rng_b)
        for w in COST_W:
            m["cost_w%g_tau05" % w] = float(np.nanmean([r[model]["cost"]["%g" % w]["cost05_test"] for r in reps]))
            m["cost_w%g_tstar" % w] = float(np.nanmean([r[model]["cost"]["%g" % w]["cost_star_test"] for r in reps]))
            m["tau_mean_w%g" % w] = float(np.nanmean([r[model]["cost"]["%g" % w]["tau_star"] for r in reps]))
        stats[model] = m
    a_lda, a_log = arr("lda", "auc"), arr("logit", "auc")
    b_lda, b_log = arr("lda", "brier"), arr("logit", "brier")
    l_lda, l_log = arr("lda", "logloss"), arr("logit", "logloss")
    d_auc = a_lda - a_log
    d_brier = b_lda - b_log
    d_loss = l_lda - l_log
    msk = np.isfinite(d_auc)
    agg["stats"] = stats
    agg["paired"] = {
        "d_auc": [round(float(v), 6) for v in d_auc],
        "d_brier": [round(float(v), 6) for v in d_brier],
        "d_logloss": [round(float(v), 6) for v in d_loss],
        "d_auc_mean": float(np.mean(d_auc[msk])),
        "d_auc_ci": boot_ci(d_auc[msk].tolist(), rng=rng_b),
        "d_brier_mean": float(np.nanmean(d_brier)),
        "d_brier_ci": boot_ci(d_brier[np.isfinite(d_brier)].tolist(), rng=rng_b),
        "d_logloss_mean": float(np.nanmean(d_loss)),
        "d_logloss_ci": boot_ci(d_loss[np.isfinite(d_loss)].tolist(), rng=rng_b),
        "lda_rel_bayes": stats["lda"]["auc"] - float(bayes),
        "logit_rel_bayes": stats["logit"]["auc"] - float(bayes),
    }
    dirs = [r["dir"] for r in reps if r.get("dir")]
    if dirs:
        agg["dir"] = {"cos_mean": float(np.nanmean([x["cos_mean"] for x in dirs])),
                      "cos_lo": float(np.nanmean([x["cos_lo"] for x in dirs])),
                      "cos_hi": float(np.nanmean([x["cos_hi"] for x in dirs])),
                      "lda_ang_sd_mean": float(np.nanmean([x["lda_ang_sd"] for x in dirs])),
                      "logit_ang_sd_mean": float(np.nanmean([x["logit_ang_sd"] for x in dirs])),
                      "n_with_dir": len(dirs)}
    if any("qda" in r for r in reps):
        q = [r["qda"] for r in reps if "qda" in r]
        agg["qda"] = {k: float(np.nanmean([x[k] for x in q])) for k in ("auc", "brier", "logloss")}
    fkeys = sorted({k for r in reps for k in r["lda"].get("by_factor", {})}, key=float)
    if fkeys:
        fbd = {}
        for key in fkeys:
            a = np.array([r["lda"]["by_factor"][key]["auc"] for r in reps if key in r["lda"].get("by_factor", {})], float)
            b = np.array([r["lda"]["by_factor"][key]["brier"] for r in reps if key in r["lda"].get("by_factor", {})], float)
            dd = a - np.array([r["logit"]["auc"] for r in reps if key in r["lda"].get("by_factor", {})], float)
            fbd[key] = {"auc": float(np.nanmean(a)), "brier": float(np.nanmean(b)),
                        "delta_lw": float(np.nanmean([r["lda"]["by_factor"][key]["delta"] for r in reps
                                                      if key in r["lda"].get("by_factor", {})])),
                        "d_auc_vs_logit": float(np.nanmean(dd)),
                        "d_auc_vs_logit_ci": boot_ci(dd[np.isfinite(dd)].tolist(), rng=rng_b)}
        agg["lda_by_factor"] = fbd
    plots = [r["plot"] for r in reps if r.get("plot")]
    if plots:
        agg["plot2d"] = plots[:2]
    return agg


# ---------------- 格点缓存 ----------------
def point_tag(stage, cfg):
    t = "n%d_d%d_lam%g_g%g" % (cfg["n"], cfg["d"], cfg["lam"], cfg["gamma"])
    if cfg.get("factors"):
        t += "_f" + "-".join("%g" % f for f in cfg["factors"])
    if cfg.get("qda"):
        t += "_qda"
    if cfg.get("stability"):
        t += "_st"
    if cfg.get("plot2d"):
        t += "_p2"
    return t


def run_point(cfg, stage, cache_dir, nrep, alphas, bayes_m, force=False):
    cpath = os.path.join(cache_dir, "point_%s_%s.json" % (stage, point_tag(stage, cfg)))
    if os.path.exists(cpath) and not force:
        with open(cpath, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        # 缓存只在质量够格时生效：quick 40-rep 产物在 full 请求下重算；error 产物不算命中
        if obj.get("n_rep", 0) >= nrep and len(obj.get("alphas", [])) >= len(alphas) and "error" not in obj:
            return obj
    base = SEED0 * 1000 + crc32_of(json.dumps(cfg, sort_keys=True))
    bayes = bayes_auc_cached(cfg["d"], cfg["lam"], cfg["gamma"], cache_dir, bayes_m)
    t0 = time.time()
    reps = []
    for r in range(nrep):
        rec = run_rep(cfg, np.random.default_rng(point_seed(base, r)), alphas)
        if rec is not None:
            reps.append(rec)
    if not reps:
        agg = {"config": cfg, "error": "no successful reps", "n_rep": 0, "runtime_s": time.time() - t0}
    else:
        agg = aggregate(cfg, reps, bayes, time.time() - t0)
    os.makedirs(cache_dir, exist_ok=True)
    agg["alphas"] = [float(a) for a in alphas]
    with open(cpath, "w", encoding="utf-8") as fh:
        json.dump(agg, fh, ensure_ascii=False)
    return agg


def write_stage(stage, points, results_dir):
    os.makedirs(results_dir, exist_ok=True)
    out = {"stage": stage, "seed0": SEED0, "numpy_version": np.__version__,
           "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "points": points}
    p = os.path.join(results_dir, "%s.json" % stage)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return p


# ---------------- 真实锚点（E6） ----------------
def read_csv_rows(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.reader(fh):
            if not r or all(not c.strip() for c in r):
                continue
            rows.append([c.strip() for c in r])
    return rows


CANON_HEART = ["age", "sex", "chest_pain", "resting_bp", "serum_cholesterol", "fasting_blood_sugar",
               "resting_ecg", "max_heart_rate", "exercise_angina", "oldpeak", "st_slope",
               "major_vessels", "thal", "heart_disease_present"]
HEART_CAT = ["chest_pain", "resting_ecg", "st_slope", "thal"]


def load_heart():
    rows = read_csv_rows(HEART_PATH)
    has_header = any(ch.isalpha() for ch in rows[0][0])
    names = rows[0] if has_header else CANON_HEART
    data = rows[1:] if has_header else rows
    assert len(names) == len(data[0]), "heart header width mismatch: %d vs %d" % (len(names), len(data[0]))
    ti = names.index("heart_disease_present")
    y = np.array([int(float(r[ti])) for r in data])
    num_idx = [i for i, nm in enumerate(names) if i != ti and nm not in HEART_CAT]
    Xn = np.array([[float(r[i]) for i in num_idx] for r in data])
    feat_names = [names[i] for i in num_idx]
    mats = [Xn]
    for c in HEART_CAT:
        j = names.index(c)
        vals = np.array([float(r[j]) for r in data])
        levels = np.unique(vals)
        for lv in levels[1:]:
            mats.append((vals == lv).astype(float).reshape(-1, 1))
            feat_names.append("%s=%g" % (c, lv))
    return np.hstack(mats), y, feat_names


BCW_BASE = ["radius", "texture", "perimeter", "area", "smoothness", "compactness",
            "concavity", "concave_points", "symmetry", "fractal_dimension"]
BCW_NAMES = BCW_BASE + ["se_" + s for s in BCW_BASE] + ["worst_" + s for s in BCW_BASE]


def _is_num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def load_bcw():
    rows = read_csv_rows(BCW_PATH)
    data = [r for r in rows if len(r) == 31 and _is_num(r[0])]
    arr = np.array([[float(x) for x in r] for r in data])
    assert arr.shape == (569, 31), arr.shape
    X = arr[:, :30]
    y = (arr[:, 30] == 0).astype(int)   # malignant(原始编码 0) → 正类
    return X, y, list(BCW_NAMES)


def load_pima(miss0=False):
    rows = read_csv_rows(PIMA_PATH)
    names = rows[0]
    arr = np.array([[float(x) for x in r] for r in rows[1:]])
    X = arr[:, :8]
    y = arr[:, 8].astype(int)
    if miss0:   # Glucose/BP/Skin/Insulin/BMI（列 1..5）任一为 0 → 整行剔除（UCI 完整病例版）
        keep = np.all(X[:, 1:6] != 0, axis=1)
        X, y = X[keep], y[keep]
    return X, y, list(names[:8])


def run_anchor(aid, nrep, alphas, cache_dir, force=False):
    cpath = os.path.join(cache_dir, "point_e6_%s.json" % aid)
    if os.path.exists(cpath) and not force:
        with open(cpath, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        if obj.get("n_rep", 0) >= nrep and len(obj.get("alphas", [])) >= len(alphas):
            return obj
    if aid == "heart":
        X, y, names = load_heart()
    elif aid == "bcw":
        X, y, names = load_bcw()
    elif aid == "pima_keep0":
        X, y, names = load_pima(miss0=False)
    elif aid == "pima_drop0":
        X, y, names = load_pima(miss0=True)
    else:
        raise ValueError(aid)
    d = X.shape[1]
    base = SEED0 * 1000 + crc32_of(aid)
    reps = []
    t0 = time.time()
    for r in range(nrep):
        rng = np.random.default_rng(point_seed(base, r))
        folds = stratified_kfold(y, 5, rng)
        oof = {"lda": np.zeros(len(y)), "lda_lw": np.zeros(len(y)), "logit": np.zeros(len(y))}
        alphas_used = []
        nonconv = pinv = 0
        for f in folds:
            mask = np.ones(len(y), dtype=bool)
            mask[f] = False
            st = Standardizer().fit(X[mask])
            Xs, Xt = st.transform(X[mask]), st.transform(X[f])
            lds, _ = fit_lda(Xs, y[mask], factors=(0.0, 1.0))
            pinv += int(lds[0.0]["pinv"])
            oof["lda"][f] = predict_lda(lds[0.0], Xt)
            oof["lda_lw"][f] = predict_lda(lds[1.0], Xt)
            sel = select_logistic(Xs, y[mask], alphas, rng)
            nonconv += int(not sel["conv"])
            alphas_used.append(float(sel["alpha"]))
            oof["logit"][f] = logistic_prob(sel, Xt)   # 必须与训练同尺度（标准化测试行），同 LDA 路径
        def m_pack(p, tau_base=None):
            tau_base = p if tau_base is None else tau_base
            out = {"auc": auc_score(y, p), "brier": brier(y, p), "logloss": logloss(y, p), "cost": {}}
            for w in COST_W:
                tau = cost_curve(tau_base, y, w)[1]
                out["cost"]["%g" % w] = {"tau_star": float(tau),
                                         "cost05": cost_at_tau(p, y, w, 0.5),
                                         "cost_star": cost_at_tau(p, y, w, tau)}
            return out
        reps.append({"lda": m_pack(oof["lda"]), "logit": m_pack(oof["logit"]),
                     "lda_lw": m_pack(oof["lda_lw"]),
                     "fail": {"irls_nonconv": nonconv, "lda_pinv": pinv},
                     "alphas_used": alphas_used,
                     "dir": stability(X, y, min(alphas_used), rng)})   # 最弱罚：最强收缩会虚高 cos，对 H5 保守
    rng_b = np.random.default_rng(SEED0)

    def summarize(key):
        m = {}
        for k in ("auc", "brier", "logloss"):
            v = [r[key][k] for r in reps]
            m[k] = float(np.nanmean(v))
            m[k + "_ci"] = boot_ci(v, rng=rng_b)
        for w in COST_W:
            m["cost_w%g_tau05" % w] = float(np.nanmean([r[key]["cost"]["%g" % w]["cost05"] for r in reps]))
            m["cost_w%g_tstar" % w] = float(np.nanmean([r[key]["cost"]["%g" % w]["cost_star"] for r in reps]))
            m["tau_mean_w%g" % w] = float(np.nanmean([r[key]["cost"]["%g" % w]["tau_star"] for r in reps]))
        return m

    d_auc = np.array([r["lda"]["auc"] - r["logit"]["auc"] for r in reps])
    d_brier = np.array([r["lda"]["brier"] - r["logit"]["brier"] for r in reps])
    d_loss = np.array([r["lda"]["logloss"] - r["logit"]["logloss"] for r in reps])
    cnt = {}
    for rr in reps:
        for a in rr["alphas_used"]:
            cnt[a] = cnt.get(a, 0) + 1
    dirs = [r["dir"] for r in reps if r["dir"] and r["dir"]["n_ok"] >= 5]
    out = {
        "config": {"stage": "e6", "anchor": aid, "n": int(len(y)), "d": int(d),
                   "pos_rate": float(y.mean()), "features": [str(x) for x in names],
                   "protocol": "repeated stratified 5-fold × %d；τ* 与指标同用池化 OOF" % nrep},
        "n_rep": nrep, "alphas": [float(a) for a in alphas],
        "runtime_s": round(time.time() - t0, 1), "numpy_version": np.__version__,
        "lda": summarize("lda"), "logit": summarize("logit"),
        "lda_lw": {k: summarize("lda_lw")[k] for k in ("auc", "brier", "logloss")},
        "paired": {
            "d_auc_mean": float(np.mean(d_auc)), "d_auc_ci": boot_ci(d_auc.tolist(), rng=rng_b),
            "d_brier_mean": float(np.mean(d_brier)), "d_brier_ci": boot_ci(d_brier.tolist(), rng=rng_b),
            "d_logloss_mean": float(np.mean(d_loss)), "d_logloss_ci": boot_ci(d_loss.tolist(), rng=rng_b),
            "per_rep_d_auc": [round(float(v), 6) for v in d_auc],
            "per_rep_d_brier": [round(float(v), 6) for v in d_brier],
            "per_rep_d_logloss": [round(float(v), 6) for v in d_loss],
            "note": "P4 做 Wilcoxon+Holm（n=10 配对）；per_rep_* 为原始差值",
        },
        "dir": {"cos_mean": float(np.nanmean([x["cos_mean"] for x in dirs])) if dirs else None,
                "lda_ang_sd_mean": float(np.nanmean([x["lda_ang_sd"] for x in dirs])) if dirs else None,
                "logit_ang_sd_mean": float(np.nanmean([x["logit_ang_sd"] for x in dirs])) if dirs else None,
                "n_dir_reps": len(dirs)},
        "fail": {"irls_nonconv": sum(r["fail"]["irls_nonconv"] for r in reps),
                 "lda_pinv": sum(r["fail"]["lda_pinv"] for r in reps)},
        "alpha_hist": {("%g" % a): c for a, c in sorted(cnt.items())},
    }
    os.makedirs(cache_dir, exist_ok=True)
    with open(cpath, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return out


def grids():
    g = {}
    g["e1"] = ([{"n": n, "d": 5, "lam": 0.0, "gamma": 1.0} for n in (40, 60, 100, 200, 500, 1000, 2000)] +
               [{"n": n, "d": 2, "lam": 0.0, "gamma": 1.0, "plot2d": True} for n in (40, 1000)])
    g["e2"] = [{"n": 300, "d": d, "lam": 0.0, "gamma": 1.0, "stability": True}
               for d in (2, 5, 10, 20, 30, 50)]
    g["e3a"] = [{"n": 300, "d": 5, "lam": l, "gamma": 1.0, "qda": (l == 1.0)}
                for l in (0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0)]
    g["e3b"] = [{"n": 300, "d": 5, "lam": 0.0, "gamma": gg} for gg in (1.0, 1.3, 1.6, 2.0)]
    g["e5"] = ([{"n": n, "d": 5, "lam": 0.0, "gamma": 1.0, "stability": True,
                 "factors": [0.0, 0.25, 0.5, 1.0]} for n in (40, 100, 200)] +
               [{"n": 300, "d": d, "lam": 0.0, "gamma": 1.0, "stability": True,
                 "factors": [0.0, 0.25, 0.5, 1.0]} for d in (20, 30, 50)])
    return g


STAGES = ["e1", "e2", "e3a", "e3b", "e5", "e6"]


# ---------------- selftest ----------------
def selftest():
    print("numpy", np.__version__)
    rng = np.random.default_rng(1)
    # 1. 代价曲线 vs 暴力枚举
    p = rng.random(80)
    yy = (rng.random(80) < 0.4).astype(int)
    for w in COST_W:
        cmin, caum, _ = cost_curve(p, yy, w)
        brute = min(((np.sum(p[yy == 0] > t) + w * np.sum(p[yy == 1] <= t), t) for t in TAU_GRID),
                    key=lambda x: x[0])
        assert abs(brute[0] - cmin) < 1e-9, (w, cmin, brute)
        assert abs(cost_at_tau(p, yy, w, 0.5) -
                   (np.sum(p[yy == 0] > 0.5) + w * np.sum(p[yy == 1] <= 0.5))) < 1e-12
    print("t1 cost-curve vs brute force  PASS")
    # 2. AUC 定义（sklearn 文档例）
    assert abs(auc_score(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.35, 0.8])) - 0.75) < 1e-12
    print("t2 AUC definition  PASS")
    # 3. IRLS 真梯度≈0（非分离数据、无罚）
    g = np.random.default_rng(3)
    Xs = g.standard_normal((400, 3))
    b_true = np.array([0.5, -1.2, 0.8, 0.4])
    ys = (sigmoid(design(Xs) @ b_true) > g.random(400)).astype(int)
    fits, _ = fit_logistic_path(Xs, ys, [1.0, 0.0])
    beta = fits[0.0][0]
    assert fits[0.0][1]
    grad = design(Xs).T @ (ys - sigmoid(design(Xs) @ beta))
    assert np.max(np.abs(grad)) < 1e-4, np.max(np.abs(grad))
    print("t3 IRLS grad %.2e  PASS" % np.max(np.abs(grad)))
    # 4. n=4000 时 LDA/logit 方向余弦高
    Xg, yg = gen_sample(4000, 5, 0.0, 1.0, np.random.default_rng(4))
    st = Standardizer().fit(Xg)
    Xgs = st.transform(Xg)
    lds, _ = fit_lda(Xgs, yg, factors=(0.0,))
    sel = select_logistic(Xgs, yg, [1.0, 0.1], np.random.default_rng(5))
    wl, wq = lds[0.0]["beta"], sel["beta_std"][1:]
    cos = float(wl @ wq / (np.linalg.norm(wl) * np.linalg.norm(wq)))
    assert cos > 0.95, cos
    print("t4 cos(LDA, logit) @4000 = %.3f  PASS" % cos)
    # 5. 贝叶斯天花板：λ=0 闭合 Φ(SEP/√2)=0.85；λ=0.6 二次 LR 仍 ≈ 天花板±容差
    closed = 0.5 * (1.0 + math.erf(SEP / 2.0))
    mc0 = bayes_auc_mc(5, 0.0, m=30000)
    assert abs(mc0 - closed) < 0.005, (mc0, closed)
    mc06 = bayes_auc_mc(5, 0.6, m=30000)
    assert 0.70 < mc06 < 0.95, mc06
    print("t5 bayes lam0=%.4f (closed %.4f) lam0.6=%.4f  PASS" % (mc0, closed, mc06))
    # 6. 泄漏哨兵：Standardizer 只用训练行 + lda_oof 形状
    X2 = np.vstack([np.random.default_rng(7).standard_normal((200, 2)) * 0.1,
                    np.random.default_rng(7).standard_normal((50, 2)) * 0.1 + 3.0])
    y2 = np.concatenate([np.zeros(200, int), np.ones(50, int)])
    tr2, te2 = strat_split(y2, 0.2, np.random.default_rng(8))
    stc = Standardizer().fit(X2[tr2])
    # 恒等式哨兵（阈值式不可靠：分层抽样下训练行均值≈全局均值，差只有~0.01 抽样噪声）
    assert np.max(np.abs(stc.mu - X2[tr2].mean(0))) < 1e-12, "scaler must fit train rows only"
    assert np.max(np.abs(stc.transform(X2[tr2]).mean(0))) < 1e-12
    o = lda_oof(X2[tr2], y2[tr2], np.random.default_rng(9))
    assert np.all(o >= 0) and np.all(o <= 1) and len(o) == len(tr2)
    print("t6 leakage sentinel + OOF  PASS")
    # 7. Brier 常数预测恒等式
    y3 = np.array([1, 0, 1, 1, 0])
    assert abs(brier(y3, np.full(5, y3.mean())) - y3.mean() * (1 - y3.mean())) < 1e-12
    print("t7 Brier identity  PASS")
    # 8. 完整 rep 冒烟（小格点，含全部 cfg 分支）
    rec = run_rep({"n": 60, "d": 2, "lam": 0.0, "gamma": 1.0, "stability": True, "plot2d": True},
                  np.random.default_rng(11), [1.0, 0.1])
    assert rec and np.isfinite(rec["lda"]["auc"]) and rec["dir"] is not None and "plot" in rec
    rec2 = run_rep({"n": 60, "d": 3, "lam": 1.0, "gamma": 1.6, "qda": True,
                    "factors": [0.0, 1.0]}, np.random.default_rng(12), [1.0])
    assert rec2 and "by_factor" in rec2["lda"] and "qda" in rec2
    print("t8 full reps smoke (stability/plot/qda/factors) lda=%.3f/%.3f  PASS" % (
        rec["lda"]["auc"], rec2["lda"]["auc"]))
    # 9. 锚点加载形状
    Xh, yh, nh = load_heart()
    Xb, yb, nb = load_bcw()
    Xp, yp, npn = load_pima()
    Xpd, ypd, npd = load_pima(miss0=True)
    assert len(yh) == 270 and yh.sum() == 120 and Xh.shape[1] == len(nh), (len(yh), yh.sum())
    assert Xb.shape == (569, 30) and yb.sum() == 212   # malignant 正类 212/569
    assert Xp.shape == (768, 8) and yp.sum() == 268
    assert Xpd.shape[0] < 768 and Xpd.shape[1] == 8
    print("t9 loaders heart %d×%d bcw %d×%d pima %d→%d/%d  PASS" % (
        Xh.shape[0], Xh.shape[1], Xb.shape[0], Xb.shape[1], Xp.shape[0], Xpd.shape[0], Xp.shape[0]))
    print("ALL SELFTESTS PASS")


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    help="all|smoke|selftest|逗号子集(e1,e2,e3a,e3b,e5,e6)")
    ap.add_argument("--nrep", type=int, default=None, help="合成 rep 数（默认 200；--quick=40）")
    ap.add_argument("--quick", action="store_true", help="nrep=40 + 3α + 小 MC（趋势预检）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, ".tmp", "linear-models", "results"))
    ap.add_argument("--cache", default=os.path.join(ROOT, ".tmp", "linear-models", "cache"))
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    alphas = ALPHAS_QUICK if args.quick else ALPHAS_FULL
    bayes_m = MC_QUICK if args.quick else MC_FULL
    nrep = args.nrep if args.nrep else (NREP_QUICK if args.quick else NREP_DEFAULT)
    arep = ANCHOR_REP_QUICK if args.quick else ANCHOR_REP_DEFAULT

    if args.stage == "selftest":
        selftest()
        return
    if args.stage == "smoke":
        o = run_point({"n": 40, "d": 2, "lam": 0.0, "gamma": 1.0}, "smoke",
                      args.cache, 5, alphas, bayes_m, args.force)
        if "error" in o:
            print("SMOKE FAILED:", o["error"])
            return
        print("smoke ok: lda=%.4f logit=%.4f Δ=%+.4f bayes=%.3f (%.1fs)" % (
            o["stats"]["lda"]["auc"], o["stats"]["logit"]["auc"],
            o["paired"]["d_auc_mean"], o["bayes_auc"], o["runtime_s"]))
        return

    stages = STAGES if args.stage == "all" else [s.strip() for s in args.stage.split(",") if s.strip()]
    gmap = grids()
    for st in stages:
        if st == "e6":
            pts = []
            for aid in ("heart", "bcw", "pima_keep0", "pima_drop0"):
                o = run_anchor(aid, arep, alphas, args.cache, args.force)
                pts.append(o)
                print("[e6/%-11s] n=%-4d lda=%.4f log=%.4f Δ=%+.4f (%.1fs)" % (
                    aid, o["config"]["n"], o["lda"]["auc"], o["logit"]["auc"],
                    o["paired"]["d_auc_mean"], o["runtime_s"]))
            write_stage("e6", pts, args.out)
            continue
        if st not in gmap:
            print("unknown stage", st)
            continue
        pts = []
        for cfg in gmap[st]:
            o = run_point(cfg, st, args.cache, nrep, alphas, bayes_m, args.force)
            if "error" in o:
                print("[%s] %s ERROR %s" % (st, point_tag(st, cfg), o["error"]))
            else:
                extra = " nonconv=%d" % o["stats"]["logit"]["n_irls_nonconv"] if o["stats"]["logit"]["n_irls_nonconv"] else ""
                print("[%s] %-34s bayes=%.3f lda=%.4f log=%.4f Δ=%+.4f%s (%.1fs)" % (
                    st, point_tag(st, cfg), o["bayes_auc"], o["stats"]["lda"]["auc"],
                    o["stats"]["logit"]["auc"], o["paired"]["d_auc_mean"], extra, o["runtime_s"]))
            pts.append(o)
        write_stage(st, pts, args.out)
    print("done ->", args.out)


if __name__ == "__main__":
    main()
