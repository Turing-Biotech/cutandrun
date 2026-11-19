#!/usr/bin/env python3
"""fuse_report_inventory.py — 只读资产清点，为交付报告融合提供审计基线。

两种模式（对应 plan §1 / §3-T1）：

  vendor 模式（默认）：扫 vendor 交付目录（data/cut-tag/）
    - report.html 标题树（tag/id/text/pos）
    - img 引用 × （存在? / 大小 / 是否占位名 Fake|example_）
    - 表数量、CSS/JS web 资产存在性
    - 品牌串出现清单（嘉因/jiayin/rainbow/weixin-公众号链接）
    - 手术锚点注册表（供 fuse_report_zh.py 校验锚点存活）
    exit 0 = 全部资产可解析；exit 1 = 有缺失引用（列出）

  pipeline 模式：扫 nf-core/cutandrun 输出（02 生产运行或 WSL 侧运行）
    - 4 阶段目录关键产物绝对路径（fastqc/trimgalore/bowtie2/peak 全链/reporting）
    - --work-dir：MultiQC 输入面（可纯报告侧重建中文 MultiQC 报告的数据集）
    exit 0 = 清点完成（允许缺项，逐项标注 MISSING）

只读，不写任何文件（--out 写审计文本到输出目录或 cwd）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

PLACEHOLDER_RE = re.compile(r"(fake|example_)", re.I)
BRAND_KEYWORDS = ["嘉因", "jiayin", "Jiayin", "rainbow-genome", "本公司"]

# 手术锚点（vendor report.html 必须存在，供 fuse_report_zh.py 复用）
SURGERY_ANCHORS = {
    "cover_h2": 'class="baseImg">',
    "cover_img": "./imgHeader/cover_jiayin.png",
    "logo_sidebar_img": "./imgHeader/logo.jpg",
    "rainbow_link": "http://www.rainbow-genome.com",
    "flow_img": "./imgHeader/CUT_Tag3.png",
    "flow_intro_p": "通过如下图标准流程进行生物信息分析",
    "align_h2": '<h2 class="chapterTitle mar-top-80">比对分析</h2>',
    "bwa_para1": "本次分析采用 BWA 比对软件",
    "bwa_para2_tail": "本项目分析采用的是 BWA-MEM。</p>",
    "bwa_english_line": "using the bwa program",
    "bwa_result_path": "3.BwaMapping_v1",
    "s1_end_s2_h1": '标准分析 Section 2-peak分析',
    "s2_h1_tag": '<h1 class="chapterTitle mar-top-80">',
    "appendix_h1": '>附录</h1>',
    "brand_bg_text": "嘉因生物对样品检测",
    "brand_apx_1": "嘉因生物公众号",
    "brand_apx_2": "嘉因生物微信公众号-客户文章链接",
    "tail_qr_img": "./imgTail/jiayin.jpg",
}


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def vendor_inventory(vendor_dir: str, lines: list[str]) -> int:
    html_path = os.path.join(vendor_dir, "report.html")
    missing: list[str] = []
    h = read_text(html_path)

    lines.append(f"vendor dir        : {vendor_dir}")
    lines.append(f"report.html bytes : {os.path.getsize(html_path)}")
    lines.append(f"report.html chars : {len(h)}")

    # --- heading tree ---
    heads = []
    for m in re.finditer(r"<(h[1-4])\b([^>]*)>(.*?)</\1>", h, re.S):
        idm = re.search(r'id="([^"]*)"', m.group(2))
        heads.append((m.start(), m.group(1), (idm.group(1) if idm else ""), strip_tags(m.group(3))[:60]))
    lines.append(f"\nHEADINGS ({len(heads)}):")
    for pos, tag, idv, txt in heads:
        lines.append(f"  {pos:>7} {tag} {('#' + idv) if idv else '(no-id)':<26} {txt}")

    # --- imgs ---
    img_refs = []
    for m in re.finditer(r"<img\b[^>]*src=\"([^\"]+)\"", h):
        img_refs.append(m.group(1))
    uniq_imgs = sorted(set(img_refs))
    lines.append(f"\nIMGS ({len(img_refs)} refs, {len(uniq_imgs)} unique):")
    placeholders = []
    for ref in uniq_imgs:
        p = os.path.join(vendor_dir, ref.lstrip("./"))
        ok = os.path.isfile(p)
        flag = " PLACEHOLDER" if PLACEHOLDER_RE.search(os.path.basename(ref)) else ""
        size = os.path.getsize(p) if ok else 0
        if not ok:
            missing.append(ref)
        if PLACEHOLDER_RE.search(os.path.basename(ref)):
            placeholders.append(ref)
        lines.append(f"  {'OK ' if ok else 'MISSING'} {size:>10} {ref}{flag}")
    lines.append(f"PLACEHOLDER IMGS ({len(placeholders)}): " + "; ".join(placeholders))

    # --- tables ---
    ntab = len(re.findall(r"<table\b", h))
    lines.append(f"\nTABLES: {ntab}")

    # --- web assets ---
    web_missing = []
    for tag in ("link", "script"):
        for m in re.finditer(rf"<{tag}\b[^>]*href=\"([^\"]+)\"", h):
            ref = m.group(1)
            if ref.startswith("http"):
                continue
            p = os.path.join(vendor_dir, ref.lstrip("./"))
            if not os.path.isfile(p):
                web_missing.append(ref)
                lines.append(f"  WEB MISSING {tag}: {ref}")
        for m in re.finditer(rf"<{tag}\b[^>]*src=\"([^\"]+)\"", h):
            ref = m.group(1)
            if ref.startswith("http"):
                continue
            p = os.path.join(vendor_dir, ref.lstrip("./"))
            if not os.path.isfile(p):
                web_missing.append(ref)
                lines.append(f"  WEB MISSING {tag}: {ref}")
    lines.append(f"WEB assets: css/js refs all resolved={not web_missing} ({len(web_missing)} missing)")

    # --- brand strings ---
    lines.append("\nBRAND STRINGS:")
    for kw in BRAND_KEYWORDS:
        ms = [m.start() for m in re.finditer(re.escape(kw), h)]
        lines.append(f"  {kw}: {len(ms)}  at {ms[:10]}")

    # --- surgery anchors ---
    lines.append("\nSURGERY ANCHORS (fuse_report_zh.py):")
    anchor_bad = []
    for name, needle in SURGERY_ANCHORS.items():
        n = h.count(needle)
        if n == 0:
            anchor_bad.append(name)
        lines.append(f"  {'OK ' if n else 'MISSING'} x{n} {name}: {needle[:60]}")

    lines.append("\nRESULT: " + ("ALL ASSETS RESOLVED" if not missing and not web_missing and not anchor_bad
                                  else f"MISSING={len(missing)} IMG, {len(web_missing)} WEB, {len(anchor_bad)} ANCHOR"))
    return 0 if (not missing and not web_missing and not anchor_bad) else 1


PIPELINE_MARKERS: dict[str, list[tuple[str, str]]] = {
    "01_prealign": [
        ("pretrim fastqc zip", "pretrim_fastqc/**/*_fastqc.zip"),
        ("trimgalore report",  "trimgalore/**/*.html"),
        ("trimmed fastq",      "trimgalore/**/*.fastq.gz"),
    ],
    "02_alignment": [
        ("bowtie2 target log",   "bowtie2/**/*bowtie2.log"),
        ("bowtie2 spikein log",  "bowtie2_spikein/**/*bowtie2.log"),
        ("target bam",           "bowtie2/**/*.bam"),
        ("spikein bam",          "bowtie2_spikein/**/*.bam"),
    ],
    "03_peak_calling": [
        ("bedgraph",        "01_bam_to_bedgraph/*"),
        ("clip bed",        "02_clip_bed/*"),
        ("bigWig",          "03_bed_to_bigwig/*"),
        ("called peaks",    "04_called_peaks/*"),
        ("consensus peaks", "05_consensus_peaks/*"),
        ("fragments",       "06_fragments_from_bams/*"),
    ],
    "04_reporting": [
        ("deeptools QC",        "deeptools_qc/*"),
        ("heatmaps gene",       "deeptools_heatmaps/gene/*"),
        ("heatmaps peaks",      "deeptools_heatmaps/peaks/*"),
        ("preseq",              "preseq/*"),
        ("igv",                 "igv/*"),
        ("consensus upset",     "consensus_upset_plots/*"),
        ("multiqc (发布树)",     "multiqc/multiqc_report.html"),
        ("software versions",   "software_versions_summary/*"),
    ],
    "pipeline_info": [
        ("execution reports", "execution_report_*.html"),
    ],
}

# MultiQC 输入面（work 目录下按模块分子目录，见 multiqc.nf input）
MQC_INPUT_SURFACE = [
    "bowtie2/*bowtie2.log",
    "bowtie2_spikein/*bowtie2.log",
    "fastqc/*fastqc.zip",
    "trimgalore/*",
    "samtools/stats/*",
    "samtools/flagstat/*",
    "samtools/idxstats/*",
    "picard/markduplicates/*",
    "preseq/*",
    "deeptools/*",
    "peak_metrics/peak_count/*",
    "peak_metrics/peak_frip/*",
    "peak_metrics/peak_count_consensus/*",
    "peak_metrics/peak_reprod_perc/*",
    "frag_len/*",
    "linear_duplicates/*",
    "software_versions/software_versions_unique_mqc.yml",
    "workflow_summary/*",
]


def _glob(dirp: str, pattern: str) -> list[str]:
    import glob as _g
    return sorted(_g.glob(os.path.join(dirp, pattern), recursive=True))


def pipeline_inventory(pipe_dir: str, work_dir: str | None, lines: list[str]) -> int:
    lines.append(f"pipeline dir : {pipe_dir or '(unset)'}")
    lines.append(f"work dir     : {work_dir or '(unset)'}")

    if pipe_dir and os.path.isdir(pipe_dir):
        lines.append(f"\nPIPELINE STAGE PRODUCTS ({pipe_dir}):")
        for stage, markers in PIPELINE_MARKERS.items():
            sp = os.path.join(pipe_dir, stage)
            if not os.path.isdir(sp):
                lines.append(f"  [MISSING DIR] {stage}")
                continue
            lines.append(f"  {stage}:")
            for label, pat in markers:
                hits = _glob(sp, pat)
                if hits:
                    lines.append(f"    OK   x{len(hits):<3} {label}")
                else:
                    lines.append(f"    MISS       {label}  ({pat})")
    else:
        lines.append("\n[skip] pipeline dir unset or not a dir")

    if work_dir and os.path.isdir(work_dir):
        lines.append(f"\nMULTIQC INPUT SURFACE ({work_dir}):")
        total = 0
        for pat in MQC_INPUT_SURFACE:
            hits = _glob(work_dir, pat)
            total += len(hits)
            lines.append(f"  {'OK  ' if hits else 'MISS'} x{len(hits):<3} {pat}"
                         + (f"  e.g. {os.path.relpath(hits[0], work_dir)}" if hits else ""))
        sv = os.path.join(work_dir, "software_versions")
        n_sv = len(os.listdir(sv)) if os.path.isdir(sv) else 0
        lines.append(f"  software_versions dir: {n_sv} entries")
        lines.append(f"  TOTAL input-surface files: {total}")
    else:
        lines.append("\n[skip] work dir unset or not a dir")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["vendor", "pipeline"], default="vendor")
    ap.add_argument("--vendor-dir", help="vendor 交付目录（含 report.html）")
    ap.add_argument("--pipeline-dir", help="cutandrun 输出目录（01_prealign/.../pipeline_info）")
    ap.add_argument("--work-dir", help="multiqc work 输入面目录（可选）")
    ap.add_argument("--out", help="审计文本输出路径（默认 stdout）")
    a = ap.parse_args()

    lines = [f"fuse_report_inventory  {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
             f"{'=' * 70}"]
    if a.mode == "vendor":
        if not a.vendor_dir:
            print("vendor mode requires --vendor-dir", file=sys.stderr)
            return 2
        rc = vendor_inventory(a.vendor_dir, lines)
    else:
        rc = pipeline_inventory(a.pipeline_dir, a.work_dir, lines)

    text = "\n".join(lines) + "\n"
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"inventory written -> {a.out}")
    print(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
