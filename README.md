# design-scraper
Investigate a website to extract the design into an LLM friendly format

## Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd design-scraper
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: This requires Python 3 and pip.*
    *You also need a working Google Chrome installation for Selenium.*

## Usage

The script is run from the command line:

```bash
python design_scheme_extractor.py <URL> [options]
```

### Arguments

*   **`url`** (Required): The full URL of the webpage you want to analyze (e.g., `https://example.com`).

### Options

*   **`-o, --output <prefix>`**:
    Specify an output file path prefix. The main JSON schema will be saved to `<prefix>.json`. Related files (documentation, AI schema, code snippets) will be saved alongside using the same prefix with appropriate suffixes (e.g., `<prefix>_docs.md`, `<prefix>_ai.json`, `<prefix>_snippets/`). If omitted, results are only returned in memory (and potentially printed to console if `-p` is used).

*   **`-p, --pretty`**:
    Print the main extracted design schema (JSON or YAML) nicely formatted to the console after extraction.

*   **`--format <format>`**:
    Choose the output format when using `--pretty`. Options are `json` (default) or `yaml`. Requires `PyYAML` to be installed for YAML output (`pip install PyYAML`).

*   **`--no-docs`**:
    Skip generating and saving the Markdown documentation file (`<prefix>_docs.md`).

*   **`--no-code`**:
    Skip generating and saving code snippet files (CSS Variables, Tailwind Config, Styled Components Theme) in the `<prefix>_snippets/` directory.

*   **`--no-ai`**:
    Skip generating and saving the AI-optimized schema file (`<prefix>_ai.json`).

### Examples

1.  **Analyze a website and print the schema to console:**
    ```bash
    python design_scheme_extractor.py https://example.com -p
    ```

2.  **Analyze a website and save all outputs to files prefixed with `output/example`:**
    ```bash
    python design_scheme_extractor.py https://example.com -o output/example
    ```
    *(This will create `output/example.json`, `output/example_docs.md`, `output/example_ai.json`, and the `output/example_snippets/` directory)*

3.  **Analyze and save only the main schema and AI schema:**
    ```bash
    python design_scheme_extractor.py https://example.com -o output/example --no-docs --no-code
    ```

4.  **Analyze and print the schema as YAML:**
    ```bash
    python design_scheme_extractor.py https://example.com -p --format yaml
    ```
