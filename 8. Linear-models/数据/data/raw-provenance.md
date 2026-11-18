# 新增数据集来源说明（provenance）

获取时间：2026-11-03（由会话内浏览器直接落盘，未转录）。

## raw-breast_cancer_sklearn.csv
- 来源：https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/datasets/data/breast_cancer.csv
- 即 scikit-learn `load_breast_cancer()` 的内置数据文件（Wisconsin Diagnostic and Prognostic Breast Cancer, Wolberg & Mangasar, 1990s）。
- 格式：**第 1 行不是列名**，而是 `569,30,malignant,benign`（形状+类名）；其后 569 行数据，每行 30 个连续特征 + 1 个标签。
- 标签语义：`0 = malignant`（恶性，阳性/应预警），`1 = benign`。做二分类教学时建议把 malignant 记为正类。
- 特征：30 个均为连续量（radius/texture/perimeter/area/smoothness/compactness/concavity/concave points/symmetry/fractal_dimension × mean/se/worst 三组）。
- 已知特点：特征间强共线（面积与半径相关 ρ≈0.99），正类占比 62.7%（benign 多）。
- 校验：文件 570 行；首尾行与上游一致。

## raw-pima_diabetes_plotly.csv
- 来源：https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv
- 即 Pima Indians Diabetes（UCI / NIDDK, Kahn 1990）的 plotly 镜像，带列名。
- 格式：表头 + 768 行；列 `Pregnancies,Glucose,BloodPressure,SkinThickness,Insulin,BMI,DiabetesPedigreeFunction,Age,Outcome`。
- 标签：`Outcome 1 = 糖尿病`，阳性率约 34.9%。
- **注意**：Glucose/BloodPressure/SkinThickness/Insulin/BMI 中的 `0` 是生理上不可能的值，即“缺失被编码为 0”（官方文档口径）。本项目把它当作**数据假设压力测试素材**使用，不做插补修补（与 heart 的 0 哨兵问题同构，可对照讨论）。
- 校验：文件 769 行。

## 与既有数据的关系
- `data/heart.csv`：表头缺 `thal` 列名（17 名 vs 18 字段）、183/270 行含空字段——**带病，不直接用作主锚点**，仅作“脏数据审计”展示素材。
- `assets/pbl-linear-models-lda-logistic-regression/statlog-heart.csv`：干净的经典 StatLog heart（270×13+target，无缺失，阳性 120/44.4%），作为 heart 主锚点。
- 本目录两个 raw-*.csv 为新增真实锚点；其余实验数据由合成生成器现场产生。
