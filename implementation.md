# Web Page Design Scheme Extractor - Implementation Plan

## Overview

This program will extract the visual design scheme from a given web page URL, analyzing elements like colors, typography, spacing, and visual patterns. The output will be a structured format suitable for AI systems to generate visually consistent graphics.

## Implementation Steps

### 1. Setup and Dependencies

```markdown
We'll need several key libraries for this project:

- **requests**: To fetch the web page content
- **BeautifulSoup4**: For HTML parsing
- **Selenium**: For rendering JavaScript-heavy pages
- **webdriver-manager**: For managing the Chrome driver
- **Pillow (PIL)**: For image processing
- **colorthief**: For color palette extraction
- **cssutils**: For CSS parsing
- **jsonschema**: For validating our output schema

Install these dependencies with:

```bash
pip install requests beautifulsoup4 selenium webdriver-manager Pillow colorthief cssutils jsonschema
```

### 2. Web Page Fetching and Rendering

```python
def fetch_webpage(url):
    """
    Fetch a webpage using both requests (for static content) and Selenium (for dynamic content).
    This ensures we capture styles that might be applied via JavaScript.
    
    Args:
        url (str): The URL of the webpage to analyze
        
    Returns:
        tuple: (html_content, screenshot, driver)
    """
    # First try with simple requests for efficiency
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        static_html = response.text
    except Exception as e:
        print(f"Simple request failed: {e}, falling back to Selenium")
        static_html = None
    
    # Set up Selenium for full rendering
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.options import Options
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get(url)
        # Wait for page to fully load
        import time
        time.sleep(5)  # Simple wait
        
        # Take screenshot for visual analysis
        screenshot = driver.get_screenshot_as_png()
        
        # Get the fully rendered HTML
        rendered_html = driver.page_source
        
        return (static_html or rendered_html, screenshot, driver)
    except Exception as e:
        driver.quit()
        raise Exception(f"Failed to load page with Selenium: {e}")
```

### 3. Color Palette Extraction

```python
def extract_color_palette(screenshot, driver, html_content):
    """
    Extract the dominant color palette from the webpage.
    Uses multiple methods to ensure comprehensive color extraction.
    
    Args:
        screenshot: PNG screenshot data from Selenium
        driver: Selenium webdriver instance
        html_content: HTML content of the page
        
    Returns:
        dict: Color palette information
    """
    from colorthief import ColorThief
    from io import BytesIO
    from PIL import Image
    import re
    import cssutils
    import logging
    
    # Disable cssutils log messages
    cssutils.log.setLevel(logging.CRITICAL)
    
    # Create image from screenshot
    img = Image.open(BytesIO(screenshot))
    
    # Method 1: Use ColorThief to get dominant colors from the screenshot
    color_thief = ColorThief(BytesIO(screenshot))
    dominant_colors = color_thief.get_palette(color_count=10, quality=10)
    
    # Method 2: Extract colors from CSS
    colors_from_css = set()
    
    # Extract inline styles
    style_tags = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL)
    for style_content in style_tags:
        sheet = cssutils.parseString(style_content)
        for rule in sheet:
            if rule.type == rule.STYLE_RULE:
                for property in rule.style:
                    if any(color_prop in property.name for color_prop in ['color', 'background', 'border']):
                        colors_from_css.add(property.value)
    
    # Method 3: Use Selenium to extract computed styles of visible elements
    elements = driver.find_elements("css selector", "body *")
    computed_colors = set()
    for element in elements[:100]:  # Limit to first 100 elements for performance
        try:
            bg_color = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundColor", element)
            color = driver.execute_script("return window.getComputedStyle(arguments[0]).color", element)
            if bg_color and bg_color != "rgba(0, 0, 0, 0)":
                computed_colors.add(bg_color)
            if color:
                computed_colors.add(color)
        except:
            continue
    
    # Convert all colors to standardized hex format
    def rgb_to_hex(rgb_str):
        if not rgb_str or 'rgb' not in rgb_str:
            return None
        try:
            # Extract RGB values
            rgb = re.findall(r'\d+', rgb_str)
            if len(rgb) >= 3:
                r, g, b = map(int, rgb[:3])
                return f'#{r:02x}{g:02x}{b:02x}'
        except:
            pass
        return None
    
    # Process the colors
    hex_computed_colors = [rgb_to_hex(c) for c in computed_colors if rgb_to_hex(c)]
    hex_dominant_colors = [f'#{r:02x}{g:02x}{b:02x}' for r, g, b in dominant_colors]
    
    # Determine primary, secondary, accent colors
    all_colors = list(set(hex_dominant_colors + hex_computed_colors))
    
    # If we have enough colors
    if len(all_colors) >= 3:
        primary_color = all_colors[0]
        secondary_color = all_colors[1]
        accent_color = all_colors[2]
        background_color = driver.execute_script("return window.getComputedStyle(document.body).backgroundColor")
        background_color = rgb_to_hex(background_color) or '#ffffff'
        
        text_color = driver.execute_script("return window.getComputedStyle(document.body).color")
        text_color = rgb_to_hex(text_color) or '#000000'
    else:
        # Fallback to basic colors
        primary_color = all_colors[0] if all_colors else '#000000'
        secondary_color = all_colors[1] if len(all_colors) > 1 else '#ffffff'
        accent_color = all_colors[2] if len(all_colors) > 2 else '#0000ff'
        background_color = '#ffffff'
        text_color = '#000000'
    
    return {
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "accent_color": accent_color,
        "background_color": background_color,
        "text_color": text_color,
        "palette": all_colors[:10]  # Include full palette (up to 10 colors)
    }
```

### 4. Typography Extraction

```python
def extract_typography(driver, html_content):
    """
    Extract typography information from the webpage.
    
    Args:
        driver: Selenium webdriver instance
        html_content: HTML content
        
    Returns:
        dict: Typography information
    """
    import re
    
    # Use Selenium to get computed styles for typography
    heading_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    typography = {
        "headings": {},
        "body": {},
        "special": []
    }
    
    # Extract body text typography
    body_element = driver.find_element("css selector", "body")
    body_font = driver.execute_script("return window.getComputedStyle(arguments[0]).fontFamily", body_element)
    body_size = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", body_element)
    body_weight = driver.execute_script("return window.getComputedStyle(arguments[0]).fontWeight", body_element)
    body_line_height = driver.execute_script("return window.getComputedStyle(arguments[0]).lineHeight", body_element)
    
    typography["body"] = {
        "font_family": body_font.strip('"\''),
        "font_size": body_size,
        "font_weight": body_weight,
        "line_height": body_line_height
    }
    
    # Extract heading typography
    for tag in heading_tags:
        elements = driver.find_elements("css selector", tag)
        if elements:
            element = elements[0]  # Take the first one as representative
            font_family = driver.execute_script("return window.getComputedStyle(arguments[0]).fontFamily", element)
            font_size = driver.execute_script("return window.getComputedStyle(arguments[0]).fontSize", element)
            font_weight = driver.execute_script("return window.getComputedStyle(arguments[0]).fontWeight", element)
            
            typography["headings"][tag] = {
                "font_family": font_family.strip('"\''),
                "font_size": font_size,
                "font_weight": font_weight
            }
    
    # Look for Google Fonts or other font imports
    font_imports = []
    # Check for Google Fonts
    google_fonts = re.findall(r'fonts.googleapis.com/css[^"\']+', html_content)
    for font in google_fonts:
        font_imports.append(f"https://{font}")
    
    # Check for @font-face
    font_face = re.findall(r'@font-face\s*{[^}]+}', html_content)
    if font_face:
        typography["custom_fonts"] = True
    
    typography["font_imports"] = font_imports
    
    return typography
```

### 5. Layout and Spacing Analysis

```python
def analyze_layout(driver):
    """
    Analyze layout characteristics like spacing, grid systems, and content width.
    
    Args:
        driver: Selenium webdriver instance
        
    Returns:
        dict: Layout specifications
    """
    # Get page dimensions
    page_width = driver.execute_script("return document.body.clientWidth")
    page_height = driver.execute_script("return document.body.clientHeight")
    
    # Analyze main container width (often not 100% of viewport)
    main_elements = driver.find_elements("css selector", "main, .main, #main, .container, #container, .content, #content")
    container_width = None
    
    if main_elements:
        container_width = driver.execute_script("return arguments[0].clientWidth", main_elements[0])
    
    # Analyze grid systems
    potential_grids = driver.find_elements("css selector", ".row, .grid, .columns, [class*='grid'], [class*='col-']")
    has_grid = len(potential_grids) > 3  # Arbitrary threshold
    
    # Detect common spacing units by analyzing margins and paddings of multiple elements
    spacing_samples = []
    elements = driver.find_elements("css selector", "body *")[:50]  # Sample first 50 elements
    
    for element in elements:
        try:
            margin = driver.execute_script("return window.getComputedStyle(arguments[0]).marginBottom", element)
            padding = driver.execute_script("return window.getComputedStyle(arguments[0]).paddingTop", element)
            
            # Extract numeric values
            if margin and margin != '0px':
                spacing_samples.append(margin)
            if padding and padding != '0px':
                spacing_samples.append(padding)
        except:
            continue
    
    # Count occurrences to find common spacing units
    from collections import Counter
    spacing_counts = Counter(spacing_samples)
    common_spacing = [space for space, count in spacing_counts.most_common(5)]
    
    return {
        "page_dimensions": {
            "width": page_width,
            "height": page_height
        },
        "container_width": container_width,
        "has_grid_system": has_grid,
        "common_spacing_units": common_spacing
    }
```

### 6. Component and Style Pattern Detection

```python
def detect_component_patterns(driver, html_content):
    """
    Detect common UI components and their styling patterns.
    
    Args:
        driver: Selenium webdriver instance
        html_content: HTML content
        
    Returns:
        dict: Component specifications
    """
    import re
    
    components = {
        "buttons": {},
        "cards": {},
        "forms": {},
        "navigation": {},
        "detected_patterns": []
    }
    
    # Analyze buttons
    buttons = driver.find_elements("css selector", "button, .btn, [type='button'], [type='submit'], [class*='button']")
    if buttons:
        sample_button = buttons[0]
        button_bg = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundColor", sample_button)
        button_color = driver.execute_script("return window.getComputedStyle(arguments[0]).color", sample_button)
        button_padding = driver.execute_script("return window.getComputedStyle(arguments[0]).padding", sample_button)
        button_border = driver.execute_script("return window.getComputedStyle(arguments[0]).border", sample_button)
        button_radius = driver.execute_script("return window.getComputedStyle(arguments[0]).borderRadius", sample_button)
        
        components["buttons"] = {
            "background_color": button_bg,
            "text_color": button_color,
            "padding": button_padding,
            "border": button_border,
            "border_radius": button_radius
        }
    
    # Analyze card-like components
    cards = driver.find_elements("css selector", ".card, [class*='card'], article, .box, [class*='box']")
    if cards:
        sample_card = cards[0]
        card_bg = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundColor", sample_card)
        card_shadow = driver.execute_script("return window.getComputedStyle(arguments[0]).boxShadow", sample_card)
        card_radius = driver.execute_script("return window.getComputedStyle(arguments[0]).borderRadius", sample_card)
        card_padding = driver.execute_script("return window.getComputedStyle(arguments[0]).padding", sample_card)
        
        components["cards"] = {
            "background_color": card_bg,
            "box_shadow": card_shadow,
            "border_radius": card_radius,
            "padding": card_padding
        }
    
    # Analyze form styles
    forms = driver.find_elements("css selector", "form, .form")
    inputs = driver.find_elements("css selector", "input[type='text'], textarea")
    
    if inputs:
        sample_input = inputs[0]
        input_border = driver.execute_script("return window.getComputedStyle(arguments[0]).border", sample_input)
        input_radius = driver.execute_script("return window.getComputedStyle(arguments[0]).borderRadius", sample_input)
        input_padding = driver.execute_script("return window.getComputedStyle(arguments[0]).padding", sample_input)
        
        components["forms"]["inputs"] = {
            "border": input_border,
            "border_radius": input_radius,
            "padding": input_padding
        }
    
    # Analyze navigation
    nav = driver.find_elements("css selector", "nav, header, .navigation, .navbar, #navbar")
    if nav:
        nav_bg = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundColor", nav[0])
        nav_height = driver.execute_script("return arguments[0].clientHeight", nav[0])
        
        components["navigation"] = {
            "background_color": nav_bg,
            "height": nav_height
        }
    
    # Detect common style patterns (classes that appear frequently)
    class_pattern = re.compile(r'class=["\']([^"\']+)["\']')
    class_matches = class_pattern.findall(html_content)
    
    all_classes = []
    for match in class_matches:
        classes = match.split()
        all_classes.extend(classes)
    
    # Count occurrences
    from collections import Counter
    class_counter = Counter(all_classes)
    
    # Find potential utility classes or naming patterns
    common_patterns = []
    utility_prefixes = ['bg-', 'text-', 'p-', 'm-', 'flex-', 'grid-', 'border-', 'rounded-']
    
    for cls, count in class_counter.most_common(30):
        for prefix in utility_prefixes:
            if cls.startswith(prefix) and count > 3:  # Arbitrary threshold
                common_patterns.append(cls)
                break
    
    components["detected_patterns"] = common_patterns[:15]  # Top 15 patterns
    
    return components
```

### 7. Image and Icon Analysis

```python
def analyze_images_and_icons(driver, html_content):
    """
    Analyze images and icons for style patterns.
    
    Args:
        driver: Selenium webdriver instance
        html_content: HTML content
        
    Returns:
        dict: Image and icon specifications
    """
    import re
    
    image_info = {
        "has_svg_icons": False,
        "has_icon_font": False,
        "icon_classes": [],
        "image_style": {},
        "logo_detected": False
    }
    
    # Check for SVG usage
    svg_elements = driver.find_elements("css selector", "svg")
    if svg_elements:
        image_info["has_svg_icons"] = True
    
    # Check for icon fonts (FontAwesome, Material Icons, etc.)
    icon_font_patterns = [
        r'font-awesome',
        r'fa-',
        r'material-icons',
        r'glyphicon',
        r'icon-',
        r'feather',
        r'bi-'  # Bootstrap Icons
    ]
    
    for pattern in icon_font_patterns:
        if re.search(pattern, html_content, re.IGNORECASE):
            image_info["has_icon_font"] = True
            break
    
    # Extract icon classes
    if image_info["has_icon_font"]:
        for pattern in icon_font_patterns:
            icon_matches = re.findall(f'class=["\']([^"\']*{pattern}[^"\']*)["\']', html_content, re.IGNORECASE)
            for match in icon_matches:
                classes = match.split()
                for cls in classes:
                    if pattern in cls.lower():
                        image_info["icon_classes"].append(cls)
    
    # Analyze image styling
    images = driver.find_elements("css selector", "img")
    if images:
        sample_image = images[0]
        try:
            img_border_radius = driver.execute_script("return window.getComputedStyle(arguments[0]).borderRadius", sample_image)
            img_shadow = driver.execute_script("return window.getComputedStyle(arguments[0]).boxShadow", sample_image)
            img_border = driver.execute_script("return window.getComputedStyle(arguments[0]).border", sample_image)
            
            image_info["image_style"] = {
                "border_radius": img_border_radius,
                "box_shadow": img_shadow,
                "border": img_border
            }
        except:
            pass
    
    # Look for logo (typically in header, with class/id containing 'logo')
    logo_elements = driver.find_elements("css selector", ".logo, #logo, [class*='logo'], [id*='logo'], header img, [alt*='logo' i]")
    if logo_elements:
        image_info["logo_detected"] = True
        try:
            logo = logo_elements[0]
            if logo.tag_name == 'img':
                image_info["logo_url"] = logo.get_attribute("src")
            else:
                # It might be a background image
                logo_bg = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundImage", logo)
                if logo_bg and logo_bg != 'none':
                    image_info["logo_url"] = logo_bg.replace('url("', '').replace('")', '')
        except:
            pass
    
    return image_info
```

### 8. Design Schema Generation

```python
def generate_design_schema(url, colors, typography, layout, components, images):
    """
    Combine all extracted information into a comprehensive design schema.
    
    Args:
        url: The analyzed URL
        colors: Color palette info
        typography: Typography info
        layout: Layout info
        components: Component info
        images: Image and icon info
        
    Returns:
        dict: Complete design schema
    """
    import datetime
    
    schema = {
        "metadata": {
            "source_url": url,
            "extraction_date": datetime.datetime.now().isoformat(),
            "schema_version": "1.0"
        },
        "colors": colors,
        "typography": typography,
        "layout": layout,
        "components": components,
        "images": images,
        "design_summary": {
            "style_keywords": []
        }
    }
    
    # Generate style keywords based on the extracted data
    keywords = []
    
    # Analyze colors to determine style
    if colors["palette"]:
        # Determine if there's high contrast
        high_contrast = len(colors["palette"]) > 5
        if high_contrast:
            keywords.append("high-contrast")
        
        # Check for monochromatic scheme
        if len(colors["palette"]) <= 3:
            keywords.append("monochromatic")
    
    # Analyze radius to detect rounded vs sharp
    if components["buttons"].get("border_radius", "0px") != "0px":
        keywords.append("rounded")
    else:
        keywords.append("sharp-edges")
    
    # Check for shadows
    has_shadows = (
        components["cards"].get("box_shadow", "none") != "none" or
        images["image_style"].get("box_shadow", "none") != "none"
    )
    if has_shadows:
        keywords.append("shadowed")
    else:
        keywords.append("flat")
    
    # Typography style
    serif_fonts = ["serif", "georgia", "times", "palatino"]
    heading_font = typography["headings"].get("h1", {}).get("font_family", "").lower()
    
    if any(serif in heading_font for serif in serif_fonts):
        keywords.append("serif")
    else:
        keywords.append("sans-serif")
    
    # Layout keywords
    if layout["has_grid_system"]:
        keywords.append("grid-based")
    
    if images["has_svg_icons"]:
        keywords.append("modern-icons")
    
    # Combine everything for a general style assessment
    if "rounded" in keywords and "shadowed" in keywords:
        keywords.append("material-inspired")
    
    if "flat" in keywords and "sharp-edges" in keywords:
        keywords.append("minimalist")
    
    schema["design_summary"]["style_keywords"] = keywords
    
    return schema
```

### 9. JSON Schema Validation

```python
def validate_schema(design_schema):
    """
    Validate the generated schema against a defined JSON schema.
    
    Args:
        design_schema: The generated design schema
        
    Returns:
        bool: Validation result
    """
    import jsonschema
    
    # Define a schema for validation
    json_schema = {
        "type": "object",
        "required": ["metadata", "colors", "typography", "layout", "components", "images"],
        "properties": {
            "metadata": {
                "type": "object",
                "required": ["source_url", "extraction_date", "schema_version"]
            },
            "colors": {
                "type": "object",
                "required": ["primary_color", "secondary_color", "accent_color", "palette"]
            },
            "typography": {
                "type": "object",
                "required": ["headings", "body"]
            },
            "layout": {
                "type": "object",
                "required": ["page_dimensions", "common_spacing_units"]
            },
            "components": {
                "type": "object"
            },
            "images": {
                "type": "object"
            },
            "design_summary": {
                "type": "object",
                "required": ["style_keywords"]
            }
        }
    }
    
    try:
        jsonschema.validate(instance=design_schema, schema=json_schema)
        return True
    except jsonschema.exceptions.ValidationError as e:
        print(f"Schema validation error: {e}")
        return False
```

### 10. Main Program and Output

```python
def extract_design_scheme(url, output_file=None):
    """
    Main function to extract a design scheme from a URL.
    
    Args:
        url (str): The URL to analyze
        output_file (str, optional): Path to save the JSON output
        
    Returns:
        dict: The extracted design scheme
    """
    import json
    
    try:
        print(f"Analyzing {url}...")
        
        # Step 1: Fetch the webpage
        html_content, screenshot, driver = fetch_webpage(url)
        
        # Step 2: Extract components
        colors = extract_color_palette(screenshot, driver, html_content)
        typography = extract_typography(driver, html_content)
        layout = analyze_layout(driver)
        components = detect_component_patterns(driver, html_content)
        images = analyze_images_and_icons(driver, html_content)
        
        # Close the WebDriver
        driver.quit()
        
        # Step 3: Generate comprehensive schema
        design_schema = generate_design_schema(url, colors, typography, layout, components, images)
        
        # Step 4: Validate schema
        if not validate_schema(design_schema):
            print("Warning: Generated schema did not pass validation")
        
        # Step 5: Output the result
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(design_schema, f, indent=2)
            print(f"Design scheme saved to {output_file}")
        
        # Return the schema
        return design_schema
    
    except Exception as e:
        print(f"Error extracting design scheme: {e}")
        if 'driver' in locals():
            driver.quit()
        raise
```

### 11. Command-Line Interface

```python
def main():
    """Command line interface for the design scheme extractor."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(
        description='Extract design scheme from a webpage for AI-assisted brand-consistent graphics.'
    )
    parser.add_argument('url', help='URL of the webpage to analyze')
    parser.add_argument('-o', '--output', help='Output JSON file path')
    parser.add_argument('-p', '--pretty', action='store_true', help='Print pretty JSON to console')
    
    args = parser.parse_args()
    
    try:
        design_scheme = extract_design_scheme(args.url, args.output)
        
        if args.pretty:
            print(json.dumps(design_scheme, indent=2))
        else:
            print("Design scheme extraction complete!")
            print(f"Style keywords: {', '.join(design_scheme['design_summary']['style_keywords'])}")
            print(f"Primary color: {design_scheme['colors']['primary_color']}")
            print(f"Secondary color: {design_scheme['colors']['secondary_color']}")
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

## Complete Script and Usage

Put all the functions together into a single Python script called `design_scheme_extractor.py`. Then you can use it as follows:

```bash
# Basic usage - prints a summary to console
python design_scheme_extractor.py https://example.com

# Save the full schema to a JSON file
python design_scheme_extractor.py https://example.com -o design_scheme.json

# Print the full JSON schema to console
python design_scheme_extractor.py https://example.com -p
```

## Example Output Structure

The output JSON will have this structure:

```json
{
  "metadata": {
    "source_url": "https://example.com",
    "extraction_date": "2025-04-05T14:30:45.123456",
    "schema_version": "1.0"
  },
  "colors": {
    "primary_color": "#1a73e8",
    "secondary_color": "#34a853",
    "accent_color": "#fbbc04",
    "background_color": "#ffffff",
    "text_color": "#202124",
    "palette": ["#1a73e8", "#34a853", "#fbbc04", "#ea4335", "#5f6368", ...]
  },
  "typography": {
    "headings": {
      "h1": {"font_family": "Google Sans", "font_size": "32px", "font_weight": "700"},
      "h2": {"font_family": "Google Sans", "font_size": "24px", "font_weight": "700"}
    },
    "body": {
      "font_family": "Roboto",
      "font_size": "16px",
      "font_weight": "400",
      "line_height": "1.5"
    },
    "font_imports": ["https://fonts.googleapis.com/css?family=Roboto:400,500,700"]
  },
  "layout": {
    "page_dimensions": {"width": 1280, "height": 4500},
    "container_width": 1000,
    "has_grid_system": true,
    "common_spacing_units": ["16px", "24px", "8px", "32px", "4px"]
  },
  "components": {
    "buttons": {
      "background_color": "rgb(26, 115, 232)",
      "text_color": "rgb(255, 255, 255)",
      "padding": "10px 24px",
      "border": "none",
      "border_radius": "4px"
    },
    "cards": {
      "background_color": "rgb(255, 255, 255)",
      "box_shadow": "0 1px 2px 0 rgba(60, 64, 67, 0.3)",
      "border_radius": "8px",
      "padding": "16px"
    }
  },
  "images": {
    "has_svg_icons": true,
    "has_icon_font": false,
    "logo_detected": true
  },
  "design_summary": {
    "style_keywords": ["modern", "material-inspired", "rounded", "shadowed", "grid-based"]
  }
}
```

## Review and Considerations

The implementation:

1. Uses multiple methods to extract color palettes for more accurate results
2. Handles both static and JavaScript-rendered pages via Selenium
3. Analyzes component styles to capture brand specifics
4. Generates useful design keywords to describe the overall style


## Error Handling and Robustness

Let's add some robust error handling to ensure the program works well with various websites:

```python
def safe_execute_script(driver, script, element=None, default=None):
    """
    Execute JavaScript in a safe manner with proper error handling.
    
    Args:
        driver: Selenium webdriver instance
        script: JavaScript to execute
        element: Element to execute against (optional)
        default: Default value if execution fails
        
    Returns:
        Result of the script or default value if it fails
    """
    try:
        if element:
            return driver.execute_script(script, element)
        else:
            return driver.execute_script(script)
    except Exception as e:
        print(f"Script execution error: {e}")
        return default
```

### Handling Different Website Types

```python
def determine_website_type(html_content, url):
    """
    Determine the type/category of website to better tailor analysis.
    
    Args:
        html_content: HTML content of the page
        url: URL of the website
        
    Returns:
        str: Website type category
    """
    import re
    
    # Check for common CMS or frameworks
    cms_patterns = {
        "wordpress": r'wp-content|wordpress|wp-includes',
        "shopify": r'shopify\.|myshopify',
        "wix": r'wix\.com|wixsite',
        "webflow": r'webflow',
        "bootstrap": r'bootstrap',
        "tailwind": r'tailwindcss|tailwind\.css',
        "material": r'material-ui|mui|mdl-',
        "react": r'react|reactjs',
        "angular": r'ng-|angular',
        "vue": r'vue|vue\.js'
    }
    
    # Check for e-commerce indicators
    ecommerce_patterns = r'cart|checkout|product|shop|store|price'
    
    # Check for blog indicators
    blog_patterns = r'blog|article|post|author|comment'
    
    # Detect website type
    for cms, pattern in cms_patterns.items():
        if re.search(pattern, html_content, re.IGNORECASE):
            return cms
    
    if re.search(ecommerce_patterns, html_content, re.IGNORECASE):
        return "ecommerce"
    
    if re.search(blog_patterns, html_content, re.IGNORECASE):
        return "blog"
    
    # Check URL TLD for clues
    if '.gov' in url:
        return "government"
    if '.edu' in url:
        return "education"
    if '.org' in url:
        return "organization"
    
    return "general"
```

### Extensibility with Plugin System

```python
class DesignSchemeExtractorPlugin:
    """Base class for design scheme extractor plugins."""
    
    def __init__(self, website_type):
        self.website_type = website_type
    
    def applies_to(self, detected_type):
        """Check if this plugin applies to the detected website type."""
        return detected_type == self.website_type
    
    def enhance_schema(self, design_schema, html_content, driver=None):
        """
        Enhance the design schema with plugin-specific information.
        
        Args:
            design_schema: Current design schema
            html_content: HTML content
            driver: Selenium webdriver instance (optional)
            
        Returns:
            dict: Enhanced design schema
        """
        return design_schema

# Example plugin for WordPress sites
class WordPressPlugin(DesignSchemeExtractorPlugin):
    def __init__(self):
        super().__init__("wordpress")
    
    def enhance_schema(self, design_schema, html_content, driver=None):
        import re
        
        # Try to detect WordPress theme
        theme_match = re.search(r'wp-content/themes/([^/]+)', html_content)
        if theme_match:
            theme_name = theme_match.group(1)
            design_schema["metadata"]["cms"] = {
                "type": "wordpress",
                "theme": theme_name
            }
        
        # WordPress often has specific widget areas and standard components
        if driver:
            sidebar = driver.find_elements("css selector", ".widget-area, .sidebar, #sidebar")
            if sidebar:
                design_schema["components"]["sidebar"] = {
                    "present": True,
                    "width": safe_execute_script(driver, "return arguments[0].clientWidth", sidebar[0], 0)
                }
        
        return design_schema

# Plugin registry
def get_plugins():
    """Get all available plugins."""
    return [WordPressPlugin()]

# Plugin integration in main extraction function
def enhance_with_plugins(design_schema, website_type, html_content, driver=None):
    """Apply plugins to enhance the design schema."""
    plugins = get_plugins()
    
    for plugin in plugins:
        if plugin.applies_to(website_type):
            design_schema = plugin.enhance_schema(design_schema, html_content, driver)
    
    return design_schema
```

## Output Optimization for AI Consumption

Let's add specific formatting optimizations to make the output more AI-friendly:

```python
def optimize_for_ai_consumption(design_schema):
    """
    Optimize the design schema specifically for AI system consumption.
    
    Args:
        design_schema: The extracted design schema
        
    Returns:
        dict: AI-optimized schema
    """
    # Add explicit AI-friendly features and descriptions
    ai_schema = design_schema.copy()
    
    # Add natural language descriptions
    descriptions = {
        "style": "",
        "color_scheme": "",
        "typography": "",
        "components": ""
    }
    
    # Generate natural language description of style
    style_keywords = design_schema["design_summary"]["style_keywords"]
    descriptions["style"] = f"This website has a {', '.join(style_keywords[:-1]) + ' and ' + style_keywords[-1] if len(style_keywords) > 1 else style_keywords[0]} design style."
    
    # Generate natural language description of color scheme
    primary = design_schema["colors"]["primary_color"]
    secondary = design_schema["colors"]["secondary_color"]
    accent = design_schema["colors"]["accent_color"]
    bg = design_schema["colors"]["background_color"]
    
    descriptions["color_scheme"] = f"The color scheme uses {primary} as the primary color, {secondary} as the secondary color, and {accent} as an accent color against a {bg} background."
    
    # Generate natural language description of typography
    body_font = design_schema["typography"]["body"].get("font_family", "default sans-serif")
    if design_schema["typography"]["headings"]:
        heading_font = next(iter(design_schema["typography"]["headings"].values())).get("font_family", body_font)
        if heading_font == body_font:
            descriptions["typography"] = f"Typography consistently uses {body_font} throughout the site."
        else:
            descriptions["typography"] = f"Typography uses {heading_font} for headings and {body_font} for body text."
    
    # Generate natural language description of components
    component_desc = []
    if design_schema["components"]["buttons"]:
        btn_radius = design_schema["components"]["buttons"].get("border_radius", "0px")
        btn_style = "rounded" if btn_radius != "0px" else "square"
        component_desc.append(f"{btn_style} buttons")
    
    if design_schema["components"]["cards"]:
        card_shadow = design_schema["components"]["cards"].get("box_shadow", "none")
        card_style = "shadowed" if card_shadow != "none" else "flat"
        component_desc.append(f"{card_style} cards or panels")
    
    if design_schema["images"]["has_svg_icons"]:
        component_desc.append("SVG icons")
    elif design_schema["images"]["has_icon_font"]:
        component_desc.append("icon fonts")
    
    if component_desc:
        descriptions["components"] = f"The site features {', '.join(component_desc[:-1]) + ' and ' + component_desc[-1] if len(component_desc) > 1 else component_desc[0]}."
    
    # Add the descriptions to the schema
    ai_schema["ai_consumption"] = {
        "descriptions": descriptions,
        "color_palette_hex": design_schema["colors"]["palette"],
        "suggested_prompt_elements": [
            f"Use a {', '.join(style_keywords)} design style",
            f"Use {primary} as the primary color, {secondary} as the secondary color, and {accent} as accent color",
            f"Use {body_font} for typography",
            f"Maintain consistent spacing using multiples of {design_schema['layout']['common_spacing_units'][0] if design_schema['layout']['common_spacing_units'] else '8px'}"
        ]
    }
    
    return ai_schema
```

## Integration with Design Libraries

```python
def generate_design_code_snippets(design_schema):
    """
    Generate code snippets based on the extracted design.
    
    Args:
        design_schema: The extracted design schema
        
    Returns:
        dict: Code snippets for various platforms/libraries
    """
    colors = design_schema["colors"]
    primary = colors["primary_color"]
    secondary = colors["secondary_color"]
    accent = colors["accent_color"]
    background = colors["background_color"]
    text = colors["text_color"]
    
    # Typography
    body_font = design_schema["typography"]["body"].get("font_family", "sans-serif")
    body_size = design_schema["typography"]["body"].get("font_size", "16px")
    
    # Get heading font from h1 or fall back to body font
    heading_font = body_font
    if "h1" in design_schema["typography"]["headings"]:
        heading_font = design_schema["typography"]["headings"]["h1"].get("font_family", body_font)
    
    # Spacing
    spacing_unit = "8px"
    if design_schema["layout"]["common_spacing_units"]:
        spacing_unit = design_schema["layout"]["common_spacing_units"][0]
    
    # Border radius
    border_radius = "0"
    if design_schema["components"]["buttons"]:
        border_radius = design_schema["components"]["buttons"].get("border_radius", "0").replace("px", "")
    
    # Generate CSS Variables
    css_variables = f"""
:root {{
  /* Colors */
  --primary-color: {primary};
  --secondary-color: {secondary};
  --accent-color: {accent};
  --background-color: {background};
  --text-color: {text};
  
  /* Typography */
  --body-font: {body_font};
  --heading-font: {heading_font};
  --body-font-size: {body_size};
  
  /* Spacing */
  --spacing-unit: {spacing_unit};
  --spacing-small: calc(var(--spacing-unit) * 0.5);
  --spacing-medium: var(--spacing-unit);
  --spacing-large: calc(var(--spacing-unit) * 2);
  --spacing-xlarge: calc(var(--spacing-unit) * 4);
  
  /* Border Radius */
  --border-radius: {border_radius}px;
}}
"""
    
    # Generate Tailwind CSS config
    tailwind_config = f"""
module.exports = {{
  theme: {{
    extend: {{
      colors: {{
        primary: '{primary}',
        secondary: '{secondary}',
        accent: '{accent}',
        background: '{background}',
        text: '{text}',
      }},
      fontFamily: {{
        body: ['{body_font.split(",")[0].strip()}', 'sans-serif'],
        heading: ['{heading_font.split(",")[0].strip()}', 'sans-serif'],
      }},
      spacing: {{
        'unit': '{spacing_unit.replace("px", "")}px',
      }},
      borderRadius: {{
        DEFAULT: '{border_radius}px',
      }},
    }},
  }},
  variants: {{
    extend: {{}},
  }},
  plugins: [],
}}
"""
    
    # Generate React styled-components theme
    styled_components = f"""
const theme = {{
  colors: {{
    primary: '{primary}',
    secondary: '{secondary}',
    accent: '{accent}',
    background: '{background}',
    text: '{text}',
  }},
  fonts: {{
    body: '{body_font}',
    heading: '{heading_font}',
  }},
  fontSizes: {{
    body: '{body_size}',
  }},
  spacing: {{
    unit: '{spacing_unit}',
    small: 'calc({spacing_unit} * 0.5)',
    medium: '{spacing_unit}',
    large: 'calc({spacing_unit} * 2)',
    xlarge: 'calc({spacing_unit} * 4)',
  }},
  borderRadius: '{border_radius}px',
}};

export default theme;
"""
    
    # Store all snippets
    code_snippets = {
        "css_variables": css_variables,
        "tailwind_config": tailwind_config,
        "styled_components": styled_components
    }
    
    return code_snippets
```

## Documentation and User Guide

```python
def generate_documentation(design_schema):
    """
    Generate markdown documentation for the extracted design scheme.
    
    Args:
        design_schema: The extracted design schema
        
    Returns:
        str: Markdown documentation
    """
    # Extract key information from schema
    colors = design_schema["colors"]
    typography = design_schema["typography"]
    components = design_schema["components"]
    
    # Generate color palette documentation
    color_docs = f"""## Color Palette

| Role | Color | Hex Code |
|------|-------|----------|
| Primary | <div style="background-color: {colors['primary_color']}; width: 20px; height: 20px; display: inline-block; border: 1px solid #ccc;"></div> | {colors['primary_color']} |
| Secondary | <div style="background-color: {colors['secondary_color']}; width: 20px; height: 20px; display: inline-block; border: 1px solid #ccc;"></div> | {colors['secondary_color']} |
| Accent | <div style="background-color: {colors['accent_color']}; width: 20px; height: 20px; display: inline-block; border: 1px solid #ccc;"></div> | {colors['accent_color']} |
| Background | <div style="background-color: {colors['background_color']}; width: 20px; height: 20px; display: inline-block; border: 1px solid #ccc;"></div> | {colors['background_color']} |
| Text | <div style="background-color: {colors['text_color']}; width: 20px; height: 20px; display: inline-block; border: 1px solid #ccc;"></div> | {colors['text_color']} |

### Full Palette

"""
    
    for i, color in enumerate(colors['palette'][:10]):
        color_docs += f"<div style=\"background-color: {color}; width: 30px; height: 30px; display: inline-block; margin: 2px; border: 1px solid #ccc;\"></div> "
    
    # Generate typography documentation
    typo_docs = f"""## Typography

### Body Text
- Font Family: {typography['body'].get('font_family', 'Not specified')}
- Font Size: {typography['body'].get('font_size', 'Not specified')}
- Line Height: {typography['body'].get('line_height', 'Not specified')}

### Headings
"""
    
    for heading, values in typography['headings'].items():
        typo_docs += f"#### {heading.upper()}\n"
        typo_docs += f"- Font Family: {values.get('font_family', 'Not specified')}\n"
        typo_docs += f"- Font Size: {values.get('font_size', 'Not specified')}\n"
        typo_docs += f"- Font Weight: {values.get('font_weight', 'Not specified')}\n\n"
    
    # Generate components documentation
    component_docs = f"""## Components

### Buttons
"""
    
    if components['buttons']:
        button_docs = ""
        for prop, value in components['buttons'].items():
            button_docs += f"- {prop.replace('_', ' ').title()}: {value}\n"
        component_docs += button_docs
    else:
        component_docs += "- No button styles detected\n"
    
    component_docs += f"""
### Cards/Containers
"""
    
    if components['cards']:
        card_docs = ""
        for prop, value in components['cards'].items():
            card_docs += f"- {prop.replace('_', ' ').title()}: {value}\n"
        component_docs += card_docs
    else:
        component_docs += "- No card styles detected\n"
    
    # Generate AI-ready summary
    ai_prompt_docs = f"""## AI Integration Guide

When generating graphics to match this design, consider the following key elements:

1. **Design Style:** {', '.join(design_schema['design_summary']['style_keywords'])}
2. **Color Usage:**
   - Use {colors['primary_color']} as the primary color
   - Use {colors['secondary_color']} as the secondary color
   - Use {colors['accent_color']} for accents and highlights
   - Use {colors['background_color']} for backgrounds
   - Use {colors['text_color']} for text

3. **Typography:**
   - Main font: {typography['body'].get('font_family', 'system-ui')}
   - For headings: {next(iter(typography['headings'].values())).get('font_family', typography['body'].get('font_family', 'system-ui')) if typography['headings'] else typography['body'].get('font_family', 'system-ui')}

4. **Visual Elements:**
"""
    
    if design_schema['components']['detected_patterns']:
        ai_prompt_docs += "   - Common CSS patterns: " + ", ".join(design_schema['components']['detected_patterns'][:5]) + "\n"
    
    if design_schema['images']['has_svg_icons']:
        ai_prompt_docs += "   - Use SVG icons to match the site's style\n"
    elif design_schema['images']['has_icon_font']:
        ai_prompt_docs += "   - Use icon fonts similar to the site\n"
    
    # Combine all documentation
    full_docs = f"""# Design Scheme Documentation
*Extracted from: {design_schema['metadata']['source_url']}*
*Date: {design_schema['metadata']['extraction_date']}*

{color_docs}

{typo_docs}

{component_docs}

{ai_prompt_docs}
"""
    
    return full_docs
```

## Extended Main Program

Now let's update the main extraction function to incorporate the new features:

```python
def extract_design_scheme_extended(url, output_file=None, generate_docs=True, optimize_ai=True, generate_code=True):
    """
    Extended version of the main function to extract a design scheme from a URL.
    
    Args:
        url (str): The URL to analyze
        output_file (str, optional): Path to save the JSON output
        generate_docs (bool): Generate markdown documentation
        optimize_ai (bool): Create AI-optimized version of the schema
        generate_code (bool): Generate code snippets
        
    Returns:
        dict: The extracted design scheme and additional assets
    """
    import json
    import os
    
    result = {
        "design_schema": None,
        "documentation": None,
        "code_snippets": None
    }
    
    try:
        print(f"Analyzing {url}...")
        
        # Step 1: Fetch the webpage
        html_content, screenshot, driver = fetch_webpage(url)
        
        # Step 2: Determine website type
        website_type = determine_website_type(html_content, url)
        print(f"Detected website type: {website_type}")
        
        # Step 3: Extract components
        colors = extract_color_palette(screenshot, driver, html_content)
        typography = extract_typography(driver, html_content)
        layout = analyze_layout(driver)
        components = detect_component_patterns(driver, html_content)
        images = analyze_images_and_icons(driver, html_content)
        
        # Step 4: Generate comprehensive schema
        design_schema = generate_design_schema(url, colors, typography, layout, components, images)
        
        # Step 5: Enhance with plugins
        design_schema = enhance_with_plugins(design_schema, website_type, html_content, driver)
        
        # Close the WebDriver
        driver.quit()
        
        # Step 6: Validate schema
        if not validate_schema(design_schema):
            print("Warning: Generated schema did not pass validation")
        
        # Store the base schema
        result["design_schema"] = design_schema
        
        # Step a7: Generate AI-optimized version
        if optimize_ai:
            ai_schema = optimize_for_ai_consumption(design_schema)
            result["ai_optimized_schema"] = ai_schema
        
        # Step 8: Generate code snippets
        if generate_code:
            code_snippets = generate_design_code_snippets(design_schema)
            result["code_snippets"] = code_snippets
        
        # Step 9: Generate documentation
        if generate_docs:
            documentation = generate_documentation(design_schema)
            result["documentation"] = documentation
        
        # Step 10: Output results
        if output_file:
            base_name, ext = os.path.splitext(output_file)
            
            # Save main schema
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(design_schema, f, indent=2)
            print(f"Design scheme saved to {output_file}")
            
            # Save documentation if generated
            if generate_docs:
                doc_file = f"{base_name}_docs.md"
                with open(doc_file, 'w', encoding='utf-8') as f:
                    f.write(documentation)
                print(f"Documentation saved to {doc_file}")
            
            # Save AI-optimized schema if generated
            if optimize_ai:
                ai_file = f"{base_name}_ai.json"
                with open(ai_file, 'w', encoding='utf-8') as f:
                    json.dump(ai_schema, f, indent=2)
                print(f"AI-optimized schema saved to {ai_file}")
            
            # Save code snippets if generated
            if generate_code:
                for name, snippet in code_snippets.items():
                    ext = ".js" if "config" in name else ".css" if "css" in name else ".js"
                    snippet_file = f"{base_name}_{name}{ext}"
                    with open(snippet_file, 'w', encoding='utf-8') as f:
                        f.write(snippet)
                    print(f"{name} saved to {snippet_file}")
        
        return result
    
    except Exception as e:
        print(f"Error extracting design scheme: {e}")
        if 'driver' in locals():
            driver.quit()
        import traceback
        traceback.print_exc()
        return result
```

## Updated Command-Line Interface

```python
def main_extended():
    """Extended command line interface for the design scheme extractor."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(
        description='Extract design scheme from a webpage for AI-assisted brand-consistent graphics.'
    )
    parser.add_argument('url', help='URL of the webpage to analyze')
    parser.add_argument('-o', '--output', help='Output JSON file path')
    parser.add_argument('-p', '--pretty', action='store_true', help='Print pretty JSON to console')
    parser.add_argument('--no-docs', action='store_true', help='Skip documentation generation')
    parser.add_argument('--no-code', action='store_true', help='Skip code snippet generation')
    parser.add_argument('--no-ai', action='store_true', help='Skip AI optimization')
    parser.add_argument('--format', choices=['json', 'yaml'], default='json', help='Output format (default: json)')
    
    args = parser.parse_args()
    
    try:
        result = extract_design_scheme_extended(
            args.url, 
            args.output,
            generate_docs=not args.no_docs,
            optimize_ai=not args.no_ai,
            generate_code=not args.no_code
        )
        
        if args.pretty and result["design_schema"]:
            if args.format == 'json':
                print(json.dumps(result["design_schema"], indent=2))
            else:
                import yaml
                print(yaml.dump(result["design_schema"]))
        else:
            print("Design scheme extraction complete!")
            if result["design_schema"]:
                print(f"Style keywords: {', '.join(result['design_schema']['design_summary']['style_keywords'])}")
                print(f"Primary color: {result['design_schema']['colors']['primary_color']}")
                print(f"Secondary color: {result['design_schema']['colors']['secondary_color']}")
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main_extended())
```

## Complete Implementation Review

This implementation:

1. **Extracts Key Design Elements**: Colors, typography, layout, components, and image styles
2. **Handles Various Website Types**: Includes special handling for different CMS and website categories
3. **Extensible via Plugins**: Can be extended with plugins for specific website types
4. **AI-Optimized Output**: Formats outputs specifically for AI consumption
5. **Code Generation**: Creates ready-to-use code snippets for popular design systems
6. **Documentation**: Generates comprehensive markdown documentation
7. **Error Handling**: Includes robust error handling for various edge cases
8. **Command Line Interface**: Provides flexible CLI options

### Strengths

- **Comprehensive**: Captures all major design aspects of a website
- **Flexible**: Works with static and JavaScript-heavy sites
- **Adaptable**: Can handle different website types and styles
- **AI-Ready**: Provides structured output optimized for AI consumption

### Potential Improvements

1. **Performance Optimization**: The current implementation prioritizes thoroughness over speed. For larger sites, this could be slow.
2. **Caching**: Add caching to avoid re-analyzing the same page multiple times.
3. **Custom Color Name Detection**: Add functionality to detect if the website uses custom color names.
4. **Component Library Detection**: Add better detection for specific component libraries (Bootstrap, Material, etc.).
5. **Image Style Analysis**: Enhance image analysis to detect filters, image treatments, or special effects.

## Usage Examples

### Basic Usage

```bash
python design_scheme_extractor.py https://example.com
```

### Save All Outputs

```bash
python design_scheme_extractor.py https://example.com -o example_design.json
```

### Generate Only Schema, No Extra Files

```bash
python design_scheme_extractor.py https://example.com -o example_design.json --no-docs --no-code
```

### Output in YAML Format

```bash
python design_scheme_extractor.py https://example.com --format yaml -p
```

## Final Thoughts

This implementation provides a comprehensive way to extract design schemes from websites and format them for AI consumption. The output can be directly used with LLM systems to generate brand-consistent graphics and designs.

To make this production-ready, consider adding more robust error handling, unit tests, and optimization for performance. For very large websites, you might want to add sampling techniques to analyze only key pages rather than the entire site.
