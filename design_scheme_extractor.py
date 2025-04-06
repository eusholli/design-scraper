#!/usr/bin/env python
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
from io import BytesIO
from PIL import Image
import re
import cssutils
import logging
from colorthief import ColorThief
from collections import Counter
import jsonschema
import json
import datetime
import argparse
import os
import sys
import traceback
import yaml  # Added for YAML output option

# Disable cssutils log messages
cssutils.log.setLevel(logging.CRITICAL)

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
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument('--log-level=3') # Suppress console logs from Chrome/ChromeDriver

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        # Wait for page to fully load
        time.sleep(5)  # Simple wait, might need adjustment for complex pages

        # Take screenshot for visual analysis
        screenshot = driver.get_screenshot_as_png()

        # Get the fully rendered HTML
        rendered_html = driver.page_source

        # Prefer rendered HTML if available, otherwise use static
        html_content_to_use = rendered_html if rendered_html else static_html

        if not html_content_to_use:
             driver.quit()
             raise Exception("Failed to retrieve HTML content using both requests and Selenium.")

        return (html_content_to_use, screenshot, driver)
    except Exception as e:
        driver.quit()
        raise Exception(f"Failed to load page with Selenium: {e}")

def rgb_to_hex(rgb_str):
    """Converts RGB or RGBA string to hex."""
    if not rgb_str or 'rgb' not in rgb_str.lower():
        return None
    try:
        # Extract numeric values using regex, handles rgb(R, G, B) and rgba(R, G, B, A)
        numbers = re.findall(r'\d+', rgb_str)
        if len(numbers) >= 3:
            r, g, b = map(int, numbers[:3])
            # Ensure values are within 0-255 range
            r, g, b = max(0, min(r, 255)), max(0, min(g, 255)), max(0, min(b, 255))
            return f'#{r:02x}{g:02x}{b:02x}'
    except ValueError: # Handle cases where conversion to int fails
        pass
    except Exception as e: # Catch other potential errors
        print(f"Error converting RGB string '{rgb_str}' to hex: {e}")
    return None

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
    # Create image from screenshot
    try:
        img = Image.open(BytesIO(screenshot))
    except Exception as e:
        print(f"Error opening screenshot image: {e}")
        img = None

    # Method 1: Use ColorThief to get dominant colors from the screenshot
    dominant_colors_rgb = []
    if img:
        try:
            color_thief = ColorThief(BytesIO(screenshot))
            # Use a slightly higher quality setting if possible
            dominant_colors_rgb = color_thief.get_palette(color_count=10, quality=5)
        except Exception as e:
            print(f"ColorThief failed: {e}")

    hex_dominant_colors = [f'#{r:02x}{g:02x}{b:02x}' for r, g, b in dominant_colors_rgb]

    # Method 2: Extract colors from CSS in <style> tags
    colors_from_css_rules = set()
    try:
        style_tags = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
        for style_content in style_tags:
            try:
                sheet = cssutils.parseString(style_content, validate=False)
                for rule in sheet:
                    if rule.type == rule.STYLE_RULE:
                        for prop in rule.style:
                            # Check for color-related properties
                            if any(color_prop in prop.name.lower() for color_prop in ['color', 'background', 'border', 'fill', 'stroke']):
                                # Basic check to avoid invalid values like 'inherit', 'transparent', 'none'
                                if prop.value and prop.value.lower() not in ['inherit', 'transparent', 'none', 'initial', 'unset']:
                                    colors_from_css_rules.add(prop.value)
            except Exception as e:
                # Ignore errors from individual style blocks
                # print(f"CSS parsing error in style tag: {e}")
                pass # Continue parsing other tags
    except Exception as e:
        print(f"Error extracting style tags: {e}")

    # Method 3: Use Selenium to extract computed styles of visible elements
    computed_colors_raw = set()
    try:
        # Prioritize common elements like body, headers, buttons, links
        elements_to_check = driver.find_elements("css selector", "body, h1, h2, h3, p, a, button, .btn, .card")
        # Limit the number of elements checked for performance
        elements_to_check = elements_to_check[:150]

        for element in elements_to_check:
            try:
                # Check visibility might be too slow, rely on computed style checks
                # if not element.is_displayed():
                #     continue

                bg_color = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundColor", element)
                color = driver.execute_script("return window.getComputedStyle(arguments[0]).color", element)
                border_color = driver.execute_script("return window.getComputedStyle(arguments[0]).borderColor", element) # Check border color too

                # Add if it's a valid color string and not transparent
                if bg_color and 'rgba(0, 0, 0, 0)' not in bg_color and 'transparent' not in bg_color:
                    computed_colors_raw.add(bg_color)
                if color and 'rgba(0, 0, 0, 0)' not in color and 'transparent' not in color:
                    computed_colors_raw.add(color)
                if border_color and 'rgba(0, 0, 0, 0)' not in border_color and 'transparent' not in border_color and 'none' not in border_color:
                     # Border color can be complex (e.g., "rgb(0, 0, 0) none none"), extract first color part
                     border_color_match = re.match(r'(rgba?\([^)]+\))', border_color)
                     if border_color_match:
                         computed_colors_raw.add(border_color_match.group(1))

            except Exception:
                # Ignore errors for individual elements (e.g., stale element reference)
                continue
    except Exception as e:
        print(f"Error extracting computed styles: {e}")

    # Convert all extracted colors to standardized hex format
    hex_computed_colors = {rgb_to_hex(c) for c in computed_colors_raw}
    hex_css_rule_colors = {rgb_to_hex(c) for c in colors_from_css_rules} # Also convert CSS rule colors

    # Combine and filter valid hex colors
    all_hex_colors = set(hex_dominant_colors) | hex_computed_colors | hex_css_rule_colors
    valid_hex_colors = {c for c in all_hex_colors if c is not None and re.match(r'^#[0-9a-fA-F]{6}$', c)}

    # Determine primary, secondary, accent colors - simplistic approach based on frequency or order
    # A more sophisticated approach might involve color distance, contrast checks, or area coverage analysis
    sorted_colors = list(valid_hex_colors)
    # Try getting body background and text color directly as potential base colors
    try:
        body_bg_color_str = driver.execute_script("return window.getComputedStyle(document.body).backgroundColor")
        body_text_color_str = driver.execute_script("return window.getComputedStyle(document.body).color")
        background_color_hex = rgb_to_hex(body_bg_color_str) or '#ffffff' # Default white
        text_color_hex = rgb_to_hex(body_text_color_str) or '#000000' # Default black
    except Exception as e:
        print(f"Could not get body colors directly: {e}")
        background_color_hex = '#ffffff'
        text_color_hex = '#000000'


    # Prioritize non-grayscale colors if possible for primary/secondary/accent
    non_gray_colors = [c for c in sorted_colors if c.lower() not in [background_color_hex.lower(), text_color_hex.lower()] and not (c[1:3] == c[3:5] == c[5:7])] # Exclude body bg/text and grays

    if len(non_gray_colors) >= 3:
        primary_color = non_gray_colors[0]
        secondary_color = non_gray_colors[1]
        accent_color = non_gray_colors[2]
    elif len(sorted_colors) >= 3:
         # Fallback to using any colors if not enough non-grays
        potential_primaries = [c for c in sorted_colors if c.lower() not in [background_color_hex.lower(), text_color_hex.lower()]]
        primary_color = potential_primaries[0] if potential_primaries else sorted_colors[0]
        potential_secondaries = [c for c in sorted_colors if c.lower() not in [background_color_hex.lower(), text_color_hex.lower(), primary_color.lower()]]
        secondary_color = potential_secondaries[0] if potential_secondaries else (sorted_colors[1] if len(sorted_colors) > 1 else primary_color)
        potential_accents = [c for c in sorted_colors if c.lower() not in [background_color_hex.lower(), text_color_hex.lower(), primary_color.lower(), secondary_color.lower()]]
        accent_color = potential_accents[0] if potential_accents else (sorted_colors[2] if len(sorted_colors) > 2 else secondary_color)
    elif len(sorted_colors) == 2:
        primary_color = sorted_colors[0]
        secondary_color = sorted_colors[1]
        accent_color = primary_color # Fallback accent
    elif len(sorted_colors) == 1:
        primary_color = sorted_colors[0]
        secondary_color = text_color_hex if primary_color.lower() != text_color_hex.lower() else background_color_hex # Fallback secondary
        accent_color = primary_color # Fallback accent
    else:
        # Absolute fallback if no colors found
        primary_color = '#0000ff' # Blue
        secondary_color = '#d3d3d3' # Light gray
        accent_color = '#ffa500' # Orange

    return {
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "accent_color": accent_color,
        "background_color": background_color_hex,
        "text_color": text_color_hex,
        "palette": sorted(list(valid_hex_colors))[:15]  # Include full palette (up to 15 colors)
    }

def extract_typography(driver, html_content):
    """
    Extract typography information from the webpage.

    Args:
        driver: Selenium webdriver instance
        html_content: HTML content

    Returns:
        dict: Typography information
    """
    typography = {
        "headings": {},
        "body": {},
        "font_imports": [],
        "custom_fonts_detected": False # More specific key
    }

    # Helper to safely get computed style
    def get_style(element, prop):
        try:
            return driver.execute_script(f"return window.getComputedStyle(arguments[0]).{prop}", element)
        except Exception:
            return None

    # Extract body text typography
    try:
        body_element = driver.find_element("css selector", "body")
        body_font = get_style(body_element, "fontFamily")
        body_size = get_style(body_element, "fontSize")
        body_weight = get_style(body_element, "fontWeight")
        body_line_height = get_style(body_element, "lineHeight")

        typography["body"] = {
            "font_family": body_font.strip('"\'') if body_font else "sans-serif",
            "font_size": body_size if body_size else "16px",
            "font_weight": body_weight if body_weight else "400",
            "line_height": body_line_height if body_line_height else "normal"
        }
    except Exception as e:
        print(f"Error extracting body typography: {e}")
        # Provide defaults if body extraction fails
        typography["body"] = {
            "font_family": "sans-serif", "font_size": "16px", "font_weight": "400", "line_height": "normal"
        }


    # Extract heading typography (h1-h6)
    heading_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    for tag in heading_tags:
        try:
            elements = driver.find_elements("css selector", tag)
            if elements:
                # Analyze the first visible heading of this type
                visible_elements = [el for el in elements if el.is_displayed()]
                if not visible_elements:
                    continue # Skip if no visible elements of this type found

                element = visible_elements[0]
                font_family = get_style(element, "fontFamily")
                font_size = get_style(element, "fontSize")
                font_weight = get_style(element, "fontWeight")
                # Optional: color, text-transform, etc.
                # color = get_style(element, "color")
                # text_transform = get_style(element, "textTransform")

                if font_family and font_size and font_weight: # Only add if we got basic info
                    typography["headings"][tag] = {
                        "font_family": font_family.strip('"\''),
                        "font_size": font_size,
                        "font_weight": font_weight
                        # "color": rgb_to_hex(color) if color else None,
                        # "text_transform": text_transform if text_transform else "none"
                    }
        except Exception as e:
            # print(f"Error extracting typography for <{tag}>: {e}")
            continue # Continue to the next heading tag

    # Look for Google Fonts or other font imports in <link> tags and <style> tags
    font_imports = []
    try:
        # Check <link> tags for fonts.googleapis.com or other font providers
        link_tags = driver.find_elements("css selector", "link[href*='font'], link[href*='typeface']")
        for link in link_tags:
            href = link.get_attribute('href')
            if href:
                font_imports.append(href)

        # Check <style> tags for @import url(...) targeting fonts
        style_imports = re.findall(r'@import\s+url\(([^)]+?fonts[^)]+)\);', html_content, re.IGNORECASE)
        font_imports.extend(style_imports)

        # Check for @font-face rules within <style> tags
        style_tags_content = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
        for style_content in style_tags_content:
            if '@font-face' in style_content:
                typography["custom_fonts_detected"] = True
                # Could potentially parse font-family names from @font-face here
                # font_face_families = re.findall(r'font-family:\s*["\']?([^;"\']+)["\']?;', style_content)
                # print(f"Detected @font-face families: {font_face_families}")

    except Exception as e:
        print(f"Error extracting font imports: {e}")

    typography["font_imports"] = list(set(font_imports)) # Unique imports

    return typography

def analyze_layout(driver):
    """
    Analyze layout characteristics like spacing, grid systems, and content width.

    Args:
        driver: Selenium webdriver instance

    Returns:
        dict: Layout specifications
    """
    layout_info = {
        "page_dimensions": {"width": None, "height": None},
        "container_width": None,
        "has_grid_system": False,
        "common_spacing_units": []
    }

    # Helper to safely execute script and get numeric result
    def safe_get_numeric_script(script, element=None, default=None):
        try:
            result = driver.execute_script(script, element) if element else driver.execute_script(script)
            # Try to convert to number, removing 'px' etc.
            if isinstance(result, (int, float)):
                return result
            if isinstance(result, str):
                numeric_part = re.match(r'^[+-]?(\d*\.)?\d+', result)
                if numeric_part:
                    return float(numeric_part.group(0))
            return default
        except Exception:
            return default

    # Get page dimensions
    layout_info["page_dimensions"]["width"] = safe_get_numeric_script("return document.body.clientWidth", default=1920)
    layout_info["page_dimensions"]["height"] = safe_get_numeric_script("return document.body.clientHeight", default=1080)

    # Analyze main container width (often not 100% of viewport)
    try:
        # Look for common container selectors
        main_elements = driver.find_elements("css selector", "main, .main, #main, .container, #container, .content, #content, .wrapper, #wrapper")
        visible_containers = [el for el in main_elements if el.is_displayed()]
        if visible_containers:
            # Find the widest visible container, likely the main one
            widest_container = max(visible_containers, key=lambda el: safe_get_numeric_script("return arguments[0].clientWidth", el, 0))
            container_width = safe_get_numeric_script("return arguments[0].clientWidth", widest_container, 0)
            # Only record if it's significantly different from page width
            if container_width > 0 and abs(container_width - layout_info["page_dimensions"]["width"]) > 50:
                 layout_info["container_width"] = container_width
            elif len(visible_containers) == 1: # If only one container found, record its width
                 layout_info["container_width"] = container_width

    except Exception as e:
        print(f"Error analyzing container width: {e}")


    # Analyze grid systems (simple check for common class names)
    try:
        # Look for common grid/column class patterns
        potential_grids = driver.find_elements("css selector", ".row, .grid, .columns, [class*='grid-'], [class*='col-'], [class*='span-'], [class*='uk-grid'], [class*='container']")
        # Check if multiple distinct grid-related elements exist
        if len(potential_grids) > 5: # Arbitrary threshold suggesting a grid system is likely used
            layout_info["has_grid_system"] = True
    except Exception as e:
        print(f"Error analyzing grid system: {e}")

    # Detect common spacing units by analyzing margins and paddings
    spacing_samples = []
    try:
        # Sample various common elements
        elements_to_sample = driver.find_elements("css selector", "p, div, section, article, h1, h2, h3, button, img, li")[:100] # Sample more elements

        for element in elements_to_sample:
            try:
                # Check only visible elements
                if not element.is_displayed():
                    continue

                # Get various margin/padding values
                styles_to_check = ["marginTop", "marginBottom", "marginLeft", "marginRight",
                                   "paddingTop", "paddingBottom", "paddingLeft", "paddingRight"]
                for style_prop in styles_to_check:
                    value = driver.execute_script(f"return window.getComputedStyle(arguments[0]).{style_prop}", element)
                    # Keep only non-zero pixel values for simplicity
                    if value and value.endswith('px') and float(value.replace('px', '')) > 0:
                        spacing_samples.append(value)
            except Exception:
                continue # Ignore errors for individual elements

        # Count occurrences to find common spacing units
        if spacing_samples:
            spacing_counts = Counter(spacing_samples)
            # Get the top 5 most common spacing values
            layout_info["common_spacing_units"] = [space for space, count in spacing_counts.most_common(5)]

    except Exception as e:
        print(f"Error analyzing spacing: {e}")

    return layout_info

def detect_component_patterns(driver, html_content):
    """
    Detect common UI components and their styling patterns.

    Args:
        driver: Selenium webdriver instance
        html_content: HTML content

    Returns:
        dict: Component specifications
    """
    components = {
        "buttons": {},
        "cards": {},
        "forms": {"inputs": {}}, # Initialize nested dict
        "navigation": {},
        "detected_css_patterns": [] # Renamed for clarity
    }

    # Helper to safely get computed style
    def get_style(element, prop):
        try:
            # Ensure element is interactable/visible before getting style
            if element.is_displayed():
                return driver.execute_script(f"return window.getComputedStyle(arguments[0]).{prop}", element)
        except Exception:
            pass # Ignore errors like StaleElementReferenceException
        return None

    # Analyze buttons
    try:
        # More comprehensive selector for buttons
        buttons = driver.find_elements("css selector", "button, .button, .btn, [class*='button'], [class*='btn'], input[type='button'], input[type='submit'], a[role='button']")
        visible_buttons = [b for b in buttons if b.is_displayed()][:10] # Limit sample size

        if visible_buttons:
            sample_button = visible_buttons[0] # Use the first visible one as representative
            button_bg = get_style(sample_button, "backgroundColor")
            button_color = get_style(sample_button, "color")
            button_padding = get_style(sample_button, "padding")
            button_border = get_style(sample_button, "border") # Gets full border shorthand
            button_radius = get_style(sample_button, "borderRadius")
            button_font_size = get_style(sample_button, "fontSize")
            button_font_weight = get_style(sample_button, "fontWeight")
            button_text_transform = get_style(sample_button, "textTransform")

            components["buttons"] = {
                "background_color": rgb_to_hex(button_bg) if button_bg else None,
                "text_color": rgb_to_hex(button_color) if button_color else None,
                "padding": button_padding,
                "border": button_border,
                "border_radius": button_radius,
                "font_size": button_font_size,
                "font_weight": button_font_weight,
                "text_transform": button_text_transform
            }
    except Exception as e:
        print(f"Error analyzing buttons: {e}")

    # Analyze card-like components
    try:
        # Common selectors for cards/panels
        cards = driver.find_elements("css selector", ".card, [class*='card'], article, .panel, [class*='panel'], .box, [class*='box'], .widget, [class*='widget']")
        visible_cards = [c for c in cards if c.is_displayed()][:10] # Limit sample size

        if visible_cards:
            sample_card = visible_cards[0]
            card_bg = get_style(sample_card, "backgroundColor")
            card_shadow = get_style(sample_card, "boxShadow")
            card_radius = get_style(sample_card, "borderRadius")
            card_padding = get_style(sample_card, "padding")
            card_border = get_style(sample_card, "border")

            components["cards"] = {
                "background_color": rgb_to_hex(card_bg) if card_bg else None,
                "box_shadow": card_shadow if card_shadow != 'none' else None, # Store only if shadow exists
                "border_radius": card_radius,
                "padding": card_padding,
                "border": card_border
            }
    except Exception as e:
        print(f"Error analyzing cards: {e}")

    # Analyze form input styles
    try:
        # Select common input types
        inputs = driver.find_elements("css selector", "input[type='text'], input[type='email'], input[type='password'], input[type='search'], textarea, select")
        visible_inputs = [i for i in inputs if i.is_displayed()][:10] # Limit sample size

        if visible_inputs:
            sample_input = visible_inputs[0]
            input_border = get_style(sample_input, "border")
            input_radius = get_style(sample_input, "borderRadius")
            input_padding = get_style(sample_input, "padding")
            input_bg = get_style(sample_input, "backgroundColor")
            input_font_size = get_style(sample_input, "fontSize")

            components["forms"]["inputs"] = {
                "border": input_border,
                "border_radius": input_radius,
                "padding": input_padding,
                "background_color": rgb_to_hex(input_bg) if input_bg else None,
                "font_size": input_font_size
            }
    except Exception as e:
        print(f"Error analyzing form inputs: {e}")

    # Analyze navigation styles
    try:
        # Common navigation selectors
        navs = driver.find_elements("css selector", "nav, header, .navigation, .navbar, #navbar, #main-nav, .main-navigation, .header, #header")
        visible_navs = [n for n in navs if n.is_displayed()]

        if visible_navs:
            # Often the first one is the main nav/header
            sample_nav = visible_navs[0]
            nav_bg = get_style(sample_nav, "backgroundColor")
            # Use getBoundingClientRect for more reliable height
            nav_height = driver.execute_script("return arguments[0].getBoundingClientRect().height", sample_nav)
            nav_shadow = get_style(sample_nav, "boxShadow")
            # Analyze link styles within the nav
            nav_links = sample_nav.find_elements("css selector", "a")
            nav_link_color = None
            if nav_links and nav_links[0].is_displayed():
                nav_link_color = get_style(nav_links[0], "color")


            components["navigation"] = {
                "background_color": rgb_to_hex(nav_bg) if nav_bg else None,
                "height": f"{nav_height:.0f}px" if nav_height else None,
                "box_shadow": nav_shadow if nav_shadow != 'none' else None,
                "link_color": rgb_to_hex(nav_link_color) if nav_link_color else None
            }
    except Exception as e:
        print(f"Error analyzing navigation: {e}")

    # Detect common CSS class patterns (utility classes, BEM, etc.)
    try:
        class_pattern = re.compile(r'class=["\']([^"\']+)["\']')
        # Find all class attributes in the HTML
        class_matches = class_pattern.findall(html_content)

        all_classes = []
        for match in class_matches:
            # Split multi-class strings and clean up whitespace
            classes = [c.strip() for c in match.split()]
            all_classes.extend(classes)

        # Count occurrences
        if all_classes:
            class_counter = Counter(all_classes)

            # Find potential utility classes or common prefixes/suffixes
            common_patterns = []
            # Common prefixes/indicators for utility classes or frameworks
            utility_indicators = ['text-', 'bg-', 'p-', 'm-', 'flex', 'grid', 'border', 'rounded', 'w-', 'h-', 'font-', 'shadow', 'item', 'container', 'row', 'col-', 'nav-', 'btn-', 'card-', 'form-']

            # Get top 50 most common classes
            for cls, count in class_counter.most_common(50):
                 # Add if it appears frequently (e.g., > 5 times) and matches a common pattern
                if count > 5:
                    if any(indicator in cls for indicator in utility_indicators):
                         # Basic filtering to avoid overly generic or single-letter classes
                        if len(cls) > 2:
                            common_patterns.append(cls)

            # Limit to top 15 relevant patterns found
            components["detected_css_patterns"] = common_patterns[:15]
    except Exception as e:
        print(f"Error detecting CSS patterns: {e}")

    return components

def analyze_images_and_icons(driver, html_content):
    """
    Analyze images and icons for style patterns.

    Args:
        driver: Selenium webdriver instance
        html_content: HTML content

    Returns:
        dict: Image and icon specifications
    """
    image_info = {
        "has_svg_icons": False,
        "has_icon_font": False,
        "icon_classes_found": [], # Renamed for clarity
        "image_style": {},
        "logo_detected": False,
        "logo_url": None # Added to store logo URL
    }

    # Helper to safely get style
    def get_style(element, prop):
        try:
            if element.is_displayed():
                return driver.execute_script(f"return window.getComputedStyle(arguments[0]).{prop}", element)
        except Exception:
            pass
        return None

    # Check for SVG usage (both inline <svg> and <img> with .svg src)
    try:
        svg_elements = driver.find_elements("css selector", "svg")
        img_svgs = driver.find_elements("css selector", "img[src$='.svg']")
        if svg_elements or img_svgs:
            image_info["has_svg_icons"] = True
    except Exception as e:
        print(f"Error checking for SVG icons: {e}")

    # Check for common icon fonts by looking for specific class prefixes/patterns
    try:
        icon_font_patterns = [
            'fa-', 'fas', 'far', 'fal', 'fab', # FontAwesome
            'glyphicon',                     # Bootstrap 3
            'material-icons',                # Material Design Icons
            'icon-',                         # Generic prefix
            'icofont-',                      # IcoFont
            'bi-',                           # Bootstrap Icons
            'feather',                       # Feather Icons
            'mdi-'                           # Material Design Icons (alternative)
        ]
        # Search for elements with class attributes containing these patterns
        icon_elements_found = False
        for pattern in icon_font_patterns:
            # Use contains selector for efficiency
            selector = f"[class*='{pattern}']"
            try:
                icon_elements = driver.find_elements("css selector", selector)
                # Check if any found elements are likely icons (e.g., <i> or <span> tags)
                if any(el.tag_name in ['i', 'span'] for el in icon_elements[:10]): # Check first 10 matches
                    image_info["has_icon_font"] = True
                    icon_elements_found = True
                    # Extract specific classes from a sample
                    sample_icon = icon_elements[0]
                    classes = sample_icon.get_attribute('class').split()
                    image_info["icon_classes_found"].extend([cls for cls in classes if pattern in cls])
                    # break # Found one type, could stop or continue searching for others
            except Exception:
                continue # Ignore errors for specific patterns

        # Limit stored icon classes
        image_info["icon_classes_found"] = list(set(image_info["icon_classes_found"]))[:10]

    except Exception as e:
        print(f"Error checking for icon fonts: {e}")


    # Analyze image styling (border-radius, shadow, border)
    try:
        images = driver.find_elements("css selector", "img")
        visible_images = [img for img in images if img.is_displayed() and int(img.size['width']) > 20 and int(img.size['height']) > 20][:10] # Sample visible images > 20x20px

        if visible_images:
            sample_image = visible_images[0]
            img_border_radius = get_style(sample_image, "borderRadius")
            img_shadow = get_style(sample_image, "boxShadow")
            img_border = get_style(sample_image, "border")
            img_filter = get_style(sample_image, "filter") # Check for filters too

            image_info["image_style"] = {
                "border_radius": img_border_radius if img_border_radius != '0px' else None,
                "box_shadow": img_shadow if img_shadow != 'none' else None,
                "border": img_border if img_border != '0px none rgb(0, 0, 0)' else None, # More specific check for default border
                "filter": img_filter if img_filter != 'none' else None
            }
    except Exception as e:
        print(f"Error analyzing image styles: {e}")

    # Look for logo (typically in header/nav, with class/id/alt containing 'logo')
    try:
        # Comprehensive logo selectors
        logo_selectors = [
            ".logo", "#logo", "[class*='logo']", "[id*='logo']",
            "header img[alt*='logo' i]", "nav img[alt*='logo' i]",
            "header a[href='/'] img", "nav a[href='/'] img", # Logo often links to homepage
            "[aria-label*='logo' i]", "img[src*='logo']"
        ]
        logo_element = None
        for selector in logo_selectors:
            try:
                elements = driver.find_elements("css selector", selector)
                visible_logos = [el for el in elements if el.is_displayed()]
                if visible_logos:
                    logo_element = visible_logos[0] # Take the first visible match
                    break
            except Exception:
                continue # Ignore errors for specific selectors

        if logo_element:
            image_info["logo_detected"] = True
            logo_url = None
            if logo_element.tag_name == 'img':
                logo_url = logo_element.get_attribute("src")
            elif logo_element.tag_name == 'a' and logo_element.find_elements("css selector", "img"):
                 # If logo is an image inside a link
                 logo_img = logo_element.find_element("css selector", "img")
                 logo_url = logo_img.get_attribute("src")
            elif logo_element.tag_name == 'svg':
                 # Could try to get outerHTML for inline SVG logo
                 # logo_url = "inline SVG detected"
                 pass # Indicate SVG logo presence via has_svg_icons
            else:
                # Check for background image logo
                logo_bg = get_style(logo_element, "backgroundImage")
                if logo_bg and logo_bg != 'none':
                    bg_url_match = re.search(r'url\("?([^")]+)"?\)', logo_bg)
                    if bg_url_match:
                        logo_url = bg_url_match.group(1)

            # Resolve relative URL if needed
            if logo_url and not logo_url.startswith(('http:', 'https:', 'data:')):
                from urllib.parse import urljoin
                base_url = driver.current_url
                logo_url = urljoin(base_url, logo_url)

            image_info["logo_url"] = logo_url

    except Exception as e:
        print(f"Error detecting logo: {e}")

    return image_info

def generate_design_schema(url, colors, typography, layout, components, images):
    """
    Combine all extracted information into a comprehensive design schema.

    Args:
        url: The analyzed URL
        colors: Color palette info from extract_color_palette
        typography: Typography info from extract_typography
        layout: Layout info from analyze_layout
        components: Component info from detect_component_patterns
        images: Image and icon info from analyze_images_and_icons

    Returns:
        dict: Complete design schema
    """
    schema = {
        "metadata": {
            "source_url": url,
            "extraction_date": datetime.datetime.now().isoformat(),
            "schema_version": "1.0" # Define schema version
        },
        "colors": colors,
        "typography": typography,
        "layout": layout,
        "components": components,
        "images": images,
        "design_summary": {
            "style_keywords": [] # Initialize keywords
        }
    }

    # --- Generate style keywords based on the extracted data ---
    keywords = set() # Use a set to avoid duplicates

    # Analyze colors
    if colors and colors.get("palette"):
        # Simple contrast check (more distinct colors might imply higher contrast)
        if len(colors["palette"]) > 6:
            keywords.add("high-contrast") # Tentative keyword
        elif len(colors["palette"]) <= 4:
             keywords.add("limited-palette")

        # Check for monochromatic tendency (needs better logic, e.g., check hue variance)
        # if len(set(c[1:3] for c in colors['palette'])) <= 2: # Very basic hue check
        #     keywords.add("monochromatic-leaning")

    # Analyze border radius from buttons or cards for rounded/sharp
    button_radius = components.get("buttons", {}).get("border_radius", "0px")
    card_radius = components.get("cards", {}).get("border_radius", "0px")
    image_radius = images.get("image_style", {}).get("border_radius", "0px")

    # Check if any significant radius is present
    has_rounding = any(r and r != '0px' and r != '0%' for r in [button_radius, card_radius, image_radius])
    if has_rounding:
        keywords.add("rounded-corners")
    else:
        keywords.add("sharp-corners")

    # Check for shadows on cards or images
    card_shadow = components.get("cards", {}).get("box_shadow")
    image_shadow = images.get("image_style", {}).get("box_shadow")
    nav_shadow = components.get("navigation", {}).get("box_shadow")
    if card_shadow or image_shadow or nav_shadow:
        keywords.add("uses-shadows")
    else:
        keywords.add("flat-design") # Assume flat if no shadows detected

    # Typography style (Serif vs. Sans-Serif)
    # Check primary heading font first, then body font
    heading_font = None
    if typography.get("headings"):
        for h_tag in ['h1', 'h2', 'h3']: # Check major headings
            if h_tag in typography["headings"]:
                heading_font = typography["headings"][h_tag].get("font_family", "").lower()
                break
    if not heading_font: # Fallback to body font if no heading font found
        heading_font = typography.get("body", {}).get("font_family", "").lower()

    serif_indicators = ["serif", "georgia", "times", "palatino", "bookman", "charter"]
    if any(indicator in heading_font for indicator in serif_indicators):
        keywords.add("serif-typography")
    else:
        keywords.add("sans-serif-typography")

    # Layout keywords
    if layout.get("has_grid_system"):
        keywords.add("grid-layout")
    if layout.get("container_width"):
        keywords.add("contained-width")
    else:
        keywords.add("full-width-layout") # Assume full width if no specific container found

    # Icon style
    if images.get("has_svg_icons"):
        keywords.add("svg-icons")
    elif images.get("has_icon_font"):
        keywords.add("icon-font")

    # Combine keywords into the schema
    schema["design_summary"]["style_keywords"] = sorted(list(keywords))

    return schema

def validate_schema(design_schema):
    """
    Validate the generated schema against a defined JSON schema.

    Args:
        design_schema: The generated design schema dictionary

    Returns:
        bool: True if validation passes, False otherwise
    """
    # Define the expected JSON schema structure
    # This should align with the structure produced by generate_design_schema
    json_schema = {
        "type": "object",
        "required": ["metadata", "colors", "typography", "layout", "components", "images", "design_summary"],
        "properties": {
            "metadata": {
                "type": "object",
                "required": ["source_url", "extraction_date", "schema_version"],
                "properties": {
                    "source_url": {"type": "string", "format": "uri"},
                    "extraction_date": {"type": "string", "format": "date-time"},
                    "schema_version": {"type": "string"},
                    "cms": { # Optional CMS info from plugins
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "theme": {"type": "string"}
                        }
                    }
                }
            },
            "colors": {
                "type": "object",
                "required": ["primary_color", "secondary_color", "accent_color", "background_color", "text_color", "palette"],
                "properties": {
                    "primary_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "secondary_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "accent_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "background_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "text_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "palette": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"}
                    }
                }
            },
            "typography": {
                "type": "object",
                "required": ["headings", "body", "font_imports", "custom_fonts_detected"],
                 "properties": {
                    "headings": {
                        "type": "object",
                        # Properties for h1, h2, etc. are dynamic but should follow this pattern:
                        "additionalProperties": {
                            "type": "object",
                            "required": ["font_family", "font_size", "font_weight"],
                            "properties": {
                                "font_family": {"type": "string"},
                                "font_size": {"type": "string"},
                                "font_weight": {"type": ["string", "number"]} # Weight can be numeric or string (e.g., 'bold')
                            }
                        }
                    },
                    "body": {
                        "type": "object",
                        "required": ["font_family", "font_size", "font_weight", "line_height"],
                        "properties": {
                            "font_family": {"type": "string"},
                            "font_size": {"type": "string"},
                            "font_weight": {"type": ["string", "number"]},
                            "line_height": {"type": ["string", "number"]} # Line height can be unitless number or string
                        }
                    },
                    "font_imports": {"type": "array", "items": {"type": "string"}},
                    "custom_fonts_detected": {"type": "boolean"}
                }
            },
            "layout": {
                "type": "object",
                "required": ["page_dimensions", "has_grid_system", "common_spacing_units"],
                "properties": {
                    "page_dimensions": {
                        "type": "object",
                        "required": ["width", "height"],
                        "properties": {
                            "width": {"type": ["number", "null"]},
                            "height": {"type": ["number", "null"]}
                        }
                    },
                    "container_width": {"type": ["number", "null"]},
                    "has_grid_system": {"type": "boolean"},
                    "common_spacing_units": {
                        "type": "array",
                        "items": {"type": "string", "pattern": r"^\d+(\.\d+)?px$"} # Expecting pixel values
                    }
                }
            },
            "components": {
                "type": "object",
                "properties": {
                    "buttons": {"type": "object"}, # Allow flexible properties within components
                    "cards": {"type": "object"},
                    "forms": {"type": "object", "properties": {"inputs": {"type": "object"}}},
                    "navigation": {"type": "object"},
                    "detected_css_patterns": {"type": "array", "items": {"type": "string"}},
                    "sidebar": { # Optional from plugins
                        "type": "object",
                        "properties": {
                            "present": {"type": "boolean"},
                            "width": {"type": ["number", "string", "null"]}
                        }
                    }
                },
                # No required fields at the top level, as components might not be detected
            },
            "images": {
                "type": "object",
                "required": ["has_svg_icons", "has_icon_font", "icon_classes_found", "image_style", "logo_detected"],
                "properties": {
                    "has_svg_icons": {"type": "boolean"},
                    "has_icon_font": {"type": "boolean"},
                    "icon_classes_found": {"type": "array", "items": {"type": "string"}},
                    "image_style": {"type": "object"}, # Allow flexible properties
                    "logo_detected": {"type": "boolean"},
                    "logo_url": {"type": ["string", "null"], "format": "uri-reference"} # Allow null if not found
                }
            },
            "design_summary": {
                "type": "object",
                "required": ["style_keywords"],
                "properties": {
                    "style_keywords": {"type": "array", "items": {"type": "string"}}
                }
            },
             # Optional AI consumption block
            "ai_consumption": {
                "type": "object",
                "properties": {
                    "descriptions": {"type": "object"},
                    "color_palette_hex": {"type": "array", "items": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"}},
                    "suggested_prompt_elements": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    }

    try:
        jsonschema.validate(instance=design_schema, schema=json_schema)
        print("Schema validation successful.")
        return True
    except jsonschema.exceptions.ValidationError as e:
        # Provide more detailed validation error info
        print(f"Schema validation failed:")
        print(f"- Error: {e.message}")
        print(f"- Path: {list(e.path)}")
        # print(f"- Schema Path: {list(e.schema_path)}") # Can be verbose
        # print(f"- Instance Snippet: {e.instance}") # Can be large
        return False
    except Exception as e:
        print(f"An unexpected error occurred during schema validation: {e}")
        return False

# --- Helper Functions & Plugin System ---

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
            # Ensure element is valid before script execution
            if not isinstance(element, webdriver.remote.webelement.WebElement):
                 print(f"Invalid element passed to safe_execute_script: {type(element)}")
                 return default
            # Basic check if element might be stale (though not foolproof)
            try:
                 _ = element.is_enabled()
            except:
                 print("Element seems stale in safe_execute_script.")
                 return default
            return driver.execute_script(script, element)
        else:
            return driver.execute_script(script)
    except Exception as e:
        # Don't print every script error, can be noisy
        # print(f"Script execution error: {script[:50]}... - {e}")
        return default

def determine_website_type(html_content, url):
    """
    Determine the type/category of website to better tailor analysis.
    Very basic detection based on common patterns.

    Args:
        html_content: HTML content of the page
        url: URL of the website

    Returns:
        str: Website type category (e.g., 'wordpress', 'shopify', 'ecommerce', 'blog', 'general')
    """
    # Check for common CMS or frameworks first (more specific)
    # Order matters - check specific CMS before general frameworks
    cms_patterns = {
        "wordpress": r'wp-content|wordpress|wp-includes',
        "shopify": r'cdn\.shopify\.com|myshopify\.com',
        "wix": r'wix\.com|wixstatic\.com|wixsite\.com',
        "squarespace": r'squarespace\.com|static1\.squarespace\.com',
        "webflow": r'webflow\.io|webflow\.com',
        "joomla": r'joomla|com_content',
        "drupal": r'drupal\.js|sites/default/files',
        # Frameworks (less specific than CMS)
        "tailwind": r'tailwindcss|tailwind\.css|class="[^"]*(?:flex|grid|p-|m-|text-|bg-)', # Look for utility classes
        "bootstrap": r'bootstrap\.min\.css|bootstrap\.bundle\.min\.js|class="[^"]*(?:container|row|col-)',
        "react": r'react-root|data-reactid',
        "vue": r'data-v-',
        "angular": r'ng-version',
        "material": r'material-design|mdl-|mui-'
    }

    # Check CMS/Framework patterns
    for type_key, pattern in cms_patterns.items():
        try:
            if re.search(pattern, html_content, re.IGNORECASE):
                return type_key
        except Exception: # Catch potential regex errors on weird HTML
            continue

    # Check for e-commerce indicators if no specific CMS/framework found
    ecommerce_patterns = r'cart|checkout|product|shop|store|price|add to cart|woocommerce'
    if re.search(ecommerce_patterns, html_content, re.IGNORECASE):
        return "ecommerce"

    # Check for blog indicators
    blog_patterns = r'blog|article|post|author|comment|category|archive'
    if re.search(blog_patterns, html_content, re.IGNORECASE):
        return "blog"

    # Check URL TLD for clues (less reliable)
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        if domain:
            if '.gov' in domain: return "government"
            if '.edu' in domain: return "education"
            if '.org' in domain: return "organization"
    except Exception:
        pass

    return "general" # Default type

class DesignSchemeExtractorPlugin:
    """Base class for design scheme extractor plugins."""
    plugin_name = "base_plugin" # Give each plugin a name

    def __init__(self, applicable_types):
        """
        Args:
            applicable_types (list or str): Website type(s) this plugin applies to.
        """
        if isinstance(applicable_types, str):
            self.applicable_types = [applicable_types]
        else:
            self.applicable_types = applicable_types

    def applies_to(self, detected_type):
        """Check if this plugin applies to the detected website type."""
        return detected_type in self.applicable_types

    def enhance_schema(self, design_schema, html_content, driver=None):
        """
        Enhance the design schema with plugin-specific information.
        This method should be overridden by subclasses.

        Args:
            design_schema: Current design schema dictionary
            html_content: HTML content string
            driver: Selenium webdriver instance (optional)

        Returns:
            dict: Enhanced design schema dictionary
        """
        print(f"Applying plugin: {self.plugin_name} (Base implementation - does nothing)")
        return design_schema

# Example plugin for WordPress sites
class WordPressPlugin(DesignSchemeExtractorPlugin):
    plugin_name = "wordpress_enhancer"

    def __init__(self):
        super().__init__("wordpress") # This plugin applies only to 'wordpress' type

    def enhance_schema(self, design_schema, html_content, driver=None):
        print(f"Applying plugin: {self.plugin_name}")
        # Ensure metadata exists
        if "metadata" not in design_schema:
            design_schema["metadata"] = {}

        # Try to detect WordPress theme name
        theme_match = re.search(r'wp-content/themes/([^/]+)', html_content, re.IGNORECASE)
        theme_name = theme_match.group(1) if theme_match else None

        design_schema["metadata"]["cms"] = {
            "type": "wordpress",
            "theme": theme_name
        }

        # Look for common WordPress elements like sidebar widgets
        if driver:
            try:
                sidebar = driver.find_elements("css selector", ".widget-area, .sidebar, #sidebar, #secondary")
                visible_sidebar = next((s for s in sidebar if s.is_displayed()), None)
                if visible_sidebar:
                     # Ensure components dict exists
                    if "components" not in design_schema:
                        design_schema["components"] = {}
                    design_schema["components"]["sidebar"] = {
                        "present": True,
                        "width": safe_execute_script(driver, "return arguments[0].clientWidth", visible_sidebar, None)
                    }
            except Exception as e:
                print(f"WordPress plugin error checking sidebar: {e}")

        return design_schema

# Plugin registry
# Add more plugins here as needed (e.g., ShopifyPlugin, BootstrapPlugin)
_PLUGINS = [WordPressPlugin()]

def get_plugins():
    """Returns a list of available plugin instances."""
    return _PLUGINS

def enhance_with_plugins(design_schema, website_type, html_content, driver=None):
    """Apply all applicable plugins to enhance the design schema."""
    print(f"Running enhancement plugins for website type: {website_type}")
    plugins = get_plugins()
    applied_plugins = []

    for plugin in plugins:
        try:
            if plugin.applies_to(website_type):
                design_schema = plugin.enhance_schema(design_schema, html_content, driver)
                applied_plugins.append(plugin.plugin_name)
        except Exception as e:
            print(f"Error applying plugin {getattr(plugin, 'plugin_name', 'unknown')}: {e}")
            # Continue with other plugins even if one fails

    if applied_plugins:
        print(f"Applied plugins: {', '.join(applied_plugins)}")
    else:
        print("No applicable plugins found or applied.")

    return design_schema

# --- Output Generation Functions ---

def optimize_for_ai_consumption(design_schema):
    """
    Optimize the design schema specifically for AI system consumption
    by adding natural language descriptions and prompt suggestions.

    Args:
        design_schema: The extracted design schema dictionary

    Returns:
        dict: A *copy* of the design schema with an added 'ai_consumption' key,
              or the original schema if optimization fails.
    """
    # Create a deep copy to avoid modifying the original schema
    try:
        ai_schema = json.loads(json.dumps(design_schema)) # Simple deep copy via JSON
    except Exception as e:
        print(f"Error deep copying schema for AI optimization: {e}")
        return design_schema # Return original if copy fails

    # Initialize descriptions and prompt elements
    descriptions = {
        "overall_style": "",
        "color_scheme": "",
        "typography": "",
        "layout_spacing": "",
        "component_styles": ""
    }
    prompt_elements = []

    # --- Generate Natural Language Descriptions ---
    try:
        # Overall Style Description
        style_keywords = ai_schema.get("design_summary", {}).get("style_keywords", [])
        if style_keywords:
            if len(style_keywords) > 1:
                style_desc = f"The website features a {', '.join(style_keywords[:-1])} and {style_keywords[-1]} design style."
            elif len(style_keywords) == 1:
                style_desc = f"The website features a {style_keywords[0]} design style."
            else:
                style_desc = "The website's overall design style is neutral or couldn't be easily categorized."
            descriptions["overall_style"] = style_desc
            prompt_elements.append(f"Design Style: {', '.join(style_keywords)}")

        # Color Scheme Description
        colors = ai_schema.get("colors", {})
        primary = colors.get("primary_color")
        secondary = colors.get("secondary_color")
        accent = colors.get("accent_color")
        bg = colors.get("background_color")
        text_c = colors.get("text_color")
        if primary and secondary and accent and bg and text_c:
            descriptions["color_scheme"] = f"Key colors are Primary: {primary}, Secondary: {secondary}, Accent: {accent}, Background: {bg}, Text: {text_c}."
            prompt_elements.append(f"Color Palette: Primary({primary}), Secondary({secondary}), Accent({accent}), Background({bg}), Text({text_c})")
        elif colors.get("palette"):
             descriptions["color_scheme"] = f"The main color palette includes: {', '.join(colors['palette'][:5])}..."
             prompt_elements.append(f"Color Palette: {', '.join(colors['palette'][:5])}")


        # Typography Description
        typography = ai_schema.get("typography", {})
        body_font = typography.get("body", {}).get("font_family", "default")
        heading_font = body_font # Default to body font
        if typography.get("headings"):
             # Try H1, then H2, etc.
            for h_tag in ['h1', 'h2', 'h3']:
                if h_tag in typography["headings"]:
                    heading_font = typography["headings"][h_tag].get("font_family", body_font)
                    break

        if heading_font.lower() == body_font.lower():
            descriptions["typography"] = f"Typography primarily uses the '{body_font}' font family."
            prompt_elements.append(f"Typography: Use '{body_font}' font.")
        else:
            descriptions["typography"] = f"Typography uses '{heading_font}' for headings and '{body_font}' for body text."
            prompt_elements.append(f"Typography: Headings '{heading_font}', Body '{body_font}'.")

        # Layout & Spacing Description
        layout = ai_schema.get("layout", {})
        spacing_units = layout.get("common_spacing_units", [])
        layout_desc_parts = []
        if layout.get("has_grid_system"): layout_desc_parts.append("grid-based layout")
        if layout.get("container_width"): layout_desc_parts.append(f"contained width (around {layout['container_width']}px)")
        else: layout_desc_parts.append("full-width layout")
        if spacing_units:
            layout_desc_parts.append(f"common spacing unit around {spacing_units[0]}")
            prompt_elements.append(f"Spacing: Base unit ~{spacing_units[0]}.")

        descriptions["layout_spacing"] = f"Layout is generally {', '.join(layout_desc_parts)}."


        # Component Styles Description
        components = ai_schema.get("components", {})
        comp_desc_parts = []
        if components.get("buttons"):
            btn_radius = components["buttons"].get("border_radius", "0px")
            btn_style = "rounded" if btn_radius and btn_radius != "0px" else "sharp-edged"
            comp_desc_parts.append(f"{btn_style} buttons")
        if components.get("cards"):
            card_shadow = components["cards"].get("box_shadow")
            card_style = "shadowed" if card_shadow else "flat"
            comp_desc_parts.append(f"{card_style} cards/panels")
        if ai_schema.get("images", {}).get("has_svg_icons"):
            comp_desc_parts.append("uses SVG icons")
        elif ai_schema.get("images", {}).get("has_icon_font"):
             comp_desc_parts.append("uses icon fonts")

        if comp_desc_parts:
            descriptions["component_styles"] = f"Key component styles include: {', '.join(comp_desc_parts)}."
        else:
            descriptions["component_styles"] = "Specific component styles were not prominently detected."

    except Exception as e:
        print(f"Error generating AI descriptions: {e}")
        # Continue even if description generation fails partially

    # Add the generated info to the schema copy
    ai_schema["ai_consumption"] = {
        "natural_language_descriptions": descriptions,
        "suggested_prompt_elements": prompt_elements,
        "full_palette_hex": ai_schema.get("colors", {}).get("palette", []) # Include full palette for reference
    }

    return ai_schema

def generate_design_code_snippets(design_schema):
    """
    Generate code snippets (CSS Variables, Tailwind Config, Styled Components Theme)
    based on the extracted design schema.

    Args:
        design_schema: The extracted design schema dictionary

    Returns:
        dict: Dictionary containing code snippets as strings, or None if generation fails.
    """
    try:
        colors = design_schema.get("colors", {})
        typography = design_schema.get("typography", {})
        layout = design_schema.get("layout", {})
        components = design_schema.get("components", {})

        # --- Extract key values with fallbacks ---
        primary = colors.get("primary_color", "#0000ff") # Default blue
        secondary = colors.get("secondary_color", "#6c757d") # Default gray
        accent = colors.get("accent_color", "#ffc107") # Default yellow/orange
        background = colors.get("background_color", "#ffffff")
        text_color = colors.get("text_color", "#000000")

        body_info = typography.get("body", {})
        body_font_raw = body_info.get("font_family", "sans-serif")
        # Extract first font from stack for simplicity in configs
        body_font = body_font_raw.split(',')[0].strip().strip('"\'')
        body_size = body_info.get("font_size", "16px")

        heading_font_raw = body_font_raw # Default to body font
        if typography.get("headings"):
            for h_tag in ['h1', 'h2', 'h3']:
                if h_tag in typography["headings"]:
                    heading_font_raw = typography["headings"][h_tag].get("font_family", body_font_raw)
                    break
        heading_font = heading_font_raw.split(',')[0].strip().strip('"\'')

        spacing_unit_val = "8" # Default spacing unit value
        spacing_units = layout.get("common_spacing_units", [])
        if spacing_units:
            # Try to parse the first common spacing unit
            match = re.match(r'(\d+)', spacing_units[0])
            if match:
                spacing_unit_val = match.group(1)
        spacing_unit = f"{spacing_unit_val}px"

        border_radius_val = "4" # Default radius value
        button_radius = components.get("buttons", {}).get("border_radius")
        card_radius = components.get("cards", {}).get("border_radius")
        # Prioritize button radius, then card radius
        radius_to_use = button_radius or card_radius
        if radius_to_use:
             match = re.match(r'(\d+)', radius_to_use)
             if match:
                 border_radius_val = match.group(1)
        border_radius = f"{border_radius_val}px"

        # --- Generate CSS Variables ---
        css_variables = f""":root {{
  /* Colors */
  --color-primary: {primary};
  --color-secondary: {secondary};
  --color-accent: {accent};
  --color-background: {background};
  --color-text: {text_color};

  /* Typography */
  --font-body: {body_font_raw};
  --font-heading: {heading_font_raw};
  --font-size-base: {body_size};
  /* Add more font sizes if extracted */

  /* Spacing */
  --spacing-unit: {spacing_unit};
  --spacing-xs: calc(var(--spacing-unit) * 0.25);
  --spacing-sm: calc(var(--spacing-unit) * 0.5);
  --spacing-md: var(--spacing-unit);
  --spacing-lg: calc(var(--spacing-unit) * 1.5);
  --spacing-xl: calc(var(--spacing-unit) * 2);
  --spacing-xxl: calc(var(--spacing-unit) * 3);

  /* Borders */
  --border-radius: {border_radius};
  /* Add border width/style if extracted */
}}
"""

        # --- Generate Tailwind CSS config ---
        # Note: Tailwind expects font names without quotes usually
        tailwind_config = f"""
// tailwind.config.js
module.exports = {{
  theme: {{
    extend: {{
      colors: {{
        primary: '{primary}',
        secondary: '{secondary}',
        accent: '{accent}',
        'surface-bg': '{background}', // Renamed for clarity
        'text-main': '{text_color}',   // Renamed for clarity
      }},
      fontFamily: {{
        // Ensure font names are suitable for Tailwind config keys/values
        sans: ['{body_font}', 'ui-sans-serif', 'system-ui'],
        heading: ['{heading_font}', 'ui-serif', 'Georgia'], // Example fallback
      }},
      fontSize: {{
         'base': '{body_size}',
         // Add other sizes if available, e.g., 'lg': '1.125rem'
      }},
      spacing: {{
        'unit': '{spacing_unit}',
        // Generate some multiples based on the unit
        'xs': `calc(${{{spacing_unit_val}}}px * 0.25)`,
        'sm': `calc(${{{spacing_unit_val}}}px * 0.5)`,
        'md': '{spacing_unit}',
        'lg': `calc(${{{spacing_unit_val}}}px * 1.5)`,
        'xl': `calc(${{{spacing_unit_val}}}px * 2)`,
        '2xl': `calc(${{{spacing_unit_val}}}px * 3)`,
      }},
      borderRadius: {{
        DEFAULT: '{border_radius}',
        // Add other radius sizes if needed, e.g., 'lg': '0.5rem'
      }},
    }},
  }},
  plugins: [],
}}
"""

        # --- Generate React styled-components theme ---
        styled_components_theme = f"""
// theme.js (for styled-components)
const theme = {{
  colors: {{
    primary: '{primary}',
    secondary: '{secondary}',
    accent: '{accent}',
    background: '{background}',
    text: '{text_color}',
  }},
  fonts: {{
    body: '{body_font_raw}', // Keep full font stack
    heading: '{heading_font_raw}',
  }},
  fontSizes: {{
    base: '{body_size}',
    // Add more sizes if extracted, e.g., h1: '2rem'
  }},
  spacing: {{
    unit: '{spacing_unit}',
    xs: `calc({spacing_unit} * 0.25)`,
    sm: `calc({spacing_unit} * 0.5)`,
    md: '{spacing_unit}',
    lg: `calc({spacing_unit} * 1.5)`,
    xl: `calc({spacing_unit} * 2)`,
    xxl: `calc({spacing_unit} * 3)`,
  }},
  borderRadius: '{border_radius}',
}};

export default theme;
"""

        return {
            "css_variables": css_variables.strip(),
            "tailwind_config": tailwind_config.strip(),
            "styled_components_theme": styled_components_theme.strip()
        }

    except Exception as e:
        print(f"Error generating code snippets: {e}")
        return None

def generate_documentation(design_schema):
    """
    Generate markdown documentation for the extracted design scheme.

    Args:
        design_schema: The extracted design schema dictionary

    Returns:
        str: Markdown documentation string, or an empty string if generation fails.
    """
    try:
        # Extract key sections for easier access
        metadata = design_schema.get("metadata", {})
        colors = design_schema.get("colors", {})
        typography = design_schema.get("typography", {})
        layout = design_schema.get("layout", {})
        components = design_schema.get("components", {})
        images = design_schema.get("images", {})
        summary = design_schema.get("design_summary", {})
        ai_info = design_schema.get("ai_consumption", {}).get("natural_language_descriptions", {}) # Get AI descriptions if available

        # --- Header ---
        doc_parts = [
            f"# Design Scheme Documentation",
            f"*Source URL: {metadata.get('source_url', 'N/A')}*",
            f"*Extraction Date: {metadata.get('extraction_date', 'N/A')}*",
            f"*Schema Version: {metadata.get('schema_version', 'N/A')}*",
            f"\n## Overall Style Summary",
            f"{ai_info.get('overall_style', ' '.join(summary.get('style_keywords', ['N/A'])))}", # Use AI desc or keywords
        ]

        # --- Color Palette ---
        doc_parts.append("\n## Color Palette")
        doc_parts.append(f"{ai_info.get('color_scheme', 'See details below.')}") # Use AI description if available
        doc_parts.append("\n| Role             | Color Preview | Hex Code                 |")
        doc_parts.append(  "|------------------|---------------|--------------------------|")

        def color_row(role, hex_code):
            if not hex_code: return ""
            # Simple inline style for color swatch
            swatch = f'<div style="background-color: {hex_code}; width: 20px; height: 20px; display: inline-block; border: 1px solid #ccc; vertical-align: middle;"></div>'
            return f"| {role.ljust(16)} | {swatch}      | `{hex_code}`             |"

        doc_parts.append(color_row("Primary", colors.get("primary_color")))
        doc_parts.append(color_row("Secondary", colors.get("secondary_color")))
        doc_parts.append(color_row("Accent", colors.get("accent_color")))
        doc_parts.append(color_row("Background", colors.get("background_color")))
        doc_parts.append(color_row("Text", colors.get("text_color")))

        palette = colors.get("palette", [])
        if palette:
            doc_parts.append("\n### Full Palette Detected")
            palette_swatches = " ".join([
                f'<div style="background-color: {color}; width: 30px; height: 30px; display: inline-block; margin: 2px; border: 1px solid #ccc; vertical-align: middle;" title="{color}"></div>'
                for color in palette
            ])
            doc_parts.append(palette_swatches)

        # --- Typography ---
        doc_parts.append("\n## Typography")
        doc_parts.append(f"{ai_info.get('typography', 'See details below.')}") # Use AI description if available
        body_info = typography.get("body", {})
        doc_parts.append("\n### Body Text")
        doc_parts.append(f"- **Font Family:** `{body_info.get('font_family', 'N/A')}`")
        doc_parts.append(f"- **Font Size:** `{body_info.get('font_size', 'N/A')}`")
        doc_parts.append(f"- **Font Weight:** `{body_info.get('font_weight', 'N/A')}`")
        doc_parts.append(f"- **Line Height:** `{body_info.get('line_height', 'N/A')}`")

        headings = typography.get("headings", {})
        if headings:
            doc_parts.append("\n### Headings")
            for tag, styles in sorted(headings.items()):
                doc_parts.append(f"#### `<{tag}>` Style")
                doc_parts.append(f"  - **Font Family:** `{styles.get('font_family', 'N/A')}`")
                doc_parts.append(f"  - **Font Size:** `{styles.get('font_size', 'N/A')}`")
                doc_parts.append(f"  - **Font Weight:** `{styles.get('font_weight', 'N/A')}`")

        font_imports = typography.get("font_imports", [])
        if font_imports:
             doc_parts.append("\n### Font Imports Detected")
             for imp in font_imports:
                 doc_parts.append(f"- `{imp}`")
        if typography.get("custom_fonts_detected"):
            doc_parts.append("- Custom fonts (`@font-face`) detected in CSS.")


        # --- Layout & Spacing ---
        doc_parts.append("\n## Layout & Spacing")
        doc_parts.append(f"{ai_info.get('layout_spacing', 'See details below.')}") # Use AI description if available
        page_dims = layout.get("page_dimensions", {})
        doc_parts.append(f"- **Page Dimensions (Approx):** Width: `{page_dims.get('width', 'N/A')}px`, Height: `{page_dims.get('height', 'N/A')}px`")
        doc_parts.append(f"- **Container Width (Detected):** `{layout.get('container_width', 'N/A') or 'Full Width'}`")
        doc_parts.append(f"- **Grid System Likely:** `{'Yes' if layout.get('has_grid_system') else 'No'}`")
        spacing = layout.get("common_spacing_units", [])
        if spacing:
            doc_parts.append(f"- **Common Spacing Units:** `{', '.join(spacing)}`")

        # --- Components ---
        doc_parts.append("\n## Component Styles (Sampled)")
        doc_parts.append(f"{ai_info.get('component_styles', 'See details below.')}") # Use AI description if available

        if components.get("buttons"):
            doc_parts.append("\n### Buttons")
            for prop, value in components["buttons"].items():
                if value: doc_parts.append(f"- **{prop.replace('_', ' ').title()}:** `{value}`")
        if components.get("cards"):
            doc_parts.append("\n### Cards / Panels")
            for prop, value in components["cards"].items():
                 if value: doc_parts.append(f"- **{prop.replace('_', ' ').title()}:** `{value}`")
        if components.get("forms", {}).get("inputs"):
             doc_parts.append("\n### Form Inputs")
             for prop, value in components["forms"]["inputs"].items():
                 if value: doc_parts.append(f"- **{prop.replace('_', ' ').title()}:** `{value}`")
        if components.get("navigation"):
             doc_parts.append("\n### Navigation / Header")
             for prop, value in components["navigation"].items():
                 if value: doc_parts.append(f"- **{prop.replace('_', ' ').title()}:** `{value}`")

        css_patterns = components.get("detected_css_patterns", [])
        if css_patterns:
            doc_parts.append("\n### Detected CSS Class Patterns")
            doc_parts.append(f"`{', '.join(css_patterns)}`")

        # --- Images & Icons ---
        doc_parts.append("\n## Images & Icons")
        doc_parts.append(f"- **SVG Icons Used:** `{'Yes' if images.get('has_svg_icons') else 'No'}`")
        doc_parts.append(f"- **Icon Font Used:** `{'Yes' if images.get('has_icon_font') else 'No'}`")
        icon_classes = images.get("icon_classes_found", [])
        if icon_classes:
            doc_parts.append(f"- **Detected Icon Classes:** `{', '.join(icon_classes)}`")

        image_style = images.get("image_style", {})
        if any(image_style.values()): # Check if any style was detected
            doc_parts.append("\n### Image Styling (Sampled)")
            for prop, value in image_style.items():
                if value: doc_parts.append(f"- **{prop.replace('_', ' ').title()}:** `{value}`")

        doc_parts.append(f"\n- **Logo Detected:** `{'Yes' if images.get('logo_detected') else 'No'}`")
        if images.get("logo_url"):
             doc_parts.append(f"- **Logo URL:** `{images.get('logo_url')}`")


        # --- AI Integration Guide (Optional) ---
        if ai_info:
            doc_parts.append("\n## AI Integration Guide")
            prompt_elements = design_schema.get("ai_consumption", {}).get("suggested_prompt_elements", [])
            if prompt_elements:
                 doc_parts.append("Key elements for AI prompts:")
                 for i, element in enumerate(prompt_elements):
                      doc_parts.append(f"{i+1}. {element}")

        return "\n".join(filter(None, doc_parts)) # Join non-empty parts

    except Exception as e:
        print(f"Error generating documentation: {e}")
        return "" # Return empty string on failure


# --- Main Orchestration Function ---

def extract_design_scheme_extended(url, output_file=None, generate_docs=True, optimize_ai=True, generate_code=True):
    """
    Extended version of the main function to extract a design scheme from a URL.
    Orchestrates fetching, analysis, schema generation, validation, and output generation.

    Args:
        url (str): The URL to analyze.
        output_file (str, optional): Base path to save the JSON output and other generated files.
                                     If None, results are only returned. Defaults to None.
        generate_docs (bool): Whether to generate markdown documentation. Defaults to True.
        optimize_ai (bool): Whether to create the AI-optimized version of the schema. Defaults to True.
        generate_code (bool): Whether to generate code snippets. Defaults to True.

    Returns:
        dict: A dictionary containing the results:
              - "design_schema": The core extracted design schema (dict).
              - "ai_optimized_schema": Schema optimized for AI (dict, if optimize_ai is True).
              - "documentation": Markdown documentation (str, if generate_docs is True).
              - "code_snippets": Dictionary of code snippets (dict, if generate_code is True).
              Returns None for keys if generation is skipped or fails.
    """
    results = {
        "design_schema": None,
        "ai_optimized_schema": None,
        "documentation": None,
        "code_snippets": None
    }
    driver = None # Initialize driver to None for finally block

    try:
        print(f"Starting design scheme extraction for: {url}")

        # Step 1: Fetch the webpage content, screenshot, and driver
        print("Fetching webpage content...")
        html_content, screenshot, driver = fetch_webpage(url)
        print("Webpage content fetched.")

        # Step 2: Determine website type for potential plugin application
        print("Determining website type...")
        website_type = determine_website_type(html_content, url)
        print(f"Detected website type: {website_type}")

        # Step 3: Extract individual design components
        print("Extracting color palette...")
        colors = extract_color_palette(screenshot, driver, html_content)
        print("Extracting typography...")
        typography = extract_typography(driver, html_content)
        print("Analyzing layout and spacing...")
        layout = analyze_layout(driver)
        print("Detecting component patterns...")
        components = detect_component_patterns(driver, html_content)
        print("Analyzing images and icons...")
        images = analyze_images_and_icons(driver, html_content)
        print("Core design elements extracted.")

        # Step 4: Generate the base design schema
        print("Generating base design schema...")
        design_schema = generate_design_schema(url, colors, typography, layout, components, images)
        results["design_schema"] = design_schema # Store base schema immediately
        print("Base schema generated.")

        # Step 5: Enhance schema with plugins based on website type
        print("Applying enhancement plugins...")
        design_schema = enhance_with_plugins(design_schema, website_type, html_content, driver)
        results["design_schema"] = design_schema # Update schema after plugins
        print("Plugins applied.")

        # Step 6: Validate the final base schema
        print("Validating generated schema...")
        if not validate_schema(design_schema):
            print("Warning: Generated schema did not pass validation. Output may be incomplete or incorrect.")
        else:
            print("Schema validation passed.")

        # Step 7: Generate AI-optimized version (optional)
        if optimize_ai:
            print("Optimizing schema for AI consumption...")
            ai_schema = optimize_for_ai_consumption(design_schema)
            results["ai_optimized_schema"] = ai_schema
            print("AI optimization complete.")

        # Step 8: Generate code snippets (optional)
        if generate_code:
            print("Generating code snippets...")
            code_snippets = generate_design_code_snippets(design_schema)
            results["code_snippets"] = code_snippets
            print("Code snippets generated.")

        # Step 9: Generate documentation (optional)
        if generate_docs:
            print("Generating documentation...")
            documentation = generate_documentation(design_schema)
            results["documentation"] = documentation
            print("Documentation generated.")

        # Step 10: Output results to files if output_file path is provided
        if output_file:
            print(f"Saving results to files based on prefix: {output_file}")
            # Ensure output directory exists (create if necessary)
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"Created output directory: {output_dir}")

            base_name, _ = os.path.splitext(output_file) # Use base name for related files

            # Save main schema (JSON)
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(design_schema, f, indent=2, ensure_ascii=False)
                print(f"-> Base design scheme saved to: {output_file}")
            except Exception as e:
                 print(f"Error saving base schema JSON: {e}")

            # Save AI-optimized schema (JSON)
            if optimize_ai and results["ai_optimized_schema"]:
                ai_file = f"{base_name}_ai.json"
                try:
                    with open(ai_file, 'w', encoding='utf-8') as f:
                        json.dump(results["ai_optimized_schema"], f, indent=2, ensure_ascii=False)
                    print(f"-> AI-optimized schema saved to: {ai_file}")
                except Exception as e:
                    print(f"Error saving AI schema JSON: {e}")

            # Save documentation (Markdown)
            if generate_docs and results["documentation"]:
                doc_file = f"{base_name}_docs.md"
                try:
                    with open(doc_file, 'w', encoding='utf-8') as f:
                        f.write(results["documentation"])
                    print(f"-> Documentation saved to: {doc_file}")
                except Exception as e:
                    print(f"Error saving documentation: {e}")

            # Save code snippets
            if generate_code and results["code_snippets"]:
                snippets_dir = f"{base_name}_snippets"
                if not os.path.exists(snippets_dir):
                    os.makedirs(snippets_dir)
                    print(f"Created snippets directory: {snippets_dir}")

                for name, snippet in results["code_snippets"].items():
                    # Determine file extension based on snippet type
                    if "css" in name: ext = ".css"
                    elif "tailwind" in name: ext = ".js" # Tailwind config is JS
                    elif "styled" in name: ext = ".js" # Styled components theme is JS
                    else: ext = ".txt" # Default extension

                    snippet_file = os.path.join(snippets_dir, f"{name}{ext}")
                    try:
                        with open(snippet_file, 'w', encoding='utf-8') as f:
                            f.write(snippet)
                        print(f"-> Code snippet '{name}' saved to: {snippet_file}")
                    except Exception as e:
                        print(f"Error saving snippet {name}: {e}")
            print("File saving process complete.")

        print("Design scheme extraction finished successfully.")
        return results

    except Exception as e:
        print(f"\n--- An error occurred during extraction ---")
        print(f"Error: {e}")
        # Print traceback for debugging
        print("\n--- Traceback ---")
        traceback.print_exc()
        print("-----------------\n")
        # Return partially filled results if possible, or just the empty structure
        return results

    finally:
        # Ensure the WebDriver is always closed
        if driver:
            print("Closing WebDriver...")
            try:
                driver.quit()
                print("WebDriver closed.")
            except Exception as e:
                print(f"Error closing WebDriver: {e}")


# --- Command-Line Interface ---

def main_extended():
    """Extended command line interface for the design scheme extractor."""
    parser = argparse.ArgumentParser(
        description='Extract web page design schemes (colors, typography, layout, etc.) for AI analysis and code generation.'
    )
    parser.add_argument('url', help='URL of the webpage to analyze')
    parser.add_argument(
        '-o', '--output',
        help='Output file path prefix. Saves schema JSON here, and related files (docs, snippets) alongside with suffixes.'
    )
    parser.add_argument(
        '-p', '--pretty', action='store_true',
        help='Print the main extracted JSON schema nicely formatted to the console.'
    )
    parser.add_argument(
        '--no-docs', action='store_true',
        help='Skip generating the Markdown documentation file.'
    )
    parser.add_argument(
        '--no-code', action='store_true',
        help='Skip generating code snippet files (CSS Vars, Tailwind, Styled Components).'
    )
    parser.add_argument(
        '--no-ai', action='store_true',
        help='Skip generating the AI-optimized schema file with descriptions.'
    )
    parser.add_argument(
        '--format', choices=['json', 'yaml'], default='json',
        help='Format for printing the schema to console with --pretty (default: json).'
    )

    args = parser.parse_args()

    # Run the main extraction process
    results = extract_design_scheme_extended(
        args.url,
        args.output,
        generate_docs=not args.no_docs,
        optimize_ai=not args.no_ai,
        generate_code=not args.no_code
    )

    # Print summary or pretty output if requested
    if results and results.get("design_schema"):
        if args.pretty:
            schema_to_print = results["design_schema"]
            print("\n--- Extracted Design Schema (Console Output) ---")
            if args.format == 'json':
                print(json.dumps(schema_to_print, indent=2, ensure_ascii=False))
            elif args.format == 'yaml':
                try:
                    print(yaml.dump(schema_to_print, allow_unicode=True, sort_keys=False))
                except NameError:
                    print("YAML output requires PyYAML. Please install it (`pip install PyYAML`). Falling back to JSON.")
                    print(json.dumps(schema_to_print, indent=2, ensure_ascii=False))
            print("-------------------------------------------------")
        else:
            # Print a brief summary if not printing the full schema
            print("\n--- Extraction Summary ---")
            summary = results["design_schema"].get("design_summary", {})
            colors = results["design_schema"].get("colors", {})
            print(f"Style Keywords: {', '.join(summary.get('style_keywords', ['N/A']))}")
            print(f"Primary Color: {colors.get('primary_color', 'N/A')}")
            print(f"Secondary Color: {colors.get('secondary_color', 'N/A')}")
            print(f"Accent Color: {colors.get('accent_color', 'N/A')}")
            if args.output:
                print(f"Full results saved with prefix: {args.output}")
            print("------------------------")
        return 0 # Indicate success
    else:
        print("\nExtraction failed or produced no results.")
        return 1 # Indicate failure


if __name__ == "__main__":
    # Add urllib.parse import needed for logo URL resolution
    from urllib.parse import urljoin
    sys.exit(main_extended())
