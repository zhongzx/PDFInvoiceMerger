from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class BuildContext:
    project_root: Path
    assets_dir: Path
    dist_dir: Path
    build_dir: Path
    artifacts_dir: Path
    app_name: str
    arch: str


def run_command(args: Sequence[str], cwd: Path) -> None:
    subprocess.check_call(list(args), cwd=str(cwd))


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def create_windows_ico(png_path: Path, ico_path: Path) -> Path:
    from PIL import Image

    img = Image.open(png_path)
    img.save(str(ico_path), format="ICO", sizes=[(256, 256)])
    return ico_path


def create_macos_icns(
    ctx: BuildContext, png_path: Path, icns_path: Path
) -> Path:
    iconset_dir = ctx.build_dir / "icon.iconset"
    ensure_clean_dir(iconset_dir)

    icon_sizes = [16, 32, 128, 256, 512]
    for size in icon_sizes:
        out_1x = iconset_dir / f"icon_{size}x{size}.png"
        out_2x = iconset_dir / f"icon_{size}x{size}@2x.png"

        run_command(
            [
                "sips",
                "-z",
                str(size),
                str(size),
                str(png_path),
                "--out",
                str(out_1x),
            ],
            cwd=ctx.project_root,
        )
        run_command(
            [
                "sips",
                "-z",
                str(size * 2),
                str(size * 2),
                str(png_path),
                "--out",
                str(out_2x),
            ],
            cwd=ctx.project_root,
        )

    if icns_path.exists():
        icns_path.unlink()
    run_command(
        ["iconutil", "-c", "icns", str(iconset_dir)], cwd=ctx.project_root
    )

    generated = ctx.build_dir / "icon.icns"
    if not generated.exists():
        raise FileNotFoundError(str(generated))

    shutil.move(str(generated), str(icns_path))
    shutil.rmtree(iconset_dir, ignore_errors=True)
    return icns_path


def pyinstaller_base_args(ctx: BuildContext) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        ctx.app_name,
        "--windowed",
        "--add-data",
        f"{ctx.assets_dir}{os.pathsep}assets",
        "--hidden-import",
        "patoolib",
        "main.py",
    ]


def build_with_pyinstaller(ctx: BuildContext) -> None:
    args = pyinstaller_base_args(ctx)

    png_icon = ctx.assets_dir / "icon.png"
    if sys_platform() == "win32":
        ico_path = ctx.build_dir / "icon.ico"
        create_windows_ico(png_icon, ico_path)
        args = args[:-1] + ["--onefile", "--icon", str(ico_path)] + args[-1:]
    elif sys_platform() == "darwin":
        icns_path = ctx.build_dir / "icon.icns"
        create_macos_icns(ctx, png_icon, icns_path)
        args = args[:-1] + ["--icon", str(icns_path)] + args[-1:]
    else:
        args = args[:-1] + ["--onefile"] + args[-1:]

    run_command(args, cwd=ctx.project_root)


def zip_file(src: Path, dst_zip: Path) -> None:
    with zipfile.ZipFile(dst_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src, arcname=src.name)


def tar_gz_file(src: Path, dst_tgz: Path) -> None:
    with tarfile.open(dst_tgz, "w:gz") as tf:
        tf.add(src, arcname=src.name)


def package_artifacts(ctx: BuildContext) -> Path:
    ensure_clean_dir(ctx.artifacts_dir)

    if sys_platform() == "win32":
        exe_path = ctx.dist_dir / f"{ctx.app_name}.exe"
        out_zip = ctx.artifacts_dir / f"{ctx.app_name}-windows-{ctx.arch}.zip"
        zip_file(exe_path, out_zip)
        return out_zip

    if sys_platform() == "darwin":
        app_path = ctx.dist_dir / f"{ctx.app_name}.app"
        out_zip = ctx.artifacts_dir / f"{ctx.app_name}-macos-{ctx.arch}.zip"
        run_command(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(app_path),
                str(out_zip),
            ],
            cwd=ctx.project_root,
        )
        return out_zip

    bin_path = ctx.dist_dir / ctx.app_name
    out_tgz = ctx.artifacts_dir / f"{ctx.app_name}-linux-{ctx.arch}.tar.gz"
    tar_gz_file(bin_path, out_tgz)
    return out_tgz


def sys_platform() -> str:
    value = sys.platform
    if value == "win32":
        return "win32"
    if value == "darwin":
        return "darwin"
    return "linux"


def create_context() -> BuildContext:
    project_root = Path(__file__).resolve().parent
    return BuildContext(
        project_root=project_root,
        assets_dir=project_root / "assets",
        dist_dir=project_root / "dist",
        build_dir=project_root / "build_ci",
        artifacts_dir=project_root / "dist_artifacts",
        app_name="PDFInvoiceMerger",
        arch=platform.machine().lower() or "unknown",
    )


def main() -> None:
    ctx = create_context()
    ensure_clean_dir(ctx.build_dir)
    build_with_pyinstaller(ctx)
    out_path = package_artifacts(ctx)
    print(str(out_path))


if __name__ == "__main__":
    main()
