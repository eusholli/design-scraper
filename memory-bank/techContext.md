# Tech Context: Web Page Design Scheme Extractor

## Language

-   **Python 3**

## Core Dependencies

The project relies on several key Python libraries:

-   **`requests`**: For fetching static HTML content efficiently.
-   **`BeautifulSoup4`**: (Implicitly used or intended, though not explicitly shown in the final code snippets provided in `implementation.md` - primarily relies on Selenium and regex for parsing). Standard library for HTML parsing if needed.
-   **`selenium`**: For browser automation, rendering JavaScript-heavy pages, taking screenshots, and accessing computed styles.
-   **`webdriver-manager`**: To automatically manage the necessary browser drivers (specifically ChromeDriver).
-   **`Pillow` (PIL)**: Used for basic image processing, primarily to handle the screenshot data before passing it to `colorthief`.
-   **`colorthief`**: For extracting dominant colors from the webpage screenshot.
-   **`cssutils`**: For parsing CSS rules found within `<style>` tags.
-   **`jsonschema`**: For validating the structure of the generated JSON output against a defined schema.
-   **`PyYAML`**: (Optional, added in the extended CLI) For outputting the schema in YAML format.

## Development Setup & Execution

-   The application is structured as a single Python script (`design_scheme_extractor.py`).
-   Dependencies are managed using `pip` and can be installed via `pip install requests beautifulsoup4 selenium webdriver-manager Pillow colorthief cssutils jsonschema PyYAML`.
-   Execution is done via the command line: `python design_scheme_extractor.py <URL> [options]`.
-   Requires a working Chrome browser installation for Selenium/ChromeDriver to function correctly.

## Key Tool Usage Patterns

-   **Selenium (`webdriver`)**: Central to the process for accurate rendering and style computation. Used with headless mode for background execution. `getComputedStyle` is frequently used via `driver.execute_script`.
-   **Regular Expressions (`re`)**: Used for extracting information from HTML/CSS strings (e.g., finding style tags, font imports, class names).
-   **JSON Handling (`json`)**: Used for generating and potentially saving the final schema output.
-   **Command-Line Arguments (`argparse`)**: Provides the user interface for running the script.
