from selenium.webdriver.chrome import webdriver, options
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.relative_locator import By 
from selenium.webdriver.support.select import Select 
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlsplit
import os
import pandas as pd
from selenium.webdriver.support.color import Color
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import current_process 
import logging
import gzip
import shutil
import datetime
from logging.handlers import TimedRotatingFileHandler
from tqdm import tqdm
import time
import re

LOGGING_LEVEL = logging.DEBUG
LOGGING_FOLDER = './scraping_logs'
LOGGING_FILE = f'{LOGGING_FOLDER}/cult_beauty.log'

if not os.path.isdir(LOGGING_FOLDER):
    os.makedirs(LOGGING_FOLDER)

def rotator(source, dest):
    with open(source, 'rb') as f_in:
        with gzip.open(f'{dest}.gz', 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    os.remove(source)

def filer(default_name):
    now = datetime.datetime.now()
    folder_name = f'{LOGGING_FOLDER}/{now.strftime("%Y")}/{now.strftime("%Y-%m")}'
    if not os.path.isdir(folder_name):
        os.makedirs(folder_name)
    base_name = os.path.basename(default_name)
    return f'{folder_name}/{base_name}'

logger = logging.getLogger(__name__)

logging_formatter = logging.Formatter(
    fmt='%(asctime)s %(processName)s %(filename)s Line.%(lineno)d %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

file_handler = TimedRotatingFileHandler(filename=LOGGING_FILE, when='midnight')
file_handler.setFormatter(logging_formatter)
file_handler.namer = filer
file_handler.rotator = rotator

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging_formatter)

logger.addHandler(file_handler)

logger.setLevel(LOGGING_LEVEL)


class ProductType:
    SINGLE = 'single'
    MULTI_SIZE = 'multi-size'
    MULTI_COLOR = 'multi-color'
    MULTI_SHADE = 'multi-shade'
    MULTI_OPTION = 'multi-option'

def safe_get_element(wd: webdriver.WebDriver, by: By, value:str):
    try:
        element = wd.find_element(by, value)
        return element
    except NoSuchElementException:
        return None
    

def click_element_refresh_stale(wd: webdriver.WebDriver, element: WebElement, by: By, locator: str, index = None):
    while True:
        try:
            wd.execute_script("arguments[0].click();", element)
            return element
        except Exception:
            logger.debug('Could not click element. Refreshing...')
            if index is None:
                element = wd.find_element(by, locator)
            else:
                element = wd.find_elements(by, locator)[index]

def get_variation_name(variation_details: dict[str, object]):
    if variation_details is None:
        return ''
    product_type = variation_details.get('product_type', None)
    if product_type == ProductType.MULTI_COLOR:
        variation = variation_details['color']
    elif product_type == ProductType.MULTI_SIZE:
        variation = variation_details['size']
    elif product_type == ProductType.MULTI_SHADE:
        variation = variation_details['shade']
    elif product_type == ProductType.SINGLE:
        variation = 'single'
    else:
        variation = 'NOT_FOUND'
    return variation

def get_attribute_retry_stale(wd: webdriver.WebDriver, element: WebElement ,attribute: str, 
                              variation_details: dict[str, object], by: By, value: str, 
                              index = None, label = 'element', max_retries = 5):
    stale_counter = 0
    result = None

    if element is None: return None
    while stale_counter < max_retries:
        try:
            result = element.get_attribute(attribute)
            break
        except StaleElementReferenceException:
            variation = get_variation_name(variation_details)
            logger.debug(f'{label} {index + 1 if index is not None else ""} in URL: "{variation_details["product_url"]}" variation: "{variation}" is stale. Refreshing...')
            if index is None:
                searched_element = safe_get_element(wd, by, value)
                if searched_element is not None:
                    element = searched_element
                else:
                    stale_counter += 1
            else:
                elements = wd.find_elements(By.CLASS_NAME, 'athenaProductImageCarousel_image')
                if len(elements) >= index + 1:
                    element = elements[index]
                else:
                    stale_counter += 1
    return result

def get_variation_images(wd: webdriver.WebDriver, variation_details:dict[str, object]):
    right_arrow = wd.find_element(By.CLASS_NAME, 'athenaProductImageCarousel_rightArrow')
    for i, image in enumerate(wd.find_elements(By.CLASS_NAME, 'athenaProductImageCarousel_image')):
        if i != 0:
            right_arrow = click_element_refresh_stale(wd, right_arrow, By.CLASS_NAME, 'athenaProductImageCarousel_rightArrow')
        image_src = get_attribute_retry_stale(wd, image, 'src', variation_details, By.CLASS_NAME
                                                           , 'athenaProductImageCarousel_image', i, 'image')
        if image_src is None:
            break
        variation_details[f'product_image_{i+1}'] = image_src
    return variation_details

def wait_for_presence_get(wd: webdriver.WebDriver, by: By, value: str, wait_for: int = 2):
    try:
        WebDriverWait(wd, wait_for).until(EC.presence_of_element_located((by, value)))
    except TimeoutException:
        return None
    return wd.find_element(by, value)

def get_variation_misc_details(wd: webdriver.WebDriver, variation_details:dict[str, object], product_id: str):
    variation_details['variant_SKU'] = product_id
    product_name = wait_for_presence_get(wd, By.CLASS_NAME, 'productName_title')
    variation_details['product_name'] = get_attribute_retry_stale(wd, product_name, 'textContent', variation_details
                                                                ,By.CLASS_NAME, 'productName_title', label='Product name')
    try:
        product_rating = wait_for_presence_get(wd ,By.CLASS_NAME, 'productReviewStarsPresentational')

        product_rating = get_attribute_retry_stale(wd, product_rating, 'aria-label', variation_details, By.CLASS_NAME, 
                                                   'productReviewStarsPresentational', label='Product rating')
        if product_rating is not None:
            variation_details['product_rating'] = float(product_rating.strip().split(' ')[0])
        else:
            variation_details['product_rating'] = None
    except NoSuchElementException:
        variation_details['product_rating'] = None
    try:
        number_of_reviews = wait_for_presence_get(wd, By.CLASS_NAME, 'productReviewStars_numberOfReviews')
        number_of_reviews = get_attribute_retry_stale(wd, number_of_reviews, 'textContent', variation_details, By.CLASS_NAME, 
                                                   'productReviewStars_numberOfReviews', label='Number of reviews')
        if number_of_reviews is not None:
            variation_details['number_of_reviews'] = int(number_of_reviews.strip().split(' ')[0])
        else:
            variation_details['number_of_reviews'] = None
    except NoSuchElementException:
        variation_details['number_of_reviews'] = None
    variation_details['price'] = wd.find_element(By.CLASS_NAME, 'productPrice_price').text.strip('£ ')
    try:
        wd.find_element(By.CLASS_NAME, 'productAddToBasket-soldOut')
        variation_details['in_stock'] = 'no'
    except NoSuchElementException:
        variation_details['in_stock'] = 'yes'
    return variation_details

def get_multi_size_details(wd: webdriver.WebDriver, product_details: dict[str, object]) -> list[dict[str, object]]:
    variations = []
    buttons = wd.find_elements(By.CLASS_NAME, 'athenaProductVariations_box')
    for i, button in enumerate(buttons):
        button = wd.find_elements(By.CLASS_NAME, 'athenaProductVariations_box')[i]
        variation_details = product_details.copy()
        is_selected = safe_get_element(button, By.CLASS_NAME, 'srf-hide')
        if is_selected is None:
            old_price = get_old_price(wd)
            wd.execute_script('arguments[0].click();', button)
            try:
                WebDriverWait(wd, 10).until(EC.staleness_of(old_price))
            except Exception:
                logger.warning(f'Could not find old price for url: "{product_details["product_url"]}"')
            button = wd.find_elements(By.CLASS_NAME, 'athenaProductVariations_box')[i]
        variation_details['size'] = button.text
        variation_details = get_variation_images(wd, variation_details)
        if not variation_details.get('product_image_1', False):
            logger.error(f'Could not find primary image from URL: "{variation_details["product_url"]}". Size: "{variation_details["size"]}"')
            continue
        product_id = get_id_from_url(variation_details['product_image_1'])
        variation_details = get_variation_misc_details(wd, variation_details, product_id)
        variations.append(variation_details)
    return variations

def get_id_from_url(url:str):
    base_name = os.path.basename(urlsplit(url).path)
    return base_name.split('.')[0].split('-')[0].strip()

def get_old_price(wd: webdriver.WebDriver):
    try:
        return wd.find_element(By.CLASS_NAME, 'productPrice_price')
    except NoSuchElementException:
        return wd.find_element(By.CLASS_NAME, 'productPrice_fromPrice')
    
def rgb_to_hex(rgb: list):
    return '#%02x%02x%02x' % (int(rgb[0]), int(rgb[1]), int(rgb[2]))

def get_multi_color_details(wd: webdriver.WebDriver, product_details: dict[str, object], product_type: str) -> list[dict[str, object]]:
    variations = []
    drop_down_list = wd.find_element(By.CLASS_NAME, 'athenaProductVariations_dropdown')
    select = Select(drop_down_list)
    for option, id in [(x.text, x.get_attribute('value')) for x in select.options if x.text.casefold() != 'Please choose...'.casefold()]:
        variation_details = product_details.copy()
        old_price = get_old_price(wd)
        select = Select(wd.find_element(By.CLASS_NAME, 'athenaProductVariations_dropdown'))
        select.select_by_visible_text(option)
        try:
            WebDriverWait(wd, 10).until(EC.staleness_of(old_price))
        except Exception:
            logger.debug(f'Could not find old price for url: "{product_details["product_url"]}", for value')
        if product_type == ProductType.MULTI_COLOR:
            variation_type = 'color'
        elif product_type == ProductType.MULTI_SHADE:
            variation_type = 'shade'
        elif product_type == ProductType.MULTI_OPTION:
            variation_type = 'option'
        else:
            raise ValueError(f'Invalid product type: {product_type}')
        variation_details[variation_type] = option
        variation_details = get_variation_images(wd, variation_details)
        product_id = get_id_from_url(variation_details['product_image_1'])
        variation_details = get_variation_misc_details(wd, variation_details, product_id)

        if product_type != ProductType.MULTI_OPTION:
            color = wd.find_element(By.CSS_SELECTOR, f"span[data-value-id='{id}']").value_of_css_property('background-color')
            color = Color.from_string(color).hex
            variation_details[f'{variation_type}_hex'] = color
        variations.append(variation_details)
    return variations

def create_serialized_sku(group:pd.Series, mask):
    count = 2
    serialized_skus = []
    for idx, row in group.items():
        if mask[idx]:
            serialized_skus.append((f"{row}-1", pd.NA))
        else:
            serialized_skus.append((f"{row}-{count}", row))
            count += 1
    return pd.Series(serialized_skus, index=group.index)

def get_product_variations_from_type(wd: webdriver.WebDriver, product_details: dict[str, object], url):
    variation_label = safe_get_element(wd, By.CLASS_NAME, 'athenaProductVariations_dropdownLabel')
    product_variations = []
    if variation_label is not None:
        variation = variation_label.text.strip()
        if variation.replace(' ', '').casefold() in color_variation_tags:
            product_details['product_type'] = ProductType.MULTI_COLOR
            product_variations = get_multi_color_details(wd, product_details, ProductType.MULTI_COLOR)
        elif variation.replace(' ', '').casefold() in shade_variation_tags:
            product_details['product_type'] = ProductType.MULTI_SHADE
            product_variations = get_multi_color_details(wd, product_details, ProductType.MULTI_SHADE)
        elif variation.replace(' ', '').casefold() in size_variation_tags:
            product_details['product_type'] = ProductType.MULTI_SIZE
            product_variations = get_multi_size_details(wd, product_details)
        elif variation.replace(' ', '').casefold() in option_variation_tags:
            product_details['product_type'] = ProductType.MULTI_OPTION
            product_variations = get_multi_color_details(wd, product_details, ProductType.MULTI_OPTION)
        else:
            logger.error(f'Unknown variant type: "{variation}". URL: {url}')
    else:
        product_details['product_type'] = ProductType.SINGLE
        product_details = get_variation_images(wd, product_details)
        if not product_details.get('product_image_1', False):
            logger.error(f'Could not find primary image of single product from URL: "{product_details["product_url"]}".')
            return product_variations
        product_id = get_id_from_url(product_details['product_image_1'])
        product_details = get_variation_misc_details(wd, product_details, product_id)
        product_variations = [product_details]
    return product_variations

def get_product_descriptions(wd: webdriver.WebDriver, product_details: dict[str, object]):
    for button in wd.find_elements(By.CLASS_NAME, 'productDescription_accordionControl'):
        try:
            if not button.text:
                continue
            button_id = button.get_attribute("id")
            is_expanded = button.get_attribute('aria-expanded')
            if is_expanded == 'false':
                wd.execute_script("arguments[0].click();", button)
            description_content = wd.find_element(By.ID, button_id.replace('heading', 'content')).text
            product_details[button.text] = description_content
        except ElementNotInteractableException:
            logger.debug(f'cannot click element with id: {button_id}')
        except Exception:
            logger.exception('Unexpected error occurred while getting product descriptions.', exc_info=True)
        time.sleep(ACTION_DELAY_SEC)
    
    return product_details

def get_product_details(wd:webdriver.WebDriver, urls: list[str], current_bar_position: int):
    df = pd.DataFrame()
    # TODO add reset and leave = True
    for url in tqdm(urls, colour='green', position=current_bar_position + 1, desc='Products scanned', unit='Products', leave=False):
        try:
            wd.get(url)
            product_details = {}
            product_variations = []
            product_details['product_url'] = url
            brand_element = safe_get_element(wd, By.CLASS_NAME, 'productBrandLogo_image')

            product_details['brand_name'] = brand_element.get_attribute('title') if brand_element is not None else None
            product_details['brand_logo'] = brand_element.get_attribute('src') if brand_element is not None else None

            primary_sku = wait_for_presence_get(wd, By.CLASS_NAME, 'athenaProductImageCarousel_image')
            primary_sku = get_attribute_retry_stale(wd, primary_sku, 'src', product_details, By.CLASS_NAME, 'athenaProductImageCarousel_image',
                                                    label = 'Primary SKU')
            if primary_sku is None:
                logger.error('Could not find primary SKU for URL: "%s". Skipping...', url)
                continue
            product_details['primary_SKU'] = get_id_from_url(primary_sku)
            product_details = get_product_descriptions(wd, product_details)
            product_variations = get_product_variations_from_type(wd, product_details, url)
            df = pd.concat([df, pd.DataFrame(product_variations)], ignore_index=True)
            time.sleep(ACTION_DELAY_SEC)
        except Exception:
            logger.exception(f'Unexpected error with trying to fetch data in url "{url}".', exc_info=True)
        time.sleep(ACTION_DELAY_SEC)
    return df

def get_category_links(browser_options: options.Options, url):
    worker = current_process()
    current_process_id = worker._identity[0]
    category_name = get_id_from_url(url)
    worker.name = f'WORKER#{current_process_id}_{category_name}'
    progress_bar_position = (current_process_id - 1) * 2
    with webdriver.WebDriver(browser_options) as wd:
        time.sleep(ACTION_DELAY_SEC)
        product_details = pd.DataFrame()
        wd.get(f'{url}')
        last_page = wait_for_presence_get(wd, By.CSS_SELECTOR, 'a.responsivePaginationButton.responsivePageSelector.responsivePaginationButton--last')
        if last_page is not None:
            last_page = get_attribute_retry_stale(wd, last_page, 'textContent', {}, By.CSS_SELECTOR, 
                                                  'a.responsivePaginationButton.responsivePageSelector.responsivePaginationButton--last'
                                                  , label='Last Page button')
            if last_page is None:
                logger.warning('Could not find last page button for URL: "%s". Assuming 1 page...', url)
                last_page = 1
            else:
                last_page = int(last_page)
        for page in tqdm(range(1, last_page + 1), colour='red', position= progress_bar_position, desc='Pages scanned', unit='Pages', postfix = {'category': category_name}):
            wd.get(f'{url}?pageNumber={page}')
            product_links = list(set([x.find_element(By.CLASS_NAME, 'productBlock_link').get_attribute('href') for x in wd.find_elements(By.CLASS_NAME, 'productBlock_itemDetails_wrapper')]))
            product_details = pd.concat([product_details, get_product_details(wd, product_links, progress_bar_position)], ignore_index=True)
            time.sleep(ACTION_DELAY_SEC)
        return product_details

def order_serialized_columns(columns: list[str], regex = r'_(\d+)'):
    ordered_columns = []
    groups = {}
    for i, column in enumerate(columns):
        index = re.search(regex, column)
        if index is None or index.group(1) is None:
            ordered_columns.append(column)
            continue
        index = int(index.group(1))
        group_name = re.sub(regex, '', column)
        if group_name not in groups:
            groups[group_name] = {'starting_index': i, 'names': [{'index':index, 'name':column}]}
        else:
            groups[group_name]['names'].append({'index':index, 'name':column})
            if i < groups[group_name]['starting_index']:
                groups[group_name]['starting_index'] = i
    for group in groups.values():
        group['names'] = sorted(group['names'], key=lambda d: d['index'], reverse=True) 

        for name in group['names']:
            ordered_columns.insert(group['starting_index'], name['name'])

    return ordered_columns

def main():
    start_time = time.time()
    df = pd.DataFrame()
    with ProcessPoolExecutor(max_workers=10, initializer=tqdm.set_lock, initargs=(tqdm.get_lock(),)) as executor:
        results = executor.map(get_category_links, [browser_options for _ in CATEGORY_LINKS],CATEGORY_LINKS)
    for result in results:
        df = pd.concat([df, result], ignore_index=True)
    logger.info(f'Total data-frame shape: {df.shape}')
    logger.info('Renaming product_type column...')
    df.rename({'product_type':'variant_type'}, inplace=True)
    logger.info('Reordering columns...')
    df = df.reindex(order_serialized_columns(df.columns), axis=1)
    logger.info("Exporting excel with duplicates...")
    df.to_excel('./test_cult_beauty_with_duplicates.xlsx', index=False)

    logger.info("Removing duplicate entries...")
    df.drop_duplicates(subset='variant_SKU', inplace=True, ignore_index=True)
    logger.info('Total data-frame shape after deduplication: %s', df.shape)
    mask = df['primary_SKU'] == df['variant_SKU']
    transform = df.groupby('primary_SKU')['primary_SKU'].transform(create_serialized_sku, mask)
    logger.info("Serializing primary SKU...")
    df[['serialized_primary_SKU', 'is_variant_of']] = pd.DataFrame(transform.to_list(), columns=['serialized_primary_SKU', 'is_variant_of']
                                                                , index=transform.index)
    logger.info("Cleaning price column...")
    df['price'] = df['price'].transform(lambda x: re.sub(r'[^\d.]', '', x))

    logger.info("Dropping empty columns...")
    df.dropna(axis=1, how='all', inplace=True)
    logger.info("Exporting excel without duplicates...")
    df.to_excel('./test_cult_beauty_without_duplicates.xlsx', index=False)
    logger.info('Total execution time: %s', datetime.timedelta(seconds=time.time() - start_time))

if __name__ == '__main__':
    ACTION_DELAY_SEC = 1
    browser_options = options.Options()
    browser_options.add_argument('-disable-notifications')
    browser_options.add_experimental_option("prefs", {"profile.default_content_setting_values.cookies": 2})
    browser_options.add_argument('-headless')

    color_variation_tags = [x.casefold() for x in ['colour:', 'color:']]
    shade_variation_tags = [x.casefold() for x in ['shade:']]
    size_variation_tags = [x.casefold() for x in ['size:']]
    option_variation_tags = [x.casefold() for x in ['option:']]

    CATEGORY_LINKS = ['https://www.cultbeauty.com/body-wellbeing/tanning-suncare/shop-all.list',
                    'https://www.cultbeauty.com/skin-care.list',
                    'https://www.cultbeauty.com/make-up.list',
                    'https://www.cultbeauty.com/hair-care.list',
                    'https://www.cultbeauty.com/body-wellbeing.list',
                    'https://www.cultbeauty.com/fragrance.list',
                    'https://www.cultbeauty.com/gifts.list',
                    'https://www.cultbeauty.com/minis.list',
                    'https://www.cultbeauty.com/sale.list',
                    'https://www.cultbeauty.com/men.list']
    main()