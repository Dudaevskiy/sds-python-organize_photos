import json
import os
import shutil
from datetime import datetime
import glob
from PIL import Image
from PIL.ExifTags import TAGS
import time
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata

# Розширений список підтримуваних форматів
PHOTO_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp',
    '.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2', , '.dng', '.pef'
}
VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.wmv', '.flv', '.webm', '.mkv', 
    '.m4v', '.3gp', '.mpg', '.mpeg'
}
ALL_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS

# Мінімальна допустима дата (1 січня 2000 року)
MIN_VALID_TIMESTAMP = 946684800  # timestamp for 2000-01-01

def get_exif_date(file_path):
    """
    Extract date from EXIF data for photos
    """
    try:
        with Image.open(file_path) as img:
            exif = img._getexif()
            if exif:
                # Пріоритетний список EXIF тегів для дати
                date_tags = ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']
                for tag in date_tags:
                    for tag_id in exif:
                        if TAGS.get(tag_id) == tag:
                            date_str = exif[tag_id]
                            try:
                                # Parse date string in format: '2023:12:07 15:30:00'
                                timestamp = time.mktime(datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S').timetuple())
                                if timestamp > MIN_VALID_TIMESTAMP:
                                    print(f"Found EXIF {tag} date: {datetime.fromtimestamp(timestamp)} for {file_path}")
                                    return timestamp
                            except Exception as e:
                                print(f"Error parsing EXIF date {date_str}: {str(e)}")
                                continue
    except Exception as e:
        print(f"Error reading EXIF from {file_path}: {str(e)}")
    return None

def get_video_creation_time(file_path):
    """
    Extract creation time from video metadata
    """
    try:
        parser = createParser(file_path)
        if parser:
            metadata = extractMetadata(parser)
            if metadata:
                # Список можливих полів з датою у відео файлах
                date_fields = [
                    'creation_date',           # Основна дата створення
                    'last_modification',       # Дата модифікації
                    'record_date',             # Дата запису (для камер)
                    'date_time_original'       # Оригінальна дата (деякі формати)
                ]
                
                for field in date_fields:
                    if hasattr(metadata, field):
                        date = getattr(metadata, field)
                        if date:
                            timestamp = time.mktime(date.timetuple())
                            if timestamp > MIN_VALID_TIMESTAMP:
                                print(f"Found video {field} date: {datetime.fromtimestamp(timestamp)} for {file_path}")
                                return timestamp
            
            # Додатково пробуємо отримати дату з потоків відео
            if hasattr(metadata, 'streams'):
                for stream in metadata.streams:
                    if hasattr(stream, 'creation_date'):
                        date = stream.creation_date
                        if date:
                            timestamp = time.mktime(date.timetuple())
                            if timestamp > MIN_VALID_TIMESTAMP:
                                print(f"Found video stream creation date: {datetime.fromtimestamp(timestamp)} for {file_path}")
                                return timestamp
                                
    except Exception as e:
        print(f"Error reading video metadata from {file_path}: {str(e)}")
    return None

def get_json_date(metadata):
    """
    Extract valid date from JSON metadata
    """
    try:
        photo_taken_timestamp = int(metadata['photoTakenTime']['timestamp'])
        if photo_taken_timestamp > MIN_VALID_TIMESTAMP:
            return photo_taken_timestamp, "JSON photoTakenTime"
    except:
        pass
    
    try:
        creation_timestamp = int(metadata['creationTime']['timestamp'])
        if creation_timestamp > MIN_VALID_TIMESTAMP:
            return creation_timestamp, "JSON creationTime"
    except:
        pass
    
    return None, None

def should_process_directory(path, target_dir):
    """
    Check if directory should be processed
    """
    # Нормалізуємо шляхи для порівняння
    norm_path = os.path.normpath(path).lower()
    norm_target = os.path.normpath(target_dir).lower()
    
    # Пропускаємо цільову директорію та її підпапки
    return not norm_path.startswith(norm_target)

def get_file_date(file_path):
    """
    Get file date using different methods for files without JSON
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext in PHOTO_EXTENSIONS:
        # Для фото використовуємо тільки EXIF
        exif_date = get_exif_date(file_path)
        if exif_date:
            return exif_date, "EXIF"
    elif file_ext in VIDEO_EXTENSIONS:
        # Для відео використовуємо метадані відео
        video_date = get_video_creation_time(file_path)
        if video_date:
            return video_date, "Video metadata"
    
    # Якщо метадані не знайдені, використовуємо системні дати
    try:
        creation_time = os.path.getctime(file_path)
        if creation_time > MIN_VALID_TIMESTAMP:
            return creation_time, "File creation time"
    except:
        pass
    
    modification_time = os.path.getmtime(file_path)
    return modification_time, "File modification time"

def get_valid_timestamp(metadata, media_path):
    """
    Get valid timestamp from metadata and file, prioritizing media metadata
    """
    file_ext = os.path.splitext(media_path)[1].lower()
    
    # Спочатку завжди перевіряємо медіа метадані
    if file_ext in PHOTO_EXTENSIONS:
        exif_date = get_exif_date(media_path)
        if exif_date:
            return exif_date, "EXIF"
    elif file_ext in VIDEO_EXTENSIONS:
        video_date = get_video_creation_time(media_path)
        if video_date:
            return video_date, "Video metadata"
    
    # Якщо медіа метадані не знайдені, використовуємо JSON
    json_date, json_source = get_json_date(metadata)
    if json_date:
        return json_date, json_source
    
    # В останню чергу системні дати
    try:
        creation_time = os.path.getctime(media_path)
        if creation_time > MIN_VALID_TIMESTAMP:
            return creation_time, "File creation time"
    except:
        pass
    
    modification_time = os.path.getmtime(media_path)
    return modification_time, "File modification time"

def find_media_file(json_path, title):
    """
    Try different methods to find the corresponding media file
    """
    base_path = os.path.splitext(json_path)[0]
    
    for ext in ALL_MEDIA_EXTENSIONS:
        if os.path.exists(base_path + ext.lower()) or os.path.exists(base_path + ext.upper()):
            return base_path + ext.lower()
    
    dir_path = os.path.dirname(json_path)
    title_without_ext = os.path.splitext(title)[0]
    
    for ext in ALL_MEDIA_EXTENSIONS:
        potential_path = os.path.join(dir_path, title_without_ext + ext)
        if os.path.exists(potential_path):
            return potential_path
    
    for ext in ALL_MEDIA_EXTENSIONS:
        pattern = os.path.join(dir_path, f"*{title_without_ext}*{ext}")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    
    raise FileNotFoundError(f"No media file found for {json_path} (title: {title})")

def get_target_path(timestamp, media_path):
    """
    Generate target path based on timestamp
    """
    date = datetime.fromtimestamp(timestamp)
    year = str(date.year)
    month = str(date.month).zfill(2)
    day = str(date.day).zfill(2)
    
    media_extension = os.path.splitext(media_path)[1].lower()
    media_filename = os.path.splitext(os.path.basename(media_path))[0]
    
    return os.path.join(
        year,
        f"{year}-{month}-{day}",
        f"{media_filename}{media_extension}"
    ), media_extension

def process_media_without_json(media_path):
    """
    Process media file without JSON metadata
    """
    timestamp, source = get_file_date(media_path)
    print(f"Using {source} date {datetime.fromtimestamp(timestamp)} for {media_path}")
    target_path, media_ext = get_target_path(timestamp, media_path)
    return target_path, media_ext

def process_json_file(json_path):
    """
    Process JSON file and corresponding media file
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    media_path = find_media_file(json_path, metadata['title'])
    timestamp, source = get_valid_timestamp(metadata, media_path)
    print(f"Using {source} date {datetime.fromtimestamp(timestamp)} for {media_path}")
    target_path, media_ext = get_target_path(timestamp, media_path)
    
    return target_path, media_ext, media_path

def organize_media(source_dir='.', target_dir='___organized_media'):
    """
    Organize photos and videos based on their metadata
    """
    source_dir = os.path.abspath(source_dir)
    target_dir = os.path.abspath(target_dir)
    
    stats = {
        'processed': 0,
        'processed_with_json': 0,
        'processed_without_json': 0,
        'errors': 0,
        'photos': 0,
        'videos': 0,
        'skipped_directories': 0
    }
    
    print(f"Starting media organization...")
    print(f"Source directory: {source_dir}")
    print(f"Target directory: {target_dir}")
    
    # First, process files with JSON
    processed_media_files = set()
    for root, _, files in os.walk(source_dir):
        # Пропускаємо цільову директорію та її підпапки
        if not should_process_directory(root, target_dir):
            stats['skipped_directories'] += 1
            continue
            
        for file in files:
            if file.endswith('.json'):
                json_path = os.path.join(root, file)
                
                try:
                    target_path, media_ext, media_path = process_json_file(json_path)
                    processed_media_files.add(media_path.lower())
                    
                    full_target_dir = os.path.join(target_dir, os.path.dirname(target_path))
                    os.makedirs(full_target_dir, exist_ok=True)
                    
                    shutil.move(media_path, os.path.join(target_dir, target_path))
                    shutil.move(json_path, os.path.join(target_dir, os.path.dirname(target_path), 
                                                      os.path.basename(json_path)))
                    
                    stats['processed'] += 1
                    stats['processed_with_json'] += 1
                    if media_ext in PHOTO_EXTENSIONS:
                        stats['photos'] += 1
                    else:
                        stats['videos'] += 1
                    
                    print(f"Moved (with JSON) {os.path.basename(media_path)} to {target_path}")
                    
                except Exception as e:
                    stats['errors'] += 1
                    print(f"Error processing {file}: {str(e)}")
    
    # Then, process remaining media files
    for root, _, files in os.walk(source_dir):
        # Пропускаємо цільову директорію та її підпапки
        if not should_process_directory(root, target_dir):
            continue
            
        for file in files:
            file_path = os.path.join(root, file)
            if file_path.lower() not in processed_media_files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in ALL_MEDIA_EXTENSIONS:
                    try:
                        target_path, media_ext = process_media_without_json(file_path)
                        
                        full_target_dir = os.path.join(target_dir, os.path.dirname(target_path))
                        os.makedirs(full_target_dir, exist_ok=True)
                        
                        shutil.move(file_path, os.path.join(target_dir, target_path))
                        
                        stats['processed'] += 1
                        stats['processed_without_json'] += 1
                        if media_ext in PHOTO_EXTENSIONS:
                            stats['photos'] += 1
                        else:
                            stats['videos'] += 1
                        
                        print(f"Moved (without JSON) {file} to {target_path}")
                        
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"Error processing {file}: {str(e)}")
    
    print("\nOrganization completed!")
    print(f"Total processed files: {stats['processed']}")
    print(f"Processed with JSON: {stats['processed_with_json']}")
    print(f"Processed without JSON: {stats['processed_without_json']}")
    print(f"Photos: {stats['photos']}")
    print(f"Videos: {stats['videos']}")
    print(f"Skipped directories: {stats['skipped_directories']}")
    print(f"Errors: {stats['errors']}")

if __name__ == "__main__":
    organize_media()
