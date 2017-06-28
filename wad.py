#!/usr/bin/env python3

import requests as r
from lxml import html
import json
import os
import re
import subprocess as subp
from time import sleep
import argparse
import logging

def dec(node): return re.sub(r'&#([^;]+);', lambda x: chr(int(x.group(1))), node.replace("/", "_"))

def VK_auth(sess, email, password):
  logging.info("Trying to auth...")

  resp = sess.get("https://m.vk.com/login")

  act = html.fromstring(resp.text).xpath("//form/@action")
  if not act:
    logging.error("Login form not found")
    raise SystemExit
  act = act[0]

  resp = sess.post(act, data={"email": email, "pass": password})

  if "login.vk.com/?act=logout_mobile" in sess.get("https://m.vk.com/login").text:
    return sess
  else:
    logging.error("Auth failed")
    raise SystemExit

def download_audio(audio, download_dir):
  if os.access(download_dir, os.W_OK):
    logging.info("Downloading... {} - {}".format(audio["artist"], audio["title"]))
    subp.run([
      "wget",
      "{}".format(audio["url"]),
      "-O",
      "{}/{} :: {}.mp3".format(download_dir, audio["artist"], audio["title"])
    ], stdout=subp.PIPE, stderr=subp.PIPE)
  else:
    logging.error("«{}»: Permission denied".format(download_dir))
    raise SystemExit

def parse_wall_audios(sess, domain, download_dir):
  count = 100
  offset = 0
  timeout = 1
  api_ver = "5.65"

  audios = []

  while True:
    resp = sess.get("https://vk.com/dev/wall.get")

    hash_ = html.fromstring(resp.text).xpath("//button[@id='dev_req_run_btn']/@onclick")
    if not hash_:
      logging.error("Hash not found")
      raise SystemExit
    hash_ = hash_[0].split("Run('")[-1].split("', this")[0]

    req_body = {
      "act": "a_run_method",
      "al": "1",
      "hash": hash_,
      "method": "wall.get",
      "param_count": count,
      "param_domain": domain,
      "param_extended": "0",
      "param_filter": "owner",
      "param_offset": offset,
      "param_v": api_ver
    }
    resp = sess.post("https://vk.com/dev", data=req_body)

    json_resp = json.loads("{\"response\""+resp.text.split("{\"response\"")[-1])

    logging.info("{}/{}".format(offset+count, json_resp["response"]["count"]))

    if not json_resp["response"]["items"]:
      break
    for item in json_resp["response"]["items"]:
      if "attachments" in item:
        for attach in item["attachments"]:
          if attach["type"] == "audio" and attach["audio"]["url"]:
            a = attach["audio"]
            artist = dec(a["artist"])
            title = dec(a["title"])
            url = a["url"]

            if os.path.isfile("{}/{} :: {}.mp3".format(download_dir, artist, title)):
              logging.info("{} - {} already exists".format(artist, title))
            else:
              logging.info("{} - {}, URL: {}".format(artist, title, url))
              audios.append({"artist":artist,"title":title,"url":url})

    offset += count
    sleep(timeout)

  return audios

def parse_post_audios(sess, post_id, download_dir):
  api_ver = "5.65"

  audios = []

  resp = sess.get("https://vk.com/dev/wall.getById")

  hash_ = html.fromstring(resp.text).xpath("//button[@id='dev_req_run_btn']/@onclick")
  if not hash_:
    logging.error("Hash not found")
    raise SystemExit
  hash_ = hash_[0].split("Run('")[-1].split("', this")[0]

  req_body = {
    "act": "a_run_method",
    "al": "1",
    "hash": hash_,
    "method": "wall.getById",
    "param_copy_history_depth": "2",
    "param_extended": "0",
    "param_posts": post_id,
    "param_v": api_ver
  }
  resp = sess.post("https://vk.com/dev", data=req_body)

  json_resp = json.loads("{\"response\""+resp.text.split("{\"response\"")[-1])

  item = json_resp["response"][0]
  if "attachments" in item:
    for attach in item["attachments"]:
      if attach["type"] == "audio" and attach["audio"]["url"]:
        a = attach["audio"]
        artist = dec(a["artist"])
        title = dec(a["title"])
        url = a["url"]
        if os.path.isfile("{}/{} :: {}.mp3".format(download_dir, artist, title)):
          logging.info("{} - {} already exists".format(artist, title))
        else:
          logging.info("{} - {}, URL: {}".format(artist, title, url))
          audios.append({"artist":artist,"title":title,"url":url})

  return audios

def download_wall_audios(sess, domain, download_dir):
  audios = parse_wall_audios(sess, domain, download_dir)
  for audio in audios:
    download_audio(audio, download_dir)

def download_post_audios(sess, post_id, download_dir):
  audios = parse_post_audios(sess, post_id, download_dir)
  for audio in audios:
    download_audio(audio, download_dir)

def main():
  parser = argparse.ArgumentParser(
    description = "vk {community,user} Wall Audios Downloader (with wget)"
  )
  parser.add_argument("-u", "--url", help="vk.com URL", required=True)
  parser.add_argument("-c", "--config", help="path to a config file (default: ./cfg.json)", default="cfg.json")
  parser.add_argument("-a", "--all", action="store_true", help="download audios from all posts on the wall")
  parser.add_argument("-p", "--post", action="store_true", help="download audios from the specified post on the wall")

  args = parser.parse_args()

  logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)

  with open(args.config, "r") as fd:
    cfg = json.loads(fd.read())

  sess = r.Session()
  sess.headers.update({"User-Agent": cfg["UA"]})
  
  if args.all:
    domain = re.findall("^https?:\/\/m?\.?vk\.com\/([a-zA-Z0-9]+)$", args.url)
    if domain:
      sess = VK_auth(sess, cfg["email"], cfg["password"])
      download_wall_audios(sess, domain[0], cfg["download_dir"])
    else:
      logging.error("Incorrect URL")
  elif args.post:
    post_id = re.findall("^https?:\/\/m?\.?vk\.com\/wall(-?[0-9]+_[0-9]+)$", args.url)
    if post_id:
      sess = VK_auth(sess, cfg["email"], cfg["password"])
      download_post_audios(sess, post_id[0], cfg["download_dir"])
    else:
      logging.error("Incorrect URL")
  else:
    parser.print_help()
    raise SystemExit

if __name__ == "__main__":
  main()
