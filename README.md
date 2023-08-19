# Cult Beauty Siin Scraper

> This project was run and tested on python 3.11.4 with ubuntu 22.04. 

## Requirements:

To run this project you will need to install the following dependencies:

- Chrome browser 114 or later.
- Python 3.10 or later.

## How to use:

1. Clone the repository into your machine ```git clone https://github.com/eslam-allam/cult_beauty.git``` or download the zip file and extract it.

2. Create and activate virtual environment with python 3.10 or later.
   > This can be done using [conda](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#activating-an-environment), [virtualenv](https://docs.python.org/3/library/venv.html)...
3. Install the required packages from the **requirements.txt** file ```pip install -r requirements.txt```
4. Navigate to cult_beauty.py and locate **NUM_OF_WORKERS** variable and change it to a suitable number depending on the number of CPUs available on your machine.
5. Run the script ```python cult_beauty.py```

## Methodology

### Terminology

- **primary_SKU**: a unique identifier for the parent product found in the image url.
- **variant_SKU**: a unique identifier for variants of the parent product found in their image urls.
- **variant**: some sort of variation of the product such as color, size, shade, etc...
- **sub variant**: a variation of the parent product.
- **variant_type**: type of variations present for this product e.g. multi-color, multi-size, multi-shade, etc...
- **Stale element**: element that was previously present on the page but was destroyed somehow by some javascript in the page.
-  **element is present**: the element is currently on the page somewhere. (not necessarily visible)
-  **element is visible**: the element is currently on the page somewhere and it's also visible. (can be seen by the user)

In cult beauty we have multiple categories. Within each category you will find multiple pages. And within each page you will find multiple product links. First we manually put the links to the 10 categories in a list of strings. Then we programmatically traverse each page and every product in that page. 

Whenever you click on a specific product (regardless of whether the product has multiple variations or not), you will notice that cult beauty will display the same image of the same **variant** every time. We consider this to be the image of the **parent/primary product**. Every other variation of this product such as other colors or sizes are considered **variant**s.

When we first visit a product page, we grab the **primary_SKU** as well as any information that would not differ between the different **sub_variant**s such as description, brand_name, etc... This becomes the base for all **sub_variant**s later on. Then we check the **variant_type** of the product. Every **variant_type** will have a slightly different method for scraping. Then we navigate through every **variant** and grab information related to that specific **sub_variant** such as **variant_SKU**, price, number of reviews, rating, images, etc...

Lastly, we conduct some cleanup methods using pandas on some of the rows to match a specific format and export the result as an excel sheet.