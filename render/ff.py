# -*- coding: utf-8 -*-
"""ffmpeg 래퍼 — 최소한만. `mp4maker/ffmpeg_runner.py` 의 규약을 따른다.

**한글 파일명 3원칙:**
  1. `subprocess.run([bin, *args], shell=False)` — 명령 문자열을 만들지 않는다
  2. 파생 파일은 전부 ascii. 한글은 JSON 값(`source_label`)에만 산다
  3. 매니페스트↔`os.listdir` 비교 전에 NFC 정규화

ffmpeg 이 없어도 파이프라인은 돈다 — 트랜스코딩을 건너뛰고 원본을 그대로 복사한다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

COMMON = ["-hide_banner", "-loglevel", "error", "-nostdin", "-y"]


def bin_path(name: str) -> Optional[str]:
    return shutil.which(name)


def run(args: List[str], *, timeout: int = 600) -> tuple[bool, str]:
    ff = bin_path("ffmpeg")
    if not ff:
        return False, "ffmpeg 없음"
    try:
        r = subprocess.run([ff, *COMMON, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return (r.returncode == 0), (r.stderr or "").strip()[-400:]


def to_aac(src: Path, dst: Path, *, kbps: int = 96) -> tuple[bool, str]:
    """폴더 빌드용 — 외부 파일로 두므로 품질을 조금 더 준다."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    return run(["-i", str(src), "-vn", "-c:a", "aac", "-b:a", f"{kbps}k",
                "-movflags", "+faststart", str(dst)])


def to_opus(src: Path, dst: Path, *, kbps: int = 32) -> tuple[bool, str]:
    """단일 파일용 — base64 로 HTML 에 박히므로 크기가 곧 파일 크기다.
    PCM16 wav 는 초당 48KB 라 20초 여섯 개면 벌써 5.8MB 다. opus 32k 면 1/16."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    return run(["-i", str(src), "-vn", "-c:a", "libopus", "-b:a", f"{kbps}k",
                "-application", "voip", str(dst)])


def image_audio_clip(image: Path, dst: Path, *, audio: Optional[Path] = None,
                     duration: float = 3.0, fps: int = 30) -> tuple[bool, str]:
    """정지 이미지 + 오디오(없으면 무음) → 그 길이만큼의 mp4 한 조각.

    ★ 오디오가 없는 장도 **무음 오디오 트랙을 넣는다.** 이어 붙일 때(concat)
      모든 조각의 스트림 구성(영상+오디오)이 같아야 재인코딩 없이 붙는다 —
      한 조각만 오디오가 없으면 이어 붙이다 어긋나거나 실패한다.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    vcommon = ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
               "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
               "-movflags", "+faststart"]
    if audio and audio.is_file():
        return run(["-loop", "1", "-i", str(image), "-i", str(audio),
                   *vcommon, "-shortest", str(dst)])
    dur = max(float(duration), 1.0)
    return run(["-loop", "1", "-i", str(image),
               "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               *vcommon, "-t", f"{dur:.2f}", str(dst)])


def concat(segments: List[Path], dst: Path) -> tuple[bool, str]:
    """조각들을 번호 순서로 이어 붙인다 — 전부 같은 코덱이라 재인코딩 없이 스트림 복사."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    listfile = dst.with_suffix(".txt")
    listfile.write_text(
        "\n".join(f"file '{s.resolve().as_posix()}'" for s in segments), encoding="utf-8")
    ok, err = run(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(dst)])
    try:
        listfile.unlink()
    except OSError:
        pass
    return ok, err


def remux_mp4(src: Path, dst: Path) -> tuple[bool, str]:
    """mkv → mp4. **재인코딩하지 않는다** — h264 스트림을 그대로 옮긴다.
    `+faststart` 가 없으면 브라우저가 전체를 받고서야 재생을 시작한다."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    ok, err = run(["-i", str(src), "-map", "0:v:0", "-c", "copy", "-an",
                   "-movflags", "+faststart", str(dst)])
    if ok:
        return ok, err
    # 컨테이너가 못 받아 주면 그때만 다시 인코딩한다
    return run(["-i", str(src), "-map", "0:v:0", "-c:v", "libx264", "-crf", "23",
                "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an",
                "-movflags", "+faststart", str(dst)])
