import datetime
import logging.config
from environs import Env
from seller import download_stock

import requests

from seller import divide, price_conversion

logger = logging.getLogger(__file__)

#НЕКОТОРЫЕ ЗАПРОСЫ МЕРТВЫ, ПОЛУЧИТЬ ИНФОРМАЦИЮ О ПРОШЛОМ ТЕЛЕ ОТВЕТА НЕ ПОЛУЧИЛОСЬ.
#ВЕСЬ ВЫВОД С ТЕКУЩЕГО СОСТОЯНИЯ АПИ ЯНДЕКСА C ДРУГИХ КОМАНД

def get_product_list(page, campaign_id, access_token):
    """
    Получает список товаров со страницы Яндекса

    Args:
        page (str):
            Id страницы
        campaign_id (str):
            Идентификатор магазина в Яндексе
        access_token (str):
            API-ключ Яндекса

    Returns:
        dict:
            Словарь с полями 'offers' - товары, 'paging'- словарь с id следующей страницы

    Raises:
        requests.exceptions.HTTPError: Яндекс вернул ошибки 40х или 500
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        AttributeError: вызов get(), если разобранный ответ оказался не словарём
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> market_page = get_product_list(page, campaign_id, access_token)
        >>> market_page['offers'][0]
        {'offerId': 'example', 'available': True, 'basicPrice': {}, 'campaignPrice': {}, 'status': 'PUBLISHED', 'errors': [None], 'warnings': [None]}
    """
    endpoint_url = "https://api.partner.market.yandex.ru/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Host": "api.partner.market.yandex.ru",
    }
    payload = {
        "page_token": page,
        "limit": 200,
    }
    url = endpoint_url + f"campaigns/{campaign_id}/offer-mapping-entries"
    response = requests.get(url, headers=headers, params=payload)
    response.raise_for_status()
    response_object = response.json()
    return response_object.get("result")


def update_stocks(stocks, campaign_id, access_token):
    """
    Обновляет остатки запасов товаров на Яндексе.

    Args:
        stocks (list):
            Список словарей с остатками товаров. Содержит поля:
                "sku": string,
                "warehouseId": int,
                "items": []
        campaign_id (str):
            Идентификатор магазина в Яндексе
        access_token (str):
            API-ключ Яндекса

    Returns:
        dict:
            Полный расшифрованный ответ API

    Raises:
        requests.exceptions.HTTPError: Яндекс вернул ошибки 40х или 500
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> update_stocks(stocks, campaign_id, access_token)
        {'status': 'OK'}
    """
    endpoint_url = "https://api.partner.market.yandex.ru/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Host": "api.partner.market.yandex.ru",
    }
    payload = {"skus": stocks}
    url = endpoint_url + f"campaigns/{campaign_id}/offers/stocks"
    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    response_object = response.json()
    return response_object


def update_price(prices, campaign_id, access_token):
    """
    Отправляет заготовленный список цен на сервер Яндекса для обновления цен товаров.

    Args:
        prices (list):
            Список словарей с ценами. Содержит поля:
                "id": string,
                "price": {
                    "value": int,
                    "currencyId": string
                }
        campaign_id (str):
            Идентификатор магазина в Яндексе
        access_token (str):
            API-ключ Яндекса

    Returns:
        dict:
            Полный расшифрованный ответ API

    Raises:
        requests.exceptions.HTTPError: Яндекс вернул ошибки 40х или 500
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> update_price(prices, campaign_id, access_token)
        {'status': 'OK'}
    """
    endpoint_url = "https://api.partner.market.yandex.ru/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Host": "api.partner.market.yandex.ru",
    }
    payload = {"offers": prices}
    url = endpoint_url + f"campaigns/{campaign_id}/offer-prices/updates"
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    response_object = response.json()
    return response_object


def get_offer_ids(campaign_id, market_token):
    """
    Получает артикулы товаров Яндекса, собирая данные с каждого вызова get_product_list(),
    пока в ответе не пропадёт id следующей страницы

    Args:
        campaign_id (str):
            Идентификатор магазина в Яндексе
        market_token (str):
            API-ключ Яндекса

    Returns:
        list: Артикулы товаров в виде списка строк

    Raises:
        requests.exceptions.HTTPError: Яндекс вернул ошибки 40х или 500
        requests.exceptions.JSONDecodeError: ошибка преобразования в json
        AttributeError: вызов get(), если разобранный ответ оказался не словарём
        requests.exceptions.RequestException: сетевая ошибка при выполнение запросов

    Example:
        >>> get_offer_ids(campaign_id, market_token)
        ['123456', '7891011', '880055535']
    """
    page = ""
    product_list = []
    while True:
        some_prod = get_product_list(page, campaign_id, market_token)
        product_list.extend(some_prod.get("offerMappingEntries"))
        page = some_prod.get("paging").get("nextPageToken")
        if not page:
            break
    offer_ids = []
    for product in product_list:
        offer_ids.append(product.get("offer").get("shopSku"))
    return offer_ids


def create_stocks(watch_remnants, offer_ids, warehouse_id):
    """
    Создаёт список товаров для загрузки в Яндекс, приводя данные к таковым из Яндекса.

    Args:
        watch_remnants (list):
            Каталог поставщика, полученный с помощью download_stock()
        offer_ids (list):
            Артикулы товаров магазина
        warehouse_id (str):
            Идентификатор фулфилмент-склада в Яндексе

    Returns:
        list:
        Список словарей формата:
            {
                "sku": string,
                "warehouseId": int,
                "items": [
                    {
                        "count": int,
                        "type": string,
                        "updatedAt": string
                    }
                ]
            }

    Raises:
        ValueError: некорректный тип данных в поле "Количество"
        AttributeError: в watch_remnants передан не список словарей

    Example:
        >>> create_stocks(watch_remnants, offer_ids, warehouse_id)
        [{'sku': '121212', 'warehouseId': '1232324242', 'items': [{'count': 100, 'type': 'FIT', 'updatedAt': '2026-09-01T14:30:00Z'}]}]
    """
    stocks = list()
    date = str(datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z")
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            count = str(watch.get("Количество"))
            if count == ">10":
                stock = 100
            elif count == "1":
                stock = 0
            else:
                stock = int(watch.get("Количество"))
            stocks.append(
                {
                    "sku": str(watch.get("Код")),
                    "warehouseId": warehouse_id,
                    "items": [
                        {
                            "count": stock,
                            "type": "FIT",
                            "updatedAt": date,
                        }
                    ],
                }
            )
            offer_ids.remove(str(watch.get("Код")))
    # Добавим недостающее из загруженного:
    for offer_id in offer_ids:
        stocks.append(
            {
                "sku": offer_id,
                "warehouseId": warehouse_id,
                "items": [
                    {
                        "count": 0,
                        "type": "FIT",
                        "updatedAt": date,
                    }
                ],
            }
        )
    return stocks


def create_prices(watch_remnants, offer_ids):
    """
    Формирует список цен для загрузки на Яндекс, приводя их к совместимому формату

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
        [{'id': '121212', 'price': {'value': 1212121, 'currencyId': 'RUR'}}]
    """
    prices = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            price = {
                "id": str(watch.get("Код")),
                # "feed": {"id": 0},
                "price": {
                    "value": int(price_conversion(watch.get("Цена"))),
                    # "discountBase": 0,
                    "currencyId": "RUR",
                    # "vat": 0,
                },
                # "marketSku": 0,
                # "shopSku": "string",
            }
            prices.append(price)
    return prices


async def upload_prices(watch_remnants, campaign_id, market_token):
    """
    Получает артикулы товаров, формирует соответствующий список цен и загружает всё на Яндекс порциями по 500 единиц.

    Args:
        watch_remnants (list):
            Прайс-лист поставщика, полученный с помощью download_stock()
        campaign_id (str):
            Идентификатор магазина в Яндекс Маркете
        market_token (str):
            API-ключ Яндекс Маркета

    Returns:
        list:
        Список отправленных цен.

    Raises:
        requests.exceptions.HTTPError: Сайт вернул ошибки 40х или 500
        requests.exceptions.RequestException: сетевая ошибка
        AttributeError: в поле "Цена" лежит не строка

    Example:
        >>> prices = upload_prices(watch_remnants, campaign_id, market_token)
        >>> prices[0]
        {'id': '234234', 'price': {'value': 88005553535, 'currencyId': 'RUR'}}
    """
    offer_ids = get_offer_ids(campaign_id, market_token)
    prices = create_prices(watch_remnants, offer_ids)
    for some_prices in list(divide(prices, 500)):
        update_price(some_prices, campaign_id, market_token)
    return prices


async def upload_stocks(watch_remnants, campaign_id, market_token, warehouse_id):
    """
    Получает артикулы товаров, формирует соответствующий остаток товаров и загружает всё на Яндекс Маркет порциями по 2000 единиц.

    Args:
        watch_remnants (list):
            Каталог поставщика, полученный с помощью download_stock()
        campaign_id (str):
            Идентификатор магазина в Яндексе
        market_token (str):
            API-ключ Яндекс Маркета
        warehouse_id (str):
            Идентификатор фулфилмент-склада в Яндексе

    Returns:
        tuple:
        Кортеж из двух списков, в первом товары с ненулевым остатком, во втором все товары

    Raises:
        requests.exceptions.HTTPError: Сайт вернул ошибки 40х или 500
        requests.exceptions.RequestException: сетевая ошибка
        ValueError: некорректный тип данных в поле "Количество"

    Example:
        >>> not_empty, all_stocks = upload_stocks(watch_remnants, campaign_id, market_token, warehouse_id)
        >>> not_empty[0]
        {'sku': '23232323', 'warehouseId': '132324234', 'items': [{'count': 100, 'type': 'FIT', 'updatedAt': '2026-09-01T14:30:00Z'}]}
    """
    offer_ids = get_offer_ids(campaign_id, market_token)
    stocks = create_stocks(watch_remnants, offer_ids, warehouse_id)
    for some_stock in list(divide(stocks, 2000)):
        update_stocks(some_stock, campaign_id, market_token)
    not_empty = list(
        filter(lambda stock: (stock.get("items")[0].get("count") != 0), stocks)
    )
    return not_empty, stocks


def main():
    """
    Читает токен, идентификаторы магазинов и фулфилмент-складов в переменной окружения и приводит остаток и цены
    магазинов FBS и DBS Яндекс Маркета в соответствии с каталогом Casio и, в случае ошибки, выводит её в консоль.

    Example:
        При успешном запуске в консоли нет вывода
    """
    env = Env()
    market_token = env.str("MARKET_TOKEN")
    campaign_fbs_id = env.str("FBS_ID")
    campaign_dbs_id = env.str("DBS_ID")
    warehouse_fbs_id = env.str("WAREHOUSE_FBS_ID")
    warehouse_dbs_id = env.str("WAREHOUSE_DBS_ID")

    watch_remnants = download_stock()
    try:
        # FBS
        offer_ids = get_offer_ids(campaign_fbs_id, market_token)
        # Обновить остатки FBS
        stocks = create_stocks(watch_remnants, offer_ids, warehouse_fbs_id)
        for some_stock in list(divide(stocks, 2000)):
            update_stocks(some_stock, campaign_fbs_id, market_token)
        # Поменять цены FBS
        upload_prices(watch_remnants, campaign_fbs_id, market_token)

        # DBS
        offer_ids = get_offer_ids(campaign_dbs_id, market_token)
        # Обновить остатки DBS
        stocks = create_stocks(watch_remnants, offer_ids, warehouse_dbs_id)
        for some_stock in list(divide(stocks, 2000)):
            update_stocks(some_stock, campaign_dbs_id, market_token)
        # Поменять цены DBS
        upload_prices(watch_remnants, campaign_dbs_id, market_token)
    except requests.exceptions.ReadTimeout:
        print("Превышено время ожидания...")
    except requests.exceptions.ConnectionError as error:
        print(error, "Ошибка соединения")
    except Exception as error:
        print(error, "ERROR_2")


if __name__ == "__main__":
    main()
