# Shopify Ad Creative Generator
A work-in-progress automated tool to generate HTML5 ad creatives from Shopify product pages. This tool extracts product information and generates responsive, animated ad banners in multiple standard sizes.
## Features
- Extracts product data from any Shopify product page
 Generates HTML5 ad creatives in multiple sizes (300x250, 300x600, 728x90)
 Automatic image carousel with smooth transitions
 Responsive design with modern UI elements
 Price comparison and discount highlighting
 Mobile-friendly and cross-browser compatible
 Automatic image quality validation
 Duplicate image detection
 Fallback image detection using OpenCV
## Requirements
- Python 3.7+
 Chrome WebDriver (for Selenium)
 Required Python packages (see requirements.txt)
## Installation
1. Clone the repository:
`bash
git clone https://github.com/kart00z/product-ad-generator.git
cd product-ad-generator`

2. Install required packages:
`bash
pip install -r requirements.txt`

3. Install Chrome WebDriver for your Chrome version

## Usage

Run the script with:
`bash
python shopify_ad_tool_working.py`

When prompted, enter a Shopify product URL. The script will generate ad creatives in the following sizes:
- 300x250 (Medium Rectangle)
- 300x600 (Half Page)
- 728x90 (Leaderboard)

Output files will be created in the `output` directory.

## Project Structure
```
product-ad-generator/
├── shopify_ad_tool_working.py # Main script
├── requirements.txt # Python dependencies
├── README.md # Project documentation
├── templates/ # HTML templates
└── ad_template.html # Ad creative template
```


## How It Works

1. **Product Data Extraction**
   - Scrapes product information from product pages
   - Handles both standard Shopify and WooCommerce formats, along with fallback cases (that use OpenCV) for other online stores 
   - Extracts prices, images, titles, and other metadata

2. **Image Processing**
   - Validates image quality and dimensions
   - Detects and removes duplicate images
   - Falls back to CV-based detection if needed

3. **Ad Generation**
   - Uses Jinja2 templating for HTML generation
   - Creates responsive layouts for different ad sizes
   - Implements smooth image carousel
   - Adds interactive elements and animations

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
