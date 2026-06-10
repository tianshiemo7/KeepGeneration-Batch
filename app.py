import os
import random
import threading
import time
import uuid
import zipfile
from io import BytesIO
from flask import Flask, render_template, request, send_file, url_for, jsonify
from datetime import datetime, timedelta
from PIL import Image
from KeepSultan import KeepSultanApp, KeepConfig, NumberRange, TimeRange

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_fallback_secret_key_change_me')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['OUTPUT_FOLDER'] = 'static/output'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB限制
app.config['FILE_MAX_AGE_SECONDS'] = int(os.environ.get('FILE_MAX_AGE_SECONDS', 1 * 60 * 60))
app.config['CLEANUP_INTERVAL_SECONDS'] = int(os.environ.get('CLEANUP_INTERVAL_SECONDS', 30 * 60))
app.config['MAX_BATCH_COUNT'] = 100  # 批量生成最大数量
app.config['MAP_FOLDER'] = 'static/maps'  # 地图文件夹
app.config['BATTERY_FOLDER'] = 'static/battery'  # 电池图标文件夹

DEFAULT_AVATAR = 'static/default_avatar.png'
# 电池图标在模板上的区域：左上(950,41) 右下(1015,72)，即 65×31
BATTERY_POS = (950, 43)
BATTERY_SIZE = (65, 31)


def get_map_files(folder: str = None) -> list:
    """扫描指定文件夹，返回所有图片文件路径列表（按文件名排序）"""
    if folder is None:
        folder = app.config['MAP_FOLDER']
    map_dir = folder
    if not os.path.isdir(map_dir):
        return []
    exts = {'.png', '.jpg', '.jpeg', '.webp'}
    files = []
    for f in sorted(os.listdir(map_dir)):
        if os.path.splitext(f)[1].lower() in exts:
            files.append(os.path.join(map_dir, f).replace('\\', '/'))
    return files


# 创建必要目录
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)


def cleanup_old_files(folder_path: str, max_age_seconds: int):
    now = time.time()
    for root, _, files in os.walk(folder_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            try:
                if not os.path.isfile(file_path):
                    continue
                if now - os.path.getmtime(file_path) > max_age_seconds:
                    os.remove(file_path)
                    app.logger.info("Removed stale file: %s", file_path)
            except FileNotFoundError:
                continue
            except Exception as exc:
                app.logger.warning("Failed to remove file %s: %s", file_path, exc)


def start_cleanup_scheduler():
    def _run_cleanup_loop():
        while True:
            try:
                max_age = app.config['FILE_MAX_AGE_SECONDS']
                for folder in (app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']):
                    cleanup_old_files(folder, max_age)
            except Exception as exc:
                app.logger.error("Error during scheduled cleanup: %s", exc)
            time.sleep(app.config['CLEANUP_INTERVAL_SECONDS'])

    thread = threading.Thread(target=_run_cleanup_loop, daemon=True, name="cleanup-worker")
    thread.start()
    return thread


if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_cleanup_scheduler()

# 默认配置
# 地图列表在首次请求时懒加载，避免模块导入时文件夹还不存在
_map_cache = None


def get_cached_maps() -> list:
    global _map_cache
    if _map_cache is None:
        _map_cache = get_map_files()
    return _map_cache


DEFAULT_CONFIG = {
    "template": "static/default_template.png",
    "username": "Keep User",
    "date": datetime.now().strftime("%Y-%m-%d"),
    "end_time": ["18:00", "20:00"],
    "location": "广州市",
    "weather_weights": {"晴": 3, "多云": 5, "阴天": 2},
    "temperature": [18, 28],
    "total_km": [4.02, 4.3],
    "sport_time": ["00:23:00", "00:25:00"],
    "total_time": ["00:27:00", "00:31:00"],
    "cumulative_climb": [90, 96],
    "average_cadence": [90, 99],
    "exercise_load": [70, 90],
    "battery": [30, 80]
}


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', default_config=DEFAULT_CONFIG)


@app.route('/api/list_maps', methods=['GET'])
def api_list_maps():
    """扫描指定文件夹，返回图片文件列表"""
    folder = request.args.get('folder', app.config['MAP_FOLDER']).strip()
    if not folder:
        folder = app.config['MAP_FOLDER']
    # 安全检查：只允许相对路径，防止目录遍历
    folder = folder.replace('\\', '/')
    if folder.startswith('/') or '..' in folder:
        return jsonify({"success": False, "error": "不允许的路径"}), 400
    files = get_map_files(folder)
    return jsonify({
        "success": True,
        "folder": folder,
        "files": [{
            "name": os.path.basename(f),
            "url": "/" + f.replace('\\', '/')  # 相对URL供前端预览
        } for f in files]
    })


def handle_upload(field_name: str, file_type: str) -> str | None:
    if field_name not in request.files:
        return None
    file = request.files[field_name]
    if file.filename == '' or file.filename is None:
        return None
    if file and allowed_file(file.filename):
        img = Image.open(file.stream)
        img = img.convert("RGBA")
        filename = f"{file_type}_{uuid.uuid4().hex}.png"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        img.save(save_path, format="PNG")
        return save_path
    return None


def allowed_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'webp'}


def random_time_between(time_min: str, time_max: str) -> str:
    """在两个 HH:MM 时间之间随机取值，返回 HH:MM:SS"""
    def to_minutes(t: str) -> int:
        parts = t.strip().split(':')
        return int(parts[0]) * 60 + int(parts[1])
    min_mins = to_minutes(time_min)
    max_mins = to_minutes(time_max)
    if min_mins > max_mins:
        min_mins, max_mins = max_mins, min_mins
    rand_mins = random.randint(min_mins, max_mins)
    hh, mm = divmod(rand_mins, 60)
    return f"{hh:02d}:{mm:02d}:00"


def advance_date(date_str: str, days: int) -> str:
    """日期递增指定的天数，返回 YYYY-MM-DD"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return (dt + timedelta(days=days)).strftime('%Y-%m-%d')


def random_weather(weights: dict) -> str:
    """根据权重随机选择天气，weights 如 {'晴': 3, '多云': 5, '阴天': 2}"""
    types = list(weights.keys())
    w = [weights[t] for t in types]
    total = sum(w)
    if total <= 0:
        return "多云"
    return random.choices(types, weights=w, k=1)[0]


def overlay_battery(image_path: str, battery_path: str, pos: tuple, size: tuple):
    """在已生成的截图上叠加电池图标"""
    base = Image.open(image_path).convert("RGBA")
    battery = Image.open(battery_path).convert("RGBA")
    battery = battery.resize(size, Image.LANCZOS)
    base.paste(battery, pos, battery)
    base.save(image_path, format="PNG")


def generate_image(template_path: str, map_path: str, avatar_path: str, params: dict,
                   output_path: str, battery_path: str = None):
    """生成单张Keep跑步截图，可选叠加电池图标"""
    cfg = KeepConfig(
        template=template_path,
        map=map_path,
        avatar=avatar_path,
        username=params['username'],
        date=params['date'].replace('-', '/'),
        location=params['location'],
        weather=params['weather'],
        temperature=params['temperature'],
        end_time=params['end_time'],
        total_km=NumberRange(params['total_km'][0], params['total_km'][1], 2),
        sport_time=TimeRange(params['sport_time'][0], params['sport_time'][1]),
        total_time=TimeRange(params['total_time'][0], params['total_time'][1]),
        cumulative_climb=NumberRange(params['cumulative_climb'][0], params['cumulative_climb'][1], 0),
        average_cadence=NumberRange(params['average_cadence'][0], params['average_cadence'][1], 0),
        exercise_load=NumberRange(params['exercise_load'][0], params['exercise_load'][1], 0)
    )

    # 左上角状态栏时间 = 结束时间 + 随机 0~15 分钟
    end_sec = int(params['end_time'].split(':')[0]) * 3600 + int(params['end_time'].split(':')[1]) * 60
    offset_sec = random.randint(0, 15 * 60)
    status_sec = end_sec + offset_sec
    sh = status_sec // 3600
    sm = (status_sec % 3600) // 60
    cfg.status_bar_time = f"{sh:02d}:{sm:02d}:00"

    ks = KeepSultanApp(cfg)
    ks.process()
    ks.save(output_path)

    # 叠加电池图标
    if battery_path and os.path.isfile(battery_path):
        overlay_battery(output_path, battery_path, BATTERY_POS, BATTERY_SIZE)


def create_zip_file(file_paths: list, zip_name: str) -> str:
    """将多个文件打包为ZIP，返回ZIP文件路径"""
    zip_dir = os.path.join(app.config['OUTPUT_FOLDER'], 'zips')
    os.makedirs(zip_dir, exist_ok=True)
    zip_path = os.path.join(zip_dir, zip_name)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            zf.write(fp, os.path.basename(fp))

    return zip_path


# ==================== 单张生成接口（保留原功能） ====================

@app.route('/api/generate', methods=['POST'])
def api_generate():
    try:
        avatar_uploaded_path = handle_upload('avatar', 'avatar')

        map_folder = request.form.get('map_folder', app.config['MAP_FOLDER']).strip()
        if not map_folder or '..' in map_folder or map_folder.startswith('/'):
            map_folder = app.config['MAP_FOLDER']
        map_files = get_map_files(map_folder)
        map_path = random.choice(map_files) if map_files else 'static/maps/default.png'

        if avatar_uploaded_path:
            avatar_path = avatar_uploaded_path
        else:
            avatar_path = DEFAULT_AVATAR

        def get_val(key, default):
            val = request.form.get(key)
            if val is not None:
                val = val.strip()
            return val if val else default

        # 结束时间：支持范围随机
        end_time_min = get_val('end_time_min', DEFAULT_CONFIG['end_time'][0])
        end_time_max = get_val('end_time_max', DEFAULT_CONFIG['end_time'][1])

        # 天气权重
        weather_weights = {}
        weather_map = {'qing': '晴', 'duoyun': '多云', 'yintian': '阴天'}
        for key, label in weather_map.items():
            w = int(get_val(f'weather_{key}', str(DEFAULT_CONFIG['weather_weights'].get(label, 0))))
            if w > 0:
                weather_weights[label] = w
        if not weather_weights:
            weather_weights = DEFAULT_CONFIG['weather_weights']

        # 温度范围
        temp_min = int(get_val('temperature_min', str(DEFAULT_CONFIG['temperature'][0])))
        temp_max = int(get_val('temperature_max', str(DEFAULT_CONFIG['temperature'][1])))

        # 电池电量范围
        battery_min = int(get_val('battery_min', str(DEFAULT_CONFIG['battery'][0])))
        battery_max = int(get_val('battery_max', str(DEFAULT_CONFIG['battery'][1])))
        battery_pct = random.randint(battery_min, battery_max)
        battery_path = os.path.join(app.config['BATTERY_FOLDER'], f"{battery_pct}.png").replace('\\', '/')

        form_data = {
            'username': get_val('username', DEFAULT_CONFIG['username']),
            'date': get_val('date', DEFAULT_CONFIG['date']),
            'location': get_val('location', DEFAULT_CONFIG['location']),
            'weather': random_weather(weather_weights),
            'temperature': f"{random.randint(temp_min, temp_max)}°C",
            'end_time': random_time_between(end_time_min, end_time_max),
            'total_km': [
                float(get_val('total_km_min', DEFAULT_CONFIG['total_km'][0])),
                float(get_val('total_km_max', DEFAULT_CONFIG['total_km'][1]))
            ],
            'sport_time': [
                get_val('sport_time_min', DEFAULT_CONFIG['sport_time'][0]),
                get_val('sport_time_max', DEFAULT_CONFIG['sport_time'][1])
            ],
            'total_time': [
                get_val('total_time_min', DEFAULT_CONFIG['total_time'][0]),
                get_val('total_time_max', DEFAULT_CONFIG['total_time'][1])
            ],
            'cumulative_climb': [
                int(get_val('cumulative_climb_min', DEFAULT_CONFIG['cumulative_climb'][0])),
                int(get_val('cumulative_climb_max', DEFAULT_CONFIG['cumulative_climb'][1]))
            ],
            'average_cadence': [
                int(get_val('average_cadence_min', DEFAULT_CONFIG['average_cadence'][0])),
                int(get_val('average_cadence_max', DEFAULT_CONFIG['average_cadence'][1]))
            ],
            'exercise_load': [
                int(get_val('exercise_load_min', DEFAULT_CONFIG['exercise_load'][0])),
                int(get_val('exercise_load_max', DEFAULT_CONFIG['exercise_load'][1]))
            ]
        }

        output_filename = f"result_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        generate_image(
            DEFAULT_CONFIG['template'],
            map_path or DEFAULT_CONFIG['map'],
            avatar_path,
            form_data,
            output_path,
            battery_path=battery_path
        )

        return jsonify({
            "success": True,
            "image_url": url_for('download', filename=output_filename),
            "download_url": url_for('download', filename=output_filename)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 批量生成接口 ====================

@app.route('/api/batch_generate', methods=['POST'])
def api_batch_generate():
    try:
        # 获取生成数量
        count = int(request.form.get('count', 1))
        count = max(1, min(count, app.config['MAX_BATCH_COUNT']))

        avatar_uploaded_path = handle_upload('avatar', 'avatar')

        # 确定地图随机池：从用户指定的文件夹读取
        map_folder = request.form.get('map_folder', app.config['MAP_FOLDER']).strip()
        if not map_folder or '..' in map_folder or map_folder.startswith('/'):
            map_folder = app.config['MAP_FOLDER']

        # 获取用户勾选的地图，未勾选则用全部
        selected_maps = request.form.getlist('map_pool')
        if selected_maps:
            map_pool = []
            for m in selected_maps:
                full = os.path.join(map_folder, m).replace('\\', '/')
                if os.path.isfile(full):
                    map_pool.append(full)
        else:
            map_pool = get_map_files(map_folder)

        if not map_pool:
            map_pool = get_map_files(app.config['MAP_FOLDER'])
        if not map_pool:
            map_pool.append('static/maps/default.png')

        # 头像路径
        if avatar_uploaded_path:
            avatar_path = avatar_uploaded_path
        else:
            avatar_path = DEFAULT_AVATAR

        # 获取表单参数
        def get_val(key, default):
            val = request.form.get(key)
            if val is not None:
                val = val.strip()
            return val if val else default

        # 结束时间范围
        end_time_min = get_val('end_time_min', DEFAULT_CONFIG['end_time'][0])
        end_time_max = get_val('end_time_max', DEFAULT_CONFIG['end_time'][1])

        # 天气权重
        weather_weights = {}
        weather_map = {'qing': '晴', 'duoyun': '多云', 'yintian': '阴天'}
        for key, label in weather_map.items():
            w = int(get_val(f'weather_{key}', str(DEFAULT_CONFIG['weather_weights'].get(label, 0))))
            if w > 0:
                weather_weights[label] = w
        if not weather_weights:
            weather_weights = DEFAULT_CONFIG['weather_weights']

        # 温度范围
        temp_min = int(get_val('temperature_min', str(DEFAULT_CONFIG['temperature'][0])))
        temp_max = int(get_val('temperature_max', str(DEFAULT_CONFIG['temperature'][1])))

        # 电池电量范围
        battery_min = int(get_val('battery_min', str(DEFAULT_CONFIG['battery'][0])))
        battery_max = int(get_val('battery_max', str(DEFAULT_CONFIG['battery'][1])))

        base_form_data = {
            'username': get_val('username', DEFAULT_CONFIG['username']),
            'date': get_val('date', DEFAULT_CONFIG['date']),
            'location': get_val('location', DEFAULT_CONFIG['location']),
            'weather': '',  # 每张独立随机
            'temperature': '',  # 每张独立随机
            'total_km': [
                float(get_val('total_km_min', DEFAULT_CONFIG['total_km'][0])),
                float(get_val('total_km_max', DEFAULT_CONFIG['total_km'][1]))
            ],
            'sport_time': [
                get_val('sport_time_min', DEFAULT_CONFIG['sport_time'][0]),
                get_val('sport_time_max', DEFAULT_CONFIG['sport_time'][1])
            ],
            'total_time': [
                get_val('total_time_min', DEFAULT_CONFIG['total_time'][0]),
                get_val('total_time_max', DEFAULT_CONFIG['total_time'][1])
            ],
            'cumulative_climb': [
                int(get_val('cumulative_climb_min', DEFAULT_CONFIG['cumulative_climb'][0])),
                int(get_val('cumulative_climb_max', DEFAULT_CONFIG['cumulative_climb'][1]))
            ],
            'average_cadence': [
                int(get_val('average_cadence_min', DEFAULT_CONFIG['average_cadence'][0])),
                int(get_val('average_cadence_max', DEFAULT_CONFIG['average_cadence'][1]))
            ],
            'exercise_load': [
                int(get_val('exercise_load_min', DEFAULT_CONFIG['exercise_load'][0])),
                int(get_val('exercise_load_max', DEFAULT_CONFIG['exercise_load'][1]))
            ]
        }

        # 批量生成
        batch_id = datetime.now().strftime('%Y%m%d%H%M%S')
        generated_images = []
        prev_map = None

        for i in range(count):
            # 日期递增：每张图片往后延一天
            iter_form_data = dict(base_form_data)
            iter_form_data['date'] = advance_date(base_form_data['date'], i)

            # 结束时间在范围内随机
            iter_form_data['end_time'] = random_time_between(end_time_min, end_time_max)

            # 天气按权重随机
            iter_form_data['weather'] = random_weather(weather_weights)

            # 温度在范围内随机
            iter_form_data['temperature'] = f"{random.randint(temp_min, temp_max)}°C"

            # 电池电量在范围内随机
            battery_pct = random.randint(battery_min, battery_max)
            battery_path = os.path.join(app.config['BATTERY_FOLDER'], f"{battery_pct}.png").replace('\\', '/')

            # 随机选择地图（连续两张不重复）
            if len(map_pool) > 1 and prev_map is not None:
                candidates = [m for m in map_pool if m != prev_map]
                random_map = random.choice(candidates)
            else:
                random_map = random.choice(map_pool)
            prev_map = random_map

            output_filename = f"batch_{batch_id}_{i+1:03d}.png"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

            generate_image(
                DEFAULT_CONFIG['template'],
                random_map,
                avatar_path,
                iter_form_data,
                output_path,
                battery_path=battery_path
            )

            generated_images.append({
                'index': i + 1,
                'filename': output_filename,
                'url': url_for('download', filename=output_filename),
                'map_used': os.path.basename(random_map),
                'date': iter_form_data['date']
            })

        # 如果生成数量 > 1，创建ZIP包
        zip_url = None
        if count > 1:
            image_paths = [
                os.path.join(app.config['OUTPUT_FOLDER'], img['filename'])
                for img in generated_images
            ]
            zip_filename = f"keep_batch_{batch_id}.zip"
            create_zip_file(image_paths, zip_filename)
            zip_url = url_for('download_zip', filename=zip_filename)

        return jsonify({
            "success": True,
            "count": count,
            "images": generated_images,
            "zip_url": zip_url
        })

    except Exception as e:
        app.logger.error(f"Batch generation error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/download/<filename>', methods=['GET'])
def download(filename):
    return send_file(
        os.path.join(app.config['OUTPUT_FOLDER'], filename),
        as_attachment=True,
        download_name=f"keep_result_{datetime.now().strftime('%Y%m%d')}.png"
    )


@app.route('/download_zip/<filename>', methods=['GET'])
def download_zip(filename):
    """下载ZIP包"""
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], 'zips', filename)
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"keep_batch_{datetime.now().strftime('%Y%m%d')}.zip",
        mimetype='application/zip'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=False)
