#!/usr/bin/env python
import os
import sys
import requests
import configparser
import re
from bs4 import BeautifulSoup

prefix = "https://sauce.zdv.uni-mainz.de"


class Submission:
    def __init__(self, tr):
        grade = tr.find(class_="col_10").find("span")
        if grade is None:
            self.grade = 0.0
        else:
            self.grade = float(grade.string)
        self.judgement = tr.find(class_="col_9").find("a").string.strip() is "Yes"
        self.judgement_url = prefix + tr.find(class_="col_9").find("a")["href"]
        self.created = tr.find(class_="col_6").string.strip()
        self.mod = tr.find(class_="col_7").string.strip()
        self.language = tr.find(class_="col_5").string.strip()
        self.assignment = tr.find(class_="col_4").find("a").string.strip()
        self.team = tr.find(class_="col_3").string.strip()
        self.user = tr.find(class_="col_2").string.strip()
        self.id = tr.find(class_="col_1").string.strip()
        self.result = tr.find(class_="col_8").find("span").string.strip()
        self.del_url = prefix + tr.find("a", class_="btn btn-danger")["href"]
        self.show_url = prefix + tr.find(class_="col_0").find("a", title="Show")["href"]
        self.root_url = self.show_url[0:-5]


def login_sauce(user, password):
    loginUrl = "https://sauce.zdv.uni-mainz.de/login?came_from=%2F"
    hiddenUrl = "https://sauce.zdv.uni-mainz.de:443/Shibboleth.sso/SAML2/POST"
    reqHeaders = {'Content-Type': 'application/x-www-form-urlencoded',
                  'Connection': 'keep-alive'}
    formData = {'UserName': user + "@UNI-MAINZ",
                'Password': password,
                'Kmsi': "true",
                'AuthMethod': 'FormsAuthentication'}
    hiddenFormData = {"SAMLResponse": ""}
    print("start grabbing...")

    session = requests.Session()
    try:
        r = requests.get(loginUrl)
        rPost = session.post(r.url, headers=reqHeaders, data=formData)
        if (rPost.status_code is not 200):
            raise requests.exceptions.RequestException("login failed! ")

        html = BeautifulSoup(rPost.text, "lxml")
        response = html.find("input")["value"]
        hiddenFormData["SAMLResponse"] = response
        newPost = session.post(hiddenUrl, headers=reqHeaders, data=hiddenFormData)
    except TypeError as typeError:
        print("[ERROR] - Type error occured %s " % typeError)
        sys.exit(1)
    except requests.exceptions.RequestException as exception:
        print("[ERROR] - Exception occured %s " % exception)
        sys.exit(1)
    return session


def read_config(path):
    """connection parameters"""
    config = configparser.ConfigParser()

    try:
        if not config.read(path):
            raise configparser.Error('config file not found')
        user = config.get("LOGIN_DATA", 'UserName')
        password = config.get("LOGIN_DATA", 'password')
        lesson = "Lesson " + config.get("LOGIN_DATA", 'lessonNumber')
        path = config.get("PATHS", "downloadPath")
    except configparser.Error as e:
        print("[ERROR] loginData.cfg file incorrect or doesn't exist! : " + str(e))
        sys.exit(1)

    return user, password, lesson, path


def get_current_events():
    page = requests.get(prefix + "/events")
    html = BeautifulSoup(page.text, "lxml")
    dict = {}
    selection = html.find("h2", string="Current events:").find_next("dl").find_all("a")
    for event in selection:
        dict[event.string] = prefix + event["href"]
    return dict


def get_sheets(event_url):
    page = requests.get(event_url)
    html = BeautifulSoup(page.text, "lxml")
    dict = {}
    selection = html.find("ul", class_="nav  ").find_all("a")[2:]
    for sheet in selection:
        dict[sheet.string] = prefix + sheet["href"]
    return dict


def get_assignments(sheet_url):
    page = requests.get(sheet_url + "/assignments")
    html = BeautifulSoup(page.text, "lxml")
    dict = {}
    selection = html.find("div", class_="page-header").find_next("dl").find_all("a")
    for assignment in selection:
        dict[assignment.string] = prefix + assignment["href"]
    return dict


def get_lessons(assign_url, session):
    page = session.get(assign_url)
    html = BeautifulSoup(page.text, "lxml")
    dict = {}
    selection = html.find("li", class_="nav-header", string="Lessons").parent \
        .find_all("a", href=re.compile("/lessons/"))
    for assignment in selection:
        dict[assignment.string.split(":")[0]] = prefix + assignment["href"]
    return dict


def get_own_submissions_of_assignment(session, assign_url, lesson):
    page = session.get(get_lessons(assign_url, session)[lesson])
    html = BeautifulSoup(page.text, "lxml")
    return get_list_of_submissions(html)


def get_list_of_submissions(html):
    submissions = []
    selection = html.find("tbody").find_all("tr")

    for row in selection:
        submissions.append(Submission(row))
    return submissions


def download_submission(session, submission, path):
    page = session.get(submission.root_url + "/download")
    print("Downloading submission " + submission.id)
    if not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(path, submission.user + submission.id + ".java").replace(" ", "").replace(",", "")
    with open(path, 'w') as f:
        f.write(page.text)


def download_all_submissions_from_sheet(session, event_name, sheet_name, lesson, path):
    print("Downloading submissions from " + event_name + " " + sheet_name)
    event = get_current_events()[event_name]
    sheet = get_sheets(event)[sheet_name]
    for assignment in get_assignments(sheet).items():
        assignment_name = assignment[0]
        assignment_url = assignment[1]
        print("\nDownloading submissions for assignment " + assignment_name)
        submissions = get_own_submissions_of_assignment(session, assignment_url, lesson)
        download_prefix = os.path.join(path, event_name, sheet_name, assignment_name)
        for submission in submissions:
            download_path = os.path.join(download_prefix, submission.team)
            download_path = download_path.replace(" ", "").replace(",", "")
            download_submission(session, submission, download_path)
    print("\nDownload successful")


def get_all_own_submissions(session, event_name, lesson):
    event = get_current_events()[event_name]
    page = session.get(event)
    html = BeautifulSoup(page.text, "lxml")
    lesson_url = html.find("li", string=re.compile(lesson)).find_next("a")["href"]

    page = session.get(prefix + lesson_url + "/submissions")
    html = BeautifulSoup(page.text, "lxml")
    return get_list_of_submissions(html)


def get_dict_of_points(submissions):

    dic = {}
    for submission in submissions:
        dic[submission.team] = dic.setdefault(submission.team, 0.0) + submission.grade

    return dic


def get_scores(session, event_name, lesson):
    return get_dict_of_points(get_all_own_submissions(session, event_name, lesson))


if __name__ == '__main__':
    user, password, lesson, path = read_config("configFile.cfg")

    session = login_sauce(user, password)

    sheet_name = "Blatt 05"
    event_name = "EiP SS 2016"
    # download_all_submissions_from_sheet(session, event_name, sheet_name, lesson, path)
    print(get_scores(session, event_name, lesson))
