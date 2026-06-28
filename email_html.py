"""Shared Markdown-to-HTML email rendering."""

from __future__ import annotations

import html

import markdown


def build_email_html(
    markdown_body: str,
    date_str: str,
    intro: str,
) -> str:
    """Turn pipeline Markdown into styled HTML for mail clients."""
    fragment = markdown.markdown(
        markdown_body,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    safe_intro = intro.replace("{date}", html.escape(date_str, quote=True))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style type="text/css">
  body {{ margin: 0; padding: 0; background: #f4f4f5; }}
  .shell {{ max-width: 640px; margin: 0 auto; padding: 24px 20px 40px; }}
  .intro {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; font-size: 14px; line-height: 1.5; color: #52525b; margin: 0 0 20px; }}
  .summary-html {{ font-family: Georgia, 'Times New Roman', serif; font-size: 17px; line-height: 1.65; color: #18181b; }}
  .summary-html h1 {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; font-size: 26px; font-weight: 700; margin: 0 0 0.5em; line-height: 1.25; color: #0f172a; }}
  .summary-html h2 {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; font-size: 22px; font-weight: 650; margin: 1.15em 0 0.45em; line-height: 1.3; color: #0f172a; }}
  .summary-html h3 {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; font-size: 20px; font-weight: 650; margin: 1.1em 0 0.4em; line-height: 1.35; color: #0f172a; }}
  .summary-html h4, .summary-html h5, .summary-html h6 {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; font-size: 18px; font-weight: 600; margin: 1em 0 0.35em; color: #1e293b; }}
  .summary-html p {{ margin: 0.65em 0; font-size: 17px; }}
  .summary-html ul, .summary-html ol {{ margin: 0.65em 0; padding-left: 1.35em; font-size: 17px; }}
  .summary-html li {{ margin: 0.35em 0; }}
  .summary-html strong {{ font-weight: 600; }}
  .summary-html code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 15px; background: #f4f4f5; padding: 0.12em 0.35em; border-radius: 4px; }}
  .summary-html pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; line-height: 1.5; background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px 16px; overflow-x: auto; }}
  .summary-html pre code {{ background: transparent; padding: 0; font-size: inherit; }}
  .summary-html blockquote {{ margin: 1em 0; padding-left: 1em; border-left: 4px solid #e5e7eb; color: #52525b; }}
  .summary-html hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 1.5em 0; }}
  .summary-html table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 16px; }}
  .summary-html th, .summary-html td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
  .summary-html th {{ background: #fafafa; font-weight: 600; }}
</style>
</head>
<body>
<div class="shell">
<p class="intro">{safe_intro}</p>
<div class="summary-html">
{fragment}
</div>
</div>
</body>
</html>"""
