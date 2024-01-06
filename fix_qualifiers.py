#!/usr/bin/python
"""This script is obsolete!"""
import pywikibot

from pywikibot import pagegenerators

from query_store import QueryStore
from wikidata import WikidataEntityBot


class QualifiersFixingBot(WikidataEntityBot):

    blacklist = frozenset(['P143', 'P248', 'P459', 'P518', 'P577', 'P805',
                           'P972', 'P1065', 'P1135', 'P1480', 'P1545', 'P1932',
                           'P2315', 'P2701', 'P3274', ])
    whitelist = frozenset(['P17', 'P21', 'P39', 'P155', 'P156', 'P281', 'P580',
                           'P582', 'P585', 'P669', 'P708', 'P969', 'P1355',
                           'P1356', ])
    good_item = 'Q15720608'
    use_from_page = False

    def __init__(self, **kwargs):
        kwargs.update({
            'bad_cache': kwargs.get('bad_cache', []) + list(self.blacklist),
            'good_cache': kwargs.get('good_cache', []) + list(self.whitelist),
        })
        super().__init__(**kwargs)
        self.store = QueryStore()

    def filterProperty(self, prop_page):
        if prop_page.type == 'external-id':
            return False

        prop_page.get()
        if 'P31' not in prop_page.claims:
            pywikibot.warning(f'{prop_page.getID()} is not classified')
            return False

        return any(
            claim.target_equals(self.good_item)
            for claim in prop_page.claims['P31']
        )

    @property
    def generator(self):
        query = self.store.build_query(
            'qualifiers', item=self.good_item,
            good=', wd:'.join(self.whitelist),
            bad=', wd:'.join(self.blacklist))
        return pagegenerators.PreloadingItemGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo))

    def treat_page_and_item(self, page, item):
        for prop in item.claims.keys():
            for claim in item.claims[prop]:
                moved = set()
                json = claim.toJSON()
                i = -1
                for source in claim.sources:
                    i += 1
                    for ref_prop in filter(self.checkProperty, source.keys()):
                        for snak in source[ref_prop]:
                            json.setdefault('qualifiers', {}).setdefault(ref_prop, [])
                            for qual in (pywikibot.Claim.qualifierFromJSON(self.repo, q)
                                         for q in json['qualifiers'][ref_prop]):
                                if qual.target_equals(snak.getTarget()):
                                    break
                            else:
                                snak.isReference = False
                                snak.isQualifier = True
                                json['qualifiers'][ref_prop].append(snak.toJSON())
                            json['references'][i]['snaks'][ref_prop].pop(0)
                            if len(json['references'][i]['snaks'][ref_prop]) == 0:
                                json['references'][i]['snaks'].pop(ref_prop)
                                if len(json['references'][i]['snaks']) == 0:
                                    json['references'].pop(i)
                                    i -= 1
                            moved.add(ref_prop)

                if moved:
                    data = {'claims': [json]}
                    self.user_edit_entity(item, data, summary=self.makeSummary(prop, moved),
                                          asynchronous=True)

    def makeSummary(self, prop, props):
        props = [
            f'[[Property:P{pid}]]' for pid in sorted(int(pid[1:]) for pid in props)
        ]
        return '[[Property:%s]]: moving misplaced reference%s %s to qualifiers' % (
            prop,
            's' if len(props) > 1 else '',
            f"{', '.join(props[:-1])} and {props[-1]}"
            if len(props) > 1
            else props[0],
        )


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    site = pywikibot.Site('wikidata', 'wikidata')
    bot = QualifiersFixingBot(site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
