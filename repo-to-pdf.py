#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
import yaml
import shutil
import tempfile
import logging
import git
from datetime import datetime
import markdown
from bs4 import BeautifulSoup
import hashlib
import re
import requests
from urllib.parse import urlparse
from tqdm import tqdm

# 动态设置 Cairo 库路径（仅 macOS 需要）
if os.uname().sysname == 'Darwin':
    # 检查常见的 Homebrew 安装路径
    homebrew_paths = ['/opt/homebrew/lib', '/usr/local/lib']
    for path in homebrew_paths:
        if os.path.exists(path):
            os.environ['DYLD_LIBRARY_PATH'] = f"{path}:" + os.environ.get('DYLD_LIBRARY_PATH', '')
            break

# 获取主日志记录器
logger = logging.getLogger(__name__)

# 设置 git 模块的日志级别为 WARNING，抑制调试信息
logging.getLogger('git').setLevel(logging.WARNING)
logging.getLogger('git.cmd').setLevel(logging.WARNING)
logging.getLogger('git.util').setLevel(logging.WARNING)

def get_device_presets():
    """获取设备预设配置"""
    return {
        'desktop': {
            'description': '桌面端阅读优化',
            'template': 'default',
            'pdf_overrides': {
                'margin': 'margin=1in',
                'fontsize': '10pt',
                'code_fontsize': '\\small',
                'linespread': '1.0'
            }
        },
        'kindle7': {
            'description': '7英寸Kindle设备优化',
            'template': 'kindle',
            'pdf_overrides': {
                'margin': 'margin=0.4in',
                'fontsize': '11pt',  # 按专家建议使用11pt正文字体
                'code_fontsize': '\\small',  # 在11pt文档中\small约为10pt
                'linespread': '1.0',  # 标准行间距
                'parskip': '5pt',  # 适当的段落间距
                'max_file_size': '200KB',
                'max_line_length': 60
            }
        },
        'tablet': {
            'description': '平板设备阅读优化',
            'template': 'technical',
            'pdf_overrides': {
                'margin': 'margin=0.6in',
                'fontsize': '9pt',
                'code_fontsize': '\\small',
                'linespread': '0.95'
            }
        },
        'mobile': {
            'description': '手机端阅读优化',
            'template': 'kindle',
            'pdf_overrides': {
                'margin': 'margin=0.3in',
                'fontsize': '7pt',
                'code_fontsize': '\\tiny',
                'linespread': '0.85',
                'parskip': '2pt'
            }
        }
    }

def get_system_fonts():
    """动态检测系统可用的字体"""
    system = os.uname().sysname
    
    # 默认字体配置
    default_fonts = {
        'Darwin': {  # macOS
            'main_font': 'Songti SC',
            'sans_font': 'PingFang SC',
            'mono_font': 'SF Mono',
            'fallback_fonts': ['STSong', 'Hiragino Sans GB', 'Arial Unicode MS'],
            # 常见的可用 emoji 字体（按优先级，优先选择黑白字体以保证 XeLaTeX 稳定渲染）
            'emoji_fonts': [
                'Noto Emoji',
                'Noto Color Emoji',
                'Segoe UI Emoji',
                'Apple Color Emoji',
                
            ]
        },
        'Linux': {
            'main_font': 'Noto Serif CJK SC',
            'sans_font': 'Noto Sans CJK SC',
            'mono_font': 'DejaVu Sans Mono',
            'fallback_fonts': ['WenQuanYi Micro Hei', 'AR PL UMing CN', 'SimSun'],
            'emoji_fonts': [
                'Noto Emoji',
                'Noto Color Emoji',
                'Twitter Color Emoji',
                'EmojiOne Color',
                
            ]
        },
        'Windows': {
            'main_font': 'SimSun',
            'sans_font': 'Microsoft YaHei',
            'mono_font': 'Consolas',
            'fallback_fonts': ['KaiTi', 'FangSong'],
            'emoji_fonts': [
                'Noto Emoji',
                'Noto Color Emoji',
                'Segoe UI Emoji',
                
            ]
        }
    }
    
    fonts = default_fonts.get(system, default_fonts['Linux'])
    
    # 尝试检测实际可用的字体
    try:
        # 使用 fc-list 命令检测字体（仅 Linux）。macOS 上保持默认以避免不稳定回退。
        if system in ['Linux']:
            result = subprocess.run(['fc-list', ':lang=zh', 'family'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                available_fonts = set(result.stdout.strip().split('\n'))
                logger.debug(f"Available Chinese fonts: {available_fonts}")
                
                # 检查默认字体是否可用
                for font_type in ['main_font', 'sans_font']:
                    if fonts[font_type] not in available_fonts:
                        # 尝试使用备选字体
                        for fallback in fonts['fallback_fonts']:
                            if fallback in available_fonts:
                                fonts[font_type] = fallback
                                logger.info(f"Using fallback font {fallback} for {font_type}")
                                break
    except Exception as e:
        logger.debug(f"Could not detect system fonts: {e}")
    
    # 如果没有提供 emoji_fonts（理论上不会发生），提供一个兜底值
    if 'emoji_fonts' not in fonts:
        fonts['emoji_fonts'] = ['Noto Color Emoji', 'Noto Emoji', 'Segoe UI Emoji', 'Apple Color Emoji']

    return fonts

class GitRepoManager:
    def __init__(self, repo_url: str, branch: str = 'main'):
        self.repo_url = repo_url
        self.branch = branch
        self.repo_dir = None
        
        # 设置 Git 环境变量，避免不必要的检查
        if os.uname().sysname == 'Darwin':  # macOS
            os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = '/usr/bin/git'
            os.environ['GIT_PYTHON_REFRESH'] = 'quiet'
        
    def clone_or_pull(self, workspace_dir: Path) -> Path:
        """克隆或更新仓库"""
        # 使用 urlparse 安全解析 URL
        parsed_url = urlparse(self.repo_url)
        if parsed_url.scheme in ['http', 'https']:
            # 处理 HTTP(S) URL
            path_parts = parsed_url.path.strip('/').split('/')
            if len(path_parts) >= 2:
                repo_name = path_parts[-1].replace('.git', '')
            else:
                repo_name = 'unknown_repo'
        elif '@' in self.repo_url and ':' in self.repo_url:
            # 处理 SSH URL (git@github.com:user/repo.git)
            repo_part = self.repo_url.split(':')[-1]
            repo_name = repo_part.split('/')[-1].replace('.git', '')
        else:
            # 其他格式，使用原来的方法作为后备
            repo_name = self.repo_url.split('/')[-1].replace('.git', '')
        
        self.repo_dir = workspace_dir / repo_name
        
        try:
            if self.repo_dir.exists():
                logger.info(f"Repository exists, pulling latest changes from {self.branch}")
                repo = git.Repo(self.repo_dir)
                # 确保远程分支存在
                if not repo.remotes:
                    repo.create_remote('origin', self.repo_url)
                origin = repo.remotes.origin
                # 获取最新的远程分支信息
                origin.fetch()
                # 重置到远程分支的最新状态
                repo.git.reset('--hard', f'origin/{self.branch}')
            else:
                logger.info(f"Cloning repository from {self.repo_url}")
                # 使用官方推荐的克隆参数
                git.Repo.clone_from(
                    url=self.repo_url,
                    to_path=self.repo_dir,
                    branch=self.branch,
                    depth=1,  # 浅克隆
                    single_branch=True,  # 单分支
                    filter='blob:none'  # 不下载大文件，只获取文件树
                )
                
            return self.repo_dir
            
        except git.GitCommandError as e:
            logger.error(f"Git operation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during git operation: {str(e)}")
            raise

class RepoPDFConverter:
    def __init__(self, config_path: Path, template_name: str = None):
        self.project_root = config_path.parent.absolute()
        self.config = self._load_config(config_path)
        self.temp_dir = None
        self.template = None
        
        # 处理设备预设
        self._apply_device_preset()
        
        # 加载模板（如果指定）
        if template_name:
            self.template = self._load_template(template_name)
        # 如果没有指定模板，检查是否有设备预设指定的模板
        elif hasattr(self, 'device_preset_template'):
            self.template = self._load_template(self.device_preset_template)
        
        # 确保所有路径都相对于项目根目录
        self.workspace_dir = self.project_root / self.config['workspace_dir']
        # 缓存表情图片路径（sequence -> png path）
        self._emoji_cache = {}
        self.output_dir = self.project_root / self.config['output_dir']

        # 通用 PDF 相关开关（带默认值）
        pdf_cfg = self.config.get('pdf_settings', {})
        self.render_header_comments_outside_code = pdf_cfg.get('render_header_comments_outside_code', True)
        self.code_block_strategy = pdf_cfg.get('code_block_strategy', 'normal')
        # 控制极端长行的强制折行阈值
        try:
            self.max_line_length = int(pdf_cfg.get('max_line_length', 200))
        except Exception:
            self.max_line_length = 200
        # Emoji 下载与缓存
        self.emoji_download = bool(pdf_cfg.get('emoji_download', True))
        
        # 创建必要的目录
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 支持的图片格式
        self.image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.svgz'}
        
        # 支持的代码文件扩展名和对应的语言
        self.code_extensions = {
            # 前端相关
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.vue': 'javascript',
            '.svelte': 'javascript',
            '.css': 'css',
            '.scss': 'css',
            '.sass': 'css',
            '.less': 'css',
            '.html': 'html',
            '.json': 'javascript',
            '.graphql': 'graphql',
            '.gql': 'graphql',
            
            # 后端相关
            '.py': 'python',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.cs': 'csharp',
            
            # 配置和脚本
            '.sh': 'bash',
            '.bash': 'bash',
            '.zsh': 'bash',
            '.sql': 'sql',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.toml': 'toml',
            '.xml': 'xml',
            '.md': 'markdown',
            '.mdx': 'mdx',
        }
        
        # 初始化 Markdown 转换器
        self.md = markdown.Markdown(extensions=['fenced_code', 'tables'])
        
    def _load_config(self, config_path: Path) -> dict:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _apply_device_preset(self):
        """应用设备预设配置"""
        # 优先使用环境变量，然后是配置文件中的设置
        device_preset = os.environ.get('DEVICE') or self.config.get('device_preset', 'desktop')
        
        # 获取预设配置
        device_presets = get_device_presets()
        config_presets = self.config.get('device_presets', {})
        
        # 合并代码中的预设和配置文件中的预设
        all_presets = {**device_presets, **config_presets}
        
        if device_preset in all_presets:
            preset_config = all_presets[device_preset]
            logger.info(f"Applying device preset: {device_preset} - {preset_config.get('description', '')}")
            
            # 保存模板名称供后续使用
            if 'template' in preset_config:
                self.device_preset_template = preset_config['template']
            
            # 应用PDF设置覆盖
            if 'pdf_overrides' in preset_config:
                pdf_settings = self.config.setdefault('pdf_settings', {})
                for key, value in preset_config['pdf_overrides'].items():
                    pdf_settings[key] = value
                    logger.debug(f"Applied preset override: {key}={value}")
        else:
            logger.warning(f"Unknown device preset: {device_preset}, using default settings")
    
    def _load_template(self, template_name: str) -> dict:
        """加载模板文件"""
        template_path = self.project_root / 'templates' / f'{template_name}.yaml'
        if not template_path.exists():
            logger.warning(f"Template {template_name} not found, using default settings")
            return None
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template = yaml.safe_load(f)
            logger.info(f"Loaded template: {template.get('name', template_name)}")
            return template
            
    def create_temp_markdown(self):
        """创建临时目录并准备 Markdown 文件"""
        # 在项目根目录下创建 temp_conversion_files 目录
        self.temp_dir = self.project_root / 'temp_conversion_files'
        # 如果目录已存在，先清空它
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建 images 子目录
        images_dir = self.temp_dir / "images"
        images_dir.mkdir(exist_ok=True)
        
        logger.info(f"Created temporary directory: {self.temp_dir}")
        temp_md = self.temp_dir / "combined_output.md"
        # 创建空文件
        temp_md.touch()
        return temp_md

    def convert_svg_to_png(self, svg_content: str, output_path: Path) -> bool:
        """将 SVG 内容转换为 PNG 文件"""
        try:
            import cairosvg
            from xml.etree import ElementTree as ET
            from io import BytesIO
            
            # 移除 XML 声明
            svg_content = svg_content.replace('<?xml version="1.0" encoding="UTF-8"?>', '')
            svg_content = svg_content.replace('<?xml version="1.0"?>', '')
            
            logger.debug(f"处理 SVG 内容: {svg_content[:200]}...")  # 打印前200个字符用于调试
            
            # 检查是否是图标定义文件
            if '<symbol' in svg_content or '<defs>' in svg_content:
                logger.debug("跳过图标定义 SVG 文件")
                return False
            
            # 解析 SVG 内容
            tree = ET.fromstring(svg_content)
            
            # 获取或设置 SVG 尺寸
            width = tree.get('width', '').strip()
            height = tree.get('height', '').strip()
            viewBox = tree.get('viewBox', '').strip()
            
            logger.debug(f"原始尺寸 - 宽度: {width}, 高度: {height}, viewBox: {viewBox}")
            
            # 检查尺寸是否为 0
            try:
                if width and float(width.replace('px', '').strip()) == 0:
                    logger.debug("跳过宽度为 0 的 SVG")
                    return False
                if height and float(height.replace('px', '').strip()) == 0:
                    logger.debug("跳过高度为 0 的 SVG")
                    return False
            except ValueError:
                pass  # 忽略无法转换为数字的值
            
            # 如果有 viewBox 但没有宽高，从 viewBox 提取
            if viewBox and not (width and height):
                try:
                    vb_parts = viewBox.split()
                    if len(vb_parts) == 4:
                        _, _, vb_width, vb_height = vb_parts
                        # 检查 viewBox 尺寸是否为 0
                        if float(vb_width) == 0 or float(vb_height) == 0:
                            logger.debug("跳过 viewBox 尺寸为 0 的 SVG")
                            return False
                        tree.set('width', vb_width + 'px')
                        tree.set('height', vb_height + 'px')
                        logger.debug(f"从 viewBox 提取尺寸 - 宽度: {vb_width}px, 高度: {vb_height}px")
                except Exception as e:
                    logger.debug(f"从 viewBox 提取尺寸失败: {e}")
            
            # 如果仍然没有尺寸信息，添加默认尺寸
            width = tree.get('width', '').strip()
            height = tree.get('height', '').strip()
            if not (width and height):
                # 设置默认尺寸为 800x600
                tree.set('width', '800px')
                tree.set('height', '600px')
                logger.debug("使用默认尺寸 800x600px")
            
            # 确保单位
            for dim in ['width', 'height']:
                value = tree.get(dim, '')
                if value and not any(unit in value.lower() for unit in ['px', 'pt', 'cm', 'mm', 'in']):
                    tree.set(dim, value + 'px')
                    logger.debug(f"添加像素单位到 {dim}: {value}px")
            
            # 重新生成 SVG 内容
            svg_content = ET.tostring(tree, encoding='unicode')
            logger.debug(f"最终 SVG 尺寸 - 宽度: {tree.get('width')}, 高度: {tree.get('height')}")
            
            # 转换为 PNG，设置合适的输出尺寸
            cairosvg.svg2png(
                bytestring=svg_content.encode('utf-8'),
                write_to=str(output_path),
                parent_width=1600,  # 设置父容器宽度
                parent_height=1200,  # 设置父容器高度
                scale=2.0  # 设置缩放比例以提高清晰度
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to convert SVG to PNG using cairosvg: {e}")
            try:
                # 尝试使用 Inkscape 作为备选方案
                inkscape_cmd = ['inkscape', 
                              '--export-type=png',
                              '--export-filename=' + str(output_path),
                              '--export-width=1600']
                
                # 将 SVG 内容写入临时文件
                temp_svg = output_path.parent / f"temp_{output_path.stem}.svg"
                with open(temp_svg, 'w', encoding='utf-8') as f:
                    f.write(svg_content)
                
                # 运行 Inkscape 命令
                result = subprocess.run([*inkscape_cmd, str(temp_svg)], 
                                     capture_output=True, 
                                     text=True)
                
                # 删除临时文件
                temp_svg.unlink()
                
                if result.returncode == 0 and output_path.exists():
                    return True
                    
                logger.warning(f"Inkscape conversion failed: {result.stderr}")
            except Exception as e2:
                logger.warning(f"Backup SVG conversion also failed: {e2}")
            return False

    def _convert_image_to_png(self, path: str) -> str:
        """转换图片为 PNG 格式"""
        try:
            # 创建 images 目录
            images_dir = self.temp_dir / "images"
            images_dir.mkdir(exist_ok=True)
            
            # 处理相对路径和绝对路径
            img_path = Path(path)
            if not img_path.is_absolute():
                img_path = self.project_root / path
                
            if not img_path.exists():
                return path  # 如果文件不存在，返回原路径
                
            if path.lower().endswith('.svg'):
                # SVG 转 PNG 的处理
                with open(img_path, 'r', encoding='utf-8') as f:
                    svg_content = f.read()
                
                hash_name = hashlib.md5(svg_content.encode()).hexdigest()
                png_path = images_dir / f"{hash_name}.png"
                
                if png_path.exists():
                    return f"images/{png_path.name}"
                    
                if self.convert_svg_to_png(svg_content, png_path):
                    return f"images/{png_path.name}"
                    
            return path
        except Exception as e:
            logger.warning(f"Failed to convert image {path}: {e}")
            return path

    def _is_valid_svg(self, content: str) -> bool:
        """检查是否是有效的 SVG 内容"""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            svg = soup.find('svg')
            return svg is not None and (svg.get('width') or svg.get('height') or svg.get('viewBox'))
        except:
            return False

    def _convert_svg_content_to_png(self, svg_content: str) -> str:
        """将 SVG 内容转换为 PNG"""
        try:
            images_dir = self.temp_dir / "images"
            images_dir.mkdir(exist_ok=True)
            
            hash_name = hashlib.md5(svg_content.encode()).hexdigest()
            png_path = images_dir / f"{hash_name}.png"
            
            if png_path.exists():
                return png_path.name
                
            if self.convert_svg_to_png(svg_content, png_path):
                return png_path.name
                
            return ""
        except Exception as e:
            logger.warning(f"Failed to convert SVG content to PNG: {e}")
            return ""

    def _download_remote_image(self, url: str, images_dir: Path) -> str:
        """下载远程图片到本地"""
        try:
            # 创建 images 目录
            images_dir.mkdir(exist_ok=True)
            
            # 生成文件名基础部分（不带扩展名）
            hash_name = hashlib.md5(url.encode()).hexdigest()
            
            # 下载图片
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 从 Content-Type 获取实际格式
            content_type = response.headers.get('Content-Type', '').lower()
            if 'svg' in content_type or url.lower().endswith('.svg'):
                # 如果是 SVG，转换为 PNG
                png_path = images_dir / f"{hash_name}.png"
                if png_path.exists():
                    return f"images/{png_path.name}"
                
                # 保存 SVG 内容
                if self.convert_svg_to_png(response.text, png_path):
                    return f"images/{png_path.name}"
            else:
                # 对于其他格式，从 URL 或 Content-Type 确定扩展名
                if 'image/png' in content_type:
                    ext = '.png'
                elif 'image/jpeg' in content_type:
                    ext = '.jpg'
                elif 'image/gif' in content_type:
                    ext = '.gif'
                else:
                    # 从 URL 获取扩展名
                    ext = os.path.splitext(url)[1]
                    if not ext:
                        ext = '.png'  # 默认使用 .png
                
                local_path = images_dir / f"{hash_name}{ext}"
                if local_path.exists():
                    return f"images/{local_path.name}"
                
                # 保存图片
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                
                return f"images/{local_path.name}"
                
            return ""
        except Exception as e:
            logger.warning(f"Failed to download remote image {url}: {e}")
            return ""

    def process_markdown(self, content: str) -> str:
        """处理 Markdown 内容，处理图片和 SVG"""
        # 1. 处理代码块的 title 属性
        content = re.sub(r'```(\w+)\s+title="([^"]+)"', r'```\1', content)
        
        # 2. 收集引用式链接定义
        reference_links = {}
        for match in re.finditer(r'^\[(.*?)\]:\s*(\S+)(?:\s+"(.*?)")?$', content, re.MULTILINE):
            ref_id, url, title = match.groups()
            reference_links[ref_id] = {'url': url, 'title': title}
        
        # 3. 处理引用式图片链接
        def process_ref_image(match):
            alt = match.group(1) or ''
            ref_id = match.group(2)
            
            if ref_id in reference_links:
                ref = reference_links[ref_id]
                url = ref['url']
                title = ref['title']
                
                # 处理远程图片
                if url.startswith(('http://', 'https://')):
                    images_dir = self.temp_dir / "images"
                    new_path = self._download_remote_image(url, images_dir)
                    if new_path:
                        if title:
                            return f'![{alt}]({new_path} "{title}")'
                        return f'![{alt}]({new_path})'
                    return ''
                
                # 处理本地 SVG
                if url.lower().endswith('.svg'):
                    new_path = self._convert_image_to_png(url)
                    if title:
                        return f'![{alt}]({new_path} "{title}")'
                    return f'![{alt}]({new_path})'
                
                # 其他情况保持原样
                if title:
                    return f'![{alt}]({url} "{title}")'
                return f'![{alt}]({url})'
            return match.group(0)
        
        # 处理引用式图片链接
        content = re.sub(r'!\[(.*?)\]\[(.*?)\]', process_ref_image, content)
        
        # 4. 处理普通图片语法
        def process_md_image(match):
            alt = match.group(1) or ''
            path = match.group(2)
            title = match.group(3) or '' if len(match.groups()) > 2 else ''
            
            # 处理远程图片（包括动态徽章）
            if path.startswith(('http://', 'https://')):
                images_dir = self.temp_dir / "images"
                new_path = self._download_remote_image(path, images_dir)
                if new_path:
                    if title:
                        return f'![{alt}]({new_path} "{title}")'
                    return f'![{alt}]({new_path})'
                return ''  # 如果下载失败，移除图片引用
            
            # 处理本地 SVG
            if path.lower().endswith('.svg'):
                new_path = self._convert_image_to_png(path)
                if title:
                    return f'![{alt}]({new_path} "{title}")'
                return f'![{alt}]({new_path})'
            return match.group(0)
        
        # 处理带 title 的图片
        content = re.sub(r'!\[(.*?)\]\((.*?)\s+"(.*?)"\)', process_md_image, content)
        # 处理不带 title 的图片
        content = re.sub(r'!\[(.*?)\]\((.*?)\)', process_md_image, content)
        
        # 5. 处理 HTML 图片标签
        def process_html_image(match):
            tag = match.group(0)
            soup = BeautifulSoup(tag, 'html.parser')
            img = soup.find('img')
            if not img:
                return tag
                
            src = img.get('src', '')
            if src.lower().endswith('.svg'):
                new_src = self._convert_image_to_png(src)
                img['src'] = new_src
                return str(img)
            return tag
        
        # 匹配 HTML img 标签，考虑单引号和双引号
        content = re.sub(r'<img\s+[^>]+>', process_html_image, content, flags=re.IGNORECASE)
        
        # 6. 处理内嵌 SVG
        def process_svg(match):
            svg_content = match.group(0)
            if self._is_valid_svg(svg_content):
                png_path = self._convert_svg_content_to_png(svg_content)
                if png_path:
                    return f'![](images/{png_path})'
            return match.group(0)
        
        # 匹配内嵌的 SVG 标签
        content = re.sub(r'<svg\s*.*?>.*?</svg>', process_svg, content, flags=re.DOTALL | re.IGNORECASE)
        
        # 7. 转义非代码区域中的 \UXXXX 与 \uXXXX 序列，避免被 LaTeX 识别为控制序列
        def escape_backslash_u_outside_code(md: str) -> str:
            import re
            lines = md.splitlines()
            out = []
            in_code = False
            fence = None
            for ln in lines:
                if not in_code:
                    m = re.match(r"^(?P<fence>```+)(?P<info>.*)$", ln)
                    if m:
                        in_code = True
                        fence = m.group('fence')
                        out.append(ln)
                        continue
                    # 转义 \UXXXXXXXX 或 \uXXXX
                    ln = re.sub(r"\\U([0-9A-Fa-f]{8})", r"\\textbackslash{}U\\1", ln)
                    ln = re.sub(r"\\u([0-9A-Fa-f]{4})", r"\\textbackslash{}u\\1", ln)
                    out.append(ln)
                else:
                    out.append(ln)
                    if ln.startswith(fence):
                        in_code = False
                        fence = None
            return '\n'.join(out)

        content = escape_backslash_u_outside_code(content)

        # 8. 对 Markdown 中的 fenced code blocks 执行硬折行，防止 Verbatim 溢出
        def hard_wrap_md_code_blocks(md: str) -> str:
            import re
            lines = md.splitlines()
            out = []
            in_code = False
            fence = None
            hard_wrap_threshold = max(40, int(self.config.get('pdf_settings', {}).get('max_line_length', 200)))
            wrap_width = max(40, min(160, int(hard_wrap_threshold * 0.75)))
            for ln in lines:
                if not in_code:
                    m = re.match(r"^(?P<fence>```+)(?P<info>.*)$", ln)
                    if m:
                        info = (m.group('info') or '').strip().lower()
                        fence = m.group('fence')
                        in_code = True
                        out.append(ln)
                        # 跳过我们注入的原生 LaTeX 代码块，不修改其中内容
                        skip_block = ('{=latex}' in info) or (info == 'latex')
                        if skip_block:
                            # 标记特殊状态：in_code 仍为 True，但不做折行
                            fence = fence + '|SKIP'
                        continue
                    out.append(ln)
                else:
                    # 结束 fenced block
                    if ln.startswith((fence if 'SKIP' not in fence else fence.split('|')[0])):
                        in_code = False
                        out.append(ln)
                        fence = None
                        continue
                    # 对普通 fenced code 行做硬折行
                    if 'SKIP' in fence:
                        out.append(ln)
                    else:
                        if len(ln) > hard_wrap_threshold:
                            out.append('\n'.join(ln[i:i+wrap_width] for i in range(0, len(ln), wrap_width)))
                        else:
                            out.append(ln)
            return '\n'.join(out)

        content = hard_wrap_md_code_blocks(content)

        return content

    def _clean_text(self, text: str) -> str:
        """清理文本内容，保持原始格式"""
        # 禁用 raw_tex 后，不需要转义反斜杠
        # pandoc 会正确处理代码块中的特殊字符
        return text

    def process_file(self, file_path: Path, repo_root: Path) -> str:
        """处理单个文件，返回对应的 Markdown 内容"""
        import re

        ext = file_path.suffix.lower()
        rel_path = file_path.relative_to(repo_root)
        
        # 内置的忽略扩展名
        ignored_extensions = {'.pyc', '.pyo', '.pyd', '.so', '.dylib', '.dll', '.class', '.o', '.obj'}
        if ext in ignored_extensions:
            return ""
        
        # 添加对.cursorrules文件的特殊处理
        if file_path.name == '.cursorrules':
            # 检查文件大小
            file_size = file_path.stat().st_size / (1024 * 1024)
            if file_size > 1:
                logger.debug(f"跳过大文件 ({file_size:.1f}MB): {file_path}")
                return ""
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = self._clean_text(f.read().strip())
                # 简化处理，统一使用markdown格式化
                return f"\n\n# {rel_path}\n\n`````markdown\n{content}\n`````\n\n"
            except UnicodeDecodeError:
                logger.debug(f"跳过无法解码的文件: {file_path}")
                return ""
        
        # 检查是否在忽略列表中
        if any(ignore in str(rel_path) for ignore in self.config.get('ignores', [])):
            return ""
            
        # 创建临时目录下的 images 目录
        # 确保 temp_dir 存在
        if not self.temp_dir:
            self.temp_dir = self.project_root / "temp_conversion_files"
            self.temp_dir.mkdir(exist_ok=True)
            
        images_dir = self.temp_dir / "images"
        images_dir.mkdir(exist_ok=True)
            
        # 处理图片文件
        if ext.lower() in self.image_extensions:
            try:
                if ext.lower() in {'.svg', '.svgz'}:
                    # 处理 SVG 文件
                    new_path = self._convert_image_to_png(str(file_path))
                    if not new_path:
                        return ""
                else:
                    # 处理其他图片文件
                    target_path = images_dir / file_path.name
                    shutil.copy2(file_path, target_path)
            except Exception as e:
                logger.warning(f"Failed to process image {file_path}: {e}")
            return ""
            
        try:
            # 获取文件大小（MB）
            file_size = file_path.stat().st_size / (1024 * 1024)
            # 如果文件大于 0.5MB，跳过
            if file_size > 0.5 and ext not in self.image_extensions:
                logger.debug(f"跳过大文件 ({file_size:.1f}MB): {file_path}")
                return ""
            
            # 读取文件内容并清理
            with open(file_path, 'r', encoding='utf-8') as f:
                content = self._clean_text(f.read().strip())
            
            # 如果是 HTML 文件，转换 HTML 为 Markdown（使用 Pandoc 进行转换），以保证数学模式正确处理
            if ext == '.html':
                result = subprocess.run(
                    ["pandoc", "--from=html", "--to=markdown", "--wrap=none"],
                    input=content, text=True, capture_output=True
                )
                markdown_content = result.stdout
                return f"\n\n# {rel_path}\n\n{markdown_content}\n\n"
            
            # 如果是 Markdown 或 MDX 文件，处理图片路径
            if ext in {'.md', '.mdx'}:
                # 处理图片路径
                def process_image_path(match):
                    img_path = match.group(2)
                    if not img_path.startswith(('http://', 'https://')):
                        # 处理绝对路径（以 / 开头）
                        if img_path.startswith('/'):
                            # 去掉开头的斜杠，作为相对于仓库根目录的路径
                            img_path = img_path.lstrip('/')
                        
                        # 尝试多种路径解析方式
                        possible_paths = [
                            # 1. 从当前文件目录解析
                            file_path.parent / img_path,
                            # 2. 从仓库根目录解析
                            repo_root / img_path,
                            # 3. 处理 ../类型的相对路径
                            (file_path.parent / img_path).resolve(),
                            # 4. 处理 ./类型的相对路径
                            (file_path.parent / img_path.lstrip('./')).resolve(),
                            # 5. 如果路径以 docs/ 开头，尝试从仓库根目录解析
                            repo_root / img_path.lstrip('./')
                        ]
                        
                        # 尝试所有可能的路径
                        for abs_img_path in possible_paths:
                            try:
                                if abs_img_path.exists() and abs_img_path.suffix.lower() in self.image_extensions:
                                    # 复制图片到临时目录
                                    target_path = images_dir / abs_img_path.name
                                    shutil.copy2(abs_img_path, target_path)
                                    logger.debug(f"成功处理图片: {abs_img_path} -> {target_path}")
                                    return f"![{match.group(1)}](images/{target_path.name})"
                            except Exception as e:
                                logger.debug(f"尝试路径 {abs_img_path} 失败: {e}")
                                continue
                        
                        logger.warning(f"无法找到图片: {img_path}, 在文件: {file_path}")
                        # 为避免 Pandoc 因缺图失败，移除该图片并保留替代文本
                        alt_text = match.group(1) or ''
                        return alt_text
                    return match.group(0)
                
                # 处理 Markdown 中的图片引用
                content = re.sub(r'!\[(.*?)\]\((.*?)\)', process_image_path, content)
                cleaned_content = self.process_markdown(content)
                
                # 转义独立的 --- 行，避免被 pandoc 解释为 YAML 分隔符
                cleaned_content = re.sub(r'^---$', '\\---', cleaned_content, flags=re.MULTILINE)
                
                # 如果是 MDX 文件，使用 MDX 语法高亮
                if ext == '.mdx':
                    return f"\n\n# {rel_path}\n\n`````mdx\n{cleaned_content}\n`````\n\n"
                return f"\n\n# {rel_path}\n\n{cleaned_content}\n\n"
            
            # 如果是支持的代码文件（排除已处理的 MDX）
            if ext in self.code_extensions and ext != '.mdx':
                # 跳过包含 SVG 的文件
                if '<svg' in content:
                    return ""
                    
                # 对于 package.json 和 package-lock.json 文件不使用高亮
                if file_path.name in ['package.json', 'package-lock.json', 'yarn.lock']:
                    return f"\n\n# {rel_path}\n\n`````\n{content}\n`````\n\n"
                    
                # 对于其他文件使用语言高亮
                lang = self.code_extensions[ext]
                # 1) 可选：提取头部注释为正文（非代码块），避免 emoji 落在代码环境中
                header_md = ""
                code_body = content
                if self.render_header_comments_outside_code:
                    header_text, code_body = self._extract_header_comment(code_body, ext)
                    if header_text:
                        # 将 emoji 转成 PNG，并在正文中用普通 LaTeX 宏插入
                        header_text = self._replace_emoji_with_images(header_text, in_code=False)
                        header_md = header_text.strip() + "\n\n"

                # 2) 处理长字符串，将它们分割成多行
                code_body = self._process_long_lines(code_body)

                # 3) 更激进的长行防御：强制切分超长行
                hard_wrap_threshold = max(40, int(self.max_line_length))
                wrap_width = max(40, min(160, int(self.max_line_length * 0.75)))
                tmp_lines = []
                for _ln in code_body.splitlines():
                    if len(_ln) > hard_wrap_threshold:
                        tmp_lines.append('\n'.join(_ln[i:i+wrap_width] for i in range(0, len(_ln), wrap_width)))
                    else:
                        tmp_lines.append(_ln)
                code_body = '\n'.join(tmp_lines)

                # 4) 将 Emoji 替换为内联图片（仅代码正文）
                code_transformed = self._replace_emoji_with_images(code_body, in_code=True)
                contains_emoji_in_code = '§emojiimg' in code_transformed

                # 如果内容过大，分割成多个部分
                lines = code_transformed.splitlines()
                if len(lines) > 1000:
                    # 检查配置是否启用了智能分割
                    if self.config.get('pdf_settings', {}).get('split_large_files', True):
                        # 写入标题与可能的头注释后，分段输出代码
                        head = f"\n\n# {rel_path}\n\n" + header_md
                        parts = self._process_large_file(rel_path, lines, lang)
                        return head + parts
                    else:
                        # 使用传统的截断方式
                        code_transformed = '\n'.join(lines[:1000]) + '\n\n... (文件太大，已截断)'

                # 5) 输出（根据策略选择 CodeBlock）
                head = f"\n\n# {rel_path}\n\n" + header_md
                if contains_emoji_in_code and self.code_block_strategy in ("codeblock_for_emoji", "normal"):
                    return head + (
                        f"```{{=latex}}\n\\begin{{CodeBlock}}\n{code_transformed}\n\\end{{CodeBlock}}\n```\n\n"
                    )
                else:
                    return head + f"`````{lang}\n{code_transformed}\n`````\n\n"
                
            return ""
        except UnicodeDecodeError:
            logger.debug(f"跳过二进制文件: {file_path}")
            return ""
    
    def _process_long_lines(self, content: str, max_length: int = 80) -> str:
        """处理长行，将它们分割成多行"""
        lines = []
        for line in content.splitlines():
            if len(line) > max_length:
                # 检查是否是数组
                if '[' in line and ']' in line:
                    # 在逗号后添加换行
                    indent = ' ' * (len(line) - len(line.lstrip()))
                    parts = line.split(',')
                    formatted_parts = []
                    current_line = parts[0]
                    
                    for part in parts[1:]:
                        if len(current_line + ',' + part) > max_length:
                            formatted_parts.append(current_line + ',')
                            current_line = indent + part.lstrip()
                        else:
                            current_line += ',' + part
                            
                    formatted_parts.append(current_line)
                    line = '\n'.join(formatted_parts)
                # 对于包含长字符串的行进行特殊处理
                elif '"' in line or "'" in line:
                    line = self._break_long_strings(line)
            lines.append(line)
        return '\n'.join(lines)
        
    def _break_long_strings(self, line: str) -> str:
        """处理包含长字符串的行"""
        import re
        # 查找长字符串（包括包名和版本号）
        pattern = r'["\']([^"\']{100,})["\']'
        
        def replacer(match):
            # 将长字符串每隔 80 个字符添加换行和适当的缩进
            s = match.group(1)
            indent = ' ' * (len(line) - len(line.lstrip()))
            parts = [s[i:i+80] for i in range(0, len(s), 80)]
            if len(parts) > 1:
                quote = match.group(0)[0]  # 获取原始引号
                return f'{quote}\\\n{indent}'.join(parts) + quote
            return match.group(0)
            
        return re.sub(pattern, replacer, line)

    # ========== Emoji 处理 ==========
    def _emoji_regex(self):
        import re
        return re.compile(
            r"([\U0001F300-\U0001FAFF\u2600-\u27BF])"  # 基本 emoji 范围
            r"(\uFE0F)?"                                 # 可选 VS16
            r"(?:\u200D[\U0001F300-\U0001FAFF\u2600-\u27BF](\uFE0F)?)*"  # 可选 ZWJ 序列
        )

    def _ensure_emoji_png(self, seq_full: str) -> str:
        """确保给定 emoji 序列的 PNG 存在，返回相对文件名（位于 temp_conversion_files/images/emoji）。
        可能返回空字符串表示不可用。
        遵循配置：emoji_download（允许下载），多版本回退。
        """
        # 懒创建资源目录
        if not self.temp_dir:
            self.temp_dir = self.project_root / "temp_conversion_files"
            self.temp_dir.mkdir(exist_ok=True)
        emoji_dir = self.temp_dir / "images" / "emoji"
        emoji_dir.mkdir(parents=True, exist_ok=True)

        # 命中内存缓存
        if seq_full in self._emoji_cache:
            return self._emoji_cache[seq_full]

        # 构造候选序列：完整 -> 去 fe0f -> 首码位
        seqs = [seq_full]
        no_fe0f = "-".join(p for p in seq_full.split('-') if p != 'fe0f')
        if no_fe0f not in seqs:
            seqs.append(no_fe0f)
        first = seq_full.split('-')[0]
        if first not in seqs:
            seqs.append(first)

        # 先查缓存文件是否已存在
        for name in seqs:
            candidate = emoji_dir / f"{name}.png"
            if candidate.exists():
                self._emoji_cache[seq_full] = candidate.name
                return candidate.name

        # 不允许下载则直接返回空
        if not self.emoji_download:
            self._emoji_cache[seq_full] = ""
            return ""

        # 允许下载，按版本序列重试
        versions = ["v14.0.2", "v14.0.0", "master"]
        chosen_name = None
        svg_bytes = None
        for ver in versions:
            url_tpl = f"https://raw.githubusercontent.com/twitter/twemoji/{ver}/assets/svg/{{name}}.svg"
            for name in seqs:
                try:
                    resp = requests.get(url_tpl.format(name=name), timeout=10)
                    if resp.status_code == 200 and resp.content:
                        svg_bytes = resp.content
                        chosen_name = name
                        break
                except Exception:
                    continue
            if svg_bytes:
                break

        if not svg_bytes or not chosen_name:
            self._emoji_cache[seq_full] = ""
            return ""

        # 转写为 PNG
        out_name = f"{chosen_name}.png"
        out_path = emoji_dir / out_name
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=svg_bytes, write_to=str(out_path))
            self._emoji_cache[seq_full] = out_name
            return out_name
        except Exception:
            self._emoji_cache[seq_full] = ""
            return ""

    def _replace_emoji_with_images(self, text: str, in_code: bool) -> str:
        """把文本中的 Emoji 替换为 `\emojiimg{...}`（正文）或 `§emojiimg«... »`（代码）并准备好 PNG 资源。"""
        try:
            emoji_re = self._emoji_regex()

            def codepoints_to_seq(s: str) -> str:
                return "-".join(f"{ord(ch):x}" for ch in s)

            def repl(m):
                s = m.group(0)
                seq = codepoints_to_seq(s)
                rel = self._ensure_emoji_png(seq)
                if rel:
                    return (f"§emojiimg«{rel}»" if in_code else f"\\emojiimg{{{rel}}}")
                return s

            return emoji_re.sub(repl, text)
        except Exception:
            return text

    def _replace_emoji_with_images_in_code(self, text: str) -> str:
        # 兼容旧调用
        return self._replace_emoji_with_images(text, in_code=True)

    # ========== 文件头注释抽取 ==========
    def _extract_header_comment(self, content: str, ext: str):
        """抽取文件开头的注释块，返回 (header_text, remaining_code)。
        仅处理典型语言：
        - C 类: // 与 /* */
        - 脚本/配置: #
        - SQL: --
        遇到第一行空行或非注释行即停止抽取。
        """
        lines = content.splitlines()
        if not lines:
            return "", content

        i = 0
        n = len(lines)

        def is_blank(idx):
            return idx < n and lines[idx].strip() == ""

        def starts_with(idx, prefix):
            return idx < n and lines[idx].lstrip().startswith(prefix)

        header_chunks = []

        # 判定注释风格
        c_like_exts = {'.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.go', '.cs', '.php'}
        sharp_exts = {'.py', '.sh', '.bash', '.zsh', '.rb', '.yaml', '.yml', '.toml', '.ini'}
        sql_exts = {'.sql'}

        def strip_line_comment(s, marker):
            # 去掉 marker 及后续一个空格
            t = s.lstrip()
            if t.startswith(marker):
                return t[len(marker):].lstrip()
            return s

        # 仅当第一行就是注释时才开始提取
        if is_blank(0):
            return "", content

        consumed = 0
        if ext in c_like_exts:
            # 处理块注释开头
            if starts_with(0, "/*"):
                buf = []
                line = lines[i].lstrip()
                # 去头
                if line.startswith("/*"):
                    line = line[2:]
                # 读取直到 */
                while i < n:
                    end_pos = line.find("*/")
                    if end_pos != -1:
                        buf.append(line[:end_pos])
                        i += 1
                        break
                    buf.append(line)
                    i += 1
                    if i < n:
                        line = lines[i]
                header_chunks.append("\n".join(buf))
                consumed = i
                # 块注释后，如果下一行是空行则停止；如果仍是 // 连续注释则继续收集直到空行
                while consumed < n and lines[consumed].lstrip().startswith("//"):
                    header_chunks.append(strip_line_comment(lines[consumed], "//"))
                    consumed += 1
                if consumed < n and lines[consumed].strip() == "":
                    i = consumed  # 跳过空行
                else:
                    i = consumed
            elif starts_with(0, "//"):
                while i < n and lines[i].lstrip().startswith("//"):
                    header_chunks.append(strip_line_comment(lines[i], "//"))
                    i += 1
            else:
                return "", content
        elif ext in sharp_exts:
            if lines[0].lstrip().startswith("#"):
                while i < n and lines[i].lstrip().startswith("#"):
                    header_chunks.append(strip_line_comment(lines[i], "#"))
                    i += 1
            else:
                return "", content
        elif ext in sql_exts:
            if lines[0].lstrip().startswith("--"):
                while i < n and lines[i].lstrip().startswith("--"):
                    header_chunks.append(strip_line_comment(lines[i], "--"))
                    i += 1
            else:
                return "", content
        else:
            # 其他语言暂不处理
            return "", content

        # 到空行即止，不包含空行
        if i < n and lines[i].strip() == "":
            i += 1  # 跳过这一空行

        header_text = "\n".join(h.rstrip() for h in header_chunks).strip()
        remaining = "\n".join(lines[i:])
        return header_text, remaining
    
    def _process_large_file(self, rel_path: str, lines: list, lang: str) -> str:
        """处理大文件，将其分割成多个部分"""
        result = []
        total_lines = len(lines)
        chunk_size = 800  # 每个部分的行数
        num_parts = (total_lines + chunk_size - 1) // chunk_size
        
        # 添加文件说明
        result.append(f"\n\n# {rel_path}")
        result.append(f"\n> 注意：此文件包含 {total_lines} 行，已分为 {num_parts} 个部分显示\n")
        
        # 分割文件内容
        for i in range(num_parts):
            start = i * chunk_size
            end = min((i + 1) * chunk_size, total_lines)
            part_content = '\n'.join(lines[start:end])
            
            # 添加部分标题
            result.append(f"\n## {rel_path} - 第 {i+1}/{num_parts} 部分 (行 {start+1}-{end})")
            if '§emojiimg' in part_content:
                result.append("\n```{=latex}\n")
                result.append("\\begin{CodeBlock}\n")
                result.append(part_content)
                result.append("\n\\end{CodeBlock}\n")
                result.append("```\n")
            else:
                result.append(f"\n`````{lang}\n")
                result.append(part_content)
                result.append("\n`````\n")
        
        return ''.join(result)
    
    def generate_directory_tree(self, repo_path: Path, max_depth: int = 3) -> str:
        """生成项目的目录树结构"""
        
        def should_ignore_dir(path: Path) -> bool:
            """检查目录是否应该被忽略"""
            dir_name = path.name
            # 忽略隐藏目录和配置中指定的目录
            if dir_name.startswith('.'):
                return True
            for ignore in self.config.get('ignores', []):
                if ignore.rstrip('/') == dir_name or ignore in str(path):
                    return True
            return False
        
        def build_tree(current_path: Path, prefix: str = "", depth: int = 0) -> list:
            """递归构建目录树"""
            if depth > max_depth:
                return []
            
            items = []
            try:
                # 获取所有子项并排序（目录在前，文件在后）
                entries = sorted(current_path.iterdir(), 
                               key=lambda x: (not x.is_dir(), x.name.lower()))
                
                for i, entry in enumerate(entries):
                    is_last = i == len(entries) - 1
                    
                    # 跳过隐藏文件/目录（除了特定的如 .cursorrules）
                    if entry.name.startswith('.') and entry.name not in ['.cursorrules', '.gitignore']:
                        continue
                    
                    # 构建树形符号
                    if is_last:
                        current_prefix = "└── "
                        extension = "    "
                    else:
                        current_prefix = "├── "
                        extension = "│   "
                    
                    if entry.is_dir():
                        if not should_ignore_dir(entry):
                            items.append(f"{prefix}{current_prefix}{entry.name}/")
                            # 递归处理子目录
                            sub_items = build_tree(entry, prefix + extension, depth + 1)
                            items.extend(sub_items)
                    else:
                        # 检查文件是否应该被忽略
                        if not self._should_ignore(entry):
                            # 获取文件大小
                            size = entry.stat().st_size
                            if size < 1024:
                                size_str = f"{size}B"
                            elif size < 1024 * 1024:
                                size_str = f"{size/1024:.1f}KB"
                            else:
                                size_str = f"{size/(1024*1024):.1f}MB"
                            
                            items.append(f"{prefix}{current_prefix}{entry.name} ({size_str})")
                            
            except PermissionError:
                items.append(f"{prefix}[Permission Denied]")
            
            return items
        
        # 生成目录树
        tree_lines = [f"# 项目结构\n\n```"]
        tree_lines.append(f"{repo_path.name}/")
        tree_lines.extend(build_tree(repo_path))
        tree_lines.append("```\n")
        
        return "\n".join(tree_lines)
    
    def _should_ignore(self, file_path: Path) -> bool:
        """检查文件是否应该被忽略"""
        # 检查文件名和扩展名
        for ignore in self.config.get('ignores', []):
            if ignore in str(file_path) or file_path.name == ignore:
                return True
            # 处理通配符模式
            if '*' in ignore:
                import fnmatch
                if fnmatch.fnmatch(file_path.name, ignore):
                    return True
        return False
    
    def generate_code_stats(self, repo_path: Path) -> str:
        """生成代码统计信息"""
        stats = {
            'total_files': 0,
            'total_lines': 0,
            'total_size': 0,
            'by_language': {},
            'by_extension': {}
        }
        
        # 收集统计信息
        for file_path in repo_path.rglob('*'):
            if file_path.is_file() and not self._should_ignore(file_path):
                stats['total_files'] += 1
                size = file_path.stat().st_size
                stats['total_size'] += size
                
                # 统计扩展名
                ext = file_path.suffix.lower()
                if ext:
                    stats['by_extension'][ext] = stats['by_extension'].get(ext, 0) + 1
                    
                    # 统计语言
                    if ext in self.code_extensions:
                        lang = self.code_extensions[ext]
                        if lang not in stats['by_language']:
                            stats['by_language'][lang] = {'files': 0, 'lines': 0}
                        stats['by_language'][lang]['files'] += 1
                        
                        # 统计行数（仅代码文件）
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = len(f.readlines())
                                stats['total_lines'] += lines
                                stats['by_language'][lang]['lines'] += lines
                        except:
                            pass
        
        # 生成统计报告
        report = ["# 代码统计\n"]
        report.append(f"- 总文件数：{stats['total_files']:,}")
        report.append(f"- 总代码行数：{stats['total_lines']:,}")
        report.append(f"- 总大小：{stats['total_size']/(1024*1024):.2f} MB\n")
        
        if stats['by_language']:
            report.append("## 按语言统计\n")
            report.append("| 语言 | 文件数 | 代码行数 |")
            report.append("|------|--------|----------|")
            for lang, data in sorted(stats['by_language'].items(), 
                                   key=lambda x: x[1]['lines'], reverse=True):
                report.append(f"| {lang} | {data['files']} | {data['lines']:,} |")
            report.append("")
        
        if stats['by_extension']:
            report.append("## 按文件类型统计\n")
            report.append("| 扩展名 | 文件数 |")
            report.append("|--------|--------|")
            for ext, count in sorted(stats['by_extension'].items(), 
                                   key=lambda x: x[1], reverse=True)[:20]:
                report.append(f"| {ext} | {count} |")
            report.append("")
        
        return "\n".join(report)
            
    def _process_long_lines(self, content: str, max_length: int = 80) -> str:
        """处理长行，将它们分割成多行"""
        lines = []
        for line in content.splitlines():
            if len(line) > max_length:
                # 检查是否是数组
                if '[' in line and ']' in line:
                    # 在逗号后添加换行
                    indent = ' ' * (len(line) - len(line.lstrip()))
                    parts = line.split(',')
                    formatted_parts = []
                    current_line = parts[0]
                    
                    for part in parts[1:]:
                        if len(current_line + ',' + part) > max_length:
                            formatted_parts.append(current_line + ',')
                            current_line = indent + part.lstrip()
                        else:
                            current_line += ',' + part
                            
                    formatted_parts.append(current_line)
                    line = '\n'.join(formatted_parts)
                # 对于包含长字符串的行进行特殊处理
                elif '"' in line or "'" in line:
                    line = self._break_long_strings(line)
            lines.append(line)
        return '\n'.join(lines)
        
    def _break_long_strings(self, line: str) -> str:
        """处理包含长字符串的行"""
        import re
        # 查找长字符串（包括包名和版本号）
        pattern = r'["\']([^"\']{100,})["\']'
        
        def replacer(match):
            # 将长字符串每隔 80 个字符添加换行和适当的缩进
            s = match.group(1)
            indent = ' ' * (len(line) - len(line.lstrip()))
            parts = [s[i:i+80] for i in range(0, len(s), 80)]
            if len(parts) > 1:
                quote = match.group(0)[0]  # 获取原始引号
                return f'{quote}\\\n{indent}'.join(parts) + quote
            return match.group(0)
            
        return re.sub(pattern, replacer, line)

    def create_pandoc_yaml(self, repo_name: str) -> Path:
        """创建 Pandoc 的 YAML 配置文件"""
        # 确保 temp_dir 已经创建
        if not self.temp_dir:
            self.temp_dir = self.project_root / "temp_conversion_files"
            self.temp_dir.mkdir(exist_ok=True)
            
        pdf_config = self.config.get('pdf_settings', {})
        
        # 创建一个更简单的 pandoc defaults 文件，避免复杂的 header-includes
        
        # 获取系统字体
        system_fonts = get_system_fonts()
        
        # 优先使用配置文件中的字体，如果没有则使用系统检测的字体
        main_font = pdf_config.get('main_font', system_fonts['main_font'])
        sans_font = pdf_config.get('sans_font', system_fonts['sans_font'])
        mono_font = pdf_config.get('mono_font', system_fonts['mono_font'])
        
        # 获取设备相关的字体大小和布局设置
        code_fontsize = pdf_config.get('code_fontsize', '\\small')
        fontsize = pdf_config.get('fontsize', '10pt')
        linespread = pdf_config.get('linespread', '1.0')
        parskip = pdf_config.get('parskip', '6pt')
        
        yaml_config = {
            'pdf-engine': 'xelatex',
            'highlight-style': pdf_config.get('highlight_style', 'tango'),
            'from': 'markdown+fenced_code_attributes+fenced_code_blocks+backtick_code_blocks',  # 移除 highlighting
            'variables': {
                'documentclass': 'article',
                'geometry': pdf_config.get('margin', 'margin=1in'),
                'fontsize': fontsize,  # 添加字体大小设置
                # 中文正文字体
                'CJKmainfont': main_font,
                'CJKsansfont': sans_font,
                'CJKmonofont': main_font,  # 使用主字体作为等宽中文字体
                # 等宽字体（代码）
                'monofont': mono_font,
                'monofontoptions': ['Scale=0.85'],
                'colorlinks': True,
                'linkcolor': 'blue',
                'urlcolor': 'blue',
                'header-includes': [
                    # 加载必要的包
                    '\\usepackage{fontspec}',    # XeTeX 的字体支持
                    '\\usepackage{xunicode}',    # Unicode 支持
                    '\\usepackage{xeCJK}',       # 中文支持
                    '\\usepackage{fvextra}',     # 代码块支持
                    '\\usepackage[most]{tcolorbox}',
                    '\\usepackage{graphicx}',
                    '\\usepackage{float}',
                    '\\usepackage{sectsty}',   # 节标题格式支持
                    '\\usepackage{hyperref}',  # hyperref 应该最后加载
                    '\\usepackage{longtable}', # 基本表格支持
                    '\\usepackage{ragged2e}',  # 段落对齐支持
                    # 段落对齐设置
                    '\\AtBeginDocument{\\justifying}',
                    # 添加listings包和创建Shaded环境（而不是重新定义）
                    '\\usepackage{listings}',
                    # PDF 元数据设置 - 合并为单个字符串以避免YAML解析错误
                    f'\\hypersetup{{pdftitle={{{repo_name} 代码文档}}, pdfauthor={{Repo-to-PDF Generator}}, colorlinks=true, linkcolor=blue, urlcolor=blue}}',
                    # 布局设置
                    f'\\linespread{{{linespread}}}',
                    f'\\setlength{{\\parskip}}{{{parskip}}}',
                    # 字体设置
                    '\\defaultfontfeatures{Mapping=tex-text}',  # 启用 TeX 连字
                    # 中文字体设置（使用检测到的字体）
                    f'\\setCJKmainfont{{{main_font}}}',
                    f'\\setCJKsansfont{{{sans_font}}}',
                    f'\\setCJKmonofont{{{main_font}}}',
                    # 中文断行设置
                    '\\XeTeXlinebreaklocale "zh"',
                    '\\XeTeXlinebreakskip = 0pt plus 1pt',
                    # 标题格式设置
                    '\\allsectionsfont{\\CJKfamily{sf}}',  # 使用 sectsty 包的命令设置所有标题字体
                    # 图片设置
                    '\\DeclareGraphicsExtensions{.png,.jpg,.jpeg,.gif}',
                    '\\graphicspath{{./images/}}',
                    # 图片处理设置
                    '\\usepackage{adjustbox}',
                    '\\setkeys{Gin}{width=0.8\\linewidth,keepaspectratio}',
                    # 代码块设置 - 使用可配置的字体大小
                    f'\\DefineVerbatimEnvironment{{Highlighting}}{{Verbatim}}{{breaklines,commandchars=\\\\\\{{\\}}, fontsize={code_fontsize}}}',
                    f'\\fvset{{breaklines=true, breakanywhere=true, breakafter=\\\\, fontsize={code_fontsize}}}',
                    # 代码框设置 - 只保留一个定义
                    '\\renewenvironment{Shaded}{\\begin{tcolorbox}[breakable,boxrule=0pt,frame hidden,sharp corners]}{\\end{tcolorbox}}',
                ]
            }
        }
        
        yaml_path = Path(self.temp_dir) / "pandoc_defaults.yaml"
        
        # 先创建 header includes 文件
        header_tex_path = Path(self.temp_dir) / "header.tex"
        # Emoji 字体回退：defaults 分支也启用，避免 PDF 中 emoji 乱码
        emoji_candidates = []
        cfg_emoji = pdf_config.get('emoji_font')
        if isinstance(cfg_emoji, list):
            emoji_candidates.extend([str(x) for x in cfg_emoji if x])
        elif isinstance(cfg_emoji, str) and cfg_emoji.strip():
            emoji_candidates.append(cfg_emoji.strip())
        for e in system_fonts.get('emoji_fonts', []):
            if e not in emoji_candidates:
                emoji_candidates.append(e)
        emoji_setup_tex_lines = [
            "\\newif\\ifemojiavailable",
            "\\emojiavailablefalse",
        ]
        for name in emoji_candidates:
            safe_name = name.replace('\\\\', r'\\\\').replace('{', '').replace('}', '')
            emoji_setup_tex_lines.append(
                f"\\IfFontExistsTF{{{safe_name}}}{{\\newfontfamily\\EmojiFont{{{safe_name}}}\\emojiavailabletrue}}{{}}"
            )
        emoji_setup_tex_lines.append(
            f"\\ifemojiavailable\\setmonofont[Scale=0.85,FallbackFamilies={{EmojiFont}}]{{{mono_font}}}\\else\\setmonofont[Scale=0.85]{{{mono_font}}}\\fi"
        )
        emoji_setup_tex = "\n".join(emoji_setup_tex_lines)

        header_content = (
            "\\usepackage{fontspec}\n"
            "\\usepackage{xunicode}\n"
            "\\usepackage{xeCJK}\n"
            "\\usepackage{fvextra}\n"
            "\\usepackage[most]{tcolorbox}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{float}\n"
            "\\usepackage{sectsty}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{longtable}\n"
            "\\usepackage{ragged2e}\n"
            "\\AtBeginDocument{\\justifying}\n"
            "\\usepackage{listings}\n"
            "\\hypersetup{pdftitle={" + repo_name + " 代码文档}, pdfauthor={Repo-to-PDF Generator}, colorlinks=true, linkcolor=blue, urlcolor=blue}\n"
            "\\defaultfontfeatures{Mapping=tex-text}\n"
            "\\setCJKmainfont{" + main_font + "}\n"
            "\\setCJKsansfont{" + sans_font + "}\n"
            "\\setCJKmonofont{" + main_font + "}\n"
            "\\XeTeXlinebreaklocale \"zh\"\n"
            "\\XeTeXlinebreakskip = 0pt plus 1pt\n"
            "\\allsectionsfont{\\CJKfamily{sf}}\n"
            "\\DeclareGraphicsExtensions{.png,.jpg,.jpeg,.gif}\n"
            "\\graphicspath{{./images/}}\n"
            "\\usepackage{adjustbox}\n"
            "\\setkeys{Gin}{width=0.8\\linewidth,keepaspectratio}\n"
            "\\RecustomVerbatimEnvironment{verbatim}{Verbatim}{breaklines,commandchars=\\\\\\{\\}}\n"
            "\\fvset{breaklines=true, breakanywhere=true, breakafter=\\\\}\n"
            "\\renewenvironment{Shaded}{\\begin{tcolorbox}[breakable,boxrule=0pt,frame hidden,sharp corners]}{\\end{tcolorbox}}\n"
            "% Emoji 图片宏（用于代码块内插入 PNG）\n"
            "\\newcommand{\\emojiimg}[1]{\\raisebox{-0.2ex}{\\includegraphics[height=1.0em]{images/emoji/#1}}}\n"
        )
        # 将 Emoji 设置追加到 header 中（在字体设置之后即可）
        header_content = header_content + "\n" + emoji_setup_tex + "\n"
        
        with open(header_tex_path, 'w', encoding='utf-8') as f:
            f.write(header_content)
        
        # 创建 pandoc defaults 文件
        yaml_content = f"""# Pandoc defaults file
pdf-engine: xelatex
from: markdown+fenced_code_attributes+fenced_code_blocks+backtick_code_blocks
highlight-style: {pdf_config.get('highlight_style', 'tango')}

include-in-header:
  - {header_tex_path}

variables:
  documentclass: article
  geometry: {pdf_config.get('margin', 'margin=1in')}
  CJKmainfont: "{main_font}"
  CJKsansfont: "{sans_font}"
  CJKmonofont: "{main_font}"
  monofont: "{mono_font}"
  monofontoptions: 
    - Scale=0.85
  colorlinks: true
  linkcolor: blue
  urlcolor: blue
"""
        
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        
        return yaml_path

    def convert(self):
        """转换仓库内容为 PDF"""
        try:
            # 不需要创建工作目录，因为在初始化时已经创建
            
            # 克隆或更新仓库
            repo_manager = GitRepoManager(
                self.config['repository']['url'],
                self.config['repository'].get('branch', 'main')
            )
            repo_path = repo_manager.clone_or_pull(self.workspace_dir)
            
            # 创建临时文件
            temp_md = self.create_temp_markdown()
            
            # 生成输出路径（已经是相对于项目根目录）
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_pdf = self.output_dir / f"{repo_path.name}_{timestamp}.pdf"
            
            # 收集并处理所有文件
            with open(temp_md, 'w', encoding='utf-8') as out_file:
                # 写入标题 (移除 YAML 前置内容，通过命令行传递)
                out_file.write(f"# {repo_path.name} 代码文档\n\n")
                
                # 根据模板生成内容
                if self.template and self.template.get('structure'):
                    structure = self.template['structure']
                    
                    # 处理模板中的各个部分
                    for section in structure.get('sections', []):
                        if section.get('type') == 'tree' and structure.get('include_tree', True):
                            logger.info("Generating directory tree...")
                            tree_depth = structure.get('tree_max_depth', 3)
                            directory_tree = self.generate_directory_tree(repo_path, tree_depth)
                            out_file.write(directory_tree)
                            out_file.write("\n\n")
                        elif section.get('type') == 'stats' and structure.get('include_stats', True):
                            logger.info("Generating code statistics...")
                            stats = self.generate_code_stats(repo_path)
                            out_file.write(stats)
                            out_file.write("\n\n")
                        elif section.get('content'):
                            # 替换模板变量
                            content = section['content']
                            content = content.replace('{{repo_name}}', repo_path.name)
                            content = content.replace('{{date}}', datetime.now().strftime('%Y-%m-%d'))
                            out_file.write(content)
                            out_file.write("\n\n")
                else:
                    # 使用默认结构
                    logger.info("Generating directory tree...")
                    directory_tree = self.generate_directory_tree(repo_path)
                    out_file.write(directory_tree)
                    out_file.write("\n\n")
                
                # 收集所有需要处理的文件
                all_files = []
                for file_path in sorted(repo_path.rglob('*')):
                    # 允许处理特定的以点开头的文件，如 .cursorrules
                    if file_path.is_file() and (file_path.name == '.cursorrules' or not any(part.startswith('.') for part in file_path.parts)):
                        all_files.append(file_path)
                
                # 使用进度条处理所有文件
                logger.info(f"Processing {len(all_files)} files...")
                for file_path in tqdm(all_files, desc="Processing files", unit="file", disable=logger.level > logging.INFO):
                    try:
                        content = self.process_file(file_path, repo_path)
                        if content:
                            out_file.write(content)
                            out_file.flush()  # 立即刷新到磁盘，避免内存堆积
                    except Exception as e:
                        logger.warning(f"Failed to process {file_path}: {e}")
                        # 继续处理其他文件
            
            # 获取系统字体
            pdf_config = self.config.get('pdf_settings', {})
            system_fonts = get_system_fonts()
            main_font = pdf_config.get('main_font', system_fonts['main_font'])
            sans_font = pdf_config.get('sans_font', system_fonts['sans_font'])
            mono_font = pdf_config.get('mono_font', system_fonts['mono_font'])
            
            # 获取设备相关的字体大小设置
            code_fontsize = pdf_config.get('code_fontsize', '\\small')
            linespread = pdf_config.get('linespread', '1.0')
            parskip = pdf_config.get('parskip', '6pt')
            
            # 创建 header.tex 文件
            header_tex_path = self.temp_dir / "header.tex"
            # 构建 Emoji 字体回退设置（在等宽字体中启用，保证代码块内表情不乱码）
            emoji_candidates = []
            cfg_emoji = pdf_config.get('emoji_font')
            if isinstance(cfg_emoji, list):
                emoji_candidates.extend([str(x) for x in cfg_emoji if x])
            elif isinstance(cfg_emoji, str) and cfg_emoji.strip():
                emoji_candidates.append(cfg_emoji.strip())
            # 追加系统候选字体
            for e in system_fonts.get('emoji_fonts', []):
                if e not in emoji_candidates:
                    emoji_candidates.append(e)

            # 生成 TeX 条件判断代码，尝试依次加载候选的 Emoji 字体
            emoji_setup_tex_lines = [
                "% Emoji 字体设置",
                "\\newif\\ifemojiavailable",
                "\\emojiavailablefalse",
            ]
            for name in emoji_candidates:
                safe_name = name.replace('\\', r'\\').replace('{', '').replace('}', '')
                emoji_setup_tex_lines.append(
                    f"\\IfFontExistsTF{{{safe_name}}}{{\\newfontfamily\\EmojiFont{{{safe_name}}}\\emojiavailabletrue}}{{}}"
                )
            # 如果找到 Emoji 字体，则创建一个 \emoji 命令用于切换字体
            emoji_setup_tex_lines.append("\\ifemojiavailable\\newcommand{\\emoji}[1]{{{\\EmojiFont #1}}}\\else\\newcommand{\\emoji}[1]{#1}\\fi")
            emoji_setup_tex = "\n".join(emoji_setup_tex_lines)

            header_lines = []
            header_lines.append("% 设置字体")
            header_lines.append("\\usepackage{fontspec}")
            header_lines.append("\\usepackage{xeCJK}")
            header_lines.append("\\setCJKmainfont{" + main_font + "}")
            header_lines.append("\\setCJKsansfont{" + sans_font + "}")
            header_lines.append("\\setCJKmonofont{" + main_font + "}")
            header_lines.append("% Emoji 字体和命令")
            header_lines.append(emoji_setup_tex)
            header_lines.append("% 等宽字体（用于代码）")
            header_lines.append("\\setmonofont{" + mono_font + "}")
            header_lines.append("")
            header_lines.append("% 布局设置")
            header_lines.append("\\linespread{" + linespread + "}")
            header_lines.append("\\setlength{\\parskip}{" + parskip + "}")
            header_lines.append("")
            header_lines.append("% 中文支持")
            header_lines.append("\\XeTeXlinebreaklocale \"zh\"")
            header_lines.append("\\XeTeXlinebreakskip = 0pt plus 1pt")
            header_lines.append("")
            header_lines.append("% 代码环境（使用 fancyvrb 提供的 Verbatim，并让 verbatim 支持选择性命令执行）")
            header_lines.append("\\usepackage{fvextra}")
            # 使用少见字符 '§' 作为转义起始，避免普通反斜线被当作命令
            # 全局 verbatim 不启用 commandchars，减少复杂度；仅 CodeBlock 允许命令执行
            header_lines.append("\\RecustomVerbatimEnvironment{verbatim}{Verbatim}{breaklines,breakanywhere,obeytabs,tabsize=2, fontsize=" + code_fontsize + "}")
            # 提供一个稳定的 CodeBlock 环境，避免外部包覆盖 verbatim 行为（更激进的折行与更小字号）
            # 专用 CodeBlock：使用不与代码冲突的分组符号 « »
            header_lines.append("\\newenvironment{CodeBlock}{\\Verbatim[breaklines,breakanywhere=false,obeytabs,tabsize=2,commandchars=§«», fontsize=\\footnotesize]}{\\endVerbatim}")
            header_lines.append("\\fvset{breaklines=true, breakanywhere=true, fontsize=" + code_fontsize + ", tabsize=2}")
            header_lines.append("% Emoji 图片宏（用于代码块内插入 PNG）")
            header_lines.append("\\newcommand{\\emojiimg}[1]{\\raisebox{-0.2ex}{\\includegraphics[height=1.0em]{temp_conversion_files/images/emoji/#1}}}")
            header_lines.append("")
            header_lines.append("")
            header_lines.append("% 防止 Dimension too large 错误")
            header_lines.append("\\maxdeadcycles=200")
            header_lines.append("\\emergencystretch=5em")
            header_lines.append("\\usepackage{etoolbox}")
            header_lines.append("\\makeatletter")
            header_lines.append("\\patchcmd{\\@verbatim}")
            header_lines.append("  {\\verbatim@font}")
            header_lines.append("  {\\verbatim@font\\small}")
            header_lines.append("  {}{}")
            header_lines.append("\\makeatother")
            header_lines.append("")
            header_lines.append("% 页面设置")
            header_lines.append("\\usepackage{graphicx}")
            header_lines.append("\\DeclareGraphicsExtensions{.png,.jpg,.jpeg,.gif}")
            header_lines.append("\\graphicspath{{./images/}}")
            header_lines.append("")
            header_lines.append("% 超链接")
            header_lines.append("\\usepackage{hyperref}")
            header_lines.append("\\hypersetup{")
            header_lines.append("    pdftitle={" + repo_path.name + " 代码文档},")
            header_lines.append("    pdfauthor={Repo-to-PDF Generator},")
            header_lines.append("    colorlinks=true,")
            header_lines.append("    linkcolor=blue,")
            header_lines.append("    urlcolor=blue")
            header_lines.append("}")
            header_content = "\n".join(header_lines) + "\n"
            
            with open(header_tex_path, 'w', encoding='utf-8') as f:
                f.write(header_content)
            
            # 调用 pandoc 进行转换，添加更多选项
            cmd = [
                'pandoc',
                '-f', 'markdown+pipe_tables+grid_tables+table_captions+smart+fenced_code_blocks+fenced_code_attributes+backtick_code_blocks+inline_code_attributes+line_blocks+fancy_lists+definition_lists+example_lists+task_lists+citations+footnotes+smart+superscript+subscript+raw_html+tex_math_dollars+tex_math_single_backslash+tex_math_double_backslash+raw_tex+implicit_figures+link_attributes+bracketed_spans+native_divs+native_spans+raw_attribute+header_attributes+auto_identifiers+autolink_bare_uris+emoji+hard_line_breaks+escaped_line_breaks+blank_before_blockquote+blank_before_header+space_in_atx_header+strikeout+east_asian_line_breaks',
                '--pdf-engine=xelatex',
                '--no-highlight',
                '--wrap=none',
                '--toc',
                '--toc-depth=2',
                                '-V', 'documentclass=article',
                '-V', f'title={repo_path.name} 代码文档',
                '-V', 'date=\\today',
                '-V', 'geometry:margin=0.5in',
                '-V', 'fontsize=10pt',
                '-V', f'CJKmainfont={main_font}',
                '-V', f'CJKsansfont={sans_font}',
                '-V', f'CJKmonofont={main_font}',
                '-V', f'monofont={mono_font}',
                '-V', 'colorlinks=true',
                '-V', 'linkcolor=blue',
                '-V', 'urlcolor=blue',
                '-H', str(header_tex_path),  # 使用 -H 选项包含 header 文件
                '--resource-path=' + str(self.temp_dir),
                '--standalone',
                # 输出设置
                '-o', str(output_pdf),
                str(temp_md)
            ]
            
            # 设置环境变量来增加 TeX 内存
            env = os.environ.copy()
            env['max_print_line'] = '1000'
            env['error_line'] = '254'
            env['half_error_line'] = '238'
            
            logger.info("Converting to PDF...")
            logger.info(f"Running command: {' '.join(cmd)}")  # 打印完整命令便于调试
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(self.project_root))
            
            if result.returncode != 0:
                logger.error(f"Pandoc stderr: {result.stderr}")
                logger.error(f"Pandoc stdout: {result.stdout}")
                raise Exception(f"Pandoc conversion failed: {result.stderr}")
                
            logger.info(f"Successfully created PDF: {output_pdf}")
            
        except Exception as e:
            logger.error(f"转换失败: {str(e)}")
            # 保存生成的 markdown 文件以便调试
            debug_md = self.project_root / "debug.md"
            if temp_md.exists():
                import shutil
                shutil.copy2(temp_md, debug_md)
                logger.info(f"已保存调试用 Markdown 文件: {debug_md}")
            raise
            
        finally:
            # 不再删除临时目录，因为它在项目目录下可能还有用
            if self.temp_dir and self.temp_dir.exists():
                logger.info(f"临时文件保存在: {self.temp_dir}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert GitHub repository to PDF with syntax highlighting')
    parser.add_argument('-c', '--config', type=Path, required=True,
                      help='Path to configuration YAML file')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Enable verbose output (DEBUG level)')
    parser.add_argument('-q', '--quiet', action='store_true',
                      help='Only show warnings and errors')
    parser.add_argument('-t', '--template', type=str, default=None,
                      help='Template name to use (e.g., default, technical)')
    
    args = parser.parse_args()
    
    # 配置日志级别
    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    # 配置日志
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # 设置 git 模块的日志级别
    git_level = logging.WARNING if not args.verbose else log_level
    logging.getLogger('git').setLevel(git_level)
    logging.getLogger('git.cmd').setLevel(git_level)
    logging.getLogger('git.util').setLevel(git_level)
    
    # 设置其他模块的日志级别
    logging.getLogger('MARKDOWN').setLevel(git_level)
    
    converter = RepoPDFConverter(args.config, args.template)
    converter.convert()

if __name__ == '__main__':
    main()
