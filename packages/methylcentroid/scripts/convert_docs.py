#!/usr/bin/env python3
"""
Script to convert Markdown documentation to HTML format.
Usage: python convert_docs.py [input.md] [output.html]
"""

import sys
import os
from pathlib import Path
import markdown
from markdown.extensions import toc, fenced_code, tables, codehilite

def convert_markdown_to_html(input_file: str, output_file: str = None):
    """
    Convert a Markdown file to HTML with enhanced formatting.

    Args:
        input_file: Path to the input Markdown file
        output_file: Path to the output HTML file (optional)
    """
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.")
        return False

    if output_file is None:
        output_file = os.path.splitext(input_file)[0] + '.html'

    # Read the markdown content
    with open(input_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()

    # Configure markdown extensions
    extensions = [
        'toc',  # Table of contents
        'fenced_code',  # Code blocks with ```
        'tables',  # Table support
        'codehilite',  # Syntax highlighting
        'footnotes',  # Footnote support
        'md_in_html',  # Allow markdown inside HTML
    ]

    # Convert to HTML
    html_content = markdown.markdown(markdown_content, extensions=extensions)

    # Create a complete HTML document with styling
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MethylCentroid: Theoretical Foundations</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}

        .container {{
            background-color: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}

        h1 {{
            text-align: center;
            color: #3498db;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}

        h2 {{
            border-bottom: 2px solid #3498db;
            padding-bottom: 5px;
        }}

        h3 {{
            color: #34495e;
        }}

        code {{
            background-color: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}

        pre {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            border-left: 4px solid #3498db;
        }}

        pre code {{
            background-color: transparent;
            padding: 0;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}

        th {{
            background-color: #f8f9fa;
            font-weight: bold;
            color: #2c3e50;
        }}

        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}

        blockquote {{
            border-left: 4px solid #3498db;
            margin: 20px 0;
            padding-left: 20px;
            font-style: italic;
            color: #555;
        }}

        .formula {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            padding: 15px;
            margin: 15px 0;
            font-family: 'Times New Roman', serif;
            text-align: center;
        }}

        .algorithm {{
            background-color: #f0f8ff;
            border: 1px solid #b3d9ff;
            border-radius: 5px;
            padding: 15px;
            margin: 15px 0;
        }}

        .toc {{
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
        }}

        .toc ul {{
            list-style-type: none;
            padding-left: 0;
        }}

        .toc li {{
            margin: 5px 0;
        }}

        .toc a {{
            color: #3498db;
            text-decoration: none;
        }}

        .toc a:hover {{
            text-decoration: underline;
        }}

        @media print {{
            body {{
                background-color: white;
                max-width: none;
                margin: 0;
                padding: 20px;
            }}

            .container {{
                box-shadow: none;
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
    </div>

    <script>
        // Add some interactivity for better navigation
        document.addEventListener('DOMContentLoaded', function() {{
            // Make table of contents links work
            const tocLinks = document.querySelectorAll('.toc a');
            tocLinks.forEach(link => {{
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const targetId = this.getAttribute('href').substring(1);
                    const targetElement = document.getElementById(targetId);
                    if (targetElement) {{
                        targetElement.scrollIntoView({{ behavior: 'smooth' }});
                    }}
                }});
            }});

            // Add smooth scrolling to all internal links
            const allLinks = document.querySelectorAll('a[href^="#"]');
            allLinks.forEach(link => {{
                link.addEventListener('click', function(e) {{
                    const targetId = this.getAttribute('href').substring(1);
                    const targetElement = document.getElementById(targetId);
                    if (targetElement) {{
                        e.preventDefault();
                        targetElement.scrollIntoView({{ behavior: 'smooth' }});
                    }}
                }});
            }});
        }});
    </script>
</body>
</html>"""

    # Write the HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)

    print(f"Successfully converted '{input_file}' to '{output_file}'")
    return True

def main():
    """Main function for command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: python convert_docs.py <input.md> [output.html]")
        print("Example: python convert_docs.py docs/MethylCentroid_Theory.md")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    if convert_markdown_to_html(input_file, output_file):
        print("\nTo convert HTML to PDF, you can use one of the following methods:")
        print("1. Open the HTML file in a web browser and print to PDF")
        print("2. Use wkhtmltopdf: wkhtmltopdf input.html output.pdf")
        print("3. Use a web-based converter")
        print("4. Use browser developer tools to save as PDF")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
