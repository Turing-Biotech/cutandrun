#!/usr/bin/env python3
"""Assemble the MultiQC input face for a nf-core/cutandrun run whose work/
directory has been cleaned.

Reads the PUBLISHED output tree (01_prealign/02_alignment/03_peak_calling/
04_reporting) of a finished run and builds a directory laid out exactly like
the work dir of the pipeline's MULTIQC process (modules/local/multiqc.nf),
plus recomputes the two deterministic peak-metric custom_content TSVs
(primary_peak_counts, consensus_peak_counts) exactly the way
modules/local/peak_counts.nf does:  cat <bed> | wc -l  + the repo's own
header asset (assets/multiqc/peak_counts_header.txt / _consensus_header.txt).
Byte-identical to what the pipeline emitted.

What this does NOT recover (work-only, gone once work/ is cleaned):
  peak_frip, peak_reprod_perc, frag_len (_mqc.yml), linear_duplicates,
  picard MarkDuplicates metrics, software_versions*, workflow_summary.
Those sections simply do not appear in the rendered report; the gap is
recorded in assets/zh_CN/missing_data_registry.yml, not silently filled.

Usage:
  python3 scripts/build_multiqc_input_face.py --outdir FACE6 --output-dir <run>/output
  # then
  multiqc -f -c assets/multiqc_config_zh_CN.yml -o OUT FACE6

Standard library only.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDR_COUNT = os.path.join(REPO, "assets/multiqc/peak_counts_header.txt")
HDR_CONSENSUS = os.path.join(REPO, "assets/multiqc/peak_counts_consensus_header.txt")

# (source glob under output dir, destination subpath inside face dir)
PUBLISHED_PATTERNS = [
    ("01_prealign/pretrim_fastqc/*_fastqc.zip",          "fastqc"),
    ("01_prealign/trimgalore/*_trimming_report.txt",     "trimgalore"),
    ("01_prealign/trimgalore/fastqc/*.zip",              "trimgalore/fastqc"),
    ("02_alignment/bowtie2/target/log/*",                "bowtie2"),
    ("02_alignment/bowtie2/spikein/log/*",               "bowtie2_spikein"),
    ("02_alignment/bowtie2/target/markdup/*.stats",      "samtools/stats"),
    ("02_alignment/bowtie2/target/markdup/*.flagstat",   "samtools/flagstat"),
    ("02_alignment/bowtie2/target/markdup/*.idxstats",   "samtools/idxstats"),
    ("04_reporting/preseq/*.lc_extrap.txt",              "preseq"),
    ("04_reporting/deeptools_qc/*plotFingerprint.raw.txt", "deeptools"),
    ("04_reporting/deeptools_qc/*plotFingerprint.qcmetrics.txt", "deeptools"),
    ("04_reporting/deeptools_qc/all_target_bams.plotPCA.tab", "deeptools"),
    ("04_reporting/deeptools_qc/all_target_bams.plotPCA.pdf", "deeptools"),
    ("04_reporting/deeptools_qc/all_target_bams.plotCorrelation.mat.tab", "deeptools"),
    ("04_reporting/deeptools_qc/all_target_bams.plotCorrelation.pdf", "deeptools"),
]

# Peak beds used only for the deterministic wc -l recompute (not copied as
# MultiQC input — peak metrics carry the counts, the beds do not feed 1.19).
# Per-sample dedup: prefer the MACS2 narrowPeak (the 8-19 final production
# run's output), fall back to the SEACR stringent bed — mirrors the
# pipeline's one E_*_mqc.tsv per sample (channel outputs share the meta.id
# prefix, last write wins).
PRIMARY_PEAK_BED_MACS2 = "03_peak_calling/04_called_peaks/macs2/*_peaks.narrowPeak"
PRIMARY_PEAK_BED_SEACR = "03_peak_calling/04_called_peaks/seacr/*"
CONSENSUS_PEAK_BED = "03_peak_calling/05_consensus_peaks/*.consensus.peaks*.bed"

# Consensus prefix (meta.group) is passed explicitly because it cannot be
# inferred from the bed filename. Target group only — controls never get
# peaks called (see PEAK_COUNTS / CONSENSUS_PEAKS in workflows/cutandrun.nf).
DEFAULT_CONSENSUS_PREFIXES = ("E",)


def sample_id(basename: str) -> str | None:
    """Peak bed names are <meta.id>.<caller>.peaks... — the id is the
    text before the first '.' (meta.id itself contains underscores, e.g.
    E_R1). Mirrors task.ext.prefix = meta.id in peak_counts.nf."""
    stem = basename
    for junk in (".md5",):
        if stem.endswith(junk):
            return None
    return stem.split(".")[0]


def read_header(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    if not txt.endswith("\n"):
        txt += "\n"
    return txt


def bed_line_count(path: str) -> int:
    n = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for _ in f:
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", required=True, help="face dir to build (created/cleaned first)")
    ap.add_argument("--output-dir", required=True, help="published run output/ tree")
    ap.add_argument("--consensus-prefix", action="append", default=None,
                    help="meta.group name for consensus *_mqc.tsv (repeatable; "
                         "default: C and E)")
    args = ap.parse_args()

    import glob
    out = args.outdir
    od = args.output_dir
    if not os.path.isdir(od):
        print(f"error: --output-dir not a directory: {od}", file=sys.stderr)
        return 2
    if os.path.exists(out):
        shutil.rmtree(out)

    # 1. published inputs -> pipeline MULTIQC layout
    copied = 0
    for pat, dest in PUBLISHED_PATTERNS:
        matches = sorted(glob.glob(os.path.join(od, pat)))
        if not matches:
            print(f"warn  no published files for: {pat}")
            continue
        dest_d = os.path.join(out, dest)
        os.makedirs(dest_d, exist_ok=True)
        for m in matches:
            shutil.copy2(m, dest_d)
            copied += 1
    print(f"copied {copied} published input files")

    # 2. primary peak counts: one {meta.id}_mqc.tsv per target sample.
    #    Prefer MACS2 narrowPeak over the SEACR stringent bed for the same
    #    sample id (one file per sample, as the pipeline emits).
    peak_d = os.path.join(out, "peak_metrics", "peak_count")
    os.makedirs(peak_d, exist_ok=True)
    hdr = read_header(HDR_COUNT)
    macs2: dict[str, str] = {}
    seacr: dict[str, str] = {}
    for bed in sorted(glob.glob(os.path.join(od, PRIMARY_PEAK_BED_MACS2))):
        rid = sample_id(os.path.basename(bed))
        if rid:
            macs2[rid] = bed
    for bed in sorted(glob.glob(os.path.join(od, PRIMARY_PEAK_BED_SEACR))):
        rid = sample_id(os.path.basename(bed))
        if rid:
            seacr.setdefault(rid, bed)
    n_pk = 0
    for rid in sorted(set(macs2) | set(seacr)):
        bed = macs2.get(rid, seacr[rid])
        n = bed_line_count(bed)
        with open(os.path.join(peak_d, f"{rid}_mqc.tsv"), "w", encoding="utf-8") as f:
            f.write(hdr)
            f.write(f"Peak Count\t{n}\n")
        src = "macs2" if rid in macs2 else "seacr"
        print(f"peak_count {rid}: {n}  ({src}, {os.path.basename(bed)})")
        n_pk += 1
    if n_pk == 0:
        print("warn  no primary peak beds found — primary_peak_counts section missing")

    # 3. consensus peak counts: one {group}_mqc.tsv per target group
    #    (controls get no peaks — consensus is built per target group only).
    groups = sorted(set(args.consensus_prefix or DEFAULT_CONSENSUS_PREFIXES))
    cons_d = os.path.join(out, "peak_metrics", "peak_count_consensus")
    os.makedirs(cons_d, exist_ok=True)
    hdr_c = read_header(HDR_CONSENSUS)
    beds = sorted(glob.glob(os.path.join(od, CONSENSUS_PEAK_BED)))
    # keep only the non-counts bed (awk/merged form) — line count of either
    # consensus bed is the consensus peak total; prefer the plain peaks bed.
    plain = [b for b in beds if "peak_counts" not in os.path.basename(b)]
    if not plain:
        plain = beds
    n = 0
    written = []
    for b in plain:
        base = os.path.basename(b)
        gid = sample_id(base)          # E.seacr.consensus.peaks.awk.bed -> E
        if gid not in groups:
            continue
        n = bed_line_count(b)
        with open(os.path.join(cons_d, f"{gid}_mqc.tsv"), "w", encoding="utf-8") as f:
            f.write(hdr_c)
            f.write(f"Peak Count\t{n}\n")
        written.append((gid, n, base))
    for gid, n, base in written:
        print(f"consensus_peak_counts {gid}: {n}  (from {base})")
    if not written:
        print("warn  no consensus bed for requested groups"
              f" {groups} — consensus_peak_counts section missing")

    print(f"face built at {out}: {copied} copied + {n_pk} primary + {len(written)} consensus tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
