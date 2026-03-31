# Project: sds-python-organize_photos

## What this is
Single-file Python script (`organize_photos.py`, ~494 lines) to organize media files (photos/videos) by creation date into a folder structure `year/year-month-day/filename`. Primarily built for Google Photos Takeout exports but works with any media files.

## How to run
```bash
# Place the script in the folder with media files, then:
python organize_photos.py
```
- Source: current directory (`.`)
- Target: `___organized_media/` subfolder
- No CLI arguments supported — source/target are hardcoded in `organize_media()` at line 391

## Script structure and flow

### Phase 0: Auto-install dependencies (lines 1-47)
- `install_package()` — tries `__import__()`, if ImportError runs `pip install` via subprocess
- `check_and_install_dependencies()` — checks Pillow, hachoir, pywin32; exits if any fail
- Runs at import time (line 47), before any other imports

### Phase 1: Process files WITH JSON metadata (lines 412-447)
- Walks entire `source_dir` recursively via `os.walk()`
- For each `.json` file: `process_json_file()` reads JSON, finds matching media file, determines date
- Tracks processed media files in `processed_media_files` set to avoid double-processing
- Moves both media file and its JSON to target folder
- Skips if file is already at the correct target path

### Phase 2: Process remaining media files WITHOUT JSON (lines 449-481)
- Second `os.walk()` pass over the same source dir
- Skips files already processed in Phase 1 (checked via `processed_media_files` set)
- Only processes files with extensions in `ALL_MEDIA_EXTENSIONS`
- Uses `get_file_date()` which has no JSON fallback

### Key functions

#### Date extraction (priority chain)

**`get_valid_timestamp(metadata, media_path)`** — for files WITH JSON (line 287):
1. EXIF date (`get_exif_date`) — photos only
2. Video metadata (`get_video_creation_time`) — videos only
3. JSON `photoTakenTime.timestamp` or `creationTime.timestamp`
4. Filename date pattern (`get_date_from_filename`)
5. `os.path.getctime()` — file creation time
6. `os.path.getmtime()` — file modification time

**`get_file_date(file_path)`** — for files WITHOUT JSON (line 224):
1. Video metadata (`get_video_creation_time`) — videos only
2. Filename date pattern (`get_date_from_filename`)
3. Windows API creation time via `win32file.CreateFile` + `GetFileTime`
4. `os.path.getmtime()` — modification time
5. `os.path.getctime()` — creation time
6. `time.time()` — current time as last resort

**Note:** these two functions have different priority orders and different fallbacks. `get_file_date` uses Windows API (pywin32) while `get_valid_timestamp` does not. `get_file_date` does not try EXIF for photos.

#### `get_date_from_filename(file_path)` (line 77)
Extracts date from basename only (not path). Two regex patterns:
1. Date+time: `(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[_\-]?(\d{2})(\d{2})(\d{2})`
2. Date-only fallback: `(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])`

Recognized patterns:
- `20210913_185344` — bare date_time
- `IMG_20211219_203324_685` — prefix + date_time + suffix
- `VID_20220101_120000` — video prefix
- `Screenshot_20210913-185344` — dash separator
- `PXL_20210913_185344123` — Pixel phone format
- `20210913` — date only, time set to 00:00:00

Only matches years 20xx. Validates month (01-12) and day (01-31) in regex. Uses `datetime()` constructor for final validation (catches Feb 30 etc). All dates before 2000-01-01 are rejected via `MIN_VALID_TIMESTAMP`.

#### `get_exif_date(file_path)` (line 117)
- Opens image with Pillow, reads `_getexif()`
- Checks tags in priority order: DateTimeOriginal > DateTime > DateTimeDigitized
- Parses format `'%Y:%m:%d %H:%M:%S'`

#### `get_video_creation_time(file_path)` (line 144)
- Uses hachoir `createParser()` + `extractMetadata()`
- Checks fields: creation_date, last_modification, record_date, date_time_original
- Also checks stream-level creation_date
- **Critical:** closes `parser.stream._input.close()` in `finally` block to prevent WinError 32 file locks

#### `get_json_date(metadata)` (line 189)
- Tries `metadata['photoTakenTime']['timestamp']` first
- Falls back to `metadata['creationTime']['timestamp']`
- Both must be > MIN_VALID_TIMESTAMP

#### `find_media_file(json_path, title)` (line 324)
Three strategies to find media file matching a JSON:
1. Same path as JSON but with media extension (e.g. `photo.json` -> `photo.jpg`)
2. Match by `title` field from JSON metadata in same directory
3. Glob pattern `*{title}*{ext}` as fuzzy fallback

#### `is_already_in_correct_place(file_path, timestamp, target_dir)` (line 209)
Compares file's actual directory vs expected `target_dir/year/year-month-day/`. Case-insensitive. Used to skip files that are already sorted correctly — enables re-running the script without moving files that don't need it.

#### `get_target_path(timestamp, media_path)` (line 350)
Generates relative path: `year/year-month-day/filename.ext`

### Constants
- `PHOTO_EXTENSIONS` — 15 extensions (jpg, jpeg, png, gif, bmp, tiff, webp, raw, cr2, nef, arw, dng, orf, rw2, pef). Note: `.dng` is listed twice.
- `VIDEO_EXTENSIONS` — 11 extensions (mp4, mov, avi, wmv, flv, webm, mkv, m4v, 3gp, mpg, mpeg)
- `MIN_VALID_TIMESTAMP = 946684800` — 2000-01-01, rejects older dates

### Output stats
Prints after completion: total processed, with JSON, without JSON, photos, videos, skipped (already correct), errors.

## Known issues / quirks
- **Windows-only** — `win32file`/`win32con` imports will fail on Linux/Mac
- **`import re` is on line 75** instead of at the top with other imports
- **`.dng` is duplicated** in PHOTO_EXTENSIONS set (no runtime error, just redundant)
- **`get_file_date` doesn't check EXIF** for photos — only `get_valid_timestamp` does. So photos without JSON go through: video metadata (skipped for photos) -> filename -> Windows API -> mtime -> ctime. EXIF is never checked for photos without JSON.
- **Bare `except:`** on lines 197, 318 — catches all exceptions silently
- **Two `os.walk()` passes** over the entire directory tree — one for JSON files, one for remaining media
- **`shutil.move()` behavior**: moves (not copies) files. If target already exists with same name, will raise an error
- **No duplicate filename handling** — if two files have the same name but from different source folders, the second move will fail
- **No CLI arguments** — source_dir and target_dir are hardcoded defaults

## Dependencies
- **Pillow** — EXIF reading from photos
- **hachoir** — video metadata extraction
- **pywin32** — Windows API for accurate file creation timestamps

## Platform
- Windows only (uses `win32file`, `win32con`)
