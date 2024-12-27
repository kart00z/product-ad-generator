import requests
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urlparse
from jinja2 import Environment, FileSystemLoader
import re
import time
from datetime import datetime
from PIL import Image
import io
import numpy as np
from urllib.request import urlopen
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import cv2
import base64
from io import BytesIO
from playwright.sync_api import sync_playwright
from PIL import ImageSequence

def clean_image_url(url):
    """
    Cleans image URLs to get highest quality version
    """
    try:
        # AJIO specific cleaning (replace small dimensions with larger ones)
        if 'assets.ajio.com' in url:
            # Replace dimension patterns like -78Wx98H- with -1200Wx1500H-
            url = re.sub(r'-\d+Wx\d+H-', '-1200Wx1500H-', url)
        
        # Generic CDN parameter cleaning
        # Remove common low-quality indicators
        url = re.sub(r'(?i)(small|thumb|tiny|mobile|low|min)', 'large', url)
        
        # Remove or replace size-related parameters
        url = re.sub(r'[?&](w|width|h|height)=\d+', '', url)
        url = re.sub(r'[?&]size=\d+x\d+', '', url)
        url = re.sub(r'[?&]quality=\d+', '', url)
        
        # Try to get highest quality version
        if '?' in url:
            url = url.split('?')[0]
            
        return url
    except:
        return url

def is_valid_image(image_url, min_width=200, min_height=200, max_compression_ratio=0.1):
    """
    Checks if an image is valid based on:
    1. Not being blank/solid color
    2. Meeting minimum resolution requirements
    3. Not being too pixelated/low quality
    
    Args:
        image_url: URL of the image to check
        min_width: Minimum acceptable width in pixels
        min_height: Minimum acceptable height in pixels
        max_compression_ratio: Maximum acceptable compression ratio (lower means more compressed/lower quality)
    """
    try:
        # Download image
        response = urlopen(image_url, timeout=5)
        image_data = response.read()
        
        # Open image with PIL
        img = Image.open(io.BytesIO(image_data))
        
        # Check dimensions
        width, height = img.size
        if width < min_width or height < min_height:
            print(f"Debug - Image rejected (too small): {width}x{height}")
            return False
            
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Convert to numpy array for analysis
        img_array = np.array(img)
        
        # Check if image is blank or solid color
        std_dev = np.std(img_array)
        if std_dev < 10:  # Arbitrary threshold for "blankness"
            print(f"Debug - Image rejected (blank/solid color): std_dev={std_dev}")
            return False
            
        # Check for low quality/high compression
        # Calculate entropy as a measure of image detail
        histogram = img.histogram()
        histogram_length = sum(histogram)
        samples_probability = [hist_value/histogram_length for hist_value in histogram]
        entropy = -sum([p * np.log2(p) for p in samples_probability if p != 0])
        
        if entropy < max_compression_ratio * np.log2(256):
            print(f"Debug - Image rejected (low quality): entropy={entropy}")
            return False
            
        # Check for visible pixelation
        # Downscale and upscale to detect pixel patterns
        small = img.resize((width//4, height//4), Image.Resampling.LANCZOS)
        large = small.resize((width, height), Image.Resampling.NEAREST)
        diff = np.array(img) - np.array(large)
        if np.mean(np.abs(diff)) < 5:  # Arbitrary threshold for pixelation
            print(f"Debug - Image rejected (pixelated)")
            return False
            
        return True
        
    except Exception as e:
        print(f"Debug - Error checking image {image_url}: {str(e)}")
        return False

def is_duplicate_image(new_image_url, existing_images, similarity_threshold=0.95):
    """
    Checks if an image is a duplicate of existing images by comparing content
    
    Args:
        new_image_url: URL of the image to check
        existing_images: List of existing image URLs
        similarity_threshold: Threshold for considering images as duplicates (0-1)
    """
    try:
        # Download and process new image
        response = urlopen(new_image_url, timeout=5)
        new_img_data = response.read()
        new_img = Image.open(io.BytesIO(new_img_data))
        
        # Convert to small grayscale for faster comparison
        new_img = new_img.convert('L').resize((32, 32))
        new_array = np.array(new_img)
        
        # Compare with existing images in our list
        for existing_url in existing_images:
            try:
                # Download and process existing image
                response = urlopen(existing_url, timeout=5)
                existing_img_data = response.read()
                existing_img = Image.open(io.BytesIO(existing_img_data))
                
                # Convert to small grayscale
                existing_img = existing_img.convert('L').resize((32, 32))
                existing_array = np.array(existing_img)
                
                # Calculate similarity
                correlation = np.corrcoef(new_array.flatten(), existing_array.flatten())[0,1]
                if correlation > similarity_threshold:
                    print(f"Debug - Image rejected (duplicate): similarity={correlation:.2f}")
                    return True
                    
            except Exception as e:
                print(f"Debug - Error comparing with existing image {existing_url}: {str(e)}")
                continue
                
        return False
        
    except Exception as e:
        print(f"Debug - Error checking duplicate {new_image_url}: {str(e)}")
        return False

def extract_product_data(product_url):
    """
    Extracts product data from a public product page with more flexible selectors
    """
    try:
        # List of common User-Agents to rotate through/we do this to circumvent the bot detection
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]
        
        # Modified headers to be more browser-like and explicitly handle encoding
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',  # Explicitly state accepted encodings
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        session = requests.Session()
        
        # Try up to 3 times with different User-Agents. We do this to circumvent the bot detection
        for attempt in range(3):
            try:
                headers['User-Agent'] = random.choice(user_agents)
                response = requests.get(product_url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Debug information
                print("\nResponse Headers:", dict(response.headers))
                print("Content-Type:", response.headers.get('content-type'))
                print("Content-Encoding:", response.headers.get('content-encoding'))
                
                # Try to get content, falling back to raw text if decompression fails
                try:
                    if response.headers.get('content-encoding') == 'gzip':
                        import gzip
                        content = gzip.decompress(response.content).decode('utf-8')
                    elif response.headers.get('content-encoding') == 'deflate':
                        import zlib
                        content = zlib.decompress(response.content).decode('utf-8')
                    else:
                        content = response.text
                except Exception as e:
                    print(f"Warning - Decompression failed: {str(e)}, falling back to raw text")
                    content = response.text
                
                # Debug output
                print("\nResponse Status:", response.status_code)
                print("Response Encoding:", response.encoding)
                print("\nFirst 500 characters of decoded response:")
                print(content[:500])
                
                # Write response to file for debugging
                with open('debug_response.html', 'w', encoding='utf-8') as f:
                    f.write(content)
                
                soup = BeautifulSoup(content, 'html.parser')
                product_data = {}
                
                # Try to find structured data first
                for script in soup.find_all('script', {'type': 'application/ld+json'}):
                    try:
                        data = json.loads(script.string)
                        print("\nDebug - Found structured data:", json.dumps(data, indent=2)[:500])
                        
                        # Check if it's product data
                        if isinstance(data, dict) and data.get('@type') == 'Product':
                            product_data['title'] = data.get('name')
                            
                            # Get price from offers and that we can generate 
                            
                            if 'offers' in data:
                                offers = data['offers']
                                if isinstance(offers, dict):
                                    product_data['price'] = float(offers.get('price', 0))
                                elif isinstance(offers, list) and offers:
                                    product_data['price'] = float(offers[0].get('price', 0))
                            
                            # Get images
                            images = data.get('image', [])
                            if isinstance(images, str):
                                images = [images]
                            product_data['images'] = images[:4]
                            
                            print("\nDebug - Extracted product data from structured data:", json.dumps(product_data, indent=2))
                            break
                    except Exception as e:
                        print(f"Debug - Error parsing structured data: {str(e)}")
                        continue
                
                # If no data found, try meta tags
                if not product_data.get('images'):
                    # Try Open Graph tags
                    og_image = soup.find('meta', {'property': 'og:image'})
                    if og_image:
                        product_data['images'] = [og_image.get('content')]
                    
                    og_title = soup.find('meta', {'property': 'og:title'})
                    if og_title:
                        product_data['title'] = og_title.get('content')
                    
                    og_price = soup.find('meta', {'property': 'product:price:amount'})
                    if og_price:
                        try:
                            product_data['price'] = float(og_price.get('content', 0))
                        except:
                            pass
                    
                    print("\nDebug - Extracted product data from meta tags:", json.dumps(product_data, indent=2))
                
                # If still no data, continue with existing logic...
                if not product_data.get('images'):
                    # ... rest of the existing code ...
                    pass
                
                break
                
            except requests.exceptions.RequestException as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:  # Last attempt
                    raise
                time.sleep(1)  # Wait before retry
        
        # Try to determine if it's WooCommerce
        is_woocommerce = 'woocommerce' in content.lower()

        if is_woocommerce:
            # WooCommerce specific extraction
            title_element = soup.select_one('.product_title')
            if title_element:
                product_data['title'] = title_element.get_text().strip()
            
            # WooCommerce price - try multiple selectors
            price_selectors = [
                'p.price span.woocommerce-Price-amount bdi',
                '.price .woocommerce-Price-amount',
                '.summary .price .woocommerce-Price-amount',
                '[data-product-price]',
                '.price ins .woocommerce-Price-amount',
                '.price > .woocommerce-Price-amount'
            ]
            
            for selector in price_selectors:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.get_text().strip()
                    try:
                        # Extract only numbers and decimal points
                        price = ''.join(c for c in price_text if c.isdigit() or c == '.')
                        if price:
                            product_data['price'] = float(price)
                            break
                    except:
                        continue

            # WooCommerce images
            images = []
            # Main product image
            main_image = soup.select_one('.woocommerce-product-gallery__image img')
            if main_image:
                src = main_image.get('data-src') or main_image.get('src')
                if src:
                    images.append(src)
            
            # Gallery images
            gallery_images = soup.select('.woocommerce-product-gallery__image a')
            for img in gallery_images:
                src = img.get('href')
                if src and src not in images:
                    images.append(src)

            if images:
                product_data['image_url'] = images[0]
                product_data['images'] = images[:4]  # Limit to 4 images

            # Don't set default rating/review values for WooCommerce
            # Only add if actually found on the page
            rating_element = soup.select_one('.woocommerce-product-rating .rating')
            review_count_element = soup.select_one('.woocommerce-review-link')
            if rating_element and review_count_element:
                try:
                    product_data['rating'] = float(rating_element.get('value', 0))
                    review_text = review_count_element.get_text()
                    review_count = ''.join(filter(str.isdigit, review_text))
                    product_data['review_count'] = int(review_count) if review_count else 0
                except:
                    pass

        else:
            # Shopify logic
            product_data = {'title': '', 'price': None, 'images': [], 'description': '', 'rating': None}
            
            # First try to get price from JSON-LD
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and '@type' in data and data['@type'] == 'Product':
                        if 'offers' in data:
                            offers = data['offers']
                            if isinstance(offers, dict):
                                product_data['price'] = float(offers.get('price', 0))
                            elif isinstance(offers, list) and offers:
                                product_data['price'] = float(offers[0].get('price', 0))
                        break
                except:
                    continue

            # If no price found, try meta tags
            if not product_data['price']:
                price_meta = soup.find('meta', property='og:price:amount')
                if price_meta:
                    try:
                        product_data['price'] = float(price_meta.get('content', 0))
                    except:
                        pass

            # Try to find Shopify product JSON for images
            for script in soup.find_all('script'):
                if script.string and 'var meta = ' in script.string:
                    try:
                        json_text = script.string.split('var meta = ')[1].split(';\n')[0]
                        meta_data = json.loads(json_text)
                        
                        if 'product' in meta_data:
                            product = meta_data['product']
                            # Get images from product media
                            if 'media' in product:
                                for media in product['media']:
                                    if media.get('media_type') == 'image':
                                        src = media.get('src') or media.get('preview_image', {}).get('src')
                                        if src:
                                            if not src.startswith('http'):
                                                src = f"https:{src}"
                                            # Remove URL parameters to avoid duplicates
                                            base_src = src.split('?')[0]
                                            if base_src not in [img.split('?')[0] for img in product_data['images']]:
                                                # Clean the URL before adding it
                                                cleaned_src = clean_image_url(src)
                                                product_data['images'].append(cleaned_src)
                                break
                    except Exception as e:
                        print(f"Debug - Error parsing Shopify JSON: {str(e)}")
                        continue
            
            # If still no images, try the previous methods
            #We will only fall back to OpenCV if all other methods are exhausted
            if not product_data['images']:
                # Try meta og:image
                og_image = soup.find('meta', property='og:image')
                if og_image:
                    src = og_image.get('content')
                    if src and src not in product_data['images']:
                        # Clean the URL before adding it
                        cleaned_src = clean_image_url(src)
                        product_data['images'].append(cleaned_src)

            # Debug output
            print("\nDebug - Found images:", product_data['images'])
            print("Debug - Found price:", product_data['price'])
            
            # Ensure we have max 4 unique images
            product_data['images'] = list(dict.fromkeys([img.split('?')[0] for img in product_data['images']]))[:4]

            # Try to find additional product images
            if len(product_data['images']) < 4:
                # Try product gallery images
                gallery_selectors = [
                    '.product-gallery__image img',
                    '.product__media-item img',
                    '.product-single__media img',
                    '.product-single__photo img',
                    '[data-product-media-type="image"] img',
                    '.product__slide img',
                    '.product-single__thumbnail img'
                ]
                #Note: we don't need to do this
                for selector in gallery_selectors:
                    gallery_images = soup.select(selector)
                    for img in gallery_images:
                        src = img.get('data-src') or img.get('data-original') or img.get('src')
                        if src:
                            if not src.startswith('http'):
                                src = f"https:{src}"
                            base_src = src.split('?')[0]
                            if base_src not in [img.split('?')[0] for img in product_data['images']]:
                                # Clean the URL before adding it
                                cleaned_src = clean_image_url(src)
                                product_data['images'].append(cleaned_src)
                                if len(product_data['images']) >= 4:
                                    break
                        if len(product_data['images']) >= 4:
                            break

                # Try product variant images if still not enough
                if len(product_data['images']) < 4:
                    for script in soup.find_all('script'):
                        if script.string and ('productImages' in script.string or 'product_images' in script.string):
                            try:
                                # Look for image URLs in the script content
                                urls = re.findall(r'https?://[^\s<>"\']+?(?:jpg|jpeg|png|webp)', script.string)
                                for url in urls:
                                    base_url = url.split('?')[0]
                                    if base_url not in [img.split('?')[0] for img in product_data['images']]:
                                        # Clean the URL before adding it
                                        cleaned_url = clean_image_url(url)
                                        product_data['images'].append(cleaned_url)
                                        if len(product_data['images']) >= 4:
                                            break
                            except:
                                continue

        # Add this after the existing image extraction logic in extract_product_data function
        # If we still don't have enough images, try generic selectors
        if len(product_data['images']) < 4:
            # Super comprehensive list of generic image selectors
            generic_image_selectors = [
                # High-priority product image selectors
                '[id*="product"][id*="image"] img', '[class*="product"][class*="image"] img',
                '[id*="product"][id*="photo"] img', '[class*="product"][class*="photo"] img',
                '[id*="product"][id*="media"] img', '[class*="product"][class*="media"] img',
                '[id*="product"] img', '[class*="product"] img',
                
                # Gallery and slider patterns
                '[class*="gallery"] img', '[class*="slider"] img', '[class*="carousel"] img',
                '[class*="slide"] img', '[class*="thumbnail"] img', '[class*="preview"] img',
                '.swiper img', '.slick img', '.owl-carousel img',
                
                # Common e-commerce patterns
                '[class*="main-image"]', '[class*="featured-image"]', '[class*="product-image"]',
                '[class*="hero-image"]', '[class*="zoom"]', '[class*="magnify"]',
                
                # Image containers
                '[class*="image-container"] img', '[class*="img-container"] img',
                '[class*="photo-container"] img', '[class*="media-container"] img',
                
                # Common attribute patterns
                '[data-image]', '[data-src]', '[data-lazy]', '[data-srcset]',
                '[data-zoom]', '[data-zoom-image]', '[data-large]', '[data-full]',
                '[data-slide]', '[data-thumb]', '[data-preview]',
                
                # Schema.org and OpenGraph
                '[itemprop="image"]', '[property="og:image"]',
                
                # Fallback to content areas
                'main img', 'article img', '.content img', '.product img',
                '.details img', '.info img', '.description img'
            ]
            
            # Comprehensive list of image attributes to check
            image_attributes = [
                'src', 'data-src', 'data-original', 'data-lazy', 'data-srcset',
                'data-zoom-image', 'data-large', 'data-full', 'data-image',
                'data-zoom', 'data-high-res', 'data-retina', 'srcset',
                'data-original-src', 'data-lazy-src', 'data-master',
                'data-thumb', 'data-slide-img', 'data-normal',
                'data-zoom-src', 'data-large-src', 'data-big',
                'data-super-size', 'data-xlarge', 'href'
            ]

            # Try each selector
            for selector in generic_image_selectors:
                if len(product_data['images']) >= 4:
                    break
                    
                try:
                    
                    
                    images = soup.select(selector)
                    for img in images:
                        if len(product_data['images']) >= 4:
                            break
                            
                        # Try all possible attributes
                        for attr in image_attributes:
                            if img.get(attr):
                                src = img[attr]
                                
                                # Handle srcset attribute
                                if attr == 'srcset':
                                    try:
                                        srcset = src.split(',')[0].strip().split(' ')[0]
                                        src = srcset
                                    except:
                                        continue
                                
                                # Clean and validate URL
                                if src:
                                    try:
                                        # Handle relative URLs
                                        if src.startswith('//'):
                                            src = 'https:' + src
                                        elif src.startswith('/'):
                                            parsed_url = urlparse(product_url)
                                            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                            src = base_url + src
                                        elif not src.startswith(('http://', 'https://')):
                                            parsed_url = urlparse(product_url)
                                            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                            src = f"{base_url}/{src.lstrip('/')}"
                                            
                                        # Remove URL parameters and check for duplicates
                                        base_src = src.split('?')[0]
                                        if base_src not in [img.split('?')[0] for img in product_data['images']]:
                                            # Validate image URL extension
                                            if any(base_src.lower().endswith(ext) for ext in ['.jpg','.jpeg','.png','.webp','.gif']):
                                                # Check image quality and duplicates
                                                if is_valid_image(src) and not is_duplicate_image(src, product_data['images']):
                                                    product_data['images'].append(src)
                                                    break
                                    except:
                                        continue
                except:
                    continue

            # Try to find images in any JSON/script data
            if len(product_data['images']) < 4:
                for script in soup.find_all('script'):
                    if script.string:
                        try:
                            # Look for image URLs in the script content
                            urls = re.findall(r'https?://[^\s<>"\']+?(?:jpg|jpeg|png|webp|gif)', script.string)
                            # Also look for base64 encoded images
                            base64_images = re.findall(r'data:image/[^;]+;base64,[a-zA-Z0-9+/]+=*', script.string)
                            
                            # Process regular URLs
                            for url in urls:
                                base_url = url.split('?')[0]
                                if base_url not in [img.split('?')[0] for img in product_data['images']]:
                                    product_data['images'].append(url)
                                    if len(product_data['images']) >= 4:
                                        break
                                    
                            # Process base64 images if needed
                            if len(product_data['images']) < 4 and base64_images:
                                for base64_img in base64_images:
                                    if base64_img not in product_data['images']:
                                        product_data['images'].append(base64_img)
                                        if len(product_data['images']) >= 4:
                                            break
                        except:
                            continue

            # Try parsing structured data
            if len(product_data['images']) < 4:
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        json_data = json.loads(script.string)
                        if isinstance(json_data, dict):
                            # Look for images in common schema.org structures
                            image_fields = ['image', 'images', 'photo', 'photos', 'thumbnail']
                            for field in image_fields:
                                if field in json_data:
                                    images = json_data[field]
                                    if isinstance(images, str):
                                        images = [images]
                                    if isinstance(images, list):
                                        for img in images:
                                            if isinstance(img, str) and img not in product_data['images']:
                                                product_data['images'].append(img)
                                                if len(product_data['images']) >= 4:
                                                    break
                    except:
                        continue

            # Ensure all image URLs are valid and unique
            product_data['images'] = list(dict.fromkeys([
                img for img in product_data['images'] 
                if img.startswith(('http://', 'https://', 'data:image/'))
            ]))[:4]

        # Extract store name from URL
        parsed_url = urlparse(product_url)
        store_name = parsed_url.netloc.split('.')[0].upper()
        if store_name == 'WWW':  # Handle www. prefix
            store_name = parsed_url.netloc.split('.')[1].upper()

        # Update product data
        product_data.update({
            'brand_name': store_name,
            'original_price': float(product_data['price']) * 1.2 if product_data.get('price') else None,
            'discount_percent': 20,
            'features': [
                'Premium Quality',
                'Limited Edition',
                'Exclusive Design'
            ],
            'shipping': 'Free Shipping Available',
            'product_url': product_url
        })

        # After all image extraction attempts, validate the images before returning
        if product_data.get('images'):
            valid_images = []
            for img_url in product_data['images']:
                if img_url.startswith('data:image'):
                    valid_images.append(img_url)
                elif is_valid_image(img_url):  # Using existing is_valid_image function
                    valid_images.append(img_url)
            
            # If no valid images found, try CV approach
            if not valid_images:
                print("\nDebug - No valid images found, attempting CV-based image detection...")
                cv_images = find_images_with_cv(product_url)
                if cv_images:
                    product_data['images'] = cv_images
                    print(f"\nDebug - Found {len(cv_images)} images using CV")
            else:
                product_data['images'] = valid_images

        # If still no images found, try computer vision approach (existing fallback)
        if not product_data.get('images'):
            print("\nDebug - Attempting CV-based image detection...")
            cv_images = find_images_with_cv(product_url)
            if cv_images:
                product_data['images'] = cv_images
                print(f"\nDebug - Found {len(cv_images)} images using CV")

        return product_data
        
    except Exception as e:
        print(f"Debug - Error in extract_product_data: {str(e)}")
        raise Exception(f"Error extracting product data: {str(e)}")
    
def generate_ad_creative(product_data, output_path, width=300, height=300, template_name='ad_template.html'):
    """
    Generates the ad creative HTML file with option to choose template
    """
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template(template_name)

    # Store original numeric values
    original_price_value = product_data.get('price')
    original_original_price_value = product_data.get('original_price')

    # Add clickTag with properly encoded special characters
    url = product_data.get('product_url', '')
    parsed_url = urlparse(url)
    
    # Encode the path components individually to preserve URL structure
    path_parts = parsed_url.path.split('/')
    encoded_path_parts = [part.replace('-', '%2D') for part in path_parts]
    encoded_path = '/'.join(encoded_path_parts)
    
    # Reconstruct the URL preserving the original scheme and domain
    encoded_url = f"{parsed_url.scheme}://{parsed_url.netloc}{encoded_path}"
    if parsed_url.query:
        encoded_url += f"?{parsed_url.query}"
    if parsed_url.fragment:
        encoded_url += f"#{parsed_url.fragment}"
        
    # Store both the encoded and original URLs
    product_data['clickTag'] = encoded_url
    product_data['product_url'] = encoded_url  # This is what the template will use

    # Format prices with ₹ symbol (without $)
    if product_data.get('price'):
        price = f"₹{int(float(original_price_value)):,}"
        # Remove any $ symbol if present
        price = price.replace('$', '')
    else:
        price = None
        
    if product_data.get('original_price'):
        original_price = f"₹{int(float(original_original_price_value)):,}"
        # Remove any $ symbol if present
        original_price = original_price.replace('$', '')

    else:
        original_price = None
    
    # Keep the original numeric values in product_data
    product_data['price'] = original_price_value
    product_data['original_price'] = original_original_price_value

    ad_html = template.render(
        width=width,
        height=height,
        images=product_data.get('images', []),
        image_url=product_data.get('image_url'),
        title=product_data['title'],
        price=price,
        original_price=original_price,
        product_url=product_data['product_url'],
        brand_name=product_data.get('brand_name'),
        discount_percent=product_data.get('discount_percent'),
        review_count=product_data.get('review_count'),
        rating=product_data.get('rating', 4.9),
        features=product_data.get('features'),
        shipping=product_data.get('shipping'),
        product_data=product_data
    )

    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(ad_html)

def get_all_product_urls(shop_url):
    all_product_urls = []
    page = 1
    
    while True:
        url = f"{shop_url}/products.json?limit=250&page={page}"
        response = requests.get(url)
        products = response.json().get('products', [])
        
        if not products:
            break
            
        for product in products:
            all_product_urls.append(f"{shop_url}/products/{product['handle']}")
            
            # Break if we have 5 products
            if len(all_product_urls) >= 1:
                return all_product_urls[:1]
                
        page += 1
    
    return all_product_urls[:5]  # Ensure we only return 5 products

def validate_product_data(product_data):
    """
    Validates product data and images are still accessible
    """
    required_fields = ['title', 'price', 'images']
    for field in required_fields:
        if not product_data.get(field):
            raise ValueError(f"Missing required field: {field}")
            
    # Validate images are accessible
    for image_url in product_data.get('images', []):
        response = requests.head(image_url)
        if response.status_code != 200:
            raise ValueError(f"Image not accessible: {image_url}")

def find_images_with_cv(product_url):
    """
    Uses Selenium and OpenCV to find product images on the page
    """
    try:
        # Setup headless Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(product_url)
        
        # Wait for page to load
        driver.implicitly_wait(5)
        
        # Take screenshot
        screenshot = driver.get_screenshot_as_png()
        nparr = np.frombuffer(screenshot, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Find potential product image areas
        # Look for rectangular areas that might be product images
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        potential_images = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            # Filter for reasonable image sizes
            if w > 200 and h > 200:  # Minimum size threshold
                roi = img[y:y+h, x:x+w]
                # Save region as PNG

                is_success, buffer = cv2.imencode(".png", roi)
                if is_success:
                    potential_images.append(BytesIO(buffer.tobytes()))
        
        driver.quit()
        
        # Convert to base64 for storage
        image_urls = []
        for i, img_bytes in enumerate(potential_images[:4]):  # Limit to 4 images
            img = Image.open(img_bytes)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            image_urls.append(f"data:image/png;base64,{img_str}")
        
        return image_urls
        
    except Exception as e:
        print(f"Debug - Error in CV image detection: {str(e)}")
        return []

def capture_ad_as_gif(html_path, output_gif_path, width=300, height=250, duration=5, fps=30):  # Increased fps from 24 to 30
    """
    Captures the HTML ad animation as a GIF using Playwright with higher quality settings
    """
    try:
        with sync_playwright() as p:
            # Launch browser with specific viewport
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': width, 'height': height},
                device_scale_factor=2  # Keep at 2 to maintain proper scaling
            )
            page = context.new_page()
            
            # Navigate to the HTML file
            page.goto(f"file://{os.path.abspath(html_path)}")
            
            # Wait for the ad container to be ready
            page.wait_for_selector('.ad-container')
            
            # Inject custom styles to ensure proper rendering
            page.add_style_tag(content="""
                body { margin: 0; padding: 0; overflow: hidden; }
                .ad-container {
                    width: 300px !important;
                    height: 250px !important;
                    overflow: hidden !important;
                    position: relative !important;
                    transform: none !important;
                }
            """)
            
            # Wait for animations to start
            page.wait_for_timeout(1000)
            
            # Capture frames with higher quality settings
            frames = []
            frame_count = duration * fps
            
            for _ in range(frame_count):
                # Capture screenshot with higher quality
                screenshot = page.screenshot(
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                    type='png',
                    quality=100
                )
                
                # Convert to PIL Image
                img = Image.open(io.BytesIO(screenshot))
                frames.append(img)
                
                # Wait for next frame
                page.wait_for_timeout(int(1000/fps))
            
            # Save as optimized GIF with higher quality settings
            frames[0].save(
                output_gif_path,
                save_all=True,
                append_images=frames[1:],
                optimize=False,
                duration=int(1000/fps),
                loop=0,
                quality=100
            )
            
            # Close browser
            browser.close()
            
            print(f"Generated GIF: {output_gif_path}")
            
            # Optimize file size while maintaining quality
            try:
                with Image.open(output_gif_path) as img:
                    img.save(
                        output_gif_path,
                        save_all=True,
                        append_images=list(ImageSequence.Iterator(img))[1:],
                        optimize=True,
                        duration=int(1000/fps),
                        loop=0,
                        quality=100,  # Increased from 95 to 100
                        disposal=2,
                        transparency=0
                    )
            except Exception as e:
                print(f"Warning: Could not optimize GIF: {str(e)}")
                
    except Exception as e:
        print(f"Error generating GIF: {str(e)}")

def main():
    try:
        product_url = input("Enter the Shopify product URL: ").strip()
        if not product_url:
            raise ValueError("Product URL cannot be empty")
            
        try:
            print(f"\nProcessing: {product_url}")
            product_data = extract_product_data(product_url)
            
            output_dir = 'output'
            os.makedirs(output_dir, exist_ok=True)
            
            product_handle = urlparse(product_url).path.split('/')[-1]
            
            for width, height in [(300, 250), (300, 600), (728, 90)]:
                size_output_path = os.path.join(output_dir, f'{product_handle}_{width}x{height}_ad.html')
                generate_ad_creative(product_data, size_output_path, width, height)
                print(f"Generated ad creative: {size_output_path}")
                
        except Exception as e:
            print(f"Error processing {product_url}: {str(e)}")
                
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    main()



