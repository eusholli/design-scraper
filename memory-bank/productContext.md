# Product Context: Web Page Design Scheme Extractor

## Problem Solved

Generating visually consistent graphics or UI elements that match an existing website's brand identity can be time-consuming and require manual analysis. AI systems capable of generating graphics need a structured understanding of the target website's design language to maintain consistency.

## How It Works

This program addresses the problem by automatically analyzing a given web page URL. It fetches the page content (handling dynamic JavaScript rendering), inspects the HTML and CSS, and analyzes visual elements (including screenshots) to identify key design characteristics.

## Core Purpose

The primary purpose is to extract and structure the visual design scheme of a webpage. This includes:

-   **Colors:** Identifying primary, secondary, accent, background, and text colors, along with a broader palette.
-   **Typography:** Determining font families, sizes, weights, and line heights for body text and headings.
-   **Layout:** Analyzing page dimensions, common container widths, grid system usage, and typical spacing units.
-   **Components:** Detecting styling patterns for common UI elements like buttons, cards, and forms.
-   **Images/Icons:** Identifying the use of SVG, icon fonts, and common image styling.

## Target Output

The program generates a structured JSON output containing the extracted design scheme. This format is specifically designed to be easily consumable by AI systems, enabling them to generate graphics, UI mockups, or other assets that adhere to the analyzed website's visual style. Additional outputs like documentation and code snippets further aid developers and designers.
