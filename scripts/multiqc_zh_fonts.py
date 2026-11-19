#!/usr/bin/env python3
"""multiqc_zh_fonts.py — 以 CJK 字体渲染 MultiQC 的启动器（纯新增，零上游修改）。

背景：MultiQC 1.19 的 matplotlib 图表（柱状/折线/分组图）默认走 DejaVu Sans。
中文 config（module_order info / custom_data 中文标题 / section_comments）下，
中文轴标签、图例、组名会字形缺失（UserWarning: Glyph … missing → 豆腐块）。
MultiQC 1.19 无字体配置入口。

机制：在临时目录生成 sitecustomize.py，经 PYTHONPATH 让 multiqc 子进程启动时
自动注册候选 CJK 字体并改写 font.sans-serif，再 exec 本机 venv 的 multiqc。
不修改 MultiQC 源码、不修改用户目录配置、不污染仓库之外的系统状态
（唯一落盘产物 = 临时 sitecustomize 目录，进程结束即可删）。

用法：
  python3 multiqc_zh_fonts.py -f -c CONFIG -o OUTDIR INPUTDIR …
等价于：
  PYTHONPATH=<tmp> multiqc -f -c CONFIG -o OUTDIR INPUTDIR …
（<tmp>/sitecustomize.py 完成字体注入）

退出码 = multiqc 退出码。
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

# 候选 CJK 字体：命中第一个作为主族，全部命中者进 sans 回退池。
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/mnt/c/Windows/Fonts/LXGWWenKai-Regular.ttf",
    "/mnt/c/Windows/Fonts/LXGWWenKai-Medium.ttf",
    "/mnt/c/Windows/Fonts/msyh.ttc",
    "/mnt/c/Windows/Fonts/simhei.ttf",
    "/mnt/c/Windows/Fonts/Deng.ttf",
]
GLOBAL_GLOBS = [
    "/usr/share/fonts/**/*CJK*.tt*",
    "/usr/share/fonts/**/*wqy*.ttc",
    "/usr/share/fonts/**/*uming*.tt*",
]

SITECUSTOMIZE_TMPL = '''
import sys

def _zh_fonts_setup():
    try:
        from matplotlib import font_manager as _fm
        import matplotlib as _mpl
    except Exception as _e:  # matplotlib 未安装（如子进程非渲染路径）——静默
        return
    _paths = {
        {_cand_lines}
    }
    _paths = [_p for _p in _paths if _p and __import__("os").path.isfile(_p)]
    if not _paths:
        return
    _names = []
    for _p in _paths:
        try:
            _fm.fontManager.addfont(_p)
            _nm = _fm.FontProperties(fname=_p).get_name()
            if _nm not in _names:
                _names.append(_nm)
        except Exception:
            pass
    cur = list(_mpl.rcParams.get("font.sans-serif", []) or [])
    for _i, _n in enumerate(_names):
        if _n not in cur:
            cur.insert(_i, _n)
    if "DejaVu Sans" not in cur:
        cur.append("DejaVu Sans")
    _mpl.rcParams["font.sans-serif"] = cur
    _mpl.rcParams["axes.unicode_minus"] = False
    if os.environ.get("MULTIQC_ZH_FONTS_VERBOSE"):
        _sys = sys.__stderr__
        _sys.write("multiqc_zh_fonts: sans-serif=%r\\n" % _names)

import os
_zh_fonts_setup()
'''


def find_cjk_fonts() -> list[str]:
    found: list[str] = [p for p in FONT_CANDIDATES if os.path.isfile(p)]
    for pat in GLOBAL_GLOBS:
        for p in sorted(glob.glob(pat, recursive=True)):
            if os.path.isfile(p) and p not in found:
                found.append(p)
    return found


def locate_multiqc() -> str:
    bin_dir = os.path.dirname(sys.executable)
    cand = os.path.join(bin_dir, "multiqc")
    if os.path.isfile(cand) and os.access(cand, os.X_OK):
        return cand
    on_path = shutil.which("multiqc")
    if not on_path:
        raise SystemExit("multiqc_zh_fonts: 找不到 multiqc（当前解释器的 bin 与 PATH 均无）")
    return on_path


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("argv", nargs=argparse.REMAINDER,
                    help="multic 的原始参数（-f -c CONFIG -o OUTDIR INPUTDIR …，前导 -- 可选）")
    a = ap.parse_args()
    argv = [x for x in a.argv if x != "--"]
    if not argv:
        ap.error("需要 multiqc 参数，例如：multiqc_zh_fonts.py -- -f -c X -o Y INDIR")

    fonts = find_cjk_fonts()
    if not fonts:
        raise SystemExit("multiqc_zh_fonts: 未找到 CJK 字体（候选清单 + /usr/share/fonts 兜底均落空）")
    print(f"[multiqc_zh_fonts] 注入 {len(fonts)} 个字体文件")

    cand_lines = ", ".join(repr(p) for p in fonts)
    tmpl = SITECUSTOMIZE_TMPL.replace("{_cand_lines}", cand_lines)
    tmpdir = tempfile.mkdtemp(prefix="mqc_zh_fonts_")
    with open(os.path.join(tmpdir, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(tmpl)

    try:
        multiqc_bin = locate_multiqc()
        env = dict(os.environ)
        env["PYTHONPATH"] = tmpdir + os.pathsep + env.get("PYTHONPATH", "")
        print(f"[multiqc_zh_fonts] exec: {multiqc_bin} {' '.join(argv)}")
        proc = subprocess.run([multiqc_bin, *argv], env=env)
        return proc.returncode
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
