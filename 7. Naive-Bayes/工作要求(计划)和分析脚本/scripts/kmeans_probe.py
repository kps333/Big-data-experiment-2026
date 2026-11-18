"""验证「KMeans 分簇做诊断」这个想法。

跑法:  python scripts/kmeans_probe.py
只读 data/student/*.csv，不写任何文件。

回答三个问题:
  1. train.csv 里到底有多少种不同的症状组合? 每种组合的标签纯不纯?
  2. 纯 KMeans(无监督) 加一个簇->标签的映射, 在 train/validation 上能拿多少分?
  3. 如果按"查表 / 最近邻"来预测(即 KMeans 的极端情形 k=每种组合一个簇), 能拿多少分?
"""
from pathlib import Path
import itertools

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import accuracy_score, adjusted_rand_score, confusion_matrix
from sklearn.naive_bayes import BernoulliNB

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ['fever_ge_38', 'nausea', 'lumbar_pain',
            'urine_pushing', 'micturition_pain', 'burning_urethra']
TARGET = 'bladder_inflammation'

train = pd.read_csv(ROOT / 'data/student/train.csv')
val = pd.read_csv(ROOT / 'data/student/validation.csv')
test = pd.read_csv(ROOT / 'data/student/locked-test-features.csv')

Xtr, ytr = train[FEATURES].to_numpy(int), train[TARGET].to_numpy(int)
Xva, yva = val[FEATURES].to_numpy(int), val[TARGET].to_numpy(int)
Xte = test[FEATURES].to_numpy(int)

line = '-' * 78


def metrics(y, yhat):
    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    acc = accuracy_score(y, yhat)
    sens = tp / (tp + fn) if (tp + fn) else float('nan')
    spec = tn / (tn + fp) if (tn + fp) else float('nan')
    return acc, sens, spec, (tp, fn, fp, tn)


print(line)
print(f'train {Xtr.shape[0]} 条 / validation {Xva.shape[0]} 条 / '
      f'test {Xte.shape[0]} 条(无标签, 不评分)')
print(f'标签分布 train: {np.bincount(ytr)}   validation: {np.bincount(yva)}')

# ---------------------------------------------------------------- 1. 组合纯度
print(line)
print('[1] train.csv 里到底有几种症状组合?')
prof = train.groupby(FEATURES, sort=False)[TARGET].agg(n='count', pos='sum')
prof['neg'] = prof['n'] - prof['pos']
prof['pure'] = (prof['pos'].eq(0) | prof['pos'].eq(prof['n']))
display_prof = prof.reset_index()
for _, r in display_prof.iterrows():
    bits = ''.join(str(int(r[f])) for f in FEATURES)
    print(f"  {bits}  n={int(r['n']):>2}  阴性={int(r['neg']):>2} "
          f"阳性={int(r['pos']):>2}  {'纯' if r['pure'] else '混合'}")

n_prof = len(prof)
print(f'-> 共 {n_prof} 种组合; 其中混合标签的 {int((~prof["pure"]).sum())} 种')
print(f'-> 组合层面的天花板: 每种组合只能猜一个标签时, train 最多对 '
      f'{int(prof["n"].where(prof["pure"], prof[["pos", "neg"]].max(axis=1)).sum())} / {len(ytr)}')

# validation 的组合是否都出现过
tr_keys = set(map(tuple, Xtr))
seen = sum(1 for r in Xva if tuple(r) in tr_keys)
print(f'-> validation 里组合在训练集出现过的: {seen} / {len(Xva)}')

# ---------------------------------------------------------------- 2. KMeans 扫描
print(line)
print('[2] KMeans 分簇 + 簇内多数票 -> 标签 (纯无监督特征, 只用训练标签定簇名)')
print(f'{"k":>3} {"簇内阳性率":>22} {"train acc":>10} {"val acc":>8} '
      f'{"val sens":>9} {"val spec":>9} {"ARI":>6}')
rows = []
for k in range(2, min(n_prof, len(ytr)) + 1):
    km = KMeans(n_clusters=k, n_init=50, random_state=7).fit(Xtr)
    mapping = {}
    rates = []
    for c in range(k):
        mask = km.labels_ == c
        rate = ytr[mask].mean() if mask.any() else 0.0
        mapping[c] = int(rate >= 0.5)
        rates.append(f'{rate:.2f}({int(mask.sum())})')
    pred_tr = np.array([mapping[int(c)] for c in km.labels_])
    pred_va = np.array([mapping[int(c)] for c in km.predict(Xva)])
    acc_tr = accuracy_score(ytr, pred_tr)
    acc_va, sens_va, spec_va, _ = metrics(yva, pred_va)
    ari = adjusted_rand_score(ytr, km.labels_)
    rows.append((k, acc_tr, acc_va, sens_va, spec_va, ari))
    print(f'{k:>3} {" ".join(rates):>22} {acc_tr:>10.3f} {acc_va:>8.3f} '
          f'{sens_va:>9.3f} {spec_va:>9.3f} {ari:>6.3f}')

# ---------------------------------------------------------------- 3. 查表 / 最近邻
print(line)
print('[3] 查表 + 最近邻(k=每种组合一个簇的极端情形)')


def lookup_predict(X_train, y_train, Xq):
    agg = {}
    for r, t in zip(map(tuple, X_train), y_train):
        agg.setdefault(r, [0, 0])[int(t)] += 1
    prior = int(y_train.mean() >= 0.5)
    keys = np.array(list(agg.keys()), dtype=int)
    vals = np.array([agg[k][1] - agg[k][0] for k in agg])
    out = []
    for q in Xq:
        q = np.asarray(q, dtype=int)
        d = (keys != q).sum(axis=1)
        dmin = d.min()
        vote = vals[d == dmin].sum()          # >0 偏阳性, <0 偏阴性
        out.append(int(vote > 0) if vote != 0 else prior)
    return np.array(out)


for name, Xq, yq in (('train', Xtr, ytr), ('validation', Xva, yva)):
    yhat = lookup_predict(Xtr, ytr, Xq)
    acc, sens, spec, cm = metrics(yq, yhat)
    print(f'  {name:<11} acc={acc:.3f}  sens={sens:.3f}  spec={spec:.3f}  '
          f'混淆(tp,fn,fp,tn)={cm}')

# ---------------------------------------------------------------- 4. 参考: NB
print(line)
print('[4] 参考: 本课的 BernoulliNB(alpha=1)')
nb = BernoulliNB(alpha=1, binarize=None).fit(Xtr, ytr)
for name, Xq, yq in (('train', Xtr, ytr), ('validation', Xva, yva)):
    yhat = nb.predict(Xq)
    acc, sens, spec, cm = metrics(yq, yhat)
    print(f'  {name:<11} acc={acc:.3f}  sens={sens:.3f}  spec={spec:.3f}  '
          f'混淆(tp,fn,fp,tn)={cm}')

# ---------------------------------------------------------------- 5. k=2 的全局最优划分
print(line)
print('[5] 9 种组合上的全局最优 2 划分(穷举), 看 KMeans 是否找到了它')


def best_partition(U, w, k):
    n = len(U)
    best, best_sse = None, np.inf
    for assign in itertools.product(range(k), repeat=n):
        if len(set(assign)) < k:
            continue
        first = {}
        canon = []
        for a in assign:
            if a not in first:
                first[a] = len(first)
            canon.append(first[a])
        if canon != list(assign):
            continue
        sse = 0.0
        for c in range(k):
            idx = np.array([i for i in range(n) if assign[i] == c])
            ww, pts = w[idx].astype(float), U[idx].astype(float)
            mu = (pts * ww[:, None]).sum(0) / ww.sum()
            sse += float((ww * ((pts - mu) ** 2).sum(1)).sum())
        if sse < best_sse:
            best_sse, best = sse, assign
    return best, best_sse


U = prof.index.to_numpy(dtype=int)
w = prof['n'].to_numpy()
ybar = (prof['pos'] > prof['neg']).to_numpy().astype(int)

part, sse_opt = best_partition(U, w, 2)
print(f'  最优 2 划分 SSE={sse_opt:.2f}, 划分 = ')
for c in (0, 1):
    idx = [i for i, a in enumerate(part) if a == c]
    bits = [' '.join(str(b) for b in U[i]) for i in idx]
    labels = [ybar[i] for i in idx]
    print(f'    簇{c}: ' + ' | '.join(bits))
    print(f'           n={int(w[idx].sum()):>2}  多数标签={int(pd.Series(labels).mode()[0])}  '
          f'阳性率={w[idx][ybar[idx] == 1].sum() / w[idx].sum():.2f}')

label_split = np.array([ybar[i] for i in range(len(U))])
sse_lab = 0.0
for c in (0, 1):
    idx = np.where(label_split == c)[0]
    ww, pts = w[idx].astype(float), U[idx].astype(float)
    mu = (pts * ww[:, None]).sum(0) / ww.sum()
    sse_lab += float((ww * ((pts - mu) ** 2).sum(1)).sum())
print(f'  把「同标签」当作划分时的 SSE={sse_lab:.2f}  '
      f'(最优 2 划分比它{"小" if sse_opt < sse_lab else "大"}, '
      f'所以 KMeans 更愿意按别的东西切)')
print(line)