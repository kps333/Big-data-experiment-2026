"""弹性网 logistic 回归 vs 朴素贝叶斯：在这份数据上到底能不能分出高下。

跑法:  python scripts/logit_probe.py

要点:
  1. 这份数据「完全可分」(9 种组合, 每种标签纯), 无正则的 logistic MLE 不存在, 系数会发散。
  2. validation 只有 24 条且组合全被训练集覆盖, 任何模型都是 1.0 -> 超参选不出来。
  3. Bernoulli NB 在二元特征上本身就是线性分类器, 斜率 = logit(theta1) - logit(theta0),
     跟 logistic 的系数可以直接并排比较。
"""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.naive_bayes import BernoulliNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
FEAT = ['fever_ge_38', 'nausea', 'lumbar_pain',
        'urine_pushing', 'micturition_pain', 'burning_urethra']
TARGET = 'bladder_inflammation'

train = pd.read_csv(ROOT / 'data/student/train.csv')
val = pd.read_csv(ROOT / 'data/student/validation.csv')
Xtr, ytr = train[FEAT].to_numpy(int), train[TARGET].to_numpy(int)
Xva, yva = val[FEAT].to_numpy(int), val[TARGET].to_numpy(int)
line = '-' * 74


def report(tag, y, p, thr=0.5):
    yhat = (p >= thr).astype(int)
    print(f'  {tag:<16} acc={accuracy_score(y, yhat):.3f}  '
          f'log_loss={log_loss(y, np.clip(p, 1e-9, 1 - 1e-9)):.4f}  '
          f'brier={brier_score_loss(y, p):.4f}')


def scale_pipe(**kw):
    return make_pipeline(StandardScaler(),
                         LogisticRegression(penalty='elasticnet',
                                            solver='saga', max_iter=5000,
                                            random_state=7, **kw))


print(line)
print('[1] 完全可分时, 不加正则的 logistic 会怎样?')
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    big = make_pipeline(StandardScaler(),
                        LogisticRegression(penalty=None, solver='lbfgs',
                                           max_iter=50000))
    big.fit(Xtr, ytr)
    msgs = [str(w.message)[:70] for w in caught]
print(f'  迭代次数 n_iter_ = {big[-1].n_iter_}')
print(f'  系数 = {np.round(big[-1].coef_[0], 2)}')
print(f'  警告 = {msgs if msgs else "无(数据并非完全可分, 或者碰巧收敛了)"}')
print('  说明: 系数随迭代继续增大、或不收敛, 都说明 MLE 在这类数据上不存在。')

print(line)
print('[2] 弹性网: 用 train 内 5 折 CV 选 (C, l1_ratio)')
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=7)
rows = []
for l1 in (0.2, 0.5, 0.8, 1.0):
    for C in (0.01, 0.03, 0.1, 0.3, 1.0, 3.0):
        s = cross_val_score(scale_pipe(C=C, l1_ratio=l1), Xtr, ytr, cv=cv,
                            scoring='accuracy')
        rows.append((l1, C, s.mean(), s.std()))
grid = pd.DataFrame(rows, columns=['l1_ratio', 'C', 'cv_acc', 'cv_std'])
print(grid.pivot(index='l1_ratio', columns='C', values='cv_acc').round(3).to_string())
print(f'  不同取值的 CV 准确率范围 = [{grid.cv_acc.min():.3f}, {grid.cv_acc.max():.3f}], '
      f'标准差最大 {grid.cv_std.max():.3f}')
n_best = int((grid.cv_acc >= grid.cv_acc.max() - 1e-12).sum())
print(f'  并列最优的超参组合数 = {n_best} / {len(grid)}  '
      f'-> 无法据此挑出一个"更好"的 C')

print(line)
print('[3] 取一个具体组合 (C=0.3, l1_ratio=0.5) 与 NB 对比')
logit = scale_pipe(C=0.3, l1_ratio=0.5).fit(Xtr, ytr)
nb = BernoulliNB(alpha=1, binarize=None).fit(Xtr, ytr)
report('弹性网 logistic', yva, logit.predict_proba(Xva)[:, 1])
report('BernoulliNB', yva, nb.predict_proba(Xva)[:, 1])
report('先验基线', yva, np.full(len(yva), ytr.mean()))
print(f'  logistic 非零系数个数 = {int((np.abs(logit[-1].coef_[0]) > 1e-8).sum())} / {len(FEAT)}')

print(line)
print('[4] 两边的系数并排 (logistic 用标准化前的原始尺度)')
nb_slope = np.log(nb.feature_log_prob_[1] / (1 - nb.feature_log_prob_[1])) \
         - np.log(nb.feature_log_prob_[0] / (1 - nb.feature_log_prob_[0]))
z = StandardScaler().fit(Xtr)
lg_slope = logit[-1].coef_[0] / z.scale_
print(f'{"feature":<18}{"NB 斜率":>10}{"logistic":>12}{"被 L1 归零":>12}')
for f, a, b in zip(FEAT, nb_slope, lg_slope):
    print(f'{f:<18}{a:>10.3f}{b:>12.3f}{"是" if abs(b) < 1e-6 else "否":>12}')
print(f'{"截距":<18}{np.log(nb.class_log_prior_[1] / nb.class_log_prior_[0]):>10.3f}')
print('  读法: 两个模型在 urine_pushing 上都给了很大的正权重;')
print('        fever/lumbar 在 NB 里是负的 —— 这是 9 种组合造成的共线性假象, 不是医学结论。')
print(line)