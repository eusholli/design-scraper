# System Patterns: Web Page Design Scheme Extractor

## Architecture Overview

The system follows a sequential pipeline architecture:

1.  **Fetch & Render:** Obtain webpage content, handling both static HTML and dynamic JavaScript rendering.
2.  **Analyze:** Extract various design elements (colors, typography, layout, components, images) using dedicated functions.
3.  **Synthesize:** Combine extracted data into a structured JSON schema.
4.  **Enhance (Optional):** Apply plugins based on detected website type (e.g., WordPress).
5.  **Validate:** Ensure the generated schema conforms to a predefined structure.
6.  **Augment (Optional):** Generate supplementary outputs like AI-optimized schemas, code snippets, and documentation.
7.  **Output:** Save or display the results.

## Key Technical Decisions & Patterns

-   **Hybrid Fetching:** Utilizes `requests` for initial, fast fetching of static content, falling back to `Selenium` with a headless browser (`ChromeDriverManager`) only when necessary or for full JavaScript rendering and screenshotting. This balances performance and accuracy.
-   **Multi-Method Analysis:** Employs multiple techniques for critical extractions like color analysis (`ColorThief` on screenshots, CSS parsing via `cssutils`, Selenium `getComputedStyle`). This increases the robustness and comprehensiveness of the results.
-   **Computed Style Reliance:** Leverages Selenium's `getComputedStyle` extensively to determine the actual rendered styles of elements, accounting for CSS specificity and JavaScript modifications.
-   **Targeted Component Analysis:** Focuses on identifying and analyzing common UI components (buttons, cards, forms, navigation) using specific CSS selectors and extracting their key styling properties.
-   **Statistical Pattern Detection:** Uses frequency analysis (e.g., `collections.Counter`) on CSS classes and spacing values to identify recurring patterns and common units.
-   **Modular Design:** The core logic is broken down into distinct functions, each responsible for a specific aspect of the extraction process (e.g., `extract_color_palette`, `extract_typography`).
-   **Plugin Architecture:** Implements a basic plugin system (`DesignSchemeExtractorPlugin` base class) allowing for extensibility to handle nuances of specific platforms (like WordPress).
-   **Schema-Centric:** The entire process revolves around generating and validating a well-defined JSON schema (`jsonschema` validation).
-   **Output Diversification:** Generates multiple output formats tailored for different use cases: raw JSON schema, AI-optimized JSON, code snippets (CSS, Tailwind, Styled Components), and Markdown documentation.
-   **Safe Script Execution:** Wraps Selenium's `execute_script` calls in a helper function (`safe_execute_script`) for better error handling.
-   **Standard CLI:** Uses Python's `argparse` module to provide a standard command-line interface.

## Component Relationships

-   The main function (`extract_design_scheme_extended`) orchestrates the calls to fetching, analysis, generation, and output functions.
-   Analysis functions (e.g., `extract_color_palette`, `extract_typography`) depend on the output of `fetch_webpage` (HTML content, screenshot, Selenium driver).
-   `generate_design_schema` aggregates the results from all analysis functions.
-   Optional enhancement/generation functions (`enhance_with_plugins`, `optimize_for_ai_consumption`, `generate_design_code_snippets`, `generate_documentation`) take the base `design_schema` as input.
-   The CLI function (`main_extended`) parses arguments and calls the main extraction function.
