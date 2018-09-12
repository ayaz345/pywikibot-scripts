# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)

from queue import Queue
from threading import Lock, Thread

from .merger import Merger
from .query_store import QueryStore
from .wikidata import WikidataEntityBot
from scripts.revertbot import BaseRevertBot


class DupesMergingBot(WikidataEntityBot):

    dupe_items = {'Q1263068', 'Q17362920', 'Q20511493', 'Q28065731'}
    use_from_page = False

    def __init__(self, generator, offset=0, **kwargs):
        self.availableOptions.update({
            'threads': 1,
        })
        super(DupesMergingBot, self).__init__(**kwargs)
        self.offset = offset
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()
        self.save_lock = Lock()
        self.access_lock = Lock()
        self.site_locks = {}

    @property
    def generator(self):
        return PreloadingEntityGenerator(self._generator)

    def custom_generator(self):
        query = self.store.build_query(
            'dupes', dupe=' wd:'.join(self.dupe_items), offset=self.offset)
        return WikidataSPARQLPageGenerator(query, site=self.repo,
                                           result_type=list)

    def setup(self):
        super(DupesMergingBot, self).setup()
        count = self.getOption('threads')
        self.queue = Queue(count)
        self.workers = []
        for i in range(count):
            thread = Thread(target=self.work)
            thread.start()
            self.workers.append(thread)

    def get_lock_for(self, site):
        with self.access_lock:
            return self.site_locks.setdefault(site, Lock())

    def work(self):
        while True:
            item = self.queue.get()
            if item is None:
                break
            self.process_item(item)
            self.queue.task_done()

    def init_page(self, item):
        self.offset += 1
        return super(DupesMergingBot, self).init_page(item)

    def skip_page(self, item):
        return 'P31' not in item.claims or (
            super(DupesMergingBot, self).skip_page(item))

    def treat_page_and_item(self, page, item):
        self.queue.put(item)

    def process_item(self, item):
        claims = []
        targets = set()
        for claim in item.claims['P31']:
            if claim.snaktype != 'value':
                continue
            if claim.target.id not in self.dupe_items:
                continue
            claims.append(claim)
            for prop in ['P460', 'P642']:
                for snak in claim.qualifiers.get(prop, []):
                    if snak.snaktype == 'value':
                        targets.add(snak.getTarget())

        for claim in item.claims.get('P460', []):
            if claim.snaktype == 'value':
                claims.append(claim)
                targets.add(claim.getTarget())

        sitelinks = []
        if not targets:
            for page in item.iterlinks():
                site = page.site
                with self.get_lock_for(site):
                    if not page.exists():
                        sitelinks.append(site)
                        continue
                    if page.isRedirectPage():
                        try:
                            target = page.getRedirectTarget().data_item()
                        except pywikibot.NoPage:
                            pass
                        else:
                            targets.add(target)

        if not targets:
            pywikibot.output('No target found')
            return

        target = targets.pop()
        if targets:
            pywikibot.output('Multiple targets found')
            return

        while target.isRedirectPage():
            pywikibot.warning('Target %s is redirect' % target.getID())
            target = target.getRedirectTarget()

        if item == target:
            self._save_page(item, self._save_entity, item.removeClaims, claims)
            return

        target_sitelinks = []
        target.get()
        for page in item.iterlinks():
            site = page.site
            with self.get_lock_for(site):
                try:
                    target_link = target.getSitelink(site)
                except pywikibot.NoPage:
                    continue

                if not page.exists():
                    sitelinks.append(site)
                    continue

                target_page = pywikibot.Page(site, target_link)
                if not target_page.exists():
                    target_sitelinks.append(site)
                    continue
                if (self.redirectsTo(page, target_page) or
                        self.redirectsTo(target_page, page)):
                    continue

            pywikibot.output('Target has a conflicting sitelink: %s'
                             % site.dbName())
            return

        target_claims = []
        for claim in target.claims.get('P460', []):
            if claim.snaktype != 'value':
                continue
            if claim.target_equals(item):
                target_claims.append(claim)

        for claim in target.claims.get('P31', []):
            if claim.snaktype != 'value':
                continue
            if claim.target.id not in self.dupe_items:
                continue
            for prop in ['P460', 'P642']:
                for snak in claim.qualifiers.get(prop, []):
                    if snak.snaktype != 'value':
                        continue
                    if snak.target_equals(item):
                        target_claims.append(claim)

        if len(sitelinks) > 0:
            self._save_page(
                item, self._save_entity, item.removeSitelinks, sitelinks,
                summary='removing sitelink(s) to non-existing page(s)')
        if len(claims) > 0:
            self._save_page(item, self._save_entity, item.removeClaims, claims)
        if len(target_sitelinks) > 0:
            self._save_page(
                target, self._save_entity, target.removeSitelinks, target_sitelinks,
                summary='removing sitelink(s) to non-existing page(s)')
        if len(target_claims) > 0:
            self._save_page(
                target, self._save_entity, target.removeClaims, target_claims)

        if not self._save_page(
                item, self._save_entity, Merger.clean_merge, item, target,
                ignore_conflicts=['description']):
            pywikibot.output('Reverting changes...')
            bot = BaseRevertBot(self.site)  # todo: integrate to Merger
            bot.comment = 'Error occurred when attempting to merge with %s' % target.title(as_link=True)
            bot.revert({'title': item.title()})
            bot.comment = 'Error occurred when attempting to merge with %s' % item.title(as_link=True)
            bot.revert({'title': target.title()})
            return

        self.offset -= 1

    def redirectsTo(self, page, target):
        return page.isRedirectPage() and page.getRedirectTarget() == target

    def _save_entity(self, callback, *args, **kwargs):
        with self.save_lock:
            if 'asynchronous' in kwargs:
                kwargs.pop('asynchronous')
            return callback(*args, **kwargs)

    def teardown(self):
        count = len(self.workers)
        for i in range(count):
            self.queue.put(None)
        for worker in self.workers:
            worker.join()
        super(DupesMergingBot, self).teardown()

    def exit(self):
        super(DupesMergingBot, self).exit()
        pywikibot.output('\nCurrent offset: %i (use %i)\n' % (
            self.offset, self.offset - self.offset % 50))


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = GeneratorFactory(site=site)
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = DupesMergingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
