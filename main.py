from xbmcswift2 import Plugin
import re
import requests
import xbmc,xbmcaddon,xbmcvfs,xbmcgui
import xbmcplugin
import base64
import random
import urllib
import sqlite3
import time,datetime
import threading
import json
import HTMLParser

import os,os.path

from struct import *
from collections import namedtuple


plugin = Plugin()
big_list_view = False



def addon_id():
    return xbmcaddon.Addon().getAddonInfo('id')

def log(v):
    xbmc.log(repr(v),xbmc.LOGERROR)


def get_icon_path(icon_name):
    if plugin.get_setting('user.icons') == "true":
        user_icon = "special://profile/addon_data/%s/icons/%s.png" % (addon_id(),icon_name)
        if xbmcvfs.exists(user_icon):
            return user_icon
    return "special://home/addons/%s/resources/img/%s.png" % (addon_id(),icon_name)

def remove_formatting(label):
    label = re.sub(r"\[/?[BI]\]",'',label)
    label = re.sub(r"\[/?COLOR.*?\]",'',label)
    return label

def escape( str ):
    str = str.replace("&", "&amp;")
    str = str.replace("<", "&lt;")
    str = str.replace(">", "&gt;")
    str = str.replace("\"", "&quot;")
    return str

def unescape( str ):
    str = str.replace("&lt;","<")
    str = str.replace("&gt;",">")
    str = str.replace("&quot;","\"")
    str = str.replace("&amp;","&")
    return str

def delete(path):
    dirs, files = xbmcvfs.listdir(path)
    for file in files:
        xbmcvfs.delete(path+file)
    for dir in dirs:
        delete(path + dir + '/')
    xbmcvfs.rmdir(path)



@plugin.route('/service')
def service():
    threading.Thread(target=bbc).start()



def _handle_paging(result):
    items = result['Items']
    while 'Next' in result['Paging']:
        result = _http_request(result['Paging']['Next'])
        items.extend(result['Items'])
    return items

def _http_request(url):
    try:
        return json.loads(requests.get(url).content)
    except:
        pass


@plugin.route('/play/<id>')
def play(id):
    url = "https://www.bbc.co.uk/iplayer/episode/%s" % id
    #log(url)
    streams = ScrapeAvailableStreams(url)
    #log(streams)
    stream = streams.get("stream_id_st")
    if stream:
        url = ParseStreams(stream)
        plugin.set_resolved_url(url)

@plugin.route('/bbc')
def bbc():
    servicing = 'special://profile/addon_data/plugin.video.bbc.strms/servicing'
    #if xbmcvfs.exists(servicing):
    #    return
    f = xbmcvfs.File(servicing,'wb')
    #f.write('')
    f.close()
    folder = 'special://profile/addon_data/plugin.video.bbc.strms/TV/'
    delete(folder)
    xbmcvfs.mkdirs(folder)

    normal = ['bbcone','bbctwo','bbcfour','bbcthree']
    tv = ['bbcnews','bbcparliament','cbbc','cbeebies']
    for channel in normal + tv:
        channel_folder = folder+channel+'/'
        xbmcvfs.mkdirs(channel_folder)

        shows = set()
        page = 1
        max_page = 1
        while page <= max_page:
            if channel in tv:
                url = 'https://www.bbc.co.uk/tv/%s/a-z?page=%s' % (channel,page)
            else:
                url = 'https://www.bbc.co.uk/%s/a-z?page=%s' % (channel,page)

            r = requests.get(url)
            html = r.content
            #with open("out.html","w") as f:
            #    f.write(html)

            shows = shows | set(re.findall('/iplayer/episodes/(.*?)"',html))
            #log(shows)

            try:
                pages = re.findall('href="\?page&#x3D;([0-9]+?)"',html)
                #log(pages)
                max_page = int(max(pages,key=lambda k: int(k)))
                #log((type(max_page),max_page))
                page += 1
                #log((max_page,page))
            except:
                break
            #break #debug

        for show_id in shows:


            #log(show_id)
            #show_id = "b01psl8r"
            url = 'https://www.bbc.co.uk/iplayer/episodes/%s' % show_id

            r = requests.get(url)
            html = r.content
            #with open("episode.html","w") as f:
            #    f.write(html)

            jpg = re.search('https://ichef\.bbci\.co\.uk/images/ic/.*?/(.*?)\.jpg',html)
            if jpg:
                jpg = 'https://ichef.bbci.co.uk/images/ic/raw/%s.jpg' % jpg.group(1)
            #log(jpg)

            episodes = re.findall('href="/iplayer/episode/(.*?)/(.*?)"',html)
            #log(episodes)
            if not episodes:
                continue
            show = show_id

            match = re.search('<h1.*?>(.*?)</h1>',html)
            if match:
                show = HTMLParser.HTMLParser().unescape(match.group(1))
                show = urllib.quote(show).replace("%20"," ")
            '''
            link = episodes[0][1]
            if "series" in link:
                link = link.replace('-',' ')
                match = re.search('(.*?) series ([0-9]+) ([0-9]+) (.*)',link)
                if match:
                    show = match.group(1).title()
            else:
                link = link.replace('-',' ')
                match = re.search('(.*?) ([0-9]{8})',link)
                if match:
                    show = match.group(1).title()
            '''
            show_folder = channel_folder + show + '/'
            xbmcvfs.mkdirs(show_folder)

            show = None
            for id,link in episodes:
                if "series" in link:
                    link = link.replace('-',' ')
                    match = re.search('(.*?) series ([0-9]+) ([0-9]+) (.*)',link)
                    if match:
                        show = match.group(1).title()
                        season = match.group(2)
                        episode = match.group(3)
                        title = match.group(4).title()
                        #log((show,season,episode,title,link))

                        name = "%s S%sE%s" % (show,season,episode)

                        f = xbmcvfs.File(show_folder+name+'.strm','w')
                        f.write("plugin://plugin.video.bbc.strms/play/%s" % id)
                        f.close()

                        f = xbmcvfs.File(show_folder+name+'.nfo','w')
                        f.write("<episodedetails><showtitle>%s</showtitle><title>%s</title><season>%s</season><episode>%s</episode><thumb>%s</thumb></episodedetails>" % (show,title,season,episode,jpg))
                        f.close()
                else:
                    link = link.replace('-',' ')
                    match = re.search('(.*?) ([0-9]{8})',link)
                    if match:
                        show = match.group(1).title()
                        date = match.group(2)
                        date = "%s-%s-%s" % (date[4:8],date[2:4],date[0:2])
                        #episode = match.group(3)
                        #title = match.group(4).title()
                        #log((show,season,episode,title,link))

                        name = "%s %s" % (show,date)

                        f = xbmcvfs.File(show_folder+name+'.strm','w')
                        f.write("plugin://plugin.video.bbc.strms/play/%s" % id)
                        f.close()

                        f = xbmcvfs.File(show_folder+name+'.nfo','w')
                        f.write("<episodedetails><showtitle>%s</showtitle><title>%s</title><thumb>%s</thumb><aired>%s</aired></episodedetails>" % (show,show,jpg,date))
                        f.close()
                    else:
                        title = link.title()

                        f = xbmcvfs.File(show_folder+title+'.strm','w')
                        f.write("plugin://plugin.video.bbc.strms/play/%s" % id)
                        f.close()

                        f = xbmcvfs.File(show_folder+title+'.nfo','w')
                        f.write("<episodedetails><showtitle>%s</showtitle><title>%s</title><thumb>%s</thumb><aired>%s</aired></episodedetails>" % (show,title,jpg,date))
                        f.close()

            if show:
                f = xbmcvfs.File(show_folder+'tvshow.nfo','w')
                f.write("<tvshow><title>%s</title><thumb>%s</thumb><art><poster>%s</poster><fanart>%s</fanart><thumb>%s</thumb></art></tvshow>" % (show,jpg,jpg,jpg,jpg))
                f.close()



            #break #debug

        break #debug



def ScrapeAvailableStreams(url):
    # Open page and retrieve the stream ID
    html = requests.get(url).content

    name = None
    image = None
    description = None
    stream_id_st = []
    stream_id_sl = []
    stream_id_ad = []

    match = re.search(r'window\.mediatorDefer\=page\(document\.getElementById\(\"tviplayer\"\),(.*?)\);', html, re.DOTALL)
    if match:
        data = match.group(1)
        json_data = json.loads(data)
        # print json.dumps(json_data, indent=2, sort_keys=True)
        if 'title' in json_data['episode']:
            name = json_data['episode']['title']
        if 'synopses' in json_data['episode']:
            synopses = json_data['episode']['synopses']
            if 'large' in synopses:
                description = synopses['large']
            elif 'medium' in synopses:
                description = synopses['medium']
            elif 'small' in synopses:
                description = synopses['small']
            elif 'editorial' in synopses:
                description = synopses['editorial']
        if 'standard' in json_data['episode']['images']:
            image = json_data['episode']['images']['standard'].replace('{recipe}','832x468')
        for stream in json_data['episode']['versions']:
            if ((stream['kind'] == 'original') or
               (stream['kind'] == 'iplayer-version') or
               (stream['kind'] == 'technical-replacement') or
               (stream['kind'] == 'editorial') or
               (stream['kind'] == 'shortened') or
               (stream['kind'] == 'webcast')):
                stream_id_st = stream['id']
            elif (stream['kind'] == 'signed'):
                stream_id_sl = stream['id']
            elif (stream['kind'] == 'audio-described'):
                stream_id_ad = stream['id']
            else:
                print "iPlayer WWW warning: New stream kind: %s" % stream['kind']
                stream_id_st = stream['id']

    return {'stream_id_st': stream_id_st, 'stream_id_sl': stream_id_sl, 'stream_id_ad': stream_id_ad, 'name': name, 'image':image, 'description': description}


def ParseStreams(stream_id):
    retlist = []
    # print "Parsing streams for PID: %s"%stream_id
    # Open the page with the actual strem information and display the various available streams.
    NEW_URL = "https://open.live.bbc.co.uk/mediaselector/5/select/version/2.0/mediaset/iptv-all/vpid/%s" % stream_id
    html = requests.get(NEW_URL).content
    # Parse the different streams and add them as new directory entries.
    match = re.compile(
        'connection authExpires=".+?href="(.+?)".+?supplier="mf_(.+?)".+?transferFormat="(.+?)"'
        ).findall(html)
    source = 1
    for m3u8_url, supplier, transfer_format in match:
        tmp_sup = 0
        tmp_br = 0
        if transfer_format == 'hls':
            if supplier.startswith('akamai') and source in [0,1]:
                tmp_sup = 1
            elif supplier.startswith('limelight') and source in [0,2]:
                tmp_sup = 2
            elif supplier.startswith('bidi') and source in [0,3]:
                tmp_sup = 3
            else:
                continue
            m3u8_breakdown = re.compile('(.+?)iptv.+?m3u8(.+?)$').findall(m3u8_url)
            m3u8_html = requests.get(m3u8_url).content
            m3u8_match = re.compile('BANDWIDTH=(.+?),.+?RESOLUTION=(.+?)(?:,.+?\n|\n)(.+?)\n').findall(m3u8_html)
            for bandwidth, resolution, stream in m3u8_match:
                url = "%s%s%s" % (m3u8_breakdown[0][0], stream, m3u8_breakdown[0][1])
                if 1000000 <= int(bandwidth) <= 1100000:
                    tmp_br = 2
                elif 1790000 <= int(bandwidth) <= 1800000:
                    tmp_br = 4
                elif 3100000 <= int(bandwidth) <= 3120000:
                    tmp_br = 6
                elif int(bandwidth) >= 5500000:
                    tmp_br = 7
                retlist.append((tmp_sup, tmp_br, url, resolution))
    # It may be useful to parse these additional streams as a default as they offer additional bandwidths.
    match = re.compile(
        'kind="video".+?connection href="(.+?)".+?supplier="(.+?)".+?transferFormat="(.+?)"'
        ).findall(html)
    unique = []
    [unique.append(item) for item in match if item not in unique]
    for m3u8_url, supplier, transfer_format in unique:
        tmp_sup = 0
        tmp_br = 0
        if transfer_format == 'hls':
            if supplier.startswith('akamai_hls_open') and source in [0,1]:
                tmp_sup = 1
            elif supplier.startswith('limelight_hls_open') and source in [0,2]:
                tmp_sup = 2
            else:
                continue
            m3u8_breakdown = re.compile('.+?master.m3u8(.+?)$').findall(m3u8_url)
        m3u8_html = requests.get(m3u8_url).content
        m3u8_match = re.compile('BANDWIDTH=(.+?),RESOLUTION=(.+?),.+?\n(.+?)\n').findall(m3u8_html)
        for bandwidth, resolution, stream in m3u8_match:
            url = "%s%s" % (stream, m3u8_breakdown[0][0])
            # This is not entirely correct, displayed bandwidth may be higher or lower than actual bandwidth.
            if int(bandwidth) <= 801000:
                tmp_br = 1
            elif int(bandwidth) <= 1510000:
                tmp_br = 3
            elif int(bandwidth) <= 2410000:
                tmp_br = 5
            retlist.append((tmp_sup, tmp_br, url, resolution))
    # Some events have special live streams which show up as normal programmes.
    # They need to be parsed separately.
    match = re.compile(
        'connection.+?href="(.+?)".+?supplier="(.+?)".+?transferFormat="(.+?)"'
        ).findall(html)
    unique = []
    [unique.append(item) for item in match if item not in unique]
    for m3u8_url, supplier, transfer_format in unique:
        tmp_sup = 0
        tmp_br = 0
        if transfer_format == 'hls':
            if supplier == 'akamai_hls_live':
                tmp_sup = 1
            elif supplier == 'll_hls_live':
                tmp_sup = 2
            else:
                # This is not a live stream, skip code to avoid unnecessary loading of playlists.
                continue
            html = requests.get(m3u8_url).content
            match = re.compile('#EXT-X-STREAM-INF:PROGRAM-ID=(.+?),BANDWIDTH=(.+?),CODECS="(.*?)",RESOLUTION=(.+?)\s*(.+?.m3u8)').findall(html)
            for stream_id, bandwidth, codecs, resolution, url in match:
                # Note: This is not entirely correct as these bandwidths relate to live programmes,
                # not catchup.
                if int(bandwidth) <= 1000000:
                    tmp_br = 1
                elif int(bandwidth) <= 1100000:
                    tmp_br = 2
                elif 1700000 <= int(bandwidth) <= 1900000:
                    tmp_br = 4
                elif 3100000 <= int(bandwidth) <= 3120000:
                    tmp_br = 6
                elif int(bandwidth) >= 5500000:
                    tmp_br = 7
                retlist.append((tmp_sup, tmp_br, url, resolution))
    match = re.compile('service="captions".+?connection href="(.+?)"').findall(html)
    # print "Subtitle URL: %s"%match
    # print retlist
    if not match:
        # print "No streams found"
        check_geo = re.search(
            '<error id="geolocation"/>', html)
        if check_geo:
            # print "Geoblock detected, raising error message"
            #dialog = xbmcgui.Dialog()
            #dialog.ok(translation(30400), translation(30401))
            #raise
            log("NOT UK")
    #return retlist, match
    return retlist[-1][2]


@plugin.route('/')
def index():
    items = []
    context_items = []

    items.append(
    {
        'label': "Make BBC strms in addon_data folder",
        'path': plugin.url_for('bbc'),
        'thumbnail':get_icon_path('settings'),
        'context_menu': context_items,
    })

    return items

if __name__ == '__main__':
    plugin.run()
