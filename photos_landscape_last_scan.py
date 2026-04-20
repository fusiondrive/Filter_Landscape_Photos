#!/opt/homebrew/bin/python3

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SOURCE_ALBUM_NAME = "𝕏"
TARGET_ALBUM_NAME = "橫向照片篩選"

METADATA_BATCH_SIZE = 5
WRITE_BATCH_SIZE = 5
MAX_ITEMS_PER_RUN = 500

FETCH_TIMEOUT_SECONDS = 45
ADD_TIMEOUT_SECONDS = 30
PAUSE_BETWEEN_CHUNKS_SECONDS = 0.25
PAUSE_BETWEEN_ADDS_SECONDS = 0.08
PROGRESS_NOTIFY_EVERY = 50
COOLDOWN_EVERY_ITEMS = 100
COOLDOWN_SECONDS = 2.0

LAST_SCAN_FILE = Path.home() / ".photos_landscape_last_scan"
RESUME_FILE = Path.home() / ".photos_landscape_last_scan_resume"


class PhotosBridgeError(RuntimeError):
    """Raised when a Photos AppleScript command fails."""


class PhotosBridgeTimeout(PhotosBridgeError):
    """Raised when a Photos AppleScript command times out."""


@dataclass
class ChunkPhoto:
    index: int
    photo_id: str
    width: int
    height: int


@dataclass
class ResumeState:
    snapshot_count: int
    next_resume_index: int


class PhotosAddVerificationError(PhotosBridgeError):
    """Raised when Photos accepted an add request but items are still missing from the target album."""


def run_osascript(lines: list[str], args: list[str], timeout_seconds: int) -> str:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    cmd.append("--")
    cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise PhotosBridgeTimeout("AppleScript command timed out") from exc

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    combined = "\n".join(part for part in (stdout, stderr) if part)

    if result.returncode != 0:
        if "-1712" in combined or "AppleEvent timed out" in combined:
            raise PhotosBridgeTimeout(combined or "AppleEvent timed out")
        raise PhotosBridgeError(combined or "AppleScript command failed")

    return stdout


def ui_script(statement: str) -> None:
    subprocess.run(["osascript", "-e", statement], check=False, capture_output=True, text=True)


def escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str) -> None:
    safe_title = escape_applescript_string(title)
    safe_message = escape_applescript_string(message)
    ui_script(f'display notification "{safe_message}" with title "{safe_title}"')


def dialog(message: str, title: str = "Photos 增量扫描") -> None:
    safe_title = escape_applescript_string(title)
    safe_message = escape_applescript_string(message)
    ui_script(f'display dialog "{safe_message}" with title "{safe_title}" buttons {{"确定"}}')


def beep() -> None:
    ui_script("beep")


def read_last_scan_epoch() -> int:
    try:
        raw = LAST_SCAN_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return 0
        return int(float(raw))
    except (FileNotFoundError, ValueError):
        return 0


def write_last_scan_epoch(epoch: int) -> None:
    LAST_SCAN_FILE.write_text(f"{epoch}\n", encoding="utf-8")


def format_epoch_for_dialog(epoch: int) -> str:
    if epoch <= 0:
        return "未设置（epoch 0）"

    local_time = datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"{local_time}（epoch {epoch}）"


def read_resume_state() -> ResumeState | None:
    try:
        raw = RESUME_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None

    if not raw or "|" not in raw:
        return None

    left, right = raw.split("|", 1)
    try:
        return ResumeState(snapshot_count=int(left), next_resume_index=int(right))
    except ValueError:
        return None


def write_resume_state(snapshot_count: int, next_resume_index: int) -> None:
    RESUME_FILE.write_text(f"{snapshot_count}|{next_resume_index}\n", encoding="utf-8")


def clear_resume_state() -> None:
    try:
        RESUME_FILE.unlink()
    except FileNotFoundError:
        pass


def get_source_album_count() -> int:
    lines = [
        "on run argv",
        "set sourceAlbumName to item 1 of argv",
        'tell application "Photos"',
        'set sourceAlbumsList to every album whose name is sourceAlbumName',
        'if sourceAlbumsList is {} then error "找不到来源相册: " & sourceAlbumName number 1001',
        "set currentAlbum to item 1 of sourceAlbumsList",
        "return (count of media items of currentAlbum) as text",
        "end tell",
        "end run",
    ]
    return int(run_osascript(lines, [SOURCE_ALBUM_NAME], FETCH_TIMEOUT_SECONDS))


def fetch_chunk(lower_index: int, upper_index: int, last_scan_epoch: int) -> tuple[list[ChunkPhoto], bool]:
    lines = [
        "on run argv",
        "set sourceAlbumName to item 1 of argv",
        "set lowerIndex to item 2 of argv as integer",
        "set upperIndex to item 3 of argv as integer",
        "set lastScanEpoch to item 4 of argv as real",
        "set linefeed to ASCII character 10",
        "set tabChar to ASCII character 9",
        "set baseDate to (current date)",
        "set year of baseDate to 1970",
        "set month of baseDate to January",
        "set day of baseDate to 1",
        "set time of baseDate to 0",
        "set lastCheckDate to baseDate + lastScanEpoch",
        'tell application "Photos"',
        'set sourceAlbumsList to every album whose name is sourceAlbumName',
        'if sourceAlbumsList is {} then error "找不到来源相册: " & sourceAlbumName number 1001',
        "set currentAlbum to item 1 of sourceAlbumsList",
        "set outputLines to {}",
        "set reachedOld to false",
        "repeat with i from upperIndex to lowerIndex by -1",
        "set targetPhoto to media item i of currentAlbum",
        "if (date of targetPhoto) > lastCheckDate then",
        'set end of outputLines to ((i as text) & tabChar & (id of targetPhoto) & tabChar & (width of targetPhoto as text) & tabChar & (height of targetPhoto as text))',
        "else",
        "set reachedOld to true",
        "exit repeat",
        "end if",
        "set targetPhoto to missing value",
        "end repeat",
        "set oldTIDs to AppleScript's text item delimiters",
        "set AppleScript's text item delimiters to linefeed",
        'if reachedOld then set statusLine to "STATUS" & tabChar & "REACHED_OLD"',
        'if not reachedOld then set statusLine to "STATUS" & tabChar & "CONTINUE"',
        "if outputLines is {} then",
        "set AppleScript's text item delimiters to oldTIDs",
        "return statusLine",
        "end if",
        "set joinedLines to outputLines as text",
        "set AppleScript's text item delimiters to oldTIDs",
        "return statusLine & linefeed & joinedLines",
        "end tell",
        "end run",
    ]

    output = run_osascript(
        lines,
        [SOURCE_ALBUM_NAME, str(lower_index), str(upper_index), str(last_scan_epoch)],
        FETCH_TIMEOUT_SECONDS,
    )

    if not output:
        return [], False

    lines_out = output.splitlines()
    status = lines_out[0].split("\t", 1)[1] if "\t" in lines_out[0] else "CONTINUE"

    photos: list[ChunkPhoto] = []
    for line in lines_out[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            raise PhotosBridgeError(f"无法解析 Photos 返回数据: {line}")
        photos.append(
            ChunkPhoto(
                index=int(parts[0]),
                photo_id=parts[1],
                width=int(parts[2]),
                height=int(parts[3]),
            )
        )

    return photos, status == "REACHED_OLD"


def add_photo_ids(photo_ids: list[str]) -> int:
    if not photo_ids:
        return 0

    lines = [
        "on run argv",
        "set targetAlbumName to item 1 of argv",
        "set maxRetry to 3",
        'tell application "Photos"',
        'set targetAlbumList to every album whose name is targetAlbumName',
        'if targetAlbumList is {} then',
        'make new album named targetAlbumName',
        'set targetAlbumList to every album whose name is targetAlbumName',
        "end if",
        "set targetAlbum to item 1 of targetAlbumList",
        "set mediaList to {}",
        "set requestedNewCount to 0",
        "repeat with argIndex from 2 to (count of argv)",
        "set photoID to item argIndex of argv",
        "set mediaItemRef to media item id photoID",
        "copy mediaItemRef to end of mediaList",
        "if (count of (media items of targetAlbum whose id is photoID)) is 0 then",
        "set requestedNewCount to requestedNewCount + 1",
        "end if",
        "end repeat",
        "if mediaList is {} then return \"0\"",
        "set tryCount to 0",
        "set addedAll to false",
        "repeat while (tryCount < maxRetry) and (addedAll is false)",
        "add mediaList to targetAlbum",
        "set addedAll to true",
        "repeat with mediaItemRef in mediaList",
        "set mediaID to id of mediaItemRef",
        "if (count of (media items of targetAlbum whose id is mediaID)) is 0 then",
        "set addedAll to false",
        "end if",
        "end repeat",
        "set tryCount to tryCount + 1",
        "end repeat",
        "if addedAll is false then error \"Photos 未能把请求的照片写入目标相册\" number 1002",
        "return requestedNewCount as text",
        "end tell",
        "end run",
    ]

    try:
        return int(run_osascript(lines, [TARGET_ALBUM_NAME, *photo_ids], ADD_TIMEOUT_SECONDS))
    except PhotosBridgeError as exc:
        message = str(exc)
        if "1002" in message or "未能把请求的照片写入目标相册" in message:
            raise PhotosAddVerificationError(message) from exc
        raise


def build_scan_ranges(current_count: int, resume_state: ResumeState | None) -> tuple[list[tuple[int, int]], bool]:
    if not resume_state or resume_state.next_resume_index <= 0:
        return ([(current_count, 1)] if current_count > 0 else []), False

    ranges: list[tuple[int, int]] = []
    if current_count > resume_state.snapshot_count:
        ranges.append((current_count, resume_state.snapshot_count + 1))

    resume_upper = min(resume_state.next_resume_index, current_count)
    if resume_upper >= 1:
        ranges.append((resume_upper, 1))

    return ranges, True


def save_checkpoint(snapshot_count: int, next_resume_index: int) -> None:
    write_resume_state(snapshot_count, next_resume_index)


def main() -> int:
    current_run_epoch = int(time.time())
    last_scan_epoch = read_last_scan_epoch()

    try:
        source_count = get_source_album_count()
    except PhotosBridgeError as exc:
        dialog(f"无法读取来源相册数量。\n\n{exc}")
        return 0

    if source_count <= 0:
        notify("无需更新", "来源相册为空，无需扫描。")
        return 0

    resume_state = read_resume_state()
    scan_ranges, resume_used = build_scan_ranges(source_count, resume_state)

    if resume_used:
        notify(
            "继续增量扫描",
            f"來源相簿共有 {source_count} 張；本次會從上次中斷點繼續，並先補掃中斷後新增的尾部照片。單次最多自動處理 {MAX_ITEMS_PER_RUN} 張。",
        )
    else:
        notify(
            "开始增量扫描",
            f"來源相簿共有 {source_count} 張；本次只检查上次扫描之后的新照片。單次最多自動處理 {MAX_ITEMS_PER_RUN} 張。",
        )

    total_added = 0
    process_count = 0
    pending_ids: list[str] = []
    next_resume_index = source_count
    hit_per_run_limit = False
    reached_old_boundary = False
    timed_out = False
    timed_out_message = ""

    try:
        for range_upper, range_lower in scan_ranges:
            chunk_upper = range_upper

            while chunk_upper >= range_lower:
                if process_count >= MAX_ITEMS_PER_RUN:
                    hit_per_run_limit = True
                    break

                chunk_lower = max(range_lower, chunk_upper - METADATA_BATCH_SIZE + 1)

                try:
                    photos, reached_old_in_chunk = fetch_chunk(chunk_lower, chunk_upper, last_scan_epoch)
                except PhotosBridgeTimeout as exc:
                    timed_out = True
                    timed_out_message = (
                        f"讀取第 {chunk_lower}-{chunk_upper} 張時超時，已保存續跑進度。"
                    )
                    save_checkpoint(source_count, max(1, next_resume_index))
                    notify("Photos 超时", timed_out_message)
                    break
                except PhotosBridgeError as exc:
                    save_checkpoint(source_count, max(1, next_resume_index))
                    dialog(f"读取照片元数据失败，已保存续跑进度。\n\n{exc}")
                    return 0

                for photo in photos:
                    process_count += 1
                    next_resume_index = photo.index - 1

                    if photo.width > photo.height:
                        pending_ids.append(photo.photo_id)

                    if len(pending_ids) >= WRITE_BATCH_SIZE:
                        try:
                            total_added += add_photo_ids(pending_ids)
                        except PhotosBridgeTimeout:
                            timed_out = True
                            timed_out_message = "寫入目標相簿時超時，已保存續跑進度。"
                            save_checkpoint(source_count, max(1, next_resume_index))
                            notify("Photos 超时", timed_out_message)
                            break
                        except PhotosBridgeError as exc:
                            save_checkpoint(source_count, max(1, next_resume_index))
                            dialog(f"写入目标相册失败，已保存续跑进度。\n\n{exc}")
                            return 0

                        pending_ids.clear()
                        time.sleep(PAUSE_BETWEEN_ADDS_SECONDS)

                    if process_count % PROGRESS_NOTIFY_EVERY == 0:
                        notify(
                            "运行中",
                            f"本次已安全检查 {process_count} 张新照片；若尚未扫完，会自动继续到本轮上限。",
                        )

                    if process_count % COOLDOWN_EVERY_ITEMS == 0:
                        time.sleep(COOLDOWN_SECONDS)

                    if process_count >= MAX_ITEMS_PER_RUN:
                        hit_per_run_limit = True
                        break

                if timed_out or hit_per_run_limit:
                    break

                save_checkpoint(source_count, max(1, next_resume_index))

                if reached_old_in_chunk:
                    reached_old_boundary = True
                    break

                chunk_upper = chunk_lower - 1
                time.sleep(PAUSE_BETWEEN_CHUNKS_SECONDS)

            if timed_out or hit_per_run_limit or reached_old_boundary:
                break

        if pending_ids and not timed_out:
            try:
                total_added += add_photo_ids(pending_ids)
            except PhotosBridgeTimeout:
                timed_out = True
                timed_out_message = "寫入目標相簿時超時，已保存續跑進度。"
                save_checkpoint(source_count, max(1, next_resume_index))
                notify("Photos 超时", timed_out_message)
            except PhotosBridgeError as exc:
                save_checkpoint(source_count, max(1, next_resume_index))
                dialog(f"写入目标相册失败，已保存续跑进度。\n\n{exc}")
                return 0
    finally:
        pending_ids.clear()

    beep()

    if timed_out:
        dialog(
            "本轮在与 Photos 通讯时超时，已保存续跑进度。"
            f"\n\n來源相簿總數：{source_count} 張"
            f"\n本輪已檢查：{process_count} 張"
            f"\n本輪已新增橫圖：{total_added} 張"
            f"\n完成掃描時間戳：本輪未更新"
            f"\n當前仍為：{format_epoch_for_dialog(last_scan_epoch)}"
            f"\n說明：{timed_out_message or '下次執行會從最新檢查點繼續。'}"
        )
        return 0

    if hit_per_run_limit:
        save_checkpoint(source_count, max(1, next_resume_index))
        dialog(
            "本轮已安全处理到上限，已保存续跑进度。"
            f"\n\n來源相簿總數：{source_count} 張"
            f"\n本輪檢查新照片：{process_count} 張"
            f"\n本輪新增橫圖：{total_added} 張"
            f"\n本輪單次上限：{MAX_ITEMS_PER_RUN} 張"
            f"\n完成掃描時間戳：本輪未更新"
            f"\n當前仍為：{format_epoch_for_dialog(last_scan_epoch)}"
            "\n再次執行此腳本會從中斷位置繼續。",
        )
        return 0

    clear_resume_state()
    write_last_scan_epoch(current_run_epoch)

    if total_added > 0:
        dialog(
            "增量整理完成！"
            f"\n\n來源相簿總數：{source_count} 張"
            f"\n共检查新照片：{process_count} 张"
            f"\n新增横图：{total_added} 张"
            f"\n完成掃描時間戳已更新為：{format_epoch_for_dialog(current_run_epoch)}"
        )
    else:
        dialog(
            "增量整理完成！"
            f"\n\n來源相簿總數：{source_count} 張"
            f"\n共检查新照片：{process_count} 张"
            "\n新增横图：0 张"
            f"\n完成掃描時間戳已更新為：{format_epoch_for_dialog(current_run_epoch)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
