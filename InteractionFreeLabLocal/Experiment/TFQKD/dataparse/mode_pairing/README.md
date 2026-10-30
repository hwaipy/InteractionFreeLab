# Mode-pairing QKD 模型与论文复现

状态：**研究模型可运行，但“所有理论和实验论文均吻合”的验收尚未通过。**
不能把最终密钥公式回代、原始计数估计、独立光学仿真三者混为一谈。
现有 SNS/AOPP 程序不参与本模型。

## 文献与复现范围

1. Pei Zeng, Hongyi Zhou, Weijie Wu, Xiongfeng Ma, **Mode-pairing quantum key distribution**, Nature Communications 13, 3903 (2022).
   [正式论文](https://doi.org/10.1038/s41467-022-31534-7)，[开放正文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9262923/)，[预印本及推导](https://arxiv.org/abs/2201.04300)。
   当前理论实现逐式对应 arXiv v2 Appendix D1–D15、Fig.4；正式版对应 Fig.3。
   参数：每探测器背景 1.2e-8、效率 20%、损耗 0.2 dB/km、失配 4%、f=1.15。
   原始绘图数据和代码需要向作者申请；目前验证了公式、极限及随机配对，未声称逐像素重合。
2. Hao-Tao Zhu et al., **Experimental Mode-Pairing Measurement-Device-Independent Quantum Key Distribution without Global Phase Locking**, PRL 130, 030801 (2023).
   [论文](https://doi.org/10.1103/PhysRevLett.130.030801)，[含补充材料的预印本](https://arxiv.org/abs/2208.05649)。
   Table VI 四个距离：101/202/304/407 km。当前验证配对率 B7，并回代论文公布的单光子数和相位界；尚未从这篇所有原始计数重做诱骗估计。
3. Hao-Tao Zhu et al., **Field test of mode-pairing quantum key distribution**, Optica 11, 883 (2024).
   [论文](https://doi.org/10.1364/OPTICA.520697)，[预印本](https://arxiv.org/abs/2403.09339)。
   对称 195.85 km、非对称 127.92 km；录入 Table V 原始计数与 Table VI 中间界。
   Z 单光子下界接近表格，X 相位界未复现；详见下文。
4. Likang Zhang et al., **Experimental Mode-Pairing Quantum Key Distribution Surpassing the Repeaterless Bound**, PRX 15, 021037 (2025).
   [论文及附录](https://doi.org/10.1103/PhysRevX.15.021037)。
   录入 Table I/III，使用 C1–C9；202/403 km 原始计数估计已接近发表值，101 km 有一项转录歧义。
5. Lai Zhou et al., **Experimental Quantum Communication Overcomes the Rate-Loss Limit without Global Phase Tracking**, PRL 130, 250801 (2023).
   [论文](https://doi.org/10.1103/PhysRevLett.130.250801)。
   是相关的异步配对实现，413/508 km 对应 590.61/42.64 bit/s。
   本版本只登记文献，未把它与上述 MP 参数配置混用，尚未实现其完整有限码长分析。

文献通过网页正文/PDF 文本读取；本地 PDF 下载的提权请求被拒绝。
PDF 截图也未成功，因此表格歧义单独保留，未猜数字来对齐结果。

## 运行

在本目录运行：

```bash
/opt/homebrew/bin/python run.py
/opt/homebrew/bin/python reproduce.py
/opt/homebrew/bin/python -m unittest discover -s . -p test_model.py
```

`run.py` 的所有配置位于 `main()`：发送概率、强弱源、两臂损耗、探测效率、背景概率、总时隙数、配对长度、线宽、残余相位漂移等。
它生成 `results/simulation.json`。

`reproduce.py` 生成：

- `results/validation.json`：逐项结果、偏差、失败原因，`all_papers_reproduced` 当前固定为 false。
- `results/theory_curves.png` / `.json`：七种配对窗口的理论距离曲线和数据。
- `results/experimental_checks.png`：实验对照，明确区分回代与原始计数估计。
- `results/phase_noise.png`：PRX B10 相位噪声模型。

程序与文献参数保留为可跟踪文件；生成结果由本目录 `.gitignore` 忽略。

## 模型接口

- `model.theory_rate` / `optimize_theory`：原始理论的渐近模型，独立优化 mu。
- `model.expected_counts`：相干态、分束器、两个阈值探测器，只保留单击；枚举 Z 编码，积分 X 探测奇偶性，输出各源组合期望计数。
- `monte_carlo.simulate`：逐脉冲生成源选择、随机相位和探测器点击；按时序贪心配对，生成整数 Z/X 计数。
- `model.analytical_estimate`：对称三强度解析诱骗界、两次 Chernoff、随机抽样相位界。
- `decoy.estimate`：用于核对 2024 附录的光子数后验 LP；默认使用原始错误计数，失败会报错。
- `decoy.estimate_prx2025`：LP 诱骗界加直接 Chernoff 和随机抽样，用于 PRX 原始计数复算。

矩阵均为 3×3，行 Alice、列 Bob，顺序 `[0, nu, mu]`。
X 标签表示两个脉冲总强度 `[0, 2nu, 2mu]`。
`z/x` 是探测配对数，`ze/xe` 是其中错误数。
期望模型输出浮点均值；逐脉冲仿真输出整数实现。

统一 `keyrate = key_bits / n_slots`：一个时隙指 Alice/Bob 同时各发送一个脉冲。
`bits_per_second = keyrate * quantum_clock_hz`，有效频率已含量子帧占空比。
2023/2024 的 “bit per pair” 数值与每两个发送时隙归一化一致，应除以 2 才能与本接口比较；这里不是除以探测成功后的配对数。

## 尚未通过的检查与限制

- 2023 年 202 km：用 Table VI 的 5.03e7 单光子数、25.71% 相位界和原始 Z 误码回代，约为 1827 bit/s，表格为 2080 bit/s。其它三点差异小于 0.6%。此差异不能靠显示精度充分解释；尚不能断言是论文错误。
- 2024 年：若直接使用 Table V 的真空 X 错误计数，并同时施加 A8 的真空光子错误率 1/2 约束，当前 LP 不可行。`vacuum_errors='random_bit'` 明确把真空错误期望设为探测数一半，只是诊断选项，绝非悄悄修改实验数据。该诊断下 Z 单光子数已接近论文，但相位上界仍约 0.41/0.40，而论文约 0.313/0.315。因此不能用“回代最终率吻合”代替全链路复现。
- 2025 年：文本抽取的 101 km `X(2mu,0)` 为 `14 554 3908`，含歧义；`papers.py` 保留原转录并标记，报告跳过该点，未擅自改成更符合预期的数值。
- PRX 的 `budget='per_bound'` 为每项使用 1e-10；`budget='union'` 会划分总失败预算。不同预算结果同时记录。不能将单项失败率误称为整个协议的可组合安全参数。
- LP 截断 8/12/16 光子数做数值收敛检查，尚未完成截断尾项的安全证明。当前用途是研究复现，不能视为已认证的最终隐私放大实现。
- 渐近原理论采用其低点击近似；光学模型采用恰好一只探测器点击的精确相干态概率，两者不应在高透过率时强求完全一致。
- `expected_counts` 的相位噪声对奇偶关联的衰减采用弱光近似。逐脉冲模拟可检查这一近似。量子/参考帧边界、真实频率跟踪残差和探测器死时间尚未完整建模；`lmin` 是数据筛选，不等同于硬件死时间。
- 2024 光学对照保留探测效率是否已含在 eta、lmin 是否沿用 63 的四种解释；未把接近实验的解释冒充论文明确给出的参数。

下一步验收应先解决 X 真空计数定义、实验方使用的 LP/失败预算及 PRX 表格转录，再补全三个实验的光学端到端曲线。不要通过手动改计数、拟合目标成码率或增设乘法因子使验证通过。
