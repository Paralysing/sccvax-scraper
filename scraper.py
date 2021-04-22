from datetime import datetime
import cfscrape
import random
import time
import traceback
import json

#Replace these placeholders with actual links and proxies

#Format: {'https://schedulecare.sccgov.org/mychartprd/SignupAndSchedule/EmbeddedSchedule...': 'Vaccination Site Nickname'}
vaccination_calendar_sites = {}

#Format: {'http': 'http://username:password@proxyaddress', 'https': 'http://username:password@proxyaddress'} (standard Python requests module format)
proxies = {}

#How long before requests are abandoned (seconds)
timeout = 10

#Used for passing any Cloudflare checks
#Incapsula also seems to be in use, may need to implement something for that in the future
scraper = cfscrape.create_scraper()

def get_appointment_data(site_url):
    available_appointments = {}
    try:
        embedded_schedule = scraper.get(site_url, proxies=proxies, timeout=timeout)
        if embedded_schedule.status_code == 200:
            request_data = { #Preparing for request for data from the API
                'id': str(site_url.split('id=')[1].split('&')[0]),
                'vt': str(site_url.split('vt=')[1].split('&')[0]),
                'dept': str(site_url.split('dept=')[1].split('&')[0]),
                'view': 'grouped',
                'start': '',
                'filters': ''
            }
            request_data['filters'] = json.dumps({
                'Providers': {
                    str(request_data['id']): True,
                },
                'Departments': {
                    str(request_data['dept']): True
                },
                'DaysOfWeek': {
                    '0': True,
                    '1': True,
                    '2': True,
                    '3': True,
                    '4': True,
                    '5': True,
                    '6': True
                },
                'TimesOfDay': 'both'
            })
            token = embedded_schedule.text.split('<input name="__RequestVerificationToken" type="hidden" value="')[1].split('"')[0]
            keep_incrementing_date = True
            current_incremented_date = str(datetime.now()).split(' ')[0]
            while keep_incrementing_date:
                request_data['start'] = current_incremented_date
                headers = { #Browser header emulation
                    'Connection': 'keep-alive',
                    'Accept': '*/*',
                    'X-Requested-With': 'XMLHttpRequest',
                    '__RequestVerificationToken': token,
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Sec-GPC': '1',
                    'Sec-Fetch-Site': 'same-origin',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Dest': 'empty',
                    'Referer': 'https://vax.sccgov.org/',
                    'Host': 'schedulecare.sccgov.org',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
                available_appointment_data = scraper.post('https://schedulecare.sccgov.org/MyChartPRD/OpenScheduling/OpenScheduling/GetOpeningsForProvider?noCache=' + str(random.random()), data=request_data, headers=headers, proxies=proxies, timeout=timeout)
                if available_appointment_data.status_code == 200:
                    available_appointment_data = available_appointment_data.json()
                    if available_appointment_data['ErrorCode']:
                        keep_incrementing_date = False #Stop scraping when the API throws an error (same way as how the site does it)
                    else:
                        current_incremented_date = available_appointment_data['LatestDate']
                    if available_appointment_data['AllDays'] and len(available_appointment_data['AllDays']) > 0:
                        for appointment_loc_id in available_appointment_data['AllDays']:
                            available_appointments[appointment_loc_id] = available_appointment_data['AllDays'][appointment_loc_id]
                else:
                    keep_incrementing_date = False
                    print('Error occurred when fetching available appointment information:')
                    print('Status Code: ' + str(available_appointment_data.status_code))
                    print('Response: ' + available_appointment_data.text)
                    print('')
        else:
            print('Error occurred when fetching the calendar:')
            print('Status Code: ' + str(embedded_schedule.status_code))
            print('Response: ' + embedded_schedule.text)
            print('')
    except Exception as e:
        print('Exception occurred')
        traceback.print_exc()
    return available_appointments

def find_appointments():
    appointments_aggregated = {}
    for site_url in vaccination_calendar_sites:
        appointments_aggregated[site_url] = get_appointment_data(site_url)
    return appointments_aggregated

def are_questions_available():
    available = False
    try:
        headers = { #Browser header emulation
            'Connection': 'keep-alive',
            'Accept': '*/*',
            'X-Requested-With': 'XMLHttpRequest',
            'Sec-GPC': '1',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': 'https://vax.sccgov.org/',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0'
        }
        eligibility_check = scraper.get('https://vax.sccgov.org/Question/FormQuery?_=' + str(int(time.time() * 1000)), headers=headers, proxies=proxies, timeout=timeout)
        if eligibility_check.status_code == 200 and eligibility_check.json()['questions']:
            available = True
    except Exception as e:
        print('Exception occurred')
        traceback.print_exc()
    return available

def is_registration_open():
    open = False
    try:
        main_page = scraper.get('https://vax.sccgov.org/home', proxies=proxies, timeout=timeout, allow_redirects=False)
        if main_page.status_code == 200:
            open = True
    except Exception as e:
        print('Exception occurred')
        traceback.print_exc()
    return open

def print_notification(appointments):
    appointment_exists = False
    for site_url in appointments:
        if len(appointments[site_url]) > 0:
            appointment_count = 0
            latest_appointment_date = 'N/A'
            for appointment_loc_id in appointments[site_url]:
                appointment_count += len(appointments[site_url][appointment_loc_id]['Slots'])
                appointment_date = datetime.strptime(appointments[site_url][appointment_loc_id]['DateISO'], '%Y-%m-%d')
                if latest_appointment_date == 'N/A' or appointment_date > latest_appointment_date:
                    latest_appointment_date = appointment_date
            print('[{}] {}x timeslot(s) available at {} (latest on {})'.format(datetime.now(), appointment_count, vaccination_calendar_sites[site_url], latest_appointment_date.strftime('%Y-%m-%d')))
            appointment_exists = True
    if not appointment_exists:
        print('[{}] No appointments currently available on SCC site'.format(datetime.now()))
    print('')

def main():
    last_registration_status = False
    while True:
        registration_status = is_registration_open()
        if registration_status != 'Error':
            registration_open = is_registration_open()
            questions_available = are_questions_available()
            if registration_open and questions_available:
                print('Registration open')
                if not last_registration_status:
                    appointments = find_appointments()
                    print_notification(appointments)
                    last_registration_status = True
            else:
                print('Registration closed ({}, {})'.format(registration_open, questions_available))
                last_registration_status = False
        time.sleep(30)

if __name__ == '__main__':
    main()
