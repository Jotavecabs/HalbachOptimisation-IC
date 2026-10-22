"""Converte um relatório Markdown (com imagens) em PDF A4, usando o Google Chrome.

O Markdown vira HTML com um estilo de documento e o Chrome, sem abrir
janela, imprime em PDF. As imagens são lidas pelos caminhos relativos ao
arquivo .md.

Uso::

    uv run --with markdown python scripts/md_para_pdf.py DOCS/relatorio_viabilidade.md
    # gera DOCS/relatorio_viabilidade.pdf
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 19pt; margin: 0 0 4pt 0; color: #0b3d63; }
h2 { font-size: 14pt; margin-top: 16pt; border-bottom: 1.5px solid #0b3d63; padding-bottom: 2pt;
     color: #0b3d63; break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 12pt; color: #1f5f8b; break-after: avoid; }
p, li { text-align: justify; }
hr { border: none; border-top: 1px solid #ccc; margin: 12pt 0; }
table { border-collapse: collapse; margin: 6pt 0 10pt 0; font-size: 9.5pt; width: auto; break-inside: avoid; }
th, td { border: 1px solid #b8c4ce; padding: 3pt 6pt; vertical-align: top; }
th { background: #e8eef3; }
img { max-width: 100%; display: block; margin: 6pt auto; break-inside: avoid; }
td img { margin: 0; }
p:has(> img) { break-inside: avoid; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; background: #f4f7f9; border-left: 3px solid #1f5f8b; }
code { font-family: Menlo, monospace; font-size: 9pt; background: #f2f2f2; padding: 0 2px; }
"""


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate
    raise SystemExit("Google Chrome/Chromium não encontrado")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("markdown_file", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None, help="PDF de saída (padrão: mesmo nome .pdf)")
    args = parser.parse_args()

    source = args.markdown_file.resolve()
    output = (args.output or source.with_suffix(".pdf")).resolve()
    body = markdown.markdown(source.read_text(encoding="utf-8"), extensions=["tables", "sane_lists"])
    html = (f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<base href="{source.parent.as_uri()}/"><style>{CSS}</style></head><body>{body}</body></html>')

    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "relatorio.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [find_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             "--allow-file-access-from-files", f"--print-to-pdf={output}", page.as_uri()],
            check=True, capture_output=True,
        )
    print(f"PDF gerado: {output}")


if __name__ == "__main__":
    main()
