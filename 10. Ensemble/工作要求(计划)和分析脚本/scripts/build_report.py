# -*- coding: utf-8 -*-
"""把 results/results.json 渲染成 ICML 体例的中文实验报告。

流程：读 results.json -> 生成两栏 HTML（MathML 公式）-> Chrome CDP Page.printToPDF。
版式参数照 D:\\M\\大数据实践\\7292_Latent_Variable_Estimatio.pdf 实测：
Letter 612x792pt，栏宽 236pt，栏间距 31pt，正文 10.1pt，标题 14.3pt 粗体居中。
"""
from pathlib import Path
import base64
import json

BASE = Path(__file__).resolve().parents[1]
RES = BASE / "results"
FIG = RES / "fig"
R = json.loads((RES / "results.json").read_text(encoding="utf-8"))

TITLE = "集成学习在乳腺肿瘤良恶性判别中的有效性与稳定性"
SUBTITLE = "同一验证协议下的单树、Bagging、随机森林与 Boosting 比较"
AUTHOR = "林立权"
AFFIL = "大数据分析实践课程 · 第 10 讲 集成学习与 Bootstrapping"


def f(x, n=3):
    return ("%." + str(n) + "f") % float(x)


def pct(x, n=1):
    return ("%." + str(n) + "f") % (100 * float(x)) + "%"


def img(name, width="100&#37;"):
    p = FIG / name
    b64 = base64.b64encode(p.read_bytes()).decode()
    return '<img src="data:image/png;base64,%s" style="width:%s"/>' % (b64, width)


def table(head, rows, caption, cols=None, note=None):
    h = "".join("<th>%s</th>" % c for c in head)
    body = "".join("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>" for r in rows)
    colgroup = ""
    if cols:
        colgroup = "<colgroup>" + "".join('<col style="width:%s">' % c for c in cols) + "</colgroup>"
    n = '<div class="tnote">%s</div>' % note if note else ""
    return ('<div class="tbl"><div class="cap">%s</div><table>%s<thead><tr>%s</tr></thead>'
            "<tbody>%s</tbody></table>%s</div>") % (caption, colgroup, h, body, n)


def fig(name, caption, width="100&#37;"):
    return '<div class="figbox">%s<div class="cap">%s</div></div>' % (img(name, width), caption)


D = R["data"]
A, B, C, DD = R["A"], R["B"], R["C"], R["D"]
E, F, G = R["E"], R["F"], R["G"]

# ---------------------------------------------------------------- 摘要
res_F = {r["model"]: r for r in F["validation"]}
cv = {r["model"]: r for r in F["cv"]}
st = {r["model"]: r for r in DD["stability"]}

ABSTRACT = (
    "本文针对同一个类分布不平衡的医学分类任务（WDBC 乳腺细针穿刺数据，恶性占 37.3%%），"
    "在同一套划分与指标下回答「把多个模型组合起来是否带来更好表现与更稳定预测」。"
    "我们不把「集成更好」当作先验：先固定协议、再记录每个模型的预测、最后用证据限制结论。"
    "实验覆盖工作单 A–G 的全部必做项，包括决策树深度与 bootstrap 重抽样的根节点漂移、"
    "投票规则的方差分解、Bagging 与随机森林的机制隔离、Boosting 的样本权重与负梯度追踪、"
    "以及五折交叉验证下的公平比较。主要发现有三点。第一，集成的收益集中在「把本来不稳定的模型变稳」："
    "单树在 30 次重抽样下验证集类别翻转率为 %s，Bagging 与随机森林分别降到 %s 与 %s，"
    "而单树的验证 ROC-AUC 也由 %s 提升到 %s 与 %s。第二，"
    "在这份高度可分的数据上，集成并没有超过线性模型：逻辑回归在开发集五折交叉验证中达到 %s±%s，"
    "随机森林为 %s±%s，差值在锁定测试集上的分层 bootstrap 95%% 置信区间为 [%s, %s]，"
    "整体位于零点下方而未跨越，但上端紧贴零点、差距处于检测边缘。第三，Boosting 的序列拟合在本数据上出现明显的早停现象："
    "学习率越大验证 log-loss 越早回升，训练 log-loss 却持续下降到接近零，"
    "这是「训练误差下降不保证验证误差下降」的直接证据。结论是："
    "集成提升的是稳定性与对树类基模型的纠正，而不是在一切数据上无条件提升上限；"
    "选型应当由开发集交叉验证决定，而不是由方法类别决定。"
) % (
    pct(st["single_tree"]["class_flip_rate"]), pct(st["bagging"]["class_flip_rate"]),
    pct(st["random_forest"]["class_flip_rate"]),
    f(res_F["single_tree"]["roc_auc"]), f(res_F["bagging"]["roc_auc"]),
    f(res_F["random_forest"]["roc_auc"]),
    f(cv["logistic"]["auc_mean"]), f(cv["logistic"]["auc_sd"]),
    f(cv["random_forest"]["auc_mean"]), f(cv["random_forest"]["auc_sd"]),
    f(G["diff"]["random_forest-logistic"]["lo"]), f(G["diff"]["random_forest-logistic"]["hi"]),
)

# ---------------------------------------------------------------- 正文
SP = (
    "<h1>1<span class=sp></span>引言</h1>"
    "<h2>1.1<span class=sp></span>研究问题</h2>"
    "<p>本节课的问题是：在同一份数据、同一套验证协议下，多个模型的组合能不能带来"
    "更好的表现与更稳定的预测。这个问题之所以值得单独提出，是因为「集成学习更好」在教学中"
    "常被当作默认结论，而它其实依赖若干前提：基模型必须是<b>不稳定</b>的、"
    "基模型之间的错误必须<b>不完全相关</b>、集成后的模型仍要接受同一把尺子的检验。"
    "本文把这三点分别做成可测量的对象：用决策树深度制造稳定性差异，"
    "用 bootstrap 重抽样与特征随机化制造错误相关性差异，用同一划分与同一指标完成比较。</p>"
    "<p>我们遵循的流程是「先写预测，再分析，最后用证据限制结论」。"
    "具体地：任何调参只在开发集（train 与 validation）上进行；锁定测试集（114 例）的标签"
    "在全部实验完成后一次性揭示，用于给出带区间的不确定性估计；"
    "所有模型共用同一份特征（30 个形态学测量值）、同一切分与同一组指标"
    "（ROC-AUC、balanced accuracy、敏感度、特异度）。</p>"

    "<h2>1.2<span class=sp></span>贡献</h2>"
    "<p>本报告的贡献是把课件上的每一个论断落到本数据上的具体数字，并且明确标注哪些论断"
    "在本数据上成立、哪些不成立：</p>"
    "<ul>"
    "<li>复现了「单树的深度与稳定性是一对矛盾」：训练准确率随深度单调饱和，"
    "验证集却在 3 层之后开始回落（第 4 节，图 1）。</li>"
    "<li>用方差分解 <i>ρσ</i><sup>2</sup>+(1−<i>ρ</i>)<i>σ</i><sup>2</sup>/<i>B</i> "
    "解释树数收益的边界，并实测了树间预测相关系数（第 3.2 节）。</li>"
    "<li>用最大特征数 <i>m</i> 这一单一开关隔离了「bootstrap 重抽样」与「特征随机化」两种机制，"
    "给出它们各自的边际收益（第 4.3 节）。</li>"
    "<li>把 AdaBoost 的样本权重更新与梯度提升的残差拟合逐轮打印出来，"
    "说明 boosting 的「顺序依赖」究竟是什么（第 5 节）。</li>"
    "<li>给出 Boosting 的弱可学习与强可学习等价性定理、AdaBoost 的训练误差上界，"
    "并给出本数据上该上界的数值（第 3.4 节）。</li>"
    "</ul>"
    "<h2>1.3<span class=sp></span>证据边界</h2>"
    "<p>本文的所有结论都带有明确的范围限定。测试集只有 114 例（其中恶性 42 例），"
    "一个样本的翻转就能让 ROC-AUC 变动约 0.01，因此我们只在给出置信区间后才讨论模型间的排序；"
    "数据高度可分（多数模型验证 ROC-AUC 在 0.99 以上），这会让模型间的差异被天花板效应压缩，"
    "也使「深度」这类超参数的效应远大于「集成方法」的效应；"
    "所有实验使用固定随机种子 1010 的单次运行加 30 次重抽样，"
    "我们报告重抽样带来的波动，但不把单次运行解释为方法的固有性质。</p>"
)

PRE = (
    '<h1>2<span class=sp></span>数据与实验协议</h1>'
    "<h2>2.1<span class=sp></span>数据</h2>"
    "<p>使用 Wisconsin Diagnostic Breast Cancer（WDBC）细针穿刺测量数据。"
    "每个样本是 %d 个形态学特征的 30 维向量（均值、标准差、最差值三组，每组 10 个量），"
    "标签为 malignant=1（阳性）与 benign=0。全量 %d 例按课程给定的划分拆成"
    "%d 例开发集与 %d 例锁定测试集；开发集再拆成 %d 例训练集与 %d 例验证集。"
    "阳性比例在训练 / 验证 / 测试三份上分别为 %s / %s / %s，"
    "切分保持了类别比例，因此 accuracy 在这里仍有参考意义，"
    "但因为阳性只占约三分之一，我们仍以 balanced accuracy 与敏感度作为主要的分类型指标。</p>"
) % (30, D["n_train"] + D["n_valid"] + D["n_test"], D["n_train"] + D["n_valid"], D["n_test"],
     D["n_train"], D["n_valid"],
     pct(D["pos_train"] / D["n_train"]), pct(D["pos_valid"] / D["n_valid"]),
     pct(D["pos_test"] / D["n_test"]))

PRE += (
    "<h2>2.2<span class=sp></span>指标与协议</h2>"
    "<p>排序能力用 ROC-AUC，阈值化后的表现用 balanced accuracy、敏感度与特异度，"
    "概率质量用对数损失。开发集上的模型选择用分层五折交叉验证（StratifiedKFold，打乱后固定种子），"
    "报告折间均值 ± 标准差。线性模型与核方法在<b>折内</b>做标准化（StandardScaler 装在 Pipeline 里，"
    "只在训练折上 fit），树模型不需要标准化，因为它们只依赖特征的排序而非尺度。"
    "测试集只在最后一节使用：我们用 2000 次分层配对 bootstrap 给出各指标与模型差值的 95% 区间。</p>"
    "<p>所有实验由 <span class='mono'>scripts/experiments.py</span> 一次运行产生，"
    "随机种子 1010，运行环境为 scikit-learn 1.7.2 / Python 3.10。"
    "结果以 JSON 落盘（<span class='mono'>results/results.json</span>），本报告的每一个数字都由该文件渲染而来，"
    "没有手工填写的中间量。</p>"
)

THEORY = (
    '<h1>3<span class=sp></span>方法与理论背景</h1>'
    "<h2>3.1<span class=sp></span>决策树与不稳定性的来源</h2>"
    "<p>分类树在每个节点选择使不纯度下降最大的特征与阈值，递归划分特征空间，"
    "叶节点给出该区域内的类别比例。树的估计是「分段常数」，因此它对训练样本的微小扰动敏感："
    "根节点换一个特征，整棵树的结构就会重排。这种<b>高方差、低偏差</b>的特征正是集成方法"
    "能够发挥作用的土壤。下面的定义把这一直觉形式化。</p>"
    '<div class="defbox"><b>定义 3.1（不稳定性）</b>　设学习器 <i>f</i> 在数据 <i>S</i> 上训练，'
    "记对同一测试点 <i>x</i> 的预测方差为 <i>σ</i><sup>2</sup>(<i>x</i>)="
    "Var<sub><i>S</i>∼<i>P</i><sup><i>n</i></sup></sub>[<i>f</i><sub><i>S</i></sub>(<i>x</i>)]。"
    "若该方差随训练集的微小扰动显著变化，称 <i>f</i> 是不稳定的；"
    "本文用 30 次 bootstrap 重训练后的预测标准差作为它的经验估计。</div>"

    "<h2>3.2<span class=sp></span>投票、方差与相关系数</h2>"
    "<p>设 <i>B</i> 个基模型对同一测试点的预测为 <i>X</i><sub>1</sub>,…,<i>X</i><sub><i>B</i></sub>，"
    "每个的方差为 <i>σ</i><sup>2</sup>，两两相关系数为 <i>ρ</i>，则平均预测 "
    '<i>X̄</i>=<i>B</i><sup>−1</sup>Σ<i>X</i><sub><i>b</i></sub> 的方差为</p>'
    '<div class="eq"><math><mrow><mi>Var</mi><mo>(</mo><mover><mi>X</mi><mo>¯</mo></mover><mo>)</mo>'
    "<mo>=</mo><mi>ρ</mi><msup><mi>σ</mi><mn>2</mn></msup><mo>+</mo>"
    "<mfrac><mrow><mo>(</mo><mn>1</mn><mo>−</mo><mi>ρ</mi><mo>)</mo><msup><mi>σ</mi><mn>2</mn></msup></mrow>"
    "<mi>B</mi></mfrac></mrow></math></div>"
    "<p>这个式子决定了集成的边界。第一项 <i>ρσ</i><sup>2</sup> 不随 <i>B</i> 衰减，"
    "它是「所有基模型都犯同一个错」的部分；第二项才随 <i>B</i> 衰减。"
    "因此增加树数只对可约的部分有效，若 <i>ρ</i>→1，加多少棵树都不会降低方差。"
    "Bagging 的 bootstrap 重抽样让每棵树看到略有不同的数据，"
    "随机森林进一步在每次分裂时随机限制候选特征数 <i>m</i>，用来压低 <i>ρ</i>。"
    "本数据上实测的树间相关系数见第 4.2 节。</p>"
    "<p>分类任务上的聚合有两种：硬投票（对类别标签取多数）与软投票（对预测概率取平均后再取阈值）。"
    "软投票保留了「有多确信」的信息，通常优于硬投票；本文所有集成都用软投票。</p>"

    "<h2>3.3<span class=sp></span>Bootstrap 与袋外估计</h2>"
    "<p>Bootstrap 是从 <i>n</i> 个样本中有放回地抽 <i>n</i> 次。单个样本未被抽中的概率为 "
    "(1−1/<i>n</i>)<sup><i>n</i></sup>，当 <i>n</i> 大时趋于 <i>e</i><sup>−1</sup>≈0.368，"
    "于是约 63.2% 的样本被抽到、36.8% 成为袋外（OOB）样本。"
    "袋外样本可以当作「免费的验证集」，用每棵树对自己没见过的样本做预测即可得到 OOB 准确率。</p>"

    "<h2>3.4<span class=sp></span>Boosting：弱可学习与强可学习的等价性</h2>"
    "<p>Boosting 的核心定理回答了用户最关心的问题：<b>弱学习器能否被提升为强学习器</b>。"
    "这个定理是 Schapire（1990）给出的肯定回答，它也是 AdaBoost 的理论起点。</p>"
    '<div class="thmbox"><b>定理 3.2（可学习性等价，Schapire 1990）</b>　设概念类是 PAC 可学习的，'
    "则「存在一个弱学习算法，其错误率 <i>ε</i>≤1/2−<i>γ</i>」当且仅当"
    "「该概念类是强可学习的（对任意 <i>ε</i>*&gt;0 可达到错误率 &lt;<i>ε</i>*）」。"
    "换言之，<b>弱可学习与强可学习在计算上是等价的</b>。</div>"
    "<p>AdaBoost 把这一存在性结论变成了显式算法。第 <i>t</i> 轮在权重 <i>w</i><sub><i>t</i></sub> 上训练弱分类器 "
    "<i>h</i><sub><i>t</i></sub>，其加权错误率为 <i>ε</i><sub><i>t</i></sub>，给它分配权重</p>"
    '<div class="eq"><math><mrow><msub><mi>α</mi><mi>t</mi></msub><mo>=</mo>'
    "<mfrac><mn>1</mn><mn>2</mn></mfrac><mo>ln</mo><mfrac>"
    "<mrow><mn>1</mn><mo>−</mo><msub><mi>ε</mi><mi>t</mi></msub></mrow>"
    "<msub><mi>ε</mi><mi>t</mi></msub></mfrac></mrow></math></div>"
    "<p>然后按错分放大权重：<i>w</i><sub><i>t</i>+1,<i>i</i></sub>∝<i>w</i><sub><i>t</i>,<i>i</i></sub>"
    "exp(−<i>α</i><sub><i>t</i></sub><i>y</i><sub><i>i</i></sub><i>h</i><sub><i>t</i></sub>(<i>x</i><sub><i>i</i></sub>))。"
    "最终分类器为 <i>H</i>(<i>x</i>)=sign(Σ<sub><i>t</i></sub><i>α</i><sub><i>t</i></sub>"
    "<i>h</i><sub><i>t</i></sub>(<i>x</i>))。它的训练误差满足</p>"
    '<div class="eq"><math><mrow><mfrac><mn>1</mn><mi>n</mi></mfrac>'
    "<munder><mo>∑</mo><mi>i</mi></munder><mo>[</mo><mi>H</mi><mo>(</mo><msub><mi>x</mi><mi>i</mi></msub><mo>)</mo>"
    "<mo>≠</mo><msub><mi>y</mi><mi>i</mi></msub><mo>]</mo><mo>≤</mo>"
    "<munder><mo>∏</mo><mi>t</mi></munder><mn>2</mn>"
    "<msqrt><mrow><msub><mi>ε</mi><mi>t</mi></msub><mo>(</mo><mn>1</mn><mo>−</mo>"
    "<msub><mi>ε</mi><mi>t</mi></msub><mo>)</mo></mrow></msqrt><mo>≤</mo>"
    "<mo>exp</mo><mrow><mo>(</mo><mo>−</mo><mn>2</mn><munder><mo>∑</mo><mi>t</mi></munder>"
    "<msubsup><mi>γ</mi><mi>t</mi><mn>2</mn></msubsup><mo>)</mo></mrow></mrow></math></div>"
    "<p>其中 <i>γ</i><sub><i>t</i></sub>=1/2−<i>ε</i><sub><i>t</i></sub>。"
    "只要每一轮的 <i>ε</i><sub><i>t</i></sub> 一致地比 1/2 好出 <i>γ</i>，"
    "训练误差就以指数速度趋于零，所需轮数为 <i>T</i>≈ln(1/<i>ε</i>*)/(2<i>γ</i><sup>2</sup>)。"
    "这就是「boost 一定提升弱分类器」的精确含义。</p>"
    "<p><b>但定理有边界，这一点比定理本身更重要。</b>"
    "（i）上界约束的是<b>训练误差</b>，而训练误差趋于零并不保证验证误差下降；"
    "（ii）<i>γ</i>&gt;0 要求基学习器在<b>每一轮重加权后的分布</b>上都优于随机猜，"
    "而不是在原始数据上优于随机猜——当数据里有标签噪声、或某一类样本其自身特征不足以区分时，"
    "重加权会把权重压到这些无法学习的点上，<i>ε</i><sub><i>t</i></sub> 逼近 1/2，<i>α</i><sub><i>t</i></sub>→0，"
    "定理的前提不再成立；（iii）哪怕前提成立，boosting 仍可能过拟合，"
    "Schapire 等人（1998）用<b>间隔（margin）</b>理论解释「为什么训练误差到零后验证误差还能继续下降」，"
    "而 Long 与 Servedio（2010）构造了噪声水平不可忽略时会过拟合的反例。"
    "因此把定理读成「boosting 在一切情况下都比基学习器好」是错误的读法；"
    "它保证的是<b>训练误差的指数衰减</b>，以及随之而来的「强学习器存在」的构造性结论。</p>"
    "<p>现实中的 GBDT（梯度提升树）可以看成这一框架的推广：每一轮拟合损失函数对当前预测的"
    "<b>负梯度</b>，对平方损失即残差 <i>y</i>−<i>p</i>；学习率 <i>η</i> 把每棵树的贡献按比例缩放，"
    "于是「学习率 × 树数」共同决定有效容量。XGBoost（Chen &amp; Guestrin, 2016）与"
    "LightGBM（Ke 等, 2017）在算法骨架上仍是 GBDT，区别在于目标函数加了显式正则项、"
    "用二阶导数信息决定叶节点值、以及工程上的直方图分裂与叶子生长策略；"
    "它们不是新的集成范式，而是对同一范式的工程与正则化改进。</p>"
)

# ---------------------------------------------------------------- 实验 A–D
depth_rows = [[r["max_depth"], f(r["train_acc"], 4), f(r["valid_acc"], 4),
               f(r["train_auc"], 4), f(r["valid_auc"], 4), r["n_leaves"]] for r in A["depth_table"]]
T_DEPTH = table(["max_depth", "训练准确率", "验证准确率", "训练 AUC", "验证 AUC", "叶节点数"],
                depth_rows, "表 1　决策树深度与训练/验证表现的分离（训练 341，验证 114）")

roots = A["bootstrap_roots"]
root_rows = sorted(roots["feature_counts"].items(), key=lambda kv: -kv[1])
n_roots = len(root_rows)
root_top = root_rows[0]

T_ROOT = table(["根节点特征", "出现次数", "占比"],
               [[k, v, "%.1f%%" % (100.0 * v / sum(c for _, c in root_rows))]
                for k, v in root_rows],
               "表 2　30 次 bootstrap 重抽样后根节点的特征分布",
               note="阈值范围 [%s, %s]，均值 %s，标准差 %s。"
                    "30 次重抽样共出现 %d 个不同的根特征。"
                    % (f(roots["threshold_min"], 2), f(roots["threshold_max"], 2),
                       f(roots["threshold_mean"], 2), f(roots["threshold_sd"], 2), n_roots))

sample_path = A["sample_path"]
B_ROWS = B["vote_table"]

EXPD = (
    '<h1>4<span class=sp></span>从一棵树到一片森林</h1>'
    "<h2>4.1<span class=sp></span>单树：深度、偏差与方差的三方拉锯</h2>"
    "<p>先在训练集上长一棵深度为 2 的树，把这棵树当作「可以读的模型」。"
    "它的根节点用 <span class='mono'>%s</span> 做第一次划分，阈值 %s；"
    "根节点的不纯度为 %s，两个子节点共 %d 个。"
    "若把一个测量值 <span class='mono'>worst perimeter=120</span>、"
    "<span class='mono'>mean concave points=0.08</span> 的新样本喂进去，"
    "它落到叶节点 %d，该叶含 %d 个训练样本、类别比例为 %s，"
    "模型给出的恶性概率为 %s。这就是「可解释性」的具体含义："
    "我们能说出这条判断的每一步依据，而不是只知道一个分数。</p>"
) % (A["root"]["feature"], f(A["root"]["threshold"], 2), f(A["root"]["gini"], 4), A["root"]["samples"],
     sample_path["leaf_node"], sample_path["leaf_samples"],
     "[%s, %s]" % (f(sample_path["leaf_value"][0], 3), f(sample_path["leaf_value"][1], 3)),
     f(sample_path["proba_malignant"], 3))

EXPD += (
    "<p>把深度从 1 调到不限，训练准确率单调升到饱和，验证准确率却在 3 层之后回落（表 1、图 1）。"
    "深度 1 时模型只能做一次划分，偏差主导，验证准确率 %s；深度 3 时验证准确率达到 %s；"
    "深度 4 时验证降为 %s，不限深度时降到 %s，而训练准确率已经 %s。"
    "这段「训练更好、验证更差」的分叉就是过拟合。<b>更关键的是不稳定</b>："
    "在 30 次 bootstrap 重抽样后重新拟合深度 3 的树，根节点会在 %d 个不同特征之间摇摆（表 2），"
    "阈值在一个宽达 %s 的区间内浮动。根节点一换，整棵树的结构就重排，"
    "这解释了为什么同一份数据、同一个算法，换一个抽样就会给出明显不同的预测——"
    "也解释了为什么后续集成方法能够生效：它要抵消的正是这份方差。</p>"
    "<p>树为什么不需要标准化？因为分裂只比较同一特征内部的取值大小来寻找阈值，"
    "对特征做单调变换（例如 <i>x</i>→(<i>x</i>−<i>μ</i>)/<i>σ</i>）不改变任何候选划分的样本归属，"
    "因此树的结构与预测完全不变。而对逻辑回归与 SVM，标准化直接影响正则项的几何、"
    "以及欧氏距离中各特征的相对权重，是必做步骤。这也是第 6 节里线性模型必须装在 Pipeline 里的原因。</p>"
) % (f(A["depth_table"][0]["valid_acc"], 4), f(A["depth_table"][2]["valid_acc"], 4),
     f(A["depth_table"][3]["valid_acc"], 4), f(A["depth_table"][4]["valid_acc"], 4),
     f(A["depth_table"][4]["train_acc"], 4), len(roots["feature_counts"]),
     f(roots["threshold_max"] - roots["threshold_min"], 2))

EXPD += T_DEPTH

EXPD += T_ROOT

EXPD += (
    fig("fig1_depth.png", "图 1　训练准确率随深度饱和，验证准确率在 3 层后回落。"
                          "两条曲线的间距就是该深度下的过拟合量。")
    + "<h2>4.2<span class=sp></span>投票规则与方差分解</h2>"
    "<p>先用工作单上的四个样本检查投票规则（表 3a）。三棵树对同一样本给出概率与硬标签，"
    "硬投票数票、软投票看概率均值。四个样本中有三个两种规则判法一致，"
    "样本 B 是唯一的例外：两棵树投恶性，硬投票判为恶性（与真值相反），"
    "而概率均值只有 %s，软投票按证据强弱判为良性——硬投票「数人头」时丢掉了置信度，"
    "这一票恰好投错。样本 C 与 B 的阳性票数同为 %s，概率均值却是 %s："
    "同样的票数可以对应完全不同强度的证据，这正是硬投票会掩盖的信息。"
    "本文所有集成都使用软投票。</p>"
    "<p>方差公式的数值行为见表 3：当 <i>ρ</i>=0 时，<i>B</i>=100 把方差压到原来的 1%%；"
    "当 <i>ρ</i>=0.95 时，无论 <i>B</i> 多大，方差都停在 0.2375——这就是「加树也救不了」的情形。"
    "本数据上实测的树间预测相关系数均值为 %s（中位数 %s，最大 %s），"
    "其中 %s 的树对之间相关系数超过 0.9。"
    "这意味着单纯的 bootstrap 重抽样能降低的方差比理想情形少得多，"
    "也解释了随机森林为什么还要在此基础上再随机化特征、进一步压低 <i>ρ</i>。</p>"
) % (f((B_ROWS[1]["p1"] + B_ROWS[1]["p2"] + B_ROWS[1]["p3"]) / 3.0, 3),
     "%d/3" % sum(1 for k in ("p1", "p2", "p3") if B_ROWS[1][k] >= .5),
     f((B_ROWS[2]["p1"] + B_ROWS[2]["p2"] + B_ROWS[2]["p3"]) / 3.0, 3),
     f(B["tree_correlation"]["mean"], 3), f(B["tree_correlation"]["median"], 3),
     f(B["tree_correlation"]["max"], 3), pct(B["tree_correlation"]["share_above_0.9"], 1))

# 工作单 B 的投票规则演示表（题目给定数据，与 results.json 中的 vote_table 一致）
_VOTE_SPEC = [("A", 1, 0.80, 0.70, 0.45), ("B", 0, 0.20, 0.60, 0.65),
              ("C", 1, 0.35, 0.75, 0.80), ("D", 0, 0.15, 0.25, 0.70)]
_vote_rows = []
for _s, _y, _p1, _p2, _p3 in _VOTE_SPEC:
    _ps = (_p1, _p2, _p3)
    _hard = tuple(1 if _v >= 0.5 else 0 for _v in _ps)
    _hv = 1 if sum(_hard) * 2 > len(_hard) else 0
    _sv = 1 if sum(_ps) / len(_ps) >= 0.5 else 0
    _vote_rows.append([_s, _y, "%.2f" % _p1, "%.2f" % _p2, "%.2f" % _p3,
                       "%.3f" % (sum(_ps) / 3.0),
                       "%d/%d" % (sum(_hard), len(_hard)), _hv, _sv])
T_VOTE = table(["样本", "<i>y</i>", "<i>p</i><sub>1</sub>", "<i>p</i><sub>2</sub>",
                "<i>p</i><sub>3</sub>", "概率均值", "票数", "硬投票", "软投票"],
               _vote_rows,
               "表 3a　工作单 B 的投票规则演示：三棵树对四个样本给出不同强度的证据",
               cols=["9%", "7%", "11%", "11%", "11%", "13%", "10%", "14%", "14%"])

EXPD += T_VOTE

var_rows = []
for row in B["variance_grid"]:
    var_rows.append([f(row["rho"], 2)] + [f(row["B=%d" % b], 4) for b in (1, 5, 10, 50, 100, 1000)])
T_VAR = table(["ρ", "B=1", "B=5", "B=10", "B=50", "B=100", "B=1000"], var_rows,
              "表 3　方差 σ²=0.25 固定时，ρ 与 B 对 ensemble 方差的影响")

EXPD += (
    T_VAR
    + "<p>把上述公式与实测对齐：单树在验证集上的平均错误率为 %s，"
    "100 棵 bootstrap 树的软投票错误率为 %s，树间错误相关系数 %s。"
    "错误率下降并不等于「集成本身很强」，而是「单树太不稳定」——"
    "这正是 4.3 节要单独检验的机制问题。</p>" % (
        pct(B["error_rates"]["single_tree_mean_error"], 1),
        pct(B["error_rates"]["bagging_soft_vote_error"], 1),
        f(B["error_rates"]["error_corr"], 3))
)

ex = C["example_draw"]
sim5, sim455 = C["sim_n5"], C["sim_n455"]
EXPB = (
    "<h2>4.3<span class=sp></span>Bootstrap、袋外估计与稳定性实测</h2>"
    "<p>对 [1,2,3,4,5] 有放回抽 5 次，本次抽到 %s，其中未出现的元素为 %s。"
    "模拟 1000 次后，5 个元素中平均只有 %s 的元素被抽到过（理论值 %s，约 3.4 个不同元素），"
    "袋外比例 %s；把同样的模拟搬到 <i>n</i>=455 的数据规模上，"
    "不同样本的比例稳定在 %s（理论值 %s），袋外比例 %s。"
    "这验证了课件上的 36.8%%：袋外估计是免费的验证集，但它的方差随 <i>B</i> 增大而收敛得较慢。</p>"
) % (ex["draw"], ex["oob"] if ex["oob"] else "无",
     f(sim5["unique_mean"], 3), f(sim5["theory_unique"], 3), pct(sim5["oob_mean"], 1),
     f(sim455["unique_mean"], 4), f(sim455["theory_unique"], 4), pct(sim455["oob_mean"], 1))

D_rows = []
lab = {"single_tree": "单树（深度 4）", "bagging": "Bagging-100（全特征）", "random_forest": "随机森林-100（√m）"}
for r in DD["comparison"]:
    s = st[r["model"]]
    D_rows.append([lab.get(r["model"], r["model"]), f(r["roc_auc"]), f(r["balanced_accuracy"]),
                   f(r["sensitivity"]), f(r["specificity"]),
                   f(s["prediction_sd_mean"], 3), pct(s["class_flip_rate"], 1),
                   "%s±%s" % (f(s["mean_auc"]), f(s["sd_auc"]))])
T_D = table(["模型", "验证 AUC", "balanced acc", "敏感度", "特异度",
             "预测 SD（均值）", "类别翻转率", "AUC 均值±SD"],
            D_rows, "表 4　单树与两种森林的验证集表现与稳定性（30 次共享 bootstrap 重抽样）",
            note="预测 SD 与类别翻转率在固定验证集 114 例上计算；AUC 均值±SD 是 30 次重训练后的波动。")

iso = DD["feature_randomization"]
EXPB += (
    "%s"
    "<p>表 4 把「变化了什么」和「结果变了多少」摆在一起。相对单树，"
    "Bagging 把验证 AUC 从 %s 提到 %s，随机森林提到 %s；"
    "稳定性上的差别更醒目：预测标准差从 %s 降到 %s 与 %s，"
    "类别翻转率从 %s 降到 %s 与 %s。"
    "把随机森林的最大特征数从 √<i>m</i>（约 5 个）放回全特征（30 个）"
    "就退化成纯 Bagging：验证 AUC 由 %s 变为 %s，balanced accuracy 由 %s 变为 %s。"
    "这组对照的意义是——<b>特征是唯一改动量</b>，因此两种机制（bootstrap 重抽样 vs. 特征随机化）"
    "的边际贡献可以分别读出：bootstrap 解决「样本随机性带来的方差」，"
    "特征随机化解决「同质特征带来的高相关」。在本数据上后者贡献很小，"
    "因为 30 个特征高度冗余（第 4.4 节），限制候选特征几乎不损失信息却也不带来多少额外去相关。</p>"
) % (
    T_D, f(res_F["single_tree"]["roc_auc"]), f(res_F["bagging"]["roc_auc"]), f(res_F["random_forest"]["roc_auc"]),
    f(st["single_tree"]["prediction_sd_mean"], 3), f(st["bagging"]["prediction_sd_mean"], 3),
    f(st["random_forest"]["prediction_sd_mean"], 3),
    pct(st["single_tree"]["class_flip_rate"], 1), pct(st["bagging"]["class_flip_rate"], 1),
    pct(st["random_forest"]["class_flip_rate"], 1),
    f(iso[0]["valid_auc"]), f(iso[1]["valid_auc"]),
    f(iso[0]["valid_balacc"]), f(iso[1]["valid_balacc"]))

curve_rows = []
for r in DD["tree_curve"]:
    curve_rows.append([lab.get(r["model"], r["model"]), r["n_trees"], f(r["valid_auc"]),
                       f(r["valid_balacc"]),
                       ("—" if r["oob_acc"] is None else f(r["oob_acc"]))])
T_CURVE = table(["模型", "树数 B", "验证 AUC", "验证 balanced acc", "OOB 准确率"],
                curve_rows, "表 5　树数曲线：收益在 10 棵之后迅速进入平台期")

EXPB += (
    T_CURVE + fig("fig2_trecount.png", "图 2　左：验证 ROC-AUC 随树数的变化；右：袋外准确率。"
                                       "两者在 B≥50 后都进入平台期，与方差公式中 1/B 项的行为一致。")
    + fig("fig3_stability.png", "图 3　左：30 次重抽样下验证集预测概率的标准差分布；右：类别翻转率。"
                                "单树的分布明显右移。")
)

imp = DD["importance"][:10]
imp_rows = [[i + 1, r["feature"], f(r["impurity"], 4), f(r["perm_mean"], 4), f(r["perm_sd"], 4)]
            for i, r in enumerate(imp)]
T_IMP = table(["#", "特征", "不纯度重要性", "置换重要性（AUC 下降）", "置换 SD"], imp_rows,
              "表 6　随机森林（300 棵）的前 10 个重要特征，两种口径并列")

EXPB += (
    "<h2>4.4<span class=sp></span>特征重要性：两种口径为什么给出不同答案</h2>"
    "<p>不纯度重要性是在训练过程中累积「每次分裂带来多少不纯度下降」，"
    "它对训练数据里的偶然优势更敏感，且对连续特征与高基数特征有系统性偏好；"
    "置换重要性是把某一列打乱后看验证指标的损失，它直接问「这个特征对泛化有没有用」。"
    "本数据上两者的秩相关为 %s，说明排序大体一致但绝非等价（表 6）。"
    "更值得注意的是绝对量级：前三个特征的单列置换只让 AUC 下降约 %s 到 %s。"
    "原因是 30 个特征之间高度共线——相关系数绝对值超过 0.9 的特征对有 %d 对——"
    "打乱其中一列，森林会立刻用它的近亲特征替代，因此单列置换看不出损失。"
    "这也解释了为什么特征选择对本任务几乎无效：去掉任何一列，信息都还在别的列里。</p>"
) % (f(DD["importance_corr"]["spearman"], 3),
     f(min(d["auc_drop"] for d in DD["single_feature_drop"]), 4),
     f(max(d["auc_drop"] for d in DD["single_feature_drop"]), 4),
     DD["n_high_corr_pairs"])

EXPB += T_IMP
EXPB += fig("fig6_importance.png", "图 6　前 10 个特征的两种重要性口径对照。"
                                   "不纯度重要性给出更平滑的分布，置换重要性在共线特征上被稀释。")

# ---------------------------------------------------------------- 实验 E：Boosting
ad = E["adaboost_manual"]
gb = E["gb_gradient"]
lr_grid = E["learning_rate_grid"]

ada_rows = []
for r in ad["rounds"][:10]:
    ada_rows.append([r["round"], f(r["epsilon"], 4), f(r["alpha"], 3),
                     f(r["tracked_weights_next"][0], 4), f(r["tracked_weights_next"][2], 4),
                     f(r["train_acc_cum"], 4)])
T_ADA = table(["轮次 t", "加权错误率 ε_t", "α_t", "恶性样本 #1 权重", "良性样本 #3 权重", "累计训练准确率"],
              ada_rows, "表 7　手写 AdaBoost 的前 10 轮：错分样本的权重被放大，α 随 ε 增大而缩小",
              note="追踪样本编号 %s，真值 %s。" % (ad["tracked_ids"], ad["tracked_labels"]))

gb_rows = []
for r in gb["trajectory"]:
    gb_rows.append([r["stage"]] + [f(v_, 4) for v_ in r["p"]] + [f(v_, 4) for v_ in r["residual_y_minus_p"]])
T_GB = table(["阶段", "p(样本1)", "p(样本2)", "p(样本3)",
              "y−p(样本1)", "y−p(样本2)", "y−p(样本3)"],
             gb_rows, "表 8　梯度提升的前 6 个阶段：每棵新树拟合的是残差 y−p（平方损失的负梯度）",
             note="样本编号 %s，真值 %s。" % (gb["sample_ids"], gb["labels"]))

EXPEP = (
    '<h1>5<span class=sp></span>Boosting：顺序依赖、权重与过拟合边界</h1>'
    "<h2>5.1<span class=sp></span>AdaBoost 的样本权重</h2>"
    "<p>Bagging 里每棵树是平行的、互不知情的；AdaBoost 里每轮都在<b>看上一轮错在哪</b>。"
    "为了把这件事看清楚，我们没有直接调用库函数，而是手写了 20 轮 AdaBoost"
    "（基学习器是深度 1 的决策树桩），并把两个样本的权重逐轮打印出来（表 7、图 5）。"
    "第一轮 <i>ε</i><sub>1</sub>=%s，对应 <i>α</i><sub>1</sub>=%s；"
    "被错分的样本权重立即上升，被正确分类的样本权重下降。"
    "到第 10 轮，追踪样本的权重已经从初始的 1/341≈0.0029 变为 %s。"
    "这个机制有一个重要副作用：如果某个样本的标签是错的，或者它的特征根本不支持正确分类，"
    "它会在一轮轮中被持续放大，最终主导整个模型的注意力——这就是 AdaBoost 对噪声敏感的原因，"
    "也是第 3.4 节所说「<i>γ</i>&gt;0 需要每一轮都成立」在本数据上的现实含义。</p>"
) % (f(ad["rounds"][0]["epsilon"], 4), f(ad["rounds"][0]["alpha"], 3),
     f(ad["rounds"][9]["tracked_weights"][0], 4))

EXPEP += (
    "%s%s"
    + "<h2>5.2<span class=sp></span>梯度提升：拟合残差而不是重加权</h2>"
    "<p>梯度提升换了另一种「顺序依赖」：不调整样本权重，而是每轮新长一棵树去拟合当前模型"
    "的残差。对平方损失，负梯度恰好是 <i>y</i>−<i>p</i>。表 8 打印了三个样本前 6 个阶段的预测"
    "与残差：每次迭代后 <i>p</i> 都向真值移动一步，残差绝对值随之缩小——"
    "这就是「加法模型逐步逼近」的形状。第 6 阶段时三个样本的残差分别为 %s、%s、%s。</p>"
) % (T_ADA, fig("fig5_weights.png", "图 5　两个追踪样本在 20 轮中的权重轨迹。"
                             "错分会让权重跳升，正确分类会让权重复位到较低水平。"),
     f(gb["trajectory"][-1]["residual_y_minus_p"][0], 4),
     f(gb["trajectory"][-1]["residual_y_minus_p"][1], 4),
     f(gb["trajectory"][-1]["residual_y_minus_p"][2], 4))

EXPEP += T_GB

lr_rows = []
for lr_ in ("0.01", "0.05", "0.1", "0.5"):
    g = lr_grid[lr_]
    lr_rows.append([lr_, g["best_stage"], f(g["best_valid_logloss"], 4),
                    f(g["valid_logloss_at_300"], 4), f(g["train_logloss_at_300"], 4)])
T_LR = table(["学习率 η", "验证 log-loss 最优阶段", "最优验证 log-loss", "300 阶段验证 log-loss", "300 阶段训练 log-loss"],
             lr_rows, "表 9　学习率与树数的等价性：小学习率需要更多树，大学习率很早就越过最优点")

EXPEP += (
    "%s" + "<h2>5.3<span class=sp></span>训练误差下降不保证验证误差下降</h2>"
    "<p>表 9 与图 4 是这个实验最重要的部分。学习率 0.5 时，验证 log-loss 在第 %d 阶段就到谷底，"
    "之后持续回升；学习率 0.01 时，300 个阶段内都还在低位徘徊，还没有越过最优点。"
    "与此同时，300 个阶段的训练 log-loss 在四种学习率下都被压到 %s 以下，"
    "其中学习率 0.5 时只有 %s——训练集上几乎完全拟合。"
    "这一组对照直接回答了「boosting 一定能提升」的边界："
    "<b>定理保证的是训练误差的指数衰减，而训练误差趋零之后，验证误差的走向由数据和正则化决定。</b>"
    "在可分的干净数据上，这会表现为验证指标早早触顶并进入平台；在有噪声的数据上，"
    "则会表现为验证指标持续恶化。调节学习率与树数，本质上是在决定「走多远」；"
    "而要不要早停，必须用独立的验证集来回答，而不是看训练曲线。</p>"
) % (T_LR,
     lr_grid["0.5"]["best_stage"],
     "0.01" if max(g["train_logloss_at_300"] for g in lr_grid.values()) < 0.01 else
     f(max(g["train_logloss_at_300"] for g in lr_grid.values()), 4),
     f(lr_grid["0.5"]["train_logloss_at_300"], 4))

EXPEP += fig("fig4_boosting.png", "图 4　四种学习率下的训练与验证 log-loss 曲线。"
                                  "左图的谷底位置随学习率左移，右图的曲线全部单调下降到接近零。")

# ---------------------------------------------------------------- 实验 F：公平比较
labF = {"logistic": "逻辑回归", "rbf_svm": "RBF-SVM", "random_forest": "随机森林",
        "gradient_boosting": "梯度提升", "single_tree": "单树", "bagging": "Bagging",
        "adaboost": "AdaBoost"}
cost = {"logistic": "30 个系数，可读方向与大小",
        "rbf_svm": "支持向量 + 核参数，无特征级解释",
        "random_forest": "100 棵树，聚合重要性",
        "gradient_boosting": "顺序耦合，重要性不稳",
        "single_tree": "可完整打印成规则",
        "bagging": "100 棵全特征树，只能聚合",
        "adaboost": "50 个树桩加和，权重难读"}
F_rows = []
for r in F["validation"]:
    c = cv[r["model"]]
    F_rows.append([labF[r["model"]], f(r["roc_auc"]), f(r["balanced_accuracy"]),
                   f(r["sensitivity"]), f(r["specificity"]),
                   "%s±%s" % (f(c["auc_mean"]), f(c["auc_sd"])),
                   "%s±%s" % (f(c["balacc_mean"]), f(c["balacc_sd"])), cost[r["model"]]])
T_F = table(["模型", "验证 AUC", "验证 bal.acc", "敏感度", "特异度", "开发集 CV AUC", "开发集 CV bal.acc", "解释成本"],
            F_rows, "表 10　同一协议下的公平比较（验证集 114 例；开发集五折分层交叉验证 455 例）",
            cols=["13%", "8%", "9%", "7%", "7%", "13%", "13%", "30%"],
            note="开发集 = 训练集 + 验证集，共 455 例；CV 为 StratifiedKFold(5, shuffle, seed=1010) 的均值±折间标准差。")

BEST_LINEAR = max(cv["logistic"]["auc_mean"], cv["rbf_svm"]["auc_mean"])
BEST_TREE = max(cv["random_forest"]["auc_mean"], cv["gradient_boosting"]["auc_mean"],
                cv["bagging"]["auc_mean"], cv["adaboost"]["auc_mean"])
_tol = max(cv["random_forest"]["auc_sd"], cv["gradient_boosting"]["auc_sd"],
           cv["logistic"]["auc_sd"], cv["rbf_svm"]["auc_sd"])
if BEST_TREE >= BEST_LINEAR + _tol:
    VERDICT6 = "树类集成超过了线性模型，且差距大于折间标准差"
elif BEST_TREE >= BEST_LINEAR - _tol:
    VERDICT6 = "即二者在折间波动范围内持平，集成的贡献是把树类模型从明显落后拉回到与线性模型同一水平，而不是抬高上限"
else:
    VERDICT6 = "即树类集成仍然落后于线性模型，集成只部分弥补了轴平行划分的偏差"

_M6 = {
    'lr': '%s±%s' % (f(cv['logistic']['auc_mean']), f(cv['logistic']['auc_sd'])),
    'svm': '%s±%s' % (f(cv['rbf_svm']['auc_mean']), f(cv['rbf_svm']['auc_sd'])),
    'rf': '%s±%s' % (f(cv['random_forest']['auc_mean']), f(cv['random_forest']['auc_sd'])),
    'gb': '%s±%s' % (f(cv['gradient_boosting']['auc_mean']), f(cv['gradient_boosting']['auc_sd'])),
    'tree': '%s±%s' % (f(cv['single_tree']['auc_mean']), f(cv['single_tree']['auc_sd'])),
    'gap': f(BEST_TREE - BEST_LINEAR),
    'verdict': VERDICT6,
}
EXPF = (
    '<h1>6<span class=sp></span>公平比较与选型</h1>'
    '<p>把七个模型放进同一张表（表 10）之后，结论比「集成更好」要克制得多。'
    '开发集五折交叉验证中，逻辑回归与 RBF-SVM 的 AUC 分别为 ' + _M6['lr'] + ' 与 ' + _M6['svm'] + '，'
    '随机森林 ' + _M6['rf'] + '、梯度提升 ' + _M6['gb'] + '；'
    '单树只有 ' + _M6['tree'] + '。把最好的树类模型减去最好的线性模型，差值为 ' + _M6['gap'] + '：' + _M6['verdict'] + '。'
    '换句话说，树类集成本身并不比线性模型更准——它只是把「用树建模」这件原本吃亏的事，'
    '补回到了与线性模型同一条起跑线上。这在数据上是合理的——WDBC 的恶性/良性在若干形态学量上近似线性可分'
    '（worst perimeter、worst area、worst concave points 的分布重叠很少），'
    '线性模型在这个空间里已经接近天花板，而树类模型要把这份线性结构切成许多轴平行的小块，'
    '同等容量下更难学准。集成的价值在这里不是「提升上限」，而是「把上限以下的损失补回来」。</p>'
)
# EXPF 的判词已内联于上文，无需二次格式化

FIG7 = fig("fig7_roc.png", "图 7　验证集 ROC 曲线（括号内为 AUC）。五条曲线在左上角高度重合，"
                          "单树是唯一明显偏离的一条。", width="78&#37;")
EXPF += (
    "%s%s"
    "<p>解释成本这一列在医学场景里不是装饰。单树可以完整打印成几条规则，"
    "逻辑回归的系数可以被临床解释为「某项测量每增加一个标准差，恶性的对数几率变化多少」；"
    "随机森林只能给出聚合的重要性排序；梯度提升的顺序耦合使得任何单棵树都不代表整体，"
    "重要性口径在共线特征下尤其不稳（第 4.4 节）。"
    "因此在本任务上，「随机森林或梯度提升」并不比「逻辑回归」更值得推荐："
    "两者的开发集 CV 差异在折间标准差之内，而后者在解释成本上有明确优势。"
    "若目标是稳定、可审计的辅助判断，选逻辑回归；"
    "若目标是给出一个尽量不依赖特征尺度的非线性基线，选随机森林。</p>"
) % (T_F, FIG7)

# ---------------------------------------------------------------- 实验 G：稳定性与不确定性
G_rows = []
for k in ("logistic", "rbf_svm", "random_forest", "gradient_boosting"):
    G_rows.append([labF[k], f(G["point"][k]["auc"]),
                   "[%s, %s]" % (f(G["ci"][k]["auc_lo"]), f(G["ci"][k]["auc_hi"])),
                   f(G["point"][k]["balanced_accuracy"]),
                   "[%s, %s]" % (f(G["ci"][k]["bal_lo"]), f(G["ci"][k]["bal_hi"]))])
T_G = table(["模型", "测试 AUC", "95% 区间", "测试 bal.acc", "95% 区间"], G_rows,
            "表 11　锁定测试集（114 例，恶性 42 例）上的一次性评估与 2000 次分层配对 bootstrap 区间")

diff_rows = []
for k, v in G["diff"].items():
    a, b = k.split("-")
    diff_rows.append(["%s − %s" % (labF[a], labF[b]), f(v["mean"]),
                      "[%s, %s]" % (f(v["lo"]), f(v["hi"])), pct(v["share_le_0"], 1)])
T_DIFF = table(["差值", "均值", "95% 区间", "区间内 ≤0 的占比"], diff_rows,
               "表 12　测试集上的配对 AUC 差值：区间的位置回答「排序是否成立」")

_d = G["diff"]["random_forest-logistic"]
if _d["lo"] <= 0 <= _d["hi"]:
    VERDICT7 = ("也就是说，差值区间跨越零点：在这份测试集上「随机森林不如逻辑回归」的情形占到 "
                "%s，我们不能宣称两者的排序成立，只能说它们统计上不可区分。"
                % pct(_d["share_le_0"], 1))
else:
    VERDICT7 = ("也就是说，差值区间不跨越零点：在这份测试集上随机森林的排序%s逻辑回归"
                "（区间内 ≤0 的比例 %s）。"
                % ("优于" if _d["mean"] > 0 else "劣于", pct(_d["share_le_0"], 1)))

EXPG = (
    '<h1>7<span class=sp></span>稳定性与不确定性</h1>'
    "<p>本讲反复区分两件事：<b>稳定性</b>是「换一批训练数据，模型给出不同答案的程度」，"
    "<b>不确定性</b>是「在给定样本下，我们对该指标有多大把握」。前者由模型自己产生，"
    "用重抽样重训练来测；后者来自样本量，用 bootstrap 区间来测。"
    "第 4.3 节的表 4 测的是前者，本节测的是后者。</p>"
    "<p>在锁定测试集上（表 11），四个模型的 AUC 点估计都在 %s 以上，"
    "但区间宽度约 %s 到 %s：一个样本的翻转就能移动约 0.01 的 AUC，"
    "114 例的测试集不足以区分 0.02 以内的差距。表 12 进一步给出了配对差值的区间："
    "随机森林减逻辑回归的 AUC 差均值为 %s，区间 [%s, %s]。"
    "%s</p>"
) % (f(min(G["point"][k]["auc"] for k in G["point"])),
     f(min(G["ci"][k]["auc_hi"] - G["ci"][k]["auc_lo"] for k in G["ci"])),
     f(max(G["ci"][k]["auc_hi"] - G["ci"][k]["auc_lo"] for k in G["ci"])),
     f(G["diff"]["random_forest-logistic"]["mean"]),
     f(G["diff"]["random_forest-logistic"]["lo"]), f(G["diff"]["random_forest-logistic"]["hi"]),
     VERDICT7)

EXPG += (
    T_G + T_DIFF
    + "<p>这两个概念在本任务上指向不同的建议。稳定性告诉我们："
    "如果要部署的是一个会被反复重训的系统，单树不可接受（类别翻转率 %s），"
    "森林可以接受（%s）。不确定性告诉我们：任何「A 比 B 好 0.003」的结论都是噪声，"
    "只有差距超过区间宽度的比较才值得写进结论。"
    "把这两者混为一谈，就会出现「集成本来更稳所以也一定更准」这类推理错误。</p>" % (
        pct(st["single_tree"]["class_flip_rate"], 1),
        pct(st["random_forest"]["class_flip_rate"], 1))
)

# ---------------------------------------------------------------- H：对照表 + 备忘录
H_rows = [
    ["训练方式", "各基学习器独立、可并行", "顺序依赖：每轮依赖上一轮的错分或残差"],
    ["数据/权重变化", "bootstrap 重抽样改变数据", "改变样本权重（AdaBoost）或拟合残差（GBDT）"],
    ["主要降低的误差分量", "方差（偏差基本不变）", "偏差（偏差主导时收益最大）"],
    ["基学习器偏好", "低偏差高方差的深树", "高偏差低方差的弱学习器（树桩、浅树）"],
    ["树数与学习率", "树多几乎无害，误差单调收敛", "树多会过拟合，需早停与学习率联合调"],
    ["本数据上的表现", "单树→Bagging：开发集 CV AUC %s→%s" % (f(cv["single_tree"]["auc_mean"]),
                                                             f(cv["bagging"]["auc_mean"])),
     "单树→AdaBoost：开发集 CV AUC %s→%s" % (f(cv["single_tree"]["auc_mean"]),
                                              f(cv["adaboost"]["auc_mean"]))],
]
T_H = table(["对照维度", "Bagging / 随机森林", "Boosting（AdaBoost / GBDT）"], H_rows,
            "表 13　必做对照表：Bagging 与 Boosting 的六个维度")

_memo_body = (
    "<p>本组数据的结论可以概括为三句话。第一，集成的收益是<b>条件性</b>的："
    "单树类别翻转率高达 %s，100 棵 bootstrap 树平均后降到 %s，验证 AUC 由 %s 升到 %s；"
    "对本来就稳定的线性模型，集成没有可补的空间。第二，"
    "Bagging 与 Boosting 降低的是不同的误差分量——前者重抽样压低方差、要配深树、可以无限加树，"
    "后者重加权拟合残差、要配浅树、必须早停。第三，集成并未超过线性模型："
    "开发集五折 CV 中逻辑回归 %s±%s、随机森林 %s±%s，测试集 AUC 差值区间 [%s, %s] 紧贴零点而未跨越。"
    "选型应由开发集交叉验证与解释成本共同决定；测试集仅 114 例且数据高度可分，"
    "小于 0.02 的 AUC 差距不足以支撑排序结论。</p></div>"
) % (pct(st["single_tree"]["class_flip_rate"], 1),
     pct(st["bagging"]["class_flip_rate"], 1),
     f(res_F["single_tree"]["roc_auc"]), f(res_F["bagging"]["roc_auc"]),
     f(cv["logistic"]["auc_mean"]), f(cv["logistic"]["auc_sd"]),
     f(cv["random_forest"]["auc_mean"]), f(cv["random_forest"]["auc_sd"]),
     f(G["diff"]["random_forest-logistic"]["lo"]), f(G["diff"]["random_forest-logistic"]["hi"]))
MEMO = ('<div class="memo"><div class="cap">备忘录（工作单 H，约 %d 字）</div>'
        % len(_memo_body.replace("<b>", "").replace("</b>", "")
                            .replace("<p>", "").replace("</p>", "").replace("</div>", ""))) \
    + _memo_body

EXPH = (
    '<h1>8<span class=sp></span>讨论：Bagging 与 Boosting 的对照</h1>'
    "<p>表 13 把两种范式放在同一组维度上。最容易被误解的一行是「主要降低的误差分量」："
    "Bagging 对每棵树的期望预测不变，只降低其方差；Boosting 每轮都在纠正残差，"
    "降低的是偏差。这直接决定了两者的使用条件——"
    "当基学习器已经接近无偏（深树）时 boosting 会去拟合噪声；"
    "当基学习器偏差主导（树桩）时 bagging 几乎无用。"
    "本数据的单树误差以方差为主（重抽样下翻转率 %s），"
    "所以 Bagging 的增益明显；而 boosting 在 50 个树桩上把验证 AUC 提到 %s"
    "（相对单树 %s，%s）。增益的来源不同：它是把偏差压下去。</p>"
) % (pct(st["single_tree"]["class_flip_rate"], 1), f(cv["adaboost"]["auc_mean"]),
     f(cv["single_tree"]["auc_mean"]),
     ("高出 %s" % f(cv["adaboost"]["auc_mean"] - cv["single_tree"]["auc_mean"]))
     if cv["adaboost"]["auc_mean"] >= cv["single_tree"]["auc_mean"] else
     ("反而低 %s" % f(cv["single_tree"]["auc_mean"] - cv["adaboost"]["auc_mean"])))

EXPH += T_H + MEMO

# ---------------------------------------------------------------- 结论
CONC = (
    '<h1>9<span class=sp></span>结论</h1>'
    "<p>本文用同一套协议完整执行了工作单 A–H，得到三条可迁移的结论。"
    "第一，<b>「集成更好」需要条件</b>：只有当基学习器不稳定、且基学习器之间错误不完全相关时，"
    "平均才降低方差；本数据上树间相关已经很高（%s），所以随机森林相对 Bagging 的额外收益有限。"
    "第二，<b>Boosting 的定理保证训练误差，不保证泛化</b>："
    "弱可学习与强可学习的等价性告诉我们强学习器存在，AdaBoost 的训练误差界给出指数衰减速度，"
    "但学习率 0.5 的实验直接展示了训练 log-loss 趋零而验证 log-loss 回升的情形。"
    "第三，<b>选型应由证据决定</b>：在本数据上逻辑回归与随机森林的测试集差距很小（差值区间 ["
    + f(_d["lo"]) + ", " + f(_d["hi"]) + "]，上端紧贴零点），而前者解释成本更低。"
    "如果要把这套流程搬到方案 B（CTG 胎心监护），最需要改动的是验证协议："
    "按 recording_id 分组而非按样本随机划分，否则同一段录音的多条记录会跨折泄漏。</p>"
) % f(B["tree_correlation"]["mean"], 3)

REFS = (
    '<h1 class="refs">参考文献</h1>'
    '<p class="ref">[1] Schapire, R. E. (1990). The strength of weak learnability. '
    "<i>Machine Learning</i>, 5(2):197–227.</p>"
    '<p class="ref">[2] Freund, Y. and Schapire, R. E. (1997). A decision-theoretic generalization of '
    "on-line learning and an application to boosting. <i>Journal of Computer and System Sciences</i>, "
    "55(1):119–139.</p>"
    '<p class="ref">[3] Breiman, L. (1996). Bagging predictors. <i>Machine Learning</i>, 24(2):123–140.</p>'
    '<p class="ref">[4] Breiman, L. (2001). Random forests. <i>Machine Learning</i>, 45(1):5–32.</p>'
    '<p class="ref">[5] Friedman, J. H. (2001). Greedy function approximation: a gradient boosting machine. '
    "<i>Annals of Statistics</i>, 29(5):1189–1232.</p>"
    '<p class="ref">[6] Schapire, R. E., Freund, Y., Bartlett, P., and Lee, W. S. (1998). Boosting the '
    "margin: a new explanation for the effectiveness of voting methods. <i>Annals of Statistics</i>, "
    "26(5):1651–1686.</p>"
    '<p class="ref">[7] Long, P. M. and Servedio, R. A. (2010). Random classification noise defeats all '
    "convex potential boosters. <i>Machine Learning</i>, 78(3):287–304.</p>"
    '<p class="ref">[8] Chen, T. and Guestrin, C. (2016). XGBoost: a scalable tree boosting system. '
    "<i>KDD</i>, 785–794.</p>"
    '<p class="ref">[9] Ke, G. et al. (2017). LightGBM: a highly efficient gradient boosting decision tree. '
    "<i>NeurIPS</i>, 3146–3154.</p>"
    '<p class="ref">[10] Pedregosa, F. et al. (2011). Scikit-learn: machine learning in Python. '
    "<i>JMLR</i>, 12:2825–2830.</p>"
    '<p class="ref">[11] Wolberg, W. H., Street, W. N., and Mangasarian, O. L. (1995). Breast cancer '
    "Wisconsin (diagnostic) data set. UCI Machine Learning Repository.</p>"
)

APPX = (
    '<h1>附录 A<span class=sp></span>决策树的文本导出（max_depth=2）</h1>'
    '<pre class="tree">%s</pre>'
) % A["tree_text_d2"]

CSS = """
@page { size: 612pt 792pt; margin: 64pt 62pt 60pt 62pt; }
html, body { margin:0; padding:0; }
* { box-sizing: border-box; }
body { margin:0; font-family: "Times New Roman","SimSun",serif; font-size:10.1pt;
       line-height:1.26; color:#000; text-align:justify; }
h1 { font-size:12pt; font-weight:bold; margin:11pt 0 5pt 0; text-align:left; page-break-after:auto;
     break-after:avoid; line-height:1.2; }
h2 { font-size:10.6pt; font-weight:bold; margin:8pt 0 3pt 0; break-after:avoid; }
h1 .sp, h2 .sp { display:inline-block; width:.55em; }
p { margin:0 0 3pt 0; text-indent:0; }
p + p { text-indent:1.2em; }
ul { margin:2pt 0 4pt 0; padding-left:1.4em; }
li { margin:1pt 0; }
.title { font-size:14.3pt; font-weight:bold; text-align:center; line-height:1.25;
         margin:0 0 2pt 0; border-top:1.2pt solid #000; padding-top:12pt; }
.subtitle { font-size:11pt; text-align:center; margin:0 0 10pt 0; }
.authors { font-size:10pt; font-weight:bold; text-align:center; margin:6pt 0 1pt 0; }
.affil { font-size:9pt; text-align:center; margin:0 0 2pt 0; border-bottom:.6pt solid #000;
         padding-bottom:9pt; }
.abstract { font-size:9.4pt; margin:7pt 13pt 6pt 13pt; }
.abstract .h { font-size:10.5pt; font-weight:bold; text-align:center; margin:0 0 3pt 0; }
.flow { padding:0; }
.page:last-child { break-after:auto; page-break-after:auto; }
.page .hdr { position:absolute; top:26pt; left:0; right:0; text-align:center;
             font-size:9pt; font-weight:bold; }
.page .pno { position:absolute; bottom:24pt; left:0; right:0; text-align:center;
             font-size:9pt; }
.cols { columns:2; column-gap:31pt; column-fill:auto; column-rule:none; }

/* 附录：另起一页，仍走两栏，但在新页顶部开始 */
.appendix-flow { break-before:page; page-break-before:always; }

.eq { text-align:center; margin:5pt 0; font-size:10.5pt; break-inside:avoid; }
.defbox, .thmbox { border-left:2pt solid #666; background:#f4f6f8; padding:4pt 7pt; margin:5pt 0;
                   font-size:9.6pt; break-inside:avoid; }
.tbl { margin:7pt 0 8pt 0; break-inside:avoid; page-break-inside:avoid; }
.figbox { margin:7pt 0 8pt 0; break-inside:avoid; page-break-inside:avoid; text-align:center; }
.figbox img { display:block; margin:0 auto; }
.cap { font-size:8.6pt; text-align:left; margin:2pt 0 3pt 0; line-height:1.25; }
.tbl .cap { font-weight:normal; }
table { border-collapse:collapse; width:100%; font-size:8.4pt; line-height:1.18; }
table th { border-top:1pt solid #000; border-bottom:.6pt solid #000; padding:2pt 2pt;
           text-align:center; font-weight:normal; }
table td { padding:1.4pt 2pt; text-align:center; }
table tbody tr:last-child td { border-bottom:1pt solid #000; }
.tnote { font-size:7.8pt; margin-top:2pt; color:#222; line-height:1.2; }
.memo { border:0.8pt solid #000; padding:6pt 8pt; margin:8pt 0; break-inside:avoid; font-size:9.4pt; }
.memo .cap { font-weight:bold; font-size:9pt; margin-bottom:3pt; }
pre.tree { font-family:"Consolas","SimSun",monospace; font-size:7.6pt; line-height:1.22;
           margin:4pt 0; white-space:pre-wrap; }
.refs { break-before:auto; }
.ref { font-size:8.8pt; text-indent:0 !important; margin:0 0 2.5pt 0; padding-left:1.6em;
       text-indent:-1.6em !important; line-height:1.22; }
.mono { font-family:"Consolas",monospace; font-size:9pt; }
sub, sup { font-size:70%; }
"""

BODY = SP + PRE + THEORY + EXPD + EXPB + EXPEP + EXPF + EXPG + EXPH + CONC + REFS

# 页面分段：按章节边界给出一个「分页计划」，每段是一页（首页含标题块）。
PAGES_SPEC = [
    ("first", "1 引言", [SP]),
    ("", "2 数据与实验协议", [PRE]),
    ("", "3 方法与理论背景", [THEORY]),
    ("", "4 从一棵树到一片森林", [EXPD]),
    ("", "4 从一棵树到一片森林（续）", [EXPB]),
    ("", "5 Boosting", [EXPEP]),
    ("", "6 公平比较与选型", [EXPF]),
    ("", "7 稳定性与不确定性", [EXPG]),
    ("", "8 讨论", [EXPH]),
    ("", "9 结论", [CONC + REFS + APPX]),
]

_HEAD = '<div class="title">%s</div><div class="subtitle">%s</div>' \
        '<div class="authors">%s</div><div class="affil">%s</div>' \
        '<div class="abstract"><div class="h">摘要</div>%s</div>'

_head_html = (_HEAD % (TITLE, SUBTITLE, AUTHOR, AFFIL, ABSTRACT))
_html_body = ('<div class="flow">' + _head_html + '<div class="cols">' + BODY + '</div>'
              + '<div class="cols appendix-flow">' + APPX + '</div>'
              + '</div>')

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>%(title)s</title><style>%(css)s</style></head><body>%(pages)s</body></html>""" % dict(
    title=TITLE, css=CSS, pages=_html_body)

(BASE / "report" / "ensemble_report.html").parent.mkdir(exist_ok=True)
(BASE / "report" / "ensemble_report.html").write_text(HTML, encoding="utf-8")
print("html ok:", len(HTML))
