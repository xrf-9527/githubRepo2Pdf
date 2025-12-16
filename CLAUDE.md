# CLAUDE.md

Project instructions for Claude Code when working with this repository.

## Project Overview

**githubRepo2Pdf** - Converts GitHub repositories to professional PDF documents with syntax highlighting and Chinese language support.

- **Version**: 2.0 (modular architecture, 21 modules, 4,762 lines)
- **Tech Stack**: Python 3.10+, Pandoc, XeLaTeX, Pydantic
- **Entry Point**: `repo_to_pdf/cli.py`
- **Main Class**: `RepoPDFConverter` in `repo_to_pdf/converter.py`

## Quick Start Commands

```bash
# Standard workflow
make                    # Install deps + convert (default)
make debug              # Verbose logging
make clean              # Remove temp files

# Device presets
make kindle             # 7-inch Kindle optimization
make tablet             # Tablet optimization
make mobile             # Mobile optimization

# Development
make test               # Run pytest suite
make test-coverage      # With coverage report
```

## Architecture (v2.0)

**IMPORTANT**: This is a modular refactor from monolithic v1.0. Always prefer editing existing modules over creating new ones.

### Core Modules

- `cli.py` - Entry point with argparse
- `converter.py` - Main orchestration pipeline
- `core/config.py` - Pydantic validation (AppConfig, PDFSettings)
- `core/constants.py` - File limits, extensions, pandoc settings
- `git/repo_manager.py` - Shallow clones (--depth=1)
- `processors/` - File, code, markdown processing
- `converters/` - Image, emoji, LaTeX generation
- `stats/` - Directory tree, code statistics

### Conversion Pipeline

1. Apply device preset if specified
2. Clone/update repo (shallow, --depth=1)
3. Filter files by ignore patterns
4. Process files (SVG→PNG, syntax highlighting, escape sequences)
5. Combine to markdown → Generate PDF via Pandoc+XeLaTeX

## Critical Configuration

### Pandoc Extensions (latex_generator.py:87)

**YOU MUST** include these disabled extensions to prevent LaTeX errors:

```
-raw_tex                  # Prevents \\ interpretation in code
-yaml_metadata_block      # Avoids YAML parsing conflicts
-tex_math_dollars         # Prevents $ triggering math mode
```

**Why**: Without these, content like `\n` or `$#,##0` causes compilation failures.

### Text Escaping (markdown_processor.py:336-339)

**IMPORTANT**: Escape sequences `\n`, `\t`, `\r`, `\a`, `\b`, `\f`, `\v` MUST be escaped outside code blocks using:

```python
ln = re.sub(r"(?<!\\)\\([ntrabfv])", r"\\textbackslash{}\1", ln)
```

### Device Presets (config.yaml)

Optimized settings for different reading devices:
- `desktop`: 10pt fonts, 1-inch margins
- `kindle7`: 11pt fonts, `\small` code, 0.4-inch margins (expert recommended)
- `tablet`: 9pt fonts, 0.6-inch margins
- `mobile`: 7pt fonts, 0.3-inch margins

## Development Rules

### File Operations

- **ALWAYS** prefer `Edit` tool over `Write` for existing files
- **NEVER** create new modules without explicit requirement
- Large files (>1000 lines) auto-split into 800-line chunks
- File size limit: 0.5MB for non-images

### Code Style

- Type annotations required (mypy checked)
- Pydantic models for configuration
- Context managers for resource cleanup
- Comprehensive logging (INFO/DEBUG/WARNING levels)

### Testing

- Maintain >25% coverage (target: 50%+)
- Run `make test` before committing
- Integration tests in `tests/`
- CI/CD via `.github/workflows/test.yml`

## Common Issues & Solutions

### LaTeX Compilation Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Undefined control sequence \n` | Escape sequences in text | Already fixed in markdown_processor.py:339 |
| `macro parameter character # in math mode` | $ interpreted as math delimiter | Already fixed via `-tex_math_dollars` |
| `puenc-greek.def not found` | Missing Greek support | `sudo apt install texlive-lang-greek` |
| `Dimension too large` | Lines >80 chars | Auto hard-wrapped in code blocks |

### Font Issues

**Linux/WSL defaults**:
- Main: "Noto Serif CJK SC"
- Mono: "DejaVu Sans Mono"
- Emoji: "Noto Color Emoji" (NOT "Noto Emoji")

**macOS defaults**:
- Main: "Songti SC"
- Mono: "SF Mono"
- Emoji: "Apple Color Emoji"

Update `pdf_settings` in config.yaml if fonts missing.

### Debugging failed conversions

1. Run `make debug` for detailed logs
2. Check `temp_conversion_files/temp.md` for generated markdown
3. Review `temp_conversion_files/header.tex` for LaTeX issues
4. Generate debug LaTeX: `pandoc temp_conversion_files/temp.md -o debug.tex --defaults temp_conversion_files/pandoc_defaults.yaml`
5. Common fixes:
   - Missing fonts → update config.yaml
   - Special chars → already escaped in v2.0
   - Large files → auto-split enabled by default

## Important Paths

```
repo-workspace/           # Git clones (.gitignored)
repo-pdfs/               # Output PDFs (.gitignored)
temp_conversion_files/   # Debug artifacts (preserved on error)
venv/                    # Python virtualenv (.gitignored)
templates/               # PDF structure templates
repo_to_pdf/core/        # System utilities (cairo fix location)
```

## Dependencies

### Python

**Requires**: Python 3.10+ (Python 3.8/3.9 dropped in Dec 2025)

Uses: PEP 585 annotations, `Path.is_relative_to()`, match/case

Tested: 3.10, 3.11, 3.12, 3.13 on Ubuntu & macOS

### System (auto-installed via Makefile)

- pandoc, texlive-xetex, texlive-lang-greek
- cairo, inkscape (SVG conversion)
- fonts-noto-cjk, fonts-noto-color-emoji (Linux)

### Python (requirements.txt)

- GitPython 3.1.42 - Git operations
- PyYAML 6.0.1 - Config parsing
- Pydantic - Type-safe configuration
- CairoSVG ≥2.7.1 - SVG→PNG
- tqdm ≥4.66.0 - Progress bars

### Testing

- pytest ≥7.4.0, pytest-cov ≥4.1.0, pytest-mock ≥3.11.0

## Recent Critical Fixes

### Python 3.10+ Upgrade (2025-12-16)

**BREAKING**: Dropped Python 3.8/3.9 support (3.8 EOL Oct 2024)

Removed compatibility workarounds, now uses PEP 585 annotations & native `Path.is_relative_to()`. CI tests 3.10-3.13 on Ubuntu/macOS.

### Cairo Dependency & Monkeypatch (2025-12)

**Problem**: `cairosvg` failed to find Homebrew-installed `cairo` on macOS, causing SVG/emoji failures.
**Fix**: `repo_to_pdf/core/system_utils.py` monkeypatches `ctypes.util.find_library` to explicitly load `libcairo.2.dylib` from standard paths.

### LaTeX Verbatim Fix (2025-12)

**Problem**: `commandchars` in `Verbatim` environment caused `}` to crash compilation ("Argument of \FancyVerbGetLine has an extra }").
**Fix**: Removed `commandchars` from `RecustomVerbatimEnvironment` in `repo_to_pdf/converters/latex_generator.py`.

### LaTeX Escape & Math Mode (2025-10-18, commit c30fe9b)

**Fixed two major error categories**:

1. Escape sequence handling (`\n`, `\t`, etc.) → markdown_processor.py:336-339
2. Math mode conflicts (`$#,##0`) → latex_generator.py:87 (-tex_math_dollars)
3. Font package name → Makefile:166 (fonts-noto-color-emoji)

**Tested**: anthropics/skills repo (292 files, 1.6MB PDF) ✅

### Image Processing (2025-10)

- Absolute path resolution (`/img/foo.png` → repo root)
- HTML `<img>` tag conversion
- Graceful missing image handling
- Remote image downloading

### Code Highlighting (2025-10)

- Default style: `tango` (high contrast, excellent readability)
- Customizable code block styling (background, border, padding)
- Support for 30+ languages

## Configuration Example

```yaml
repository:
  url: "https://github.com/yourname/repo.git"
  branch: "main"

pdf_settings:
  margin: "1in"
  main_font: "Noto Serif CJK SC"  # Auto-detected by OS
  mono_font: "DejaVu Sans Mono"
  fontsize: "10pt"
  code_fontsize: "\\small"
  highlight_style: "tango"
  split_large_files: true

device_preset: "desktop"  # or kindle7, tablet, mobile
```

## Adding Language Support

Update `repo_to_pdf/core/constants.py`:

```python
CODE_EXTENSIONS = {
    '.ext': 'language-name',
    # Add new mapping
}
```

## Notes

- Conversion uses shallow git clones (--depth=1) for performance
- Files respect .gitignore patterns + custom ignore lists
- Progress bars show real-time processing status
- Temporary files preserved on error for debugging
- CLAUDE.old.md contains detailed historical documentation
