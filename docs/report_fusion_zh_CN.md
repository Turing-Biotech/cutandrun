# 交付报告融合（图凌生物口径）— report_fusion_zh_CN.md

把 vendor 参考报告（嘉因生物交付版，`data/cut-tag/report.html`，ztree 目录树 +
封面 + 3 个分析 Section + 附录）的结构，移植为图凌生物交付报告，并把本管线
（nf-core/cutandrun）的真实质控层嵌进去。

**生成器**：`scripts/fuse_report_zh.py`（纯新增，Python3 标准库，零上游修改）。
vendor 原目录只读；所有改动只发生在 `--outdir` 生成树上，重复运行幂等
（每次从干净 outdir 重建）。

## 用户裁决（2026-11-19，四条）

| # | 议题 | 裁决 |
|---|------|------|
| Q1 | 品牌块（嘉因生物文字×5 / logo / 公众号二维码） | 不出现其它公司名称，按图凌生物处理；logo 用纯文字占位，素材到位后替换 |
| Q2 | vendor 21 阶段商业流程图 | 两阶段：Phase 1 先给 8 模块能给出的全部信息并登记缺失；Phase 2 补模块后完善 |
| Q3 | S1 比对口径（参考报告写 BWA） | 按本管线实际使用（bowtie2） |
| Q4 | 8 张占位示例图（Fake/example_） | 后续补真实数据，现阶段登记缺失并加「示例图」角标 |

## 做了什么

1. **外壳搬移** — vendor `report.html` + 全部 21 阶段资产目录原样进 outdir。
   左侧 ztree 目录由 vendor 自带 `js/ztree_toc.js` 在渲染时从 `:header`
   动态生成并自动编号，**插入新 Section 后目录自动更新，无需维护**。
2. **品牌（Q1）** — 「嘉因生物」×5 → 「图凌生物」（附录删除后正文剩余 1 处）；
   侧栏 rainbow-genome logo 链接、封面 `cover_jiayin.png` 各换为
   图凌文字占位块；vendor 公众号微信链接（S1 可视化引用 + 附录相册）移除
   为待定标注。素材到位后只需替换占位块内的 `img`。
2b. **附录删除（2026-11-19 裁决）** — 「附录」h1 整节移除（公众号 h3×2 +
   二维码 + 客户文章链接），文档以 vendor post-content script 块收尾；
   生成器内 MultiQC Section 的自引用改为指向文内「数据口径与缺失登记」小节。
3. **流程图（Q2）** — S1 前「生物信息分析流程」改为双轨：主图为 8 模块
   流程图（`imgExtra/pipeline_8modules.png`，本管线实际流程，与 01-04
   发布目录一一对应），vendor 21 阶段图降级为附图并加「交付全流程」角标。
4. **比对口径（Q3）** — S1 方法段中英文的 BWA 表述改为实际使用的
   Bowtie2（含 `-D 20 -R 3 -N 0 -L 20 -E 2 -u 4` 局部比对模式与
   target + spike-in 双比对）。
5. **MultiQC 中文质控 Section** — 在 S1 末（S2 h1 前）插入
   「标准分析 Section 1.5-质控交互报告（MultiQC 中文版）」：中文方法段 +
   `multiqc/multiqc_report.html` 高 900px iframe + 新窗口直链 +
   「数据口径与缺失登记」小节。MultiQC 报告自包含（内联数据，无本地
   外部依赖），iframe 嵌入无断链。
6. **占位图（Q4）** — 文件名含 `Fake/example_` 的 8 张图各加红底白字
   「示例图」角标（注入 `<style>`，vendor CSS 未动）。
7. **交叉核对层（`--cross-check`）** — 解析 vendor 宽表 T6（MappedRate%）
   与 T7（Peaknum），对照本运行发布树（bowtie2 log 比对率、MACS2/SEACR
   narrowPeak 行数、consensus 110,296），在「比对结果统计」与
   「Peak Calling」两节插入口径说明表（并列展示、不互相覆盖）+
   `crosscheck.json`（机器可读）。样本名 C1/E3 → 管线 rid C_R1/E_R3
   自动映射。

## 缺失登记（Phase 2 销账）

`assets/zh_CN/missing_data_registry.yml`：
- **multiqc_work_only** — FRiP / peak 可重复性 / 片段长度 / Picard 重复率 /
  软件版本 6 样本面：数据只在被清理的 8-19 multiqc work/ 面，未发布；
  期望数据契约与 Phase 2a 补法（发布面带上 work 产物，或从 bam 重算）。
- **M1 de novo motif 图 ×4**、**M2 GO/KEGG 网络图 ×4** — 补 HOMER /
  clusterProfiler+igraph 模块后替换销账。
- **M3 差异 Peak 全链（S3 全部）** — 非本管线产物，补 R 后处理模块或
  显式标注「交付后处理流程完成」。

## 替换串单一来源

定点替换表（before/after 逐字固定）在
`assets/zh_CN/fuse_report_terms.yml`；脚本内常量与之保持一致。

## 用法

```bash
python3 scripts/fuse_report_zh.py \
  --vendor-dir  …/data/cut-tag \            # 只读 vendor 交付目录
  --outdir      …/data/report \             # 自包含交付树（幂等重建）
  --multiqc-html <rendered zh multiqc_report.html> \
  --flow-png    <8-module flow png> \
  --cross-check --run-root <published output/ tree>
# 只跑验收（不重建）：
python3 scripts/fuse_report_zh.py --verify-only --outdir …/data/report
```

## 验收（24 项内嵌于 `--verify`，当前 ALL PASS）

标题 ≥38（vendor 39 − 附录 3 + MultiQC 1）；附录 h1/公众号残留 0；MultiQC
Section/iframe 在位；嘉因/jiayin/rainbow/vendor 微信链接/BWA 旧表述全部 0
残留；图凌在位；Bowtie2 中英文段在位；表 ≥28（vendor 28 + 口径 2）；全部
img 引用可解析；「示例图」角标 ==8；8 模块主图 + 21 阶段附图均在；
multiqc zh 报告标题/Peak QC 中文化/无 tofu；css/js/imgHeader/imgTail 资产目录在位。

## 数字口径（2026-11-19 渲染实例）

比对率：vendor 97.01–99.03%（BWA 流程） vs 本管线 94.94–97.73%（bowtie2
target），全部与 02 发布树 bowtie2 log 对出。
Peak 数：vendor 626–3986；本管线 MACS2 129,711/221,472/19,175，
SEACR 4,642/11,511/95,000，consensus 110,296（E 组）。两组调用参数不同，
口径说明表已注明不直接可比。
