#!/usr/bin/env python3
"""
校验构建出的 wheel 不含任何运行时依赖。

本项目对外承诺「零第三方依赖」，此脚本在 CI 中把关：
若 wheel 的 METADATA 中出现 Requires-Dist 字段（且非条件依赖），
说明引入了运行时依赖，应立即失败。

用法：
    python scripts/check_no_deps.py [dist 目录]
"""

import glob
import os
import sys
import zipfile


def main():
    dist_dir = sys.argv[1] if len(sys.argv) > 1 else "dist"

    wheels = sorted(glob.glob(os.path.join(dist_dir, "*.whl")))
    if not wheels:
        print(f"错误：在 {dist_dir}/ 下未找到 .whl 文件")
        return 1

    wheel = wheels[0]
    print(f"检查文件: {wheel}")

    with zipfile.ZipFile(wheel) as zf:
        metadata_names = [n for n in zf.namelist()
                          if n.endswith(".dist-info/METADATA")]
        if not metadata_names:
            print("错误：wheel 中未找到 METADATA")
            return 1
        content = zf.read(metadata_names[0]).decode("utf-8")

    # 区分「运行时依赖」与「可选依赖」：
    #   Requires-Dist: foo>=1.0                    -> 运行时依赖，必须为 0
    #   Requires-Dist: foo>=1.0; extra == "dev"    -> 可选依赖，仅 pip install pkg[dev] 时安装
    runtime_deps = []
    optional_deps = []
    for line in content.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line[len("Requires-Dist:"):].strip()
        # 带 extra 标记的视为可选依赖
        if "extra ==" in spec:
            optional_deps.append(spec)
        else:
            runtime_deps.append(spec)

    if runtime_deps:
        print("失败：发现运行时依赖，与「零依赖」承诺不符")
        for item in runtime_deps:
            print(f"  {item}")
        return 1

    print("通过：wheel 不含任何运行时依赖")
    if optional_deps:
        print(f"（另有 {len(optional_deps)} 个可选依赖，不影响默认安装）")
        for item in optional_deps:
            print(f"  {item}")

    # 顺带报告包内文件，便于人工核对
    with zipfile.ZipFile(wheel) as zf:
        print("\n包内文件：")
        for name in zf.namelist():
            print(f"  {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
