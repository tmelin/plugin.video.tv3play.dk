#
#      Copyright (C) 2012 Tommy Winther
#      http://tommy.winther.nu
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this Program; see the file LICENSE.txt.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#
from xml.etree import ElementTree
import os
import sys
import urlparse
import urllib2
import re

import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

import buggalo

REGIONS = ['tv3play.dk', 'tv3play.se', 'tv3play.no', 'tv3play.lt', 'tv3play.lv', 'tv3play.ee']

class TV3PlayException(Exception):
    pass

class TV3PlayAddon(object):
    def listPrograms(self):
        html = self.downloadUrl(self.getBaseUrl() + '/program')
        items = list()
        for m in re.finditer('<a href="/program/([^"]+)">([^<]+)</a>', html):
            slug = m.group(1)
            title = m.group(2)
            fanart = self.downloadAndCacheFanart(slug, None)

            item = xbmcgui.ListItem(title, iconImage=ICON)
            if fanart:
                item.setIconImage(fanart)
                item.setProperty('Fanart_Image', fanart)
            items.append((PATH + '?program=%s' % slug, item, True))

        xbmcplugin.addDirectoryItems(HANDLE, items)
        xbmcplugin.endOfDirectory(HANDLE)

    def listSeasons(self, slug):
        html = self.downloadUrl(self.getBaseUrl() + '/program/%s' % slug)
        fanart = self.downloadAndCacheFanart(slug, html)

        seasons = list()
        for m in re.finditer('<strong>(.*?[0-9]+.*?)</strong>', html):
            season = m.group(1)

            if not seasons.count(season):
                seasons.append(season)

        items = list()
        seasons.sort()
        for season in seasons:
            item = xbmcgui.ListItem(season, iconImage = ICON)
            if fanart:
                item.setIconImage(fanart)
                item.setProperty('Fanart_Image', fanart)
            items.append((PATH + '?program=%s&season=%s' % (slug, season), item, True))

        xbmcplugin.addDirectoryItems(HANDLE, items)
        xbmcplugin.endOfDirectory(HANDLE)


    def listVideos(self, slug, season):
        html = self.downloadUrl(self.getBaseUrl() + '/program/%s' % slug)
        fanart = self.downloadAndCacheFanart(slug, html)

        m = re.search(season + '</strong>(.*?)<strong>', html, re.DOTALL)
        snip = m.group(1)

        items = list()
        for m in re.finditer('<a href="/play/([0-9]+)/" >([^<]+)<.*?col2">([^<]+)<.*?col3">([^<]+)<.*?col4">([^<]+)<', snip, re.DOTALL):
            videoId = m.group(1)
            title = m.group(2)
            episode = m.group(3)
            duration = m.group(4)
            airDate = m.group(5)

            aired = '20%s-%s-%s' % (airDate[6:8], airDate[3:5], airDate[0:2])

            item = xbmcgui.ListItem('%s (%s)' % (title, episode), iconImage = ICON)
            item.setInfo('video', {
                'studio' : ADDON.getAddonInfo('name'),
                'duration' : duration,
                'episode' : int(episode),
                'aired' : aired
            })
            item.setProperty('IsPlayable', 'true')
            if fanart:
                item.setIconImage(fanart)
                item.setProperty('Fanart_Image', fanart)
            items.append((PATH + '?playVideo=%s' % videoId, item))

        items.reverse()
        xbmcplugin.addDirectoryItems(HANDLE, items)
        xbmcplugin.endOfDirectory(HANDLE)

    def playVideo(self, videoId):
        doc = self.getPlayProductXml(videoId)
        rtmpUrl = self.getRtmpUrl(doc.findtext('Product/Videos/Video/Url')) + ' swfUrl=http://flvplayer.viastream.viasat.tv/play/swf/player111227.swf swfVfy=true'

        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()

        # Preroll
        url = doc.find('Product/AdCalls/preroll').get('url')
        node = self.getXml(url).find('Ad')
        if node is not None:
            flvUrl = node.findtext('InLine/Creatives/Creative/Linear/MediaFiles/MediaFile')
            item = xbmcgui.ListItem(ADDON.getLocalizedString(100), iconImage = ICON)
            playlist.add(flvUrl, item)
            print 'ad %s' % flvUrl

        adNodes = None
        start = 0
        for idx, node in enumerate(doc.findall('Product/AdCalls/midroll')):
            if adNodes is None:
                adXml = self.downloadUrl(node.get('url'))
                adDoc = ElementTree.fromstring(adXml)
                adNodes = adDoc.findall('Ad')

            print 'time %s' % node.get('time')
            stop = int(node.get('time'))
            itemUrl = rtmpUrl + ' start=%d stop=%d' % (start * 1000, stop * 1000)
            featureItem = xbmcgui.ListItem(doc.findtext('Product/Title'), thumbnailImage=doc.findtext('Product/Images/ImageMedia/Url'), path = itemUrl)
            playlist.add(itemUrl, featureItem)
            print 'video %s -> %s' % (start, stop)
            start = stop

            if len(adNodes) > idx:
                item = xbmcgui.ListItem(ADDON.getLocalizedString(100), iconImage = ICON)
                playlist.add(adNodes[idx].findtext('InLine/Creatives/Creative/Linear/MediaFiles/MediaFile'), item)
                print 'ad %s' % adNodes[idx].findtext('InLine/Creatives/Creative/Linear/MediaFiles/MediaFile')

        itemUrl = rtmpUrl + ' start=%d' % (start * 1000)
        featureItem = xbmcgui.ListItem(doc.findtext('Product/Title'), thumbnailImage=doc.findtext('Product/Images/ImageMedia/Url'), path = itemUrl)
        playlist.add(itemUrl, featureItem)
        print 'video %s -> end' % start

        # Postroll
        url = doc.find('Product/AdCalls/postroll').get('url')
        node = self.getXml(url).find('Ad')
        if node is not None:
            flvUrl = node.findtext('InLine/Creatives/Creative/Linear/MediaFiles/MediaFile')
            item = xbmcgui.ListItem(ADDON.getLocalizedString(100), iconImage = ICON)
            playlist.add(flvUrl, item)
            print 'ad %s' % flvUrl

        xbmcplugin.setResolvedUrl(HANDLE, True, playlist[0])

    def getPlayProductXml(self, videoId):
        xml = self.downloadUrl('http://viastream.viasat.tv/PlayProduct/%s' % videoId)
        return ElementTree.fromstring(xml)

    def getRtmpUrl(self, videoUrl):
        if videoUrl[0:4] == 'rtmp':
            return videoUrl

        xml = self.downloadUrl(videoUrl)
        doc = ElementTree.fromstring(xml)

        if doc.findtext('Success') == 'true':
            return doc.findtext('Url')
        else:
            raise TV3PlayException(doc.findtext('Msg'))

    def getXml(self, url):
        xml = self.downloadUrl(url)
        return ElementTree.fromstring(xml)

    def downloadAndCacheFanart(self, slug, html):
        fanartPath = os.path.join(CACHE_PATH, '%s.jpg' % slug.encode('iso-8859-1', 'replace'))
        if not os.path.exists(fanartPath) and html:
            m = re.search('/play/([0-9]+)/', html)
            xml = self.getPlayProductXml(m.group(1))

            fanartUrl = None
            for node in xml.findall('Product/Images/ImageMedia'):
                if node.findtext('Usage') == 'PlayImage':
                    fanartUrl = node.findtext('Url')
                    break

            if fanartUrl:
                imageData = self.downloadUrl(fanartUrl.replace(' ', '%20'))
                if imageData:
                    f = open(fanartPath, 'wb')
                    f.write(imageData)
                    f.close()

                    return fanartPath

        elif os.path.exists(fanartPath):
            return fanartPath

        return None

    def getBaseUrl(self):
        if ADDON.getSetting('region.url') == '':
            idx = xbmcgui.Dialog().select(ADDON.getLocalizedString(150), REGIONS)
            ADDON.setSetting('region.url', REGIONS[idx])

        return 'http://www.%s' % ADDON.getSetting('region.url')

    def downloadUrl(self, url):
        print "_downloader: %s" % url.encode('iso-8859-1', 'replace')
        for retries in range(0, 5):
            try:
                r = urllib2.Request(url.encode('iso-8859-1', 'replace'))
                r.add_header('User-Agent', 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:10.0.2) Gecko/20100101 Firefox/10.0.2')
                u = urllib2.urlopen(r, timeout = 30)
                contents = u.read()
                u.close()
                return contents
            except urllib2.URLError:
                return None
            except Exception, ex:
                print 'Retrying... %s' % str(ex)
                if retries > 5:
                    raise TV3PlayException(ex)


    def displayError(self, message = 'n/a'):
        heading = buggalo.getRandomHeading()
        line1 = ADDON.getLocalizedString(200)
        line2 = ADDON.getLocalizedString(201)
        xbmcgui.Dialog().ok(heading, line1, line2, message)

if __name__ == '__main__':
    ADDON = xbmcaddon.Addon()
    PATH = sys.argv[0]
    HANDLE = int(sys.argv[1])
    PARAMS = urlparse.parse_qs(sys.argv[2][1:])

    ICON = os.path.join(ADDON.getAddonInfo('path'), 'icon.png')

    CACHE_PATH = xbmc.translatePath(ADDON.getAddonInfo("Profile"))
    if not os.path.exists(CACHE_PATH):
        os.makedirs(CACHE_PATH)

    buggalo.SUBMIT_URL = 'http://tommy.winther.nu/exception/submit.php'
    tv3PlayAddon = TV3PlayAddon()
    try:
        if PARAMS.has_key('playVideo'):
            tv3PlayAddon.playVideo(PARAMS['playVideo'][0])
        elif PARAMS.has_key('program') and PARAMS.has_key('season'):
            tv3PlayAddon.listVideos(PARAMS['program'][0], PARAMS['season'][0])
        elif PARAMS.has_key('program'):
            tv3PlayAddon.listSeasons(PARAMS['program'][0])

        else:
            tv3PlayAddon.listPrograms()

    except TV3PlayException, ex:
        tv3PlayAddon.displayError(str(ex))

    except Exception:
        buggalo.onExceptionRaised()

