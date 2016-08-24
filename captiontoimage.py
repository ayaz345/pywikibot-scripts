# -*- coding: utf-8  -*-
import datetime
import pywikibot

from pywikibot import pagegenerators

start = datetime.datetime.now()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

QUERY = "SELECT DISTINCT ?item WHERE { ?item wdt:P2096 [] }"

good_cache = []

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item.get()
    if 'P2096' not in item.claims.keys():
        continue

    our_prop = 'P18'
    if our_prop not inn item.claims.keys():
        our_prop = None
        for prop in item.claims.keys():
            if prop not in good_cache:
                prop_page = pywikibot.PropertyPage(repo, prop)
                if prop_page.type == "commonsMedia":
                    good_cache.append(prop)

            if prop in good_cache:
                if our_prop is not None:
                    our_prop = False
                    break
                else:
                    our_prop = prop

    if our_prop is None:
        pywikibot.output("%s: No media property found" % item.title())
        continue

    if our_prop is False:
        pywikibot.output("%s: More than one media property used" % item.title())
        continue

    remove_claims = []
    media_claim = item.claims[our_prop][0]
    for caption in item.claims['P2096']:
        if 'P2096' not in media_claim.qualifiers.keys():
            target = caption.getTarget()
            has_same_lang = False
            for claim in media_claim.qualifiers['P2096']:
                if claim.getTarget().language == target.language:
                    has_same_lang = True
                    break
            if has_same_lang is True:
                pywikibot.output("%s: %s property already has a caption in language %s" % (item.title(), our_prop, target.language))
                continue

        caption.isQualifier = True
        media_claim.addQualifier(caption)
        remove_claims.append(caption)

    if len(remove_claims) > 0:
        site.removeClaims(remove_claims)

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
