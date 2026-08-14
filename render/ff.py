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


def codecs(src: Path) -> tuple[str, str]:
    """(영상 코덱, 소리 코덱). 못 읽으면 빈 문자열 — 그때는 다시 인코딩한다."""
    fp = bin_path("ffprobe")
    if not fp:
        return "", ""
    try:
        r = subprocess.run(
            [fp, "-v", "error", "-show_entries", "stream=codec_type,codec_name",
             "-of", "csv=p=0", str(src)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except Exception:  # noqa: BLE001
        return "", ""
    v = a = ""
    for line in (r.stdout or "").splitlines():
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        # 순서가 뒤바뀌어 나오는 빌드가 있어 양쪽을 다 본다
        name, kind = (parts[0], parts[1]) if parts[1] in ("video", "audio") else (parts[1], parts[0])
        if kind == "video" and not v:
            v = name
        elif kind == "audio" and not a:
            a = name
    return v, a


def normalize_mp4(src: Path, dst: Path) -> tuple[bool, str]:
    """화면 녹화본 → **어디서나 열리는 mp4.**

    ★ 브라우저의 `MediaRecorder` 가 내는 mp4 는 **조각 mp4(fragmented MP4)** 다.
      실시간으로 쓰다 언제 끊길지 모르니 색인(moov)을 앞에 못 두고 조각마다
      나눠 넣는 구조인데, 폰 갤러리나 일부 재생기는 그걸 못 읽어 검은 화면이
      뜨거나 튄다(2026-08-14: "폰에서 실행이 안 되고 KMPlayer 도 검은 화면").
      컨테이너를 바꿀 문제가 아니라 **다시 묶어 주면** 되는 문제다.

    ★ 먼저 **스트림 복사**로 시도한다. h264/aac 이 이미 들어 있으면 화질 손실
      없이 몇 초면 끝난다 — 다시 인코딩하면 18분짜리에 몇 분이 더 든다.
      webm(vp9/opus)으로 찍힌 경우에만 진짜 변환으로 내려간다.

    ★ `+faststart` — 색인을 파일 맨 앞으로 옮긴다. 없으면 재생기가 파일을 끝까지
      받고서야 재생을 시작한다(웹에 올렸을 때 특히 티가 난다).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    v, a = codecs(src)

    # ★ 영상이 이미 h264 면 **그대로 복사한다.** 30분짜리를 다시 인코딩하면 몇 분이
    #   더 드는데, 화질만 깎일 뿐 얻는 게 없다.
    vargs = ["-c:v", "copy"] if v == "h264" else [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]
    # ★ 소리는 aac 가 아니면 **반드시 바꾼다.** 여기가 진짜 원인이었다 —
    #   크롬은 mp4 안에 opus 를 넣어 준다(규격상 되긴 한다). 그런데 폰 갤러리도
    #   KMPlayer 도 그걸 못 읽어서, 영상은 멀쩡한데 검은 화면이 뜬다.
    aargs = ["-c:a", "copy"] if a == "aac" else [
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

    ok, err = run(["-i", str(src), *vargs, *aargs,
                   "-movflags", "+faststart", str(dst)], timeout=3600)
    if ok and dst.is_file() and dst.stat().st_size > 0:
        return True, f"v:{vargs[1]} a:{aargs[1]}"
    # 무슨 이유로든 실패하면 통째로 다시 인코딩해 본다 — 마지막 수단
    ok, err = run(["-i", str(src),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                   "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                   "-movflags", "+faststart", str(dst)], timeout=3600)
    return ok, ("encode" if ok else err)


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


def image_seq_audio_clip(images: List[Path], durations: List[float], dst: Path, *,
                         audio: Optional[Path] = None, fps: int = 30) -> tuple[bool, str]:
    """이미지 **여러 장**(각자 머무는 시간) + 오디오 하나 → 조각 하나.

    한 장 안에서 줄이 하나씩 뜨는 것을 담는 자리다. 컷마다 다음 컷 시각까지
    머물면 실제 재생과 같은 순서가 된다.

    ★ **오디오는 자르지 않는다.** 한 장의 내레이션은 한 줄기이고 그 위에서 화면만
      바뀐다. 컷마다 오디오를 잘라 붙이면 이음매마다 AAC 앞머리(priming)가 들어가
      딸깍거린다 — 지금 고치려는 바로 그 증상이다.

    ★ concat demuxer 는 **마지막 파일을 한 번 더** 적어야 그 앞 항목의 `duration`
      이 적용된다(마지막 항목의 길이는 다음 파일이 나타날 때 확정되기 때문이다).
    """
    if not images:
        return False, "이미지 없음"
    dst.parent.mkdir(parents=True, exist_ok=True)
    lst = dst.with_suffix(".txt")
    lines: List[str] = []
    for img, d in zip(images, durations):
        lines.append(f"file '{img.resolve().as_posix()}'")
        lines.append(f"duration {max(float(d), 0.05):.3f}")
    lines.append(f"file '{images[-1].resolve().as_posix()}'")
    lst.write_text("\n".join(lines), encoding="utf-8")

    args = ["-f", "concat", "-safe", "0", "-i", str(lst)]
    if audio and audio.is_file():
        args += ["-i", str(audio)]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    args += ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
             "-shortest", "-movflags", "+faststart", str(dst)]
    ok, err = run(args)
    try:
        lst.unlink()
    except OSError:
        pass
    return ok, err


def concat(segments: List[Path], dst: Path) -> tuple[bool, str]:
    """조각들을 번호 순서로 이어 붙인다 — 전부 같은 코덱이라 재인코딩 없이 스트림 복사.

    ★ `+faststart` — 조각마다 붙여 놨어도 **이어 붙이면 다시 풀린다.** 색인(moov)이
      파일 끝으로 가면 재생기가 파일을 끝까지 받고서야 재생을 시작한다. 로컬에서는
      티가 안 나지만 폰으로 옮기거나 웹에 올리면 "한참 멈춰 있다" 로 나타난다
      (2026-08-14 확인: 28분짜리 완성본이 `ftyp` 다음 바로 `mdat` 이었다).
      스트림 복사라 몇 초면 끝나므로 아낄 이유가 없다.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    listfile = dst.with_suffix(".txt")
    listfile.write_text(
        "\n".join(f"file '{s.resolve().as_posix()}'" for s in segments), encoding="utf-8")
    ok, err = run(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy",
                   "-movflags", "+faststart", str(dst)], timeout=1800)
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
