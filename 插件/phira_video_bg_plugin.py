import os
import re
import json
import shutil
import zipfile
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import fnmatch

try:
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
except AttributeError:
    CREATE_NO_WINDOW = 0


RPE_REQUIRED_FILES = {"info.txt"}
RPE_CHART_REQUIRED_KEYS = ["META", "BPMList", "judgeLineList"]
RPE_INFO_TXT_KEYS = ["Name", "Song", "Chart", "Level", "Charter", "Composer", "Picture"]


class RPEFormatValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate(self, directory):
        self.errors = []
        self.warnings = []
        is_valid = True

        if not os.path.isdir(directory):
            self.errors.append("目录不存在")
            return False

        files = os.listdir(directory)

        if not any(f == "info.txt" for f in files):
            self.errors.append("缺少必要文件: info.txt")
            is_valid = False

        chart_json_files = [f for f in files if f.endswith('.json') and f != 'extra.json' and not f.startswith('AutoSave_')]
        if not chart_json_files:
            self.errors.append("未找到谱子JSON文件")
            is_valid = False
        elif len(chart_json_files) > 1:
            self.warnings.append(f"发现多个谱子JSON文件: {', '.join(chart_json_files)}")

        audio_files = [f for f in files if os.path.splitext(f)[1].lower() in [".mp3", ".ogg", ".wav", ".flac"]]
        if not audio_files:
            self.warnings.append("未找到音频文件(.mp3/.ogg/.wav/.flac)")

        image_files = [f for f in files if os.path.splitext(f)[1].lower() in [".png", ".jpg", ".jpeg", ".webp"]]
        if not image_files:
            self.warnings.append("未找到背景图片文件(.png/.jpg/.jpeg/.webp)")

        info_txt_path = os.path.join(directory, "info.txt")
        if os.path.exists(info_txt_path):
            info_data = self._parse_info_txt(info_txt_path)
            missing_keys = [k for k in RPE_INFO_TXT_KEYS if k not in info_data]
            if missing_keys:
                self.warnings.append(f"info.txt 缺少字段: {', '.join(missing_keys)}")

        for chart_file in chart_json_files:
            chart_path = os.path.join(directory, chart_file)
            try:
                with open(chart_path, 'r', encoding='utf-8') as f:
                    chart_data = json.load(f)
                missing_chart_keys = [k for k in RPE_CHART_REQUIRED_KEYS if k not in chart_data]
                if missing_chart_keys:
                    self.errors.append(f"谱子JSON({chart_file})缺少必要字段: {', '.join(missing_chart_keys)}")
                    is_valid = False
                if 'META' in chart_data:
                    meta = chart_data['META']
                    if 'name' not in meta:
                        self.warnings.append(f"谱子JSON({chart_file})的META中缺少name字段")
                    if 'song' not in meta:
                        self.warnings.append(f"谱子JSON({chart_file})的META中缺少song字段")
            except json.JSONDecodeError as e:
                self.errors.append(f"谱子JSON({chart_file})格式错误: {str(e)}")
                is_valid = False
            except Exception as e:
                self.errors.append(f"读取谱子JSON({chart_file})失败: {str(e)}")
                is_valid = False

        return is_valid

    def _parse_info_txt(self, info_txt_path):
        info = {}
        with open(info_txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    info[key.strip()] = value.strip()
        return info

    def get_result_message(self):
        msg = []
        if self.errors:
            msg.append("错误:")
            for e in self.errors:
                msg.append(f"  - {e}")
        if self.warnings:
            msg.append("警告:")
            for w in self.warnings:
                msg.append(f"  - {w}")
        return "\n".join(msg) if msg else "验证通过"


class PhiraVideoBgPlugin:
    REQUIRED_FILES = {"info.yml", "info.txt", "extra.json"}
    EXCLUDE_PATTERNS = ["AutoSave_*.json", "blur*.png", "createTime.txt", "*.md"]
    AUDIO_EXTENSIONS = [".mp3", ".ogg", ".wav", ".flac"]
    IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"]

    def __init__(self):
        self.ffmpeg_path = None
        self.validator = RPEFormatValidator()

    def validate_rpe_format(self, input_path, progress_callback=None):
        is_pez = input_path.lower().endswith('.pez')
        is_zip = input_path.lower().endswith('.zip')

        temp_dir = None
        try:
            if is_pez or is_zip:
                temp_dir = os.path.join(os.path.dirname(input_path), '_temp_validate_' + str(os.getpid()))
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir, exist_ok=True)
                with zipfile.ZipFile(input_path, 'r') as z:
                    z.extractall(temp_dir)
                subdirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
                if len(subdirs) == 1:
                    subdir = os.path.join(temp_dir, subdirs[0])
                    sub_items = os.listdir(subdir)
                    if any(f in sub_items for f in self.REQUIRED_FILES):
                        for item in os.listdir(subdir):
                            src = os.path.join(subdir, item)
                            dst = os.path.join(temp_dir, item)
                            if os.path.exists(dst):
                                if os.path.isdir(dst):
                                    shutil.rmtree(dst)
                                else:
                                    os.remove(dst)
                            shutil.move(src, dst)
                        os.rmdir(subdir)
                validate_dir = temp_dir
            else:
                validate_dir = input_path

            is_valid = self.validator.validate(validate_dir)

            if not is_valid:
                return False, self.validator.get_result_message()

            return True, self.validator.get_result_message()
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def find_ffmpeg(self):
        if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
            return self.ffmpeg_path
        for name in ["ffmpeg", "ffmpeg.exe"]:
            path = shutil.which(name)
            if path:
                self.ffmpeg_path = path
                return path
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        for p in common_paths:
            if os.path.exists(p):
                self.ffmpeg_path = p
                return p
        return None

    def extract_pez(self, pez_path, dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(pez_path, 'r') as z:
            z.extractall(dest_dir)
        self._flatten_if_needed(dest_dir)

    def _flatten_if_needed(self, dest_dir):
        subdirs = [d for d in os.listdir(dest_dir) if os.path.isdir(os.path.join(dest_dir, d))]
        if len(subdirs) == 1:
            subdir = os.path.join(dest_dir, subdirs[0])
            sub_items = os.listdir(subdir)
            if any(f in sub_items for f in self.REQUIRED_FILES):
                for item in os.listdir(subdir):
                    src = os.path.join(subdir, item)
                    dst = os.path.join(dest_dir, item)
                    if os.path.exists(dst):
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    shutil.move(src, dst)
                os.rmdir(subdir)

    def find_chart_json(self, directory):
        for f in os.listdir(directory):
            if f.endswith('.json') and f != 'extra.json' and not f.startswith('AutoSave_'):
                return os.path.join(directory, f)
        return None

    def find_audio_file(self, directory):
        for f in os.listdir(directory):
            ext = os.path.splitext(f)[1].lower()
            if ext in self.AUDIO_EXTENSIONS:
                return f
        return None

    def find_image_file(self, directory):
        image_files = []
        for f in sorted(os.listdir(directory)):
            ext = os.path.splitext(f)[1].lower()
            if ext in self.IMAGE_EXTENSIONS:
                if f.lower() == 'line.png':
                    continue
                if f.lower().startswith('blur') and ext in ['.png']:
                    continue
                image_files.append(f)
        return image_files[0] if image_files else None

    def parse_info_txt(self, info_txt_path):
        info = {}
        if not os.path.exists(info_txt_path):
            return info
        with open(info_txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    info[key.strip()] = value.strip()
        return info

    def parse_chart_json(self, chart_path):
        with open(chart_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data

    def get_max_measure(self, chart_data):
        max_measure = 0
        for line in chart_data.get('judgeLineList', []):
            for note in line.get('notes', []):
                start_time = note.get('startTime', [0, 0, 1])
                end_time = note.get('endTime', [0, 0, 1])
                max_measure = max(max_measure, start_time[0], end_time[0])
            for layer in line.get('eventLayers', []):
                for event_type in ['alphaEvents', 'moveXEvents', 'moveYEvents', 'rotateEvents', 'speedEvents']:
                    for event in layer.get(event_type, []):
                        start_time = event.get('startTime', [0, 0, 1])
                        end_time = event.get('endTime', [0, 0, 1])
                        max_measure = max(max_measure, start_time[0], end_time[0])
        return max_measure

    def get_bpm(self, chart_data):
        bpm_list = chart_data.get('BPMList', [])
        if bpm_list:
            return bpm_list[0].get('bpm', 120.0)
        return 120.0

    def get_meta_info(self, chart_data):
        meta = chart_data.get('META', {})
        return {
            'name': meta.get('name', 'Unknown'),
            'charter': meta.get('charter', 'Unknown'),
            'composer': meta.get('composer', 'Unknown'),
            'background': meta.get('background', ''),
        }

    def strip_video_audio(self, video_path, output_dir):
        ffmpeg = self.find_ffmpeg()
        if not ffmpeg:
            return None
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(output_dir, f"{base_name}_silent.mp4")
        try:
            subprocess.run(
                [ffmpeg, '-i', video_path, '-c:v', 'copy', '-an', output_path],
                check=True, capture_output=True, timeout=300, creationflags=CREATE_NO_WINDOW
            )
            return os.path.basename(output_path)
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg错误: {e.stderr.decode('utf-8', errors='replace')}")
            return None
        except subprocess.TimeoutExpired:
            print("FFmpeg超时")
            return None

    def clean_chart_json(self, chart_path):
        with open(chart_path, 'r', encoding='utf-8') as f:
            raw = f.read()

        raw = re.sub(r',"bezier"\s*:\s*-?\d+\.?\d*', '', raw)
        raw = re.sub(r'"bezier"\s*:\s*-?\d+\.?\d*,', '', raw)
        raw = re.sub(r',"bezierPoints"\s*:\s*\[[\d\s,.-]*\]', '', raw)
        raw = re.sub(r'"bezierPoints"\s*:\s*\[[\d\s,.-]*\],', '', raw)
        raw = re.sub(r',"duration"\s*:\s*\d+\.?\d*', '', raw)
        raw = re.sub(r',"illustration"\s*:\s*"[^"]*"', '', raw)

        meta_match = re.search(r'"META"\s*:\s*\{', raw)
        if meta_match:
            start_pos = meta_match.end()
            depth = 1
            pos = start_pos
            while pos < len(raw) and depth > 0:
                if raw[pos] == '{':
                    depth += 1
                elif raw[pos] == '}':
                    depth -= 1
                pos += 1
            meta_content = raw[start_pos:pos-1]
            offset_match = re.search(r'"offset"\s*:\s*(-?\d+\.?\d*)', meta_content)
            if offset_match:
                offset_val = float(offset_match.group(1))
                if abs(offset_val) > 10:
                    raw = raw[:meta_match.end() + offset_match.start()] + '"offset": 0' + raw[meta_match.end() + offset_match.end():]

        raw = re.sub(r',\s*([}\]])', r'\1', raw)
        raw = raw.replace(',,', ',')

        try:
            json.loads(raw)
            with open(chart_path, 'w', encoding='utf-8') as f:
                f.write(raw)
            return True
        except json.JSONDecodeError as e:
            print(f"清洗后JSON格式错误: {e}")
            return False

    def create_extra_json(self, output_dir, video_filename, bpm, max_measure):
        extra_data = {
            "bpm": [
                {"time": [0, 0, 1], "bpm": bpm}
            ],
            "videos": [
                {
                    "path": video_filename,
                    "time": [0, 0, 1],
                    "scale": "cropCenter",
                    "alpha": 1,
                    "dim": 0.4,
                    "startTime": [0, 0, 1],
                    "endTime": [max_measure + 10, 0, 1],
                    "easingType": 1,
                    "easingLeft": 0.0,
                    "easingRight": 1.0
                }
            ]
        }
        extra_path = os.path.join(output_dir, 'extra.json')
        with open(extra_path, 'w', encoding='utf-8') as f:
            json.dump(extra_data, f, indent=3, ensure_ascii=False)

    def _yaml_escape(self, value):
        if isinstance(value, str):
            if any(c in value for c in '":{}[]&*?|>!%@#`'):
                return f'"{value.replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34))}"'
        return str(value)

    def create_info_yml(self, output_dir, chart_data, info_txt, audio_file, bg_image, chart_filename):
        meta_info = self.get_meta_info(chart_data)
        name = info_txt.get('Name', meta_info['name'])
        charter = info_txt.get('Charter', meta_info['charter'])
        composer = info_txt.get('Composer', meta_info['composer'])
        level = info_txt.get('Level', '0')
        chart_name = chart_filename if chart_filename else 'chart.json'
        music_name = audio_file if audio_file else 'music.mp3'
        illustration_name = bg_image if bg_image else 'bg.png'

        yml_content = f"""id: null
uploader: null
name: {self._yaml_escape(name)}
difficulty: 0.0
level: "{level}"
charter: {self._yaml_escape(charter)}
composer: {self._yaml_escape(composer)}
illustrator: "未知"
chart: {chart_name}
format: null
music: {music_name}
illustration: {illustration_name}
unlockVideo: null
previewStart: 0.0
previewEnd: 0.0
aspectRatio: 1.7777778
backgroundDim: 0.4
lineLength: 6.0
offset: 0.0
tip: null
tags: []
intro: null
holdPartialCover: false
noteUniformScale: false
forceAspectRatio: false
useRpe170Speed: null
useAttachUiFix: null
created: null
updated: null
chartUpdated: null
"""
        yml_path = os.path.join(output_dir, 'info.yml')
        with open(yml_path, 'w', encoding='utf-8') as f:
            f.write(yml_content)

    def update_info_txt(self, output_dir, video_filename):
        info_txt_path = os.path.join(output_dir, 'info.txt')
        lines = []
        if os.path.exists(info_txt_path):
            with open(info_txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        has_video = any(line.strip().startswith('Video:') for line in lines)
        if has_video:
            new_lines = []
            for line in lines:
                if line.strip().startswith('Video:'):
                    new_lines.append(f"Video: {video_filename}\n")
                else:
                    new_lines.append(line)
            lines = new_lines
        else:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            if lines and lines[-1].strip():
                lines.append('\n')
            lines.append(f"Video: {video_filename}\n")

        with open(info_txt_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def pack_pez(self, source_dir, output_path):
        temp_dir = os.path.join(source_dir, '_pez_temp')
        os.makedirs(temp_dir, exist_ok=True)

        required_files = []
        for f in os.listdir(source_dir):
            if f == '_pez_temp':
                continue
            fp = os.path.join(source_dir, f)
            if os.path.isfile(fp):
                skip = False
                for pattern in self.EXCLUDE_PATTERNS:
                    if fnmatch.fnmatch(f, pattern):
                        skip = True
                        break
                if not skip:
                    required_files.append(f)

        for f in required_files:
            shutil.copy2(os.path.join(source_dir, f), os.path.join(temp_dir, f))

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in os.listdir(temp_dir):
                z.write(os.path.join(temp_dir, f), f)

        shutil.rmtree(temp_dir)

    def rename_chart_files(self, working_dir, chart_filename, custom_name=None):
        base_name = os.path.splitext(chart_filename)[0]
        if custom_name:
            base_name = custom_name
        new_chart_name = f"{base_name}.json"
        new_audio_name = None
        new_image_name = None
        old_to_new = {}

        audio_file = self.find_audio_file(working_dir)
        if audio_file:
            ext = os.path.splitext(audio_file)[1]
            new_audio_name = f"{base_name}{ext}"
            if audio_file != new_audio_name:
                old_to_new[audio_file] = new_audio_name

        image_file = self.find_image_file(working_dir)
        if image_file:
            ext = os.path.splitext(image_file)[1]
            new_image_name = f"{base_name}{ext}"
            if image_file != new_image_name:
                old_to_new[image_file] = new_image_name

        chart_path = os.path.join(working_dir, chart_filename)
        if chart_filename != new_chart_name and os.path.exists(chart_path):
            new_chart_path = os.path.join(working_dir, new_chart_name)
            if os.path.exists(new_chart_path):
                os.remove(new_chart_path)
            shutil.move(chart_path, new_chart_path)
            chart_path = new_chart_path

        for old_name, new_name in old_to_new.items():
            old_path = os.path.join(working_dir, old_name)
            new_path = os.path.join(working_dir, new_name)
            if os.path.exists(old_path):
                shutil.move(old_path, new_path)

        if os.path.exists(chart_path):
            with open(chart_path, 'r', encoding='utf-8') as f:
                chart_data = json.load(f)

            if 'META' in chart_data:
                meta = chart_data['META']
                if new_audio_name and 'song' in meta:
                    meta['song'] = new_audio_name
                if new_image_name and 'background' in meta:
                    meta['background'] = new_image_name

            with open(chart_path, 'w', encoding='utf-8') as f:
                json.dump(chart_data, f, ensure_ascii=False, indent=2)

        info_txt_path = os.path.join(working_dir, 'info.txt')
        if os.path.exists(info_txt_path):
            with open(info_txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('Song:') and new_audio_name:
                    new_lines.append(f"Song: {new_audio_name}\n")
                elif stripped.startswith('Picture:') and new_image_name:
                    new_lines.append(f"Picture: {new_image_name}\n")
                elif stripped.startswith('Chart:') and new_chart_name:
                    new_lines.append(f"Chart: {new_chart_name}\n")
                else:
                    new_lines.append(line)
            with open(info_txt_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

        info_yml_path = os.path.join(working_dir, 'info.yml')
        if os.path.exists(info_yml_path):
            with open(info_yml_path, 'r', encoding='utf-8') as f:
                yml_content = f.read()
            if new_audio_name:
                yml_content = re.sub(r'music:\s*\S+', f'music: {new_audio_name}', yml_content)
            if new_image_name:
                yml_content = re.sub(r'illustration:\s*\S+', f'illustration: {new_image_name}', yml_content)
            if new_chart_name:
                yml_content = re.sub(r'chart:\s*\S+', f'chart: {new_chart_name}', yml_content)
            with open(info_yml_path, 'w', encoding='utf-8') as f:
                f.write(yml_content)

    def process(self, input_path, video_path, output_dir=None, copy_mode=False, copy_dest=None, compress_enabled=False, compress_format="zip", rename_files=False, custom_rename_name=None, progress_callback=None):
        if not os.path.exists(input_path):
            return False, "输入路径不存在"
        if not os.path.exists(video_path):
            return False, "视频文件不存在"

        is_pez = input_path.lower().endswith('.pez')
        is_zip = input_path.lower().endswith('.zip')

        working_dir = None

        if is_pez or is_zip:
            working_dir = os.path.join(output_dir or os.path.dirname(input_path), '_extracted_chart')
            if os.path.exists(working_dir):
                shutil.rmtree(working_dir)
            self.extract_pez(input_path, working_dir)
        else:
            if copy_mode and copy_dest:
                base_name = os.path.basename(os.path.normpath(input_path))
                working_dir = os.path.join(copy_dest, base_name + '_视频背景')
                if os.path.exists(working_dir):
                    shutil.rmtree(working_dir)
                shutil.copytree(input_path, working_dir)
            else:
                working_dir = input_path

        if progress_callback:
            progress_callback("正在分析谱子文件...")

        chart_file = self.find_chart_json(working_dir)
        if not chart_file:
            return False, "未找到谱子JSON文件"

        if progress_callback:
            progress_callback("正在解析谱子数据...")

        chart_data = self.parse_chart_json(chart_file)
        info_txt = self.parse_info_txt(os.path.join(working_dir, 'info.txt'))
        audio_file = self.find_audio_file(working_dir)
        bg_image = self.find_image_file(working_dir)
        chart_filename = os.path.basename(chart_file)

        bpm = self.get_bpm(chart_data)
        max_measure = self.get_max_measure(chart_data)

        if progress_callback:
            progress_callback("正在剥离视频音轨...")

        ffmpeg_available = self.find_ffmpeg() is not None
        video_filename = None

        if ffmpeg_available:
            video_filename = self.strip_video_audio(video_path, working_dir)
            if not video_filename:
                video_filename = os.path.basename(video_path)
                shutil.copy2(video_path, os.path.join(working_dir, video_filename))
        else:
            video_filename = os.path.basename(video_path)
            src_video = os.path.join(working_dir, video_filename)
            if not os.path.exists(src_video):
                shutil.copy2(video_path, src_video)

        if progress_callback:
            progress_callback("正在清洗谱子JSON以兼容Phira...")

        self.clean_chart_json(chart_file)

        if progress_callback:
            progress_callback("正在创建 extra.json...")

        self.create_extra_json(working_dir, video_filename, bpm, max_measure)

        if progress_callback:
            progress_callback("正在创建 info.yml...")

        self.create_info_yml(working_dir, chart_data, info_txt, audio_file, bg_image, chart_filename)

        if progress_callback:
            progress_callback("正在更新 info.txt...")

        self.update_info_txt(working_dir, video_filename)

        if rename_files:
            if progress_callback:
                progress_callback("正在重命名谱子文件...")
            chart_file = self.find_chart_json(working_dir)
            if chart_file:
                chart_filename = os.path.basename(chart_file)
                self.rename_chart_files(working_dir, chart_filename, custom_rename_name)

        if progress_callback:
            progress_callback("正在打包输出...")

        if is_pez or is_zip:
            ext = '.pez' if is_pez else '.zip'
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            if rename_files and custom_rename_name:
                base_name = custom_rename_name
            if output_dir:
                final_output = os.path.join(output_dir, f"{base_name}{ext}")
            else:
                final_output = os.path.join(os.path.dirname(input_path), f"{base_name}{ext}")

            if ext == '.pez':
                temp_zip = final_output.replace('.pez', '.zip')
                self.pack_pez(working_dir, temp_zip)
                if os.path.exists(final_output):
                    os.remove(final_output)
                os.rename(temp_zip, final_output)
            else:
                self.pack_pez(working_dir, final_output)

            shutil.rmtree(working_dir)
        elif compress_enabled:
            base_name = os.path.basename(os.path.normpath(working_dir))
            if rename_files and custom_rename_name:
                base_name = custom_rename_name
            ext = f".{compress_format}"
            if output_dir:
                final_output = os.path.join(output_dir, f"{base_name}{ext}")
            else:
                final_output = os.path.join(os.path.dirname(working_dir), f"{base_name}{ext}")
            self.pack_pez(working_dir, final_output)
            if copy_mode:
                shutil.rmtree(working_dir)
        else:
            final_output = working_dir

        return True, f"处理完成！输出路径: {final_output}"


class PhiraVideoBgGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PML-PhiraMural v1.0")
        self.root.geometry("650x600")
        self.root.resizable(True, True)

        self.plugin = PhiraVideoBgPlugin()

        self.input_path = tk.StringVar()
        self.input_mode = tk.StringVar(value="folder")
        self.video_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.copy_mode = tk.BooleanVar(value=False)
        self.copy_dest = tk.StringVar()
        self.compress_format = tk.StringVar(value="zip")
        self.compress_enabled = tk.BooleanVar(value=False)
        self.rename_files = tk.BooleanVar(value=False)
        self.rename_name = tk.StringVar()

        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.LabelFrame(main_frame, text="1. 选择谱子", padding="5")
        input_frame.pack(fill=tk.X, pady=5)

        mode_frame = ttk.Frame(input_frame)
        mode_frame.pack(fill=tk.X, pady=(0, 5))

        self.input_folder_radio = ttk.Radiobutton(mode_frame, text="文件夹", variable=self.input_mode, value="folder", command=self._toggle_input_mode)
        self.input_folder_radio.pack(side=tk.LEFT, padx=5)
        self.input_archive_radio = ttk.Radiobutton(mode_frame, text="压缩包 (.pez/.zip)", variable=self.input_mode, value="archive", command=self._toggle_input_mode)
        self.input_archive_radio.pack(side=tk.LEFT, padx=5)

        ttk.Entry(input_frame, textvariable=self.input_path, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(input_frame, text="浏览", command=self._browse_input).pack(side=tk.RIGHT)

        video_frame = ttk.LabelFrame(main_frame, text="2. 选择视频背景", padding="5")
        video_frame.pack(fill=tk.X, pady=5)

        self.video_entry = ttk.Entry(video_frame, textvariable=self.video_path, state="readonly")
        self.video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.video_btn = ttk.Button(video_frame, text="浏览", command=self._browse_video)
        self.video_btn.pack(side=tk.RIGHT)

        settings_frame = ttk.LabelFrame(main_frame, text="3. 设置", padding="5")
        settings_frame.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(settings_frame, text="复制谱子到新位置再修改（不勾选则直接修改）", variable=self.copy_mode, command=self._toggle_copy_mode).pack(anchor=tk.W)

        copy_dest_frame = ttk.Frame(settings_frame)
        copy_dest_frame.pack(fill=tk.X, pady=2)

        ttk.Label(copy_dest_frame, text="复制目标位置:").pack(side=tk.LEFT)
        self.copy_dest_entry = ttk.Entry(copy_dest_frame, textvariable=self.copy_dest, state="disabled")
        self.copy_dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.copy_dest_btn = ttk.Button(copy_dest_frame, text="浏览", command=self._browse_copy_dest, state="disabled")
        self.copy_dest_btn.pack(side=tk.RIGHT)

        self.compress_check = ttk.Checkbutton(settings_frame, text="压缩输出为包格式（仅文件夹输入时有效）", variable=self.compress_enabled, command=self._toggle_compress)
        self.compress_check.pack(anchor=tk.W, pady=(2, 0))

        compress_format_frame = ttk.Frame(settings_frame)
        compress_format_frame.pack(fill=tk.X, pady=2)

        self.comp_zip_radio = ttk.Radiobutton(compress_format_frame, text=".zip", variable=self.compress_format, value="zip")
        self.comp_zip_radio.pack(side=tk.LEFT, padx=5)
        self.comp_pez_radio = ttk.Radiobutton(compress_format_frame, text=".pez", variable=self.compress_format, value="pez")
        self.comp_pez_radio.pack(side=tk.LEFT, padx=5)
        self.compress_format_radios = [self.comp_zip_radio, self.comp_pez_radio]

        self.rename_check = ttk.Checkbutton(settings_frame, text="统一重命名文件（音频、图片、谱子JSON改为同名，仅文件夹输入时有效）", variable=self.rename_files, command=self._toggle_rename)
        self.rename_check.pack(anchor=tk.W, pady=(2, 0))

        rename_name_frame = ttk.Frame(settings_frame)
        rename_name_frame.pack(fill=tk.X, pady=2)

        ttk.Label(rename_name_frame, text="重命名名称:").pack(side=tk.LEFT)
        self.rename_name_entry = ttk.Entry(rename_name_frame, textvariable=self.rename_name, state="disabled")
        self.rename_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        output_frame = ttk.LabelFrame(main_frame, text="4. 输出位置", padding="5")
        output_frame.pack(fill=tk.X, pady=5)

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.output_btn = ttk.Button(output_frame, text="浏览", command=self._browse_output)
        self.output_btn.pack(side=tk.RIGHT)

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=5)

        self.progress_label = ttk.Label(progress_frame, text="就绪")
        self.progress_label.pack(side=tk.TOP, anchor=tk.W)

        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=2)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        ttk.Button(button_frame, text="生成", command=self._generate).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清空", command=self._clear).pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = tk.Text(log_frame, height=6, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        self.copyright_label = tk.Label(self.root, text="© 2026 青雨", font=("微软雅黑", 9), fg="#666666")
        self.copyright_label.place(relx=0, rely=1.0, anchor='sw', x=10, y=-3)

        self.root.update_idletasks()
        min_w = self.root.winfo_width()
        min_h = self.root.winfo_height() + 10
        self.root.minsize(min_w, min_h)

        self._toggle_input_mode()

    def _browse_input(self):
        if self.input_mode.get() == "archive":
            filetypes = [
                ("PEZ/ZIP压缩包", "*.pez *.zip")
            ]
            path = filedialog.askopenfilename(filetypes=filetypes)
        else:
            path = filedialog.askdirectory()
        if path:
            self.input_path.set(path)

    def _toggle_input_mode(self):
        is_archive = (self.input_mode.get() == "archive")
        
        # 压缩输出只在文件夹模式下可用
        compress_state = "disabled" if is_archive else "normal"
        self.compress_check.config(state=compress_state)
        for radio in self.compress_format_radios:
            radio.config(state=compress_state)
        
        # 重命名功能在两种模式下都可用
        self.rename_check.config(state="normal")
        self.rename_name_entry.config(state="normal")
            
        # 确保视频选择按钮始终可用（无论输入是文件夹还是压缩包，都需要视频背景）
        self.video_btn.config(state="normal")
        
        if is_archive:
            self.compress_enabled.set(False)
        
        self._toggle_compress()
        self._toggle_rename()

    def _browse_video(self):
        filetypes = [("视频文件", "*.mp4 *.mkv *.avi *.webm")]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.video_path.set(path)

    def _browse_copy_dest(self):
        path = filedialog.askdirectory()
        if path:
            self.copy_dest.set(path)
            if self.copy_mode.get():
                self.output_path.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_path.set(path)

    def _toggle_copy_mode(self):
        state = "normal" if self.copy_mode.get() else "disabled"
        self.copy_dest_entry.config(state=state)
        self.copy_dest_btn.config(state=state)
        if self.copy_mode.get():
            self.output_path.set(self.copy_dest.get())
            self.output_entry.config(state="disabled")
            self.output_btn.config(state="disabled")
        else:
            self.output_path.set("")
            self.output_entry.config(state="normal")
            self.output_btn.config(state="normal")

    def _toggle_rename(self):
        state = "normal" if self.rename_files.get() else "disabled"
        self.rename_name_entry.config(state=state)

    def _toggle_compress(self):
        state = "normal" if self.compress_enabled.get() else "disabled"
        for radio in self.compress_format_radios:
            radio.config(state=state)

    def _log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear(self):
        self.input_path.set("")
        self.video_path.set("")
        self.output_path.set("")
        self.copy_mode.set(False)
        self.copy_dest.set("")
        self.copy_dest_entry.config(state="disabled")
        self.copy_dest_btn.config(state="disabled")
        self.compress_enabled.set(False)
        self.compress_format.set("zip")
        for radio in self.compress_format_radios:
            radio.config(state="disabled")
        self.rename_files.set(False)
        self.rename_name.set("")
        self.rename_name_entry.config(state="disabled")
        self.output_entry.config(state="normal")
        self.output_btn.config(state="normal")
        self.progress_label.config(text="就绪")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.video_entry.config(state="normal")
        self.video_btn.config(state="normal")

    def _generate(self):
        input_path = self.input_path.get()
        video_path = self.video_path.get()
        output_path = self.output_path.get()
        copy_mode = self.copy_mode.get()
        copy_dest = self.copy_dest.get()
        compress_enabled = self.compress_enabled.get()
        compress_format = self.compress_format.get()
        rename_files = self.rename_files.get()
        input_mode = self.input_mode.get()

        if not input_path:
            messagebox.showerror("错误", "请选择谱子文件夹或压缩包")
            return
        
        is_archive = (input_mode == "archive")
        
        if not is_archive and not video_path:
            messagebox.showerror("错误", "请选择视频背景文件")
            return
        if copy_mode and not copy_dest:
            messagebox.showerror("错误", "请选择复制目标位置")
            return

        if not copy_mode and not is_archive and not output_path:
            messagebox.showerror("错误", "请选择输出位置或启用复制模式")
            return

        is_valid, validate_msg = self.plugin.validate_rpe_format(input_path)
        if not is_valid:
            self._log(f"验证失败: {validate_msg}")
            messagebox.showerror("格式错误", f"文件格式不符合Re:PhiEdit (RPE)规范，请重新添加符合要求的谱子文件\n\n{validate_msg}")
            return
        else:
            if validate_msg and validate_msg != "验证通过":
                self._log(f"验证通过(有警告): {validate_msg}")
            else:
                self._log("RPE格式验证通过")

        self.progress_label.config(text="正在处理...")
        self.progress_bar.start()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

        def progress_callback(message):
            self.root.after(0, lambda: self._log(message))
            self.root.after(0, lambda: self.progress_label.config(text=message))

        def run():
            success, message = self.plugin.process(
                input_path, video_path,
                output_path if output_path else None,
                copy_mode, copy_dest,
                compress_enabled, compress_format, rename_files, self.rename_name.get(),
                progress_callback
            )
            self.root.after(0, self.progress_bar.stop)
            if success:
                self.root.after(0, lambda: self.progress_label.config(text="处理完成！"))
                self.root.after(0, lambda: self._log(f"成功: {message}"))
                self.root.after(0, lambda: messagebox.showinfo("成功", message))
            else:
                self.root.after(0, lambda: self.progress_label.config(text="处理失败！"))
                self.root.after(0, lambda: self._log(f"错误: {message}"))
                self.root.after(0, lambda: messagebox.showerror("错误", message))

        import threading
        threading.Thread(target=run, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = PhiraVideoBgGUI()
    app.run()
