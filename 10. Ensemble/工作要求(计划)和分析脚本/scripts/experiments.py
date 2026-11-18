# -*- coding: utf-8 -*-
"""第 10 讲（集成学习与 Bootstrapping）学生实验：工作单 A–H 全部必做项。

数据：方案 A（WDBC），data/student 下 train/validation/locked-test-features，
data/teacher 下 locked-test-labels。协议：调参只用开发集，测试标签最后一次性揭示。

输出：results/*.json 与 results/fig/*.png
运行：python scripts/experiments.py
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["SimSun", "SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200

from sklearn.base import clone
from sklearn.ensemble import (AdaBoostClassifier, BaggingClassifier,
                              GradientBoostingClassifier, RandomForestClassifier)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (balanced_accuracy_score, confusion_matrix,
                             log_loss, roc_auc_score, roc_curve)
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier, export_text, _tree

BASE = Path(__file__).resolve().parents[1]
RES = BASE / "results"
FIG = RES / "fig"
RES.mkdir(exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)
SEED = 1010
LABEL = "malignant"


# ----------------------------------------------------------------- 数据
def load_all():
    tr = pd.read_csv(BASE / "data/student/train.csv")
    va = pd.read_csv(BASE / "data/student/validation.csv")
    te = pd.read_csv(BASE / "data/student/locked-test-features.csv")
    lab = pd.read_csv(BASE / "data/teacher/locked-test-labels.csv")
    feats = [c for c in tr.columns if c not in {"sample_id", LABEL}]
    te = te.merge(lab, on="sample_id", how="left")
    return tr, va, te, feats


def score_of(model, X):
    return model.decision_function(X) if hasattr(model, "decision_function") \
        else model.predict_proba(X)[:, 1]


def metrics(model, X, y):
    p = score_of(model, X)
    pred = model.predict(X)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"roc_auc": float(roc_auc_score(y, p)),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "sensitivity": float(tp / (tp + fn)), "specificity": float(tn / (tn + fp)),
            "train_logloss": None, "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}


def model_zoo():
    return {
        "single_tree": DecisionTreeClassifier(max_depth=4, random_state=SEED),
        "bagging": BaggingClassifier(estimator=DecisionTreeClassifier(max_depth=None, random_state=SEED),
                                     n_estimators=100, max_features=1.0, random_state=SEED, n_jobs=1),
        "random_forest": RandomForestClassifier(n_estimators=100, max_features="sqrt",
                                                random_state=SEED, n_jobs=1),
        "adaboost": AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=1, random_state=SEED),
                                       n_estimators=50, random_state=SEED),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=100, random_state=SEED),
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, random_state=SEED)),
        "rbf_svm": make_pipeline(StandardScaler(), SVC(C=1, kernel="rbf", probability=True,
                                                      random_state=SEED)),
    }


R = {}  # 结果汇总


# ----------------------------------------------------------------- A. 决策树
def part_A(tr, va, feats):
    X, y, Xv, yv = tr[feats], tr[LABEL], va[feats], va[LABEL]
    A = {}

    # A1 读示例树（max_depth=2）
    t2 = DecisionTreeClassifier(max_depth=2, random_state=SEED).fit(X, y)
    A["tree_text_d2"] = export_text(t2, feature_names=feats, decimals=2, show_weights=True)
    tree = t2.tree_
    A["tree_nodes"] = [
        {"node": i,
         "feature": (feats[tree.feature[i]] if tree.feature[i] >= 0 else "LEAF"),
         "threshold": (float(tree.threshold[i]) if tree.feature[i] >= 0 else None),
         "samples": int(tree.n_node_samples[i]),
         "value": [float(v) for v in tree.value[i][0]],
         "impurity": float(tree.impurity[i])}
        for i in range(tree.node_count)]

    # 手推：worst perimeter = 120, mean concave points = 0.08
    sample = dict(zip(feats, [0] * len(feats)))
    sample["worst perimeter"] = 120.0
    sample["mean concave points"] = 0.08
    xs = np.array([[sample[f] for f in feats]])
    leaf = t2.apply(xs)[0]
    A["sample_path"] = {"sample": {"worst perimeter": 120.0, "mean concave points": 0.08},
                        "leaf_node": int(leaf),
                        "leaf_value": [float(v) for v in tree.value[leaf][0]],
                        "leaf_samples": int(tree.n_node_samples[leaf]),
                        "proba_malignant": float(t2.predict_proba(xs)[0][1])}

    # 根节点信息
    A["root"] = {"feature": feats[tree.feature[0]], "threshold": float(tree.threshold[0]),
                 "gini": float(tree.impurity[0]), "samples": int(tree.n_node_samples[0]),
                 "value": [float(v) for v in tree.value[0][0]]}

    # A3 深度比较
    rows = []
    for d in [1, 2, 3, 4, None]:
        m = DecisionTreeClassifier(max_depth=d, random_state=SEED).fit(X, y)
        rows.append({"max_depth": ("None" if d is None else d),
                     "train_acc": float(m.score(X, y)), "valid_acc": float(m.score(Xv, yv)),
                     "train_auc": float(roc_auc_score(y, m.predict_proba(X)[:, 1])),
                     "valid_auc": float(roc_auc_score(yv, m.predict_proba(Xv)[:, 1])),
                     "n_leaves": int(m.get_n_leaves()),
                     "train_logloss": float(log_loss(y, m.predict_proba(X)[:, 1])),
                     "valid_logloss": float(log_loss(yv, m.predict_proba(Xv)[:, 1]))})
    A["depth_table"] = rows

    # A4 bootstrap 根节点变化（30 次，max_depth=3）
    rng = np.random.default_rng(SEED)
    roots = []
    for _ in range(30):
        idx = rng.choice(len(y), size=len(y), replace=True)
        m = DecisionTreeClassifier(max_depth=3, random_state=SEED).fit(X.iloc[idx], y.iloc[idx])
        roots.append({"feature": feats[m.tree_.feature[0]], "threshold": float(m.tree_.threshold[0])})
    dfr = pd.DataFrame(roots)
    A["bootstrap_roots"] = {
        "n_refits": 30,
        "feature_counts": dfr["feature"].value_counts().to_dict(),
        "threshold_min": float(dfr["threshold"].min()), "threshold_max": float(dfr["threshold"].max()),
        "threshold_mean": float(dfr["threshold"].mean()), "threshold_sd": float(dfr["threshold"].std(ddof=1)),
        "unique_trees_root_pairs": int(dfr.drop_duplicates().shape[0]),
        "details": roots,
    }
    return A


# ----------------------------------------------------------------- B. 投票与方差
def part_B(tr, va, feats):
    B = {}
    tab = pd.DataFrame({
        "sample": ["A", "B", "C", "D"], "y": [1, 0, 1, 0],
        "p1": [0.80, 0.20, 0.35, 0.15], "p2": [0.70, 0.60, 0.75, 0.25], "p3": [0.45, 0.65, 0.80, 0.70]})
    tab["hard"] = tab[["p1", "p2", "p3"]].apply(lambda r: int(round(r.mean())), axis=1)
    tab["hard_vote"] = tab[["p1", "p2", "p3"]].apply(
        lambda r: (int(r["p1"] >= .5) + int(r["p2"] >= .5) + int(r["p3"] >= .5)) > 1, axis=1).astype(int)
    tab["soft_vote"] = (tab[["p1", "p2", "p3"]].mean(axis=1) >= .5).astype(int)
    tab["hard_correct"] = tab["hard_vote"] == tab["y"]
    tab["soft_correct"] = tab["soft_vote"] == tab["y"]
    B["vote_table"] = tab.round(3).to_dict(orient="records")

    # 方差公式：rho 与 B 的数值
    sigma2, rho = 0.25, 0.5
    grid = []
    for r_ in [0.0, 0.3, 0.7, 0.95, 1.0]:
        row = {"rho": r_}
        for b in [1, 5, 10, 50, 100, 1000]:
            row["B=%d" % b] = round(r_ * sigma2 + (1 - r_) * sigma2 / b, 4)
        grid.append(row)
    B["variance_grid"] = grid

    # 实测：树间预测相关系数（bootstrap 树对验证集的概率）
    X, y, Xv = tr[feats], tr[LABEL], va[feats]
    rng = np.random.default_rng(SEED)
    probs, errs = [], []
    for _ in range(100):
        idx = rng.choice(len(y), size=len(y), replace=True)
        m = DecisionTreeClassifier(random_state=SEED).fit(X.iloc[idx], y.iloc[idx])
        p = m.predict_proba(Xv)[:, 1]
        probs.append(p)
        errs.append(((p >= .5).astype(int) != va[LABEL].values).astype(float))
    probs = np.array(probs)
    C = np.corrcoef(probs)
    iu = np.triu_indices_from(C, k=1)
    corr = C[iu]
    B["tree_correlation"] = {"mean": float(corr.mean()), "median": float(np.median(corr)),
                             "min": float(corr.min()), "max": float(corr.max()),
                             "share_above_0.9": float((corr > .9).mean())}
    Ec = np.corrcoef(np.array(errs))
    B["error_correlation"] = {"mean": float(Ec[np.triu_indices_from(Ec, k=1)].mean())}

    # 单树误差率、bagging 误差率、理论界（多数票）
    err_single = float(np.mean(errs))
    ens_err = float(np.mean(((probs.mean(axis=0) >= .5).astype(int) != va[LABEL].values)))
    rho_e = float(Ec[np.triu_indices_from(Ec, k=1)].mean())
    B["error_rates"] = {"single_tree_mean_error": err_single, "bagging_soft_vote_error": ens_err,
                        "error_corr": rho_e, "n_trees": 100}

    # 每棵树在交叉验证中被选中的次数（跨 500 次重抽样）
    Bv = 500
    cnt = np.zeros(len(Xv))
    for _ in range(Bv):
        j = np.random.default_rng(SEED).choice(len(Xv), size=len(Xv), replace=False)
        cnt[j] += 1
    B["valid_coverage"] = {"draws": Bv, "times_per_sample": cnt.tolist(),
                           "min": int(cnt.min()), "max": int(cnt.max()),
                           "share_never": float((cnt == 0).mean())}
    return B


# ----------------------------------------------------------------- C. Bootstrap
def part_C():
    C = {}
    # C1 手算例
    rng = np.random.default_rng(SEED)
    ex = rng.integers(1, 6, size=5).tolist()
    C["example_draw"] = {"indices": [1, 2, 3, 4, 5], "draw": ex,
                         "oob": sorted(set([1, 2, 3, 4, 5]) - set(ex)),
                         "duplicates": {str(k): ex.count(k) for k in set(ex) if ex.count(k) > 1}}

    # C2 模拟
    for n in (5, 455):
        sims = []
        r = np.random.default_rng(SEED)
        for _ in range(1000):
            idx = r.integers(0, n, size=n)
            sims.append(len(np.unique(idx)) / n)
        sims = np.array(sims)
        C["sim_n%d" % n] = {"n": n, "unique_mean": float(sims.mean()), "unique_sd": float(sims.std(ddof=1)),
                            "oob_mean": float(1 - sims.mean()),
                            "theory_unique": float(1 - (1 - 1 / n) ** n),
                            "theory_oob_limit": float(np.exp(-1)),
                            "min": float(sims.min()), "max": float(sims.max())}

    # 不同样本比例随重复次数收敛
    r = np.random.default_rng(SEED)
    n = 455
    uniq = []
    seen = set()
    for _ in range(1000):
        seen |= set(r.integers(0, n, size=n).tolist())
        uniq.append(len(seen) / n)
    C["convergence"] = {"curve": [round(float(v), 4) for v in uniq[::1]]}
    return C


# ----------------------------------------------------------------- D. 单树 / bagging / RF
def part_D(tr, va, feats):
    D = {}
    X, y, Xv, yv = tr[feats], tr[LABEL], va[feats], va[LABEL]
    zoo = {k: model_zoo()[k] for k in ("single_tree", "bagging", "random_forest")}

    rows, fitted = [], {}
    for k, m in zoo.items():
        m.fit(X, y)
        fitted[k] = m
        r = metrics(m, Xv, yv)
        r["model"] = k
        rows.append(r)
    D["comparison"] = rows

    # 稳定性：30 次共享 bootstrap 重训练
    rng = np.random.default_rng(SEED)
    idxs = [rng.choice(len(y), size=len(y), replace=True) for _ in range(30)]
    stab = []
    stab_probs = {}
    for k in ("single_tree", "bagging", "random_forest"):
        P = np.array([clone(zoo[k]).fit(X.iloc[i], y.iloc[i]).predict_proba(Xv)[:, 1] for i in idxs])
        stab_probs[k] = P
        share = (P >= .5).mean(axis=0)
        stab.append({"model": k, "prediction_sd_mean": float(P.std(axis=0, ddof=1).mean()),
                     "prediction_sd_max": float(P.std(axis=0, ddof=1).max()),
                     "class_flip_rate": float(((share > 0) & (share < 1)).mean()),
                     "mean_auc": float(np.mean([roc_auc_score(yv, p) for p in P])),
                     "sd_auc": float(np.std([roc_auc_score(yv, p) for p in P], ddof=1))})
    D["stability"] = stab

    # 树数曲线
    curve = []
    for n in (1, 10, 50, 100, 300):
        for name, mk in (("bagging", lambda: BaggingClassifier(
                            estimator=DecisionTreeClassifier(random_state=SEED), n_estimators=n,
                            max_features=1.0, oob_score=n >= 50, random_state=SEED)),
                         ("random_forest", lambda: RandomForestClassifier(
                            n_estimators=n, max_features="sqrt", oob_score=n >= 50, random_state=SEED))):
            m = mk().fit(X, y)
            curve.append({"model": name, "n_trees": n,
                          "valid_auc": float(roc_auc_score(yv, m.predict_proba(Xv)[:, 1])),
                          "valid_balacc": float(balanced_accuracy_score(yv, m.predict(Xv))),
                          "oob_acc": (float(m.oob_score_) if n >= 50 else None)})
    D["tree_curve"] = curve

    # 特征随机化隔离：RF max_features=1.0 vs sqrt
    iso = []
    for mf in ("sqrt", 1.0):
        m = RandomForestClassifier(n_estimators=100, max_features=mf, random_state=SEED).fit(X, y)
        iso.append({"max_features": str(mf), "valid_auc": float(roc_auc_score(yv, m.predict_proba(Xv)[:, 1])),
                    "valid_balacc": float(balanced_accuracy_score(yv, m.predict(Xv)))})
    D["feature_randomization"] = iso

    # 重要性
    forest = RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=1).fit(X, y)
    perm = permutation_importance(forest, Xv, yv, scoring="roc_auc", n_repeats=20, random_state=SEED, n_jobs=1)
    imp = pd.DataFrame({"feature": feats, "impurity": forest.feature_importances_,
                        "perm_mean": perm.importances_mean, "perm_sd": perm.importances_std})
    imp = imp.sort_values("impurity", ascending=False)
    D["importance_corr"] = {"pearson": float(np.corrcoef(imp["impurity"], imp["perm_mean"])[0, 1]),
                            "spearman": float(imp["impurity"].rank().corr(imp["perm_mean"].rank()))}
    D["importance"] = imp.round(5).to_dict(orient="records")
    D["importance_spearman"] = float(imp["impurity"].rank().corr(imp["perm_mean"].rank()))
    # 相关矩阵
    COR = X.corr()
    pairs = []
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            r = COR.loc[a, b]
            if abs(r) > 0.9:
                pairs.append({"a": a, "b": b, "r": float(r)})
    D["high_corr_pairs"] = sorted(pairs, key=lambda d: -abs(d["r"]))
    D["n_high_corr_pairs"] = len(pairs)
    # 单独置换 top3 特征的 AUC 下降
    top3 = imp.head(3)["feature"].tolist()
    drops = []
    for f in top3:
        Xp = Xv.copy()
        rr = np.random.default_rng(SEED)
        vals = Xp[f].values.copy()
        rr.shuffle(vals)
        Xp[f] = vals
        drops.append({"feature": f, "auc_drop": float(roc_auc_score(yv, forest.predict_proba(Xv)[:, 1])
                                                      - roc_auc_score(yv, forest.predict_proba(Xp)[:, 1]))})
    D["single_feature_drop"] = drops
    return D, fitted, stab_probs


# ----------------------------------------------------------------- E. Boosting
def part_E(tr, va, feats):
    E = {}
    X, y, Xv, yv = tr[feats], tr[LABEL], va[feats], va[LABEL]
    Xa, ya = X.values, y.values

    # E1 手写 AdaBoost（SAMME 两分类）追踪样本权重
    n = len(ya)
    w = np.ones(n) / n
    yy = np.where(ya == 1, 1, -1)
    traj, alphas, epsilons, errs_curve = [], [], [], []
    # 选定 4 个追踪样本：2 恶性 + 2 良性，覆盖易/难
    track = [int(np.where(ya == 1)[0][0]), int(np.where(ya == 1)[0][1]),
             int(np.where(ya == 0)[0][0]), int(np.where(ya == 0)[0][1])]
    hard_so_far = np.zeros(n)
    for_t = []
    stumps = []
    for t in range(20):
        m = DecisionTreeClassifier(max_depth=1, random_state=SEED)
        m.fit(Xa, ya, sample_weight=w)
        h = np.where(m.predict(Xa) == 1, 1, -1)
        wrong = (h != yy).astype(float)
        eps = float(np.clip((w * wrong).sum(), 1e-10, 1 - 1e-10))
        alpha = 0.5 * np.log((1 - eps) / eps)
        w = w * np.exp(-alpha * yy * h)
        w = w / w.sum()
        stumps.append((m, alpha))
        F_t = sum(a_ * np.where(mm.predict(Xa) == 1, 1, -1) for mm, a_ in stumps)
        alphas.append(float(alpha)); epsilons.append(eps)
        errs_curve.append(float((wrong * w).sum() / w.sum()))
        hard_so_far += wrong
        # 记录“更新后”与“下一轮实际使用的（再归一化）权重”，后者才与图 5 的轨迹一致
        w_next = w * np.exp(-alpha * yy * h)
        w_next = w_next / w_next.sum()
        for_t.append({"round": t + 1, "epsilon": eps, "alpha": alpha,
                      "tracked_weights": [float(w[i]) for i in track],
                      "tracked_weights_next": [float(w_next[i]) for i in track],
                      "tracked_wrong": [int(wrong[i]) for i in track],
                      "train_acc_cum": float((np.sign(F_t) == yy).mean()),
                      "train_acc_from_weights": float(((w * (h == yy)).sum() / w.sum()))})
    E["adaboost_manual"] = {"tracked_ids": [tr["sample_id"].iloc[i] for i in track],
                            "tracked_labels": [int(ya[i]) for i in track],
                            "rounds": for_t, "epsilon": epsilons, "alpha": alphas}

    # 用 sklearn AdaBoost 得到训练/验证误差曲线
    ada = AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=1, random_state=SEED),
                             n_estimators=200, random_state=SEED).fit(X, y)
    st_tr = [float(log_loss(y, p[:, 1])) for p in ada.staged_predict_proba(X)]
    st_va = [float(log_loss(yv, p[:, 1])) for p in ada.staged_predict_proba(Xv)]
    acc_tr = [float(((p[:, 1] >= .5).astype(int) == y.values).mean()) for p in ada.staged_predict_proba(X)]
    acc_va = [float(((p[:, 1] >= .5).astype(int) == yv.values).mean()) for p in ada.staged_predict_proba(Xv)]
    E["adaboost_curve"] = {"train_logloss": st_tr, "valid_logloss": st_va,
                           "train_acc": acc_tr, "valid_acc": acc_va,
                           "estimator_errors": [float(e) for e in ada.estimator_errors_[:200]]}

    # E2 梯度提升的负梯度 y-p
    gb = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, random_state=SEED).fit(X, y)
    # 追踪 3 个样本的前 6 阶段 p 与残差
    pick = [int(np.where(ya == 1)[0][0]), int(np.where(ya == 1)[0][2]), int(np.where(ya == 0)[0][3])]
    traj2 = []
    for t, p in enumerate(gb.staged_predict_proba(X)):
        if t >= 6:
            break
        p1 = p[:, 1]
        traj2.append({"stage": t + 1,
                      "p": [float(p1[i]) for i in pick],
                      "residual_y_minus_p": [float(y.values[i] - p1[i]) for i in pick]})
    E["gb_gradient"] = {"sample_ids": [tr["sample_id"].iloc[i] for i in pick],
                        "labels": [int(y.values[i]) for i in pick], "trajectory": traj2}

    # E3 learning_rate × n_estimators
    grid = {}
    for lr in (0.01, 0.05, 0.1, 0.5):
        m = GradientBoostingClassifier(n_estimators=300, learning_rate=lr, random_state=SEED).fit(X, y)
        tr_ll = [float(log_loss(y, p[:, 1])) for p in m.staged_predict_proba(X)]
        va_ll = [float(log_loss(yv, p[:, 1])) for p in m.staged_predict_proba(Xv)]
        va_auc = [float(roc_auc_score(yv, p[:, 1])) for p in m.staged_predict_proba(Xv)]
        grid[str(lr)] = {"train_logloss": tr_ll, "valid_logloss": va_ll, "valid_auc": va_auc,
                         "best_stage": int(np.argmin(va_ll)) + 1, "best_valid_logloss": float(np.min(va_ll)),
                         "valid_logloss_at_300": va_ll[-1], "train_logloss_at_300": tr_ll[-1]}
    E["learning_rate_grid"] = grid
    return E


# ----------------------------------------------------------------- F. 公平比较
def part_F(tr, va, te, feats):
    F = {}
    X, y, Xv, yv = tr[feats], tr[LABEL], va[feats], va[LABEL]
    zoo = model_zoo()
    names = ["logistic", "rbf_svm", "random_forest", "gradient_boosting", "single_tree", "bagging", "adaboost"]
    rows, fitted = [], {}
    for k in names:
        m = clone(zoo[k]).fit(X, y)
        fitted[k] = m
        r = metrics(m, Xv, yv)
        r["model"] = k
        r["valid_logloss"] = float(log_loss(yv, m.predict_proba(Xv)[:, 1]))
        rows.append(r)
    F["validation"] = rows

    dev = pd.concat([tr, va], ignore_index=True)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    cvrows = []
    for k in names:
        res = cross_validate(clone(zoo[k]), dev[feats], dev[LABEL], cv=cv, n_jobs=1,
                             scoring={"roc_auc": "roc_auc", "average_precision": "average_precision",
                                      "balanced_accuracy": "balanced_accuracy"},
                             return_estimator=False)
        cvrows.append({"model": k,
                       "auc_mean": float(res["test_roc_auc"].mean()), "auc_sd": float(res["test_roc_auc"].std(ddof=1)),
                       "ap_mean": float(res["test_average_precision"].mean()),
                       "balacc_mean": float(res["test_balanced_accuracy"].mean()),
                       "balacc_sd": float(res["test_balanced_accuracy"].std(ddof=1)),
                       "auc_folds": [float(v) for v in res["test_roc_auc"]]})
    F["cv"] = cvrows
    return F, fitted


# ----------------------------------------------------------------- G. 稳定性与不确定性
def part_G(te, feats, fitted):
    G = {}
    Xt, yt = te[feats], te[LABEL]
    print("test set:", Xt.shape, "positive:", int(yt.sum()))
    names = ["logistic", "rbf_svm", "random_forest", "gradient_boosting"]
    preds = {k: fitted[k].predict_proba(Xt)[:, 1] for k in names}

    def boot_metric(p, idx, fn):
        return fn(yt.values[idx], (p[idx] >= .5).astype(int), p[idx])

    def auc_fn(y_, pred_, p_):
        return roc_auc_score(y_, p_)

    def bal_fn(y_, pred_, p_):
        return balanced_accuracy_score(y_, (p_ >= .5).astype(int))
    rng = np.random.default_rng(SEED)
    pos = np.where(yt.values == 1)[0]
    neg = np.where(yt.values == 0)[0]
    B = 2000
    idxs = []
    for _ in range(B):
        idxs.append(np.concatenate([rng.choice(pos, len(pos), replace=True),
                                    rng.choice(neg, len(neg), replace=True)]))

    def fast_auc(y_, s_):
        """排序法 AUC，用于 bootstrap 循环（与 sklearn 结果一致，快 1~2 个数量级）。"""
        n_pos = int((y_ == 1).sum())
        n_neg = len(y_) - n_pos
        if n_pos == 0 or n_neg == 0:
            return 0.5
        order = np.argsort(s_, kind="mergesort")
        ranks = np.empty(len(s_), dtype=float)
        ss = s_[order]
        i = 0
        while i < len(ss):
            j = i
            while j + 1 < len(ss) and ss[j + 1] == ss[i]:
                j += 1
            ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return float((ranks[y_ == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))

    point = {}
    ci = {}
    for k in names:
        point[k] = {"auc": float(roc_auc_score(yt, preds[k])),
                    "balanced_accuracy": float(balanced_accuracy_score(yt, (preds[k] >= .5).astype(int)))}
        aucs = np.array([fast_auc(yt.values[i], preds[k][i]) for i in idxs])
        bals = np.array([bal_fn(yt.values[i], None, preds[k][i]) for i in idxs])
        ci[k] = {"auc_lo": float(np.percentile(aucs, 2.5)), "auc_hi": float(np.percentile(aucs, 97.5)),
                 "bal_lo": float(np.percentile(bals, 2.5)), "bal_hi": float(np.percentile(bals, 97.5))}

    diff = {}
    cache = {k: np.array([fast_auc(yt.values[i], preds[k][i]) for i in idxs]) for k in names}
    for a, b in (("random_forest", "logistic"), ("random_forest", "rbf_svm"),
                 ("gradient_boosting", "logistic"), ("random_forest", "gradient_boosting")):
        d = cache[a] - cache[b]
        diff["%s-%s" % (a, b)] = {"mean": float(d.mean()), "lo": float(np.percentile(d, 2.5)),
                                  "hi": float(np.percentile(d, 97.5)),
                                  "share_le_0": float((d <= 0).mean())}

    G.update({"n_test": int(len(yt)), "n_pos": int(yt.sum()), "point": point, "ci": ci, "diff": diff,
              "predictions": {k: [float(v) for v in preds[k]] for k in names},
              "ids": te["sample_id"].tolist(), "y": [int(v) for v in yt.values]})
    return G


# ----------------------------------------------------------------- 作图
def make_figs(A, B, C, D, E, F, G, stab_probs, va):
    feats = None
    # 图 1 深度曲线
    df = pd.DataFrame(A["depth_table"])
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    x = np.arange(len(df))
    ax.plot(x, df["train_acc"], "o-", label="训练准确率")
    ax.plot(x, df["valid_acc"], "s--", label="验证准确率")
    ax.set_xticks(x); ax.set_xticklabels([str(v) for v in df["max_depth"]])
    ax.set_xlabel("max_depth"); ax.set_ylabel("准确率"); ax.set_ylim(0.9, 1.005)
    ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / "fig1_depth.png"); plt.close(fig)

    # 图 2 树数曲线
    dfc = pd.DataFrame(D["tree_curve"])
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.4))
    for name, g in dfc.groupby("model"):
        axs[0].plot(g["n_trees"], g["valid_auc"], "o-", label=name)
        sub = g.dropna(subset=["oob_acc"])
        if len(sub):
            axs[1].plot(sub["n_trees"], sub["oob_acc"], "o-", label=name)
    axs[0].set_xscale("log"); axs[0].set_xlabel("树数 B"); axs[0].set_ylabel("验证 ROC-AUC")
    axs[0].legend(frameon=False, fontsize=7); axs[0].grid(alpha=.3)
    axs[1].set_xscale("log"); axs[1].set_xlabel("树数 B"); axs[1].set_ylabel("袋外准确率")
    axs[1].legend(frameon=False, fontsize=7); axs[1].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / "fig2_trecount.png"); plt.close(fig)

    # 图 3 稳定性
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.4))
    labels = {"single_tree": "单树", "bagging": "Bagging", "random_forest": "随机森林"}
    for k, P in stab_probs.items():
        axs[0].hist(P.std(axis=0, ddof=1), bins=20, alpha=.6, label=labels[k])
    axs[0].set_xlabel("预测概率的 SD（30 次重抽样）"); axs[0].set_ylabel("验证样本数")
    axs[0].legend(frameon=False, fontsize=7); axs[0].grid(alpha=.3)
    st = pd.DataFrame(D["stability"])
    axs[1].bar(range(len(st)), st["class_flip_rate"], color=["#c44", "#48a", "#2a6"])
    axs[1].set_xticks(range(len(st))); axs[1].set_xticklabels([labels[k] for k in st["model"]], fontsize=8)
    axs[1].set_ylabel("类别翻转率"); axs[1].grid(alpha=.3, axis="y")
    fig.tight_layout(); fig.savefig(FIG / "fig3_stability.png"); plt.close(fig)

    # 图 4 boosting 曲线
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.5))
    for lr, g in E["learning_rate_grid"].items():
        axs[0].plot(np.arange(1, len(g["valid_logloss"]) + 1), g["valid_logloss"], label="lr=%s" % lr)
        axs[1].plot(np.arange(1, len(g["train_logloss"]) + 1), g["train_logloss"], label="lr=%s" % lr)
    for ax, t in zip(axs, ["验证集 log-loss", "训练集 log-loss"]):
        ax.set_xlabel("boosting 阶段数"); ax.set_ylabel(t); ax.legend(frameon=False, fontsize=7); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / "fig4_boosting.png"); plt.close(fig)

    # 图 5 AdaBoost 权重轨迹
    AM = E["adaboost_manual"]
    rts = AM["rounds"]
    fig, ax = plt.subplots(figsize=(4.2, 2.5))
    W = np.array([r["tracked_weights_next"] for r in rts], dtype=float)
    rounds = np.array([r["round"] for r in rts], dtype=float)
    for j in range(W.shape[1]):
        lab = "样本%s (真值 %d)" % (str(AM["tracked_ids"][j])[-4:], AM["tracked_labels"][j])
        ax.plot(rounds, W[:, j], "o-", ms=2, label=lab)
    ax.set_xlabel("轮次 t"); ax.set_ylabel("样本权重 $w_i$"); ax.legend(frameon=False, fontsize=6)
    ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / "fig5_weights.png"); plt.close(fig)

    # 图 6 重要性
    imp = pd.DataFrame(D["importance"]).head(10)
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    yy = np.arange(len(imp))[::-1]
    ax.barh(yy + .2, imp["impurity"], height=.4, label="不纯度重要性")
    ax.barh(yy - .2, imp["perm_mean"], height=.4, label="置换重要性（AUC 下降）")
    ax.set_yticks(yy); ax.set_yticklabels(imp["feature"], fontsize=6)
    ax.legend(frameon=False, fontsize=7); ax.grid(alpha=.3, axis="x")
    fig.tight_layout(); fig.savefig(FIG / "fig6_importance.png"); plt.close(fig)

    # 图 7 验证集 ROC（在 make_roc 中另作）
    return


def make_roc(fitted, va, feats):
    fig, ax = plt.subplots(figsize=(3.4, 3.0))
    labels = {"single_tree": "单树", "bagging": "Bagging", "random_forest": "随机森林",
              "adaboost": "AdaBoost", "gradient_boosting": "梯度提升",
              "logistic": "逻辑回归", "rbf_svm": "RBF-SVM"}
    for k in ["single_tree", "bagging", "random_forest", "adaboost", "gradient_boosting"]:
        m = fitted[k]
        p = score_of(m, va[feats])
        fpr, tpr, _ = roc_curve(va[LABEL], p)
        ax.plot(fpr, tpr, lw=1.2, label="%s (%.3f)" % (labels[k], roc_auc_score(va[LABEL], p)))
    ax.plot([0, 1], [0, 1], "k--", lw=.6)
    ax.set_xlabel("假正率 $1-\\mathrm{specificity}$"); ax.set_ylabel("真正率 sensitivity")
    ax.legend(frameon=False, fontsize=6, loc="lower right"); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / "fig7_roc.png"); plt.close(fig)


def main():
    tr, va, te, feats = load_all()
    print("train", tr.shape, "valid", va.shape, "test", te.shape, "features", len(feats), flush=True)
    R["data"] = {"n_train": len(tr), "n_valid": len(va), "n_test": len(te),
                 "n_features": len(feats),
                 "pos_train": int(tr[LABEL].sum()), "pos_valid": int(va[LABEL].sum()),
                 "pos_test": int(te[LABEL].sum()),
                 "features": feats}
    R["A"] = part_A(tr, va, feats)
    R["B"] = part_B(tr, va, feats)
    R["C"] = part_C()
    R["D"], fitted, stab_probs = part_D(tr, va, feats)
    R["E"] = part_E(tr, va, feats)
    R["F"], fittedF = part_F(tr, va, te, feats)
    R["G"] = part_G(te, feats, fittedF)
    make_figs(R["A"], R["B"], R["C"], R["D"], R["E"], R["F"], R["G"], stab_probs, va)
    make_roc(fittedF, va, feats)
    (RES / "results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", RES / "results.json")


if __name__ == "__main__":
    main()