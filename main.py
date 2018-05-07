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
import textwrap

import os,os.path

from struct import *
from collections import namedtuple


plugin = Plugin()
big_list_view = False

labels = {'bbcnews': 'BBC News','bbcparliament': 'BBC Parliament','cbbc':'CBBC','cbeebies':'CBeeBies','bbcone':"BBC One",'bbctwo':'BBC Two', 'bbcthree':'BBC Three', 'bbcfour':'BBC Four'}
tv = ['bbcnews','bbcparliament','cbbc','cbeebies'] #/tv/bbcnews
normal = ['bbcone','bbctwo','bbcfour','bbcthree']


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
    streams = ScrapeAvailableStreams(url)
    stream = streams.get("stream_id_st")
    if stream:
        url = ParseStreams(stream)
        plugin.set_resolved_url(url)


@plugin.route('/play_video/<id>')
def play_video(id):
    url = "https://www.bbc.co.uk/iplayer/episode/%s" % id
    streams = ScrapeAvailableStreams(url)
    stream = streams.get("stream_id_st")
    if stream:
        url = ParseStreams(stream)
        #TODO label
        plugin.play_video({'label':id,'path':url})


@plugin.route('/choose_channels')
def choose_channels():
    channels = plugin.get_storage("channels")
    d = xbmcgui.Dialog()

    normal = ['bbcone','bbctwo','bbcfour','bbcthree']
    tv = ['bbcnews','bbcparliament','cbbc','cbeebies']
    labels = normal + tv

    selected = d.multiselect("Channels",labels)
    if selected:
        channels.clear()
        for i in selected:
            label = labels[i]
            channels[label] = True
    channels.sync()


@plugin.route('/browse_show/<channel>/<show>')
def browse_show(channel,show):
    show_id = show

    url = 'https://www.bbc.co.uk/iplayer/episodes/%s' % show_id

    r = requests.get(url)
    html = r.content
    #with open("episode.html","w") as f:
    #    f.write(html)

    jpg = re.search('https://ichef\.bbci\.co\.uk/images/ic/.*?/(.*?)\.jpg',html)
    if jpg:
        jpg = 'https://ichef.bbci.co.uk/images/ic/raw/%s.jpg' % jpg.group(1)

    episodes = re.findall('href="/iplayer/episode/(.*?)/(.*?)"',html)
    if not episodes:
        return

    show = show_id
    match = re.search('<h1.*?>(.*?)</h1>',html)
    if match:
        show = match.group(1)

    show_description = None
    match = re.search('<p.*?hero-header__subtitle.*?>(.*?)</p>',html)
    if match:
        show_description = match.group(1)

    list__grid__items = html.split('list__grid__item')

    items = []
    num = 1000
    for list__grid__item in list__grid__items[1:]:

        id = None

        match = re.search('/iplayer/episode/(.*?)/(.*?)"',list__grid__item)
        if match:
            id = match.group(1)
            link = match.group(2)
        else:
            continue

        match = re.search('ichef.bbci.co.uk/images/ic/.*?/(.*?).jpg',list__grid__item)
        if match:
            square_jpg = 'https://ichef.bbci.co.uk/images/ic/512x512/%s.jpg' % match.group(1)
            jpg = 'https://ichef.bbci.co.uk/images/ic/512xn/%s.jpg' % match.group(1)

        match = re.search('aria-label="(.*?)"',list__grid__item)
        if match:
            label =  HTMLParser.HTMLParser().unescape(match.group(1))
            title,description = label.split(" Description: ")
        else:
            title = link
            continue #MAYBE

        items.append({
            'label' : title,
            'path' : plugin.url_for('play_video',id=id),
            'thumbnail': jpg
        })
    return sorted(items, key=lambda k: k["label"].lower())


@plugin.route('/browse_channel/<channel>')
def browse_channel(channel):
    subscribed_shows = plugin.get_storage('subscribed_shows')

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


        list_item__programmes = html.split('list-item--programme')
        for list_item__programme in list_item__programmes[1:]:
            match = re.search('/iplayer/episodes/(.*?)"',list_item__programme)
            if match:
                id = match.group(1)
            else:
                continue
            match = re.search('list-item__title.*?>(.*?)<',list_item__programme)
            if match:
                title = match.group(1)
            else:
                continue

            jpg = re.search('https://ichef\.bbci\.co\.uk/images/ic/.*?/(.*?)\.jpg',list_item__programme)
            if jpg:
                jpg = 'https://ichef.bbci.co.uk/images/ic/512xn/%s.jpg' % jpg.group(1)

            shows.add((title,id,jpg))

        try:
            pages = re.findall('href="\?page&#x3D;([0-9]+?)"',html)
            max_page = int(max(pages,key=lambda k: int(k)))
            page += 1
        except:
            break
        #break #DEBUG

    items = []
    for title,id,jpg in shows:
        context_items = []
        context_items.append(("Subscribe", 'XBMC.RunPlugin(%s)' % (plugin.url_for(subscribe_show, show=id))))
        context_items.append(("Unsubscribe", 'XBMC.RunPlugin(%s)' % (plugin.url_for(unsubscribe_show, show=id))))
        items.append({
        'label': HTMLParser.HTMLParser().unescape(title),
        'path': plugin.url_for('browse_show',channel=channel,show=id),
        'thumbnail': jpg,
        'context_menu': context_items,
        })
    return sorted(items, key=lambda k: k["label"].lower())


@plugin.route('/subscribe_show/<show>')
def subscribe_show(show):
    subscribed_shows = plugin.get_storage('subscribed_shows')
    subscribed_shows[show] = show


@plugin.route('/unsubscribe_show/<show>')
def unsubscribe_show(show):
    subscribed_shows = plugin.get_storage('subscribed_shows')
    if show in subscribe_shows:
        del subscribed_shows[show]


@plugin.route('/subscribe_channel/<channel>/<all>')
def subscribe_channel(channel,all=False):
    subscribed_channels = plugin.get_storage('subscribed_channels')
    subscribed_channels[channel] = all


@plugin.route('/unsubscribe_channel/<channel>')
def unsubscribe_channel(channel):
    subscribed_channels = plugin.get_storage('subscribed_channels')
    if channel in subscribed_channels:
        del subscribed_channels[channel]


@plugin.route('/browse_channels')
def browse_channels():
    items = []
    normal = ['bbcone','bbctwo','bbcfour','bbcthree']
    tv = ['bbcnews','bbcparliament','cbbc','cbeebies']
    for channel in normal + tv:
        context_items = []
        context_items.append(("Subscribe All Shows", 'XBMC.RunPlugin(%s)' % (plugin.url_for(subscribe_channel, channel=channel, all=True))))
        context_items.append(("Subscribe", 'XBMC.RunPlugin(%s)' % (plugin.url_for(subscribe_channel, channel=channel, all=False))))
        context_items.append(("Unsubscribe", 'XBMC.RunPlugin(%s)' % (plugin.url_for(unsubscribe_channel, channel=channel))))
        items.append({
        'label': labels[channel],
        'path': plugin.url_for('browse_channel',channel=channel),
        'context_menu': context_items,
        })
    return items


@plugin.route('/bbc')
def bbc():
    subscribed_channels = plugin.get_storage("subscribed_channels")
    subscribed_shows = plugin.get_storage('subscribed_shows')

    servicing = 'special://profile/addon_data/plugin.video.bbc.strms/servicing'
    #if xbmcvfs.exists(servicing):
    #    return
    f = xbmcvfs.File(servicing,'wb')
    f.write('')
    f.close()

    folder = 'special://profile/addon_data/plugin.video.bbc.strms/TV/'
    delete(folder)
    xbmcvfs.mkdirs(folder)


    for channel in normal + tv:
    #for channel in ["cbeebies"]: #DEBUG

        if channel not in subscribed_channels:
            continue
        all_shows = subscribed_channels[channel]

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

            try:
                pages = re.findall('href="\?page&#x3D;([0-9]+?)"',html)
                max_page = int(max(pages,key=lambda k: int(k)))
                page += 1
            except:
                break
            #break #DEBUG

        for show_id in shows:
        #for show_id in ["b08t12cy","b08vp21p","b006m86d","b00dtjbv"]: #DEBUG
            #show_id = "b00dtjbv" #DEBUG

            if all_shows == 'False':
                if show_id not in subscribed_shows:
                    continue

            url = 'https://www.bbc.co.uk/iplayer/episodes/%s' % show_id

            r = requests.get(url)
            html = r.content
            #with open("episode.html","w") as f:
            #    f.write(html)

            jpg = re.search('https://ichef\.bbci\.co\.uk/images/ic/.*?/(.*?)\.jpg',html)
            if jpg:
                jpg = 'https://ichef.bbci.co.uk/images/ic/raw/%s.jpg' % jpg.group(1)

            episodes = re.findall('href="/iplayer/episode/(.*?)/(.*?)"',html)
            if not episodes:
                continue

            show = show_id
            match = re.search('<h1.*?>(.*?)</h1>',html)
            if match:
                show = match.group(1)

            show_folder = channel_folder + show_id + '/'
            xbmcvfs.mkdirs(show_folder)

            show_description = None
            match = re.search('<p.*?hero-header__subtitle.*?>(.*?)</p>',html)
            if match:
                show_description = match.group(1)

            list__grid__items = html.split('list__grid__item')

            num = 1000
            for list__grid__item in list__grid__items[1:]:

                id = None

                match = re.search('/iplayer/episode/(.*?)/(.*?)"',list__grid__item)
                if match:
                    id = match.group(1)
                    link = match.group(2)
                else:
                    continue

                match = re.search('ichef.bbci.co.uk/images/ic/.*?/(.*?).jpg',list__grid__item)
                if match:
                    square_jpg = 'https://ichef.bbci.co.uk/images/ic/512x512/%s.jpg' % match.group(1)
                    jpg = 'https://ichef.bbci.co.uk/images/ic/512xn/%s.jpg' % match.group(1)

                match = re.search('aria-label="(.*?)"',list__grid__item)
                if match:
                    label =  HTMLParser.HTMLParser().unescape(match.group(1))

                    try:
                        title,description = label.split(" Description: ")
                    except:
                        continue

                    season = None
                    episode = None
                    date = None

                    match = re.search('Series ([0-9]+): Episode ([0-9]+)\.',title)
                    if match:
                        season = match.group(1)
                        episode = match.group(2)
                    else:
                        match = re.search('([0-9]{2})/([0-9]{2})/([0-9]{4})\.',title)
                        if match:
                            day = match.group(1)
                            month = match.group(2)
                            year = match.group(3)
                            date = "%s-%s-%s" % (year,month,day)
                        else:
                            match = re.search('([0-9]+)\.',title)
                            if match:
                                episode = match.group(1)
                                season = 1
                            else:
                                episode = num
                                num += 1
                                season = 1000

                    if date:
                        filename = "%s" % (date)
                    else:
                        filename = "S%sE%s" % (season,episode)

                    f = xbmcvfs.File(show_folder+filename+'.strm','w')
                    f.write("plugin://plugin.video.bbc.strms/play/%s" % id)
                    f.close()

                    f = xbmcvfs.File(show_folder+filename+'.nfo','w')
                    if not date:
                        xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
                        <episodedetails>
                        <showtitle>%s</showtitle>
                        <title>%s</title>
                        <season>%s</season>
                        <episode>%s</episode>
                        <plot>%s</plot>
                        <thumb>%s</thumb>
                        </episodedetails>""" % (show,title,season,episode,description,jpg)
                    else:
                        xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
                        <episodedetails>
                        <showtitle>%s</showtitle>
                        <title>%s</title>
                        <aired>%s</aired>
                        <plot>%s</plot>
                        <thumb>%s</thumb>
                        </episodedetails>""" % (show,title,date,description,jpg)
                    xml = textwrap.dedent(xml)
                    f.write(xml.encode("utf8"))
                    f.close()

            if show:
                f = xbmcvfs.File(show_folder+'tvshow.nfo','w')
                xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
                <tvshow>
                <showtitle>%s</showtitle>
                <title>%s</title>
                <plot>%s</plot>
                <thumb>%s</thumb>
                </tvshow>""" % (show,show,show_description,jpg)
                xml = textwrap.dedent(xml)
                f.write(xml.encode("utf8"))
                f.close()

            #break #DEBUG
            #continue #DEBUG


        #break #DEBUG

    xbmc.executebuiltin('UpdateLibrary(video)')
    xbmc.executebuiltin('CleanLibrary(video)')
    #xbmc.executebuiltin('ActivateWindow(10025,library://video/tvshows/titles.xml,return)')
    xbmcvfs.delete(servicing)


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
            dialog = xbmcgui.Dialog()
            #dialog.ok(translation(30400), translation(30401))
            #raise
            dialog.ok("iPlayer","Geo-blocked!")
    #return retlist, match
    return retlist[-1][2]


@plugin.route('/')
def index():
    items = []
    context_items = []

    items.append(
    {
        'label': "Channels",
        'path': plugin.url_for('browse_channels'),
        'thumbnail':get_icon_path('settings'),
        'context_menu': context_items,
    })

    items.append(
    {
        'label': "Service",
        'path': plugin.url_for('service'),
        'thumbnail':get_icon_path('settings'),
        'context_menu': context_items,
    })

    items.append(
    {
        'label': "Subscribed strms",
        'path': 'special://profile/addon_data/plugin.video.bbc.strms/TV/',
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })
    items.append(
    {
        'label': "Library TV Shows",
        'path': 'library://video/tvshows/titles.xml/',
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })
    return items

if __name__ == '__main__':
    plugin.run()
