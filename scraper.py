from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from chromedriver_py import binary_path
import os.path, json
import smtplib, ssl
import yaml
import time

from util import Config
import json
import traceback


def store_order(file, order):
        """
        Save order into local json file
        """
        with open(file, 'w') as f:
            json.dump(order, f, indent=4)

def load_order(file):
    """
    Update Json file
    """
    with open(file, "r+") as f:
        return json.load(f)


def load_config(file):
    with open(file) as file:
        return yaml.load(file, Loader=yaml.FullLoader)



config = load_config('config.yml')


def send_notification_telegram(listing):
    coin, list_time = listing
    subject = f'Binance will list {coin} at {list_time} (UTC)'
    body = f'Read more at https://www.binance.com/en/support/announcement/c-48 or do a Google search https://www.google.com/search?q={coin}+token&oq={coin}+token&aqs=chrome.0.0i131i433i512l2j0i512l6j0i131i433i512j0i20i263i512.1732j0j4&sourceid=chrome&ie=UTF-8'
    message = 'Subject: {}\n\n{}'.format(subject, body)
    Config.NOTIFICATION_SERVICE.info(message)

def send_notification(coin):
    port = 465  # For SSL
    smtp_server = "smtp.gmail.com"
    sent_from = config['EMAIL_ADDRESS']
    to = [config['EMAIL_ADDRESS']]
    subject = f'Binance will list {coin}, deposit some funds to be able to short it when listed'
    body = f'Read more at https://www.binance.com/en/support/announcement/c-48 or do a Google search https://www.google.com/search?q={coin}+token&oq={coin}+token&aqs=chrome.0.0i131i433i512l2j0i512l6j0i131i433i512j0i20i263i512.1732j0j4&sourceid=chrome&ie=UTF-8'
    message = 'Subject: {}\n\n{}'.format(subject, body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sent_from, config['EMAIL_PASSWORD'])
            server.sendmail(sent_from, to, message)

    except Exception as e:
        print(e)




chrome_options = Options()
chrome_options.add_argument("--headless")
driver = webdriver.Chrome(executable_path=binary_path, options=chrome_options)

def get_listing_time(link_id):
    #return "2021-11-18 14:08" # hardcode
    el = driver.find_element(By.ID, link_id)
    el.click()
    x = str(driver.page_source)#.replace("2021-10-11 06:00", "2021-10-19 14:03")
    will_list_i = x.find("will list")
    if will_list_i == -1:
        will_list_i = x.find("will then list")
    if will_list_i == -1:
        return None
    x = x[will_list_i:]
    utc_i = x.find(" (UTC)")
    if utc_i == -1:
        return None
    x = x[:utc_i]
    listing_time = x[-19:].replace(" AM", "").replace(" PM", "").replace("at ", "")
    print("DEBUG PARSING LISTING TIME:", listing_time)
    try:
        time.mktime(time.strptime(listing_time, "%Y-%m-%d %H:%M"))
    except:
        return None
    return listing_time

def get_last_coin(link_id):
    """
    Scrapes new listings page for and returns new Symbol when appropriate
    """
    driver.get("https://www.binance.com/en/support/announcement/c-48")
    latest_announcement = driver.find_element(By.ID, link_id)
    latest_announcement = latest_announcement.text+"."
    print(latest_announcement)

    # Binance makes several annoucements, irrevelant ones will be ignored
    #exclusions = ['Futures', 'Margin', 'adds', 'Subscription']
    exclusions = ['Futures', 'Margin', 'adds']
    for item in exclusions:
        if item.lower() in latest_announcement.lower():
            return None, None
    if ('(' not in latest_announcement) or (')' not in latest_announcement):
        return None, None
    list_time = get_listing_time(link_id)
    if list_time is None:
        return None, None
    #enum = [item for item in enumerate(latest_announcement)]
    #uppers = ''.join(item[1] for item in enum if item[1].isupper() and (enum[enum.index(item)+1][1].isupper() or enum[enum.index(item)+1][1]==')') )

    op = latest_announcement.find('(')
    cp = latest_announcement.find(')')
    uppers = latest_announcement[op+1:cp]
    #return "ANKR", list_time # hardcode

    return uppers, list_time


def store_new_listing(listing):
    """
    Only store a new listing if different from existing value
    """
    coin, list_time = listing
    if os.path.isfile('new_listing.json'):
        file = load_order('new_listing.json')
        if coin in file:
            print("No new listings detected...")
            return False
        else:
            file = store_order('new_listing.json', listing)
            send_notification_telegram(listing)
            return True
    else:
        send_notification_telegram(listing)
        return True


def search_and_update():
    max_time = "2030-12-12 11:11"
    latest_coin, list_time = None, max_time
    this_coin, list_time_ = None, max_time
    for i in range(6): #from 0 to 2
        try:
            this_coin, list_time_ = get_last_coin('link-0-%d-p1'%i)
            list_time__ts = time.mktime(time.strptime(list_time_, "%Y-%m-%d %H:%M"))
        except Exception as e:
            print("SCRAPE ERROR")
            print(traceback.format_exc())
            continue
        Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("DETECTED [%s] at [%s] (UTC)"%(this_coin, list_time_))
        if (time.time() < list_time__ts < time.mktime(time.strptime(list_time, "%Y-%m-%d %H:%M"))) and (this_coin is not None):
            list_time = list_time_
            latest_coin = this_coin
        else:
            Config.NOTIFICATION_SERVICE.get_service('VERBOSE_FILE').error("But it's None or in the past.")
    if latest_coin is not None:
        if not store_new_listing((latest_coin, list_time)):
            return None, None
    else:
        return None, None
    return latest_coin, list_time
