import io
import logging.config
import os
import re
import zipfile
from environs import Env

import pandas as pd
import requests

logger = logging.getLogger(__file__)


def get_product_list(last_id, client_id, seller_token):
    """
    Получает список товаров со страницы на Озоне

    Args:
        last_id (str):
            ID последней полученной страницы функции
        client_id (str):
            ID продавца на Озоне
        seller_token (str):
            API-ключ Озона

    Returns:
        dict:
            Словарь с полями 'items' - товары, 'total' - общее количество страниц, 'last_id' - идентификатор страницы

    Raises:
        requests.exceptions.HTTPError: Ozon вернул ошибки 40х или 500
            Ответ доступен в error.response.json() в формате:
            {
                "code": 0, - код ошибки
                "details": [], - дополнительная информация
                "message": - описание ошибки
            }
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        AttributeError: вызов get(), если разобранный ответ оказался не словарём
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> ozon_page = get_product_list(last_id, client_id, seller_token)
        >>> ozon_page['total']
        1
        >>> ozon_page["items"][0]
        {'items': [{'product_id': 3397917680,
                    'offer_id': '2026-01-13 16:56:03 PDF',
                    'sku': 987654321,
                    'has_fbo_stocks': False,
                    'has_fbs_stocks': False,
                    'archived': False,
                    'is_discounted': False,
                    'quants': []}],
         'total': 1,
         'last_id': 'WzMzOTc5MTc2ODAsMzM5NzkxNzY4MF0='}
    """


    url = "https://api-seller.ozon.ru/v3/product/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {
        "filter": {
            "visibility": "ALL",
        },
        "last_id": last_id,
        "limit": 1000,
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    response_object = response.json()
    return response_object.get("result")


def get_offer_ids(client_id, seller_token):
    """
    Получает артикулы всех товаров магазина Озон, собирая данные с каждого вызова get_product_list(),
    пока количество обработанных страниц не сравняется с количеством всех страниц.

    Args:
        last_id (str):
            ID последней полученной страницы функции
        client_id (str):
            ID продавца на Озоне

    Returns:
        list: Артикулы товаров в виде списка строк

    Raises:
        requests.exceptions.HTTPError: Ozon вернул ошибки 40х или 500.
            Ответ доступен в error.response.json() в формате:
            {
                "code": 0, - код ошибки
                "details": [], - дополнительная информация
                "message": - описание ошибки
            }
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        AttributeError: вызов get(), если разобранный ответ оказался не словарём
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> get_offer_ids(client_id, seller_token)
        >>> ['123456', '7891011', '880055535']

    """
    last_id = ""
    product_list = []
    while True:
        some_prod = get_product_list(last_id, client_id, seller_token)
        product_list.extend(some_prod.get("items"))
        total = some_prod.get("total")
        last_id = some_prod.get("last_id")
        if total == len(product_list):
            break
    offer_ids = []
    for product in product_list:
        offer_ids.append(product.get("offer_id"))
    return offer_ids


def update_price(prices: list, client_id, seller_token):
    """
    Отправляет заготовленный список цен на сервер Ozon для обновления цен товаров.

    Args:
        prices (list):
            Список словарей с ценами. Содержит поля:
                "auto_action_enabled": string,
                "auto_add_to_ozon_actions_list_enabled": string,
                "currency_code": string,
                "manage_elastic_boosting_through_price": bool,
                "min_price": string,
                "min_price_for_auto_actions_enabled": bool,
                "net_price": string,
                "offer_id": string,
                "old_price": string,
                "price": string,
                "price_strategy_enabled": string,
                "product_id": int,
                "quant_size": int,
                "vat": string
        client_id (str):
            ID продавца на Озоне
        seller_token (str):
            API-ключ Озона

    Returns:
        dict:
            Полный расшифрованный ответ API

    Raises:
        requests.exceptions.HTTPError: Ozon вернул ошибки 40х или 500.
            Ответ доступен в error.response.json() в формате:
            {
                "code": 0, - код ошибки
                "details": [], - дополнительная информация
                "message": - описание ошибки
            }
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> response = update_price(prices, client_id, seller_token)
        >>> response['result']
        [{'product_id': 121212, 'offer_id': '121212', 'updated': True, 'errors': []}]

    """
    url = "https://api-seller.ozon.ru/v1/product/import/prices"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"prices": prices}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def update_stocks(stocks: list, client_id, seller_token):
    """
    Обновляет остатки запасов товаров на Озоне.

    Args:
        stocks (list):
            Список словарей с остатками товаров. Содержит поля:
                "offer_id": string,
                "product_id": int,
                "stock": int,
                "warehouse_id": int
        client_id (str):
            ID продавца на Озоне
        seller_token (str):
            API-ключ Озона

    Returns:
        dict:
            Полный расшифрованный ответ API

    Raises:
        requests.exceptions.HTTPError: Ozon вернул ошибки 40х или 500.
            Ответ доступен в error.response.json() в формате:
            {
                "code": 0, - код ошибки
                "details": [], - дополнительная информация
                "message": - описание ошибки
            }
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> update_stocks(stocks, client_id, seller_token)
        {'result': [{'warehouse_id': 22142605386000, 'product_id': 118597312, 'offer_id': 'PH11042', 'updated': True, 'errors': []}]}

    """
    url = "https://api-seller.ozon.ru/v1/product/import/stocks"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"stocks": stocks}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def download_stock():
    """
    Скачивает и разбирает файл ostatki с сайта Сasio timeworld.ru, распаковывает, создаёт словарь из xml файла внутри начиная с 18-ой строки
    и возвращает его, после чего удаляет файл.

    Returns:
        list:
        Cписок словарей с содержимым таблицы
    Raises:
        requests.exceptions.HTTPError: Сайт вернул ошибки 40х или 500.
        requests.exceptions.RequestException: сетевая ошибка при скачивании файла
    Example:
        >>> stock = download_stock()
        >>> stock[0]
        {'Код': 75016, 'Наименование товара': 'BA-110AH-4A', 'Изображение': 'Показать', 'Цена': "13'990.00 руб.", 'Количество': '6', 'Заказ': ''}

    """
    # Скачать остатки с сайта
    casio_url = "https://timeworld.ru/upload/files/ostatki.zip"
    session = requests.Session()
    response = session.get(casio_url)
    response.raise_for_status()
    with response, zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(".")
    # Создаем список остатков часов:
    excel_file = "ostatki.xls"
    watch_remnants = pd.read_excel(
        io=excel_file,
        na_values=None,
        keep_default_na=False,
        header=17,
    ).to_dict(orient="records")
    os.remove("./ostatki.xls")  # Удалить файл
    return watch_remnants


def create_stocks(watch_remnants, offer_ids):
    """
    Создаёт список товаров для загрузки в Озон, приводя данные к таковым из Озона.

    Args:
        watch_remnants (list):
            Каталог поставщика, полученный с помощью download_stock()
        offer_ids (list):
            Артикулы товаров магазина
    Returns:
        list:
        Список словарей формата:
            {
                "offer_id": string,
                "stock": int,
            }
    Raises:
        ValueError: некорректный тип данных в поле "Количество"
        AttributeError: в watch_remnants передан не список словарей

    Example:
        >>> create_stocks(watch_remnants, offer_ids)
        [{'offer_id': '121212', 'stock': 100}, {'offer_id': '121212', 'stock': 0}, {'offer_id': '1312132', 'stock': 5}]

    """
    stocks = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            count = str(watch.get("Количество"))
            if count == ">10":
                stock = 100
            elif count == "1":
                stock = 0
            else:
                stock = int(watch.get("Количество"))
            stocks.append({"offer_id": str(watch.get("Код")), "stock": stock})
            offer_ids.remove(str(watch.get("Код")))
    # Добавим недостающее из загруженного:
    for offer_id in offer_ids:
        stocks.append({"offer_id": offer_id, "stock": 0})
    return stocks


def create_prices(watch_remnants, offer_ids):
    """
    Формирует список цен для загрузки на Озон, приводя их к совместимому формату.

    Args:
        watch_remnants (list):
            Каталог поставщика, полученный с помощью download_stock()
        offer_ids (list):
            Артикулы товаров магазина

    Returns:
        list:
            Список словарей с ценами
    Raises:
        AttributeError: в watch_remnants передан не список словарей
        AttributeError: в поле "Цена" лежит не строка

    Example:
        >>> create_prices(watch_remnants, offer_ids)
        [{'auto_action_enabled': 'UNKNOWN', 'currency_code': 'RUB', 'offer_id': '121234', 'old_price': '0', 'price': '13990'}]

    """
    prices = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            price = {
                "auto_action_enabled": "UNKNOWN",
                "currency_code": "RUB",
                "offer_id": str(watch.get("Код")),
                "old_price": "0",
                "price": price_conversion(watch.get("Цена")),
            }
            prices.append(price)
    return prices


def price_conversion(price: str) -> str:
    """
    Преобразовывает цену. Пример: 5'990.00 руб. - 5990

    Args:
        price (str):
            Цена в формате каталога Casio, например - '5'990.00 руб.'

    Returns:
        str:
            Цена в виде строки из чисел - "5990"

    Raises:
        AttributeError: в аргумент была передана не строка

    Example:
        >>> price_conversion("5'990.00 руб.")
        '5990'

    """
    return re.sub("[^0-9]", "", price.split(".")[0])


def divide(lst: list, n: int):
    """
    Делит список lst на части по n элементов

    Args:
        lst (list):
            Изначальный список
        n (int):
            Максимальное количество элементов в одной части

    Returns (YIELD):
        list:
            Часть списка, которая отдаётся по запросу

    Raises:
        ValueError: если n не число или 0


    Example:
        >>> list(divide([12, 13, 44, 22], 2))
        [[12, 13], [44, 22]]
    """

    for i in range(0, len(lst), n):
        yield lst[i : i + n]


async def upload_prices(watch_remnants, client_id, seller_token):
    """
    Получает артикулы товаров, формирует соответствующий список цен и загружает всё на Озон порциями по 1000 единиц.

    Args:
        watch_remnants (list):
            Каталог поставщика, полученный с помощью download_stock()
        client_id (str):
            ID продавца на Озоне
        seller_token (str):
            API-ключ Озона

    Returns:
        list:
        Список отправленных цен.

    Raises:
        requests.exceptions.HTTPError: Сайт вернул ошибки 40х или 500.
        requests.exceptions.RequestException: сетевая ошибка
        AttributeError: в поле "Цена" лежит не строка

    Example:
        >>> prices = upload_prices(watch_remnants, client_id, seller_token)
        >>> prices[0]
        [{'auto_action_enabled': 'UNKNOWN', 'currency_code': 'RUB', 'offer_id': '121234', 'old_price': '0', 'price': '13990'}]

    """
    offer_ids = get_offer_ids(client_id, seller_token)
    prices = create_prices(watch_remnants, offer_ids)
    for some_price in list(divide(prices, 1000)):
        update_price(some_price, client_id, seller_token)
    return prices


async def upload_stocks(watch_remnants, client_id, seller_token):
    """
    Получает артикулы товаров, формирует соответствующий остаток товаров и загружает всё на Озон порциями по 1000 единиц.

    Args:
        Args:
        watch_remnants (list):
            Каталог поставщика, полученный с помощью download_stock()
        offer_ids (list):
            Артикулы товаров магазина
        seller_token (str):
            API-ключ Озона

    Returns:
        tuple:
        Кортеж из двух списков, в первом товары с ненулевым остатком, во втором все товары

    Raises:
        requests.exceptions.HTTPError: Сайт вернул ошибки 40х или 500.
        requests.exceptions.RequestException: сетевая ошибка
        ValueError: некорректный тип данных в поле "Количество"

    Example:
        >>> not_empty, all_stocks = upload_stocks(watch_remnants, client_id, seller_token)
        >>> not_empty[0]
        {'offer_id': '121212', 'stock': 100}
    """
    offer_ids = get_offer_ids(client_id, seller_token)
    stocks = create_stocks(watch_remnants, offer_ids)
    for some_stock in list(divide(stocks, 100)):
        update_stocks(some_stock, client_id, seller_token)
    not_empty = list(filter(lambda stock: (stock.get("stock") != 0), stocks))
    return not_empty, stocks


def main():
    """
    Читает идентификатор и токен продавца в переменной окружения и приводит остаток и цены магазина Озон в
    соответствии с каталогом Casio и, в случае ошибки, выводит её в консоль.

    Example:
        При успешном запуске в консоли нет вывода

    """
    env = Env()
    seller_token = env.str("SELLER_TOKEN")
    client_id = env.str("CLIENT_ID")
    try:
        offer_ids = get_offer_ids(client_id, seller_token)
        watch_remnants = download_stock()
        # Обновить остатки
        stocks = create_stocks(watch_remnants, offer_ids)
        for some_stock in list(divide(stocks, 100)):
            update_stocks(some_stock, client_id, seller_token)
        # Поменять цены
        prices = create_prices(watch_remnants, offer_ids)
        for some_price in list(divide(prices, 900)):
            update_price(some_price, client_id, seller_token)
    except requests.exceptions.ReadTimeout:
        print("Превышено время ожидания...")
    except requests.exceptions.ConnectionError as error:
        print(error, "Ошибка соединения")
    except Exception as error:
        print(error, "ERROR_2")


if __name__ == "__main__":
    main()
