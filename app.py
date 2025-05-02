import os
import tempfile
import logging
import unicodedata
import uuid
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
try:
    from transliterate import translit
except ImportError:
    translit = None

# Configure logging with fallback
log_file = '/home/sa1den/mysite/upload.log'
try:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
except Exception as e:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logging.error(f"Failed to configure file logging: {e}")

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuration
STORAGE_MODE = 'local'
LOCAL_UPLOAD_DIR = '/home/sa1den/mysite/uploads'

# Manual transliteration for Russian characters (fallback if transliterate is unavailable)
RUSSIAN_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
    'я': 'ya', 'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'Kh',
    'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E',
    'Ю': 'Yu', 'Я': 'Ya'
}

def manual_transliterate(text):
    return ''.join(RUSSIAN_TO_LATIN.get(c, c) for c in text)

# Function to normalize filename
def normalize_filename(filename):
    try:
        # Normalize to NFC
        normalized = unicodedata.normalize('NFC', filename)
        # Split into name and extension
        name, ext = os.path.splitext(normalized)
        # Try original name with secure_filename
        safe_name = secure_filename(name)
        logging.debug(f"Secure filename result: {name} -> {safe_name}")
        
        if not safe_name or safe_name.strip('_') == '':
            # Try transliteration
            if translit:
                try:
                    safe_name = translit(name, 'ru', reversed=True)
                    safe_name = secure_filename(safe_name)
                    logging.debug(f"Transliterate result: {name} -> {safe_name}")
                except Exception as e:
                    logging.error(f"Transliteration failed: {e}")
            if not safe_name or safe_name.strip('_') == '':
                # Manual transliteration
                safe_name = manual_transliterate(name)
                safe_name = secure_filename(safe_name)
                logging.debug(f"Manual transliterate result: {name} -> {safe_name}")
        
        if not safe_name or safe_name.strip('_') == '':
            # Fallback to UUID
            safe_name = str(uuid.uuid4())[:8]
            logging.debug(f"UUID fallback: {name} -> {safe_name}")
        
        # Recombine with extension
        safe_filename = f"{safe_name}{ext.lower()}"
        logging.debug(f"Final filename: {filename} -> {safe_filename}")
        return safe_filename
    except Exception as e:
        logging.error(f"Error normalizing filename {filename}: {e}")
        # Ultimate fallback
        ext = os.path.splitext(filename)[1].lower()
        safe_filename = f"{uuid.uuid4()[:8]}{ext}"
        logging.debug(f"Ultimate fallback: {filename} -> {safe_filename}")
        return safe_filename

# Function to format file size
def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

# Get list of files
def get_file_list():
    try:
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        files = os.listdir(LOCAL_UPLOAD_DIR)
        logging.debug(f"Retrieved local file list: {files}")
        return files
    except Exception as e:
        logging.error(f"Error retrieving local file list: {e}")
        flash(f"Error listing files: {str(e)}", 'error')
        return []

# Get file size
def get_file_size(filename):
    try:
        file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
        size = os.path.getsize(file_path)
        logging.debug(f"Local file size for {filename}: {size} bytes")
        return size
    except Exception as e:
        logging.error(f"Error getting local file size for {filename}: {e}")
        return 0

# Function to read text file
def read_file(filename):
    try:
        file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logging.debug(f"Successfully read local file: {filename}")
        return content
    except Exception as e:
        logging.error(f"Error reading local file {filename}: {e}")
        flash(f"Error reading file: {str(e)}", 'error')
        return None

# Main page
@app.route('/')
def index():
    try:
        files = get_file_list()
        files_with_sizes = []
        total_size = 0
        for f in files:
            size = get_file_size(f)
            total_size += size
            files_with_sizes.append((f, format_file_size(size)))
        total_size_formatted = format_file_size(total_size)
        logging.debug(f"Total size: {total_size} bytes ({total_size_formatted})")
        return render_template('index.html', files=files_with_sizes, total_size=total_size_formatted)
    except Exception as e:
        logging.error(f"Error rendering index: {e}")
        flash(f"Error loading page: {str(e)}", 'error')
        return render_template('index.html', files=[], total_size="0 B")

# File preview page
@app.route('/preview/<filename>')
def preview(filename):
    file_content = None
    file_type = None
    try:
        text_extensions = ('.txt', '.py', '.cpp', '.h', '.json', '.xml')
        if filename.lower().endswith(text_extensions):
            file_content = read_file(filename)
            file_type = 'text'
        elif filename.lower().endswith(('.jpg', '.png')):
            file_type = 'image'
        elif filename.lower().endswith('.mp4'):
            file_type = 'video'
        logging.debug(f"Preview for {filename}: type={file_type}")
    except Exception as e:
        logging.error(f"Error previewing file {filename}: {e}")
        flash(f"Error previewing file: {str(e)}", 'error')
    return render_template('preview.html', file=filename, file_content=file_content, file_type=file_type)

# Upload file
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file:
        flash('No file selected for upload.', 'error')
        return redirect(url_for('index'))
    
    filename = normalize_filename(file.filename)
    if not filename:
        flash('Invalid filename.', 'error')
        return redirect(url_for('index'))

    try:
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
        file.save(file_path)
        logging.debug(f"File uploaded locally: {filename}")
        flash(f'File {filename} uploaded successfully.', 'success')
    except Exception as e:
        logging.error(f"Error uploading file locally {filename}: {e}")
        flash(f'Error uploading file: {str(e)}', 'error')
    return redirect(url_for('index'))

# Download file
@app.route('/download/<filename>')
def download(filename):
    try:
        file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
        logging.debug(f"File downloaded locally: {filename}")
        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        logging.error(f"Error downloading file locally {filename}: {e}")
        flash(f"Error downloading file: {str(e)}", 'error')
        raise

# Delete file
@app.route('/delete/<filename>')
def delete(filename):
    try:
        file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
        os.remove(file_path)
        logging.debug(f"File deleted locally: {filename}")
        flash(f'File {filename} deleted successfully.', 'success')
    except Exception as e:
        logging.error(f"Error deleting file locally {filename}: {e}")
        flash(f"Error deleting file: {str(e)}", 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)